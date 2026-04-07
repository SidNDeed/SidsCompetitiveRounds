using ExitGames.Client.Photon;
using Photon.Pun;
using Steamworks;
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.RegularExpressions;
using UnityEngine;

using Hashtable = ExitGames.Client.Photon.Hashtable;

namespace CompetitiveRounds
{
    public static class GameStateWatcher
    {
        // \u2500\u2500 Room state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        private static bool wasInRoom = false;

        // \u2500\u2500 Match state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        private static bool isTracking = false;
        private static bool wasGameInProgress = false;
        private static DateTime matchStartTime;

        // Score tracking
        private static int lastP1Points = 0;
        private static int lastP2Points = 0;
        private static int lastP1Rounds = 0;
        private static int lastP2Rounds = 0;
        private static int p1Points = 0;
        private static int p2Points = 0;
        private static int p1Rounds = 0;
        private static int p2Rounds = 0;
        private static int currentRound = 1;

        // Player identity
        private static string localSteamId = "";
        private static string localDisplayName = "";
        private static string opponentSteamId = "";
        private static string opponentDisplayName = "";
        private static int localTeamId = -1;
        private static bool playersIdentified = false;
        private static bool opponentSteamIdResolved = false;

        // Ranked status
        private static bool opponentIsRanked = false;
        private static bool opponentRankChecked = false;
        private static bool matchIsRanked = false;

        // Harmony opponent card tracking
        private static bool opponentCardsViaHarmony = false;
        private static List<MatchTracker.CardPickData> preMatchOpponentCards = new List<MatchTracker.CardPickData>();

        // Card tracking
        private static List<MatchTracker.CardPickData> localCards = new List<MatchTracker.CardPickData>();
        private static List<MatchTracker.CardPickData> opponentCards = new List<MatchTracker.CardPickData>();
        private static int lastKnownP1CardCount = 0;
        private static int lastKnownP2CardCount = 0;

        // Card sharing via Photon custom properties
        private static List<string> broadcastCardNames = new List<string>();
        private static int lastKnownOpponentBroadcastCount = 0;
        private const string CARD_PROP_KEY = "cr_cards";

        // Pre-match card picks (cards picked before isTracking = true)
        // These get moved into localCards when OnMatchStarted fires
        private static List<MatchTracker.CardPickData> preMatchCards = new List<MatchTracker.CardPickData>();
        private static int preMatchPickCount = 0;

        // Room info
        private static string photonRoomId = "";
        private static string photonRegion = "";

        // Game over
        private static bool gameOverReported = false;

        // GM_ArmsRace fields
        private static FieldInfo f_p1Points;
        private static FieldInfo f_p2Points;
        private static FieldInfo f_p1Rounds;
        private static FieldInfo f_p2Rounds;
        private static FieldInfo f_roundsToWinGame;
        private static bool fieldsResolved = false;
        private static int roundsToWin = 5;

        // Poll throttle
        private static float pollTimer = 0f;

        // Session tracking
        private static DateTime roomJoinTime;
        private static DateTime sessionStartTime = DateTime.UtcNow;
        private static Dictionary<string, float> sessionTimeByOpponent = new Dictionary<string, float>();
        private static int sessionMatchCount = 0;

        // Per-opponent W/L tracking within session
        private static Dictionary<string, int[]> sessionWLByOpponent = new Dictionary<string, int[]>(); // [rW, rL, cW, cL]
        private static int sessionRankedWins = 0;
        private static int sessionRankedLosses = 0;
        private static int sessionCasualWins = 0;
        private static int sessionCasualLosses = 0;

        // Public state
        public static MatchTracker.MatchResult LastResult { get; private set; }
        public static bool HasPendingResult { get; private set; } = false;
        public static bool MatchIsRanked => matchIsRanked;

        // Session accessors
        public static Dictionary<string, float> SessionTimeByOpponent => sessionTimeByOpponent;
        public static Dictionary<string, int[]> SessionWLByOpponent => sessionWLByOpponent;
        public static int SessionMatchCount => sessionMatchCount;
        public static int SessionRankedWins => sessionRankedWins;
        public static int SessionRankedLosses => sessionRankedLosses;
        public static int SessionCasualWins => sessionCasualWins;
        public static int SessionCasualLosses => sessionCasualLosses;
        public static DateTime SessionStartTime => sessionStartTime;

