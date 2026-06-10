using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using Photon.Pun;
using UnityEngine;
using UnityEngine.Networking;

namespace CompetitiveRounds
{
    public static class ApiClient
    {
        private static string baseUrl = "";
        private static float lastFetchTime = 0f;
        private static float fetchCooldown = 5f; // Min seconds between refreshes

        // Cached data for UI
        public static LeaderboardData CachedLeaderboard { get; private set; }
        public static PlayerStatsData CachedPlayerStats { get; private set; }
        public static List<CardStatData> CachedCardStats { get; private set; }
        public static bool IsLoading { get; private set; } = false;
        public static string LastError { get; private set; } = "";

        // Version check
        public static string LatestModVersion { get; private set; } = null;
        public static string MinModVersion { get; private set; } = null;
        // Set when the server returns 426 to any request — UI hides everything and prompts update.
        public static bool ForceUpdateRequired { get; private set; } = false;

        // Recent ranked series (for leaderboard sidebar)
        public static List<RecentSeriesEntry> CachedRecentSeries { get; private set; }
        public class RecentSeriesEntry
        {
            public string winner_name;
            public string p1_name, p2_name;
            public int p1_wins, p2_wins;
            public int p1_rating, p2_rating;       // current Glicko ratings — for inline display
            public float p1_rating_change, p2_rating_change;
            public string winner_steam_id, p1_steam_id, p2_steam_id;
            public string completed_at;
            public List<SeriesBetEntry> bets = new List<SeriesBetEntry>();
        }

        public class SeriesBetEntry
        {
            public string bettor_name, bet_on_name, bettor_steam_id, bet_on_steam_id;
            public int amount;
            public int payout;        // 0 = lost, >amount = won (full credit)
            public float odds_multiplier;
            public bool won;
        }

        // ── Data classes ──────────────────────────────────────

        [Serializable]
        public class MatchResponse
        {
            public string match_id;
            public string winner_steam_id;
            public string message;
        }

        [Serializable]
        public class LeaderboardData
        {
            public LeaderboardEntry[] entries;
            public int total_players;
        }

        [Serializable]
        public class LeaderboardEntry
        {
            public int rank;
            public string steam_id;
            public string display_name;
            public int rating;
            public int rd;
            public int total_matches;
            public int wins;
            public int losses;
            public float win_rate;
            public int level;
            public int gold;
            public string title;
            public string title_color;
        }

        [Serializable]
        public class PlayerStatsData
        {
            public string steam_id;
            public string display_name;
            public float rating;
            public float rating_deviation;
            public float peak_rating;
            public int total_matches;
            public int wins;
            public int losses;
            public float win_rate;
            public bool ranked_enabled;
            public int level;
            public int total_xp;
            public int xp_into_level;
            public int xp_for_next_level;
            public int best_ranked_streak;
            public int best_casual_streak;
            public int ranked_series_wins;
            public int ranked_series_losses;
            public int ranked_dc_count;
            public string discord_id;
            public string discord_username;
            public int gold_earned;
            public int gold_spent;
            // Lifetime gun accuracy + block success counters (v1.23).
            public long bullets_fired;
            public long bullets_hit;
            public long blocks_activated;
            public long blocks_successful;
            public string active_title;
            public string active_title_color;
            public string active_trail_sku;
            public string active_trail_color;
            public int active_trail_price;
            public string active_color_sku;  // legacy single-active (first entry of active_color_skus)
            // Multi-equip map colors — player cycles between these in-game with Left Shift.
            // Empty list → no override, ArtHandler falls through to vanilla random rotation.
            public List<string> active_color_skus;
            // Player BODY color (kind=player_color). Single-equip; overrides team color.
            public string active_player_color_sku;
            public string active_player_color_hex;
            public string active_player_color_name;
            // Cursor color (kind=cursor_color). Single-equip, local-only render.
            public string active_cursor_color_sku;
            public string active_cursor_color_hex;
            // Player effect (kind=player_effect). Single-equip; Photon-synced particle aura.
            public string active_player_effect_sku;
            // Hide-gold utility toggle state. When true the leaderboard masks our gold.
            public bool hide_gold;
            // Stackable rich-text nametag styles by sku. Parsed manually (JsonUtility can't handle
            // string arrays without a wrapper class). Null or empty = no styling applied.
            public List<string> active_nametag_skus;

            // Parsed manually (JsonUtility can't handle nested arrays)
            public List<string> top_card_names;
            public List<int> top_card_picks;
            public List<float> top_card_win_rates;
            public List<string> recent_form; // "W","L","W"... last 20
            public List<float> rating_history; // oldest→newest
            // Compare-tab metrics (v1.28). Scalars parse free via JsonUtility;
            // worst_cards + region_breakdown are nested arrays parsed manually.
            public int avg_fps;
            public float avg_cards_per_game;
            public int achievements_unlocked;
            public List<string> worst_card_names;
            public List<int> worst_card_picks;
            public List<float> worst_card_win_rates;
            public List<string> region_names;   // e.g. "usw"
            public List<int> region_matches;    // parallel to region_names
            // Per-player mod version (server-tracked from X-Mod-Version header).
            public string mod_version;
            // Server-computed head-to-head against the local viewer
            // (passed via FetchPlayerStatsForView's viewer_steam_id query
            // param). Replaces the prior client-side H2H computation that
            // iterated the local match cache and missed older opponents.
            public int h2h_ranked_wins;
            public int h2h_ranked_losses;
            public int h2h_casual_wins;
            public int h2h_casual_losses;
            public int h2h_series_wins;
            public int h2h_series_losses;
        }

        [Serializable]
        public class CardStatData
        {
            public string card_name;
            public string card_rarity;
            public int times_picked;
            public int wins_with_card;
            public float win_rate;
            public int times_offered;
            public float pass_rate;
        }

        [Serializable]
        private class CardStatsWrapper
        {
            public CardStatData[] items;
        }

        [Serializable]
        public class ModCheckResponse
        {
            public bool registered;
            public bool ranked;
            public string display_name;
            public bool banned;
            public string ban_reason;
        }

        [Serializable]
        public class MatchHistoryEntry
        {
            public string match_id;
            public string opponent_steam_id;
            public string opponent_name;
            public string opponent_title;        // current active title shop_items.name
            public string opponent_title_color;  // hex like "#A040FF"
            public int player_rounds_won;
            public int opponent_rounds_won;
            public int player_points;
            public int opponent_points;
            public bool won;
            public bool is_ranked;
            public string ended_at;
            public string cards_display; // Comma-separated card names for display
            public string opp_cards_display; // Opponent's cards
            public string series_id; // For grouping matches into BO3 series
            public string series_score; // e.g. "2-0", "1-1"
            public float series_rating_change; // Elo change for completed series
            public int xp_gained; // XP earned for this match
            public int gold_gained; // Gold earned on this specific match (from XP crossings)
            public int series_gold_gained; // Gold earned from the series this match is part of (only set on the last-match-of-series row)
            // v1.25 average FPS. 0 = no data (row predates v1.25 OR opponent didn't have the mod).
            public int player_fps_avg;
            public int opponent_fps_avg;
        }

        [Serializable]
        private class MatchHistoryWrapper
        {
            public MatchHistoryEntry[] items;
        }

        // ── Achievement data ──────────────────────────────────

        [Serializable]
        public class AchievementData
        {
            public string achievement_key;
            public bool unlocked;
            public string unlocked_at; // ISO date or null
        }

        // Master definition list (mirrored from server)
        public static readonly Dictionary<string, string[]> AchievementDefs = new Dictionary<string, string[]>
        {
            {"untouchable",         new[]{"Untouchable",         "Win a game without taking any damage"}},
            {"silent_assassin",     new[]{"Silent Assassin",     "5-0 someone with Sneaky"}},
            {"total_mayhem",        new[]{"Total Mayhem",        "5-0 someone with Mayhem"}},
            {"fragile_perfection",  new[]{"Fragile Perfection",  "5-0 someone with Glass Cannon"}},
            {"no_escape",           new[]{"No Escape",           "5-0 someone with Chase"}},
            {"rise_from_the_ashes", new[]{"Rise from the Ashes", "Win 5-0 with Phoenix without losing a life"}},
            {"the_comeback_kid",    new[]{"The Comeback Kid",    "Win after being down 0-4"}},
            {"stacked_deck",        new[]{"Stacked Deck",        "Get 5 copies of one card in a game"}},
            {"regicide",            new[]{"Regicide",            "Win against Sid in a ranked series"}},
            {"pacifist",            new[]{"Pacifist",            "Win a game without firing a single shot"}},
            {"immovable_object",    new[]{"Immovable Object",    "Win a game without moving or jumping"}},
            {"master_rank",         new[]{"Master",              "Reach 2030 rating in ranked (1v1 or 2v2)"}},
            {"team_sweep",          new[]{"Tag Team Sweep",      "Win a 2v2 game 5-0"}},
        };

        // Cached data
        public static List<MatchHistoryEntry> CachedMatchHistory { get; private set; }
        public static Dictionary<string, AchievementData> CachedAchievements { get; private set; }

        // ── Initialization ────────────────────────────────────

        public static void Initialize(string url)
        {
            baseUrl = url.TrimEnd('/');
            Plugin.Log.LogInfo($"API client initialized: {baseUrl}");
            CheckModVersion();
            // Start the tournament heartbeat loop. This runs forever and fires
            // ready-up heartbeats any time the player has an active tournament
            // match — regardless of which UI tab is open or whether the
            // competitive page is even visible. Needed because sync matches
            // happen in ROUNDS gameplay (outside the F5 menu), and without
            // this the player's ready_at would go stale during their match
            // and the server would auto-forfeit their NEXT match.
            Plugin.Instance.StartCoroutine(TournamentHeartbeatLoop());
        }

        // Per-match dispatch memo. Mirrors the per-tab one in NativeUI but
        // lives at plugin scope so the loop doesn't re-fire SetPendingRoom
        // every 20 seconds for the same match. Reset implicitly when the
        // match transitions out of "ready" (server stops returning it).
        private static readonly HashSet<string> _heartbeatDispatchedMatches = new HashSet<string>();

