using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    public static class CompetitiveUI
    {
        // ── State ─────────────────────────────────────────────

        private static bool showOverlay = false;
        private static int currentTab = 0;
        private static readonly string[] tabNames = { "My Stats", "Leaderboard", "Card Stats" };

        private static Vector2 leaderboardScroll;
        private static Vector2 cardStatsScroll;

        // Leaderboard player detail
        private static string selectedPlayerSteamId = "";
        private static ApiClient.PlayerStatsData selectedPlayerStats = null;
        private static bool selectedPlayerLoading = false;

        // History pagination
        private static int rankedPage = 0;
        private static int casualPage = 0;
        private static int matchesPerPage = 5;

        // Card stats sorting
        private static string cardSortBy = "times_picked";
        private static bool cardSortDesc = true;
        private static int cardStatsFilter = 0; // 0=All, 1=Ranked, 2=Casual

        // Notification
        private static string notificationText = "";
        private static Color notificationColor = Color.white;
        private static float notificationTimer = 0f;

        private struct QueuedNotification
        {
            public string Text;
            public Color Color;
            public float Duration;
        }
        private static List<QueuedNotification> notificationQueue = new List<QueuedNotification>();

        // FPS counter
        private static float fpsTimer = 0f;
        private static int fpsFrameCount = 0;
        private static float fpsDisplay = 0f;
        private static GUIStyle fpsStyle;

        // Styles (re-initialized when needed)
        private static bool stylesInitialized = false;
        private static GUIStyle headerStyle;
        private static GUIStyle subHeaderStyle;
        private static GUIStyle statLabelStyle;
        private static GUIStyle statValueStyle;
        private static GUIStyle tabStyle;
        private static GUIStyle activeTabStyle;
        private static GUIStyle boxStyle;
        private static GUIStyle entryStyle;
        private static GUIStyle rankStyle;
        private static GUIStyle smallCenterStyle;
        private static GUIStyle notificationStyle;

        // Window
        private static Rect windowRect = new Rect(50, 50, 520, 560);
        private static bool hasLoadedData = false;
        private static Texture2D backdropTex = null;
        private static Vector2 mainScrollPos;

        // ── Public interface ──────────────────────────────────

        public static void ToggleOverlay()
        {
            showOverlay = !showOverlay;

            if (showOverlay && !hasLoadedData)
            {
                RefreshData();
                hasLoadedData = true;
            }
        }

        public static void ShowNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notificationText = text;
            notificationColor = color;
            notificationTimer = duration;
        }

        public static void QueueNotification(string text, Color color, float duration = 3f)
        {
            if (!Plugin.ShowNotifications.Value) return;
            notificationQueue.Add(new QueuedNotification { Text = text, Color = color, Duration = duration });
        }

        // Level tracking for level-up detection
        public static int LastKnownLevel = -1;

        /// <summary>
        /// Call this when the persistent object respawns to reset GUI styles.
        /// </summary>
        public static void ResetStyles()
        {
            stylesInitialized = false;
        }

        // ── Drawing ───────────────────────────────────────────

        public static void DrawUI()
        {
            DrawFPS();
            DrawNotification();
            DrawMatchStatus();

            if (!showOverlay) return;

            // Re-init styles if they were lost (e.g. after respawn)
            if (!stylesInitialized || boxStyle == null || boxStyle.normal.background == null)
            {
                stylesInitialized = false;
                InitStyles();
            }

            // ── Fullscreen backdrop: darkens screen and blocks click-through ──
            // This is purely visual — we do NOT touch EventSystem because
            // disabling/re-enabling it corrupts ROUNDS' internal UI state.
            if (backdropTex == null)
                backdropTex = MakeTex(1, 1, new Color(0f, 0f, 0f, 0.4f));
            GUI.DrawTexture(new Rect(0, 0, Screen.width, Screen.height), backdropTex);

            // Clamp window height to 85% of screen
            float maxH = Screen.height * 0.85f;
            if (windowRect.height > maxH)
                windowRect.height = maxH;

            windowRect = GUILayout.Window(
                9999,
                windowRect,
                DrawWindow,
                "",
                boxStyle,
                GUILayout.MaxHeight(maxH)
            );

            // Consume any mouse events that land outside the window
            if (Event.current.isMouse && !windowRect.Contains(Event.current.mousePosition))
            {
                Event.current.Use();
            }
        }

        private static void DrawWindow(int id)
        {
            GUILayout.BeginHorizontal();
            GUILayout.Label("COMPETITIVE ROUNDS", headerStyle);
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("X", GUILayout.Width(24), GUILayout.Height(24)))
            {
                showOverlay = false;
            }
            GUILayout.EndHorizontal();

            // Player name
            string playerName = ApiClient.CachedPlayerStats?.display_name ?? MatchTracker.LocalDisplayName;
            if (!string.IsNullOrEmpty(playerName) && playerName != "unknown" && playerName != "Unknown")
            {
                GUILayout.Label(playerName, subHeaderStyle);
            }

            GUILayout.Space(4);

            DrawRankedToggle();

            GUILayout.Space(8);

            // Tab bar
            GUILayout.BeginHorizontal();
            for (int i = 0; i < tabNames.Length; i++)
            {
                var style = (i == currentTab) ? activeTabStyle : tabStyle;
                if (GUILayout.Button(tabNames[i], style, GUILayout.Height(28)))
                {
                    currentTab = i;
                    if (i == 1 && ApiClient.CachedLeaderboard == null) ApiClient.FetchLeaderboard();
                    if (i == 2 && ApiClient.CachedCardStats == null) ApiClient.FetchCardStats(50, MatchTracker.LocalSteamId);
                }
            }
            GUILayout.EndHorizontal();

            GUILayout.Space(8);

            if (ApiClient.IsLoading)
            {
                GUILayout.Label("Loading...", subHeaderStyle);
            }

            // Scrollable content area
            mainScrollPos = GUILayout.BeginScrollView(mainScrollPos);

            switch (currentTab)
            {
                case 0: DrawMyStats(); break;
                case 1: DrawLeaderboard(); break;
                case 2: DrawCardStats(); break;
            }

            GUILayout.EndScrollView();

            GUILayout.Space(8);

            GUILayout.BeginHorizontal();
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("Refresh", GUILayout.Width(80), GUILayout.Height(24)))
            {
                RefreshData();
            }
            GUILayout.EndHorizontal();

            GUI.DragWindow();
        }

        // ── Ranked toggle ─────────────────────────────────────

        private static void DrawRankedToggle()
        {
            GUILayout.BeginHorizontal(boxStyle);

            bool ranked = Plugin.RankedEnabled.Value;
            string statusText = ranked ? "RANKED: ON" : "RANKED: OFF";
            Color statusColor = ranked ? Color.green : Color.gray;

            var originalColor = GUI.contentColor;
            GUI.contentColor = statusColor;
            GUILayout.Label(statusText, subHeaderStyle, GUILayout.Width(120));
            GUI.contentColor = originalColor;

            GUILayout.FlexibleSpace();

            if (GUILayout.Button(ranked ? "Disable" : "Enable", GUILayout.Width(70), GUILayout.Height(22)))
            {
                Plugin.RankedEnabled.Value = !ranked;
                string steamId = MatchTracker.LocalSteamId;
                if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
                {
                    ApiClient.ToggleRanked(steamId, Plugin.RankedEnabled.Value);
                }
            }

            GUILayout.EndHorizontal();
        }

        // ── My Stats tab ──────────────────────────────────────

        private static void DrawMyStats()
        {
            var stats = ApiClient.CachedPlayerStats;

            if (stats == null)
            {
                GUILayout.Label("No stats yet. Play a match to get started!", statLabelStyle);
                return;
            }

            GUILayout.BeginVertical(boxStyle);
            GUILayout.Label("Glicko-2 Rating", subHeaderStyle);

            GUILayout.BeginHorizontal();
            GUILayout.Label($"{stats.rating:F0}", headerStyle, GUILayout.Width(100));
            GUILayout.Label($"Deviation: {stats.rating_deviation:F0}", statLabelStyle);
            GUILayout.EndHorizontal();
            GUILayout.Label("(Lower deviation = more confident rating)", statLabelStyle);

            GUILayout.EndVertical();

            GUILayout.Space(6);

            // Level & XP bar
            GUILayout.BeginVertical(boxStyle);
            GUILayout.BeginHorizontal();
            var origLvlColor = GUI.contentColor;
            GUI.contentColor = new Color(0.4f, 0.8f, 1f);
            GUILayout.Label($"Level {stats.level}", subHeaderStyle, GUILayout.Width(80));
            GUI.contentColor = origLvlColor;

            if (stats.level < 100 && stats.xp_for_next_level > 0)
            {
                GUILayout.Label($"{stats.xp_into_level} / {stats.xp_for_next_level} XP", statLabelStyle);
            }
            else if (stats.level >= 100)
            {
                GUI.contentColor = new Color(1f, 0.85f, 0.3f);
                GUILayout.Label("MAX", statValueStyle);
                GUI.contentColor = origLvlColor;
            }
            GUILayout.FlexibleSpace();
            GUILayout.Label($"Total: {stats.total_xp:N0} XP", statLabelStyle);
            GUILayout.EndHorizontal();

            // XP progress bar
            if (stats.level < 100 && stats.xp_for_next_level > 0)
            {
                float progress = (float)stats.xp_into_level / stats.xp_for_next_level;
                Rect barRect = GUILayoutUtility.GetRect(0, 12, GUILayout.ExpandWidth(true));
                // Background
                GUI.DrawTexture(barRect, MakeTex(1, 1, new Color(0.2f, 0.2f, 0.25f, 0.8f)));
                // Fill
                Rect fillRect = new Rect(barRect.x, barRect.y, barRect.width * progress, barRect.height);
                GUI.DrawTexture(fillRect, MakeTex(1, 1, new Color(0.3f, 0.7f, 1f, 0.9f)));
            }
            GUILayout.EndVertical();

            GUILayout.Space(6);

            // Record section — always show both ranked and casual
            var history = ApiClient.CachedMatchHistory;
            GUILayout.BeginVertical(boxStyle);
            GUILayout.Label("Record", subHeaderStyle);

            int cWins = 0, cLosses = 0;
            int sweepsGiven = 0, sweepsTaken = 0;
            List<ApiClient.MatchHistoryEntry> sRanked = new List<ApiClient.MatchHistoryEntry>();
            List<ApiClient.MatchHistoryEntry> sCasual = new List<ApiClient.MatchHistoryEntry>();

            if (history != null && history.Count > 0)
            {
                sRanked = history.FindAll(m => m.is_ranked);
                sCasual = history.FindAll(m => !m.is_ranked);
                foreach (var m in sCasual) { if (m.won) cWins++; else cLosses++; }

                // Count sweeps from ALL matches
                foreach (var m in history)
                {
                    if (m.won && m.opponent_rounds_won == 0) sweepsGiven++;
                    if (!m.won && m.player_rounds_won == 0) sweepsTaken++;
                }
            }

            // Ranked record — use server's series-aware W/L (BO3 series, not individual games)
            int rWins = stats.ranked_series_wins;
            int rLosses = stats.ranked_series_losses;

            // Ranked record (always visible)
            GUILayout.BeginHorizontal();
            var oc = GUI.contentColor;
            GUI.contentColor = new Color(1f, 0.85f, 0.3f);
            GUILayout.Label("Ranked:", statValueStyle, GUILayout.Width(65));
            GUI.contentColor = oc;

            if (rWins + rLosses > 0)
            {
                string rRatio = rLosses > 0 ? $"({(float)rWins / rLosses:F1})" : (rWins > 0 ? $"({rWins}:0)" : "");
                GUILayout.Label($"{rWins}W / {rLosses}L  {rRatio}", statValueStyle, GUILayout.Width(160));

                int rStreak = CalcStreak(sRanked);
                string rsText = (rStreak > 0 ? $"Streak: {rStreak}W" : $"Streak: {-rStreak}L")
                    + (stats.best_ranked_streak > 0 ? $"  Best: {stats.best_ranked_streak}W" : "");
                GUI.contentColor = rStreak > 0 ? Color.green : new Color(1f, 0.4f, 0.4f);
                GUILayout.Label(rsText, statValueStyle);
                GUI.contentColor = oc;
            }
            else
            {
                GUI.contentColor = new Color(0.5f, 0.5f, 0.55f);
                GUILayout.Label("No ranked matches yet", statLabelStyle);
                GUI.contentColor = oc;
            }
            GUILayout.EndHorizontal();

            // Casual record (always visible)
            GUILayout.BeginHorizontal();
            GUILayout.Label("Casual:", statValueStyle, GUILayout.Width(65));

            if (sCasual.Count > 0)
            {
                string cRatio = cLosses > 0 ? $"({(float)cWins / cLosses:F1})" : (cWins > 0 ? $"({cWins}:0)" : "");
                GUILayout.Label($"{cWins}W / {cLosses}L  {cRatio}", statValueStyle, GUILayout.Width(160));

                int cStreak = CalcStreak(sCasual);
                string csText = (cStreak > 0 ? $"Streak: {cStreak}W" : $"Streak: {-cStreak}L")
                    + (stats.best_casual_streak > 0 ? $"  Best: {stats.best_casual_streak}W" : "");
                var oc2 = GUI.contentColor;
                GUI.contentColor = cStreak > 0 ? Color.green : new Color(1f, 0.4f, 0.4f);
                GUILayout.Label(csText, statValueStyle);
                GUI.contentColor = oc2;
            }
            else
            {
                var oc3 = GUI.contentColor;
                GUI.contentColor = new Color(0.5f, 0.5f, 0.55f);
                GUILayout.Label("No casual matches yet", statLabelStyle);
                GUI.contentColor = oc3;
            }
            GUILayout.EndHorizontal();

            // Sweep stats
            if (sweepsGiven + sweepsTaken > 0)
            {
                GUILayout.BeginHorizontal();
                GUILayout.Label("Sweeps:", statValueStyle, GUILayout.Width(65));
                var oc4 = GUI.contentColor;
                GUI.contentColor = Color.green;
                GUILayout.Label($"5-0 x{sweepsGiven}", statValueStyle, GUILayout.Width(70));
                GUI.contentColor = new Color(1f, 0.4f, 0.4f);
                GUILayout.Label($"0-5 x{sweepsTaken}", statValueStyle);
                GUI.contentColor = oc4;
                GUILayout.EndHorizontal();
            }

            // Total (use PlayerStats API for accurate lifetime count)
            GUILayout.Space(4);
            int totalW = stats.wins;
            int totalL = stats.losses;
            string totalRatio = totalL > 0 ? $"({(float)totalW / totalL:F1})" : (totalW > 0 ? $"({totalW}:0)" : "");
            GUILayout.Label($"Total: {stats.total_matches} matches  ({totalW}W / {totalL}L  {totalRatio})", statLabelStyle);

            GUILayout.EndVertical();

            GUILayout.Space(6);

            // ── Session Info ──────────────────────────────────────
            var sessionTime = GameStateWatcher.SessionTimeByOpponent;
            if (sessionTime != null && sessionTime.Count > 0)
            {
                GUILayout.BeginVertical(boxStyle);
                var oc5 = GUI.contentColor;
                GUI.contentColor = new Color(0.7f, 0.8f, 1f);
                GUILayout.Label($"Session ({GameStateWatcher.SessionMatchCount} games)", subHeaderStyle);
                GUI.contentColor = oc5;

                foreach (var kvp in sessionTime)
                {
                    int mins = (int)kvp.Value;
                    string timeStr = mins >= 60 ? $"{mins / 60}h {mins % 60}m" : $"{mins}m";
                    GUILayout.Label($"  {kvp.Key}: {timeStr}", statLabelStyle);
                }

                GUILayout.EndVertical();
                GUILayout.Space(6);
            }

            // ── Recent matches split by ranked/casual ──────────
            history = ApiClient.CachedMatchHistory;
            if (history != null && history.Count > 0)
            {
                // ── RANKED HISTORY with series grouping ──
                GUILayout.BeginVertical(boxStyle);
                var origColor1 = GUI.contentColor;
                GUI.contentColor = new Color(1f, 0.85f, 0.3f);
                GUILayout.Label("Ranked History", subHeaderStyle);
                GUI.contentColor = origColor1;

                var ranked = history.FindAll(m => m.is_ranked);
                if (ranked.Count > 0)
                {
                    // Per-opponent series W/L summary
                    DrawOpponentSummary(ranked);
                    GUILayout.Space(4);

                    // Group ranked matches into series
                    var seriesGroups = GroupMatchesBySeries(ranked);

                    // Paginate by series groups (3 per page)
                    int groupsPerPage = 3;
                    int totalSeriesPages = (seriesGroups.Count + groupsPerPage - 1) / groupsPerPage;
                    rankedPage = Math.Max(0, Math.Min(rankedPage, totalSeriesPages - 1));
                    int startIdx = rankedPage * groupsPerPage;
                    int endIdx = Math.Min(startIdx + groupsPerPage, seriesGroups.Count);

                    for (int g = startIdx; g < endIdx; g++)
                    {
                        DrawSeriesGroup(seriesGroups[g]);
                    }

                    if (totalSeriesPages > 1)
                    {
                        GUILayout.BeginHorizontal();
                        GUILayout.FlexibleSpace();
                        if (rankedPage > 0 && GUILayout.Button("< Prev", GUILayout.Width(60)))
                            rankedPage--;
                        GUILayout.Label($"{rankedPage + 1}/{totalSeriesPages}", statLabelStyle, GUILayout.Width(40));
                        if (rankedPage < totalSeriesPages - 1 && GUILayout.Button("Next >", GUILayout.Width(60)))
                            rankedPage++;
                        GUILayout.FlexibleSpace();
                        GUILayout.EndHorizontal();
                    }
                }
                else
                {
                    GUILayout.Label("No ranked matches yet", statLabelStyle);
                }
                GUILayout.EndVertical();
                GUILayout.Space(4);

                // ── CASUAL HISTORY (flat list, no series grouping) ──
                var casual = history.FindAll(m => !m.is_ranked);
                if (casual.Count > 0)
                {
                    GUILayout.BeginVertical(boxStyle);
                    GUILayout.Label("Casual History", subHeaderStyle);

                    int totalCasualPages = (casual.Count + matchesPerPage - 1) / matchesPerPage;
                    casualPage = Math.Max(0, Math.Min(casualPage, totalCasualPages - 1));
                    int csStart = casualPage * matchesPerPage;
                    int csEnd = Math.Min(csStart + matchesPerPage, casual.Count);

                    for (int i = csStart; i < csEnd; i++)
                    {
                        DrawMatchEntry(casual[i]);
                    }

                    if (totalCasualPages > 1)
                    {
                        GUILayout.BeginHorizontal();
                        GUILayout.FlexibleSpace();
                        if (casualPage > 0 && GUILayout.Button("< Prev", GUILayout.Width(60)))
                            casualPage--;
                        GUILayout.Label($"{casualPage + 1}/{totalCasualPages}", statLabelStyle, GUILayout.Width(40));
                        if (casualPage < totalCasualPages - 1 && GUILayout.Button("Next >", GUILayout.Width(60)))
                            casualPage++;
                        GUILayout.FlexibleSpace();
                        GUILayout.EndHorizontal();
                    }
                    GUILayout.EndVertical();
                }
            }
            else if (MatchTracker.HasPendingResult && MatchTracker.LastResult != null)
            {
                var result = MatchTracker.LastResult;
                GUILayout.BeginVertical(boxStyle);
                GUILayout.Label("Last Match", subHeaderStyle);

                var color = result.Won ? Color.green : new Color(1f, 0.4f, 0.4f);
                var origColor = GUI.contentColor;
                GUI.contentColor = color;
                GUILayout.Label(
                    $"{(result.Won ? "WIN" : "LOSS")} vs {result.OpponentName}  " +
                    $"({result.MyRounds} - {result.TheirRounds})",
                    statValueStyle
                );
                GUI.contentColor = origColor;

                GUILayout.EndVertical();
            }
        }

        private static void DrawMatchEntry(ApiClient.MatchHistoryEntry m)
        {
            var color = m.won ? Color.green : new Color(1f, 0.4f, 0.4f);
            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            string result = m.won ? "W" : "L";
            string oppName = TruncateName(m.opponent_name, 14);

            // Parse date from ended_at
            string dateStr = "";
            if (!string.IsNullOrEmpty(m.ended_at) && m.ended_at.Length >= 10)
            {
                try
                {
                    var dt = DateTime.Parse(m.ended_at);
                    dateStr = dt.ToString("M/d");
                }
                catch
                {
                    dateStr = m.ended_at.Substring(5, 5); // Fallback: "04-01"
                }
            }

            GUILayout.BeginHorizontal();
            GUILayout.Label(
                $"  {result}  {m.player_rounds_won}-{m.opponent_rounds_won}  vs {oppName}",
                statValueStyle
            );
            if (!string.IsNullOrEmpty(dateStr))
            {
                GUI.contentColor = new Color(0.5f, 0.5f, 0.55f);
                GUILayout.Label(dateStr, statLabelStyle, GUILayout.Width(40));
            }
            GUILayout.EndHorizontal();
            GUI.contentColor = origColor;

            // Show card picks for this match (if available)
            if (!string.IsNullOrEmpty(m.cards_display))
            {
                GUI.contentColor = new Color(0.6f, 0.7f, 0.9f);
                GUILayout.Label($"       Cards: {m.cards_display}", statLabelStyle);
                GUI.contentColor = origColor;
            }

            // Show opponent's card picks (if available)
            if (!string.IsNullOrEmpty(m.opp_cards_display))
            {
                GUI.contentColor = new Color(0.9f, 0.6f, 0.5f);
                GUILayout.Label($"       Opp:   {m.opp_cards_display}", statLabelStyle);
                GUI.contentColor = origColor;
            }
        }

        // ── Series grouping helpers ───────────────────────────

        private struct SeriesGroup
        {
            public string series_id; // null = legacy standalone match
            public List<ApiClient.MatchHistoryEntry> matches;
        }

        /// <summary>
        /// Groups ranked matches by series_id. Matches with no series_id
        /// become standalone groups. Maintains chronological order (newest first).
        /// </summary>
        private static List<SeriesGroup> GroupMatchesBySeries(List<ApiClient.MatchHistoryEntry> ranked)
        {
            var groups = new List<SeriesGroup>();
            SeriesGroup current = new SeriesGroup { series_id = null, matches = null };

            foreach (var m in ranked)
            {
                string sid = m.series_id;
                bool hasSeries = !string.IsNullOrEmpty(sid) && sid != "null";

                if (hasSeries && current.matches != null && current.series_id == sid)
                {
                    // Same series — add to current group
                    current.matches.Add(m);
                }
                else
                {
                    // Save previous group if it exists
                    if (current.matches != null && current.matches.Count > 0)
                        groups.Add(current);

                    // Start new group
                    current = new SeriesGroup
                    {
                        series_id = hasSeries ? sid : null,
                        matches = new List<ApiClient.MatchHistoryEntry> { m }
                    };
                }
            }

            // Don't forget the last group
            if (current.matches != null && current.matches.Count > 0)
                groups.Add(current);

            return groups;
        }

        /// <summary>
        /// Draws a series group: header with series result + elo change,
        /// then indented individual matches below.
        /// </summary>
        private static void DrawSeriesGroup(SeriesGroup group)
        {
            if (group.matches == null || group.matches.Count == 0) return;

            var first = group.matches[0]; // Most recent match in series (has final score)
            var origColor = GUI.contentColor;

            if (group.series_id != null)
            {
                // ── Series header ──
                string score = first.series_score ?? "?-?";
                string oppName = TruncateName(first.opponent_name, 14);

                // Determine if series is complete (either side reached 2)
                bool seriesComplete = false;
                bool seriesWon = false;
                try
                {
                    var parts = score.Split('-');
                    int myW = int.Parse(parts[0]);
                    int thW = int.Parse(parts[1]);
                    seriesComplete = (myW >= 2 || thW >= 2);
                    seriesWon = myW > thW;
                }
                catch { }

                // Header line
                Color headerColor = seriesComplete
                    ? (seriesWon ? new Color(0.3f, 1f, 0.3f) : new Color(1f, 0.4f, 0.4f))
                    : new Color(1f, 0.85f, 0.3f);
                GUI.contentColor = headerColor;

                string headerLabel = seriesComplete
                    ? $"Series {(seriesWon ? "W" : "L")} {score}  vs {oppName}"
                    : $"Series {score}  vs {oppName}  (in progress)";

                GUILayout.BeginHorizontal();
                GUILayout.Label(headerLabel, statValueStyle);

                // Show elo change for completed series
                if (seriesComplete && first.series_rating_change != 0f)
                {
                    float rc = first.series_rating_change;
                    GUI.contentColor = rc > 0 ? Color.green : new Color(1f, 0.4f, 0.4f);
                    GUILayout.Label($"{(rc > 0 ? "+" : "")}{rc:F0}", statValueStyle, GUILayout.Width(45));
                }
                GUILayout.EndHorizontal();
                GUI.contentColor = origColor;

                // Indented individual matches
                foreach (var m in group.matches)
                {
                    DrawMatchEntryIndented(m);
                }
            }
            else
            {
                // Single match (legacy or solo series match) — draw normally
                DrawMatchEntry(first);
            }

            GUILayout.Space(2);
        }

        /// <summary>
        /// Draws a match entry indented under a series header.
        /// Compact version without opponent name (already in header).
        /// </summary>
        private static void DrawMatchEntryIndented(ApiClient.MatchHistoryEntry m)
        {
            var color = m.won ? Color.green : new Color(1f, 0.4f, 0.4f);
            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            string result = m.won ? "W" : "L";
            string dateStr = "";
            if (!string.IsNullOrEmpty(m.ended_at) && m.ended_at.Length >= 10)
            {
                try { dateStr = DateTime.Parse(m.ended_at).ToString("M/d"); }
                catch { dateStr = m.ended_at.Substring(5, 5); }
            }

            GUILayout.BeginHorizontal();
            GUILayout.Label(
                $"      {result}  {m.player_rounds_won}-{m.opponent_rounds_won}",
                statValueStyle
            );
            if (!string.IsNullOrEmpty(dateStr))
            {
                GUI.contentColor = new Color(0.5f, 0.5f, 0.55f);
                GUILayout.Label(dateStr, statLabelStyle, GUILayout.Width(40));
            }
            GUILayout.EndHorizontal();
            GUI.contentColor = origColor;

            // Cards (indented further)
            if (!string.IsNullOrEmpty(m.cards_display))
            {
                GUI.contentColor = new Color(0.6f, 0.7f, 0.9f);
                GUILayout.Label($"           Cards: {m.cards_display}", statLabelStyle);
                GUI.contentColor = origColor;
            }
            if (!string.IsNullOrEmpty(m.opp_cards_display))
            {
                GUI.contentColor = new Color(0.9f, 0.6f, 0.5f);
                GUILayout.Label($"           Opp:   {m.opp_cards_display}", statLabelStyle);
                GUI.contentColor = origColor;
            }
        }

        /// <summary>
        /// Shows per-opponent series W/L summary at the top of ranked history.
        /// Counts completed BO3 series, not individual games.
        /// </summary>
        private static void DrawOpponentSummary(List<ApiClient.MatchHistoryEntry> ranked)
        {
            // Build per-opponent series stats by grouping
            var seriesGroups = GroupMatchesBySeries(ranked);
            var oppStats = new Dictionary<string, int[]>(); // [seriesWins, seriesLosses]

            foreach (var group in seriesGroups)
            {
                if (group.series_id == null || group.matches.Count == 0) continue;

                var first = group.matches[0];
                string oppName = first.opponent_name ?? "Unknown";
                string score = first.series_score ?? "";

                // Only count completed series
                try
                {
                    var parts = score.Split('-');
                    int myW = int.Parse(parts[0]);
                    int thW = int.Parse(parts[1]);
                    if (myW < 2 && thW < 2) continue; // In progress

                    if (!oppStats.ContainsKey(oppName))
                        oppStats[oppName] = new int[] { 0, 0 };

                    if (myW > thW) oppStats[oppName][0]++;
                    else oppStats[oppName][1]++;
                }
                catch { }
            }

            if (oppStats.Count == 0) return;

            var origColor = GUI.contentColor;
            GUI.contentColor = new Color(0.7f, 0.8f, 1f);

            string summaryLine = "";
            foreach (var kvp in oppStats)
            {
                if (summaryLine.Length > 0) summaryLine += "   ";
                summaryLine += $"vs {TruncateName(kvp.Key, 10)}: {kvp.Value[0]}W-{kvp.Value[1]}L";
            }
            GUILayout.Label(summaryLine, statLabelStyle);
            GUI.contentColor = origColor;
        }

        // ── Leaderboard tab ───────────────────────────────────

        private static void DrawLeaderboard()
        {
            var board = ApiClient.CachedLeaderboard;

            if (board == null || board.entries == null || board.entries.Length == 0)
            {
                GUILayout.Label("No leaderboard data yet.", statLabelStyle);
                return;
            }

            GUILayout.BeginHorizontal();
            GUILayout.Label("#", rankStyle, GUILayout.Width(26));
            GUILayout.Label("Lv", subHeaderStyle, GUILayout.Width(28));
            GUILayout.Label("Player", subHeaderStyle, GUILayout.Width(140));
            GUILayout.Label("Rating", subHeaderStyle, GUILayout.Width(55));
            GUILayout.Label("W", subHeaderStyle, GUILayout.Width(30));
            GUILayout.Label("L", subHeaderStyle, GUILayout.Width(30));
            GUILayout.Label("W/L", subHeaderStyle, GUILayout.Width(45));
            GUILayout.EndHorizontal();

            GUILayout.Space(2);

            leaderboardScroll = GUILayout.BeginScrollView(leaderboardScroll, GUILayout.Height(280));

            foreach (var entry in board.entries)
            {
                bool isLocal = entry.steam_id == MatchTracker.LocalSteamId;
                bool isSelected = entry.steam_id == selectedPlayerSteamId;
                var bgColor = GUI.backgroundColor;
                if (isLocal) GUI.backgroundColor = new Color(0.2f, 0.5f, 0.2f, 0.5f);
                else if (isSelected) GUI.backgroundColor = new Color(0.3f, 0.3f, 0.5f, 0.5f);

                GUILayout.BeginHorizontal(entryStyle);
                GUILayout.Label($"{entry.rank}", rankStyle, GUILayout.Width(26));

                // Level with color
                var lvColor = GUI.contentColor;
                GUI.contentColor = new Color(0.4f, 0.8f, 1f);
                GUILayout.Label($"{entry.level}", statLabelStyle, GUILayout.Width(28));
                GUI.contentColor = lvColor;

                // Clickable player name
                var nameStyle = isSelected ? statValueStyle : statLabelStyle;
                if (GUILayout.Button(TruncateName(entry.display_name, 16), nameStyle, GUILayout.Width(140), GUILayout.Height(18)))
                {
                    if (selectedPlayerSteamId == entry.steam_id)
                    {
                        selectedPlayerSteamId = "";
                        selectedPlayerStats = null;
                    }
                    else
                    {
                        selectedPlayerSteamId = entry.steam_id;
                        selectedPlayerStats = null;
                        selectedPlayerLoading = true;
                        ApiClient.FetchPlayerStatsForView(entry.steam_id, (data) =>
                        {
                            selectedPlayerStats = data;
                            selectedPlayerLoading = false;
                        });
                    }
                }

                GUILayout.Label($"{entry.rating}", statValueStyle, GUILayout.Width(55));
                GUILayout.Label($"{entry.wins}", statLabelStyle, GUILayout.Width(30));
                GUILayout.Label($"{entry.losses}", statLabelStyle, GUILayout.Width(30));
                string lbRatio = entry.losses > 0 ? $"{(float)entry.wins / entry.losses:F1}" : (entry.wins > 0 ? $"{entry.wins}:0" : "0:0");
                GUILayout.Label(lbRatio, statLabelStyle, GUILayout.Width(45));
                GUILayout.EndHorizontal();

                GUI.backgroundColor = bgColor;
            }

            GUILayout.EndScrollView();

            GUILayout.Label($"{board.total_players} players ranked", statLabelStyle);

            // Selected player detail panel
            if (!string.IsNullOrEmpty(selectedPlayerSteamId))
            {
                GUILayout.Space(4);
                GUILayout.BeginVertical(boxStyle);

                if (selectedPlayerLoading)
                {
                    GUILayout.Label("Loading player stats...", statLabelStyle);
                }
                else if (selectedPlayerStats != null)
                {
                    var ps = selectedPlayerStats;
                    GUILayout.BeginHorizontal();
                    GUILayout.Label(ps.display_name, subHeaderStyle);
                    GUILayout.FlexibleSpace();
                    var origLv = GUI.contentColor;
                    GUI.contentColor = new Color(0.4f, 0.8f, 1f);
                    GUILayout.Label($"Lv {ps.level}", statValueStyle);
                    GUI.contentColor = origLv;
                    GUILayout.EndHorizontal();

                    GUILayout.BeginHorizontal();
                    GUILayout.Label($"Rating: {ps.rating:F0}", statValueStyle, GUILayout.Width(120));
                    GUILayout.Label($"RD: {ps.rating_deviation:F0}", statLabelStyle, GUILayout.Width(80));
                    GUILayout.EndHorizontal();

                    string pRatio = ps.losses > 0 ? $"({(float)ps.wins / ps.losses:F1})" : (ps.wins > 0 ? $"({ps.wins}:0)" : "");
                    GUILayout.Label($"{ps.total_matches} matches  ({ps.wins}W / {ps.losses}L  {pRatio})", statLabelStyle);

                    if (ps.ranked_enabled)
                    {
                        var origC = GUI.contentColor;
                        GUI.contentColor = Color.green;
                        GUILayout.Label("Ranked: Active", statLabelStyle);
                        GUI.contentColor = origC;
                    }

                    // Top 5 cards
                    if (ps.top_card_names != null && ps.top_card_names.Count > 0)
                    {
                        GUILayout.Space(4);
                        GUILayout.Label("Top Cards:", statLabelStyle);
                        var origCardColor = GUI.contentColor;
                        GUI.contentColor = new Color(0.6f, 0.7f, 0.9f);
                        for (int ci = 0; ci < ps.top_card_names.Count && ci < 5; ci++)
                        {
                            string pickText = ps.top_card_picks.Count > ci ? $" ({ps.top_card_picks[ci]}x)" : "";
                            GUILayout.Label($"  {ps.top_card_names[ci]}{pickText}", statLabelStyle);
                        }
                        GUI.contentColor = origCardColor;
                    }
                }
                else
                {
                    GUILayout.Label("Player not found", statLabelStyle);
                }

                GUILayout.EndVertical();
            }
        }

        // ── Card Stats tab ────────────────────────────────────

        private static void DrawCardStats()
        {
            // Filter buttons: All / Ranked / Casual
            string[] filterNames = { "All", "Ranked", "Casual" };
            GUILayout.BeginHorizontal();
            for (int f = 0; f < filterNames.Length; f++)
            {
                var style = (f == cardStatsFilter) ? activeTabStyle : tabStyle;
                if (GUILayout.Button(filterNames[f], style, GUILayout.Height(22)))
                {
                    if (cardStatsFilter != f)
                    {
                        cardStatsFilter = f;
                        string isRanked = f == 1 ? "true" : (f == 2 ? "false" : null);
                        ApiClient.FetchCardStats(50, MatchTracker.LocalSteamId, "times_picked", isRanked);
                    }
                }
            }
            GUILayout.EndHorizontal();
            GUILayout.Space(4);

            var cards = ApiClient.CachedCardStats;

            if (cards == null || cards.Count == 0)
            {
                GUILayout.Label("No card stats yet.", statLabelStyle);
                return;
            }

            // Sort client-side based on current sort column
            var sorted = new List<ApiClient.CardStatData>(cards);
            switch (cardSortBy)
            {
                case "card_name":
                    sorted.Sort((a, b) => cardSortDesc ? string.Compare(b.card_name, a.card_name, StringComparison.OrdinalIgnoreCase) : string.Compare(a.card_name, b.card_name, StringComparison.OrdinalIgnoreCase));
                    break;
                case "card_rarity":
                    sorted.Sort((a, b) => cardSortDesc ? string.Compare(b.card_rarity, a.card_rarity, StringComparison.OrdinalIgnoreCase) : string.Compare(a.card_rarity, b.card_rarity, StringComparison.OrdinalIgnoreCase));
                    break;
                case "times_picked":
                    sorted.Sort((a, b) => cardSortDesc ? b.times_picked.CompareTo(a.times_picked) : a.times_picked.CompareTo(b.times_picked));
                    break;
                case "wins_with_card":
                    sorted.Sort((a, b) => cardSortDesc ? b.wins_with_card.CompareTo(a.wins_with_card) : a.wins_with_card.CompareTo(b.wins_with_card));
                    break;
                case "win_rate":
                    sorted.Sort((a, b) => cardSortDesc ? b.win_rate.CompareTo(a.win_rate) : a.win_rate.CompareTo(b.win_rate));
                    break;
            }

            // Sortable column headers
            GUILayout.BeginHorizontal();
            DrawSortButton("Card", "card_name", 160);
            DrawSortButton("Rarity", "card_rarity", 80);
            DrawSortButton("Picks", "times_picked", 50);
            DrawSortButton("Wins", "wins_with_card", 50);
            DrawSortButton("WR%", "win_rate", 50);
            GUILayout.EndHorizontal();

            GUILayout.Space(2);

            cardStatsScroll = GUILayout.BeginScrollView(cardStatsScroll, GUILayout.ExpandHeight(true));

            foreach (var card in sorted)
            {
                GUILayout.BeginHorizontal(entryStyle);
                GUILayout.Label(TruncateName(card.card_name, 20), statLabelStyle, GUILayout.Width(160));
                GUILayout.Label(card.card_rarity ?? "?", statLabelStyle, GUILayout.Width(80));
                GUILayout.Label($"{card.times_picked}", statLabelStyle, GUILayout.Width(50));
                GUILayout.Label($"{card.wins_with_card}", statLabelStyle, GUILayout.Width(50));

                float wr = card.win_rate * 100;
                var origColor = GUI.contentColor;
                GUI.contentColor = wr >= 55 ? Color.green : wr <= 45 ? new Color(1f, 0.4f, 0.4f) : Color.white;
                GUILayout.Label($"{wr:F0}%", statValueStyle, GUILayout.Width(50));
                GUI.contentColor = origColor;

                GUILayout.EndHorizontal();
            }

            GUILayout.EndScrollView();
        }

        private static void DrawSortButton(string label, string sortKey, float width)
        {
            string arrow = "";
            if (cardSortBy == sortKey)
                arrow = cardSortDesc ? " v" : " ^";

            var style = (cardSortBy == sortKey) ? activeTabStyle : tabStyle;
            if (GUILayout.Button(label + arrow, style, GUILayout.Width(width), GUILayout.Height(20)))
            {
                if (cardSortBy == sortKey)
                    cardSortDesc = !cardSortDesc;
                else
                {
                    cardSortBy = sortKey;
                    cardSortDesc = true;
                }
            }
        }

        // ── FPS Counter (top-left, small grey) ─────────────────

        private static void DrawFPS()
        {
            // Update FPS counter
            fpsFrameCount++;
            fpsTimer += Time.deltaTime;
            if (fpsTimer >= 0.5f)
            {
                fpsDisplay = fpsFrameCount / fpsTimer;
                fpsFrameCount = 0;
                fpsTimer = 0f;
            }

            if (fpsStyle == null)
            {
                fpsStyle = new GUIStyle(GUI.skin.label);
                fpsStyle.fontSize = 11;
                fpsStyle.normal.textColor = new Color(0.5f, 0.5f, 0.5f, 0.7f);
            }

            GUI.Label(new Rect(6, 4, 60, 18), $"{fpsDisplay:F0} FPS", fpsStyle);
        }

        // ── Notification (bottom center, small) ───────────────

        private static void DrawNotification()
        {
            // Process queue when current notification finishes
            if (notificationTimer <= 0f && notificationQueue.Count > 0)
            {
                var next = notificationQueue[0];
                notificationQueue.RemoveAt(0);
                notificationText = next.Text;
                notificationColor = next.Color;
                notificationTimer = next.Duration;
            }

            if (notificationTimer <= 0f) return;

            notificationTimer -= Time.deltaTime;

            float alpha = Mathf.Clamp01(notificationTimer);
            var color = new Color(notificationColor.r, notificationColor.g, notificationColor.b, alpha);

            InitStyles();

            var origColor = GUI.contentColor;
            GUI.contentColor = color;

            float width = 500;
            float x = (Screen.width - width) / 2;
            float y = Screen.height - 80;

            // Draw a subtle background behind the notification
            var bgTex = MakeTex(1, 1, new Color(0f, 0f, 0f, alpha * 0.5f));
            GUI.DrawTexture(new Rect(x, y - 2, width, 28), bgTex);

            GUI.Label(new Rect(x, y, width, 24), notificationText, notificationStyle);
            GUI.contentColor = origColor;
        }

        // ── Match status (top center, only for ranked) ────────

        private static void DrawMatchStatus()
        {
            if (!MatchTracker.IsInMatch) return;

            // Only show the indicator when the match is actually ranked
            // (both players have mod + ranked enabled)
            if (!GameStateWatcher.MatchIsRanked) return;

            InitStyles();

            float width = 140;
            float x = (Screen.width - width) / 2;
            float y = 8;

            var origColor = GUI.contentColor;
            GUI.contentColor = Color.green;
            GUI.Label(new Rect(x, y, width, 18), "RANKED - Recording", smallCenterStyle);
            GUI.contentColor = origColor;
        }

        // ── Helpers ───────────────────────────────────────────

        private static float lastRefreshTime = -10f;

        private static void RefreshData()
        {
            // Prevent spam - minimum 5 seconds between refreshes
            if (Time.realtimeSinceStartup - lastRefreshTime < 5f) return;
            lastRefreshTime = Time.realtimeSinceStartup;

            string steamId = MatchTracker.LocalSteamId;
            if (!string.IsNullOrEmpty(steamId) && steamId != "unknown")
            {
                ApiClient.FetchPlayerStats(steamId);
                ApiClient.FetchMatchHistory(steamId);
            }

            if (currentTab == 1) ApiClient.FetchLeaderboard();
            if (currentTab == 2) ApiClient.FetchCardStats(50, MatchTracker.LocalSteamId);
        }

        private static void DrawStat(string label, string value)
        {
            GUILayout.BeginVertical(GUILayout.Width(90));
            GUILayout.Label(label, statLabelStyle);
            GUILayout.Label(value, statValueStyle);
            GUILayout.EndVertical();
        }

        /// <summary>
        /// Calculates current win/loss streak from match history.
        /// Returns positive number for win streak, negative for loss streak.
        /// </summary>
        private static int CalcStreak(List<ApiClient.MatchHistoryEntry> matches)
        {
            if (matches == null || matches.Count == 0) return 0;

            bool streakType = matches[0].won; // First (most recent) match
            int count = 0;

            for (int i = 0; i < matches.Count; i++)
            {
                if (matches[i].won == streakType)
                    count++;
                else
                    break;
            }

            return streakType ? count : -count;
        }

        private static string TruncateName(string name, int maxLength)
        {
            if (string.IsNullOrEmpty(name)) return "";
            return name.Length <= maxLength ? name : name.Substring(0, maxLength - 2) + "..";
        }

        // ── Style initialization ──────────────────────────────

        private static void InitStyles()
        {
            if (stylesInitialized) return;
            stylesInitialized = true;

            var bgTex = MakeTex(2, 2, new Color(0.1f, 0.1f, 0.12f, 0.92f));
            var entryBgTex = MakeTex(2, 2, new Color(0.15f, 0.15f, 0.18f, 0.6f));
            var tabBgTex = MakeTex(2, 2, new Color(0.2f, 0.2f, 0.24f, 0.8f));
            var activeTabBgTex = MakeTex(2, 2, new Color(0.3f, 0.45f, 0.7f, 0.9f));

            boxStyle = new GUIStyle(GUI.skin.box);
            boxStyle.normal.background = bgTex;
            boxStyle.padding = new RectOffset(12, 12, 10, 10);

            entryStyle = new GUIStyle(GUI.skin.box);
            entryStyle.normal.background = entryBgTex;
            entryStyle.padding = new RectOffset(4, 4, 2, 2);
            entryStyle.margin = new RectOffset(0, 0, 1, 1);

            headerStyle = new GUIStyle(GUI.skin.label);
            headerStyle.fontSize = 22;
            headerStyle.fontStyle = FontStyle.Bold;
            headerStyle.normal.textColor = Color.white;

            subHeaderStyle = new GUIStyle(GUI.skin.label);
            subHeaderStyle.fontSize = 13;
            subHeaderStyle.fontStyle = FontStyle.Bold;
            subHeaderStyle.normal.textColor = new Color(0.8f, 0.85f, 1f);

            statLabelStyle = new GUIStyle(GUI.skin.label);
            statLabelStyle.fontSize = 12;
            statLabelStyle.normal.textColor = new Color(0.7f, 0.7f, 0.75f);

            statValueStyle = new GUIStyle(GUI.skin.label);
            statValueStyle.fontSize = 13;
            statValueStyle.fontStyle = FontStyle.Bold;
            statValueStyle.normal.textColor = Color.white;

            rankStyle = new GUIStyle(GUI.skin.label);
            rankStyle.fontSize = 13;
            rankStyle.fontStyle = FontStyle.Bold;
            rankStyle.normal.textColor = new Color(1f, 0.85f, 0.4f);
            rankStyle.alignment = TextAnchor.MiddleCenter;

            tabStyle = new GUIStyle(GUI.skin.button);
            tabStyle.normal.background = tabBgTex;
            tabStyle.fontSize = 12;
            tabStyle.normal.textColor = new Color(0.7f, 0.7f, 0.75f);

            activeTabStyle = new GUIStyle(GUI.skin.button);
            activeTabStyle.normal.background = activeTabBgTex;
            activeTabStyle.fontSize = 12;
            activeTabStyle.fontStyle = FontStyle.Bold;
            activeTabStyle.normal.textColor = Color.white;

            smallCenterStyle = new GUIStyle(GUI.skin.label);
            smallCenterStyle.fontSize = 11;
            smallCenterStyle.fontStyle = FontStyle.Bold;
            smallCenterStyle.alignment = TextAnchor.MiddleCenter;

            notificationStyle = new GUIStyle(GUI.skin.label);
            notificationStyle.fontSize = 16;
            notificationStyle.fontStyle = FontStyle.Bold;
            notificationStyle.alignment = TextAnchor.MiddleCenter;
        }

        private static Texture2D MakeTex(int width, int height, Color color)
        {
            var pixels = new Color[width * height];
            for (int i = 0; i < pixels.Length; i++) pixels[i] = color;
            var tex = new Texture2D(width, height);
            tex.SetPixels(pixels);
            tex.Apply();
            return tex;
        }
    }
}