        // \u2500\u2500 Initialization \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        public static void Initialize()
        {
            sessionStartTime = DateTime.UtcNow;
            IdentifyLocalPlayer();
            RegisterLogListener(); // Register early to catch all picks
            Plugin.Log.LogInfo("GameStateWatcher initialized");
        }

        // \u2500\u2500 Main poll loop \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        public static void Poll()
        {
            pollTimer += Time.deltaTime;
            if (pollTimer < 0.1f) return;
            pollTimer = 0f;

            PollRoomState();
            PollMatchState();
        }

        // \u2500\u2500 Room state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void PollRoomState()
        {
            bool inRoom = PhotonNetwork.InRoom;

            if (inRoom && !wasInRoom)
            {
                photonRoomId = PhotonNetwork.CurrentRoom?.Name ?? "";
                photonRegion = PhotonNetwork.CloudRegion ?? "";
                roomJoinTime = DateTime.UtcNow;
                IdentifyLocalPlayer();
                playersIdentified = false;
                opponentSteamIdResolved = false;
                opponentRankChecked = false;
                opponentIsRanked = false;
                matchIsRanked = false;
                Plugin.Log.LogInfo($"[POLL] Joined room: {photonRoomId} (region: {photonRegion})");
            }

            if (!inRoom && wasInRoom)
            {
                // Accumulate session time for this opponent
                AccumulateSessionTime();

                if (isTracking && !gameOverReported)
                {
                    // Someone disconnected mid-match
                    int localRounds = localTeamId == 0 ? p1Rounds : p2Rounds;
                    int oppRounds = localTeamId == 0 ? p2Rounds : p1Rounds;
                    string matchType = matchIsRanked ? "RANKED" : "CASUAL";

                    if (localRounds >= 4)
                    {
                        // Local player had dominant lead \u2014 count as a win
                        Plugin.Log.LogInfo($"[POLL] === {matchType} DC Win === Opponent disconnected at {localRounds}-{oppRounds}");
                        int winnerTeam = localTeamId;
                        OnGameOver(winnerTeam);
                    }
                    else if (oppRounds >= 4)
                    {
                        // Opponent had dominant lead \u2014 count as a loss (we DC'd or opponent won)
                        Plugin.Log.LogInfo($"[POLL] === {matchType} DC Loss === Disconnected at {localRounds}-{oppRounds}");
                        int winnerTeam = localTeamId == 0 ? 1 : 0;
                        OnGameOver(winnerTeam);
                    }
                    else
                    {
                        // No clear winner \u2014 log as canceled, don't report
                        Plugin.Log.LogInfo($"[POLL] === {matchType} Canceled === Disconnect at {localRounds}-{oppRounds} (not counted)");
                        CompetitiveUI.ShowNotification("Match canceled (DC)", new Color(1f, 0.7f, 0.3f));
                    }
                }

                Plugin.Log.LogInfo("[POLL] Left room");
                ResetMatchState();
            }

            if (inRoom && !opponentSteamIdResolved)
            {
                TryResolveOpponent();
            }

            // Once we have the opponent's REAL Steam ID, check if they're ranked
            if (inRoom && opponentSteamIdResolved && !opponentRankChecked)
            {
                // Don't check photon_ placeholder IDs
                if (!opponentSteamId.StartsWith("photon_"))
                {
                    opponentRankChecked = true;
                    ApiClient.CheckOpponentRanked(opponentSteamId, (isRanked) =>
                    {
                        opponentIsRanked = isRanked;
                        matchIsRanked = Plugin.RankedEnabled.Value && opponentIsRanked;
                        Plugin.Log.LogInfo($"[POLL] Opponent ranked: {opponentIsRanked}, Match ranked: {matchIsRanked}");
                    });
                }
            }

            wasInRoom = inRoom;
        }

        /// <summary>
        /// Accumulates session time for the current opponent.
        /// Called on room leave AND after game over for real-time updates.
        /// </summary>
        private static void AccumulateSessionTime()
        {
            if (!string.IsNullOrEmpty(opponentDisplayName) && opponentDisplayName != "Opponent")
            {
                float minutes = (float)(DateTime.UtcNow - roomJoinTime).TotalMinutes;
                if (sessionTimeByOpponent.ContainsKey(opponentDisplayName))
                    sessionTimeByOpponent[opponentDisplayName] += minutes;
                else
                    sessionTimeByOpponent[opponentDisplayName] = minutes;

                // Reset join time so we don't double-count
                roomJoinTime = DateTime.UtcNow;
            }
        }

