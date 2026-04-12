using System;
using System.Collections;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
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
            public string discord_id;

            // Parsed manually (JsonUtility can't handle nested arrays)
            public List<string> top_card_names;
            public List<int> top_card_picks;
            public List<float> top_card_win_rates;
            public List<string> recent_form; // "W","L","W"... last 20
        }

        [Serializable]
        public class CardStatData
        {
            public string card_name;
            public string card_rarity;
            public int times_picked;
            public int wins_with_card;
            public float win_rate;
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
        }

        [Serializable]
        public class MatchHistoryEntry
        {
            public string match_id;
            public string opponent_steam_id;
            public string opponent_name;
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
                if (!string.IsNullOrEmpty(ver))
                {
                    LatestModVersion = ver;
                    if (ver != Plugin.ModVersion)
                        Plugin.Log.LogWarning($"[VERSION] Update available: v{Plugin.ModVersion} → v{ver}");
                    else
                        Plugin.Log.LogInfo($"[VERSION] Mod is up to date (v{ver})");
                }
            }
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
            string photonRoomId, string region,
            int durationSeconds, DateTime startedAt,
            string reporterSteamId, bool isRanked)
        {
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"player1\":{{\"steam_id\":\"{Escape(p1SteamId)}\",\"display_name\":\"{Escape(p1Name)}\",\"cards\":[");
            AppendCards(sb, p1Cards);
            sb.Append("]},");
            sb.Append($"\"player2\":{{\"steam_id\":\"{Escape(p2SteamId)}\",\"display_name\":\"{Escape(p2Name)}\",\"cards\":[");
            AppendCards(sb, p2Cards);
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
            string sig = ComputeHmac(p1SteamId, p2SteamId, p1RoundsWon, p2RoundsWon, isRanked, reporterSteamId, photonRoomId);
            sb.Append($"\"hmac_signature\":\"{sig}\"");
            sb.Append("}");

            string json = sb.ToString();
            string matchType = isRanked ? "RANKED" : "CASUAL";
            Plugin.Log.LogInfo($"Reporting {matchType} match to API...");

            Plugin.Instance.StartCoroutine(PostRequest(
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

                            if (seriesStatus == "active")
                            {
                                CompetitiveUI.QueueNotification($"Series: {seriesScore}", new Color(1f, 0.85f, 0.3f), 3f);
                            }
                            else if (seriesStatus == "completed")
                            {
                                CompetitiveUI.QueueNotification($"SERIES COMPLETE {seriesScore}!", new Color(0.3f, 1f, 0.3f), 4f);
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

        // ── Data fetching ─────────────────────────────────────

        public static void FetchLeaderboard(int limit = 20, int minMatches = 1)
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
                            Plugin.Log.LogInfo($"Player stats loaded for {CachedPlayerStats.display_name}");
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

            Plugin.Instance.StartCoroutine(GetRequest(
                $"{baseUrl}/api/v1/players/{steamId}",
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

        public static void FetchMatchHistory(string steamId, int limit = 100)
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
                int end = json.IndexOf("\"", start);
                if (end < 0) return "";
                return json.Substring(start, end - start);
            }
            catch { return ""; }
        }

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

        public static void ToggleRanked(string steamId, bool enabled)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/mod/toggle-ranked/{steamId}?enabled={enabled.ToString().ToLower()}",
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

            Plugin.Instance.StartCoroutine(PostRequest(
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
                            if (!string.IsNullOrEmpty(room))
                            {
                                IsQueuePolling = false;
                                CurrentQueueState = QueueState.Idle;
                                LastPollData = null;
                                Plugin.SetPendingRoom(room, region);
                                Plugin.Log.LogInfo($"[QUEUE] Both ready! Joining room: {room} (region: {region ?? "auto"})");
                                CompetitiveUI.ShowNotification("Both ready! Joining match...", Color.green, 5f);
                                NativeUI.MarkDirty();
                            }
                        }
                        else
                        {
                            Plugin.Log.LogInfo("[QUEUE] Waiting for opponent to ready up");
                        }
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[QUEUE] Ready failed: {response}");
                    }
                }
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

        public static void BlockPlayer(string mySteamId, string targetSteamId, Action<bool> callback = null)
        {
            Plugin.Instance.StartCoroutine(PostRequest(
                $"{baseUrl}/api/v1/players/block?steam_id={Escape(mySteamId)}&target_steam_id={Escape(targetSteamId)}",
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
                $"{baseUrl}/api/v1/players/unblock?steam_id={Escape(mySteamId)}&target_steam_id={Escape(targetSteamId)}",
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

        private static IEnumerator GetRequest(string url, Action<bool, string> callback)
        {
            using (var request = UnityWebRequest.Get(url))
            {
                request.timeout = 20;
                yield return request.SendWebRequest();

                bool success = request.result == UnityWebRequest.Result.Success;
                callback(success, success ? request.downloadHandler.text : request.error);
            }
        }

        private static IEnumerator PostRequest(string url, string json, Action<bool, string> callback)
        {
            using (var request = new UnityWebRequest(url, "POST"))
            {
                if (!string.IsNullOrEmpty(json))
                {
                    byte[] bodyRaw = Encoding.UTF8.GetBytes(json);
                    request.uploadHandler = new UploadHandlerRaw(bodyRaw);
                }
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Content-Type", "application/json");
                request.timeout = 20;

                yield return request.SendWebRequest();

                bool success = request.result == UnityWebRequest.Result.Success;
                callback(success, success ? request.downloadHandler.text : request.error);
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
            string json = $"{{\"steam_id\":\"{Escape(steamId)}\",\"achievement_key\":\"{Escape(achievementKey)}\"";
            if (!string.IsNullOrEmpty(matchId))
                json += $",\"match_id\":\"{Escape(matchId)}\"";
            json += "}";

            Plugin.Instance.StartCoroutine(PostRequest(
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
    }
}