        private static IEnumerator TournamentHeartbeatLoop()
        {
            // Small initial delay so the mod finishes initializing before the
            // first call tries to resolve the local Steam ID.
            yield return new WaitForSeconds(10f);
            while (true)
            {
                yield return new WaitForSeconds(20f);
                string sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid) || sid == "unknown") continue;
                // Pull fresh active-match state. FetchMyActiveTournamentMatches
                // has its own 20s throttle so back-to-back calls are safe.
                FetchMyActiveTournamentMatches(sid);
                if (CachedMyActiveTournamentMatches == null) continue;
                // Heartbeat each tournament once per loop (dedupe by tournament_id
                // in case the player has multiple active matches somehow).
                var seen = new HashSet<string>();
                foreach (var m in CachedMyActiveTournamentMatches)
                {
                    if (string.IsNullOrEmpty(m.tournament_id) || seen.Contains(m.tournament_id)) continue;
                    seen.Add(m.tournament_id);
                    TournamentReady(m.tournament_id, sid);
                    yield return new WaitForSeconds(0.2f); // space the requests

                    // Tab-independent auto-connect dispatch. The Tournament
                    // tab's RefreshTournaments has the same logic, but it
                    // ONLY runs when the user is on tab 7 with the F5 menu
                    // open — meanwhile sync tournament matches need to
                    // start from in-game (F5 closed). Without this branch
                    // the auto-connect silently fails and the player
                    // forfeits the 5-min window.
                    bool isSyncReady = m.kind == "sync"
                        && m.status == "ready"
                        && m.my_ready
                        && m.opp_ready
                        && !string.IsNullOrEmpty(m.photon_room_name)
                        && !string.IsNullOrEmpty(m.match_id);
                    if (isSyncReady && !_heartbeatDispatchedMatches.Contains(m.match_id))
                    {
                        if (Plugin.PendingRankedRoom != m.photon_room_name)
                        {
                            _heartbeatDispatchedMatches.Add(m.match_id);
                            Plugin.SetPendingRoom(m.photon_room_name, m.photon_region);
                            Plugin.Log.LogInfo($"[TOURNAMENT-HB] Dispatch from heartbeat loop: room={m.photon_room_name} region={m.photon_region ?? "default"} match={m.match_id}");
                        }
                    }
                }
                // Drop any memo entries whose matches no longer appear —
                // lets a re-ready (e.g., player relaunched the game) fire
                // SetPendingRoom again.
                if (CachedMyActiveTournamentMatches.Count == 0)
                {
                    _heartbeatDispatchedMatches.Clear();
                }
                else
                {
                    var stillActive = new HashSet<string>();
                    foreach (var m in CachedMyActiveTournamentMatches)
                        if (!string.IsNullOrEmpty(m.match_id)) stillActive.Add(m.match_id);
                    _heartbeatDispatchedMatches.RemoveWhere(id => !stillActive.Contains(id));
                }
            }
        }

        public static void CheckModVersion()
        {
            Plugin.Instance.StartCoroutine(DoCheckModVersion());
        }

        private static IEnumerator DoCheckModVersion()
        {
            var req = UnityWebRequest.Get($"{baseUrl}/api/v1/mod-version");
            yield return req.SendWebRequest();
            if (req.result == UnityWebRequest.Result.Success)
            {
                string ver = ExtractJsonString(req.downloadHandler.text, "version");
                string minVer = ExtractJsonString(req.downloadHandler.text, "min_version");
                if (!string.IsNullOrEmpty(ver))
                {
                    LatestModVersion = ver;
                    if (ver != Plugin.ModVersion)
                        Plugin.Log.LogWarning($"[VERSION] Update available: v{Plugin.ModVersion} → v{ver}");
                    else
                        Plugin.Log.LogInfo($"[VERSION] Mod is up to date (v{ver})");
                }
                if (!string.IsNullOrEmpty(minVer))
                {
                    MinModVersion = minVer;
                    if (CompareVersion(Plugin.ModVersion, minVer) < 0)
                    {
                        ForceUpdateRequired = true;
                        Plugin.Log.LogWarning($"[VERSION] Mod is BELOW server minimum (v{Plugin.ModVersion} < v{minVer}) — update required");
                    }
                }
                // Auto-fire update on launch if behind. The Update method is no-op
                // when running the Thunderstore build (it surfaces a notification only).
                if (!string.IsNullOrEmpty(LatestModVersion) && CompareVersion(Plugin.ModVersion, LatestModVersion) < 0
                    && !IsUpdating && !UpdateReady)
                {
                    Plugin.Log.LogInfo("[VERSION] Auto-firing update on launch");
                    StartAutoUpdate();
                }
            }
        }

        /// <summary>Returns -1 / 0 / +1 by dotted-int component comparison. Treats parse failures as 0.</summary>
        private static int CompareVersion(string a, string b)
        {
            if (string.IsNullOrEmpty(a) || string.IsNullOrEmpty(b)) return 0;
            var ap = a.Split('.'); var bp = b.Split('.');
            int n = Math.Max(ap.Length, bp.Length);
            for (int i = 0; i < n; i++)
            {
                int.TryParse(i < ap.Length ? ap[i] : "0", out int ai);
                int.TryParse(i < bp.Length ? bp[i] : "0", out int bi);
                if (ai != bi) return ai < bi ? -1 : 1;
            }
            return 0;
        }

        // ── Auto-Update ─────────────────────────────────────────

        public static bool IsUpdating { get; private set; } = false;
        public static bool UpdateReady { get; private set; } = false;
        private const string GITHUB_API_LATEST = "https://api.github.com/repos/SidNDeed/SidsCompetitiveRounds/releases/latest";

        public static void StartAutoUpdate()
        {
            if (IsUpdating || UpdateReady) return;
            IsUpdating = true;
            Plugin.Instance.StartCoroutine(DoAutoUpdate());
        }

        private static IEnumerator DoAutoUpdate()
        {
#if THUNDERSTORE
            Plugin.Log.LogInfo("[UPDATE] Thunderstore build — auto-update disabled, use mod manager");
            CompetitiveUI.ShowNotification("Update available — update through your mod manager", Color.cyan, 6f);
            IsUpdating = false;
            NativeUI.MarkDirty();
            yield break;
#else
            CompetitiveUI.ShowNotification("Downloading update...", Color.cyan, 10f);
            NativeUI.MarkDirty();

            // Step 1: Get latest release info from GitHub
            var apiReq = UnityWebRequest.Get(GITHUB_API_LATEST);
            apiReq.SetRequestHeader("User-Agent", "CompetitiveRounds-AutoUpdate");
            apiReq.timeout = 15;
            yield return apiReq.SendWebRequest();

            if (apiReq.result != UnityWebRequest.Result.Success)
            {
                Plugin.Log.LogWarning($"[UPDATE] GitHub API failed: {apiReq.error}");
                CompetitiveUI.ShowNotification("Update failed — could not reach GitHub", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            string json = apiReq.downloadHandler.text;

            // Step 2: Find the DLL asset URL
            string dllUrl = null;
            var matches = Regex.Matches(json, @"""browser_download_url""\s*:\s*""([^""]+\.dll)""");
            foreach (Match m in matches)
            {
                if (m.Groups[1].Value.IndexOf("CompetitiveRounds", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    dllUrl = m.Groups[1].Value;
                    break;
                }
            }
            if (dllUrl == null && matches.Count > 0)
                dllUrl = matches[0].Groups[1].Value;

            // Fallback: try zip
            if (dllUrl == null)
            {
                var zipMatches = Regex.Matches(json, @"""browser_download_url""\s*:\s*""([^""]+\.zip)""");
                if (zipMatches.Count > 0)
                {
                    // Can't easily unzip in Unity — fall back to opening browser
                    Plugin.Log.LogWarning("[UPDATE] No DLL asset found, only zip. Opening browser.");
                    CompetitiveUI.ShowNotification("No DLL found — opening releases page", Color.yellow, 5f);
                    Application.OpenURL("https://github.com/SidNDeed/SidsCompetitiveRounds/releases/latest");
                    IsUpdating = false;
                    yield break;
                }
                Plugin.Log.LogWarning("[UPDATE] No downloadable assets found in release");
                CompetitiveUI.ShowNotification("Update failed — no assets in release", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            Plugin.Log.LogInfo($"[UPDATE] Downloading: {dllUrl}");

            // Step 3: Download the DLL to temp
            string tempPath = Path.Combine(Path.GetTempPath(), "CompetitiveRounds_update.dll");
            var dlReq = UnityWebRequest.Get(dllUrl);
            dlReq.SetRequestHeader("User-Agent", "CompetitiveRounds-AutoUpdate");
            dlReq.timeout = 30;
            dlReq.downloadHandler = new DownloadHandlerFile(tempPath);
            yield return dlReq.SendWebRequest();

            if (dlReq.result != UnityWebRequest.Result.Success)
            {
                Plugin.Log.LogWarning($"[UPDATE] Download failed: {dlReq.error}");
                CompetitiveUI.ShowNotification("Update failed — download error", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            Plugin.Log.LogInfo($"[UPDATE] Downloaded to: {tempPath}");

            // Step 4: Find where the current DLL lives
            string currentDll = "";
            try
            {
                currentDll = System.Reflection.Assembly.GetExecutingAssembly().Location;
            }
            catch { }

            if (string.IsNullOrEmpty(currentDll) || !File.Exists(currentDll))
            {
                // Fallback: use BepInEx.Paths.PluginPath (works for both vanilla and Thunderstore profiles)
                string bepPlugins = "";
                try { bepPlugins = BepInEx.Paths.PluginPath; } catch { }

                if (!string.IsNullOrEmpty(bepPlugins) && Directory.Exists(bepPlugins))
                {
                    // Search subdirectories first (e.g. plugins/CompetitiveRounds/ or plugins/SidNDeed-CompetitiveRounds/)
                    try
                    {
                        foreach (string dir in Directory.GetDirectories(bepPlugins))
                        {
                            string candidate = Path.Combine(dir, "CompetitiveRounds.dll");
                            if (File.Exists(candidate)) { currentDll = candidate; break; }
                        }
                    }
                    catch { }

                    // Also check plugins root
                    if (string.IsNullOrEmpty(currentDll) || !File.Exists(currentDll))
                    {
                        string root = Path.Combine(bepPlugins, "CompetitiveRounds.dll");
                        if (File.Exists(root)) currentDll = root;
                    }
                }

                // Last resort: vanilla hardcoded path
                if (string.IsNullOrEmpty(currentDll) || !File.Exists(currentDll))
                {
                    string vanillaPlugins = Path.Combine(Application.dataPath, "..", "BepInEx", "plugins");
                    string sub = Path.Combine(vanillaPlugins, "CompetitiveRounds", "CompetitiveRounds.dll");
                    string rootV = Path.Combine(vanillaPlugins, "CompetitiveRounds.dll");
                    if (File.Exists(sub)) currentDll = sub;
                    else if (File.Exists(rootV)) currentDll = rootV;
                }
            }

            Plugin.Log.LogInfo($"[UPDATE] Resolved DLL path: {currentDll}");

            if (string.IsNullOrEmpty(currentDll) || !File.Exists(currentDll))
            {
                Plugin.Log.LogWarning("[UPDATE] Could not locate current DLL");
                CompetitiveUI.ShowNotification("Update failed — can't find current DLL", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            // Step 5: Write batch script that waits for ROUNDS to exit, then swaps the file
            string batPath = Path.Combine(Path.GetTempPath(), "CompetitiveRounds_update.bat");
            string batContent =
                "@echo off\r\n" +
                "echo Waiting for ROUNDS to close...\r\n" +
                ":wait\r\n" +
                "tasklist /FI \"IMAGENAME eq Rounds.exe\" 2>NUL | find /I \"Rounds.exe\" >NUL\r\n" +
                "if %ERRORLEVEL%==0 (\r\n" +
                "    timeout /t 2 /nobreak >NUL\r\n" +
                "    goto wait\r\n" +
                ")\r\n" +
                "timeout /t 1 /nobreak >NUL\r\n" +
                $"copy /Y \"{tempPath}\" \"{currentDll}\"\r\n" +
                "if %ERRORLEVEL%==0 (\r\n" +
                "    echo Update complete!\r\n" +
                ") else (\r\n" +
                "    echo Update failed - could not copy file.\r\n" +
                "    pause\r\n" +
                "    exit /b 1\r\n" +
                ")\r\n" +
                $"del \"{tempPath}\"\r\n" +
                $"del \"%~f0\"\r\n";

            try
            {
                File.WriteAllText(batPath, batContent);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[UPDATE] Failed to write batch script: {ex.Message}");
                CompetitiveUI.ShowNotification("Update failed — could not write updater", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            // Step 6: Launch the batch script hidden
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = batPath,
                    CreateNoWindow = true,
                    UseShellExecute = false,
                    WindowStyle = ProcessWindowStyle.Hidden,
                };
                Process.Start(psi);
                Plugin.Log.LogInfo("[UPDATE] Updater launched — will apply after ROUNDS closes");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[UPDATE] Failed to launch updater: {ex.Message}");
                CompetitiveUI.ShowNotification("Update failed — could not launch updater", new Color(1f, 0.4f, 0.4f), 5f);
                IsUpdating = false;
                yield break;
            }

            UpdateReady = true;
            IsUpdating = false;
            CompetitiveUI.ShowNotification("Update downloaded! Close ROUNDS to apply.", new Color(0.3f, 1f, 0.3f), 15f);
            NativeUI.MarkDirty();
#endif
        }

        // ── HMAC Match Signing ────────────────────────────────

        // Obfuscated key (XOR encoded — not plain string in DLL)
        private static readonly byte[] _hkE = {0xE2,0x60,0x7D,0x46,0xD1,0x1D,0xAE,0xD4,0xF3,0x33,0x3C,0x2F,0x47,0xED,0x9A,0x32,0xD7,0x6A,0x0B,0x18,0xA5,0x04,0xE3,0xEC,0xDC,0x50,0x22,0x18,0x15,0xA6,0xE7,0x2E,0xD8,0x46,0x03,0x33,0xA7,0x5A,0xD1,0xD1,0xFD,0x78,0x1C,0x3A,0x02,0x90,0xEF,0x2D};
        private static readonly byte[] _hkX = {0xB2,0x19,0x4F,0x77,0xE6,0x6F,0x96,0xB5,0xBA,0x0A,0x6A,0x5F,0x77,0xDF,0xAE,0x4B};

        private static byte[] GetHmacKeyBytes()
        {
            byte[] result = new byte[_hkE.Length];
            for (int i = 0; i < _hkE.Length; i++)
                result[i] = (byte)(_hkE[i] ^ _hkX[i % _hkX.Length]);
            return result;
        }

        private static string ComputeHmac(string p1SteamId, string p2SteamId,
            int p1Rounds, int p2Rounds, bool isRanked,
            string reporterSteamId, string roomId)
        {
            string message = $"{p1SteamId}:{p2SteamId}:{p1Rounds}:{p2Rounds}:" +
                             $"{(isRanked ? "true" : "false")}:{reporterSteamId}:{roomId ?? ""}";
            try
            {
                using (var hmac = new HMACSHA256(GetHmacKeyBytes()))
                {
                    byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(message));
                    var sb = new StringBuilder(hash.Length * 2);
                    foreach (byte b in hash) sb.Append(b.ToString("x2"));
                    return sb.ToString();
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[HMAC] Computation failed: {ex.Message}");
                return "";
            }
        }

        private static string ComputeHmacHex(string message)
        {
            try
            {
                using (var hmac = new HMACSHA256(GetHmacKeyBytes()))
                {
                    byte[] hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(message));
                    var sb = new StringBuilder(hash.Length * 2);
                    foreach (byte b in hash) sb.Append(b.ToString("x2"));
                    return sb.ToString();
                }
            }
            catch { return ""; }
        }

        // ── Betting / Live series ────────────────────────────────
        [Serializable]
        public class ActiveSeriesEntry
        {
            public string series_id;
            public string p1_steam_id, p1_name;
            public int p1_rating, p1_wins;
            public float p1_odds;
            public string p2_steam_id, p2_name;
            public int p2_rating, p2_wins;
            public float p2_odds;
            public int live_p1_points, live_p2_points;
            public bool bets_locked;
            public string lock_reason;  // "tournament" | "private_room" | "game_in_progress" | "no_meaningful_odds" | null
            public bool is_private;
            public bool is_tournament;
            public string tournament_kind; // "sync" | "async" | null
            public string phase; // "pre_match" | "live"
        }

        public class MyBetEntry
        {
            public string series_id, bet_on_steam_id, bet_on_name, series_status, series_score;
            public int amount;
            public float odds_multiplier;
        }

        public static List<ActiveSeriesEntry> CachedActiveSeries { get; private set; }
        public static List<MyBetEntry> CachedMyBets { get; private set; } = new List<MyBetEntry>();

        public static void FetchActiveSeries()
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/series/active",
                (ok, resp) =>
                {
                    if (!ok) return;
                    var list = new List<ActiveSeriesEntry>();
                    try
                    {
                        var parts = resp.Split(new[] { "\"series_id\":" }, StringSplitOptions.None);
                        for (int i = 1; i < parts.Length; i++)
                        {
                            string chunk = "\"series_id\":" + parts[i];
                            var e = new ActiveSeriesEntry();
                            e.series_id    = ExtractJsonString(chunk, "series_id");
                            e.p1_steam_id  = ExtractJsonString(chunk, "p1_steam_id");
                            e.p1_name      = ExtractJsonString(chunk, "p1_name");
                            e.p1_rating    = ExtractJsonInt(chunk, "p1_rating");
                            e.p1_wins      = ExtractJsonInt(chunk, "p1_wins");
                            e.p1_odds      = ExtractJsonFloat(chunk, "p1_odds");
                            e.p2_steam_id  = ExtractJsonString(chunk, "p2_steam_id");
                            e.p2_name      = ExtractJsonString(chunk, "p2_name");
                            e.p2_rating    = ExtractJsonInt(chunk, "p2_rating");
                            e.p2_wins      = ExtractJsonInt(chunk, "p2_wins");
                            e.p2_odds      = ExtractJsonFloat(chunk, "p2_odds");
                            e.live_p1_points = ExtractJsonInt(chunk, "live_p1_points");
                            e.live_p2_points = ExtractJsonInt(chunk, "live_p2_points");
                            e.bets_locked   = chunk.Contains("\"bets_locked\":true") || chunk.Contains("\"bets_locked\": true");
                            e.lock_reason   = ExtractJsonString(chunk, "lock_reason");
                            e.is_private    = chunk.Contains("\"is_private\":true") || chunk.Contains("\"is_private\": true");
                            e.is_tournament = chunk.Contains("\"is_tournament\":true") || chunk.Contains("\"is_tournament\": true");
                            e.tournament_kind = ExtractJsonString(chunk, "tournament_kind");
                            e.phase           = ExtractJsonString(chunk, "phase");
                            if (!string.IsNullOrEmpty(e.series_id)) list.Add(e);
                        }
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[BET] active-series parse: {ex.Message}"); }
                    CachedActiveSeries = list;
                    NativeUI.MarkDirty();
                }
            ));
        }

        // Fetches the local player's recent bets so the live-series UI can replace the wager
        // buttons with "You bet 500g on PlayerName" once a bet is placed (server enforces one
        // bet per series per player; this is purely the visible feedback).
        public static void FetchMyBets(string steamId)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}/bets?limit=50",
                (ok, resp) =>
                {
                    if (!ok) return;
                    var list = new List<MyBetEntry>();
                    try
                    {
                        var parts = resp.Split(new[] { "\"id\":" }, StringSplitOptions.None);
                        for (int i = 1; i < parts.Length; i++)
                        {
                            string chunk = parts[i];
                            var b = new MyBetEntry();
                            b.amount         = ExtractJsonInt(chunk, "amount");
                            b.odds_multiplier= ExtractJsonFloat(chunk, "odds_multiplier");
                            b.series_id      = ExtractJsonString(chunk, "series_id");
                            b.bet_on_steam_id= ExtractJsonString(chunk, "bet_on_steam_id");
                            b.bet_on_name    = ExtractJsonString(chunk, "bet_on_name");
                            b.series_status  = ExtractJsonString(chunk, "series_status");
                            b.series_score   = ExtractJsonString(chunk, "series_score");
                            if (!string.IsNullOrEmpty(b.series_id)) list.Add(b);
                        }
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[BET] my-bets parse: {ex.Message}"); }
                    CachedMyBets = list;
                    NativeUI.MarkDirty();
                }
            ));
        }

        public static MyBetEntry GetMyBetForSeries(string seriesId)
        {
            if (string.IsNullOrEmpty(seriesId) || CachedMyBets == null) return null;
            foreach (var b in CachedMyBets) if (b.series_id == seriesId) return b;
            return null;
        }

        /// <summary>Report current game-1 point counts on a live ranked series. The server uses
        /// these to lock betting once 2+ points have been scored. Fire-and-forget; failures are
        /// logged but don't block gameplay. HMAC over "live-points:{series}:{reporter}:{p1}:{p2}".</summary>
        public static void PostLivePoints(string seriesId, string reporterSteamId, int p1Points, int p2Points)
        {
            if (string.IsNullOrEmpty(seriesId) || string.IsNullOrEmpty(reporterSteamId)) return;
            string sig = ComputeHmacHex($"live-points:{seriesId}:{reporterSteamId}:{p1Points}:{p2Points}");
            string url = $"{baseUrl}/api/v1/series/{Escape(seriesId)}/live-points" +
                         $"?p1_points={p1Points}&p2_points={p2Points}" +
                         $"&reporter_steam_id={Escape(reporterSteamId)}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[LIVE-POINTS] series={seriesId.Substring(0, Math.Min(8, seriesId.Length))} {p1Points}-{p2Points} ok={ok}");
            }));
        }

        /// <summary>Place a bet. HMAC over "bet:{bettor}:{series_id}:{bet_on}:{amount}".</summary>
        public static void PlaceBet(string bettorSteamId, string seriesId, string betOnSteamId, int amount, Action<bool, string> callback)
        {
            string sig = ComputeHmacHex($"bet:{bettorSteamId}:{seriesId}:{betOnSteamId}:{amount}");
            string url = $"{baseUrl}/api/v1/bets?steam_id={Escape(bettorSteamId)}&series_id={Escape(seriesId)}&bet_on_steam_id={Escape(betOnSteamId)}&amount={amount}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[BET] place {amount} on {betOnSteamId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok)
                {
                    FetchPlayerStats(bettorSteamId);
                    FetchActiveSeries();
                }
            }));
        }

        // ── 2v2 betting ──────────────────────────────────────────
        // Active 2v2 series, list-of-my-bets, and place-bet endpoints all
        // mirror the 1v1 shape — mostly used by the Live Series UI in the
        // Leaderboard tab. UI rendering for these is on the next pass.
        [Serializable]
        public class ActiveTeamSeriesEntry
        {
            public string series_id;
            public string t1a_steam, t1a_name, t1b_steam, t1b_name;
            public string t2a_steam, t2a_name, t2b_steam, t2b_name;
            public int t1_rating, t2_rating;          // team-average (used for odds context)
            public int t1a_rating, t1b_rating, t2a_rating, t2b_rating;  // per-player 2v2 ratings
            public int t1_wins, t2_wins;
            public float t1_odds, t2_odds;
            public bool bets_locked;
            public string lock_reason;
            public string started_at;
            public string dc_grace_until;
        }
        public static List<ActiveTeamSeriesEntry> CachedActiveTeamSeries { get; private set; } = new List<ActiveTeamSeriesEntry>();

        public static void FetchActiveTeamSeries()
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/series/active",
                (success, response) =>
                {
                    if (!success) return;
                    try { ParseActiveTeamSeries(response); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[TEAM-BET] active parse: {ex.Message}"); }
                }));
        }

        private static void ParseActiveTeamSeries(string response)
        {
            var list = new List<ActiveTeamSeriesEntry>();
            int sStart = response.IndexOf("\"series\"");
            if (sStart < 0) { CachedActiveTeamSeries = list; return; }
            int arrStart = response.IndexOf('[', sStart);
            int arrEnd = FindMatchingBracket(response, arrStart);
            if (arrStart < 0 || arrEnd < 0) { CachedActiveTeamSeries = list; return; }
            string slice = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
            int oIdx = 0;
            while (oIdx < slice.Length)
            {
                int objStart = slice.IndexOf('{', oIdx);
                if (objStart < 0) break;
                int oDepth = 1, j = objStart + 1;
                while (j < slice.Length && oDepth > 0)
                {
                    if (slice[j] == '{') oDepth++;
                    else if (slice[j] == '}') oDepth--;
                    j++;
                }
                if (oDepth != 0) break;
                string obj = slice.Substring(objStart, j - objStart);
                list.Add(new ActiveTeamSeriesEntry
                {
                    series_id = ExtractJsonString(obj, "series_id"),
                    t1a_steam = ExtractJsonString(obj, "t1a_steam"),
                    t1a_name  = ExtractJsonString(obj, "t1a_name"),
                    t1b_steam = ExtractJsonString(obj, "t1b_steam"),
                    t1b_name  = ExtractJsonString(obj, "t1b_name"),
                    t2a_steam = ExtractJsonString(obj, "t2a_steam"),
                    t2a_name  = ExtractJsonString(obj, "t2a_name"),
                    t2b_steam = ExtractJsonString(obj, "t2b_steam"),
                    t2b_name  = ExtractJsonString(obj, "t2b_name"),
                    t1_rating = ExtractJsonInt(obj, "t1_rating"),
                    t2_rating = ExtractJsonInt(obj, "t2_rating"),
                    t1a_rating = ExtractJsonInt(obj, "t1a_rating"),
                    t1b_rating = ExtractJsonInt(obj, "t1b_rating"),
                    t2a_rating = ExtractJsonInt(obj, "t2a_rating"),
                    t2b_rating = ExtractJsonInt(obj, "t2b_rating"),
                    t1_wins   = ExtractJsonInt(obj, "t1_wins"),
                    t2_wins   = ExtractJsonInt(obj, "t2_wins"),
                    t1_odds   = ExtractJsonFloat(obj, "t1_odds"),
                    t2_odds   = ExtractJsonFloat(obj, "t2_odds"),
                    bets_locked = ExtractJsonBool(obj, "bets_locked"),
                    lock_reason = ExtractJsonString(obj, "lock_reason"),
                    started_at = ExtractJsonString(obj, "started_at"),
                    dc_grace_until = ExtractJsonString(obj, "dc_grace_until"),
                });
                oIdx = j;
            }
            CachedActiveTeamSeries = list;
        }

        public static void PlaceTeamBet(string bettorSteamId, string seriesId, int betOnTeam, int amount, Action<bool, string> callback)
        {
            string sig = ComputeHmacHex($"team-bet:{bettorSteamId}:{seriesId}:{betOnTeam}:{amount}");
            string url = $"{baseUrl}/api/v1/team-bets?steam_id={Escape(bettorSteamId)}&team_series_id={Escape(seriesId)}&bet_on_team={betOnTeam}&amount={amount}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[TEAM-BET] place {amount} on team {betOnTeam}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok)
                {
                    FetchPlayerStats(bettorSteamId);
                    FetchActiveTeamSeries();
                }
            }));
        }


        // ── Shop ─────────────────────────────────────────────────
        [Serializable]
        public class ShopItemData
        {
            public long id;
            public string sku;
            public string kind;
            public string name;
            public string description;
            public int price;
            public string rarity;
            public string preview_color;
            public bool owned;
        }

        public static List<ShopItemData> CachedShopItems { get; private set; }
        public static List<ShopItemData> CachedInventory { get; private set; }

        public static void FetchShopItems(string steamId = null)
        {
            string url = $"{baseUrl}/api/v1/shop/items";
            if (!string.IsNullOrEmpty(steamId)) url += $"?steam_id={Escape(steamId)}";
            Plugin.Instance.StartCoroutine(GetRequest(url, (success, response) =>
            {
                if (!success) { Plugin.Log.LogWarning($"[SHOP] list failed: {response}"); return; }
                CachedShopItems = ParseShopItems(response);
                Plugin.Log.LogInfo($"[SHOP] loaded {CachedShopItems.Count} items");
                NativeUI.MarkDirty();
            }));
        }

        public static void FetchInventory(string steamId)
        {
            if (string.IsNullOrEmpty(steamId)) return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}/inventory",
                (success, response) =>
                {
                    if (!success) return;
                    CachedInventory = ParseShopItems(response);
                    NativeUI.MarkDirty();
                }));
        }

        /// <summary>Purchase. HMAC over "buy:{steam_id}:{sku}".</summary>
        public static void PurchaseItem(string steamId, string sku, Action<bool, string> callback)
        {
            Plugin.Log.LogInfo($"[SHOP] PurchaseItem ENTRY sku={sku} steamId={steamId}");
            try
            {
                string sig = ComputeHmacHex($"buy:{steamId}:{sku}");
                Plugin.Log.LogInfo($"[SHOP] sig computed ({sig?.Length ?? 0} chars)");
                string url = $"{baseUrl}/api/v1/shop/purchase?steam_id={steamId}&sku={sku}&sig={sig}";
                Plugin.Log.LogInfo($"[SHOP] POST {url.Substring(0, Math.Min(url.Length, 100))}...");
                Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
                {
                    Plugin.Log.LogInfo($"[SHOP] purchase callback {sku}: ok={ok} resp={(resp != null && resp.Length > 120 ? resp.Substring(0, 120) + "..." : resp)}");
                    try { callback?.Invoke(ok, resp); } catch (Exception cex) { Plugin.Log.LogWarning($"[SHOP] callback threw: {cex.Message}"); }
                    if (ok)
                    {
                        FetchPlayerStats(steamId);
                        FetchShopItems(steamId);
                        FetchInventory(steamId);
                    }
                }));
                Plugin.Log.LogInfo("[SHOP] coroutine dispatched");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[SHOP] PurchaseItem threw: {ex}");
                try { callback?.Invoke(false, ex.Message); } catch { }
            }
        }

        /// <summary>Set / clear active title. HMAC over "title:{steam_id}:{item_id or 0}".</summary>
        public static void SetActiveTitle(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"title:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-title?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set title {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Set / clear active trail. HMAC over "trail:{steam_id}:{item_id or 0}".</summary>
        public static void SetActiveTrail(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"trail:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-trail?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set trail {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        public static void SetActiveColor(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"color:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-color?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set color {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Equip / unequip a player body color (kind=player_color). itemId=0
        /// clears the current selection. HMAC over "player_color:{steam_id}:{item_id}".</summary>
        public static void SetActivePlayerColor(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"player_color:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-player-color?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set player_color {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Equip / unequip a cursor color (kind=cursor_color). itemId=0 clears.
        /// HMAC over "cursor_color:{steam_id}:{item_id}".</summary>
        public static void SetActiveCursorColor(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"cursor_color:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-cursor-color?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set cursor_color {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Equip / unequip a player effect (kind=player_effect). itemId=0 clears.
        /// HMAC over "player_effect:{steam_id}:{item_id}".</summary>
        public static void SetActivePlayerEffect(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"player_effect:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/active-player-effect?sig={sig}";
            if (itemId > 0) url += $"&item_id={itemId}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set player_effect {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Toggle the hide-gold leaderboard mask on/off. Requires owning the
        /// Hide Gold utility. HMAC over "hide_gold:{steam_id}:{1|0}".</summary>
        public static void SetHideGold(string steamId, bool on, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"hide_gold:{steamId}:{(on ? 1 : 0)}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/hide-gold?on={(on ? "true" : "false")}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] set hide_gold {on}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) { FetchPlayerStats(steamId); FetchLeaderboard(); }
            }));
        }

        /// <summary>Toggle a nametag rich-text style on/off. Stackable — multiple styles can be active.
        /// HMAC over "nametag:{steam_id}:{item_id}".</summary>
        public static void ToggleNametagStyle(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"nametag:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/nametag-toggle?item_id={itemId}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] toggle nametag {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        /// <summary>Toggle a map color in the player's active_color_ids list. Multi-equip;
        /// player cycles between equipped colors in-game with Left Shift. HMAC over
        /// "color:{steam_id}:{item_id}". Distinct from the legacy SetActiveColor (single-
        /// active, HMAC "color:{steam_id}:{item_id}" happens to match but hits different
        /// endpoint) — new clients should always use this toggle path.</summary>
        public static void ToggleMapColor(string steamId, long itemId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"color:{steamId}:{itemId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/color-toggle?item_id={itemId}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                Plugin.Log.LogInfo($"[SHOP] toggle color {itemId}: ok={ok} resp={resp}");
                callback?.Invoke(ok, resp);
                if (ok) FetchPlayerStats(steamId);
            }));
        }

        private static List<ShopItemData> ParseShopItems(string response)
        {
            var list = new List<ShopItemData>();
            if (string.IsNullOrEmpty(response)) return list;
            // Split by item object boundary.
            var parts = response.Split(new[] { "{\"id\":" }, StringSplitOptions.None);
            for (int i = 1; i < parts.Length; i++)
            {
                string chunk = "{\"id\":" + parts[i];
                var it = new ShopItemData();
                it.id = ExtractJsonInt(chunk, "id");
                it.sku = ExtractJsonString(chunk, "sku");
                it.kind = ExtractJsonString(chunk, "kind");
                it.name = ExtractJsonString(chunk, "name");
                it.description = ExtractJsonString(chunk, "description");
                it.price = ExtractJsonInt(chunk, "price");
                it.rarity = ExtractJsonString(chunk, "rarity");
                it.preview_color = ExtractJsonString(chunk, "preview_color");
                it.owned = ExtractJsonBool(chunk, "owned");
                if (!string.IsNullOrEmpty(it.sku) || !string.IsNullOrEmpty(it.name))
                    list.Add(it);
            }
            return list;
        }


        /// <summary>Pulls recent chat scrollback so the log isn't empty on a fresh connect.
        /// Each entry dispatches through ChatClient.OnMessage to share the render path.</summary>
        public static void FetchRecentChat(int limit = 50)
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/chat/recent?limit={limit}",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try
                    {
                        // Response: {"messages":[{"source":..., "message":..., ...}, ...]}
                        // Split on "source": marker so each object is one OnMessage call.
                        var parts = response.Split(new[] { "{\"source\"" }, StringSplitOptions.None);
                        for (int i = 1; i < parts.Length; i++)
                        {
                            string chunk = "{\"source\"" + parts[i];
                            // Trim to closing brace (crude but matches existing parsers)
                            int close = chunk.IndexOf("\"}");
                            if (close < 0) continue;
                            string obj = chunk.Substring(0, close + 2);
                            try { ChatClient.OnMessage?.Invoke(obj); } catch { }
                        }
                        Plugin.Log.LogInfo($"[CHAT] Scrollback loaded: {parts.Length - 1} messages");
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[CHAT] Scrollback parse error: {ex.Message}"); }
                }
            ));
        }


        /// <summary>DELETE all data associated with this Steam ID on the server.
        /// Signature: HMAC of "delete:{steam_id}". Server verifies with the shared secret.</summary>
        public static void DeletePlayerData(string steamId, Action<bool, string> callback)
        {
            if (string.IsNullOrEmpty(steamId)) { callback(false, "no-steam-id"); return; }
            string sig = ComputeHmacHex($"delete:{steamId}");
            string url = $"{baseUrl}/api/v1/players/{steamId}/data?sig={sig}";
            Plugin.Instance.StartCoroutine(DoDelete(url, callback));
        }

        private static IEnumerator DoDelete(string url, Action<bool, string> callback)
        {
            using (var request = UnityWebRequest.Delete(url))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                StampVersionHeader(request);
                request.timeout = 20;
                yield return request.SendWebRequest();
                bool success = request.result == UnityWebRequest.Result.Success;
                callback(success, success ? (request.downloadHandler?.text ?? "") : request.error);
            }
        }

        // ── Admin ─────────────────────────────────────────────

        public static bool IsAdmin { get; private set; }
        // Cached lists, refreshed by FetchFlaggedMatches / FetchBannedUsers.
        public static List<FlaggedMatchEntry> CachedFlaggedMatches { get; private set; } = new List<FlaggedMatchEntry>();
        public static List<BannedUserEntry> CachedBannedUsers { get; private set; } = new List<BannedUserEntry>();

        public class FlaggedMatchEntry
        {
            public string id, match_id, series_id, flag_reason;
            public string p1_name, p2_name;
            public List<string> player_steam_ids = new List<string>();
            public bool auto_invalidated, match_invalidated, is_ranked;
            public int duration_seconds;
            public string review_action;        // null = unreviewed
            public string created_at;
            public string flag_details_summary; // pre-rendered short string for the UI row
        }

        public class BannedUserEntry
        {
            public string id, steam_id, display_name, reason, banned_by_steam_id, banned_at;
        }

        public static void CheckAdminStatus(string steamId, Action<bool> callback = null)
        {
            if (string.IsNullOrEmpty(steamId)) { IsAdmin = false; callback?.Invoke(false); return; }
            string url = $"{baseUrl}/api/v1/admin/check-status?steam_id={steamId}";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, body) =>
            {
                bool admin = false;
                if (ok && !string.IsNullOrEmpty(body))
                    admin = body.Contains("\"is_admin\":true") || body.Contains("\"is_admin\": true");
                IsAdmin = admin;
                Plugin.Log.LogInfo($"[ADMIN] check-status for {steamId}: is_admin={admin}");
                callback?.Invoke(admin);
            }));
        }

        public static void FetchFlaggedMatches(string adminSteamId, bool includeReviewed = false, Action<bool> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId)) { callback?.Invoke(false); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:list_flagged:");
            string url = $"{baseUrl}/api/v1/admin/flagged-matches?admin_steam_id={adminSteamId}&hmac_signature={sig}&include_reviewed={(includeReviewed?"true":"false")}&limit=50";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, body) =>
            {
                if (!ok) { Plugin.Log.LogWarning($"[ADMIN] flagged fetch failed: {body}"); callback?.Invoke(false); return; }
                try { CachedFlaggedMatches = ParseFlaggedMatches(body); callback?.Invoke(true); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[ADMIN] flagged parse: {ex.Message}"); callback?.Invoke(false); }
            }));
        }

        public static void FetchBannedUsers(string adminSteamId, Action<bool> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId)) { callback?.Invoke(false); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:list_bans:");
            string url = $"{baseUrl}/api/v1/admin/banned-users?admin_steam_id={adminSteamId}&hmac_signature={sig}";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, body) =>
            {
                if (!ok) { Plugin.Log.LogWarning($"[ADMIN] bans fetch failed: {body}"); callback?.Invoke(false); return; }
                try { CachedBannedUsers = ParseBannedUsers(body); callback?.Invoke(true); }
                catch (Exception ex) { Plugin.Log.LogWarning($"[ADMIN] bans parse: {ex.Message}"); callback?.Invoke(false); }
            }));
        }

        public static void AdminBan(string adminSteamId, string targetSteamId, string reason, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"admin:{adminSteamId}:ban:{targetSteamId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"target_steam_id\":\"{Escape(targetSteamId)}\",\"reason\":\"{Escape(reason)}\",\"hmac_signature\":\"{sig}\"}}";
            Plugin.Instance.StartCoroutine(PostRequestWithRetry($"{baseUrl}/api/v1/admin/ban", body, (ok, resp) => callback?.Invoke(ok, resp)));
        }

        public static void AdminUnban(string adminSteamId, string targetSteamId, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"admin:{adminSteamId}:unban:{targetSteamId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"target_steam_id\":\"{Escape(targetSteamId)}\",\"hmac_signature\":\"{sig}\"}}";
            Plugin.Instance.StartCoroutine(PostRequestWithRetry($"{baseUrl}/api/v1/admin/unban", body, (ok, resp) => callback?.Invoke(ok, resp)));
        }

        public static void AdminGrantAchievement(string adminSteamId, string targetSteamId, string achievementKey, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"admin:{adminSteamId}:grant_achievement:{targetSteamId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"target_steam_id\":\"{Escape(targetSteamId)}\",\"achievement_key\":\"{Escape(achievementKey)}\",\"hmac_signature\":\"{sig}\"}}";
            Plugin.Instance.StartCoroutine(PostRequestWithRetry($"{baseUrl}/api/v1/admin/grant-achievement", body, (ok, resp) => callback?.Invoke(ok, resp)));
        }

        public static void AdminReverseSeries(string adminSteamId, string seriesId, string reason, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"admin:{adminSteamId}:reverse_series:{seriesId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"series_id\":\"{Escape(seriesId)}\",\"reason\":\"{Escape(reason)}\",\"hmac_signature\":\"{sig}\"}}";
            Plugin.Instance.StartCoroutine(PostRequestWithRetry($"{baseUrl}/api/v1/admin/reverse-series", body, (ok, resp) => callback?.Invoke(ok, resp)));
        }

        public static void AdminReviewFlag(string adminSteamId, string flagId, string action, Action<bool, string> callback = null)
        {
            string sig = ComputeHmacHex($"admin:{adminSteamId}:review_flag:{flagId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"flag_id\":\"{Escape(flagId)}\",\"review_action\":\"{Escape(action)}\",\"hmac_signature\":\"{sig}\"}}";
            Plugin.Instance.StartCoroutine(PostRequestWithRetry($"{baseUrl}/api/v1/admin/review-flag", body, (ok, resp) => callback?.Invoke(ok, resp)));
        }

        // ── Bug report admin viewers ─────────────────────────────────────
        [Serializable]
        public class BugReportSummary
        {
            public string id;
            public int bug_number;       // human-friendly auto-incrementing ID; quotable as "#47"
            public string created_at;
            public string steam_id;
            public string display_name;
            public string mod_version;
            public string severity;
            public string category;
            public string status;
            public string description;
            public bool has_log;
            public int log_bytes;
        }
        [Serializable]
        public class BugReportEventEntry
        {
            public string id;
            public string actor_steam_id;
            public string actor_name;
            public string event_type;   // comment | status_change | created
            public string old_status;
            public string new_status;
            public string comment;
            public string created_at;
        }
        [Serializable]
        public class BugReportDetail
        {
            public string id;
            public int bug_number;
            public string steam_id;
            public string display_name;
            public string mod_version;
            public string game_version;
            public string severity;
            public string category;
            public string description;
            public string repro_steps;
            public string status;
            public string triage_notes;
            public string created_at;
            public string log_text;
            public int log_bytes;
            public List<BugReportEventEntry> events = new List<BugReportEventEntry>();
        }
        public static List<BugReportSummary> CachedBugReports { get; private set; } = new List<BugReportSummary>();
        public static BugReportDetail CachedBugReportDetail { get; set; }

        public static void FetchBugReports(string adminSteamId, Action<bool> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId)) { callback?.Invoke(false); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:bug_reports:list");
            string url = $"{baseUrl}/api/v1/bug-reports?admin_steam_id={adminSteamId}&hmac_signature={sig}&limit=100";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, body) =>
            {
                if (!ok) { Plugin.Log.LogWarning($"[BUG-REPORTS] fetch failed: {body}"); callback?.Invoke(false); return; }
                try
                {
                    CachedBugReports = ParseBugReportList(body);
                    callback?.Invoke(true);
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[BUG-REPORTS] parse: {ex.Message}"); callback?.Invoke(false); }
            }));
        }

        public static void FetchBugReportDetail(string adminSteamId, string reportId, Action<bool> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId) || string.IsNullOrEmpty(reportId)) { callback?.Invoke(false); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:bug_reports:{reportId}");
            string url = $"{baseUrl}/api/v1/bug-reports/{reportId}?admin_steam_id={adminSteamId}&hmac_signature={sig}&include_log=true";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, body) =>
            {
                if (!ok) { Plugin.Log.LogWarning($"[BUG-REPORTS] detail fetch failed: {body}"); callback?.Invoke(false); return; }
                try
                {
                    CachedBugReportDetail = ParseBugReportDetail(body);
                    callback?.Invoke(true);
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[BUG-REPORTS] detail parse: {ex.Message}"); callback?.Invoke(false); }
            }));
        }

        private static List<BugReportSummary> ParseBugReportList(string json)
        {
            var list = new List<BugReportSummary>();
            if (string.IsNullOrEmpty(json)) return list;
            int kIdx = json.IndexOf("\"reports\":[");
            if (kIdx < 0) return list;
            int start = kIdx + "\"reports\":[".Length;
            int depth = 1, i = start;
            while (i < json.Length && depth > 0)
            {
                if (json[i] == '[') depth++;
                else if (json[i] == ']') depth--;
                i++;
            }
            if (depth != 0) return list;
            string slice = json.Substring(start, i - start - 1);
            int oIdx = 0;
            while (oIdx < slice.Length)
            {
                int objStart = slice.IndexOf('{', oIdx);
                if (objStart < 0) break;
                int oDepth = 1, j = objStart + 1;
                while (j < slice.Length && oDepth > 0)
                {
                    if (slice[j] == '{') oDepth++;
                    else if (slice[j] == '}') oDepth--;
                    j++;
                }
                if (oDepth != 0) break;
                string obj = slice.Substring(objStart, j - objStart);
                list.Add(new BugReportSummary
                {
                    id           = ExtractJsonString(obj, "id"),
                    bug_number   = ExtractJsonInt(obj, "bug_number"),
                    created_at   = ExtractJsonString(obj, "created_at"),
                    steam_id     = ExtractJsonString(obj, "steam_id"),
                    display_name = ExtractJsonString(obj, "display_name"),
                    mod_version  = ExtractJsonString(obj, "mod_version"),
                    severity     = ExtractJsonString(obj, "severity"),
                    category     = ExtractJsonString(obj, "category"),
                    status       = ExtractJsonString(obj, "status"),
                    description  = ExtractJsonString(obj, "description"),
                    has_log      = ExtractJsonBool(obj, "has_log"),
                    log_bytes    = ExtractJsonInt(obj, "log_bytes"),
                });
                oIdx = j;
            }
            return list;
        }

        private static BugReportDetail ParseBugReportDetail(string json)
        {
            var detail = new BugReportDetail
            {
                id            = ExtractJsonString(json, "id"),
                bug_number    = ExtractJsonInt(json, "bug_number"),
                steam_id      = ExtractJsonString(json, "steam_id"),
                display_name  = ExtractJsonString(json, "display_name"),
                mod_version   = ExtractJsonString(json, "mod_version"),
                game_version  = ExtractJsonString(json, "game_version"),
                severity      = ExtractJsonString(json, "severity"),
                category      = ExtractJsonString(json, "category"),
                description   = ExtractJsonString(json, "description"),
                repro_steps   = ExtractJsonString(json, "repro_steps"),
                status        = ExtractJsonString(json, "status"),
                triage_notes  = ExtractJsonString(json, "triage_notes"),
                created_at    = ExtractJsonString(json, "created_at"),
                log_text      = ExtractJsonString(json, "log_text"),
                log_bytes     = ExtractJsonInt(json, "log_bytes"),
            };
            // Parse events array — schema mirrors BugReportEventEntry. Manual
            // slicing because JsonUtility chokes on nested arrays (learning #25).
            try
            {
                int kIdx = json.IndexOf("\"events\":[");
                if (kIdx >= 0)
                {
                    int start = kIdx + "\"events\":[".Length;
                    int depth = 1, i = start;
                    while (i < json.Length && depth > 0)
                    {
                        if (json[i] == '[') depth++;
                        else if (json[i] == ']') depth--;
                        i++;
                    }
                    if (depth == 0)
                    {
                        string slice = json.Substring(start, i - start - 1);
                        int oIdx = 0;
                        while (oIdx < slice.Length)
                        {
                            int objStart = slice.IndexOf('{', oIdx);
                            if (objStart < 0) break;
                            int oDepth = 1, j = objStart + 1;
                            while (j < slice.Length && oDepth > 0)
                            {
                                if (slice[j] == '{') oDepth++;
                                else if (slice[j] == '}') oDepth--;
                                j++;
                            }
                            if (oDepth != 0) break;
                            string obj = slice.Substring(objStart, j - objStart);
                            detail.events.Add(new BugReportEventEntry
                            {
                                id              = ExtractJsonString(obj, "id"),
                                actor_steam_id  = ExtractJsonString(obj, "actor_steam_id"),
                                actor_name      = ExtractJsonString(obj, "actor_name"),
                                event_type      = ExtractJsonString(obj, "event_type"),
                                old_status      = ExtractJsonString(obj, "old_status"),
                                new_status      = ExtractJsonString(obj, "new_status"),
                                comment         = ExtractJsonString(obj, "comment"),
                                created_at      = ExtractJsonString(obj, "created_at"),
                            });
                            oIdx = j;
                        }
                    }
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[BUG-REPORTS] events parse: {ex.Message}"); }
            return detail;
        }

        public static void AdminBugReportComment(string adminSteamId, string reportId, string comment, Action<bool, string> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId) || string.IsNullOrEmpty(reportId))
            { callback?.Invoke(false, "missing args"); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:bug_reports_comment:{reportId}");
            string body = $"{{\"admin_steam_id\":\"{Escape(adminSteamId)}\",\"hmac_signature\":\"{sig}\",\"comment\":\"{Escape(comment ?? "")}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/bug-reports/{reportId}/comment", body,
                (ok, resp) => callback?.Invoke(ok, resp)));
        }

        public static void AdminBugReportStatus(string adminSteamId, string reportId, string newStatus, string comment, Action<bool, string> callback = null)
        {
            if (string.IsNullOrEmpty(adminSteamId) || string.IsNullOrEmpty(reportId) || string.IsNullOrEmpty(newStatus))
            { callback?.Invoke(false, "missing args"); return; }
            string sig = ComputeHmacHex($"admin:{adminSteamId}:bug_reports_status:{reportId}");
            var sb = new System.Text.StringBuilder();
            sb.Append("{");
            sb.Append($"\"admin_steam_id\":\"{Escape(adminSteamId)}\"");
            sb.Append($",\"hmac_signature\":\"{sig}\"");
            sb.Append($",\"new_status\":\"{Escape(newStatus)}\"");
            if (!string.IsNullOrEmpty(comment))
                sb.Append($",\"comment\":\"{Escape(comment)}\"");
            sb.Append("}");
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/bug-reports/{reportId}/status", sb.ToString(),
                (ok, resp) => callback?.Invoke(ok, resp)));
        }

        // Manual JSON parsers (the existing pattern in this file: JsonUtility silently fails on nested arrays).
        private static List<FlaggedMatchEntry> ParseFlaggedMatches(string json)
        {
            var list = new List<FlaggedMatchEntry>();
            if (string.IsNullOrEmpty(json)) return list;
            // Each flag begins with "id":"<uuid>" — split on that anchor and parse forward.
            var parts = json.Split(new[] { "\"id\":\"" }, StringSplitOptions.None);
            for (int i = 1; i < parts.Length; i++)
            {
                var chunk = parts[i];
                int qend = chunk.IndexOf('"');
                if (qend < 0) continue;
                var e = new FlaggedMatchEntry();
                e.id = chunk.Substring(0, qend);
                e.match_id = ExtractJsonString(chunk, "match_id");
                e.series_id = ExtractJsonString(chunk, "series_id");
                e.flag_reason = ExtractJsonString(chunk, "flag_reason");
                e.p1_name = ExtractJsonString(chunk, "p1_name");
                e.p2_name = ExtractJsonString(chunk, "p2_name");
                e.auto_invalidated = chunk.Contains("\"auto_invalidated\":true") || chunk.Contains("\"auto_invalidated\": true");
                e.match_invalidated = chunk.Contains("\"match_invalidated\":true") || chunk.Contains("\"match_invalidated\": true");
                e.is_ranked = chunk.Contains("\"is_ranked\":true") || chunk.Contains("\"is_ranked\": true");
                e.duration_seconds = ExtractJsonInt(chunk, "duration_seconds");
                e.review_action = ExtractJsonString(chunk, "review_action");
                e.created_at = ExtractJsonString(chunk, "created_at");
                // Rough single-line summary (the JSON is nested, we just hint the key signals).
                e.flag_details_summary = $"{e.flag_reason}  {(e.is_ranked?"R":"C")}  {e.duration_seconds}s  {(e.auto_invalidated?"[auto-inv]":"[advisory]")}";
                list.Add(e);
            }
            return list;
        }

        private static List<BannedUserEntry> ParseBannedUsers(string json)
        {
            var list = new List<BannedUserEntry>();
            if (string.IsNullOrEmpty(json)) return list;
            var parts = json.Split(new[] { "\"id\":\"" }, StringSplitOptions.None);
            for (int i = 1; i < parts.Length; i++)
            {
                var chunk = parts[i];
                int qend = chunk.IndexOf('"');
                if (qend < 0) continue;
                var e = new BannedUserEntry();
                e.id = chunk.Substring(0, qend);
                e.steam_id = ExtractJsonString(chunk, "steam_id");
                e.display_name = ExtractJsonString(chunk, "display_name");
                e.reason = ExtractJsonString(chunk, "reason");
                e.banned_by_steam_id = ExtractJsonString(chunk, "banned_by_steam_id");
                e.banned_at = ExtractJsonString(chunk, "banned_at");
                list.Add(e);
            }
            return list;
        }

        // ── Opponent ranked check ─────────────────────────────

        public static void CheckOpponentRanked(string steamId, Action<bool> callback)
        {
            if (string.IsNullOrEmpty(steamId) || steamId.StartsWith("photon_") || steamId == "unknown")
            {
                callback(false);
                return;
            }

            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/mod/check/{steamId}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            var data = JsonUtility.FromJson<ModCheckResponse>(response);
                            // Item 4: matched against a mod-banned cheater → tell the
                            // player and leave the room. Treated as not-ranked so no
                            // series spins up around a ban-aborted match.
                            if (data.banned)
                            {
                                Plugin.Log.LogWarning($"[BAN] Opponent {steamId} is mod-banned ({data.ban_reason}) — leaving match");
                                CompetitiveUI.ShowNotification(
                                    "Opponent is banned from the mod for cheating - leaving match.",
                                    new Color(1f, 0.3f, 0.3f), 8f);
                                try { if (Photon.Pun.PhotonNetwork.InRoom) Photon.Pun.PhotonNetwork.LeaveRoom(); }
                                catch (Exception ex) { Plugin.Log.LogWarning($"[BAN] LeaveRoom failed: {ex.Message}"); }
                                callback(false);
                                return;
                            }
                            bool isRanked = data.registered && data.ranked;
                            Plugin.Log.LogInfo($"Opponent ranked check: registered={data.registered}, ranked={data.ranked}");
                            callback(isRanked);
                        }
                        catch
                        {
                            callback(false);
                        }
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"Opponent rank check failed: {response}");
                        callback(false);
                    }
                }
            ));
        }

        // ── Match reporting ───────────────────────────────────

        public static void ReportMatch(
            string p1SteamId, string p1Name,
            string p2SteamId, string p2Name,
            int p1RoundsWon, int p2RoundsWon,
            int p1PointsTotal, int p2PointsTotal,
            List<MatchTracker.CardPickData> p1Cards,
            List<MatchTracker.CardPickData> p2Cards,
            List<MatchTracker.CardOfferData> p1Offers,
            List<MatchTracker.CardOfferData> p2Offers,
            string photonRoomId, string region,
            int durationSeconds, DateTime startedAt,
            string reporterSteamId, bool isRanked,
            // Anti-cheat: reporter's per-match input counts. Server flags reporter as
            // "inactive" if both are 0 across a non-trivial duration. NOT included in HMAC
            // (which is locked at exactly 7 fields) — these are advisory signals.
            int localShotsFired = 0, int localBlocksRaised = 0,
            // Hit% / Block% telemetry (v1.23). Same "advisory, not in HMAC" treatment — these
            // are stat counters on the reporter side that feed lifetime totals on the server.
            int localBulletsFired = 0, int localBulletsHit = 0,
            int localBlocksActivated = 0, int localBlocksSuccessful = 0,
            // v1.25 — average FPS this match. localAvgFps from our own counter, opponentAvgFps
            // sniffed from their Photon `cr_fps` custom property (0 = no data / no mod).
            int localAvgFps = 0, int opponentAvgFps = 0)
        {
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"player1\":{{\"steam_id\":\"{Escape(p1SteamId)}\",\"display_name\":\"{Escape(p1Name)}\",\"cards\":[");
            AppendCards(sb, p1Cards);
            sb.Append("],\"card_offers\":[");
            AppendOffers(sb, p1Offers);
            sb.Append("]},");
            sb.Append($"\"player2\":{{\"steam_id\":\"{Escape(p2SteamId)}\",\"display_name\":\"{Escape(p2Name)}\",\"cards\":[");
            AppendCards(sb, p2Cards);
            sb.Append("],\"card_offers\":[");
            AppendOffers(sb, p2Offers);
            sb.Append("]},");
            sb.Append($"\"p1_rounds_won\":{p1RoundsWon},");
            sb.Append($"\"p2_rounds_won\":{p2RoundsWon},");
            sb.Append($"\"p1_points_total\":{p1PointsTotal},");
            sb.Append($"\"p2_points_total\":{p2PointsTotal},");
            sb.Append($"\"photon_room_id\":\"{Escape(photonRoomId)}\",");
            sb.Append($"\"game_version\":\"v{Application.version}\",");
            sb.Append($"\"region\":\"{Escape(region)}\",");
            sb.Append($"\"match_duration\":{durationSeconds},");
            sb.Append($"\"started_at\":\"{startedAt:yyyy-MM-ddTHH:mm:ssZ}\",");
            sb.Append($"\"is_ranked\":{(isRanked ? "true" : "false")},");
            sb.Append($"\"reported_by_steam_id\":\"{Escape(reporterSteamId)}\",");
            // Reporter's combat input counts for inactive-player anti-cheat. Server-side advisory.
            sb.Append($"\"local_shots_fired\":{localShotsFired},");
            sb.Append($"\"local_blocks_raised\":{localBlocksRaised},");
            // v1.23 Hit% / Block% per-match deltas; server aggregates into lifetime totals.
            sb.Append($"\"local_bullets_fired\":{localBulletsFired},");
            sb.Append($"\"local_bullets_hit\":{localBulletsHit},");
            sb.Append($"\"local_blocks_activated\":{localBlocksActivated},");
            sb.Append($"\"local_blocks_successful\":{localBlocksSuccessful},");
            sb.Append($"\"local_avg_fps\":{localAvgFps},");
            sb.Append($"\"opponent_avg_fps\":{opponentAvgFps},");
            string sig = ComputeHmac(p1SteamId, p2SteamId, p1RoundsWon, p2RoundsWon, isRanked, reporterSteamId, photonRoomId);
            sb.Append($"\"hmac_signature\":\"{sig}\"");
            sb.Append("}");

            string json = sb.ToString();
            string matchType = isRanked ? "RANKED" : "CASUAL";
            Plugin.Log.LogInfo($"Reporting {matchType} match to API...");

            Plugin.Instance.StartCoroutine(PostRequestWithRetry(
                $"{baseUrl}/api/v1/matches",
                json,
                (success, response) =>
                {
                    if (success)
                    {
                        Plugin.Log.LogInfo($"Match reported successfully: {response}");

                        // Parse XP from response
                        int xpGained = ExtractJsonInt(response, "xp_gained");
                        int newLevel = ExtractJsonInt(response, "level");
                        int totalXp = ExtractJsonInt(response, "total_xp");

                        // Track previous level for level-up detection
                        int prevLevel = CompetitiveUI.LastKnownLevel;

                        // Build XP notification with breakdown
                        string xpLine = $"+{xpGained} XP";
                        var bonusParts = new List<string>();
                        if (response.Contains("Win x")) bonusParts.Add("Win x1.5");
                        if (response.Contains("Ranked x")) bonusParts.Add("Ranked x1.2");
                        if (response.Contains("Sweep")) bonusParts.Add("Sweep +100");
                        if (response.Contains("Top 5")) bonusParts.Add("Top 5 +150");

                        if (bonusParts.Count > 0)
                            xpLine += "  [" + string.Join(", ", bonusParts.ToArray()) + "]";

                        CompetitiveUI.ShowNotification(xpLine, new Color(0.4f, 0.8f, 1f), 4f);

                        // Gold pop-up, queued after XP so they don't clobber each other.
                        int goldGained = ExtractJsonInt(response, "gold_gained");
                        if (goldGained > 0)
                        {
                            // Parse the gold_bonuses string array so labels like "XP +4" and
                            // "Series win +5" land in the notification with their actual numbers
                            // (old code was doing substring contains-matching and dropping the +N).
                            var parts = new List<string>();
                            int arrIdx = response.IndexOf("\"gold_bonuses\":");
                            if (arrIdx >= 0)
                            {
                                int open = response.IndexOf('[', arrIdx);
                                int close = open >= 0 ? response.IndexOf(']', open) : -1;
                                if (open >= 0 && close > open)
                                {
                                    string body = response.Substring(open + 1, close - open - 1);
                                    foreach (var seg in body.Split(','))
                                    {
                                        string s = seg.Trim().Trim('"').Trim();
                                        if (!string.IsNullOrEmpty(s)) parts.Add(s);
                                    }
                                }
                            }
                            string goldLine = $"+{goldGained} gold";
                            if (parts.Count > 0) goldLine += "  [" + string.Join(", ", parts.ToArray()) + "]";
                            CompetitiveUI.QueueNotification(goldLine, new Color(1f, 0.85f, 0.3f), 4f);
                        }

                        // Show level-up if we gained a level
                        if (newLevel > prevLevel && prevLevel >= 0)
                        {
                            CompetitiveUI.QueueNotification($"LEVEL UP!  Level {newLevel}", new Color(1f, 0.85f, 0.3f), 4f);
                        }
                        CompetitiveUI.LastKnownLevel = newLevel;

                        FetchPlayerStats(MatchTracker.LocalSteamId);
                        FetchMatchHistory(MatchTracker.LocalSteamId);

                        // Series notifications and Glicko trigger
                        if (isRanked)
                        {
                            string seriesStatus = ExtractJsonString(response, "series_status");
                            string seriesScore = ExtractJsonString(response, "series_score");

                            // After game 1 of a series is over, live-points reporting is irrelevant
                            // (bets are locked anyway by series_wins > 0). Clear so we don't post
                            // stale series_id if a new series starts within the same room.
                            ActiveRankedSeriesId = null;

                            if (seriesStatus == "active")
                            {
                                CompetitiveUI.QueueNotification($"Series: {seriesScore}", new Color(1f, 0.85f, 0.3f), 3f);
                            }
                            else if (seriesStatus == "completed")
                            {
                                CompetitiveUI.QueueNotification($"SERIES COMPLETE {seriesScore}!", new Color(0.3f, 1f, 0.3f), 4f);
                                // Increment the session series tally. The series winner is
                                // whoever won this final reported game (a BO_n first-to-N
                                // ends on the deciding game), so map reporter-perspective
                                // win to local-perspective win and bump the right counter.
                                try
                                {
                                    string mySid = MatchTracker.LocalSteamId;
                                    bool meIsP1 = !string.IsNullOrEmpty(mySid) && mySid == p1SteamId;
                                    bool meWon = meIsP1 ? (p1RoundsWon > p2RoundsWon) : (p2RoundsWon > p1RoundsWon);
                                    GameStateWatcher.IncrementSessionRankedSeries(meWon);
                                }
                                catch (Exception ex) { Plugin.Log.LogWarning($"[SESSION] series tally update failed: {ex.Message}"); }
                                // Regicide is now handled server-side after series completion
                                GameStateWatcher.pendingRegicideCheck = false;
                            }
                        }
                    }
                    else
                    {
                        Plugin.Log.LogError($"Failed to report match: {response}");
                        CompetitiveUI.ShowNotification("Failed to report match", Color.red);
                    }
                }
            ));
        }

        private static void AppendCards(StringBuilder sb, List<MatchTracker.CardPickData> cards)
        {
            for (int i = 0; i < cards.Count; i++)
            {
                if (i > 0) sb.Append(",");
                var c = cards[i];
                sb.Append("{");
                sb.Append($"\"card_name\":\"{Escape(c.CardName)}\",");
                sb.Append($"\"card_rarity\":\"{Escape(c.CardRarity ?? "Unknown")}\",");
                sb.Append($"\"pick_order\":{c.PickOrder},");
                sb.Append($"\"round_number\":{c.RoundNumber}");
                sb.Append("}");
            }
        }

        private static void AppendOffers(StringBuilder sb, List<MatchTracker.CardOfferData> offers)
        {
            if (offers == null) return;
            for (int i = 0; i < offers.Count; i++)
            {
                if (i > 0) sb.Append(",");
                var o = offers[i];
                sb.Append("{");
                sb.Append($"\"card_name\":\"{Escape(o.CardName)}\",");
                sb.Append($"\"round_number\":{o.RoundNumber},");
                sb.Append($"\"was_picked\":{(o.WasPicked ? "true" : "false")}");
                sb.Append("}");
            }
        }

        // ── Data fetching ─────────────────────────────────────

        public static void FetchLeaderboard(int limit = 100, int minMatches = 1)
        {
            IsLoading = true;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/leaderboard?limit={limit}&min_matches={minMatches}",
                (success, response) =>
                {
                    IsLoading = false;
                    if (success)
                    {
                        try
                        {
                            // Manual parse — JsonUtility silently fails on this structure
                            var data = new LeaderboardData();
                            data.total_players = ExtractJsonInt(response, "total_players");

                            var entries = new List<LeaderboardEntry>();
                            var parts = response.Split(new[] { "\"rank\"" }, StringSplitOptions.None);

                            for (int i = 1; i < parts.Length; i++)
                            {
                                var chunk = parts[i];
                                var entry = new LeaderboardEntry();

                                // rank is right after the split point: :1,
                                try
                                {
                                    int colonIdx = chunk.IndexOf(':');
                                    if (colonIdx < 0) colonIdx = -1;
                                    int commaIdx = chunk.IndexOf(',', colonIdx + 1);
                                    if (colonIdx >= 0 && commaIdx > colonIdx)
                                    {
                                        string rankStr = chunk.Substring(colonIdx + 1, commaIdx - colonIdx - 1).Trim();
                                        entry.rank = int.Parse(rankStr);
                                    }
                                }
                                catch { entry.rank = i; }

                                entry.steam_id = ExtractJsonString(chunk, "steam_id");
                                entry.display_name = ExtractJsonString(chunk, "display_name");
                                entry.rating = ExtractJsonInt(chunk, "rating");
                                entry.rd = ExtractJsonInt(chunk, "rd");
                                entry.total_matches = ExtractJsonInt(chunk, "total_matches");
                                entry.wins = ExtractJsonInt(chunk, "wins");
                                entry.losses = ExtractJsonInt(chunk, "losses");

                                // Parse win_rate as float
                                try
                                {
                                    int wrIdx = chunk.IndexOf("\"win_rate\":");
                                    if (wrIdx >= 0)
                                    {
                                        wrIdx += "\"win_rate\":".Length;
                                        while (wrIdx < chunk.Length && chunk[wrIdx] == ' ') wrIdx++;
                                        int wrEnd = wrIdx;
                                        while (wrEnd < chunk.Length && (char.IsDigit(chunk[wrEnd]) || chunk[wrEnd] == '.' || chunk[wrEnd] == '-'))
                                            wrEnd++;
                                        if (wrEnd > wrIdx)
                                            entry.win_rate = float.Parse(chunk.Substring(wrIdx, wrEnd - wrIdx),
                                                System.Globalization.CultureInfo.InvariantCulture);
                                    }
                                }
                                catch { entry.win_rate = 0f; }

                                entry.level = ExtractJsonInt(chunk, "level");
                                entry.gold = ExtractJsonInt(chunk, "gold");
                                entry.title = ExtractJsonString(chunk, "title");
                                entry.title_color = ExtractJsonString(chunk, "title_color");

                                if (!string.IsNullOrEmpty(entry.steam_id))
                                    entries.Add(entry);
                            }

                            data.entries = entries.ToArray();
                            CachedLeaderboard = data;
                            Plugin.Log.LogInfo($"Leaderboard loaded: {CachedLeaderboard.entries?.Length ?? 0} entries");
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogError($"Failed to parse leaderboard: {ex.Message}");
                            LastError = "Failed to parse leaderboard data";
                        }
                    }
                    else
                    {
                        LastError = $"Failed to fetch leaderboard: {response}";
                        Plugin.Log.LogError(LastError);
                    }
                }
            ));
        }

        public static void FetchRecentSeries(int limit = 100)
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/series/recent?minutes=10080&limit={limit}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            var list = new List<RecentSeriesEntry>();
                            var parts = response.Split(new[] { "\"series_id\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length && list.Count < limit; i++)
                            {
                                var e = new RecentSeriesEntry();
                                e.winner_name = ExtractJsonString(parts[i], "winner_name");
                                e.p1_name = ExtractJsonString(parts[i], "p1_name");
                                e.p2_name = ExtractJsonString(parts[i], "p2_name");
                                e.p1_wins = ExtractJsonInt(parts[i], "p1_series_wins");
                                e.p2_wins = ExtractJsonInt(parts[i], "p2_series_wins");
                                e.winner_steam_id = ExtractJsonString(parts[i], "winner_steam_id");
                                e.p1_steam_id = ExtractJsonString(parts[i], "p1_steam_id");
                                e.p2_steam_id = ExtractJsonString(parts[i], "p2_steam_id");
                                // Parse rating changes as float
                                try{int rc1=parts[i].IndexOf("\"p1_rating_change\":");if(rc1>=0){rc1+="\"p1_rating_change\":".Length;int rc1e=rc1;while(rc1e<parts[i].Length&&(char.IsDigit(parts[i][rc1e])||parts[i][rc1e]=='.'||parts[i][rc1e]=='-'))rc1e++;if(rc1e>rc1)e.p1_rating_change=float.Parse(parts[i].Substring(rc1,rc1e-rc1),System.Globalization.CultureInfo.InvariantCulture);}}catch{}
                                try{int rc2=parts[i].IndexOf("\"p2_rating_change\":");if(rc2>=0){rc2+="\"p2_rating_change\":".Length;int rc2e=rc2;while(rc2e<parts[i].Length&&(char.IsDigit(parts[i][rc2e])||parts[i][rc2e]=='.'||parts[i][rc2e]=='-'))rc2e++;if(rc2e>rc2)e.p2_rating_change=float.Parse(parts[i].Substring(rc2,rc2e-rc2),System.Globalization.CultureInfo.InvariantCulture);}}catch{}
                                e.p1_rating = ExtractJsonInt(parts[i], "p1_rating");
                                e.p2_rating = ExtractJsonInt(parts[i], "p2_rating");
                                // Parse the bets array. Server inlines a 'bets' list into each series — each entry has
                                // bettor_name / amount / payout / bet_on_name / won. We isolate this series's bets chunk
                                // (from "bets" up to the next "series_id" boundary) so we don't accidentally pull bets
                                // from later series in the response.
                                int betsKey = parts[i].IndexOf("\"bets\":");
                                if (betsKey >= 0)
                                {
                                    int betsStart = parts[i].IndexOf('[', betsKey);
                                    int betsEnd = parts[i].IndexOf(']', betsStart);
                                    if (betsStart >= 0 && betsEnd > betsStart)
                                    {
                                        string betsBlock = parts[i].Substring(betsStart, betsEnd - betsStart + 1);
                                        var betChunks = betsBlock.Split(new[] { "\"bettor_name\":" }, StringSplitOptions.None);
                                        for (int bi = 1; bi < betChunks.Length; bi++)
                                        {
                                            string chunk = "\"bettor_name\":" + betChunks[bi];
                                            var b = new SeriesBetEntry();
                                            b.bettor_name = ExtractJsonString(chunk, "bettor_name");
                                            b.bettor_steam_id = ExtractJsonString(chunk, "bettor_steam_id");
                                            b.bet_on_name = ExtractJsonString(chunk, "bet_on_name");
                                            b.bet_on_steam_id = ExtractJsonString(chunk, "bet_on_steam_id");
                                            b.amount = ExtractJsonInt(chunk, "amount");
                                            b.payout = ExtractJsonInt(chunk, "payout");
                                            b.odds_multiplier = ExtractJsonFloat(chunk, "odds_multiplier");
                                            b.won = chunk.Contains("\"won\":true") || chunk.Contains("\"won\": true");
                                            if (!string.IsNullOrEmpty(b.bettor_name)) e.bets.Add(b);
                                        }
                                    }
                                }
                                if (!string.IsNullOrEmpty(e.p1_name)) list.Add(e);
                            }
                            CachedRecentSeries = list;
                            Plugin.Log.LogInfo($"Recent series loaded: {list.Count}");
                            NativeUI.MarkDirty();
                        }
                        catch (Exception ex) { Plugin.Log.LogWarning($"Recent series parse error: {ex.Message}"); }
                    }
                }
            ));
        }

        public static void FetchPlayerStats(string steamId, bool force = false)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            if (!force && IsLoading) return; // Don't stack requests

            IsLoading = true;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}",
                (success, response) =>
                {
                    IsLoading = false;
                    if (success)
                    {
                        try
                        {
                            CachedPlayerStats = JsonUtility.FromJson<PlayerStatsData>(response);
                            // JsonUtility can't handle nested arrays / List<string>, so manually
                            // parse the fields it skipped — including active_nametag_skus which
                            // the Shop + NametagStyler both read.
                            ParseTopCards(CachedPlayerStats, response);
                            Plugin.Log.LogInfo($"Player stats loaded for {CachedPlayerStats.display_name}");
                            // Re-publish Photon trail props whenever local stats refresh — covers
                            // the initial load + any later trail changes.
                            try { TrailCosmetic.PublishLocalProps(); } catch { }
                            try { PlayerColorCosmetic.PublishLocalProps(); } catch { }
                            try { PlayerEffectCosmetic.PublishLocalProps(); } catch { }
                            // Cursor color is local-only — re-apply the tinted hardware cursor.
                            try { CursorColorCosmetic.ApplyFromStats(); } catch { }
                            // Re-publish nametag styles into LocalPlayer.NickName for the same reason.
                            try { NametagStyler.PublishToPhoton(); } catch { }
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogError($"Failed to parse player stats: {ex.Message}");
                        }
                    }
                    else if (!response.Contains("404"))
                    {
                        Plugin.Log.LogError($"Failed to fetch player stats: {response}");
                    }
                }
            ));
        }


        /// <summary>
        /// Fetch stats for any player by Steam ID, with a callback.
        /// Used when clicking a player in the leaderboard.
        /// Does NOT overwrite CachedPlayerStats (that's the local player's).
        /// </summary>
        public static void FetchPlayerStatsForView(string steamId, Action<PlayerStatsData> callback)
        {
            if (string.IsNullOrEmpty(steamId))
            {
                callback(null);
                return;
            }

            // Pass the local Steam ID as the viewer so the server can
            // compute head-to-head counts against us. Falls back to no
            // viewer (no H2H) when the local ID isn't resolved yet.
            string viewer = MatchTracker.LocalSteamId;
            string viewerQ = (!string.IsNullOrEmpty(viewer) && viewer != "unknown" && viewer != steamId)
                ? $"?viewer_steam_id={Escape(viewer)}"
                : "";
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}{viewerQ}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            var data = JsonUtility.FromJson<PlayerStatsData>(response);
                            // Manually parse top_cards (JsonUtility can't handle nested arrays)
                            ParseTopCards(data, response);
                            callback(data);
                        }
                        catch
                        {
                            callback(null);
                        }
                    }
                    else
                    {
                        callback(null);
                    }
                }
            ));
        }

        private static void ParseTopCards(PlayerStatsData data, string response)
        {
            data.top_card_names = new List<string>();
            data.top_card_picks = new List<int>();
            data.top_card_win_rates = new List<float>();
            data.recent_form = new List<string>();
            data.worst_card_names = new List<string>();
            data.worst_card_picks = new List<int>();
            data.worst_card_win_rates = new List<float>();
            data.region_names = new List<string>();
            data.region_matches = new List<int>();
            try
            {
                int tcStart = response.IndexOf("\"top_cards\"");
                if (tcStart >= 0)
                {
                    int arrStart = response.IndexOf("[", tcStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0)
                    {
                        string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                        if (arr != "[]")
                        {
                            var cardParts = arr.Split(new[] { "\"card_name\"" }, StringSplitOptions.None);
                            for (int i = 1; i < cardParts.Length && i <= 10; i++)
                            {
                                string name = ExtractJsonString(cardParts[i], "");
                                int picks = ExtractJsonInt(cardParts[i], "times_picked");
                                float wr = 0f;
                                try
                                {
                                    int wrIdx = cardParts[i].IndexOf("\"win_rate\":");
                                    if (wrIdx >= 0)
                                    {
                                        wrIdx += "\"win_rate\":".Length;
                                        while (wrIdx < cardParts[i].Length && cardParts[i][wrIdx] == ' ') wrIdx++;
                                        int wrEnd = wrIdx;
                                        while (wrEnd < cardParts[i].Length && (char.IsDigit(cardParts[i][wrEnd]) || cardParts[i][wrEnd] == '.' || cardParts[i][wrEnd] == '-')) wrEnd++;
                                        if (wrEnd > wrIdx)
                                            wr = float.Parse(cardParts[i].Substring(wrIdx, wrEnd - wrIdx), System.Globalization.CultureInfo.InvariantCulture);
                                    }
                                }
                                catch { }
                                if (!string.IsNullOrEmpty(name))
                                {
                                    data.top_card_names.Add(name);
                                    data.top_card_picks.Add(picks);
                                    data.top_card_win_rates.Add(wr);
                                }
                            }
                        }
                    }
                }
            }
            catch { }

            // Parse worst_cards (same shape as top_cards: card_name/times_picked/win_rate).
            try
            {
                int wcStart = response.IndexOf("\"worst_cards\"");
                if (wcStart >= 0)
                {
                    int arrStart = response.IndexOf("[", wcStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0)
                    {
                        string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                        if (arr != "[]")
                        {
                            var cardParts = arr.Split(new[] { "\"card_name\"" }, StringSplitOptions.None);
                            for (int i = 1; i < cardParts.Length && i <= 10; i++)
                            {
                                string name = ExtractJsonString(cardParts[i], "");
                                int picks = ExtractJsonInt(cardParts[i], "times_picked");
                                float wr = ExtractJsonFloat(cardParts[i], "win_rate");
                                if (!string.IsNullOrEmpty(name))
                                {
                                    data.worst_card_names.Add(name);
                                    data.worst_card_picks.Add(picks);
                                    data.worst_card_win_rates.Add(wr);
                                }
                            }
                        }
                    }
                }
            }
            catch { }

            // Parse region_breakdown ([{region, matches}]).
            try
            {
                int rbStart = response.IndexOf("\"region_breakdown\"");
                if (rbStart >= 0)
                {
                    int arrStart = response.IndexOf("[", rbStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0)
                    {
                        string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                        if (arr != "[]")
                        {
                            var parts = arr.Split(new[] { "\"region\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length; i++)
                            {
                                string reg = ExtractJsonString(parts[i], "");
                                int matches = ExtractJsonInt(parts[i], "matches");
                                if (!string.IsNullOrEmpty(reg))
                                {
                                    data.region_names.Add(reg);
                                    data.region_matches.Add(matches);
                                }
                            }
                        }
                    }
                }
            }
            catch { }

            // Parse recent_form
            try
            {
                int rfStart = response.IndexOf("\"recent_form\"");
                if (rfStart >= 0)
                {
                    int arrStart = response.IndexOf("[", rfStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0)
                    {
                        string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                        if (arr != "[]")
                        {
                            var parts = arr.Split(new[] { "\"result\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length; i++)
                            {
                                string result = ExtractJsonString(parts[i], "");
                                if (!string.IsNullOrEmpty(result))
                                    data.recent_form.Add(result);
                            }
                        }
                    }
                }
            }
            catch { }

            // Parse active_color_skus — flat string array of equipped map-color skus.
            data.active_color_skus = new List<string>();
            try
            {
                int csStart = response.IndexOf("\"active_color_skus\"");
                if (csStart >= 0)
                {
                    int arrStart = response.IndexOf("[", csStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0 && arrEnd > arrStart)
                    {
                        string arr = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
                        int cursor = 0;
                        while (cursor < arr.Length)
                        {
                            int q1 = arr.IndexOf('"', cursor);
                            if (q1 < 0) break;
                            int q2 = arr.IndexOf('"', q1 + 1);
                            if (q2 < 0) break;
                            string sku = arr.Substring(q1 + 1, q2 - q1 - 1);
                            if (!string.IsNullOrEmpty(sku)) data.active_color_skus.Add(sku);
                            cursor = q2 + 1;
                        }
                    }
                }
            }
            catch { }

            // Parse active_nametag_skus — flat string array, one entry per active rich-text style.
            data.active_nametag_skus = new List<string>();
            try
            {
                int ntStart = response.IndexOf("\"active_nametag_skus\"");
                if (ntStart >= 0)
                {
                    int arrStart = response.IndexOf("[", ntStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0 && arrEnd > arrStart)
                    {
                        string arr = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
                        int cursor = 0;
                        while (cursor < arr.Length)
                        {
                            int q1 = arr.IndexOf('"', cursor);
                            if (q1 < 0) break;
                            int q2 = arr.IndexOf('"', q1 + 1);
                            if (q2 < 0) break;
                            string sku = arr.Substring(q1 + 1, q2 - q1 - 1);
                            if (!string.IsNullOrEmpty(sku)) data.active_nametag_skus.Add(sku);
                            cursor = q2 + 1;
                        }
                    }
                }
            }
            catch { }

            // Parse recent_rating_history
            data.rating_history = new List<float>();
            try
            {
                int rhStart = response.IndexOf("\"recent_rating_history\"");
                if (rhStart >= 0)
                {
                    int arrStart = response.IndexOf("[", rhStart);
                    int arrEnd = FindMatchingBracket(response, arrStart);
                    if (arrStart >= 0 && arrEnd >= 0)
                    {
                        string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                        if (arr != "[]")
                        {
                            var parts = arr.Split(new[] { "\"rating\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length; i++)
                            {
                                // extract number after ":"
                                int colonIdx = parts[i].IndexOf(':');
                                if (colonIdx >= 0)
                                {
                                    int vStart = colonIdx + 1;
                                    while (vStart < parts[i].Length && parts[i][vStart] == ' ') vStart++;
                                    int vEnd = vStart;
                                    while (vEnd < parts[i].Length && (char.IsDigit(parts[i][vEnd]) || parts[i][vEnd] == '.' || parts[i][vEnd] == '-')) vEnd++;
                                    if (vEnd > vStart)
                                    {
                                        float val = float.Parse(parts[i].Substring(vStart, vEnd - vStart), System.Globalization.CultureInfo.InvariantCulture);
                                        data.rating_history.Add(val);
                                    }
                                }
                            }
                        }
                    }
                }
            }
            catch { }
            // Server returns ASC (oldest → newest) since v1.26.8. Do NOT reverse —
            // the old reverse call was a v1.26.7-era hack that made the graph plot
            // right-to-left after the server switched ordering, AND made the "current
            // Elo" label read the OLDEST rating instead of the newest.
            //
            // Prepend 1500 as a synthetic first point so the graph starts at every
            // player's initial rating instead of wherever their first recorded series
            // happened to land. This matches user expectation ("shouldn't it start at
            // 1500 for everyone?") and turns the first slope into a meaningful "your
            // first series gain/loss from baseline" visualization.
            if (data.rating_history.Count > 0 && data.rating_history[0] != 1500f)
                data.rating_history.Insert(0, 1500f);
            Plugin.Log.LogInfo($"[STATS] Parsed {data.rating_history.Count} rating history points for {data.display_name} (oldest→newest, 1500 baseline prepended)");
        }

        // ── Selected player achievements (for LB detail) ─────────

        public static Dictionary<string, AchievementData> SelectedPlayerAchievements { get; private set; }
        private static string selectedAchSteamId = "";

        public static void FetchAchievementsForView(string steamId)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            if (steamId == selectedAchSteamId && SelectedPlayerAchievements != null) return; // already fetched
            selectedAchSteamId = steamId;
            SelectedPlayerAchievements = null;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/achievements/{steamId}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            var dict = new Dictionary<string, AchievementData>();
                            var parts = response.Split(new[] { "\"achievement_key\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length; i++)
                            {
                                string key = ExtractJsonString(parts[i], "");
                                if (string.IsNullOrEmpty(key)) continue;
                                bool unlocked = parts[i].Contains("\"unlocked\":true") || parts[i].Contains("\"unlocked\": true");
                                dict[key] = new AchievementData { achievement_key = key, unlocked = unlocked };
                            }
                            SelectedPlayerAchievements = dict;
                            NativeUI.MarkDirty();
                        }
                        catch { }
                    }
                }
            ));
        }

        private static int FindMatchingBracket(string s, int openPos)
        {
            if (openPos < 0 || openPos >= s.Length) return -1;
            int depth = 0;
            for (int i = openPos; i < s.Length; i++)
            {
                if (s[i] == '[') depth++;
                else if (s[i] == ']') { depth--; if (depth == 0) return i; }
            }
            return -1;
        }

        // Brace-pair finder for {} — same semantics as FindMatchingBracket. Used
        // by the cards_by_player parser, which has to extract a nested JSON
        // object (not an array) keyed by steam_id.
        private static int FindMatchingBrace(string s, int openPos)
        {
            if (openPos < 0 || openPos >= s.Length) return -1;
            int depth = 0;
            for (int i = openPos; i < s.Length; i++)
            {
                if (s[i] == '{') depth++;
                else if (s[i] == '}') { depth--; if (depth == 0) return i; }
            }
            return -1;
        }

        // Per-player card-tier-list state. (filter, card_name) -> tier letter.
        // Loaded by FetchCardTiers when the user changes the Card Stats filter.
        public static void FetchCardTiers(string steamId, string filter, Action<Dictionary<string, string>> onLoaded)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") { onLoaded?.Invoke(new Dictionary<string, string>()); return; }
            string url = $"{baseUrl}/api/v1/players/{Escape(steamId)}/card-tiers?filter={Escape(filter)}";
            Plugin.Instance.StartCoroutine(GetRequest(url, (success, response) =>
            {
                var map = new Dictionary<string, string>();
                if (!success || string.IsNullOrEmpty(response)) { onLoaded?.Invoke(map); return; }
                try
                {
                    int o = response.IndexOf("\"tiers\"");
                    if (o < 0) { onLoaded?.Invoke(map); return; }
                    int oS = response.IndexOf('{', o);
                    int oE = FindMatchingBrace(response, oS);
                    if (oS < 0 || oE < 0) { onLoaded?.Invoke(map); return; }
                    string slice = response.Substring(oS + 1, oE - oS - 1);
                    int cur = 0;
                    while (cur < slice.Length)
                    {
                        int kS = slice.IndexOf('"', cur); if (kS < 0) break;
                        int kE = slice.IndexOf('"', kS + 1); if (kE < 0) break;
                        string card = slice.Substring(kS + 1, kE - kS - 1);
                        int colon = slice.IndexOf(':', kE); if (colon < 0) break;
                        int vS = slice.IndexOf('"', colon); if (vS < 0) break;
                        int vE = slice.IndexOf('"', vS + 1); if (vE < 0) break;
                        string val = slice.Substring(vS + 1, vE - vS - 1);
                        map[card.ToLower()] = val;
                        cur = vE + 1;
                    }
                }
                catch (Exception ex) { Plugin.Log.LogWarning($"[CARD-TIER] parse: {ex.Message}"); }
                onLoaded?.Invoke(map);
            }));
        }

        public static void SetCardTier(string steamId, string cardName, string filter, string tier)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            string sig = ComputeHmacHex($"card-tier:{steamId}:{cardName}:{filter}:{tier}");
            string url = $"{baseUrl}/api/v1/players/{Escape(steamId)}/card-tiers"
                       + $"?card_name={Escape(cardName)}&filter={Escape(filter)}&tier={Escape(tier)}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (!ok) Plugin.Log.LogWarning($"[CARD-TIER] set failed: {resp}");
            }));
        }

        public static void FetchCardStats(int limit = 30, string steamId = null, string sortBy = "times_picked", string isRanked = null)
        {
            IsLoading = true;
            string url = $"{baseUrl}/api/v1/cards?limit={limit}&sort_by={sortBy}&min_picks=1";
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
                url += $"&steam_id={steamId}";
            if (!string.IsNullOrEmpty(isRanked))
                url += $"&is_ranked={isRanked}";

            Plugin.Instance.StartCoroutine(GetRequest(
                url,
                (success, response) =>
                {
                    IsLoading = false;
                    if (success)
                    {
                        try
                        {
                            if (string.IsNullOrEmpty(response) || response.Trim() == "[]")
                            {
                                CachedCardStats = new List<CardStatData>();
                                Plugin.Log.LogInfo("Card stats: no data yet");
                                return;
                            }

                            // Manual parse — split by card_name entries
                            var entries = new List<CardStatData>();
                            var parts = response.Split(new[] { "\"card_name\"" }, StringSplitOptions.None);

                            for (int i = 1; i < parts.Length; i++)
                            {
                                var chunk = parts[i];
                                var entry = new CardStatData();
                                entry.card_name = ExtractJsonString(chunk, "");
                                entry.card_rarity = ExtractJsonString(chunk, "card_rarity");
                                entry.times_picked = ExtractJsonInt(chunk, "times_picked");
                                entry.wins_with_card = ExtractJsonInt(chunk, "wins_with_card");
                                entry.times_offered = ExtractJsonInt(chunk, "times_offered");
                                entry.pass_rate = ExtractJsonFloat(chunk, "pass_rate");

                                // Parse win_rate as float
                                try
                                {
                                    string wrStr = chunk;
                                    int wrIdx = wrStr.IndexOf("\"win_rate\":");
                                    if (wrIdx >= 0)
                                    {
                                        wrIdx += "\"win_rate\":".Length;
                                        while (wrIdx < wrStr.Length && wrStr[wrIdx] == ' ') wrIdx++;
                                        int wrEnd = wrIdx;
                                        while (wrEnd < wrStr.Length && (char.IsDigit(wrStr[wrEnd]) || wrStr[wrEnd] == '.' || wrStr[wrEnd] == '-'))
                                            wrEnd++;
                                        if (wrEnd > wrIdx)
                                            entry.win_rate = float.Parse(wrStr.Substring(wrIdx, wrEnd - wrIdx),
                                                System.Globalization.CultureInfo.InvariantCulture);
                                    }
                                }
                                catch { entry.win_rate = 0f; }

                                if (!string.IsNullOrEmpty(entry.card_name))
                                    entries.Add(entry);
                            }

                            CachedCardStats = entries;
                            Plugin.Log.LogInfo($"Card stats loaded: {CachedCardStats.Count} cards");
                        }
                        catch (Exception ex)
                        {
                            CachedCardStats = new List<CardStatData>();
                            Plugin.Log.LogError($"Failed to parse card stats: {ex.Message}");
                        }
                    }
                    else
                    {
                        Plugin.Log.LogError($"Failed to fetch card stats: {response}");
                    }
                }
            ));
        }

        // limit=2000 is the server cap (see /players/{steam_id}/matches). Bumped
        // 500 → 2000 in v1.26.8 after Stan reported old matches "disappearing"
        // off the F5 history. 2000 covers ~6 months of heavy play for any user
        // and matches the server's enforcement ceiling.
        public static void FetchMatchHistory(string steamId, int limit = 2000)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;

            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}/matches?limit={limit}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            if (string.IsNullOrEmpty(response) || response.Trim() == "[]")
                            {
                                CachedMatchHistory = new List<MatchHistoryEntry>();
                                return;
                            }

                            // Manual parse since JsonUtility can't handle
                            // nested arrays (cards_picked) in list items
                            var entries = new List<MatchHistoryEntry>();
                            // Split by match_id to find each entry
                            var parts = response.Split(new[] { "\"match_id\"" }, StringSplitOptions.None);

                            for (int i = 1; i < parts.Length; i++)
                            {
                                var entry = new MatchHistoryEntry();
                                var chunk = parts[i];

                                entry.match_id = ExtractJsonString(chunk, "");
                                entry.opponent_name = ExtractJsonString(chunk, "opponent_name");
                                entry.opponent_steam_id = ExtractJsonString(chunk, "opponent_steam_id");
                                entry.opponent_title = ExtractJsonString(chunk, "opponent_title");
                                entry.opponent_title_color = ExtractJsonString(chunk, "opponent_title_color");

                                entry.player_rounds_won = ExtractJsonInt(chunk, "player_rounds_won");
                                entry.opponent_rounds_won = ExtractJsonInt(chunk, "opponent_rounds_won");
                                entry.player_points = ExtractJsonInt(chunk, "player_points");
                                entry.opponent_points = ExtractJsonInt(chunk, "opponent_points");
                                entry.won = chunk.Contains("\"won\":true") || chunk.Contains("\"won\": true");
                                entry.is_ranked = chunk.Contains("\"is_ranked\":true") || chunk.Contains("\"is_ranked\": true");
                                entry.ended_at = ExtractJsonString(chunk, "ended_at");

                                // Extract card names from cards_picked array
                                entry.cards_display = ExtractCardNames(chunk);

                                // Extract opponent card names from opponent_cards_picked array
                                entry.opp_cards_display = ExtractCardNames(chunk, "opponent_cards_picked");

                                // Extract series fields for BO3 grouping
                                entry.series_id = ExtractJsonString(chunk, "series_id");
                                entry.series_score = ExtractJsonString(chunk, "series_score");
                                entry.series_rating_change = ExtractJsonFloat(chunk, "series_rating_change");
                                entry.xp_gained = ExtractJsonInt(chunk, "xp_gained");
                                entry.gold_gained = ExtractJsonInt(chunk, "gold_gained");
                                entry.series_gold_gained = ExtractJsonInt(chunk, "series_gold_gained");
                                entry.player_fps_avg = ExtractJsonInt(chunk, "player_fps_avg");
                                entry.opponent_fps_avg = ExtractJsonInt(chunk, "opponent_fps_avg");

                                entries.Add(entry);
                            }

                            CachedMatchHistory = entries;
                            Plugin.Log.LogInfo($"Match history loaded: {CachedMatchHistory.Count} matches");
                        }
                        catch (Exception ex)
                        {
                            CachedMatchHistory = new List<MatchHistoryEntry>();
                            Plugin.Log.LogError($"Failed to parse match history: {ex.Message}");
                        }
                    }
                }
            ));
        }

        /// <summary>Parse a /matches JSON array into a MatchHistoryEntry list. Manual parse
        /// (JsonUtility can't handle the nested cards_picked arrays). Shared helper for the
        /// leaderboard view fetch below.</summary>
        private static List<MatchHistoryEntry> ParseMatchHistoryJson(string response)
        {
            var entries = new List<MatchHistoryEntry>();
            if (string.IsNullOrEmpty(response) || response.Trim() == "[]") return entries;
            var parts = response.Split(new[] { "\"match_id\"" }, StringSplitOptions.None);
            for (int i = 1; i < parts.Length; i++)
            {
                var entry = new MatchHistoryEntry();
                var chunk = parts[i];
                entry.match_id = ExtractJsonString(chunk, "");
                entry.opponent_name = ExtractJsonString(chunk, "opponent_name");
                entry.opponent_steam_id = ExtractJsonString(chunk, "opponent_steam_id");
                entry.opponent_title = ExtractJsonString(chunk, "opponent_title");
                entry.opponent_title_color = ExtractJsonString(chunk, "opponent_title_color");
                entry.player_rounds_won = ExtractJsonInt(chunk, "player_rounds_won");
                entry.opponent_rounds_won = ExtractJsonInt(chunk, "opponent_rounds_won");
                entry.player_points = ExtractJsonInt(chunk, "player_points");
                entry.opponent_points = ExtractJsonInt(chunk, "opponent_points");
                entry.won = chunk.Contains("\"won\":true") || chunk.Contains("\"won\": true");
                entry.is_ranked = chunk.Contains("\"is_ranked\":true") || chunk.Contains("\"is_ranked\": true");
                entry.ended_at = ExtractJsonString(chunk, "ended_at");
                entry.cards_display = ExtractCardNames(chunk);
                entry.opp_cards_display = ExtractCardNames(chunk, "opponent_cards_picked");
                entry.series_id = ExtractJsonString(chunk, "series_id");
                entry.series_score = ExtractJsonString(chunk, "series_score");
                entry.series_rating_change = ExtractJsonFloat(chunk, "series_rating_change");
                entry.xp_gained = ExtractJsonInt(chunk, "xp_gained");
                entry.gold_gained = ExtractJsonInt(chunk, "gold_gained");
                entry.series_gold_gained = ExtractJsonInt(chunk, "series_gold_gained");
                entry.player_fps_avg = ExtractJsonInt(chunk, "player_fps_avg");
                entry.opponent_fps_avg = ExtractJsonInt(chunk, "opponent_fps_avg");
                entries.Add(entry);
            }
            return entries;
        }

        /// <summary>Fetch ANY player's match history for the leaderboard detail view. Does NOT
        /// clobber CachedMatchHistory (that's the local player's). Used to render a clicked
        /// player's ranked history + head-to-head last series. Callback gets the parsed list.</summary>
        public static void FetchMatchHistoryForView(string steamId, Action<List<MatchHistoryEntry>> callback, int limit = 400)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") { callback?.Invoke(new List<MatchHistoryEntry>()); return; }
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}/matches?limit={limit}",
                (success, response) =>
                {
                    List<MatchHistoryEntry> list;
                    try { list = success ? ParseMatchHistoryJson(response) : new List<MatchHistoryEntry>(); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[LBVIEW] match parse failed: {ex.Message}"); list = new List<MatchHistoryEntry>(); }
                    try { callback?.Invoke(list); } catch { }
                }
            ));
        }

        private static string ExtractJsonString(string json, string key)
        {
            try
            {
                // When key is empty, we're reading the value right after a split point
                // Chunk starts with :"value",... so search for :"
                // When key is set, search for "key":"
                string search = string.IsNullOrEmpty(key) ? ":\"" : $"\"{key}\":\"";
                int start = json.IndexOf(search);
                if (start < 0) return "";
                start += search.Length;
                // Scan forward, skipping escaped chars. Without this, any value
                // containing a literal " (encoded as \" in JSON) truncates the
                // parse — bug reports with quoted log text were losing the rest
                // of the field + bleeding into adjacent fields.
                int i = start;
                var sb = new System.Text.StringBuilder();
                while (i < json.Length)
                {
                    char c = json[i];
                    if (c == '\\' && i + 1 < json.Length)
                    {
                        char nx = json[i + 1];
                        switch (nx)
                        {
                            case '"':  sb.Append('"');  i += 2; continue;
                            case '\\': sb.Append('\\'); i += 2; continue;
                            case '/':  sb.Append('/');  i += 2; continue;
                            case 'n':  sb.Append('\n'); i += 2; continue;
                            case 'r':  sb.Append('\r'); i += 2; continue;
                            case 't':  sb.Append('\t'); i += 2; continue;
                            case 'b':  sb.Append('\b'); i += 2; continue;
                            case 'f':  sb.Append('\f'); i += 2; continue;
                            case 'u':
                                if (i + 5 < json.Length)
                                {
                                    string hex = json.Substring(i + 2, 4);
                                    if (int.TryParse(hex, System.Globalization.NumberStyles.HexNumber,
                                                     System.Globalization.CultureInfo.InvariantCulture, out int code))
                                    {
                                        sb.Append((char)code);
                                        i += 6;
                                        continue;
                                    }
                                }
                                sb.Append(nx); i += 2; continue;
                            default: sb.Append(nx); i += 2; continue;
                        }
                    }
                    if (c == '"') break;
                    sb.Append(c);
                    i++;
                }
                return sb.ToString();
            }
            catch { return ""; }
        }

        // Public alias so CompetitiveUI can reuse the helper without exposing
        // every parser internal. Same semantics as ExtractJsonInt.
        public static int ExtractJsonIntPublic(string json, string key) => ExtractJsonInt(json, key);

        private static int ExtractJsonInt(string json, string key)
        {
            try
            {
                string search = $"\"{key}\":";
                int start = json.IndexOf(search);
                if (start < 0) return 0;
                start += search.Length;
                // Skip whitespace
                while (start < json.Length && (json[start] == ' ' || json[start] == '\t')) start++;
                int end = start;
                while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '-')) end++;
                if (end == start) return 0;
                return int.Parse(json.Substring(start, end - start));
            }
            catch { return 0; }
        }

        private static float ExtractJsonFloat(string json, string key)
        {
            try
            {
                string search = $"\"{key}\":";
                int start = json.IndexOf(search);
                if (start < 0) return 0f;
                start += search.Length;
                while (start < json.Length && (json[start] == ' ' || json[start] == '\t')) start++;
                // Check for null
                if (start < json.Length && json[start] == 'n') return 0f;
                int end = start;
                while (end < json.Length && (char.IsDigit(json[end]) || json[end] == '.' || json[end] == '-')) end++;
                if (end == start) return 0f;
                return float.Parse(json.Substring(start, end - start),
                    System.Globalization.CultureInfo.InvariantCulture);
            }
            catch { return 0f; }
        }

        private static bool ExtractJsonBool(string json, string key)
        {
            try
            {
                string search = $"\"{key}\":";
                int start = json.IndexOf(search);
                if (start < 0) return false;
                start += search.Length;
                while (start < json.Length && (json[start] == ' ' || json[start] == '\t')) start++;
                return start < json.Length && json[start] == 't'; // "true" vs "false"
            }
            catch { return false; }
        }

        private static string ExtractCardNames(string chunk, string key = "cards_picked")
        {
            try
            {
                int cpStart = chunk.IndexOf("\"" + key + "\"");
                if (cpStart < 0) return "";

                int arrStart = chunk.IndexOf("[", cpStart);
                int arrEnd = chunk.IndexOf("]", arrStart);
                if (arrStart < 0 || arrEnd < 0) return "";

                string arr = chunk.Substring(arrStart, arrEnd - arrStart + 1);
                if (arr == "[]") return "";

                var names = new List<string>();
                var cardParts = arr.Split(new[] { "\"card_name\"" }, StringSplitOptions.None);
                for (int j = 1; j < cardParts.Length; j++)
                {
                    string name = ExtractJsonString(cardParts[j], "");
                    if (!string.IsNullOrEmpty(name) && name != "Unknown")
                        names.Add(name);
                }

                return names.Count > 0 ? string.Join(", ", names.ToArray()) : "";
            }
            catch { return ""; }
        }

        public static void TriggerGlickoRecalc()
        {
            // The recalc endpoint requires an api_key parameter
            string apiKey = Plugin.ApiBaseUrl.Value.Contains("192.168") ? "dev" : "dev";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/glicko/recalculate?api_key={apiKey}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        Plugin.Log.LogInfo($"Glicko-2 recalculation triggered: {response}");
                        FetchPlayerStats(MatchTracker.LocalSteamId);
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"Glicko recalc failed: {response}");
                    }
                }
            ));
        }

        /// <summary>Pre-create a ranked_series row on the server for a private-room
        /// match between two ranked-enabled mod users. Idempotent — server reuses
        /// any existing active series for the pair. Without this, private-room
        /// games don't appear in /series/active until the first match completes,
        /// so spectators can't see them in the Live Ranked Games panel.</summary>
        public static void SendSeriesPreflight(string mySteamId, string oppSteamId)
        {
            if (string.IsNullOrEmpty(mySteamId) || string.IsNullOrEmpty(oppSteamId)) return;
            // Server signs HMAC over the sorted-pair canonical so either side can
            // post the preflight without coordinating who's p1/p2.
            string a = string.Compare(mySteamId, oppSteamId, StringComparison.Ordinal) <= 0 ? mySteamId : oppSteamId;
            string b = a == mySteamId ? oppSteamId : mySteamId;
            string sig = ComputeHmacHex($"preflight:{a}:{b}");
            // Pass display names so first-time-seen players show as their
            // actual nickname in Live Ranked Games / Recent Series, not as
            // the bare Steam ID until their next /stats call.
            string myName = MatchTracker.LocalDisplayName ?? mySteamId;
            string oppName = GameStateWatcher.OpponentDisplayName ?? oppSteamId;
            string url = $"{baseUrl}/api/v1/series/preflight?p1_steam_id={Escape(mySteamId)}&p2_steam_id={Escape(oppSteamId)}"
                       + $"&p1_name={Escape(myName)}&p2_name={Escape(oppName)}&sig={sig}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (ok)
                {
                    string sid = ExtractJsonString(resp, "series_id");
                    if (!string.IsNullOrEmpty(sid))
                    {
                        ActiveRankedSeriesId = sid;
                        Plugin.Log.LogInfo($"[PREFLIGHT] series_id={sid} (private room)");
                    }
                    else
                    {
                        Plugin.Log.LogInfo($"[PREFLIGHT] response: {resp}");
                    }
                }
                else
                {
                    Plugin.Log.LogWarning($"[PREFLIGHT] failed: {resp}");
                }
            }));
        }

        public static void ToggleRanked(string steamId, bool enabled)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/mod/toggle-ranked/{steamId}?enabled={enabled.ToString().ToLower()}&sig={ComputeHmacHex($"toggle-ranked:{steamId}:{enabled.ToString().ToLower()}")}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        Plugin.Log.LogInfo($"Ranked mode set to {enabled}");
                        CompetitiveUI.ShowNotification(
                            enabled ? "Ranked mode ON" : "Ranked mode OFF",
                            enabled ? Color.green : Color.yellow
                        );
                    }
                    else
                    {
                        Plugin.Log.LogError($"Failed to toggle ranked: {response}");
                    }
                }
            ));
        }

        // ── Ranked Queue ──────────────────────────────────────

        public enum QueueState { Idle, Searching, Matched, ReadySent }

        [Serializable]
        public class QueuePollData
        {
            public string status;        // searching, matched, ready_join, not_in_queue, expired
            public int wait_time;
            public int queue_size;
            public int elo_range;
            public string opponent_steam_id;
            public string opponent_name;
            public float opponent_rating;
            public bool opponent_ready;
            public string room_name;
            public string photon_region;
        }

        // Current queue state (mod-side)
        public static QueueState CurrentQueueState { get; private set; } = QueueState.Idle;
        // v1.22 — server returns this on /queue/ready when both players ready up. Used by
        // GameStateWatcher's poll to address the correct series when posting live point counts.
        // Cleared after the series's first match report (no longer needed; bets locked anyway).
        public static string ActiveRankedSeriesId;
        public static QueuePollData LastPollData { get; private set; }
        public static bool IsQueuePolling { get; private set; } = false;
        private static float queuePollTimer = 0f;
        private static float queuePollInterval = 3f;

        public static void JoinQueue(string steamId, string displayName, string region, bool rankedOnly)
        {
            // Use current Photon region if not specified
            if (string.IsNullOrEmpty(region))
            {
                try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { region = ""; }
            }
            string safeName = Escape(displayName ?? steamId);
            string json = $"{{\"steam_id\":\"{Escape(steamId)}\",\"display_name\":\"{safeName}\",\"region\":\"{Escape(region ?? "")}\",\"ranked_only\":{(rankedOnly ? "true" : "false")}}}";

            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/queue/join",
                json,
                (success, response) =>
                {
                    if (success)
                    {
                        CurrentQueueState = QueueState.Searching;
                        IsQueuePolling = true;
                        queuePollTimer = 0f;
                        Plugin.Log.LogInfo("[QUEUE] Joined ranked queue");
                        CompetitiveUI.ShowNotification("Searching for ranked match...", new Color(0.4f, 0.8f, 1f));
                        NativeUI.MarkDirty();
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[QUEUE] Failed to join queue: {response}");
                        CompetitiveUI.ShowNotification("Failed to join queue", new Color(1f, 0.4f, 0.4f));
                    }
                }
            ));
        }

        public static void LeaveQueue(string steamId)
        {
            if (CurrentQueueState == QueueState.Idle && !IsQueuePolling) return; // Already idle
            CurrentQueueState = QueueState.Idle;
            IsQueuePolling = false;
            LastPollData = null;
            NativeUI.MarkDirty();

            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/queue/leave?steam_id={Escape(steamId)}",
                "",
                (success, response) =>
                {
                    Plugin.Log.LogInfo("[QUEUE] Left ranked queue");
                }
            ));
        }

        /// <summary>
        /// Decline a matched opponent. Blocks re-matching for 5 minutes.
        /// Both players are reset to searching (stay in queue).
        /// </summary>
        public static void DeclineMatch(string steamId)
        {
            var poll = LastPollData;
            string oppSteamId = poll?.opponent_steam_id ?? "";

            // Reset local state to Searching (stay in queue, keep polling)
            CurrentQueueState = QueueState.Searching;
            LastPollData = null;
            Plugin.ClearPendingRoom();
            NativeUI.MarkDirty();

            if (string.IsNullOrEmpty(oppSteamId))
            {
                // No opponent data — just leave queue as fallback
                CurrentQueueState = QueueState.Idle;
                IsQueuePolling = false;
                Plugin.Instance.StartCoroutine(PostRequest(
                    $"{baseUrl}/api/v1/queue/leave?steam_id={Escape(steamId)}",
                    "",
                    (success, response) =>
                    {
                        Plugin.Log.LogInfo("[QUEUE] Left ranked queue (decline fallback)");
                    }
                ));
                NativeUI.MarkDirty();
                return;
            }

            string json = $"{{\"steam_id\":\"{Escape(steamId)}\",\"opponent_steam_id\":\"{Escape(oppSteamId)}\"}}";

            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/queue/decline",
                json,
                (success, response) =>
                {
                    if (success)
                        Plugin.Log.LogInfo($"[QUEUE] Declined match vs {oppSteamId}, searching for new opponent");
                    else
                        Plugin.Log.LogWarning($"[QUEUE] Decline failed: {response}");
                }
            ));
        }

        /// <summary>
        /// Signal ready for the current matched game. Server will generate
        /// a room when both players are ready.
        /// </summary>
        public static void ReadyUp(string steamId)
        {
            if (CurrentQueueState != QueueState.Matched) return;

            CurrentQueueState = QueueState.ReadySent;
            NativeUI.MarkDirty();
            Plugin.Log.LogInfo("[QUEUE] Ready Up sent");

            Plugin.Instance.StartCoroutine(PostRequestWithRetry(
                $"{baseUrl}/api/v1/queue/ready?steam_id={Escape(steamId)}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        // Check if both ready already (instant room)
                        string status = ExtractJsonString(response, "status");
                        if (status == "both_ready")
                        {
                            string room = ExtractJsonString(response, "room_name");
                            string region = ExtractJsonString(response, "photon_region");
                            // v1.22 — server now pre-creates the ranked_series and returns its id.
                            // Stash it so live-points reports during game 1 can address the right series.
                            ActiveRankedSeriesId = ExtractJsonString(response, "series_id");
                            if (!string.IsNullOrEmpty(room))
                            {
                                IsQueuePolling = false;
                                CurrentQueueState = QueueState.Idle;
                                LastPollData = null;
                                Plugin.SetPendingRoom(room, region);
                                Plugin.Log.LogInfo($"[QUEUE] Both ready! Joining room: {room} (region: {region ?? "auto"}) series={ActiveRankedSeriesId}");
                                CompetitiveUI.ShowNotification("Both ready! Joining match...", Color.green, 5f);
                                // Refresh the Live Ranked Series list immediately so spectators
                                // (and the betting UI) see the new series the moment it's
                                // created, not on the 10s poll cycle. Gives spectators the full
                                // pre-game-1 window to place bets instead of missing half of it.
                                FetchActiveSeries();
                                NativeUI.MarkDirty();
                            }
                        }
                        else
                        {
                            // Echo the server response so if a "canceled despite both ready"
                            // report comes in again we can see if the server actually said
                            // "waiting" or something weirder like "not_matched" (which would
                            // indicate the matched state was already lost before the ready hit).
                            string detail = ExtractJsonString(response, "status") ?? "(no status)";
                            string msg = ExtractJsonString(response, "message") ?? "";
                            Plugin.Log.LogInfo($"[QUEUE] Waiting for opponent to ready up (server: {detail} — {msg})");
                        }
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[QUEUE] Ready failed after retries: {response}");
                        CompetitiveUI.ShowNotification("Ready-up failed — retrying search", new Color(1f, 0.6f, 0.2f), 5f);
                        CurrentQueueState = QueueState.Searching;
                        NativeUI.MarkDirty();
                    }
                },
                maxRetries: 3, retryDelay: 2f
            ));
        }

        /// <summary>
        /// Called from Update() when polling is active. Polls every 3 seconds.
        /// </summary>
        public static void UpdateQueuePoll(string steamId)
        {
            if (!IsQueuePolling) return;

            queuePollTimer += Time.deltaTime;
            if (queuePollTimer < queuePollInterval) return;
            queuePollTimer = 0f;

            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/queue/poll/{steamId}",
                (success, response) =>
                {
                    if (!success || !IsQueuePolling) return;

                    try
                    {
                        string status = ExtractJsonString(response, "status");

                        if (status == "ready_join")
                        {
                            // Both ready — room assigned, join it!
                            string room = ExtractJsonString(response, "room_name");
                            string region = ExtractJsonString(response, "photon_region");
                            IsQueuePolling = false;
                            CurrentQueueState = QueueState.Idle;
                            LastPollData = null;
                            Plugin.SetPendingRoom(room, region);
                            Plugin.Log.LogInfo($"[QUEUE] Both ready! Joining room: {room} (region: {region ?? "auto"})");
                            CompetitiveUI.ShowNotification("Both ready! Joining match...", Color.green, 5f);
                            NativeUI.MarkDirty();
                        }
                        else if (status == "matched")
                        {
                            bool oppReady = ExtractJsonBool(response, "opponent_ready");

                            if (CurrentQueueState == QueueState.Searching)
                            {
                                // New match found!
                                CurrentQueueState = QueueState.Matched;
                                Plugin.Log.LogInfo($"[QUEUE] MATCHED! vs {ExtractJsonString(response, "opponent_name")} ({ExtractJsonFloat(response, "opponent_rating"):F0})");
                                CompetitiveUI.ShowNotification(
                                    $"MATCH FOUND!  vs {ExtractJsonString(response, "opponent_name")} ({ExtractJsonFloat(response, "opponent_rating"):F0})",
                                    Color.green, 8f
                                );
                                CompetitiveUI.PlayMatchFoundSound();
                                TaskbarFlash.Flash();
                            }

                            // Keep polling — update data (opponent_ready may change)
                            LastPollData = new QueuePollData
                            {
                                status = "matched",
                                wait_time = ExtractJsonInt(response, "wait_time"),
                                opponent_steam_id = ExtractJsonString(response, "opponent_steam_id"),
                                opponent_name = ExtractJsonString(response, "opponent_name"),
                                opponent_rating = ExtractJsonFloat(response, "opponent_rating"),
                                opponent_ready = oppReady,
                            };
                            NativeUI.MarkDirty();
                        }
                        else if (status == "searching")
                        {
                            if (CurrentQueueState == QueueState.Matched || CurrentQueueState == QueueState.ReadySent)
                            {
                                // Was matched but now searching — declined or timeout
                                Plugin.Log.LogInfo("[QUEUE] Match canceled — back to searching");
                                CompetitiveUI.ShowNotification("Match canceled — searching...", Color.yellow, 5f);
                            }

                            CurrentQueueState = QueueState.Searching;
                            LastPollData = new QueuePollData
                            {
                                status = "searching",
                                wait_time = ExtractJsonInt(response, "wait_time"),
                                queue_size = ExtractJsonInt(response, "queue_size"),
                                elo_range = ExtractJsonInt(response, "elo_range"),
                            };
                            NativeUI.MarkDirty();
                        }
                        else if (status == "expired" || status == "not_in_queue")
                        {
                            CurrentQueueState = QueueState.Idle;
                            IsQueuePolling = false;
                            LastPollData = null;
                            CompetitiveUI.ShowNotification("Queue search expired", Color.yellow);
                            NativeUI.MarkDirty();
                        }
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogWarning($"[QUEUE] Poll parse error: {ex.Message}");
                    }
                }
            ));
        }

        public static void ResetQueueState()
        {
            CurrentQueueState = QueueState.Idle;
            IsQueuePolling = false;
            LastPollData = null;
        }

        // ── Queue Count (lightweight, always-on when page open) ──

        public static int CachedQueueSearching { get; private set; } = 0;
        public static int CachedQueueTotal { get; private set; } = 0;
        private static float queueCountTimer = 0f;
        private static float queueCountInterval = 10f;

        public static void UpdateQueueCount()
        {
            queueCountTimer += Time.deltaTime;
            if (queueCountTimer < queueCountInterval) return;
            queueCountTimer = 0f;

            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/queue/count",
                (success, response) =>
                {
                    if (success)
                    {
                        int s = ExtractJsonInt(response, "searching");
                        int t = ExtractJsonInt(response, "total");
                        if (s != CachedQueueSearching || t != CachedQueueTotal)
                        {
                            CachedQueueSearching = s;
                            CachedQueueTotal = t;
                            NativeUI.MarkDirty();
                        }
                    }
                }
            ));
        }

        public static void ResetQueueCountTimer() { queueCountTimer = queueCountInterval; }

        // ════════════════════════════════════════════════════════════
        // 2v2 RANKED (Phase 2 — client side)
        // ════════════════════════════════════════════════════════════

        public enum TeamQueueState { Idle, Searching, Matched, ReadySent }

        [Serializable]
        public class TeamQueueMember
        {
            public string steam_id;
            public string display_name;
            public int rating;
            public string region;
            public int team_assigned; // 1, 2, or 0 if unassigned
            // Server-side balancer flag: true when the queuer's 2v2 sample is
            // too small to trust (completed_series < TEAM_TRUST_2V2_RATING_AFTER)
            // and the matchmaker is using their 1v1 rating instead. Surfaced in
            // the queue UI so users can verify the fallback fired when expected.
            public bool using_fallback_rating;
            public int balance_rating;     // the rating the balancer actually uses (2v2 or 1v1 fallback)
            public int completed_series;   // 2v2 series count at queue join time
            public bool ready;             // per-slot ready flag for the lock-in prompt
        }

        [Serializable]
        public class TeamQueuePollData
        {
            public string status;
            public int queue_count;
            public int elo_range;
            public string series_id;
            public int team_assigned;
            public List<TeamQueueMember> teammates = new List<TeamQueueMember>();
            public List<TeamQueueMember> opponents = new List<TeamQueueMember>();
            public string room_name;
            public string room_region;
            public int match_age_seconds;
            public bool my_ready;          // the polling player's own ready flag
        }

        [Serializable]
        public class TeamQueueListEntry
        {
            public string steam_id;
            public string display_name;
            public int rating;
            public int balance_rating;
            public bool using_fallback_rating;
            public int completed_series;
            public string region;
            public string status;
            public int team_assigned;
            public string series_id;
            public int wait_seconds;
            public bool manual_pick_enabled;
            public int preferred_team;
            public string queue_type;  // "auto" or "manual" — empty defaults to auto
        }
        public static List<TeamQueueListEntry> CachedTeamQueueList { get; private set; } = new List<TeamQueueListEntry>();
        // Pre-bucketed views for the F5 panel — saves the renderer from re-filtering every frame.
        public static List<TeamQueueListEntry> CachedTeamQueueAuto { get; private set; } = new List<TeamQueueListEntry>();
        public static List<TeamQueueListEntry> CachedTeamQueueManual { get; private set; } = new List<TeamQueueListEntry>();
        private static float teamQueueListTimer = 0f;
        // Tight 2s polling so the panel reflects new queuers within ~2s of them
        // joining. User reported: "In Queue doesn't seem to update with new
        // players when someone joins until i back out and rejoin the queue".
        private const float TEAM_QUEUE_LIST_INTERVAL = 2f;

        public static TeamQueueState CurrentTeamQueueState { get; private set; } = TeamQueueState.Idle;
        public static TeamQueuePollData LastTeamPollData { get; private set; }
        public static string ActiveTeamSeriesId { get; set; }
        public static bool IsTeamQueuePolling { get; private set; } = false;
        public static int CachedTeamQueueSearching { get; private set; } = 0;
        private static float teamQueuePollTimer = 0f;
        private static float teamQueueCountTimer = 0f;
        private const float TEAM_QUEUE_POLL_INTERVAL = 3f;
        private const float TEAM_QUEUE_COUNT_INTERVAL = 10f;

        // Tracks which queue (auto / manual) the local player joined. Read by
        // the F5 tab to render the team-pick controls only inside the manual
        // queue and to highlight the active "Search Random" / "Find Custom"
        // button.
        public static string CurrentTeamQueueType { get; private set; } = "auto";

        public static void JoinTeamQueue(string steamId, string displayName, string region, string queueType = "auto")
        {
            if (string.IsNullOrEmpty(region))
            {
                try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { region = ""; }
            }
            string qt = (queueType == "manual") ? "manual" : "auto";
            string safeName = Escape(displayName ?? steamId);
            string json = $"{{\"steam_id\":\"{Escape(steamId)}\",\"display_name\":\"{safeName}\",\"region\":\"{Escape(region ?? "")}\",\"queue_type\":\"{qt}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/team/queue/join", json,
                (success, response) =>
                {
                    if (success)
                    {
                        CurrentTeamQueueState = TeamQueueState.Searching;
                        CurrentTeamQueueType = qt;
                        IsTeamQueuePolling = true;
                        teamQueuePollTimer = 0f;
                        Plugin.Log.LogInfo($"[TEAM-QUEUE] Joined 2v2 {qt} queue");
                        string msg = qt == "manual" ? "Searching for custom 2v2 lobby..." : "Searching for 2v2 match...";
                        CompetitiveUI.ShowNotification(msg, new Color(0.4f, 0.8f, 1f));
                        NativeUI.MarkDirty();
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[TEAM-QUEUE] Join failed: {response}");
                        CompetitiveUI.ShowNotification("Failed to join 2v2 queue", new Color(1f, 0.4f, 0.4f));
                    }
                }
            ));
        }

        public static void LeaveTeamQueue(string steamId)
        {
            if (CurrentTeamQueueState == TeamQueueState.Idle && !IsTeamQueuePolling) return;
            CurrentTeamQueueState = TeamQueueState.Idle;
            IsTeamQueuePolling = false;
            LastTeamPollData = null;
            ActiveTeamSeriesId = null;
            Plugin.ClearPending2v2Slot();
            NativeUI.MarkDirty();
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/team/queue/leave?steam_id={Escape(steamId)}", "",
                (success, response) => { Plugin.Log.LogInfo("[TEAM-QUEUE] Left 2v2 queue"); }
            ));
        }

        public static void ReadyUpTeam(string steamId)
        {
            if (CurrentTeamQueueState != TeamQueueState.Matched) return;
            CurrentTeamQueueState = TeamQueueState.ReadySent;
            NativeUI.MarkDirty();
            Plugin.Log.LogInfo("[TEAM-QUEUE] Ready Up sent");
            Plugin.Instance.StartCoroutine(PostRequestWithRetry(
                $"{baseUrl}/api/v1/team/queue/ready?steam_id={Escape(steamId)}", "",
                (success, response) =>
                {
                    if (!success)
                    {
                        Plugin.Log.LogWarning($"[TEAM-QUEUE] Ready failed after retries: {response}");
                        CompetitiveUI.ShowNotification("Ready-up failed — retrying search", new Color(1f, 0.6f, 0.2f), 5f);
                        CurrentTeamQueueState = TeamQueueState.Matched;
                        NativeUI.MarkDirty();
                    }
                },
                maxRetries: 3, retryDelay: 2f
            ));
        }

        public static void UpdateTeamQueuePoll(string steamId)
        {
            if (!IsTeamQueuePolling) return;
            teamQueuePollTimer += Time.deltaTime;
            if (teamQueuePollTimer < TEAM_QUEUE_POLL_INTERVAL) return;
            teamQueuePollTimer = 0f;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/queue/poll/{steamId}",
                (success, response) =>
                {
                    if (!success || !IsTeamQueuePolling) return;
                    try { ParseTeamQueuePoll(response); }
                    catch (Exception ex) { Plugin.Log.LogError($"[TEAM-QUEUE] poll parse: {ex.Message}"); }
                }
            ));
        }

        // Polled by the F5 2v2 tab to render the "who's in queue" panel.
        // Throttled at 5s to keep request volume low.
        public static void UpdateTeamQueueList(bool force = false)
        {
            teamQueueListTimer += Time.deltaTime;
            if (!force && teamQueueListTimer < TEAM_QUEUE_LIST_INTERVAL) return;
            teamQueueListTimer = 0f;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/queue/list",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try { ParseTeamQueueList(response); NativeUI.MarkDirty(); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[TEAM-QUEUE-LIST] parse: {ex.Message}"); }
                }
            ));
        }

        private static void ParseTeamQueueList(string response)
        {
            var list = new List<TeamQueueListEntry>();
            int qStart = response.IndexOf("\"queuers\"");
            if (qStart < 0) { CachedTeamQueueList = list; return; }
            int arrStart = response.IndexOf('[', qStart);
            int arrEnd = FindMatchingBracket(response, arrStart);
            if (arrStart < 0 || arrEnd < 0) { CachedTeamQueueList = list; return; }
            string slice = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
            int oIdx = 0;
            while (oIdx < slice.Length)
            {
                int objStart = slice.IndexOf('{', oIdx);
                if (objStart < 0) break;
                int oDepth = 1, j = objStart + 1;
                while (j < slice.Length && oDepth > 0)
                {
                    if (slice[j] == '{') oDepth++;
                    else if (slice[j] == '}') oDepth--;
                    j++;
                }
                if (oDepth != 0) break;
                string obj = slice.Substring(objStart, j - objStart);
                string qt = ExtractJsonString(obj, "queue_type");
                if (string.IsNullOrEmpty(qt)) qt = "auto";
                list.Add(new TeamQueueListEntry
                {
                    steam_id = ExtractJsonString(obj, "steam_id"),
                    display_name = ExtractJsonString(obj, "display_name"),
                    rating = ExtractJsonInt(obj, "rating"),
                    balance_rating = ExtractJsonInt(obj, "balance_rating"),
                    using_fallback_rating = ExtractJsonBool(obj, "using_fallback_rating"),
                    completed_series = ExtractJsonInt(obj, "completed_series"),
                    region = ExtractJsonString(obj, "region"),
                    status = ExtractJsonString(obj, "status"),
                    team_assigned = ExtractJsonInt(obj, "team_assigned"),
                    series_id = ExtractJsonString(obj, "series_id"),
                    wait_seconds = ExtractJsonInt(obj, "wait_seconds"),
                    manual_pick_enabled = ExtractJsonBool(obj, "manual_pick_enabled"),
                    preferred_team = ExtractJsonInt(obj, "preferred_team"),
                    queue_type = qt,
                });
                oIdx = j;
            }
            CachedTeamQueueList = list;
            var autoB = new List<TeamQueueListEntry>();
            var manB = new List<TeamQueueListEntry>();
            foreach (var e in list)
            {
                if (e.queue_type == "manual") manB.Add(e); else autoB.Add(e);
            }
            CachedTeamQueueAuto = autoB;
            CachedTeamQueueManual = manB;
        }

        // Toggle the local player's manual_pick_enabled flag in the team queue.
        // When 3 of the 4 queuers have it enabled, the matchmaker honors
        // each player's preferred_team (otherwise it auto-balances by elo).
        public static void ToggleTeamManualPick(string steamId, bool enabled)
        {
            if (string.IsNullOrEmpty(steamId)) return;
            string url = $"{baseUrl}/api/v1/team/queue/manual-pick-toggle?steam_id={UnityWebRequest.EscapeURL(steamId)}&enabled={(enabled ? "true" : "false")}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (ok) Plugin.Log.LogInfo($"[2v2-MANUAL] toggle={enabled} ok: {resp}");
                else Plugin.Log.LogWarning($"[2v2-MANUAL] toggle failed: {resp}");
                UpdateTeamQueueList(force: true);
            }));
        }

        public static void SetTeamPreferredTeam(string steamId, int team)
        {
            if (string.IsNullOrEmpty(steamId)) return;
            string url = $"{baseUrl}/api/v1/team/queue/preferred-team?steam_id={UnityWebRequest.EscapeURL(steamId)}&team={team}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (ok) Plugin.Log.LogInfo($"[2v2-MANUAL] team={team} ok: {resp}");
                else Plugin.Log.LogWarning($"[2v2-MANUAL] team set failed: {resp}");
                UpdateTeamQueueList(force: true);
            }));
        }

        private static void ParseTeamQueuePoll(string response)
        {
            string status = ExtractJsonString(response, "status");
            var data = new TeamQueuePollData
            {
                status = status,
                queue_count = ExtractJsonInt(response, "queue_count"),
                elo_range = ExtractJsonInt(response, "elo_range"),
                series_id = ExtractJsonString(response, "series_id"),
                team_assigned = ExtractJsonInt(response, "team_assigned"),
                room_name = ExtractJsonString(response, "room_name"),
                room_region = ExtractJsonString(response, "room_region"),
                match_age_seconds = ExtractJsonInt(response, "match_age_seconds"),
                my_ready = ExtractJsonBool(response, "my_ready"),
            };
            data.teammates = ExtractTeamMemberList(response, "teammates");
            data.opponents = ExtractTeamMemberList(response, "opponents");
            LastTeamPollData = data;

            if (status == "ready_join")
            {
                if (!string.IsNullOrEmpty(data.room_name))
                {
                    IsTeamQueuePolling = false;
                    CurrentTeamQueueState = TeamQueueState.Idle;
                    ActiveTeamSeriesId = data.series_id;
                    // Compute MY slot in the 4-player lineup: team_assigned (1 or 2)
                    // determines team-half, and steam-id sort within team determines
                    // which of the 2 within-team slots is mine. Server's lock-time
                    // canonicalization sorts the same way, so all 4 clients agree.
                    int slot = ComputeMy2v2Slot(MatchTracker.LocalSteamId, data.team_assigned, data.teammates);
                    Plugin.SetPending2v2Slot(slot);
                    // Pre-populate Photon LocalPlayer custom properties NOW, before the
                    // room is even joined. When we join the team_ room these props ride
                    // along with the Photon Player record sent to all room members, so
                    // remote clients reading Owner.CustomProperties[p_id]/[t_id] inside
                    // Player.Start always see the correct slot — no race against
                    // PhotonNetwork.Instantiate's broadcast order.
                    try
                    {
                        var prejoin = new ExitGames.Client.Photon.Hashtable();
                        prejoin["p_id"] = slot;
                        prejoin["t_id"] = slot / 2;
                        // Publish our Steam ID under "u_id" so peers can resolve
                        // actor → Steam ID at match-end time. Vanilla
                        // PlayerAssigner.CreatePlayer normally calls AssignUserID
                        // which writes this — our 2v2 CreatePlayer override skips
                        // it (intentionally, to avoid pulling in extra ROUNDS
                        // identity machinery). Without u_id, ResolvePhotonSteamId
                        // falls back to "photon_<actor>", TryReportTeamMatch
                        // aborts with "couldn't resolve Steam ID for actor X",
                        // and the match silently routes to the 1v1 casual path.
                        // That's why every 2v2 was logging in the My Stats tab
                        // instead of the 2v2 tab.
                        string mySid = MatchTracker.LocalSteamId;
                        if (!string.IsNullOrEmpty(mySid) && mySid != "unknown")
                            prejoin["u_id"] = mySid;
                        if (PhotonNetwork.LocalPlayer != null)
                            PhotonNetwork.LocalPlayer.SetCustomProperties(prejoin);
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join SetCustomProperties: {ex.Message}"); }

                    // Publish styled NickName + cosmetic props BEFORE the Photon
                    // room join completes, so when remote clients receive the
                    // join broadcast for our actor, our NickName is already the
                    // styled version. Otherwise they cache the unstyled persona
                    // name when they first see our actor and the in-game
                    // nametag label never picks up the styling — user reported:
                    // "Sid didn't show up with all the name stylizing on
                    // anyone's screen in the first game" (then it appeared in
                    // game 2 because the periodic stats-reload publish
                    // eventually re-broadcast the styled NickName). The
                    // PublishToPhoton at room-join (GameStateWatcher) is
                    // post-join — too late for the initial spawn read.
                    try { NametagStyler.PublishToPhoton(); } catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join nametag publish: {ex.Message}"); }
                    try { PlayerColorCosmetic.PublishLocalProps(); } catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join pcolor publish: {ex.Message}"); }
                    try { TrailCosmetic.PublishLocalProps(); } catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] pre-join trail publish: {ex.Message}"); }

                    Plugin.SetPendingRoom(data.room_name, data.room_region);
                    Plugin.Log.LogInfo($"[TEAM-QUEUE] All ready! Room: {data.room_name} (region: {data.room_region ?? "auto"}) series={data.series_id} my_slot={slot}");
                    CompetitiveUI.ShowNotification("4/4 ready! Joining 2v2...", Color.green, 5f);
                    // Auto-close the F5 panel so testers don't sit on the queue screen
                    // while the Photon room is loading. Otherwise they have to manually
                    // close before they can see ROUNDS' character-select / game scene.
                    try { if (NativeUI.IsOpen) NativeUI.Close(); } catch { }
                    NativeUI.MarkDirty();
                }
            }
            else if (status == "matched")
            {
                if (CurrentTeamQueueState != TeamQueueState.ReadySent)
                    CurrentTeamQueueState = TeamQueueState.Matched;
                ActiveTeamSeriesId = data.series_id;
                NativeUI.MarkDirty();
            }
            else if (status == "searching")
            {
                if (CurrentTeamQueueState != TeamQueueState.Searching)
                {
                    // Was matched, got bumped back (someone left)
                    CurrentTeamQueueState = TeamQueueState.Searching;
                    ActiveTeamSeriesId = null;
                    Plugin.ClearPending2v2Slot();
                    CompetitiveUI.ShowNotification("Match canceled — re-searching", new Color(1f, 0.6f, 0.2f), 5f);
                }
                NativeUI.MarkDirty();
            }
            else if (status == "expired" || status == "not_in_queue")
            {
                IsTeamQueuePolling = false;
                CurrentTeamQueueState = TeamQueueState.Idle;
                LastTeamPollData = null;
                ActiveTeamSeriesId = null;
                Plugin.ClearPending2v2Slot();
                NativeUI.MarkDirty();
            }
        }

        /// <summary>Compute the local player's 0-3 slot in the 4-player ROUNDS
        /// lineup. Team 1 → slots 0,1; team 2 → slots 2,3. Within each team,
        /// the 2 slots are assigned by steam-id ordinal sort — same canonical
        /// rule the server uses at lock time, so all 4 clients independently
        /// arrive at consistent unique slots without any extra coordination.</summary>
        public static int ComputeMy2v2Slot(string mySteamId, int teamAssigned, List<TeamQueueMember> teammates)
        {
            int teamBase = (teamAssigned == 2) ? 2 : 0;
            // Find my one teammate (same team_assigned). If we can't, fall
            // back to slot 0 within team — better than collision.
            string mateSteamId = null;
            if (teammates != null)
            {
                foreach (var t in teammates)
                {
                    if (t == null) continue;
                    if (t.team_assigned == teamAssigned && t.steam_id != mySteamId)
                    {
                        mateSteamId = t.steam_id;
                        break;
                    }
                }
            }
            if (string.IsNullOrEmpty(mateSteamId)) return teamBase;
            // Within-team sort by steam_id ordinal. Lower = slot 0; higher = slot 1.
            int withinTeam = string.Compare(mySteamId, mateSteamId, StringComparison.Ordinal) <= 0 ? 0 : 1;
            return teamBase + withinTeam;
        }

        /// <summary>Manual TeamQueueMember[] parser. Photon JsonUtility chokes on
        /// nested arrays so we hand-extract the slice for `key`. Format:
        /// `"key":[{...},{...}]`. Returns empty list on missing/malformed.</summary>
        private static List<TeamQueueMember> ExtractTeamMemberList(string json, string key)
        {
            var list = new List<TeamQueueMember>();
            try
            {
                int kIdx = json.IndexOf("\"" + key + "\":[");
                if (kIdx < 0) return list;
                int start = kIdx + key.Length + 4;
                int depth = 1, i = start;
                while (i < json.Length && depth > 0)
                {
                    if (json[i] == '[') depth++;
                    else if (json[i] == ']') depth--;
                    i++;
                }
                if (depth != 0) return list;
                string slice = json.Substring(start, i - start - 1);
                int oIdx = 0;
                while (oIdx < slice.Length)
                {
                    int objStart = slice.IndexOf('{', oIdx);
                    if (objStart < 0) break;
                    int oDepth = 1, j = objStart + 1;
                    while (j < slice.Length && oDepth > 0)
                    {
                        if (slice[j] == '{') oDepth++;
                        else if (slice[j] == '}') oDepth--;
                        j++;
                    }
                    if (oDepth != 0) break;
                    string obj = slice.Substring(objStart, j - objStart);
                    list.Add(new TeamQueueMember
                    {
                        steam_id = ExtractJsonString(obj, "steam_id"),
                        display_name = ExtractJsonString(obj, "display_name"),
                        rating = ExtractJsonInt(obj, "rating"),
                        region = ExtractJsonString(obj, "region"),
                        team_assigned = ExtractJsonInt(obj, "team_assigned"),
                        using_fallback_rating = ExtractJsonBool(obj, "using_fallback_rating"),
                        balance_rating = ExtractJsonInt(obj, "balance_rating"),
                        completed_series = ExtractJsonInt(obj, "completed_series"),
                        ready = ExtractJsonBool(obj, "ready"),
                    });
                    oIdx = j;
                }
            }
            catch { }
            return list;
        }

        public static void UpdateTeamQueueCount()
        {
            teamQueueCountTimer += Time.deltaTime;
            if (teamQueueCountTimer < TEAM_QUEUE_COUNT_INTERVAL) return;
            teamQueueCountTimer = 0f;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/queue/count",
                (success, response) =>
                {
                    if (success)
                    {
                        int s = ExtractJsonInt(response, "searching");
                        if (s != CachedTeamQueueSearching)
                        {
                            CachedTeamQueueSearching = s;
                            NativeUI.MarkDirty();
                        }
                    }
                }
            ));
        }

        /// <summary>Tracks the most recent series-state poll response so the
        /// dispatcher coroutine can react. Set by PollTeamSeriesState.</summary>
        public static string LastSeriesStateStatus = null;
        public static string LastSeriesStateReason = null;
        public static int LastSeriesStateConfirmations = 0;
        public static int LastSeriesDcGraceSeconds = 0;
        public static int LastSeriesDcTeamRemaining = 0;
        public static int LastSeriesT1Wins = 0;
        public static int LastSeriesT2Wins = 0;
        // Throttled background poll of the team-series state — 2s while we
        // have an active or paused series, off otherwise.
        private static float teamSeriesStateTimer = 0f;
        private const float TEAM_SERIES_STATE_INTERVAL = 2f;
        public static void UpdateTeamSeriesStatePoll(bool force)
        {
            string sid = ActiveTeamSeriesId;
            if (string.IsNullOrEmpty(sid)) return;
            teamSeriesStateTimer += Time.deltaTime;
            if (!force && teamSeriesStateTimer < TEAM_SERIES_STATE_INTERVAL) return;
            teamSeriesStateTimer = 0f;
            PollTeamSeriesState(sid, (status, reason, conf) =>
            {
                // PollTeamSeriesState already populates LastSeriesStateStatus etc.
                // We just need to extract the DC fields, which it doesn't currently
                // parse — the response JSON has them, but the in-helper parse uses
                // a fixed callback signature. Refresh in a separate parse below.
            });
        }

        /// <summary>POST /team/series/{id}/report-dc. Called from
        /// Cr2v2DiagCallbacks.OnPlayerLeftRoom when the lowest-Steam-ID remaining
        /// client detects a mid-series DC. Server applies the 2v2 DC rule (any
        /// match abandoned with >=2 total points → non-DC team wins) and starts
        /// the 5-min sticky-team requeue grace window.</summary>
        public static void ReportTeamSeriesDc(
            string seriesId, string reporterSteamId, string dcPlayerSteamId,
            int t1PointsTotal, int t2PointsTotal)
        {
            if (string.IsNullOrEmpty(seriesId) || string.IsNullOrEmpty(reporterSteamId) || string.IsNullOrEmpty(dcPlayerSteamId)) return;
            string sig = ComputeHmacHex($"{reporterSteamId}:{seriesId}:{dcPlayerSteamId}:dc");
            string url = $"{baseUrl}/api/v1/team/series/{seriesId}/report-dc" +
                         $"?reporter_steam_id={UnityWebRequest.EscapeURL(reporterSteamId)}" +
                         $"&dc_player_steam_id={UnityWebRequest.EscapeURL(dcPlayerSteamId)}" +
                         $"&t1_points_total={t1PointsTotal}" +
                         $"&t2_points_total={t2PointsTotal}" +
                         $"&hmac_sig={UnityWebRequest.EscapeURL(sig)}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (ok) Plugin.Log.LogInfo($"[2v2-DC] report accepted: {resp}");
                else Plugin.Log.LogWarning($"[2v2-DC] report failed: {resp}");
            }));
        }

        /// <summary>POST /team/series/{id}/spawn-confirm. Called from the auto-spawn
        /// coroutine when CreatePlayer override successfully creates the local
        /// Player in a cr_ff room. Idempotent server-side.</summary>
        public static void SendTeamSpawnConfirm(string seriesId, string steamId)
        {
            if (string.IsNullOrEmpty(seriesId) || string.IsNullOrEmpty(steamId)) return;
            string sig = ComputeHmacHex($"{steamId}:{seriesId}:spawn");
            string url = $"{baseUrl}/api/v1/team/series/{seriesId}/spawn-confirm" +
                         $"?steam_id={UnityWebRequest.EscapeURL(steamId)}" +
                         $"&hmac_sig={UnityWebRequest.EscapeURL(sig)}";
            Plugin.Instance.StartCoroutine(PostRequest(url, "", (ok, resp) =>
            {
                if (ok) Plugin.Log.LogInfo($"[2v2] spawn-confirm OK: {resp}");
                else Plugin.Log.LogWarning($"[2v2] spawn-confirm failed: {resp}");
            }));
        }

        /// <summary>GET /team/series/{id}/state. Polled during the first 20s
        /// after ready_join to detect server-side assembly cancel.</summary>
        public static void PollTeamSeriesState(string seriesId, Action<string, string, int> onResponse)
        {
            if (string.IsNullOrEmpty(seriesId)) return;
            string url = $"{baseUrl}/api/v1/team/series/{seriesId}/state";
            Plugin.Instance.StartCoroutine(GetRequest(url, (ok, resp) =>
            {
                if (!ok || string.IsNullOrEmpty(resp)) return;
                string status = ExtractJsonString(resp, "status") ?? "";
                string reason = ExtractJsonString(resp, "reason") ?? "";
                int conf = ExtractJsonInt(resp, "confirmations");
                LastSeriesStateStatus = status;
                LastSeriesStateReason = reason;
                LastSeriesStateConfirmations = conf;
                LastSeriesDcGraceSeconds = ExtractJsonInt(resp, "dc_grace_seconds_remaining");
                LastSeriesDcTeamRemaining = ExtractJsonInt(resp, "dc_team_remaining");
                LastSeriesT1Wins = ExtractJsonInt(resp, "t1_series_wins");
                LastSeriesT2Wins = ExtractJsonInt(resp, "t2_series_wins");
                onResponse?.Invoke(status, reason, conf);
            }));
        }

        /// <summary>Submit a 2v2 match. Reporter is the lowest Steam ID across
        /// all 4 participants. Builds the 11-field HMAC over
        /// t1a:t1b:t2a:t2b:t1r:t2r:is_ranked:reporter:room_id:winner_team:series_id.</summary>
        public static void ReportTeamMatch(
            string seriesId,
            string t1aSteam, string t1aName, List<MatchTracker.CardPickData> t1aCards,
            string t1bSteam, string t1bName, List<MatchTracker.CardPickData> t1bCards,
            string t2aSteam, string t2aName, List<MatchTracker.CardPickData> t2aCards,
            string t2bSteam, string t2bName, List<MatchTracker.CardPickData> t2bCards,
            int t1Rounds, int t2Rounds, int t1Points, int t2Points,
            string photonRoomId, string region, int durationSeconds, DateTime startedAt,
            string reporterSteamId, bool isRanked, int winnerTeam,
            int t1aFps, int t1bFps, int t2aFps, int t2bFps)
        {
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"series_id\":\"{Escape(seriesId)}\",");
            void appendPlayer(string field, string sid, string name, List<MatchTracker.CardPickData> cards)
            {
                sb.Append($"\"{field}\":{{\"steam_id\":\"{Escape(sid)}\",\"display_name\":\"{Escape(name)}\",\"cards\":[");
                AppendCards(sb, cards);
                sb.Append("],\"card_offers\":[]},");
            }
            appendPlayer("t1a", t1aSteam, t1aName, t1aCards);
            appendPlayer("t1b", t1bSteam, t1bName, t1bCards);
            appendPlayer("t2a", t2aSteam, t2aName, t2aCards);
            appendPlayer("t2b", t2bSteam, t2bName, t2bCards);
            sb.Append($"\"t1_rounds_won\":{t1Rounds},");
            sb.Append($"\"t2_rounds_won\":{t2Rounds},");
            sb.Append($"\"t1_points_total\":{t1Points},");
            sb.Append($"\"t2_points_total\":{t2Points},");
            sb.Append($"\"winner_team\":{winnerTeam},");
            sb.Append($"\"photon_room_id\":\"{Escape(photonRoomId)}\",");
            sb.Append($"\"game_version\":\"v{Application.version}\",");
            sb.Append($"\"region\":\"{Escape(region)}\",");
            sb.Append($"\"match_duration\":{durationSeconds},");
            sb.Append($"\"started_at\":\"{startedAt:yyyy-MM-ddTHH:mm:ssZ}\",");
            sb.Append($"\"is_ranked\":{(isRanked ? "true" : "false")},");
            sb.Append($"\"reported_by_steam_id\":\"{Escape(reporterSteamId)}\",");
            sb.Append($"\"t1a_fps\":{t1aFps},\"t1b_fps\":{t1bFps},\"t2a_fps\":{t2aFps},\"t2b_fps\":{t2bFps},");

            string canonical =
                $"{t1aSteam}:{t1bSteam}:{t2aSteam}:{t2bSteam}:" +
                $"{t1Rounds}:{t2Rounds}:" +
                $"{(isRanked ? "true" : "false")}:{reporterSteamId}:" +
                $"{photonRoomId ?? ""}:{winnerTeam}:{seriesId}";
            string sig = ComputeHmacHex(canonical);
            sb.Append($"\"hmac_signature\":\"{sig}\"");
            sb.Append("}");

            string json = sb.ToString();
            Plugin.Log.LogInfo($"Reporting 2v2 match (series={seriesId}, winner=T{winnerTeam}, {t1Rounds}-{t2Rounds})...");
            Plugin.Instance.StartCoroutine(PostRequestWithRetry(
                $"{baseUrl}/api/v1/team/matches", json,
                (success, response) =>
                {
                    if (success)
                    {
                        Plugin.Log.LogInfo($"2v2 match reported: {response}");
                        string sStatus = ExtractJsonString(response, "series_status");
                        string sScore = ExtractJsonString(response, "series_score");
                        if (sStatus == "completed")
                        {
                            CompetitiveUI.ShowNotification($"Series complete: {sScore}", Color.green, 6f);
                            // Tally the series result into the Session Info panel
                            // (2v2 row). series_score is from the reporter's team
                            // perspective, e.g. "2-1" if the reporter's team won.
                            try
                            {
                                bool seriesWon = false;
                                if (!string.IsNullOrEmpty(sScore))
                                {
                                    var sp = sScore.Split('-');
                                    if (sp.Length == 2 && int.TryParse(sp[0], out int sw) && int.TryParse(sp[1], out int sl))
                                        seriesWon = sw > sl;
                                }
                                // The reporter is the lowest-Steam-ID participant.
                                // For OTHER team members the report still lands but
                                // the local report-callback only fires on the
                                // reporter's client. Fan out via team-stats refresh
                                // below which all 4 will pick up.
                                GameStateWatcher.RecordSessionTeamSeries(seriesWon);
                            }
                            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2] session tally failed: {ex.Message}"); }
                            ActiveTeamSeriesId = null;
                            Plugin.ClearPending2v2Slot();
                        }
                        else if (!string.IsNullOrEmpty(sScore))
                        {
                            CompetitiveUI.ShowNotification($"Series: {sScore}", new Color(0.6f, 0.8f, 1f), 4f);
                        }
                        // Mid-series rebalance — server sends rebalance_assignments
                        // when the previous match was lopsided enough to swap a
                        // weakest-winner with strongest-loser. Parse + log so we
                        // can verify the trigger; full client-side team mutation
                        // (TeamID + spawn + body color updates) ships next round.
                        try
                        {
                            int rIdx = response.IndexOf("\"rebalance_assignments\":");
                            if (rIdx >= 0)
                            {
                                int oStart = response.IndexOf('{', rIdx);
                                int oEnd = oStart >= 0 ? FindMatchingBrace(response, oStart) : -1;
                                if (oStart > 0 && oEnd > oStart)
                                {
                                    string slice = response.Substring(oStart + 1, oEnd - oStart - 1);
                                    if (!string.IsNullOrEmpty(slice.Trim()))
                                    {
                                        Plugin.Log.LogInfo($"[2v2-REBALANCE] server says swap teams next match: {slice}");
                                        CompetitiveUI.ShowNotification("Teams will rebalance next match!", new Color(1f, 0.8f, 0.4f), 5f);
                                    }
                                }
                            }
                        }
                        catch (Exception rex) { Plugin.Log.LogWarning($"[2v2-REBALANCE] parse: {rex.Message}"); }
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"2v2 match report failed: {response}");
                    }
                },
                maxRetries: 3, retryDelay: 2f
            ));
        }

        public static void ResetTeamQueue()
        {
            CurrentTeamQueueState = TeamQueueState.Idle;
            IsTeamQueuePolling = false;
            LastTeamPollData = null;
        }

        // ── 2v2 Leaderboard ──────────────────────────────────────
        [Serializable]
        public class TeamLeaderboardEntry
        {
            public int rank;
            public string steam_id;
            public string display_name;
            public int rating;
            public int rd;
            public int completed_series;
            public int series_wins;
            public int series_losses;
            public float win_rate;
            public int level;
            public string title, title_color;
            public int avg_teammate_elo;
            public int team_gold_earned;
            public int team_xp_earned;
        }
        public static List<TeamLeaderboardEntry> CachedTeamLeaderboard { get; private set; } = new List<TeamLeaderboardEntry>();
        public static int CachedTeamLeaderboardTotal { get; private set; } = 0;
        public static string CachedTeamLeaderboardSort { get; private set; } = "rating";

        // ── Paged 2v2 series feed ──────────────────────────────
        // Drives Recent 2v2 Series. Replaces the per-player team-matches feed
        // with a global paginated view that includes per-player gold/xp + titles.
        [Serializable]
        public class TeamSeriesSlot
        {
            public string steam_id, name, title, title_color;
            public int rating;
            public float rating_change;
            public int gold_earned, xp_earned;
        }

        [Serializable]
        public class TeamSeriesMatch
        {
            public string match_id, ended_at;
            public int t1_rounds_won, t2_rounds_won, t1_points_total, t2_points_total;
            // steam_id -> [card_name, card_name, ...]
            public Dictionary<string, List<string>> cards_by_player = new Dictionary<string, List<string>>();
        }

        [Serializable]
        public class TeamSeriesPagedEntry
        {
            public string series_id, completed_at;
            public int winner_team, t1_series_wins, t2_series_wins;
            public TeamSeriesSlot t1a, t1b, t2a, t2b;
            public List<TeamSeriesMatch> matches = new List<TeamSeriesMatch>();
        }

        public static List<TeamSeriesPagedEntry> CachedTeamSeriesPaged { get; private set; } = new List<TeamSeriesPagedEntry>();
        public static int CachedTeamSeriesTotal { get; private set; } = 0;
        public static int CachedTeamSeriesPage { get; private set; } = 0;
        public static int CachedTeamSeriesPageSize { get; private set; } = 3;
        public static int CachedTeamSeriesTotalPages { get; private set; } = 0;

        public static void FetchAllSeriesPaged(int page = 0, int pageSize = 3)
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/all-series-paged?page={page}&page_size={pageSize}",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try { ParseAllSeriesPaged(response, page, pageSize); NativeUI.MarkDirty(); }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[TEAM-SERIES-PAGED] parse: {ex.Message}"); }
                }
            ));
        }

        private static void ParseAllSeriesPaged(string response, int reqPage, int reqPageSize)
        {
            var list = new List<TeamSeriesPagedEntry>();
            int sStart = response.IndexOf("\"series\"");
            if (sStart < 0) { CachedTeamSeriesPaged = list; return; }
            int arrStart = response.IndexOf('[', sStart);
            int arrEnd = FindMatchingBracket(response, arrStart);
            if (arrStart < 0 || arrEnd < 0) { CachedTeamSeriesPaged = list; return; }
            string slice = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
            int oIdx = 0;
            while (oIdx < slice.Length)
            {
                int objStart = slice.IndexOf('{', oIdx);
                if (objStart < 0) break;
                int oEnd = FindMatchingBrace(slice, objStart);
                if (oEnd < 0) break;
                string obj = slice.Substring(objStart, oEnd - objStart + 1);
                var e = new TeamSeriesPagedEntry
                {
                    series_id = ExtractJsonString(obj, "series_id"),
                    completed_at = ExtractJsonString(obj, "completed_at"),
                    winner_team = ExtractJsonInt(obj, "winner_team"),
                    t1_series_wins = ExtractJsonInt(obj, "t1_series_wins"),
                    t2_series_wins = ExtractJsonInt(obj, "t2_series_wins"),
                    t1a = ParseSeriesSlot(obj, "t1a"),
                    t1b = ParseSeriesSlot(obj, "t1b"),
                    t2a = ParseSeriesSlot(obj, "t2a"),
                    t2b = ParseSeriesSlot(obj, "t2b"),
                    matches = ParseSeriesMatches(obj),
                };
                list.Add(e);
                oIdx = oEnd + 1;
            }
            CachedTeamSeriesPaged = list;
            CachedTeamSeriesTotal = ExtractJsonInt(response, "total");
            CachedTeamSeriesPage = reqPage;
            CachedTeamSeriesPageSize = reqPageSize;
            CachedTeamSeriesTotalPages = ExtractJsonInt(response, "total_pages");
        }

        private static TeamSeriesSlot ParseSeriesSlot(string seriesObj, string slotKey)
        {
            // Find "<slotKey>": { ... }  inside the series object.
            int kIdx = seriesObj.IndexOf($"\"{slotKey}\":");
            if (kIdx < 0) return new TeamSeriesSlot();
            int oStart = seriesObj.IndexOf('{', kIdx);
            int oEnd = FindMatchingBrace(seriesObj, oStart);
            if (oStart < 0 || oEnd < 0) return new TeamSeriesSlot();
            string s = seriesObj.Substring(oStart, oEnd - oStart + 1);
            return new TeamSeriesSlot
            {
                steam_id = ExtractJsonString(s, "steam_id"),
                name = ExtractJsonString(s, "name"),
                title = ExtractJsonString(s, "title"),
                title_color = ExtractJsonString(s, "title_color"),
                rating = (int)ExtractJsonFloat(s, "rating"),
                rating_change = ExtractJsonFloat(s, "rating_change"),
                gold_earned = ExtractJsonInt(s, "gold_earned"),
                xp_earned = ExtractJsonInt(s, "xp_earned"),
            };
        }

        private static List<TeamSeriesMatch> ParseSeriesMatches(string seriesObj)
        {
            var list = new List<TeamSeriesMatch>();
            int mIdx = seriesObj.IndexOf("\"matches\":");
            if (mIdx < 0) return list;
            int aStart = seriesObj.IndexOf('[', mIdx);
            int aEnd = FindMatchingBracket(seriesObj, aStart);
            if (aStart < 0 || aEnd < 0) return list;
            string slice = seriesObj.Substring(aStart + 1, aEnd - aStart - 1);
            int cur = 0;
            while (cur < slice.Length)
            {
                int objStart = slice.IndexOf('{', cur);
                if (objStart < 0) break;
                int oEnd = FindMatchingBrace(slice, objStart);
                if (oEnd < 0) break;
                string m = slice.Substring(objStart, oEnd - objStart + 1);
                var entry = new TeamSeriesMatch
                {
                    match_id = ExtractJsonString(m, "match_id"),
                    ended_at = ExtractJsonString(m, "ended_at"),
                    t1_rounds_won = ExtractJsonInt(m, "t1_rounds_won"),
                    t2_rounds_won = ExtractJsonInt(m, "t2_rounds_won"),
                    t1_points_total = ExtractJsonInt(m, "t1_points_total"),
                    t2_points_total = ExtractJsonInt(m, "t2_points_total"),
                };
                // cards_by_player parser (same shape as TeamMatchHistoryEntry).
                int cIdx = m.IndexOf("\"cards_by_player\":");
                if (cIdx >= 0)
                {
                    int cbStart = m.IndexOf('{', cIdx);
                    int cbEnd = FindMatchingBrace(m, cbStart);
                    if (cbStart >= 0 && cbEnd > cbStart)
                    {
                        string cbSlice = m.Substring(cbStart + 1, cbEnd - cbStart - 1);
                        int cursor = 0;
                        while (cursor < cbSlice.Length)
                        {
                            int kS = cbSlice.IndexOf('"', cursor);
                            if (kS < 0) break;
                            int kE = cbSlice.IndexOf('"', kS + 1);
                            if (kE < 0) break;
                            string sid = cbSlice.Substring(kS + 1, kE - kS - 1);
                            int aS2 = cbSlice.IndexOf('[', kE);
                            int aE2 = FindMatchingBracket(cbSlice, aS2);
                            if (aS2 < 0 || aE2 < 0) break;
                            string aSlice = cbSlice.Substring(aS2 + 1, aE2 - aS2 - 1);
                            // Cards are bare strings here (the new endpoint flattens them).
                            var cards = new List<string>();
                            int sCur = 0;
                            while (sCur < aSlice.Length)
                            {
                                int qs = aSlice.IndexOf('"', sCur);
                                if (qs < 0) break;
                                int qe = aSlice.IndexOf('"', qs + 1);
                                if (qe < 0) break;
                                cards.Add(aSlice.Substring(qs + 1, qe - qs - 1));
                                sCur = qe + 1;
                            }
                            entry.cards_by_player[sid] = cards;
                            cursor = aE2 + 1;
                        }
                    }
                }
                list.Add(entry);
                cur = oEnd + 1;
            }
            return list;
        }

        public class TeamMatchHistoryEntry
        {
            public string match_id, series_id, ended_at;
            public bool won;
            public int my_team;
            public string t1a_steam_id, t1a_name, t1b_steam_id, t1b_name;
            public string t2a_steam_id, t2a_name, t2b_steam_id, t2b_name;
            public int t1_rounds_won, t2_rounds_won;
            public int t1_points_total, t2_points_total;
            public string series_score;
            public float series_rating_change;
            // FPS keyed by Steam ID; absent = no data
            public Dictionary<string, int> fps_by_player = new Dictionary<string, int>();
            // Card names picked, keyed by Steam ID. Drives the per-match cards
            // section in the F5 2v2 history UI ("Sid+Sid2 took: Shields Up,
            // Big Bullet  vs  Sid3+Sid4 took: Dazzle, Cold Bullets").
            public Dictionary<string, List<string>> cards_by_player = new Dictionary<string, List<string>>();
        }
        public static List<TeamMatchHistoryEntry> CachedTeamMatchHistory { get; private set; } = new List<TeamMatchHistoryEntry>();

        [Serializable]
        public class TeamStatsData
        {
            public string steam_id, display_name;
            public float rating, rating_deviation, peak_rating;
            public int completed_series, series_wins, series_losses;
            public float series_win_rate;
            public int match_wins, match_losses, current_streak;
        }
        public static TeamStatsData CachedTeamStats { get; private set; }

        public static void FetchTeamStats(string steamId)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/players/{steamId}/team-stats",
                (success, response) =>
                {
                    if (!success) return;
                    try
                    {
                        var d = new TeamStatsData
                        {
                            steam_id = ExtractJsonString(response, "steam_id"),
                            display_name = ExtractJsonString(response, "display_name"),
                            rating = ExtractJsonFloat(response, "rating"),
                            rating_deviation = ExtractJsonFloat(response, "rating_deviation"),
                            peak_rating = ExtractJsonFloat(response, "peak_rating"),
                            completed_series = ExtractJsonInt(response, "completed_series"),
                            series_wins = ExtractJsonInt(response, "series_wins"),
                            series_losses = ExtractJsonInt(response, "series_losses"),
                            series_win_rate = ExtractJsonFloat(response, "series_win_rate"),
                            match_wins = ExtractJsonInt(response, "match_wins"),
                            match_losses = ExtractJsonInt(response, "match_losses"),
                            current_streak = ExtractJsonInt(response, "current_streak"),
                        };
                        CachedTeamStats = d;
                        NativeUI.MarkDirty();
                    }
                    catch (Exception ex) { Plugin.Log.LogError($"[TEAM-STATS] parse: {ex.Message}"); }
                }
            ));
        }

        public static void FetchTeamMatchHistory(string steamId, int limit = 50)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/players/{steamId}/team-matches?limit={limit}",
                (success, response) =>
                {
                    if (!success) return;
                    try
                    {
                        var entries = new List<TeamMatchHistoryEntry>();
                        if (string.IsNullOrEmpty(response) || response.Trim() == "[]")
                        {
                            CachedTeamMatchHistory = entries;
                            NativeUI.MarkDirty();
                            return;
                        }
                        var parts = response.Split(new[] { "\"match_id\"" }, StringSplitOptions.None);
                        for (int i = 1; i < parts.Length; i++)
                        {
                            var chunk = parts[i];
                            var e = new TeamMatchHistoryEntry
                            {
                                match_id = ExtractJsonString(chunk, ""),
                                series_id = ExtractJsonString(chunk, "series_id"),
                                ended_at = ExtractJsonString(chunk, "ended_at"),
                                won = chunk.Contains("\"won\":true"),
                                my_team = ExtractJsonInt(chunk, "my_team"),
                                t1a_steam_id = ExtractJsonString(chunk, "t1a_steam_id"),
                                t1a_name = ExtractJsonString(chunk, "t1a_name"),
                                t1b_steam_id = ExtractJsonString(chunk, "t1b_steam_id"),
                                t1b_name = ExtractJsonString(chunk, "t1b_name"),
                                t2a_steam_id = ExtractJsonString(chunk, "t2a_steam_id"),
                                t2a_name = ExtractJsonString(chunk, "t2a_name"),
                                t2b_steam_id = ExtractJsonString(chunk, "t2b_steam_id"),
                                t2b_name = ExtractJsonString(chunk, "t2b_name"),
                                t1_rounds_won = ExtractJsonInt(chunk, "t1_rounds_won"),
                                t2_rounds_won = ExtractJsonInt(chunk, "t2_rounds_won"),
                                t1_points_total = ExtractJsonInt(chunk, "t1_points_total"),
                                t2_points_total = ExtractJsonInt(chunk, "t2_points_total"),
                                series_score = ExtractJsonString(chunk, "series_score"),
                                series_rating_change = ExtractJsonFloat(chunk, "series_rating_change"),
                            };
                            // Parse cards_by_player: dict keyed by steam_id, value
                            // is a list of card-objects each with a card_name.
                            try
                            {
                                int cStart = chunk.IndexOf("\"cards_by_player\"");
                                if (cStart >= 0)
                                {
                                    int oStart = chunk.IndexOf('{', cStart);
                                    int oEnd = FindMatchingBrace(chunk, oStart);
                                    if (oStart >= 0 && oEnd > oStart)
                                    {
                                        string slice = chunk.Substring(oStart + 1, oEnd - oStart - 1);
                                        int cursor = 0;
                                        while (cursor < slice.Length)
                                        {
                                            int kS = slice.IndexOf('"', cursor);
                                            if (kS < 0) break;
                                            int kE = slice.IndexOf('"', kS + 1);
                                            if (kE < 0) break;
                                            string sid = slice.Substring(kS + 1, kE - kS - 1);
                                            int aS = slice.IndexOf('[', kE);
                                            int aE = FindMatchingBracket(slice, aS);
                                            if (aS < 0 || aE < 0) break;
                                            string aSlice = slice.Substring(aS + 1, aE - aS - 1);
                                            var cardList = new List<string>();
                                            int oC = 0;
                                            while (oC < aSlice.Length)
                                            {
                                                int oS = aSlice.IndexOf('{', oC);
                                                if (oS < 0) break;
                                                int oD = 1, j = oS + 1;
                                                while (j < aSlice.Length && oD > 0)
                                                {
                                                    if (aSlice[j] == '{') oD++;
                                                    else if (aSlice[j] == '}') oD--;
                                                    j++;
                                                }
                                                string objStr = aSlice.Substring(oS, j - oS);
                                                string cn = ExtractJsonString(objStr, "card_name");
                                                if (!string.IsNullOrEmpty(cn)) cardList.Add(cn);
                                                oC = j;
                                            }
                                            e.cards_by_player[sid] = cardList;
                                            cursor = aE + 1;
                                        }
                                    }
                                }
                            }
                            catch { }
                            entries.Add(e);
                        }
                        CachedTeamMatchHistory = entries;
                        Plugin.Log.LogInfo($"[TEAM-HIST] loaded {entries.Count} 2v2 matches");
                        NativeUI.MarkDirty();
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogError($"[TEAM-HIST] parse: {ex.Message}");
                    }
                }
            ));
        }

        public static void FetchTeamLeaderboard(int limit = 200, string sortBy = "rating")
        {
            CachedTeamLeaderboardSort = sortBy;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/team/leaderboard?limit={limit}&sort_by={sortBy}",
                (success, response) =>
                {
                    if (!success) return;
                    try
                    {
                        var entries = new List<TeamLeaderboardEntry>();
                        var parts = response.Split(new[] { "\"rank\":" }, StringSplitOptions.None);
                        for (int i = 1; i < parts.Length; i++)
                        {
                            var chunk = parts[i];
                            int rankVal = 0; try { int comma = chunk.IndexOf(','); rankVal = int.Parse(chunk.Substring(0, comma)); } catch { }
                            entries.Add(new TeamLeaderboardEntry
                            {
                                rank = rankVal,
                                steam_id = ExtractJsonString(chunk, "steam_id"),
                                display_name = ExtractJsonString(chunk, "display_name"),
                                rating = ExtractJsonInt(chunk, "rating"),
                                rd = ExtractJsonInt(chunk, "rd"),
                                completed_series = ExtractJsonInt(chunk, "completed_series"),
                                series_wins = ExtractJsonInt(chunk, "series_wins"),
                                series_losses = ExtractJsonInt(chunk, "series_losses"),
                                win_rate = ExtractJsonFloat(chunk, "win_rate"),
                                level = ExtractJsonInt(chunk, "level"),
                                title = ExtractJsonString(chunk, "title"),
                                title_color = ExtractJsonString(chunk, "title_color"),
                                avg_teammate_elo = ExtractJsonInt(chunk, "avg_teammate_elo"),
                                team_gold_earned = ExtractJsonInt(chunk, "team_gold_earned"),
                                team_xp_earned = ExtractJsonInt(chunk, "team_xp_earned"),
                            });
                        }
                        CachedTeamLeaderboard = entries;
                        CachedTeamLeaderboardTotal = ExtractJsonInt(response, "total_players");
                        NativeUI.MarkDirty();
                        Plugin.Log.LogInfo($"[TEAM-LB] Loaded {entries.Count} 2v2 ranked players");
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogError($"[TEAM-LB] parse error: {ex.Message}");
                    }
                }
            ));
        }

        // ── Player Blocks (permanent, from leaderboard) ──────────

        public static HashSet<string> BlockedSteamIds { get; private set; } = new HashSet<string>();
        private static bool blocksLoaded = false;

        public static void FetchBlockedPlayers(string steamId)
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/blocks/{steamId}",
                (success, response) =>
                {
                    if (success)
                    {
                        BlockedSteamIds.Clear();
                        // Parse JSON array of steam IDs
                        int arrStart = response.IndexOf("[");
                        int arrEnd = response.IndexOf("]");
                        if (arrStart >= 0 && arrEnd > arrStart)
                        {
                            string arr = response.Substring(arrStart + 1, arrEnd - arrStart - 1);
                            if (!string.IsNullOrEmpty(arr))
                            {
                                foreach (string part in arr.Split(','))
                                {
                                    string sid = part.Trim().Trim('"');
                                    if (!string.IsNullOrEmpty(sid))
                                        BlockedSteamIds.Add(sid);
                                }
                            }
                        }
                        blocksLoaded = true;
                        NativeUI.MarkDirty();
                        Plugin.Log.LogInfo($"[BLOCKS] Loaded {BlockedSteamIds.Count} blocked players");
                    }
                }
            ));
        }

        public static bool IsPlayerBlocked(string steamId)
        {
            return BlockedSteamIds.Contains(steamId);
        }

        // ── Disconnect Reporting (leave % tracking) ─────────

        public static void ReportDisconnect(string reporterSteamId, string disconnectedSteamId)
        {
            if (string.IsNullOrEmpty(reporterSteamId) || string.IsNullOrEmpty(disconnectedSteamId)) return;
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/report-disconnect?reporter_steam_id={Escape(reporterSteamId)}&disconnected_steam_id={Escape(disconnectedSteamId)}",
                "",
                (success, response) =>
                {
                    if (success)
                        Plugin.Log.LogInfo($"[DC] Reported disconnect by {disconnectedSteamId}: {response}");
                    else
                        Plugin.Log.LogWarning($"[DC] Failed to report disconnect: {response}");
                }
            ));
        }

        public static void BlockPlayer(string mySteamId, string targetSteamId, Action<bool> callback = null)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/players/block?steam_id={Escape(mySteamId)}&target_steam_id={Escape(targetSteamId)}&sig={ComputeHmacHex($"block:{mySteamId}:{targetSteamId}")}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        BlockedSteamIds.Add(targetSteamId);
                        Plugin.Log.LogInfo($"[BLOCKS] Blocked {targetSteamId}");
                        NativeUI.MarkDirty();
                    }
                    callback?.Invoke(success);
                }
            ));
        }

        public static void UnblockPlayer(string mySteamId, string targetSteamId, Action<bool> callback = null)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/players/unblock?steam_id={Escape(mySteamId)}&target_steam_id={Escape(targetSteamId)}&sig={ComputeHmacHex($"unblock:{mySteamId}:{targetSteamId}")}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        BlockedSteamIds.Remove(targetSteamId);
                        Plugin.Log.LogInfo($"[BLOCKS] Unblocked {targetSteamId}");
                        NativeUI.MarkDirty();
                    }
                    callback?.Invoke(success);
                }
            ));
        }

        // ── HTTP helpers ──────────────────────────────────────

        // Stamp every outbound API call with the mod's own version so the server
        // can reject (426) any client that drops below the configured floor.
        private static void StampVersionHeader(UnityWebRequest req)
        {
            try { req.SetRequestHeader("X-Mod-Version", Plugin.ModVersion ?? "0.0.0"); } catch { }
        }

        // Paths that MUST work before consent is granted (version probe so we can auto-update
        // out-of-date clients regardless of consent state).
        private static bool IsConsentBypassed(string url)
        {
            if (string.IsNullOrEmpty(url)) return false;
            return url.Contains("/api/v1/mod-version");
        }

        // Short-circuit any data-carrying request when consent hasn't been granted.
        // Returns true if the caller should skip the request entirely.
        private static bool ConsentBlocksRequest(string url)
        {
            if (Plugin.DataConsentGranted) return false;
            if (IsConsentBypassed(url)) return false;
            return true;
        }

        /// <summary>Hook from the consent modal — kick the initial data fetches the moment
        /// the user grants consent (otherwise they'd wait for the next poll cycle).
        /// On revoke, drop the local cache AND turn off ranked mode so the mod runs
        /// completely offline — no API traffic, no ranked queue, no ongoing tracking.</summary>
        public static void OnConsentChanged()
        {
            if (Plugin.DataConsentGranted)
            {
                string id = MatchTracker.LocalSteamId;
                if (!string.IsNullOrEmpty(id) && id != "unknown")
                {
                    FetchPlayerStats(id);
                    FetchMatchHistory(id);
                    FetchAchievements(id);
                }
                FetchLeaderboard();
                FetchRecentSeries();
                ChatClient.Connect();
            }
            else
            {
                CachedLeaderboard = null;
                CachedPlayerStats = null;
                CachedCardStats = null;
                CachedMatchHistory = null;
                CachedRecentSeries = null;
                CachedAchievements = null;
                CachedShopItems = null;
                CachedInventory = null;
                CachedActiveSeries = null;
                ChatClient.Disconnect();
                // Flip ranked off — if the user is in queue, server rejects further polls (410)
                // and the queue entry expires via the cleanup cron. No more match reports will
                // leave the client because every helper short-circuits on !DataConsentGranted.
                if (Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value)
                {
                    Plugin.RankedEnabled.Value = false;
                    Plugin.Log.LogInfo("[CONSENT] Ranked mode disabled due to revoke");
                }
            }
            NativeUI.MarkDirty();
        }

        // Detect server-side version-gate rejection. UnityWebRequest treats 4xx as
        // ProtocolError, so we look at responseCode rather than result.
        private static bool HandleVersionGate(UnityWebRequest req)
        {
            if (req.responseCode == 426)
            {
                if (!ForceUpdateRequired)
                    Plugin.Log.LogWarning("[VERSION] Server returned 426 — mod is below required version, gating UI");
                ForceUpdateRequired = true;
                return true;
            }
            return false;
        }

        // Heartbeat — track the most recent ATTEMPT and the most recent SUCCESS, separately.
        // Banner only shows when:  attempt within last 10s  AND  success was >5s before that attempt.
        // This prevents false-positives during quiet periods (no API calls = no info either way).
        public static float LastApiSuccessAt = -999f;
        public static float LastApiAttemptAt = -999f;
        public static bool LastResponseWasMaintenance = false;
        private static void NoteAttempt() { LastApiAttemptAt = Time.unscaledTime; }
        private static void NoteResult(bool success, long httpCode)
        {
            if (success) { LastApiSuccessAt = Time.unscaledTime; LastResponseWasMaintenance = false; }
            else if (httpCode == 503) { LastResponseWasMaintenance = true; }
        }
        /// <summary>True when we've recently TRIED to talk to the API and the most recent attempt
        /// hasn't succeeded — distinct from "haven't tried in a while".</summary>
        public static bool ApiLooksDown
        {
            get
            {
                if (LastApiAttemptAt < 0f) return false;
                float now = Time.unscaledTime;
                if (now - LastApiAttemptAt > 15f) return false;        // no recent attempts → don't claim down
                return (now - LastApiSuccessAt) > 10f;                  // attempts happening but no recent success
            }
        }

        private static IEnumerator GetRequest(string url, Action<bool, string> callback)
        {
            if (ConsentBlocksRequest(url)) { callback(false, "no-consent"); yield break; }
            NoteAttempt();
            using (var request = UnityWebRequest.Get(url))
            {
                StampVersionHeader(request);
                request.timeout = 20;
                yield return request.SendWebRequest();

                if (HandleVersionGate(request)) { callback(false, "outdated"); yield break; }
                bool success = request.result == UnityWebRequest.Result.Success;
                NoteResult(success, request.responseCode);
                callback(success, success ? request.downloadHandler.text : request.error);
            }
        }

        private static IEnumerator PostRequest(string url, string json, Action<bool, string> callback)
        {
            if (ConsentBlocksRequest(url)) { callback(false, "no-consent"); yield break; }
            NoteAttempt();
            using (var request = new UnityWebRequest(url, "POST"))
            {
                if (!string.IsNullOrEmpty(json))
                {
                    byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
                    request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                }
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                StampVersionHeader(request);
                request.timeout = 20;

                yield return request.SendWebRequest();

                if (HandleVersionGate(request)) { callback(false, "outdated"); yield break; }
                bool success = request.result == UnityWebRequest.Result.Success;
                NoteResult(success, request.responseCode);
                callback(success, success ? request.downloadHandler.text : request.error);
            }
        }

        /// <summary>POST with automatic retry on failure (DNS hiccups, timeouts).</summary>
        private static IEnumerator PostRequestWithRetry(string url, string json, Action<bool, string> callback, int maxRetries = 3, float retryDelay = 2f)
        {
            if (ConsentBlocksRequest(url)) { callback(false, "no-consent"); yield break; }
            for (int attempt = 1; attempt <= maxRetries; attempt++)
            {
                NoteAttempt();
                using (var request = new UnityWebRequest(url, "POST"))
                {
                    if (!string.IsNullOrEmpty(json))
                    {
                        byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
                        request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                    }
                    request.downloadHandler = new DownloadHandlerBuffer();
                    request.SetRequestHeader("Content-Type", "application/json");
                    StampVersionHeader(request);
                    request.timeout = 10;

                    yield return request.SendWebRequest();

                    if (HandleVersionGate(request)) { callback(false, "outdated"); yield break; }

                    bool success = request.result == UnityWebRequest.Result.Success;
                    NoteResult(success, request.responseCode);
                    if (success)
                    {
                        callback(true, request.downloadHandler.text);
                        yield break;
                    }

                    Plugin.Log.LogWarning($"[HTTP] POST attempt {attempt}/{maxRetries} failed: {request.error}");

                    if (attempt < maxRetries)
                        yield return new WaitForSeconds(retryDelay);
                    else
                        callback(false, request.error);
                }
            }
        }

        // ── Discord Linking ──────────────────────────────────────

        public static void GenerateLinkCode(string steamId)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/players/link-code?steam_id={Escape(steamId)}",
                "",
                (success, response) =>
                {
                    if (success)
                    {
                        string code = ExtractJsonString(response, "code");
                        if (!string.IsNullOrEmpty(code))
                        {
                            Plugin.Log.LogInfo($"[LINK] Generated link code: {code}");
                            CompetitiveUI.ShowNotification($"Link code: {code}", Color.cyan, 15f);
                            NativeUI.SetLinkCode(code);
                        }
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[LINK] Failed to generate code: {response}");
                        CompetitiveUI.ShowNotification("Failed to get link code", new Color(1f, 0.4f, 0.4f));
                    }
                }
            ));
        }

        // ── Achievements ──────────────────────────────────────────

        public static void FetchAchievements(string steamId)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/achievements/{steamId}",
                (success, response) =>
                {
                    if (success)
                    {
                        try
                        {
                            var dict = new Dictionary<string, AchievementData>();
                            // Manual parse — array of {achievement_key, unlocked, unlocked_at}
                            var parts = response.Split(new[] { "\"achievement_key\"" }, StringSplitOptions.None);
                            for (int i = 1; i < parts.Length; i++)
                            {
                                string key = ExtractJsonString(parts[i], "");
                                if (string.IsNullOrEmpty(key)) continue;
                                bool unlocked = parts[i].Contains("\"unlocked\":true") || parts[i].Contains("\"unlocked\": true");
                                string unlockedAt = ExtractJsonString(parts[i], "unlocked_at");
                                dict[key] = new AchievementData
                                {
                                    achievement_key = key,
                                    unlocked = unlocked,
                                    unlocked_at = unlockedAt
                                };
                            }
                            CachedAchievements = dict;
                            NativeUI.MarkDirty();
                            Plugin.Log.LogInfo($"[ACH] Loaded {dict.Count} achievements");
                        }
                        catch (Exception ex)
                        {
                            Plugin.Log.LogWarning($"[ACH] Parse error: {ex.Message}");
                        }
                    }
                }
            ));
        }

        public static void UnlockAchievement(string steamId, string achievementKey, string matchId = null)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            string achSig = ComputeHmacHex($"achievement:{steamId}:{achievementKey}");
            string json = $"{{\"steam_id\":\"{Escape(steamId)}\",\"achievement_key\":\"{Escape(achievementKey)}\",\"hmac_signature\":\"{Escape(achSig)}\"";
            if (!string.IsNullOrEmpty(matchId))
                json += $",\"match_id\":\"{Escape(matchId)}\"";
            json += "}";

            Plugin.Instance.StartCoroutine(PostRequestWithRetry(
                $"{baseUrl}/api/v1/achievements/unlock",
                json,
                (success, response) =>
                {
                    if (success)
                    {
                        string status = ExtractJsonString(response, "status");
                        string name = ExtractJsonString(response, "name");
                        if (status == "unlocked" && !string.IsNullOrEmpty(name))
                        {
                            CompetitiveUI.ShowNotification($"Achievement Unlocked: {name}!", new Color(1f, 0.85f, 0.3f), 6f);
                            Plugin.Log.LogInfo($"[ACH] Unlocked: {achievementKey} ({name})");
                        }
                        else
                        {
                            Plugin.Log.LogInfo($"[ACH] {achievementKey}: {status}");
                        }
                        // Refresh cached achievements
                        FetchAchievements(steamId);
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[ACH] Unlock failed for {achievementKey}: {response}");
                    }
                }
            ));
        }

        private static string Escape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            return s.Replace("\\", "\\\\")
                    .Replace("\"", "\\\"")
                    .Replace("\n", "\\n")
                    .Replace("\r", "\\r");
        }

        // ── Bug reports ──────────────────────────────────────────────────────
        // POST /api/v1/bug-reports. Server gzips + persists the log blob to
        // disk; we just pass plain text up. Caps log payload at ~3.5MB to
        // stay under the server's 4MB validator and FastAPI's body limit.
        public const int BUG_REPORT_LOG_CAP_CHARS = 3_500_000;
        public static void SubmitBugReport(string steamId, string displayName, string description,
                                           string reproSteps, string severity, string category,
                                           string logText, Action<bool, string> done)
        {
            if (string.IsNullOrEmpty(steamId))
            {
                done?.Invoke(false, "steam_id missing");
                return;
            }
            if (logText != null && logText.Length > BUG_REPORT_LOG_CAP_CHARS)
                logText = logText.Substring(logText.Length - BUG_REPORT_LOG_CAP_CHARS); // tail-most window
            var sb = new System.Text.StringBuilder();
            sb.Append("{");
            sb.Append($"\"steam_id\":\"{Escape(steamId)}\"");
            sb.Append($",\"display_name\":\"{Escape(displayName ?? "")}\"");
            sb.Append($",\"mod_version\":\"{Escape(Plugin.ModVersion)}\"");
            sb.Append($",\"game_version\":\"{Escape(UnityEngine.Application.version ?? "")}\"");
            sb.Append($",\"severity\":\"{Escape(severity ?? "medium")}\"");
            sb.Append($",\"category\":\"{Escape(category ?? "other")}\"");
            sb.Append($",\"description\":\"{Escape(description ?? "")}\"");
            if (!string.IsNullOrEmpty(reproSteps))
                sb.Append($",\"repro_steps\":\"{Escape(reproSteps)}\"");
            if (!string.IsNullOrEmpty(logText))
                sb.Append($",\"log_text\":\"{Escape(logText)}\"");
            sb.Append("}");
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/bug-reports", sb.ToString(),
                (ok, response) =>
                {
                    if (ok) Plugin.Log.LogInfo($"[BUG-REPORT] submitted ok: {response}");
                    else Plugin.Log.LogWarning($"[BUG-REPORT] submit failed: {response}");
                    done?.Invoke(ok, response);
                }
            ));
        }

        // Reads the tail of a log file (BepInEx LogOutput.log or Unity output_log.txt)
        // with sane caps so we don't blow out memory on a multi-MB log.
        public static string ReadLogTail(string path, int maxChars = BUG_REPORT_LOG_CAP_CHARS)
        {
            try
            {
                if (string.IsNullOrEmpty(path) || !System.IO.File.Exists(path)) return "";
                // FileShare.ReadWrite — BepInEx + Unity keep these handles open.
                using (var fs = new System.IO.FileStream(path, System.IO.FileMode.Open,
                                                        System.IO.FileAccess.Read,
                                                        System.IO.FileShare.ReadWrite))
                using (var sr = new System.IO.StreamReader(fs))
                {
                    string all = sr.ReadToEnd();
                    if (all.Length <= maxChars) return all;
                    return all.Substring(all.Length - maxChars);
                }
            }
            catch (Exception ex)
            {
                return $"[log read error: {ex.Message}]";
            }
        }


        // ── Tournaments ──────────────────────────────────────────────────────
        //
        // Raw-JSON caching + field-level extraction for the Tournaments tab. We
        // avoid JsonUtility-with-nested-arrays per the codebase convention (see
        // CLAUDE.md learnings 25). Top-level flat fields are parsed into
        // TournamentSnapshot; signups/matches/time_slots stay as raw JSON and
        // are sliced into per-row strings that the UI re-parses lazily.

        public static string CachedTournamentJson;
        public static TournamentSnapshot CachedTournament;
        private static float _tournamentRefreshAt;

        [Serializable]
        public class TournamentSnapshot
        {
            public string tournament_id;
            public string status;            // voting | locked | running | completed | null
            public string kind;              // sync | async
            public string default_start_ts;
            public string scheduled_start_ts;
            public string lock_at;
            public string started_at;
            public string ended_at;
            public int min_players;
            public int max_players;
            public string my_signup_id;
            public bool my_ready;
            public float my_penalty_pct;
            public bool my_discord_linked;
            public int force_vote_count;
            public string photon_region;         // tournament's canonical Photon region (null until lock)
            public string[] my_votes;            // ISO datetimes
            public string[] time_slot_options;   // ISO datetimes
            public TimeVoteTally[] time_slot_tallies;
            public TournamentSignupRow[] signups;
            public TournamentMatchRow[] matches;
        }

        [Serializable]
        public class TimeVoteTally
        {
            public string slot_ts;
            public int votes;
        }

        [Serializable]
        public class TournamentSignupRow
        {
            public string signup_id;
            public string steam_id;
            public string display_name;
            public bool is_speculative;
            public int seed;        // 0 until lock
            public float penalty_at_signup;
            public bool ready;
            public bool forfeited;
            public int placed_rank; // 0 if not placed
            public string progress_label;  // "WB R2" / "LB R3" / "eliminated WB R2" / "CHAMPION"
        }

        [Serializable]
        public class TournamentMatchRow
        {
            public string match_id;
            public int round;
            public string bracket_side;   // W | TP | L | GF | GF_RESET
            public int slot_idx;
            public string p1_signup_id;
            public string p2_signup_id;
            public string p1_display_name;
            public string p2_display_name;
            public bool is_bye;
            public string status;         // pending | ready | forfeit | completed | bye_auto
            public string series_id;
            public string winner_signup_id;
            public int p1_series_wins;
            public int p2_series_wins;
            public string deadline_at;    // async 7-day match deadline (null for sync)
            // UUIDs of the matches whose winners (or losers, per
            // prereq_roles) feed into this match's p1/p2 slots. Empty for
            // round-1 WB matches. Used by the visual bracket renderer to
            // draw connector lines between cells.
            public string[] prereq_match_ids;
            // Server-issued Photon room name. Set when the match
            // transitions to 'ready'. Replaces client-side derivation
            // ("sct-" + match_id[:12]) so both clients always converge
            // on the same room. Falls back to null for older matches
            // that pre-date the column.
            public string photon_room_name;
        }

        // Tracks which kind (sync | async) the client is currently viewing. Set
        // by the UI's sub-tab; defaults to sync so existing callers keep the
        // Phase 1 behavior.
        public static string TournamentKind = "sync";

        public static void FetchTournamentCurrent(string steamId, bool force = false)
        {
            if (!force && Time.unscaledTime < _tournamentRefreshAt) return;
            _tournamentRefreshAt = Time.unscaledTime + 5f;   // throttle
            string kindParam = string.IsNullOrEmpty(TournamentKind) ? "sync" : TournamentKind;
            string q = string.IsNullOrEmpty(steamId) || steamId == "unknown"
                ? $"?kind={kindParam}"
                : $"?steam_id={Escape(steamId)}&kind={kindParam}";
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/tournaments/current{q}",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try
                    {
                        CachedTournamentJson = response;
                        CachedTournament = ParseTournament(response);
                        NativeUI.MarkDirty();
                    }
                    catch (Exception e)
                    {
                        Plugin.Log.LogWarning($"[TOURNAMENT] parse failed: {e.Message}");
                    }
                }
            ));
        }

        private static TournamentSnapshot ParseTournament(string json)
        {
            var t = new TournamentSnapshot();
            t.tournament_id = ExtractString(json, "tournament_id");
            t.status = ExtractString(json, "status");
            t.kind = ExtractString(json, "kind");
            t.default_start_ts = ExtractString(json, "default_start_ts");
            t.scheduled_start_ts = ExtractString(json, "scheduled_start_ts");
            t.lock_at = ExtractString(json, "lock_at");
            t.started_at = ExtractString(json, "started_at");
            t.ended_at = ExtractString(json, "ended_at");
            t.min_players = ExtractInt(json, "min_players", 8);
            t.max_players = ExtractInt(json, "max_players", 16);
            t.my_signup_id = ExtractString(json, "my_signup_id");
            t.my_ready = ExtractBool(json, "my_ready");
            t.my_penalty_pct = ExtractFloat(json, "my_penalty_pct");
            t.my_discord_linked = ExtractBool(json, "my_discord_linked");
            t.force_vote_count = ExtractInt(json, "force_vote_count", 0);
            t.photon_region = ExtractString(json, "photon_region");
            t.my_votes = ExtractStringArray(json, "my_votes");
            t.time_slot_options = ExtractStringArray(json, "time_slot_options");
            t.time_slot_tallies = ExtractObjectArray(json, "time_slot_tallies",
                raw => new TimeVoteTally
                {
                    slot_ts = ExtractString(raw, "slot_ts"),
                    votes = ExtractInt(raw, "votes", 0),
                });
            t.signups = ExtractObjectArray(json, "signups", raw => new TournamentSignupRow
            {
                signup_id = ExtractString(raw, "signup_id"),
                steam_id = ExtractString(raw, "steam_id"),
                display_name = ExtractString(raw, "display_name"),
                is_speculative = ExtractBool(raw, "is_speculative"),
                seed = ExtractInt(raw, "seed", 0),
                penalty_at_signup = ExtractFloat(raw, "penalty_at_signup"),
                ready = ExtractBool(raw, "ready"),
                forfeited = ExtractBool(raw, "forfeited"),
                placed_rank = ExtractInt(raw, "placed_rank", 0),
                progress_label = ExtractString(raw, "progress_label"),
            });
            t.matches = ExtractObjectArray(json, "matches", raw => new TournamentMatchRow
            {
                match_id = ExtractString(raw, "match_id"),
                round = ExtractInt(raw, "round", 0),
                bracket_side = ExtractString(raw, "bracket_side"),
                slot_idx = ExtractInt(raw, "slot_idx", 0),
                p1_signup_id = ExtractString(raw, "p1_signup_id"),
                p2_signup_id = ExtractString(raw, "p2_signup_id"),
                p1_display_name = ExtractString(raw, "p1_display_name"),
                p2_display_name = ExtractString(raw, "p2_display_name"),
                is_bye = ExtractBool(raw, "is_bye"),
                status = ExtractString(raw, "status"),
                series_id = ExtractString(raw, "series_id"),
                winner_signup_id = ExtractString(raw, "winner_signup_id"),
                p1_series_wins = ExtractInt(raw, "p1_series_wins", 0),
                p2_series_wins = ExtractInt(raw, "p2_series_wins", 0),
                deadline_at = ExtractString(raw, "deadline_at"),
                prereq_match_ids = ExtractStringArray(raw, "prereq_match_ids"),
                photon_room_name = ExtractString(raw, "photon_room_name"),
            });
            return t;
        }

        // Small, forgiving JSON extractors. NOT a full parser — they handle the
        // shapes we control (API response) and ignore the rest.
        private static string ExtractString(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return null;
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return null;
            int c = json.IndexOf(':', i);
            if (c < 0) return null;
            int p = c + 1;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length) return null;
            if (json[p] == 'n' && json.Length >= p + 4 && json.Substring(p, 4) == "null") return null;
            if (json[p] != '"') return null;
            int start = p + 1;
            var sb = new System.Text.StringBuilder();
            for (int k = start; k < json.Length; k++)
            {
                char ch = json[k];
                if (ch == '\\' && k + 1 < json.Length) { sb.Append(json[k + 1]); k++; continue; }
                if (ch == '"') break;
                sb.Append(ch);
            }
            return sb.ToString();
        }

        private static int ExtractInt(string json, string key, int def)
        {
            if (string.IsNullOrEmpty(json)) return def;
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return def;
            int c = json.IndexOf(':', i);
            if (c < 0) return def;
            int p = c + 1;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length) return def;
            int e = p;
            while (e < json.Length && (char.IsDigit(json[e]) || json[e] == '-')) e++;
            if (e == p) return def;
            int v; return int.TryParse(json.Substring(p, e - p), out v) ? v : def;
        }

        private static float ExtractFloat(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return 0f;
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return 0f;
            int c = json.IndexOf(':', i);
            if (c < 0) return 0f;
            int p = c + 1;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            if (p >= json.Length) return 0f;
            int e = p;
            while (e < json.Length && (char.IsDigit(json[e]) || json[e] == '-' || json[e] == '.' || json[e] == 'e' || json[e] == 'E' || json[e] == '+')) e++;
            if (e == p) return 0f;
            float v; return float.TryParse(json.Substring(p, e - p), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v) ? v : 0f;
        }

        private static bool ExtractBool(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return false;
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return false;
            int c = json.IndexOf(':', i);
            if (c < 0) return false;
            int p = c + 1;
            while (p < json.Length && (json[p] == ' ' || json[p] == '\t')) p++;
            return p + 4 <= json.Length && json.Substring(p, 4) == "true";
        }

        private static string[] ExtractStringArray(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return Array.Empty<string>();
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return Array.Empty<string>();
            int b = json.IndexOf('[', i);
            if (b < 0) return Array.Empty<string>();
            int e = json.IndexOf(']', b);
            if (e < 0) return Array.Empty<string>();
            string inner = json.Substring(b + 1, e - b - 1);
            var list = new List<string>();
            int p = 0;
            while (p < inner.Length)
            {
                int q = inner.IndexOf('"', p);
                if (q < 0) break;
                int q2 = inner.IndexOf('"', q + 1);
                if (q2 < 0) break;
                list.Add(inner.Substring(q + 1, q2 - q - 1));
                p = q2 + 1;
            }
            return list.ToArray();
        }

        private static T[] ExtractObjectArray<T>(string json, string key, Func<string, T> parse)
        {
            if (string.IsNullOrEmpty(json)) return Array.Empty<T>();
            int i = json.IndexOf("\"" + key + "\"");
            if (i < 0) return Array.Empty<T>();
            int b = json.IndexOf('[', i);
            if (b < 0) return Array.Empty<T>();
            // Scan forward, tracking brace depth, collect { ... } segments at depth 1.
            var list = new List<T>();
            int depth = 0;
            int objStart = -1;
            for (int k = b; k < json.Length; k++)
            {
                char ch = json[k];
                if (ch == '[') { depth++; continue; }
                if (ch == ']') { depth--; if (depth == 0) break; continue; }
                if (ch == '{')
                {
                    if (objStart < 0) objStart = k;
                    depth++;
                    continue;
                }
                if (ch == '}')
                {
                    depth--;
                    if (depth == 1 && objStart >= 0)
                    {
                        list.Add(parse(json.Substring(objStart, k - objStart + 1)));
                        objStart = -1;
                    }
                }
            }
            return list.ToArray();
        }

        public static void TournamentSignup(string tournamentId, string steamId, string displayName)
        {
            // Include the client's current Photon region so the server can pick the
            // tournament's canonical region at lock time (mode of all signups'
            // regions). Auto-connect then pins every match to that region.
            string region = "";
            try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { region = ""; }
            string body = $"{{\"steam_id\":\"{Escape(steamId)}\",\"display_name\":\"{Escape(displayName ?? steamId)}\",\"region\":\"{Escape(region)}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/tournaments/{tournamentId}/signup", body,
                (s, r) =>
                {
                    if (s) { FetchTournamentCurrent(steamId, force: true); CompetitiveUI.ShowNotification("Signed up for tournament", new Color(0.4f, 1f, 0.5f)); }
                    else { CompetitiveUI.ShowNotification(ExtractErrorDetail(r) ?? "Signup failed", new Color(1f, 0.4f, 0.4f)); }
                }));
        }

        public static void TournamentUnsignup(string tournamentId, string steamId)
        {
            string body = $"{{\"steam_id\":\"{Escape(steamId)}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/tournaments/{tournamentId}/unsignup", body,
                (s, r) =>
                {
                    if (s) { FetchTournamentCurrent(steamId, force: true); CompetitiveUI.ShowNotification("Left tournament signup", new Color(0.9f, 0.9f, 0.4f)); }
                    else { CompetitiveUI.ShowNotification(ExtractErrorDetail(r) ?? "Failed", new Color(1f, 0.4f, 0.4f)); }
                }));
        }

        public static void TournamentTimeVote(string tournamentId, string steamId, string[] slotIsos)
        {
            var sb = new System.Text.StringBuilder();
            sb.Append("{\"steam_id\":\"").Append(Escape(steamId)).Append("\",\"slot_ts\":[");
            for (int i = 0; i < slotIsos.Length; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append('"').Append(Escape(slotIsos[i])).Append('"');
            }
            sb.Append("]}");
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/tournaments/{tournamentId}/time-vote", sb.ToString(),
                (s, r) => { if (s) FetchTournamentCurrent(steamId, force: true); }));
        }

        public static void TournamentForceStartVote(string tournamentId, string steamId)
        {
            string body = $"{{\"steam_id\":\"{Escape(steamId)}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/tournaments/{tournamentId}/force-start-vote", body,
                (s, r) => { if (s) FetchTournamentCurrent(steamId, force: true); }));
        }

        public static void TournamentReady(string tournamentId, string steamId)
        {
            string body = $"{{\"steam_id\":\"{Escape(steamId)}\"}}";
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/tournaments/{tournamentId}/ready", body,
                (s, r) => { if (s) FetchTournamentCurrent(steamId, force: true); }));
        }

        private static string ExtractErrorDetail(string response)
        {
            if (string.IsNullOrEmpty(response)) return null;
            try
            {
                // FastAPI returns {"detail":"..."} on HTTPException
                return ExtractString(response, "detail");
            }
            catch { return null; }
        }


        // ── Tournament history (per-player trophy counts + recent tournaments) ─
        //
        // Populated lazily: FetchPlayerTournaments hits /api/v1/tournaments/players/{steam}/tournaments
        // and stores the parsed PlayerTournamentHistory keyed by steam_id. Used by the
        // Leaderboard click-a-player detail (shows trophy summary for the viewed player)
        // and the Tournaments tab (shows the local player's own history line).

        [Serializable]
        public class PlayerTournamentHistory
        {
            public string steam_id;
            public int winner_count;
            public int runner_up_count;
            public int third_place_count;
            public int participant_count;
            public PlayerTournamentEntry[] recent;
        }

        [Serializable]
        public class PlayerTournamentEntry
        {
            public string tournament_id;
            public string ended_at;
            public int placed_rank;
            public string kind;
            public int signup_count;
            public string winner_display_name;
        }

        public static readonly Dictionary<string, PlayerTournamentHistory> CachedPlayerTournaments
            = new Dictionary<string, PlayerTournamentHistory>();

        public static void FetchPlayerTournaments(string steamId, Action onDone = null)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/tournaments/players/{Escape(steamId)}/tournaments?limit=8",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try
                    {
                        var h = new PlayerTournamentHistory
                        {
                            steam_id = ExtractString(response, "steam_id") ?? steamId,
                            winner_count = ExtractInt(response, "winner_count", 0),
                            runner_up_count = ExtractInt(response, "runner_up_count", 0),
                            third_place_count = ExtractInt(response, "third_place_count", 0),
                            participant_count = ExtractInt(response, "participant_count", 0),
                            recent = ExtractObjectArray(response, "recent", raw => new PlayerTournamentEntry
                            {
                                tournament_id = ExtractString(raw, "tournament_id"),
                                ended_at = ExtractString(raw, "ended_at"),
                                placed_rank = ExtractInt(raw, "placed_rank", 0),
                                kind = ExtractString(raw, "kind"),
                                signup_count = ExtractInt(raw, "signup_count", 0),
                                winner_display_name = ExtractString(raw, "winner_display_name"),
                            }),
                        };
                        CachedPlayerTournaments[steamId] = h;
                        NativeUI.MarkDirty();
                        onDone?.Invoke();
                    }
                    catch (Exception e) { Plugin.Log.LogWarning($"[TOURNAMENT-HIST] parse: {e.Message}"); }
                }
            ));
        }

        // "Am I in a tournament match right now?" — polled every 20s regardless
        // of tab so the TOURNAMENT GAME indicator at the top of the competitive
        // page can light up when in a room with a tournament opponent. Spans
        // both sync and async so a player in both doesn't miss either.
        [Serializable]
        public class ActiveTournamentMatch
        {
            public string tournament_id;
            public string kind;
            public string match_id;
            public string status;
            public string bracket_side;
            public int round;
            public string opponent_steam_id;
            public string opponent_display_name;
            // Server-issued Photon room + region. Used by the
            // tournament dispatch loop to fire SetPendingRoom from a
            // plugin-level coroutine, independent of which UI tab is
            // open — without it, auto-connect only ran when the user
            // happened to be on the Tournament tab.
            public string photon_room_name;
            public string photon_region;
            public bool my_ready;
            public bool opp_ready;
        }
        public static List<ActiveTournamentMatch> CachedMyActiveTournamentMatches = new List<ActiveTournamentMatch>();
        private static float _myActiveMatchesRefreshAt;
        public static void FetchMyActiveTournamentMatches(string steamId)
        {
            if (string.IsNullOrEmpty(steamId) || steamId == "unknown") return;
            if (Time.unscaledTime < _myActiveMatchesRefreshAt) return;
            _myActiveMatchesRefreshAt = Time.unscaledTime + 20f;
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/tournaments/my-active-matches?steam_id={Escape(steamId)}",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try
                    {
                        var list = new List<ActiveTournamentMatch>();
                        foreach (var raw in ExtractObjectArray(response, "matches", r => r))
                        {
                            list.Add(new ActiveTournamentMatch
                            {
                                tournament_id = ExtractString(raw, "tournament_id"),
                                kind = ExtractString(raw, "kind"),
                                match_id = ExtractString(raw, "match_id"),
                                status = ExtractString(raw, "status"),
                                bracket_side = ExtractString(raw, "bracket_side"),
                                round = ExtractInt(raw, "round", 0),
                                opponent_steam_id = ExtractString(raw, "opponent_steam_id"),
                                opponent_display_name = ExtractString(raw, "opponent_display_name"),
                                photon_room_name = ExtractString(raw, "photon_room_name"),
                                photon_region = ExtractString(raw, "photon_region"),
                                my_ready = ExtractBool(raw, "my_ready"),
                                opp_ready = ExtractBool(raw, "opp_ready"),
                            });
                        }
                        CachedMyActiveTournamentMatches = list;
                        NativeUI.MarkDirty();
                    }
                    catch (Exception e) { Plugin.Log.LogWarning($"[TOURNAMENT-ACTIVE] parse: {e.Message}"); }
                }
            ));
        }

        // Recent completed tournaments (site-wide history), used by the Tournaments
        // tab's "Recent Tournaments" section. Returns a JSON array which we
        // slice row-by-row.
        public static PlayerTournamentEntry[] CachedSiteTournamentHistory;
        public static string[] CachedSiteTournamentHistoryNames;  // aligned with ^, each entry's winner_display_name
        public static void FetchSiteTournamentHistory()
        {
            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/tournaments/history?limit=12",
                (success, response) =>
                {
                    if (!success || string.IsNullOrEmpty(response)) return;
                    try
                    {
                        // /tournaments/history returns a bare array [ {...}, ... ].
                        // Reuse ExtractObjectArray by wrapping it under a synthetic key.
                        string wrapped = "{\"_hist\":" + response + "}";
                        CachedSiteTournamentHistory = ExtractObjectArray(wrapped, "_hist", raw => new PlayerTournamentEntry
                        {
                            tournament_id = ExtractString(raw, "tournament_id"),
                            ended_at = ExtractString(raw, "ended_at"),
                            placed_rank = 0,
                            kind = ExtractString(raw, "kind"),
                            signup_count = ExtractInt(raw, "signup_count", 0),
                            winner_display_name = ExtractString(raw, "winner_display_name"),
                        });
                        NativeUI.MarkDirty();
                    }
                    catch (Exception e) { Plugin.Log.LogWarning($"[TOURNAMENT-SITEHIST] parse: {e.Message}"); }
                }
            ));
        }
    }
}