        // \u2500\u2500 Opponent identification \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void TryResolveOpponent()
        {
            try
            {
                Photon.Realtime.Player[] players = PhotonNetwork.PlayerList;
                if (players == null) return;

                foreach (var player in players)
                {
                    if (player == null || player.IsLocal) continue;

                    opponentDisplayName = StripRichText(player.NickName ?? "Opponent");

                    var props = player.CustomProperties;
                    if (props != null && props.Count > 0)
                    {
                        if (props.ContainsKey("u_id"))
                        {
                            opponentSteamId = props["u_id"].ToString();
                            opponentSteamIdResolved = true;
                            Plugin.Log.LogInfo($"[POLL] Opponent: {opponentDisplayName} (Steam: {opponentSteamId})");
                            return;
                        }
                        if (props.ContainsKey("unity_id"))
                        {
                            opponentSteamId = props["unity_id"].ToString();
                            opponentSteamIdResolved = true;
                            Plugin.Log.LogInfo($"[POLL] Opponent: {opponentDisplayName} (Steam: {opponentSteamId})");
                            return;
                        }
                    }

                    if (!playersIdentified)
                    {
                        playersIdentified = true;
                        opponentSteamId = $"photon_{player.ActorNumber}";
                        Plugin.Log.LogInfo($"[POLL] Opponent found: {opponentDisplayName} (waiting for Steam ID...)");
                    }
                    return;
                }
            }
            catch { }
        }

        // \u2500\u2500 Local player / team \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void IdentifyLocalPlayer()
        {
            try
            {
                CSteamID steamId = SteamUser.GetSteamID();
                if (steamId.m_SteamID != 0)
                {
                    localSteamId = steamId.m_SteamID.ToString();
                    localDisplayName = StripRichText(SteamFriends.GetPersonaName());
                    return;
                }
            }
            catch { }

            try
            {
                localSteamId = PhotonNetwork.LocalPlayer?.UserId ?? "unknown";
                localDisplayName = StripRichText(PhotonNetwork.LocalPlayer?.NickName ?? "Unknown");
            }
            catch
            {
                localSteamId = "unknown";
                localDisplayName = "Unknown";
            }
        }

