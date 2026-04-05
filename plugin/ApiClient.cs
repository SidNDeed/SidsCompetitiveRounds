using System;
using System.Collections;
using System.Collections.Generic;
using System.Text;
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

            // Parsed manually (JsonUtility can't handle nested arrays)
            public List<string> top_card_names;
            public List<int> top_card_picks;
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
            public bool won;
            public bool is_ranked;
            public string ended_at;
            public string cards_display; // Comma-separated card names for display
            public string opp_cards_display; // Opponent's cards
            public string series_id; // For grouping matches into BO3 series
            public string series_score; // e.g. "2-0", "1-1"
            public float series_rating_change; // Elo change for completed series
        }

        [Serializable]
        private class MatchHistoryWrapper
        {
            public MatchHistoryEntry[] items;
        }

        // Cached data
        public static List<MatchHistoryEntry> CachedMatchHistory { get; private set; }

        // ── Initialization ────────────────────────────────────

        public static void Initialize(string url)
        {
            baseUrl = url.TrimEnd('/');
            Plugin.Log.LogInfo($"API client initialized: {baseUrl}");
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
            sb.Append($"\"reported_by_steam_id\":\"{Escape(reporterSteamId)}\"");
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
            try
            {
                int tcStart = response.IndexOf("\"top_cards\"");
                if (tcStart < 0) return;

                int arrStart = response.IndexOf("[", tcStart);
                int arrEnd = FindMatchingBracket(response, arrStart);
                if (arrStart < 0 || arrEnd < 0) return;

                string arr = response.Substring(arrStart, arrEnd - arrStart + 1);
                if (arr == "[]") return;

                var cardParts = arr.Split(new[] { "\"card_name\"" }, StringSplitOptions.None);
                for (int i = 1; i < cardParts.Length && i <= 5; i++)
                {
                    string name = ExtractJsonString(cardParts[i], "");
                    int picks = ExtractJsonInt(cardParts[i], "times_picked");
                    if (!string.IsNullOrEmpty(name))
                    {
                        data.top_card_names.Add(name);
                        data.top_card_picks.Add(picks);
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