        private static void DetermineLocalTeam()
        {
            try
            {
                var localProps = PhotonNetwork.LocalPlayer?.CustomProperties;
                if (localProps != null && localProps.ContainsKey("t_id"))
                {
                    localTeamId = System.Convert.ToInt32(localProps["t_id"]);
                    Plugin.Log.LogInfo($"[POLL] Local team: {localTeamId} (from Photon t_id)");
                    return;
                }
            }
            catch { }

            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;

                foreach (var playerObj in pm.players)
                {
                    if (playerObj == null) continue;
                    var pv = playerObj.GetComponent<PhotonView>();
                    if (pv != null && pv.IsMine)
                    {
                        var charData = playerObj.GetComponent<CharacterData>();
                        if (charData != null)
                        {
                            var field = typeof(CharacterData).GetField("teamID",
                                BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
                            if (field != null)
                            {
                                localTeamId = (int)field.GetValue(charData);
                                Plugin.Log.LogInfo($"[POLL] Local team: {localTeamId} (from CharacterData)");
                                return;
                            }
                        }

                        for (int i = 0; i < pm.players.Count; i++)
                        {
                            var ipv = pm.players[i]?.GetComponent<PhotonView>();
                            if (ipv != null && ipv.IsMine)
                            {
                                localTeamId = i;
                                Plugin.Log.LogInfo($"[POLL] Local team: {localTeamId} (from index)");
                                return;
                            }
                        }
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[POLL] Team detection error: {ex.Message}");
            }
        }

        // \u2500\u2500 Match state polling \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void PollMatchState()
        {
            if (!PhotonNetwork.InRoom) return;

            var gm = GM_ArmsRace.instance;
            if (gm == null) return;

            if (!fieldsResolved)
            {
                ResolveFields(gm);
                if (!fieldsResolved) return;
            }

            int curP1Points = GetFieldInt(gm, f_p1Points);
            int curP2Points = GetFieldInt(gm, f_p2Points);
            int curP1Rounds = GetFieldInt(gm, f_p1Rounds);
            int curP2Rounds = GetFieldInt(gm, f_p2Rounds);

            bool gameActive = (curP1Rounds > 0 || curP2Rounds > 0 ||
                               curP1Points > 0 || curP2Points > 0);

            if (gameActive && !wasGameInProgress && !isTracking)
            {
                OnMatchStarted();
            }

            if (isTracking)
            {
                if (curP1Points != lastP1Points || curP2Points != lastP2Points)
                {
                    p1Points = curP1Points;
                    p2Points = curP2Points;
                }

                if (curP1Rounds != lastP1Rounds || curP2Rounds != lastP2Rounds)
                {
                    p1Rounds = curP1Rounds;
                    p2Rounds = curP2Rounds;
                    currentRound = p1Rounds + p2Rounds + 1;

                    if (curP1Rounds > lastP1Rounds)
                        Plugin.Log.LogInfo($"[POLL] Round: P1! Rounds: {p1Rounds}-{p2Rounds}");
                    if (curP2Rounds > lastP2Rounds)
                        Plugin.Log.LogInfo($"[POLL] Round: P2! Rounds: {p1Rounds}-{p2Rounds}");

                    if (!gameOverReported && (curP1Rounds >= roundsToWin || curP2Rounds >= roundsToWin))
                    {
                        int winnerTeam = curP1Rounds > curP2Rounds ? 0 : 1;
                        OnGameOver(winnerTeam);
                    }
                }
                // Track card picks
                PollCardPicks();
            }

            lastP1Points = curP1Points;
            lastP2Points = curP2Points;
            lastP1Rounds = curP1Rounds;
            lastP2Rounds = curP2Rounds;
            wasGameInProgress = gameActive;
        }

        // \u2500\u2500 Events \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void OnMatchStarted()
        {
            isTracking = true;
            gameOverReported = false;
            matchStartTime = DateTime.UtcNow;

            // Retry card rarity scan if it didn't work at startup
            if (CardRarityLookup.Count == 0)
            {
                try
                {
                    CardRarityLookup.ScanAll();
                }
                catch { }
            }

            p1Points = 0; p2Points = 0;
            p1Rounds = 0; p2Rounds = 0;
            currentRound = 1;
            localCards.Clear();
            opponentCards.Clear();
            lastKnownP1CardCount = 0;
            lastKnownP2CardCount = 0;
            pickCountThisMatch = 0;

            // Clear our broadcast for the new match
            broadcastCardNames.Clear();
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.LocalPlayer != null)
                {
                    var props = new Hashtable();
                    props[CARD_PROP_KEY] = "";
                    PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                }
            }
            catch { }

            // Recover pre-match card picks into localCards
            // These were captured by the log listener before tracking started
            if (preMatchCards.Count > 0)
            {
                Plugin.Log.LogInfo($"[POLL] Recovering {preMatchCards.Count} pre-match card(s)");
                foreach (var card in preMatchCards)
                {
                    pickCountThisMatch++;
                    card.PickOrder = pickCountThisMatch;
                    card.RoundNumber = 1;
                    localCards.Add(card);
                    broadcastCardNames.Add(card.CardName);
                    Plugin.Log.LogInfo($"[POLL] Card: Pre-match picked {card.CardName} [#{pickCountThisMatch}]");
                }

                // Broadcast recovered cards to opponent
                try
                {
                    if (PhotonNetwork.InRoom && PhotonNetwork.LocalPlayer != null)
                    {
                        string cardList = string.Join("|", broadcastCardNames.ToArray());
                        var props = new Hashtable();
                        props[CARD_PROP_KEY] = cardList;
                        PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                        Plugin.Log.LogInfo($"[POLL] Broadcast recovered cards: {cardList}");
                    }
                }
                catch { }
            }
            preMatchCards.Clear();
            preMatchPickCount = 0;

            // Recover pre-match opponent cards from Harmony hooks
            if (preMatchOpponentCards.Count > 0)
            {
                Plugin.Log.LogInfo($"[HARMONY-CARD] Recovering {preMatchOpponentCards.Count} pre-match opponent card(s)");
                foreach (var card in preMatchOpponentCards)
                {
                    card.RoundNumber = 1;
                    card.PickOrder = opponentCards.Count + 1;
                    opponentCards.Add(card);
                    opponentCardsViaHarmony = true;
                    Plugin.Log.LogInfo($"[HARMONY-CARD] Opp pre-match recovered: {card.CardName} [#{card.PickOrder}]");
                }
            }
            preMatchOpponentCards.Clear();

            // Snapshot opponent's current broadcast count so we ignore stale cards
            lastKnownOpponentBroadcastCount = 0;
            try
            {
                var players = PhotonNetwork.PlayerList;
                foreach (var p in players)
                {
                    if (p != null && !p.IsLocal && p.CustomProperties != null
                        && p.CustomProperties.ContainsKey(CARD_PROP_KEY))
                    {
                        string existing = p.CustomProperties[CARD_PROP_KEY].ToString();
                        if (!string.IsNullOrEmpty(existing))
                        {
                            lastKnownOpponentBroadcastCount = existing.Split('|').Length;
                            Plugin.Log.LogInfo($"[POLL] Ignoring {lastKnownOpponentBroadcastCount} stale opponent cards from previous match");
                        }
                        break;
                    }
                }
            }
            catch { }

            IdentifyLocalPlayer();
            TryResolveOpponent();
            DetermineLocalTeam();

            // Re-evaluate ranked status at match start
            matchIsRanked = Plugin.RankedEnabled.Value && opponentIsRanked;

            string matchType = matchIsRanked ? "RANKED" : "CASUAL";
            Plugin.Log.LogInfo($"[POLL] === {matchType} Match Started ===");
            Plugin.Log.LogInfo($"[POLL] Me: {localDisplayName} ({localSteamId}) team {localTeamId}");
            Plugin.Log.LogInfo($"[POLL] Opp: {opponentDisplayName} ({opponentSteamId}) oppRanked={opponentIsRanked}");
        }

        private static void OnGameOver(int winnerTeam)
        {
            if (!isTracking || gameOverReported) return;
            gameOverReported = true;
            sessionMatchCount++;

            if (!opponentSteamIdResolved)
                TryResolveOpponent();

            bool localWon = (winnerTeam == localTeamId);

            string matchType = matchIsRanked ? "RANKED" : "CASUAL";
            Plugin.Log.LogInfo($"[POLL] === {matchType} Match Over === Winner: team {winnerTeam}");
            Plugin.Log.LogInfo(localWon
                ? $"[POLL] YOU WON vs {opponentDisplayName}!"
                : $"[POLL] You lost to {opponentDisplayName}");
            Plugin.Log.LogInfo($"[POLL] Final: P1 {p1Rounds}r - P2 {p2Rounds}r");

            // \u2500\u2500 Update session W/L tracking \u2500\u2500
            string oppKey = opponentDisplayName ?? "Unknown";
            if (!sessionWLByOpponent.ContainsKey(oppKey))
                sessionWLByOpponent[oppKey] = new int[] { 0, 0, 0, 0 }; // [rW, rL, cW, cL]

            if (matchIsRanked)
            {
                if (localWon) sessionWLByOpponent[oppKey][0]++;
                else sessionWLByOpponent[oppKey][1]++;
            }
            else
            {
                if (localWon) sessionWLByOpponent[oppKey][2]++;
                else sessionWLByOpponent[oppKey][3]++;
            }

            if (matchIsRanked)
            {
                if (localWon) sessionRankedWins++; else sessionRankedLosses++;
            }
            else
            {
                if (localWon) sessionCasualWins++; else sessionCasualLosses++;
            }

            // Update session time immediately (not just on room leave)
            AccumulateSessionTime();

            LastResult = new MatchTracker.MatchResult
            {
                Won = localWon,
                MyRounds = localTeamId == 0 ? p1Rounds : p2Rounds,
                TheirRounds = localTeamId == 0 ? p2Rounds : p1Rounds,
                OpponentName = opponentDisplayName,
                Timestamp = DateTime.UtcNow,
            };
            HasPendingResult = true;

            string p1SteamId, p1Name, p2SteamId, p2Name;

            if (localTeamId == 0)
            {
                p1SteamId = localSteamId;
                p1Name = localDisplayName;
                p2SteamId = opponentSteamId;
                p2Name = opponentDisplayName;
            }
            else
            {
                p1SteamId = opponentSteamId;
                p1Name = opponentDisplayName;
                p2SteamId = localSteamId;
                p2Name = localDisplayName;
            }

            int duration = (int)(DateTime.UtcNow - matchStartTime).TotalSeconds;

            // When both players have the mod, only the player with the lower
            // Steam ID reports to avoid duplicates. When the opponent doesn't
            // have the mod, always report (only we can).
            bool shouldReport = true;
            if (opponentSteamIdResolved && !opponentSteamId.StartsWith("photon_"))
            {
                // Both have real Steam IDs \u2014 check if opponent has the mod
                // by looking for their cr_cards property (mod-only feature)
                bool opponentHasMod = false;
                try
                {
                    var players = PhotonNetwork.PlayerList;
                    foreach (var p in players)
                    {
                        if (p != null && !p.IsLocal && p.CustomProperties != null
                            && p.CustomProperties.ContainsKey(CARD_PROP_KEY))
                        {
                            opponentHasMod = true;
                            break;
                        }
                    }
                }
                catch { }

                if (opponentHasMod)
                {
                    // Both have mod \u2014 only lower Steam ID reports
                    long myId = 0, theirId = 0;
                    long.TryParse(localSteamId, out myId);
                    long.TryParse(opponentSteamId, out theirId);
                    shouldReport = (myId <= theirId);
                    if (!shouldReport)
                        Plugin.Log.LogInfo("[POLL] Opponent will report this match (lower Steam ID)");
                }
            }

            // Use consistent room ID (no per-PC timestamp, use round count instead)
            string reportRoomId = $"{photonRoomId}_{matchStartTime:HHmmss}_r{p1Rounds + p2Rounds}";

            if (shouldReport)
            {
                ApiClient.ReportMatch(
                    p1SteamId: p1SteamId,
                    p1Name: p1Name,
                    p2SteamId: p2SteamId,
                    p2Name: p2Name,
                    p1RoundsWon: p1Rounds,
                    p2RoundsWon: p2Rounds,
                    p1PointsTotal: p1Points,
                    p2PointsTotal: p2Points,
                    p1Cards: localTeamId == 0 ? localCards : opponentCards,
                    p2Cards: localTeamId == 0 ? opponentCards : localCards,
                    photonRoomId: reportRoomId,
                    region: photonRegion,
                    durationSeconds: duration,
                    startedAt: matchStartTime,
                    reporterSteamId: localSteamId,
                    isRanked: matchIsRanked
                );
            }

            isTracking = false;
            matchIsRanked = false; // Clear indicator immediately
        }

        // \u2500\u2500 Card tracking via CardBar \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        // \u2500\u2500 Card tracking via Unity log capture \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
        // The game logs "Picking Card: CardName(Clone)" for each pick.
        // We capture these via Application.logMessageReceived.

        private static bool logListenerRegistered = false;
        private static int pickCountThisMatch = 0;

        public static void RegisterLogListener()
        {
            if (logListenerRegistered) return;
            Application.logMessageReceived += OnUnityLog;
            logListenerRegistered = true;
            Plugin.Log.LogInfo("[POLL] Unity log listener registered for card tracking");
        }

        public static void UnregisterLogListener()
        {
            if (!logListenerRegistered) return;
            Application.logMessageReceived -= OnUnityLog;
            logListenerRegistered = false;
        }

        private static void OnUnityLog(string message, string stackTrace, LogType type)
        {
            if (type != LogType.Log) return;

            // The game logs "Picking Card: CardName(Clone)" only for the LOCAL player
            if (message.StartsWith("Picking Card: "))
            {
                string raw = message.Substring("Picking Card: ".Length);
                string cardName = ToTitleCase(raw.Replace("(Clone)", "").Trim());

                if (string.IsNullOrEmpty(cardName)) return;

                if (!isTracking)
                {
                    // Store for later \u2014 OnMatchStarted will recover these
                    preMatchPickCount++;
                    preMatchCards.Add(new MatchTracker.CardPickData
                    {
                        CardName = cardName,
                        CardRarity = CardRarityLookup.GetRarity(cardName),
                        PickOrder = preMatchPickCount,
                        RoundNumber = 1,
                    });
                    Plugin.Log.LogInfo($"[POLL] Card stored (pre-match): {cardName} [#{preMatchPickCount}]");
                    return;
                }

                pickCountThisMatch++;

                var pick = new MatchTracker.CardPickData
                {
                    CardName = cardName,
                    CardRarity = CardRarityLookup.GetRarity(cardName),
                    PickOrder = pickCountThisMatch,
                    RoundNumber = currentRound,
                };

                localCards.Add(pick);
                Plugin.Log.LogInfo($"[POLL] Card: Local picked {cardName} [#{pickCountThisMatch}]");

                // Broadcast to opponent via Photon custom properties
                BroadcastCardPick(cardName);
            }
        }

        /// <summary>
        /// Broadcasts the local player's card picks to the opponent via Photon custom properties.
        /// The property "cr_cards" stores a pipe-delimited list of all cards picked this match.
        /// </summary>
        private static void BroadcastCardPick(string cardName)
        {
            try
            {
                if (!PhotonNetwork.InRoom) return;

                broadcastCardNames.Add(cardName);
                string cardList = string.Join("|", broadcastCardNames.ToArray());

                var props = new Hashtable();
                props[CARD_PROP_KEY] = cardList;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);

                Plugin.Log.LogInfo($"[POLL] Broadcast cards: {cardList}");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[POLL] Card broadcast failed: {ex.Message}");
            }
        }

        /// <summary>
        /// Polls opponent's Photon custom properties for card picks they've broadcast.
        /// Only works when the opponent also has the mod installed.
        /// </summary>
        /// <summary>
        /// Called by the Harmony CardChoice hooks when the opponent picks a card.
        /// Works even when the opponent doesn't have the mod installed.
        /// </summary>
        public static void OnOpponentCardPicked(string cardName, string rarity)
        {
            cardName = ToTitleCase(cardName);

            if (!isTracking)
            {
                // Buffer for later recovery
                preMatchOpponentCards.Add(new MatchTracker.CardPickData
                {
                    CardName = cardName,
                    CardRarity = rarity,
                    PickOrder = preMatchOpponentCards.Count + 1,
                    RoundNumber = 1,
                });
                Plugin.Log.LogInfo($"[HARMONY-CARD] Opp card stored (pre-match): {cardName}");
                return;
            }

            opponentCardsViaHarmony = true;

            var pick = new MatchTracker.CardPickData
            {
                CardName = cardName,
                CardRarity = rarity,
                PickOrder = opponentCards.Count + 1,
                RoundNumber = currentRound,
            };

            opponentCards.Add(pick);
            Plugin.Log.LogInfo($"[HARMONY-CARD] Opp card added: {cardName} [#{pick.PickOrder}] (via Harmony)");
        }

        /// <summary>
        /// Polls opponent's Photon custom properties for card picks they've broadcast.
        /// Skipped when Harmony hook is providing opponent cards (preferred source).
        /// </summary>
        private static void PollCardPicks()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return;
                if (opponentCardsViaHarmony) return; // Harmony provides cards, skip Photon polling

                Photon.Realtime.Player[] players = PhotonNetwork.PlayerList;
                if (players == null) return;

                foreach (var player in players)
                {
                    if (player == null || player.IsLocal) continue;

                    var props = player.CustomProperties;
                    if (props == null || !props.ContainsKey(CARD_PROP_KEY)) continue;

                    string cardList = props[CARD_PROP_KEY].ToString();
                    if (string.IsNullOrEmpty(cardList)) continue;

                    string[] cards = cardList.Split('|');
                    int newCount = cards.Length;

                    // Detect opponent broadcast reset (they cleared for a new match)
                    // When count drops, opponent has restarted their card list
                    if (newCount < lastKnownOpponentBroadcastCount)
                    {
                        Plugin.Log.LogInfo($"[POLL] Opponent broadcast reset detected ({lastKnownOpponentBroadcastCount} -> {newCount}), re-syncing");
                        lastKnownOpponentBroadcastCount = 0;
                    }

                    if (newCount > lastKnownOpponentBroadcastCount)
                    {
                        // New cards from opponent
                        for (int i = lastKnownOpponentBroadcastCount; i < newCount; i++)
                        {
                            string cn = ToTitleCase(cards[i].Trim());
                            if (string.IsNullOrEmpty(cn)) continue;

                            var pick = new MatchTracker.CardPickData
                            {
                                CardName = cn,
                                CardRarity = CardRarityLookup.GetRarity(cn),
                                PickOrder = i + 1,
                                RoundNumber = currentRound,
                            };

                            opponentCards.Add(pick);
                            Plugin.Log.LogInfo($"[POLL] Card: Opp picked {cn} [via mod sync]");
                        }

                        lastKnownOpponentBroadcastCount = newCount;
                    }

                    return; // Only one opponent in 1v1
                }
            }
            catch { }
        }

        // \u2500\u2500 Helpers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        private static void ResolveFields(GM_ArmsRace gm)
        {
            try
            {
                var type = gm.GetType();
                var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
                f_p1Points = type.GetField("p1Points", flags);
                f_p2Points = type.GetField("p2Points", flags);
                f_p1Rounds = type.GetField("p1Rounds", flags);
                f_p2Rounds = type.GetField("p2Rounds", flags);

                // Find the rounds-to-win setting
                f_roundsToWinGame = type.GetField("roundsToWinGame", flags);
                if (f_roundsToWinGame == null)
                    f_roundsToWinGame = type.GetField("roundsToWin", flags);
                if (f_roundsToWinGame == null)
                    f_roundsToWinGame = type.GetField("m_roundsToWinGame", flags);

                if (f_roundsToWinGame != null)
                {
                    roundsToWin = GetFieldInt(gm, f_roundsToWinGame);
                    if (roundsToWin <= 0) roundsToWin = 5;
                    Plugin.Log.LogInfo($"[POLL] Rounds to win: {roundsToWin}");
                }
                else
                {
                    roundsToWin = 5;
                    Plugin.Log.LogInfo($"[POLL] roundsToWinGame field not found, defaulting to {roundsToWin}");
                }

                if (f_p1Points != null && f_p1Rounds != null)
                {
                    fieldsResolved = true;
                    Plugin.Log.LogInfo("[POLL] GM_ArmsRace fields resolved");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[POLL] Field resolution failed: {ex.Message}");
            }
        }

        private static int GetFieldInt(object obj, FieldInfo field)
        {
            if (field == null || obj == null) return 0;
            try { return (int)field.GetValue(obj); }
            catch { return 0; }
        }

        private static string StripRichText(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            return Regex.Replace(input, "<.*?>", "").Trim();
        }

        private static string ToTitleCase(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            // Convert "POISON BULLETS" or "poison bullets" to "Poison Bullets"
            var words = input.ToLower().Split(' ');
            for (int i = 0; i < words.Length; i++)
            {
                if (words[i].Length > 0)
                    words[i] = char.ToUpper(words[i][0]) + words[i].Substring(1);
            }
            return string.Join(" ", words);
        }

        private static void ResetMatchState()
        {
            isTracking = false;
            gameOverReported = false;
            wasGameInProgress = false;
            p1Points = 0; p2Points = 0;
            p1Rounds = 0; p2Rounds = 0;
            lastP1Points = 0; lastP2Points = 0;
            lastP1Rounds = 0; lastP2Rounds = 0;
            currentRound = 1;
            localTeamId = -1;
            playersIdentified = false;
            opponentSteamIdResolved = false;
            opponentRankChecked = false;
            opponentIsRanked = false;
            matchIsRanked = false;
            localCards.Clear();
            opponentCards.Clear();
            lastKnownP1CardCount = 0;
            lastKnownP2CardCount = 0;
            pickCountThisMatch = 0;
            broadcastCardNames.Clear();
            lastKnownOpponentBroadcastCount = 0;
            preMatchCards.Clear();
            preMatchPickCount = 0;
            opponentCardsViaHarmony = false;
            preMatchOpponentCards.Clear();
            fieldsResolved = false;

            // Clear our card broadcast when leaving room
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.LocalPlayer != null)
                {
                    var props = new Hashtable();
                    props[CARD_PROP_KEY] = "";
                    PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                }
            }
            catch { }
        }

        // \u2500\u2500 Public accessors \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        public static bool IsInMatch => isTracking;
        public static bool IsInRoom => wasInRoom;
        public static string LocalSteamId => localSteamId;
        public static string LocalDisplayName => localDisplayName;
        public static string OpponentDisplayName => opponentDisplayName;
        public static int P1Rounds => p1Rounds;
        public static int P2Rounds => p2Rounds;
        public static int P1Points => p1Points;
        public static int P2Points => p2Points;
        public static int LocalTeamId => localTeamId;
    }
}
