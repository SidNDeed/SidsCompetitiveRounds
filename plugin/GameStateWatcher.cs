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
        // Pick-phase color apply latch. Fires once per room as soon as both player
        // GOs exist, so body colors render during the very first pick phase (before
        // OnMatchStarted, which only triggers once combat begins).
        private static bool pcolorRoomApplied = false;
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
        // Time of the last /mod/check call. We keep re-checking every ~5s while
        // in the room with a not-yet-ranked-but-modded opponent — handles the
        // race where the opponent's mod hasn't finished posting their initial
        // /toggle-ranked sync by the time we asked. Without retries, two new
        // mod users meeting for the first time get a permanent casual flag for
        // the whole room session.
        private static float lastOpponentRankCheck = -999f;
        // Pre-flight latch: once per room, when matchIsRanked first goes true
        // AND we don't already have a queue-issued series_id, ask the server
        // to create the ranked_series row. Surfaces non-queue (private room)
        // ranked matches in /series/active immediately rather than after the
        // first match completes.
        private static bool seriesPreflightSent = false;
        // (#26) Opponent-never-arrived watchdog state (ranked_* rooms only).
        private static bool rankedRoomStallHandled = false;
        private static bool rankedRoomStallWarned = false;
        private static bool rankedRoomEverFull = false;
        private static bool matchIsRanked = false;

        // Harmony opponent card tracking
        private static bool opponentCardsViaHarmony = false;
        private static List<MatchTracker.CardPickData> preMatchOpponentCards = new List<MatchTracker.CardPickData>();

        // Card tracking
        private static List<MatchTracker.CardPickData> localCards = new List<MatchTracker.CardPickData>();
        private static List<MatchTracker.CardPickData> opponentCards = new List<MatchTracker.CardPickData>();

        // Pass-tracking: cards offered to the LOCAL player. Opponent's offers come from
        // their own mod report, so we never populate opponentOffers.
        private static List<MatchTracker.CardOfferData> localOffers = new List<MatchTracker.CardOfferData>();
        private static readonly List<MatchTracker.CardOfferData> emptyOffers = new List<MatchTracker.CardOfferData>();
        private static int lastKnownP1CardCount = 0;
        private static int lastKnownP2CardCount = 0;

        // Card sharing via Photon custom properties
        private static List<string> broadcastCardNames = new List<string>();
        private static int lastKnownOpponentBroadcastCount = 0;
        private const string CARD_PROP_KEY = "cr_cards";

        // FPS sampling (v1.25). TickFrame() runs every Unity frame while a match is
        // being tracked; LocalAvgFps = frame_count / wall_seconds at any point.
        // Periodically broadcast via Photon custom prop so the opponent can read ours.
        // Display-only — never feeds Glicko / anti-cheat / matchmaking.
        private const string FPS_PROP_KEY = "cr_fps";
        private static int fpsFrameCount = 0;
        private static float fpsTimeAccum = 0f;
        private static float fpsBroadcastTimer = 0f;
        private static int opponentAvgFps = 0;
        public static int LocalAvgFps => fpsTimeAccum > 0.5f
            ? (int)Math.Round(fpsFrameCount / (double)fpsTimeAccum)
            : 0;
        public static int OpponentAvgFps => opponentAvgFps;

        // Pre-match card picks (cards picked before isTracking = true)
        // These get moved into localCards when OnMatchStarted fires
        private static List<MatchTracker.CardPickData> preMatchCards = new List<MatchTracker.CardPickData>();
        private static int preMatchPickCount = 0;

        // Room info
        private static string photonRoomId = "";
        private static string photonRegion = "";

        // Game over
        private static bool gameOverReported = false;

        // Opponent disconnect detection
        private static bool opponentWasPresent = false;
        private static bool opponentDCReported = false;

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
        // Session SERIES tally — distinct from match wins/losses above. A
        // BO3 series can include 2-3 matches; only the deciding match flips
        // these counters. Incremented from ApiClient.ReportMatch's success
        // callback when the server response carries series_status='completed'.
        private static int sessionRankedSeriesWins = 0;
        private static int sessionRankedSeriesLosses = 0;
        // Current BO3 series score, tracked locally off OnGameOver events so
        // the in-match HUD doesn't depend on a stale /series/active cache.
        // Reset on room change (new series), and at series-completion when
        // the report-match callback bumps the session series tally.
        private static int currentSeriesGamesWon = 0;
        private static int currentSeriesGamesLost = 0;
        private static int sessionCasualWins = 0;
        private static int sessionCasualLosses = 0;
        // 2v2 series tally for the in-mod Session Info panel. Incremented from
        // the team-match report success callback when series_status=='completed'.
        private static int sessionTeamSeriesWins = 0;
        private static int sessionTeamSeriesLosses = 0;

        // Achievement tracking within current match
        private static bool achTookDamage = false;       // health ever < MaxHealth during a round
        private static bool achPhoenixUsed = false;       // remainingRespawns < respawns detected
        private static bool achDied = false;              // data.dead became true (actual death)
        private static int achMaxOpponentRounds = 0;      // highest round count opponent reached (for comeback)
        private static bool achWasDown04 = false;         // opponent had 4 rounds while local had 0
        private static bool lastDeadState = false;
        private static int lastRemainingRespawns = -1;
        private static bool achFiredShot = false;         // left mouse clicked during match
        private static bool achMoved = false;              // WASD or Space pressed during match
        // Anti-cheat: per-match counts of the LOCAL player's combat inputs. Sent in the match report
        // so the server can flag a reporter who just sat idle the whole match (botting / AFK farming).
        // Counters reset in OnMatchStarted alongside the achievement flags.
        public static int LocalShotsThisMatch { get; private set; }
        public static int LocalBlocksThisMatch { get; private set; }
        // v1.29 — input-rate metrics for the Compare tab ("avg keystrokes/sec").
        // Keys = discrete anyKeyDown events during active combat (movement, shots,
        // blocks — anything). Seconds = wall time actually spent alive in combat
        // (pick phase / death / menus excluded), so the ratio is a true in-game
        // input rate. Reset with the other per-match counters.
        public static int LocalKeysThisMatch { get; private set; }
        public static float LocalActiveSecondsThisMatch { get; private set; }
        // v1.23 — hit/block lifetime counters.
        //   bullets_fired  — sum of Gun.numberOfProjectiles across every Gun.Attack call by the
        //                    local player (counts individual pellets/bullets, not trigger pulls;
        //                    auto-fire weapons firing 20 rounds count 20, not 1)
        //   bullets_hit    — damage events dealt to an opposing player by a real projectile
        //                    (damagingWeapon has a ProjectileHit component — excludes DOT ticks,
        //                    explosion splash, card-effect damage). Bounded per match by the
        //                    _hitsRemaining gate so bullets_hit ≤ bullets_fired always.
        //   blocks_activated  — alias of LocalBlocksThisMatch (right-click count)
        //   blocks_successful — Harmony Block.DoBlock → block animations that actually fired
        public static int LocalBulletsFiredThisMatch { get; private set; }
        public static int LocalBulletsHitThisMatch { get; private set; }
        public static int LocalBlocksActivatedThisMatch { get; private set; }
        public static int LocalBlocksSuccessfulThisMatch { get; private set; }

        // First-fire-per-match log lines let us confirm Harmony patches attach and fire without
        // spamming on every event. Reset in OnMatchStarted alongside the counters.
        private static bool _loggedFirstFire, _loggedFirstHit, _loggedFirstBlockAct, _loggedFirstBlockOk;

        // Block.DoBlock fires every time the block absorbs a projectile AND when the block
        // extends (ROUNDS' block gets duration bumps per absorb). Without dedup, this
        // produces >100% "success rate" in card-heavy matches. A 1.0s cooldown between
        // credited successes captures "this activation window absorbed at least one bullet"
        // which matches user-facing semantics. Block cooldown in ROUNDS is ~1.5s by default
        // so successive activations can't realistically happen inside the dedup window.
        private static float _lastBlockSuccessTime = -999f;

        // Per-projectile hit gating. Previous binary gate "arm on click, consume on first hit"
        // produced 1 hit max per trigger-pull, which undercounts shotguns (5 pellets hitting
        // = 5 real hits but we'd count 1). Switch to a counter: Gun.Attack Postfix adds N to
        // _hitsRemaining where N is numberOfProjectiles, then each filtered bullet-impact on
        // an enemy decrements. Bounds bullets_hit ≤ bullets_fired naturally without drops on
        // multi-projectile weapons.
        private static int _hitsRemaining;

        public static void OnLocalBulletFired(int projectiles)
        {
            if (!isTracking || inPickPhase) return;
            if (projectiles < 1) projectiles = 1;
            LocalBulletsFiredThisMatch += projectiles;
            _hitsRemaining += projectiles;
            if (!_loggedFirstFire) { _loggedFirstFire = true; Plugin.Log.LogInfo($"[STATS] first bullet fired this match (projectiles={projectiles})"); }
        }

        public static void OnLocalBulletHit()
        {
            if (!isTracking || inPickPhase) return;
            if (_hitsRemaining <= 0) return;  // more damage events than projectiles (splash/DOT) — skip
            _hitsRemaining--;
            LocalBulletsHitThisMatch++;
            if (!_loggedFirstHit) { _loggedFirstHit = true; Plugin.Log.LogInfo("[STATS] first bullet-hit this match"); }
        }
        // Debug-visible signals for the Block % investigation overlay. Populated
        // unconditionally during a tracked match; CompetitiveUI reads them to flash
        // the corner panel. Remove once the block% stat is trusted.
        public static int LocalBlockRawAbsorbs { get; private set; }   // every DoBlock fire, pre-dedup
        public static int LocalBlockDedupeDrops { get; private set; }  // DoBlock events rejected by the 1.0s dedup
        public static float LastBlockActivatedTime { get; private set; } = -999f;
        public static float LastBlockSuccessfulTime { get; private set; } = -999f;
        public static float LastBlockAbsorbTime { get; private set; } = -999f;
        public static float LastLocalHitTime { get; private set; } = -999f;
        public static float LastBlockMissTime { get; private set; } = -999f;  // when overlay should flash red
        public static string LastBlockEventLabel { get; private set; } = "";
        // ROUNDS block window — empirically ~0.5s active. Tuned from observation; tweak
        // if "too early" feedback fires when it shouldn't. Only affects the overlay
        // classification, never the actual success count.
        private const float BLOCK_ACTIVE_WINDOW = 0.5f;

        public static void OnLocalBlockActivated()
        {
            if (!isTracking || inPickPhase) return;
            LocalBlocksActivatedThisMatch++;
            LastBlockActivatedTime = Time.time;
            // Retro-classify: did this activation happen right AFTER a hit? That's the
            // "too slow" case. Under 250ms after a hit is human reaction-time territory
            // — they panic-blocked after seeing the bullet connect.
            float sinceHit = Time.time - LastLocalHitTime;
            if (sinceHit >= 0 && sinceHit < 0.25f)
            {
                LastBlockMissTime = Time.time;
                LastBlockEventLabel = $"TOO SLOW (block +{sinceHit*1000:F0}ms after hit)";
                Plugin.Log.LogInfo($"[BLOCK-DBG] TOO-SLOW   act={LocalBlocksActivatedThisMatch}  hit_to_block={sinceHit*1000:F0}ms");
            }
            else
            {
                LastBlockEventLabel = $"ACTIVATED #{LocalBlocksActivatedThisMatch}";
                Plugin.Log.LogInfo($"[BLOCK-DBG] ACTIVATED  act={LocalBlocksActivatedThisMatch}  succ={LocalBlocksSuccessfulThisMatch}/{LocalBlockRawAbsorbs}");
            }
            if (!_loggedFirstBlockAct) { _loggedFirstBlockAct = true; Plugin.Log.LogInfo("[STATS] first block activation this match"); }
        }

        /// <summary>Called when the local player takes damage. Classifies the hit against
        /// the most-recent block activation time so the overlay can tell the user whether
        /// their block was too early (window ended) or no-block-at-all.
        /// Too-slow is detected asymmetrically in OnLocalBlockActivated (activation after hit).</summary>
        public static void OnLocalPlayerHit(float damage)
        {
            if (!isTracking || inPickPhase) return;
            LastLocalHitTime = Time.time;
            LastBlockMissTime = Time.time;
            float sinceAct = Time.time - LastBlockActivatedTime;
            // sinceAct == +∞ → no block activation this match yet (< 0 impossible since act is always past).
            if (sinceAct > 0 && sinceAct < BLOCK_ACTIVE_WINDOW)
            {
                // Activated before hit, within window — but the block still didn't absorb.
                // Likely card-specific unblockable damage (e.g. Poison tick, Lifesteal pen).
                LastBlockEventLabel = $"HIT (block active, {sinceAct*1000:F0}ms in) — unblockable?";
                Plugin.Log.LogInfo($"[BLOCK-DBG] HIT-ACTIVE act={LocalBlocksActivatedThisMatch} since_act={sinceAct*1000:F0}ms dmg={damage:F1}");
            }
            else if (sinceAct > BLOCK_ACTIVE_WINDOW && sinceAct < 2.0f)
            {
                LastBlockEventLabel = $"TOO EARLY (blocked {sinceAct*1000:F0}ms before hit)";
                Plugin.Log.LogInfo($"[BLOCK-DBG] TOO-EARLY  since_act={sinceAct*1000:F0}ms dmg={damage:F1}");
            }
            else
            {
                LastBlockEventLabel = $"HIT (no recent block)";
                Plugin.Log.LogInfo($"[BLOCK-DBG] HIT-NOBLK  since_act={sinceAct:F1}s dmg={damage:F1}");
            }
        }
        public static void OnLocalBlockSuccessful()
        {
            if (!isTracking || inPickPhase) return;
            LocalBlockRawAbsorbs++;
            LastBlockAbsorbTime = Time.time;
            float timeSincePrev = Time.time - _lastBlockSuccessTime;
            if (timeSincePrev < 1.0f)
            {
                LocalBlockDedupeDrops++;
                LastBlockEventLabel = $"ABSORB (deduped, +{timeSincePrev:F2}s)";
                Plugin.Log.LogInfo($"[BLOCK-DBG] ABSORB-DEDUP  raw={LocalBlockRawAbsorbs}  since_last_credit={timeSincePrev:F2}s  credited={LocalBlocksSuccessfulThisMatch}");
                return;
            }
            _lastBlockSuccessTime = Time.time;
            LocalBlocksSuccessfulThisMatch++;
            LastBlockSuccessfulTime = Time.time;
            LastBlockEventLabel = $"SUCCESSFUL #{LocalBlocksSuccessfulThisMatch}";
            Plugin.Log.LogInfo($"[BLOCK-DBG] SUCCESS    act={LocalBlocksActivatedThisMatch}  succ={LocalBlocksSuccessfulThisMatch}  raw={LocalBlockRawAbsorbs}  drops={LocalBlockDedupeDrops}");
            if (!_loggedFirstBlockOk) { _loggedFirstBlockOk = true; Plugin.Log.LogInfo("[STATS] first successful block this match"); }
        }
        // Pick-phase gate: input gating must exclude card-pick UI (Space jump, A/D carousel,
        // mouse click on cards) which would otherwise count as movement / firing.
        // Set true on "PICK PHASE" log; cleared on "MOVE PLAYERS END" (combat about to begin)
        // or any round-end marker. CharacterData often reports !dead && health>0 during pick.
        private static bool inPickPhase = false;

        // Sid's Steam ID for "Regicide" achievement
        private const string SID_STEAM_ID = "76561198040410653";

        // Public state
        public static MatchTracker.MatchResult LastResult { get; private set; }
        public static bool HasPendingResult { get; private set; } = false;
        public static bool MatchIsRanked => matchIsRanked;
        public static int LastP1Points => p1Points;
        public static int LastP2Points => p2Points;

        // Session accessors
        public static Dictionary<string, float> SessionTimeByOpponent => sessionTimeByOpponent;
        public static Dictionary<string, int[]> SessionWLByOpponent => sessionWLByOpponent;
        public static int SessionMatchCount => sessionMatchCount;
        public static int SessionRankedWins => sessionRankedWins;
        public static int SessionRankedLosses => sessionRankedLosses;
        public static int SessionRankedSeriesWins => sessionRankedSeriesWins;
        public static int SessionRankedSeriesLosses => sessionRankedSeriesLosses;
        public static int CurrentSeriesGamesWon => currentSeriesGamesWon;
        public static int CurrentSeriesGamesLost => currentSeriesGamesLost;
        public static void IncrementSessionRankedSeries(bool won)
        {
            if (won) sessionRankedSeriesWins++; else sessionRankedSeriesLosses++;
            // Series ended -> reset the per-series game counter so the next
            // BO3 starts at 0-0 in the HUD.
            currentSeriesGamesWon = 0;
            currentSeriesGamesLost = 0;
            Plugin.Log.LogInfo($"[SESSION] Ranked series tally: {sessionRankedSeriesWins}-{sessionRankedSeriesLosses}; current series counters reset");
            SaveSessionState();
        }
        public static void ResetCurrentSeriesScore()
        {
            currentSeriesGamesWon = 0;
            currentSeriesGamesLost = 0;
        }
        /// <summary>Adopt a resumed BO3's tally from the server (preflight
        /// "exists" response after a DC + reconnect, #33) so the HUD picks up
        /// at the real score instead of 0-0.</summary>
        public static void AdoptSeriesScore(int myWins, int oppWins)
        {
            currentSeriesGamesWon = Mathf.Max(0, myWins);
            currentSeriesGamesLost = Mathf.Max(0, oppWins);
            Plugin.Log.LogInfo($"[SESSION] Adopted resumed series score {currentSeriesGamesWon}-{currentSeriesGamesLost} from preflight");
        }
        /// <summary>v1.29 (#42): the server refused a ranked series for this
        /// pairing (one side has ranked explicitly disabled). Flip the match
        /// to casual so the HUD and the eventual match report agree with the
        /// server-side enforcement — no bets, no series, no rating.</summary>
        public static void DowngradeToCasual(string reason)
        {
            if (!matchIsRanked) return;
            matchIsRanked = false;
            Plugin.Log.LogInfo($"[POLL] Match downgraded to CASUAL ({reason})");
            try
            {
                CompetitiveUI.QueueNotification("Casual match — a player has ranked disabled",
                    new Color(0.85f, 0.8f, 0.5f), 4f);
            }
            catch { }
        }
        public static int SessionCasualWins => sessionCasualWins;
        public static int SessionCasualLosses => sessionCasualLosses;
        public static int SessionTeamSeriesWins => sessionTeamSeriesWins;
        public static int SessionTeamSeriesLosses => sessionTeamSeriesLosses;
        public static void RecordSessionTeamSeries(bool won)
        {
            if (won) sessionTeamSeriesWins++;
            else sessionTeamSeriesLosses++;
            SaveSessionState();
        }
        public static DateTime SessionStartTime => sessionStartTime;

        // Session persistence (v1.26.7). Counters survive game restarts; reset
        // only when the gap between SaveSession() calls exceeds SESSION_INACTIVITY_HOURS,
        // so a player who quits, restarts, and comes back within the window keeps
        // their session intact. Stored via PlayerPrefs (per-user, per-machine).
        private const double SESSION_INACTIVITY_HOURS = 3.0;
        private const string PP_SESSION_LAST_ACTIVITY = "cr_session_last_activity_unix";
        private const string PP_SESSION_START         = "cr_session_start_unix";
        private const string PP_SESSION_MATCHES       = "cr_session_match_count";
        private const string PP_SESSION_RW            = "cr_session_ranked_wins";
        private const string PP_SESSION_RL            = "cr_session_ranked_losses";
        private const string PP_SESSION_CW            = "cr_session_casual_wins";
        private const string PP_SESSION_CL            = "cr_session_casual_losses";
        private const string PP_SESSION_RSW           = "cr_session_rseries_wins";
        private const string PP_SESSION_RSL           = "cr_session_rseries_losses";
        private const string PP_SESSION_T2W           = "cr_session_tseries_wins";
        private const string PP_SESSION_T2L           = "cr_session_tseries_losses";
        private const string PP_SESSION_WL_BY_OPP     = "cr_session_wl_by_opp";
        private const string PP_SESSION_TIME_BY_OPP   = "cr_session_time_by_opp";

        private static long _DtToUnix(DateTime utc)
        {
            var epoch = new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc);
            return (long)(utc.ToUniversalTime() - epoch).TotalSeconds;
        }
        private static DateTime _UnixToDt(long secs)
        {
            return new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc).AddSeconds(secs);
        }

        public static void SaveSessionState()
        {
            try
            {
                PlayerPrefs.SetString(PP_SESSION_LAST_ACTIVITY, _DtToUnix(DateTime.UtcNow).ToString());
                PlayerPrefs.SetString(PP_SESSION_START, _DtToUnix(sessionStartTime).ToString());
                PlayerPrefs.SetInt(PP_SESSION_MATCHES, sessionMatchCount);
                PlayerPrefs.SetInt(PP_SESSION_RW, sessionRankedWins);
                PlayerPrefs.SetInt(PP_SESSION_RL, sessionRankedLosses);
                PlayerPrefs.SetInt(PP_SESSION_CW, sessionCasualWins);
                PlayerPrefs.SetInt(PP_SESSION_CL, sessionCasualLosses);
                PlayerPrefs.SetInt(PP_SESSION_RSW, sessionRankedSeriesWins);
                PlayerPrefs.SetInt(PP_SESSION_RSL, sessionRankedSeriesLosses);
                PlayerPrefs.SetInt(PP_SESSION_T2W, sessionTeamSeriesWins);
                PlayerPrefs.SetInt(PP_SESSION_T2L, sessionTeamSeriesLosses);
                // Encode WL dict: "name1=rW,rL,cW,cL|name2=rW,rL,cW,cL|..."
                // Replace | = , in display names with safe placeholders before joining.
                var sbWl = new System.Text.StringBuilder();
                bool firstWl = true;
                foreach (var kv in sessionWLByOpponent)
                {
                    if (kv.Value == null || kv.Value.Length < 4) continue;
                    string name = (kv.Key ?? "").Replace("|", "/").Replace("=", "-").Replace(",", ".");
                    if (!firstWl) sbWl.Append('|');
                    sbWl.Append(name).Append('=')
                        .Append(kv.Value[0]).Append(',')
                        .Append(kv.Value[1]).Append(',')
                        .Append(kv.Value[2]).Append(',')
                        .Append(kv.Value[3]);
                    firstWl = false;
                }
                PlayerPrefs.SetString(PP_SESSION_WL_BY_OPP, sbWl.ToString());
                var sbT = new System.Text.StringBuilder();
                bool firstT = true;
                foreach (var kv in sessionTimeByOpponent)
                {
                    string name = (kv.Key ?? "").Replace("|", "/").Replace("=", "-");
                    if (!firstT) sbT.Append('|');
                    sbT.Append(name).Append('=').Append(kv.Value.ToString("F2", System.Globalization.CultureInfo.InvariantCulture));
                    firstT = false;
                }
                PlayerPrefs.SetString(PP_SESSION_TIME_BY_OPP, sbT.ToString());
                PlayerPrefs.Save();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[SESSION] save failed: {ex.Message}"); }
        }

        private static void LoadSessionStateOrReset()
        {
            try
            {
                string lastStr = PlayerPrefs.GetString(PP_SESSION_LAST_ACTIVITY, "");
                if (string.IsNullOrEmpty(lastStr))
                {
                    sessionStartTime = DateTime.UtcNow;
                    Plugin.Log.LogInfo("[SESSION] no prior session - starting fresh");
                    return;
                }
                if (!long.TryParse(lastStr, out long lastUnix))
                {
                    sessionStartTime = DateTime.UtcNow;
                    return;
                }
                DateTime lastActivity = _UnixToDt(lastUnix);
                double idleHours = (DateTime.UtcNow - lastActivity).TotalHours;
                if (idleHours > SESSION_INACTIVITY_HOURS || idleHours < 0)
                {
                    sessionStartTime = DateTime.UtcNow;
                    Plugin.Log.LogInfo($"[SESSION] last activity {idleHours:F1}h ago (>{SESSION_INACTIVITY_HOURS}h) - starting fresh");
                    return;
                }
                long startUnix = long.Parse(PlayerPrefs.GetString(PP_SESSION_START, lastUnix.ToString()));
                sessionStartTime = _UnixToDt(startUnix);
                sessionMatchCount        = PlayerPrefs.GetInt(PP_SESSION_MATCHES, 0);
                sessionRankedWins        = PlayerPrefs.GetInt(PP_SESSION_RW, 0);
                sessionRankedLosses      = PlayerPrefs.GetInt(PP_SESSION_RL, 0);
                sessionCasualWins        = PlayerPrefs.GetInt(PP_SESSION_CW, 0);
                sessionCasualLosses      = PlayerPrefs.GetInt(PP_SESSION_CL, 0);
                sessionRankedSeriesWins  = PlayerPrefs.GetInt(PP_SESSION_RSW, 0);
                sessionRankedSeriesLosses= PlayerPrefs.GetInt(PP_SESSION_RSL, 0);
                sessionTeamSeriesWins    = PlayerPrefs.GetInt(PP_SESSION_T2W, 0);
                sessionTeamSeriesLosses  = PlayerPrefs.GetInt(PP_SESSION_T2L, 0);
                sessionWLByOpponent.Clear();
                foreach (var entry in (PlayerPrefs.GetString(PP_SESSION_WL_BY_OPP, "") ?? "").Split('|'))
                {
                    if (string.IsNullOrEmpty(entry)) continue;
                    int eq = entry.IndexOf('=');
                    if (eq <= 0) continue;
                    string name = entry.Substring(0, eq);
                    var parts = entry.Substring(eq + 1).Split(',');
                    if (parts.Length != 4) continue;
                    if (int.TryParse(parts[0], out int rw) && int.TryParse(parts[1], out int rl)
                        && int.TryParse(parts[2], out int cw) && int.TryParse(parts[3], out int cl))
                    {
                        sessionWLByOpponent[name] = new int[] { rw, rl, cw, cl };
                    }
                }
                sessionTimeByOpponent.Clear();
                foreach (var entry in (PlayerPrefs.GetString(PP_SESSION_TIME_BY_OPP, "") ?? "").Split('|'))
                {
                    if (string.IsNullOrEmpty(entry)) continue;
                    int eq = entry.IndexOf('=');
                    if (eq <= 0) continue;
                    string name = entry.Substring(0, eq);
                    if (float.TryParse(entry.Substring(eq + 1), System.Globalization.NumberStyles.Float,
                                       System.Globalization.CultureInfo.InvariantCulture, out float mins))
                        sessionTimeByOpponent[name] = mins;
                }
                Plugin.Log.LogInfo($"[SESSION] restored prior session ({idleHours:F1}h since last activity): " +
                                   $"{sessionMatchCount} games, {sessionRankedWins}-{sessionRankedLosses}R / {sessionCasualWins}-{sessionCasualLosses}C, " +
                                   $"{sessionWLByOpponent.Count} opponents");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[SESSION] load failed: {ex.Message} - starting fresh");
                sessionStartTime = DateTime.UtcNow;
            }
        }

        // Initialization

        public static void Initialize()
        {
            LoadSessionStateOrReset();
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

        /// <summary>Per-Unity-frame tick; counts frames + accumulates real time so we
        /// can report a true average FPS for this match. Cheap (no allocations, no
        /// reflection); also broadcasts the running average via Photon every ~3s so
        /// the opponent can read it. Only active while a match is being tracked.</summary>
        public static void TickFrame()
        {
            if (!isTracking) return;
            float dt = Time.unscaledDeltaTime;
            if (dt <= 0f || dt > 1f) return; // skip pause / first-frame outliers
            fpsFrameCount++;
            fpsTimeAccum += dt;
            fpsBroadcastTimer += dt;
            if (fpsBroadcastTimer >= 3f)
            {
                fpsBroadcastTimer = 0f;
                BroadcastFps();
                PollOpponentFps();
            }
        }

        private static void BroadcastFps()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.LocalPlayer == null) return;
                int avg = LocalAvgFps;
                if (avg <= 0) return;
                var props = new Hashtable();
                props[FPS_PROP_KEY] = avg;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
            }
            catch { }
        }

        private static void PollOpponentFps()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return;
                var players = PhotonNetwork.PlayerList;
                if (players == null) return;
                foreach (var p in players)
                {
                    if (p == null || p.IsLocal || p.CustomProperties == null) continue;
                    if (!p.CustomProperties.ContainsKey(FPS_PROP_KEY)) continue;
                    try { opponentAvgFps = Convert.ToInt32(p.CustomProperties[FPS_PROP_KEY]); }
                    catch { }
                    return; // first non-local mod-reporting peer wins; 1v1 only has one
                }
            }
            catch { }
        }

        // \u2500\u2500 Room state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500

        // Vanilla matchmaking freeze watchdog (v1.26.8).
        // Symptom (reported by Stan + others, ~10-15% of vanilla queue joins):
        // after vanilla matches you with someone, the ready-up screen freezes —
        // spacebar doesn't register, sometimes alt+F4 is the only way out.
        // Suspected root cause: Unity's input system silently dropping events
        // when the window isn't focused (Application.runInBackground=false).
        //
        // Fix: while in any Photon room, force runInBackground=true so Unity
        // keeps processing input/network events even when the player tabbed
        // away. Restored to whatever vanilla had set on room leave.
        //
        // Belt-and-suspenders: after 20s of being in a non-mod-issued room
        // with no match started, surface an IMGUI overlay (rendered by
        // CompetitiveUI) with a "Force exit room" button so the player
        // never needs alt+F4 to recover.
        private static bool _runInBackgroundOverridden = false;
        private static bool _origRunInBackground = false;
        private static DateTime _stuckOverlayDismissedAt = DateTime.MinValue;
        public static bool ShouldShowMatchFoundStuckOverlay { get; private set; }
        public static int SecondsInUnstartedRoom { get; private set; }
        public static void DismissMatchFoundStuckOverlay()
        {
            _stuckOverlayDismissedAt = DateTime.UtcNow;
            ShouldShowMatchFoundStuckOverlay = false;
        }

        private static void PollRoomState()
        {
            bool inRoom = PhotonNetwork.InRoom;

            // Focus-loss safety: keep Unity processing events while we're in
            // any room, even if the window is in the background. Vanilla
            // ROUNDS may default to runInBackground=false which makes the
            // ready-up keybind handler silently drop space presses when the
            // player tabs away — that's the root-cause hypothesis for the
            // stuck-on-match-found bug. We restore the original value on
            // room exit so vanilla menu/screensaver behavior stays normal.
            if (inRoom && !_runInBackgroundOverridden)
            {
                try
                {
                    _origRunInBackground = UnityEngine.Application.runInBackground;
                    UnityEngine.Application.runInBackground = true;
                    _runInBackgroundOverridden = true;
                    Plugin.Log.LogInfo($"[FOCUS] In Photon room — Application.runInBackground forced true (was {_origRunInBackground})");
                }
                catch { }
            }
            else if (!inRoom && _runInBackgroundOverridden)
            {
                try
                {
                    UnityEngine.Application.runInBackground = _origRunInBackground;
                    _runInBackgroundOverridden = false;
                    Plugin.Log.LogInfo($"[FOCUS] Left Photon room — runInBackground restored to {_origRunInBackground}");
                }
                catch { }
            }

            // Watchdog: detect "stuck on the ready-up screen specifically".
            // Tight gates: suppress in mod-issued rooms (we manage those),
            // suppress once pick phase has started (cards are being chosen),
            // suppress once players have spawned in PlayerManager (game past
            // the ready prompt), and suppress once combat counters have
            // ticked (isTracking). Threshold bumped to 25s to err on the
            // side of fewer false positives.
            if (inRoom && !isTracking && !inPickPhase)
            {
                int secs = (int)(DateTime.UtcNow - roomJoinTime).TotalSeconds;
                SecondsInUnstartedRoom = secs;
                bool isModIssued = false;
                bool playersSpawned = false;
                try
                {
                    var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                    string rname = PhotonNetwork.CurrentRoom?.Name ?? "";
                    isModIssued = (rp != null && rp.ContainsKey("cr_ff"))
                                || rname.StartsWith("ranked_")
                                || rname.StartsWith("team_")
                                || rname.StartsWith("sct-");
                    var pm = PlayerManager.instance;
                    playersSpawned = pm != null && pm.players != null && pm.players.Count >= 1;
                }
                catch { }
                // Sandbox / offline practice runs in PhotonNetwork.OfflineMode — it's a
                // local-only "room" with no matchmaking and no ready-up screen, so the
                // stuck-on-match-found watchdog must NEVER arm there. Before this guard the
                // watchdog saw Sandbox as "a non-mod room with no match started", armed after
                // 25s, and re-armed every 60s after each dismiss → the escape hatch appeared on
                // entering Sandbox and flashed periodically while the player warmed up / searched
                // from Sandbox. The escape hatch is strictly for recovering from a real online
                // match-found stall, which can't happen offline.
                bool isOffline = false;
                try { isOffline = PhotonNetwork.OfflineMode; } catch { }
                bool dismissExpired = (DateTime.UtcNow - _stuckOverlayDismissedAt).TotalSeconds > 60;
                ShouldShowMatchFoundStuckOverlay =
                    !isModIssued && !isOffline && !playersSpawned && secs >= 25 && dismissExpired;
            }
            else
            {
                SecondsInUnstartedRoom = 0;
                ShouldShowMatchFoundStuckOverlay = false;
            }

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
                // Mod-issued competitive rooms are definitionally ranked. Set
                // immediately at room-join so [POLL] === Match Started === doesn't
                // log CASUAL while CheckOpponentRanked is still racing. cr_ff
                // covers 2v2; ranked_* covers 1v1 ranked queue; sct-* covers
                // sync tournament matches. Vanilla casual / private rooms still
                // go through the regular self-healing CheckOpponentRanked path.
                try
                {
                    var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                    string rname = PhotonNetwork.CurrentRoom?.Name ?? "";
                    bool isModIssued = (rp != null && rp.ContainsKey("cr_ff"))
                                    || rname.StartsWith("ranked_")
                                    || rname.StartsWith("team_")
                                    || rname.StartsWith("sct-");
                    if (isModIssued)
                    {
                        matchIsRanked = true;
                        opponentIsRanked = true;
                        Plugin.Log.LogInfo($"[POLL] mod-issued competitive room detected ({rname}) — matchIsRanked forced true");
                    }
                }
                catch { }
                seriesPreflightSent = false;
                lastOpponentRankCheck = -999f;
                // (#26) Re-arm the opponent-never-arrived watchdog for this room.
                rankedRoomStallHandled = false;
                rankedRoomStallWarned = false;
                rankedRoomEverFull = false;
                // Fresh room = new series. Reset the in-match HUD's BO3 score
                // counter so it doesn't carry over from the prior room. The
                // session game / series tallies stay (they're cumulative).
                currentSeriesGamesWon = 0;
                currentSeriesGamesLost = 0;
                Plugin.Log.LogInfo($"[POLL] Joined room: {photonRoomId} (region: {photonRegion})");
                // Republish all local cosmetic props on every room join. Photon
                // resets state at room creation; without re-publish, remote clients
                // can't see our nametag/color/trail until our stats happen to
                // reload (which only fires on /stats endpoint hits, not on a
                // schedule). User reported: "my body color didn't show for
                // everyone else until the first game finished" — that was
                // because the only PCColor publish was the periodic stats
                // refresh, which landed mid-game-1.
                try { NametagStyler.PublishToPhoton(); } catch { }
                try { PlayerColorCosmetic.PublishLocalProps(); } catch { }
                try { TrailCosmetic.PublishLocalProps(); } catch { }
                try { PlayerEffectCosmetic.PublishLocalProps(); } catch { }
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

                    if (LeavingForRanked)
                    {
                        // We initiated the leave for a ranked match — cancel, don't count
                        Plugin.Log.LogInfo($"[POLL] === {matchType} Canceled === Left for ranked queue at {localRounds}-{oppRounds} (not counted)");
                        CompetitiveUI.ShowNotification("Left match for ranked queue", new Color(0.4f, 0.8f, 1f));
                        LeavingForRanked = false;
                    }
                    else if (localRounds >= 4 && oppRounds >= 4)
                    {
                        // Both at match point and someone DC'd — give the win to the
                        // local player (the one still in the room). Closes the
                        // 4-4 DC exploit (where the DC'er would otherwise get the win
                        // because they had ≥4 rounds at disconnect time).
                        Plugin.Log.LogInfo($"[POLL] === {matchType} DC Win (4-4 tiebreak) === Opponent DC'd at {localRounds}-{oppRounds}");
                        int winnerTeam = localTeamId;
                        OnGameOver(winnerTeam);
                    }
                    else if (localRounds >= 4)
                    {
                        // Local player had dominant lead — count as a win
                        Plugin.Log.LogInfo($"[POLL] === {matchType} DC Win === Opponent disconnected at {localRounds}-{oppRounds}");
                        int winnerTeam = localTeamId;
                        OnGameOver(winnerTeam);
                    }
                    else
                    {
                        // No clear winner OR opponent led but DC'd before clinching.
                        // Cancel the match — opponent doesn't get an undeserved win
                        // for DCing while ahead, and we don't get an undeserved
                        // loss either. Leave % still tracks them via the DC-detection
                        // path below (opponentDCReported), so habitual rage-quitters
                        // still face the leave-percentage penalty.
                        if (oppRounds >= 4)
                            Plugin.Log.LogInfo($"[POLL] === {matchType} Canceled === Opp DC'd while ahead at {localRounds}-{oppRounds} (no win awarded)");
                        else
                            Plugin.Log.LogInfo($"[POLL] === {matchType} Canceled === Disconnect at {localRounds}-{oppRounds} (not counted)");
                        CompetitiveUI.ShowNotification("Match canceled (DC)", new Color(1f, 0.7f, 0.3f));
                    }
                }

                Plugin.Log.LogInfo("[POLL] Left room");
                // Dump per-match perf-patch hit counts so we can verify in the log
                // which ported patches actually fired this match (and how often).
                PerfGate.DumpAndReset();
                ResetMatchState();
            }

            if (inRoom && !opponentSteamIdResolved)
            {
                TryResolveOpponent();
            }

            // (#26) Opponent-never-arrived watchdog for mod-issued 1v1 ranked
            // rooms. Lopi's log (bug #26): the queue matched, both readied, HE
            // joined ranked_13acb279b859 fine — but the opponent never arrived
            // (players stuck 1/2), the vanilla loading screen sat there forever,
            // and the only way out was Escape (which vanilla treats as a raw
            // NetworkRestart during loading). Detect the stall, tell the player
            // what happened, and return to menu cleanly. No match ever started,
            // so no DC/leave penalty applies on either side.
            if (inRoom && !rankedRoomStallHandled && photonRoomId.StartsWith("ranked_"))
            {
                int pc = 0;
                try { pc = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0; } catch { }
                if (pc >= 2) rankedRoomEverFull = true;
                if (!rankedRoomEverFull && !isTracking)
                {
                    double waited = (DateTime.UtcNow - roomJoinTime).TotalSeconds;
                    if (!rankedRoomStallWarned && waited >= 25)
                    {
                        rankedRoomStallWarned = true;
                        CompetitiveUI.ShowNotification("Opponent hasn't connected yet — hang tight...", new Color(1f, 0.8f, 0.3f), 6f);
                    }
                    if (waited >= 60)
                    {
                        rankedRoomStallHandled = true;
                        Plugin.Log.LogWarning($"[QUEUE-STALL] Opponent never joined {photonRoomId} after {(int)waited}s — returning to menu (no match started, no penalty)");
                        CompetitiveUI.ShowNotification("Opponent failed to join — returning to menu. Requeue when ready.", new Color(1f, 0.5f, 0.4f), 10f);
                        try { NetworkConnectionHandler.instance.NetworkRestart(); }
                        catch (Exception ex) { Plugin.Log.LogWarning($"[QUEUE-STALL] NetworkRestart failed: {ex.Message}"); }
                    }
                }
            }

            // Eager preflight for private rooms. The matchIsRanked-gated
            // preflight inside the CheckOpponentRanked callback (further
            // down) is async — it waits for an HTTP /mod/check round
            // trip before firing. For private rooms that delay routinely
            // landed the /series/active row a whole game late, which
            // meant Discord #live-bets and the in-game Live Ranked Games
            // panel only surfaced the match when game 1 was already over.
            // Fire as soon as we have the opponent's Steam ID and see
            // their mod props (cr_*) on Photon — server's preflight
            // endpoint is idempotent and already returns "skipped" if
            // either player isn't ranked, so calling it eagerly is safe.
            // Mod-issued rooms (ranked_*, sct-*) skip this branch — the
            // queue / tournament flow pre-creates the series row anyway,
            // and inCrFf rooms are 2v2 (separate team_series pipeline).
            if (inRoom && !seriesPreflightSent
                && opponentSteamIdResolved
                && !string.IsNullOrEmpty(opponentSteamId)
                && !opponentSteamId.StartsWith("photon_")
                && OpponentHasMod()
                && (Plugin.RankedEnabled?.Value ?? false)
                && string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)
                && !string.IsNullOrEmpty(localSteamId))
            {
                bool inCrFfEager = false;
                try
                {
                    var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                    inCrFfEager = rp != null && rp.ContainsKey("cr_ff");
                }
                catch { }
                string rNameEager = "";
                try { rNameEager = PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
                // 2v2 rooms (cr_ff / team_) keep their own team_series pipeline —
                // never 1v1-preflight there. ranked_* / sct-* rooms ARE allowed
                // now (v1.28.3, #36): series 1 already has ActiveRankedSeriesId
                // from the queue/tournament flow (so the id-empty gate above
                // skips them), but REMATCH series in the same room need this
                // preflight to exist before game 1 ends or they're born
                // bet-locked. Server side is idempotent find-or-create.
                bool is2v2Eager = inCrFfEager || rNameEager.StartsWith("team_");
                if (!is2v2Eager)
                {
                    seriesPreflightSent = true;
                    Plugin.Log.LogInfo($"[POLL] Eager preflight: opponent {opponentSteamId} has mod props — firing /series/preflight before /mod/check completes");
                    ApiClient.SendSeriesPreflight(localSteamId, opponentSteamId);
                }
            }

            // Opponent ranked-check + retry. Initial check fires as soon as their
            // Steam ID is resolved; subsequent retries fire every 5s while in room
            // IF the previous check returned false but we can see they have the mod
            // (cr_* Photon props). That covers the race where their mod's startup
            // /toggle-ranked sync hasn't reached the server yet by the time we ask.
            if (inRoom && opponentSteamIdResolved
                && !opponentSteamId.StartsWith("photon_"))
            {
                bool firstCheck = !opponentRankChecked;
                bool shouldRetry = !firstCheck
                    && !opponentIsRanked
                    && OpponentHasMod()
                    && (Time.realtimeSinceStartup - lastOpponentRankCheck) >= 5f;
                if (firstCheck || shouldRetry)
                {
                    opponentRankChecked = true;
                    lastOpponentRankCheck = Time.realtimeSinceStartup;
                    ApiClient.CheckOpponentRanked(opponentSteamId, (isRanked) =>
                    {
                        bool oldRanked = opponentIsRanked;
                        opponentIsRanked = isRanked;
                        // 2v2 cr_ff rooms are queue-issued team rooms — definitionally
                        // ranked. The 1v1 "opponent has mod + ranked toggled on" check
                        // races against /mod/check responses for the 3 other players,
                        // and even one slow response would flip the entire match to
                        // casual. In cr_ff, force ranked.
                        bool inCrFf = false;
                        try
                        {
                            var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                            inCrFf = rp != null && rp.ContainsKey("cr_ff");
                        }
                        catch { }
                        if (inCrFf)
                        {
                            matchIsRanked = true;
                        }
                        else
                        {
                            matchIsRanked = Plugin.RankedEnabled.Value && opponentIsRanked && OpponentHasMod();
                        }
                        if (oldRanked != opponentIsRanked || firstCheck)
                            Plugin.Log.LogInfo($"[POLL] Opponent ranked: {opponentIsRanked}, hasMod: {OpponentHasMod()}, Match ranked: {matchIsRanked}{(shouldRetry ? " (retry)" : "")}");
                        // Series pre-flight: now that we know the match is ranked, if
                        // this isn't a queue-issued series (ActiveRankedSeriesId is
                        // empty), ask the server to create the ranked_series row so it
                        // appears in /series/active immediately. One-shot per room.
                        //
                        // Skip the 1v1 preflight in 2v2 (cr_ff) rooms — the team_series
                        // row already exists from the queue lock, and creating a 1v1
                        // ranked_series here pollutes the live-bets panel + 1v1 stats
                        // with phantom rows for arbitrary opponent pairs (whichever
                        // opponentSteamId the poll happened to latch onto first).
                        if (matchIsRanked && !inCrFf && !seriesPreflightSent
                            && string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)
                            && !string.IsNullOrEmpty(localSteamId)
                            && !string.IsNullOrEmpty(opponentSteamId)
                            && !opponentSteamId.StartsWith("photon_"))
                        {
                            seriesPreflightSent = true;
                            ApiClient.SendSeriesPreflight(localSteamId, opponentSteamId);
                        }
                    });
                }
            }

            // ── Opponent DC detection (leave % tracking) ──
            // While still in the room during an active match, check if opponent left
            if (inRoom && isTracking && !gameOverReported)
            {
                try
                {
                    int playerCount = PhotonNetwork.PlayerList?.Length ?? 0;
                    if (playerCount >= 2)
                        opponentWasPresent = true;

                    if (opponentWasPresent && playerCount <= 1 && !opponentDCReported)
                    {
                        opponentDCReported = true;
                        int localR = localTeamId == 0 ? p1Rounds : p2Rounds;
                        int oppR = localTeamId == 0 ? p2Rounds : p1Rounds;
                        int totalPts = p1Points + p2Points;
                        int seriesGames = p1Rounds + p2Rounds; // games already won this series

                        // Report for leave % if:
                        //  - match is ranked
                        //  - meaningful play happened (>=2 firefights in current game,
                        //    OR at least one prior game completed in this series so the
                        //    series has progressed past round 1)
                        //  - neither player at match point in current game (>=4 firefights);
                        //    DC'er already in a losing position when they leave at 4-X
                        //    is recorded as a regular DC win, not a leave-% incident.
                        bool meaningfulPlay = totalPts >= 2 || seriesGames >= 1;
                        if (matchIsRanked && meaningfulPlay && localR < 4 && oppR < 4
                            && opponentSteamIdResolved && !opponentSteamId.StartsWith("photon_"))
                        {
                            Plugin.Log.LogInfo($"[DC] Opponent {opponentDisplayName} disconnected at game-rounds={localR}-{oppR}, pts={totalPts}, series-games={seriesGames} — reporting leave");
                            ApiClient.ReportDisconnect(localSteamId, opponentSteamId);
                        }
                        else
                        {
                            Plugin.Log.LogInfo($"[DC] Opponent left (ranked={matchIsRanked}, pts={totalPts}, series-games={seriesGames}, rounds={localR}-{oppR}) — not eligible for leave tracking");
                        }
                    }
                }
                catch { }
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

        // Tracks whether we've pushed the local player's RankedEnabled config to the
        // server's ranked_enabled column for this session. The server's /mod/toggle-ranked
        // endpoint auto-registers the player on first hit, so this is also the new-install
        // auto-registration path. Without this, fresh installs stay ranked_enabled=false
        // on the server until the user manually clicks Enable in F5 — which broke
        // ranked-matching for RoarkCats' first two games (opponent's mod-check returned
        // ranked=false even though Sid's client had ranked ON).
        private static bool _rankedSyncSent;

        private static void IdentifyLocalPlayer()
        {
            try
            {
                CSteamID steamId = SteamUser.GetSteamID();
                if (steamId.m_SteamID != 0)
                {
                    localSteamId = steamId.m_SteamID.ToString();
                    localDisplayName = StripRichText(SteamFriends.GetPersonaName());
                    MaybeSyncRankedStateOnce();
                    return;
                }
            }
            catch { }

            try
            {
                localSteamId = PhotonNetwork.LocalPlayer?.UserId ?? "unknown";
                localDisplayName = StripRichText(PhotonNetwork.LocalPlayer?.NickName ?? "Unknown");
                MaybeSyncRankedStateOnce();
            }
            catch
            {
                localSteamId = "unknown";
                localDisplayName = "Unknown";
            }
        }

        /// <summary>One-shot per session: push the local RankedEnabled config to the server
        /// so the server-side ranked_enabled column matches the client's intent and the mod-
        /// check endpoint returns accurate state for opponents who query us. Idempotent on
        /// the server (plain UPSERT) so re-calling is safe; we still gate to once-per-session
        /// to avoid spamming. Called whenever IdentifyLocalPlayer succeeds — covers the race
        /// where Steam's API hadn't returned the ID by the time Plugin.cs ran its startup
        /// sync and skipped the call.</summary>
        private static void MaybeSyncRankedStateOnce()
        {
            if (_rankedSyncSent) return;
            if (string.IsNullOrEmpty(localSteamId) || localSteamId == "unknown") return;
            try
            {
                bool wanted = Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value;
                ApiClient.ToggleRanked(localSteamId, wanted);
                _rankedSyncSent = true;
                Plugin.Log.LogInfo($"[POLL] Initial ranked state synced to server: enabled={wanted}");
            }
            catch (Exception ex)
            {
                // Leave _rankedSyncSent=false so the next IdentifyLocalPlayer call retries.
                Plugin.Log.LogWarning($"[POLL] Initial ranked sync failed: {ex.Message}");
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
                    CardChoiceEndPickPatch.FlushPendingPicks(localTeamId);
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
                                CardChoiceEndPickPatch.FlushPendingPicks(localTeamId);
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
                                CardChoiceEndPickPatch.FlushPendingPicks(localTeamId);
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

            // Pick-phase body-color apply. Fires the moment both player GameObjects
            // are present in PlayerManager — that happens during pick phase #1, well
            // before OnMatchStarted (which waits on rounds/points to tick). One-shot
            // per room; subsequent rounds reuse the persisted Player GOs so the tint
            // doesn't need re-applying.
            if (!pcolorRoomApplied)
            {
                try
                {
                    var pm = PlayerManager.instance;
                    int pc = pm != null && pm.players != null ? pm.players.Count : 0;
                    if (pc >= 2)
                    {
                        pcolorRoomApplied = true;
                        PlayerColorCosmetic.OnMatchStart();
                        // Also trigger TrailCosmetic — it has its own DelayedAttachAll
                        // pass that iterates players + reads their cr_trail_* props.
                        // Previously only PCColor was kicked here, so trails on
                        // remote players weren't being attached until OnMatchStarted
                        // fired (which can be much later in 2v2 due to the late-joiner
                        // assembly path).
                        try { TrailCosmetic.OnMatchStart(); } catch { }
                        try { PlayerEffectCosmetic.OnMatchStart(); } catch { }
                    }
                }
                catch { }
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
                    // v1.22 — report live points to the server during ranked games so betting
                    // locks once 2 points are scored in game 1. Only fires while we're in the
                    // first match of a series (p1Rounds + p2Rounds == 0) to keep traffic low.
                    if (matchIsRanked && curP1Rounds == 0 && curP2Rounds == 0
                        && !string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)
                        && !string.IsNullOrEmpty(LocalSteamId))
                    {
                        ApiClient.PostLivePoints(ApiClient.ActiveRankedSeriesId, LocalSteamId, curP1Points, curP2Points);
                    }
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

                    // Re-tint player_color cosmetic after every round
                    // transition — vanilla spawns new sprites mid-match
                    // (Phoenix respawn, card effects spawning visual
                    // children) that our match-start DelayedApplyAll
                    // never reaches. Players reported seeing native
                    // team color "leak through" their cosmetic; that's
                    // these later-spawned sprites.
                    try { PlayerColorCosmetic.OnRoundStart(); } catch { }
                    try { PlayerEffectCosmetic.OnRoundStart(); } catch { }

                    // Achievement: track comeback (0-4 deficit)
                    int localR = localTeamId == 0 ? p1Rounds : p2Rounds;
                    int oppR = localTeamId == 0 ? p2Rounds : p1Rounds;
                    if (oppR > achMaxOpponentRounds) achMaxOpponentRounds = oppR;
                    if (localR == 0 && oppR >= 4) achWasDown04 = true;

                    if (!gameOverReported && (curP1Rounds >= roundsToWin || curP2Rounds >= roundsToWin))
                    {
                        int winnerTeam = curP1Rounds > curP2Rounds ? 0 : 1;
                        OnGameOver(winnerTeam);
                    }
                }
                // Track card picks
                PollCardPicks();

                // Achievement: poll health and death state on local player
                PollAchievementState();
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

            // Restore matchIsRanked for game 2+ in a series. OnGameOver clears
            // matchIsRanked at the end of every game (line ~1370) so the in-game
            // "RANKED" indicator goes away during the inter-match break, but
            // games 2 and 3 of a ranked series are obviously still ranked. The
            // room-join branch at the top of Update() (~line 425) only fires
            // once per Photon room transition and the room stays open across
            // the whole series, so without re-deriving matchIsRanked here the
            // remainder of the series is silently treated as casual: leaver
            // reports skipped, session W/L tallied as casual, the OnGameOver
            // log line says "CASUAL Match Over" mid-ranked-series. Caught
            // 2026-04-30 when Galaxy Ice DC'd mid-game-2 of a ranked series
            // with ~6 firefights on the board and got no leaver penalty.
            try
            {
                var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                string rname = PhotonNetwork.CurrentRoom?.Name ?? "";
                bool isModIssued = (rp != null && rp.ContainsKey("cr_ff"))
                                || rname.StartsWith("ranked_")
                                || rname.StartsWith("team_")
                                || rname.StartsWith("sct-");
                if (isModIssued)
                {
                    matchIsRanked = true;
                }
                else if (opponentRankChecked && opponentIsRanked && OpponentHasMod()
                         && Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value)
                {
                    // Vanilla casual room with both players opted-in for cross-room ranked.
                    matchIsRanked = true;
                }

                // Re-arm the series preflight when a ranked game starts with no
                // live series id (#36). Two cases land here: (a) game 1 of a
                // REMATCH series in the same room — the previous BO3 completed,
                // ActiveRankedSeriesId was cleared, and without a fresh preflight
                // the new series row would only be born at first match report
                // (already 1-0 → permanently bet-locked); (b) games 2/3 of any
                // series (id cleared after each report) — the refire is harmless
                // there: the server's find-or-create returns the same active
                // series, restoring the id for live-points. cr_ff (2v2) keeps
                // its own team_series pipeline and is excluded by the poll-side
                // preflight gates.
                bool inCrFfStart = rp != null && rp.ContainsKey("cr_ff");
                if (matchIsRanked && !inCrFfStart && seriesPreflightSent
                    && string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId))
                {
                    seriesPreflightSent = false;
                    Plugin.Log.LogInfo("[POLL] Re-armed series preflight at game start (no live series id)");
                }
            }
            catch { }

            // Spawn the cosmetic trail for this match (if the player owns one).
            TrailCosmetic.OnMatchStart();
            PlayerColorCosmetic.OnMatchStart();
            try { PlayerEffectCosmetic.OnMatchStart(); } catch { }

            // Reset achievement tracking for this match
            achTookDamage = false;
            achPhoenixUsed = false;
            achDied = false;
            achMaxOpponentRounds = 0;
            achWasDown04 = false;
            lastDeadState = false;
            lastRemainingRespawns = -1;
            achFiredShot = false;
            achMoved = false;
            inPickPhase = false;
            pendingRegicideCheck = false;
            LocalShotsThisMatch = 0;
            LocalBlocksThisMatch = 0;
            LocalKeysThisMatch = 0;
            LocalActiveSecondsThisMatch = 0f;
            LocalBulletsFiredThisMatch = 0;
            LocalBulletsHitThisMatch = 0;
            LocalBlocksActivatedThisMatch = 0;
            LocalBlocksSuccessfulThisMatch = 0;
            LocalBlockRawAbsorbs = 0;
            LocalBlockDedupeDrops = 0;
            LastBlockActivatedTime = -999f;
            LastBlockSuccessfulTime = -999f;
            LastBlockAbsorbTime = -999f;
            LastLocalHitTime = -999f;
            LastBlockMissTime = -999f;
            LastBlockEventLabel = "";
            fpsFrameCount = 0;
            fpsTimeAccum = 0f;
            fpsBroadcastTimer = 0f;
            opponentAvgFps = 0;
            _hitsRemaining = 0;
            _lastBlockSuccessTime = -999f;
            _loggedFirstFire = _loggedFirstHit = _loggedFirstBlockAct = _loggedFirstBlockOk = false;

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
            localOffers.Clear();
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
                    props[FPS_PROP_KEY] = 0;
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
                    // Also synthesize an offer row so card_offers reflects the pre-match
                    // pick. Without this, matches where the local player wins every round
                    // (only pre-match pick ever fires) submit with zero offers and every
                    // card reads as "100% pass rate" server-side. The Harmony EndPick hook
                    // and the mid-match synthesize path both miss pre-match picks because
                    // ROUNDS' pre-match auto-pick doesn't route through CardChoice.RPCA_DoEndPick.
                    localOffers.Add(new MatchTracker.CardOfferData
                    {
                        CardName = card.CardName,
                        RoundNumber = 1,
                        WasPicked = true,
                    });
                    Plugin.Log.LogInfo($"[POLL] Card: Pre-match picked {card.CardName} [#{pickCountThisMatch}] (+synth offer)");
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

            // Re-evaluate ranked status at match start. Three gates:
            //   1. WE have ranked enabled
            //   2. Opponent's player record has ranked_enabled=true (server-checked)
            //   3. Opponent's mod is actually running — detected by the presence of
            //      any cr_* Photon custom property they've published (cr_cards,
            //      cr_trail_*, cr_pcolor_*, cr_fps, cr_nametag_*, etc).
            // Gate #3 is the Lemon-vs-Ghelici fix: vanilla players with no mod
            // can never be put into a ranked match, even if their DB record
            // somehow shows ranked_enabled=true (e.g. tombstoned mod install,
            // server-side data drift). 1v1 random-queue between two real mod
            // users is still ranked — that's an intended feature.
            matchIsRanked = Plugin.RankedEnabled.Value && opponentIsRanked && OpponentHasMod();

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

            // ── Update session W/L tracking ──
            // Build the opponent set: in 1v1 it's just opponentDisplayName; in
            // 2v2 it's every other player in the room (sans teammate). Tracks
            // all three opponents in 2v2 so Session Info shows them all rather
            // than whichever one we latched onto first.
            var oppKeys = new List<string>();
            bool sessionRoomIsCrFf = false;
            try
            {
                var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                sessionRoomIsCrFf = rp != null && rp.ContainsKey("cr_ff");
            } catch { }
            if (sessionRoomIsCrFf && PhotonNetwork.PlayerList != null && PhotonNetwork.PlayerList.Length >= 4)
            {
                foreach (var pp in PhotonNetwork.PlayerList)
                {
                    if (pp == null) continue;
                    if (PhotonNetwork.LocalPlayer != null && pp.ActorNumber == PhotonNetwork.LocalPlayer.ActorNumber) continue;
                    string nm = pp.NickName;
                    if (string.IsNullOrEmpty(nm)) continue;
                    oppKeys.Add(nm);
                }
            }
            if (oppKeys.Count == 0)
                oppKeys.Add(opponentDisplayName ?? "Unknown");

            foreach (var oppKey in oppKeys)
            {
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
            }

            if (matchIsRanked)
            {
                if (localWon) sessionRankedWins++; else sessionRankedLosses++;
                // BO3 in-progress: bump the per-series game counter so the HUD
                // can show "Series: 1-0" the moment game 1 ends, without
                // waiting for the next /series/active fetch.
                //
                // Self-correcting reset (bug #20): if the PREVIOUS series already
                // reached the BO3 win threshold (2), this game-over belongs to a
                // NEW series — zero the counter first so the HUD never shows >2
                // (e.g. "4-0"). The other resets — IncrementSessionRankedSeries
                // (server-confirmed completion) and the room-change path — only
                // fire on the REPORTER's client (lower Steam ID reports), so the
                // non-reporter would otherwise accumulate across back-to-back
                // series played in the same room. Keying off the score fixes both
                // sides and is harmless when those other resets already ran (the
                // counter is already 0).
                if (currentSeriesGamesWon >= 2 || currentSeriesGamesLost >= 2)
                {
                    currentSeriesGamesWon = 0;
                    currentSeriesGamesLost = 0;
                }
                if (localWon) currentSeriesGamesWon++; else currentSeriesGamesLost++;
            }
            else
            {
                if (localWon) sessionCasualWins++; else sessionCasualLosses++;
            }

            // Update session time immediately (not just on room leave)
            AccumulateSessionTime();

            // Checkpoint session state to PlayerPrefs so a restart-within-3h
            // restores all of this. AccumulateSessionTime already bumped the
            // time-by-opponent dict; the WL dict + counters were bumped above.
            SaveSessionState();

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

            // Hard block: offline / practice / bot matches must never reach the server. ROUNDS'
            // offline mode uses photon room names like "offline room" and replaces the opponent
            // slot with an AI — our cached opponent steam_id from the previous ranked series
            // would otherwise end up attributed to a phantom 5-0 match. Check both the Photon
            // OfflineMode flag AND the room name as a belt-and-suspenders defense (observed two
            // such phantom rows reported against 'Sid' from an opponent's offline practice).
            bool isOfflineMatch = false;
            try
            {
                if (PhotonNetwork.OfflineMode) isOfflineMatch = true;
                if (!string.IsNullOrEmpty(photonRoomId)
                    && photonRoomId.IndexOf("offline", StringComparison.OrdinalIgnoreCase) >= 0)
                    isOfflineMatch = true;
            }
            catch { }
            if (isOfflineMatch)
            {
                Plugin.Log.LogInfo($"[POLL] Skipping match report — offline/practice detected (room='{photonRoomId}')");
                shouldReport = false;
            }

            // ── 2v2 routing ────────────────────────────────────────
            // If this room has 4 players AND we have an active team series id, route through
            // the 2v2 match report instead of 1v1. The reporter (lowest Steam ID across the 4)
            // assembles the canonical t1a/t1b/t2a/t2b ordering by sorting each team's Steam IDs
            // — server canonicalizes the same way at lock, so the 11-field HMAC byte-matches.
            bool routedTeamMatch = false;
            try
            {
                int playerListLen = PhotonNetwork.PlayerList?.Length ?? -1;
                bool hasSeries = !string.IsNullOrEmpty(ApiClient.ActiveTeamSeriesId);
                bool roomIsCrFf = false;
                try
                {
                    var rp = PhotonNetwork.CurrentRoom?.CustomProperties;
                    roomIsCrFf = rp != null && rp.ContainsKey("cr_ff");
                }
                catch { }
                Plugin.Log.LogInfo($"[2v2-REPORT-ROUTE] shouldReport={shouldReport} ActiveTeamSeriesId={(hasSeries ? ApiClient.ActiveTeamSeriesId : "(null)")} PlayerList.Length={playerListLen} cr_ff={roomIsCrFf}");

                if (shouldReport
                    && hasSeries
                    && PhotonNetwork.PlayerList != null
                    && PhotonNetwork.PlayerList.Length == 4)
                {
                    routedTeamMatch = TryReportTeamMatch(reportRoomId, duration);
                    if (routedTeamMatch)
                    {
                        EvaluateAchievements(localWon);
                        isTracking = false;
                        matchIsRanked = false;
                        return;
                    }
                }

                // Any 2v2 signal (cr_ff room or team series) bans the 1v1 fallback —
                // otherwise we leak phantom 1v1 matches + ranked_series rows for arbitrary
                // 2v2 opponent pairs, polluting bets and 1v1 history.
                if (roomIsCrFf || hasSeries)
                {
                    Plugin.Log.LogWarning($"[2v2-REPORT-ROUTE] BLOCKING 1v1 fallback in 2v2 context: shouldReport={shouldReport} hasSeries={hasSeries} playerListLen={playerListLen} cr_ff={roomIsCrFf} — match will not be reported");
                    EvaluateAchievements(localWon);
                    isTracking = false;
                    matchIsRanked = false;
                    return;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogError($"[POLL] 2v2 routing error: {ex.Message}");
            }

            if (shouldReport)
            {
                // Diagnostic for the 1v1 / tournament report path. Same shape as
                // [2v2-REPORT-ROUTE] — surfaces the key signals so silent
                // mis-routing (e.g., ranked match logged casual, tournament match
                // logged 1v1 ranked) is diagnosable instead of invisible.
                try
                {
                    string rn = PhotonNetwork.CurrentRoom?.Name ?? "(no room)";
                    bool isTour = rn.StartsWith("sct-");
                    bool isRk = rn.StartsWith("ranked_");
                    Plugin.Log.LogInfo($"[REPORT-ROUTE] 1v1 path: room={rn} isRanked={matchIsRanked} tournament={isTour} ranked_queue={isRk} reporter={localSteamId} opponent={opponentSteamId}");
                }
                catch { }
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
                    p1Offers: localTeamId == 0 ? localOffers : emptyOffers,
                    p2Offers: localTeamId == 0 ? emptyOffers : localOffers,
                    photonRoomId: reportRoomId,
                    region: photonRegion,
                    durationSeconds: duration,
                    startedAt: matchStartTime,
                    reporterSteamId: localSteamId,
                    isRanked: matchIsRanked,
                    localShotsFired: LocalShotsThisMatch,
                    localBlocksRaised: LocalBlocksThisMatch,
                    // bullets_fired = projectile count via Gun.Attack Postfix × numberOfProjectiles
                    // (captures shotgun pellets, auto-fire, burst weapons — not just trigger pulls).
                    // blocks_activated = right-click count. bullets_hit / blocks_successful come
                    // from Harmony hooks (HealthHandler.TakeDamage with projectile filter, and
                    // Block.DoBlock) wired in Plugin.cs.
                    localBulletsFired: LocalBulletsFiredThisMatch,
                    localBulletsHit: LocalBulletsHitThisMatch,
                    // TryBlock-based activation counter includes manual right-click AND any
                    // source (cards like Shields Up / Empower that trigger block via the
                    // same code path). LocalBlocksThisMatch (mouse-only) remains the anti-
                    // cheat advisory signal.
                    localBlocksActivated: LocalBlocksActivatedThisMatch,
                    localBlocksSuccessful: LocalBlocksSuccessfulThisMatch,
                    localAvgFps: LocalAvgFps,
                    opponentAvgFps: OpponentAvgFps,
                    localKeysPressed: LocalKeysThisMatch,
                    localActiveSeconds: LocalActiveSecondsThisMatch
                );
            }

            // Evaluate achievements before clearing match state
            EvaluateAchievements(localWon);

            isTracking = false;
            matchIsRanked = false; // Clear indicator immediately
        }

        /// <summary>Build + submit a 2v2 match report. Reads each peer's broadcast cards
        /// (cr_cards) + FPS (cr_fps) off Photon custom properties. Reporter selection:
        /// lowest Steam ID across the 4 participants. Canonical slot ordering: t1a/t1b/t2a/t2b
        /// where team1 = team-with-localTeamId-0, sorted within each team by Steam ID — same
        /// rule the server applies at lock-time so the 11-field HMAC matches.</summary>
        private static bool TryReportTeamMatch(string reportRoomId, int duration)
        {
            if (PhotonNetwork.PlayerList == null || PhotonNetwork.PlayerList.Length != 4)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] aborting: PlayerList.Length={PhotonNetwork.PlayerList?.Length ?? -1} (expected 4)");
                return false;
            }

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] aborting: PlayerManager.instance={(pm == null ? "null" : "set")} pm.players={(pm?.players == null ? "null" : "set")}");
                return false;
            }

            // Map each Photon player → in-game Player → TeamID. The teamID
            // lives on Player (public property TeamID; private field m_teamID),
            // NOT on CharacterData. v1.25.11 used reflection on
            // CharacterData.teamID which returned null silently and aborted
            // the entire 2v2 report path — that's why every match was logging
            // as 1v1 casual. PlayerManager.players is List<Player>.

            // Resolve Photon ActorNumber → Steam ID via the same ck_id hint our existing
            // resolver writes; if missing, fall back to UserId. We also need each player's
            // teamID to know who's on team 1 vs team 2.
            var photonPlayers = PhotonNetwork.PlayerList;
            var bySteam = new Dictionary<string, (string name, int teamId, List<MatchTracker.CardPickData> cards, int fps)>();

            foreach (var pp in photonPlayers)
            {
                if (pp == null) continue;
                string sid = ResolvePhotonSteamId(pp);
                if (string.IsNullOrEmpty(sid) || sid.StartsWith("photon_"))
                {
                    Plugin.Log.LogWarning($"[2v2-REPORT] couldn't resolve Steam ID for actor {pp.ActorNumber}");
                    return false;
                }
                // Strip rich-text from NickName before sending to server. The schema
                // limits display_name to 64 chars; styled nicknames (e.g. neon-pink
                // wrap with bold/italic/underline/size tags) easily exceed that.
                // Pydantic rejects with 422 → the entire 2v2 report fails silently.
                string name = StripRichText(pp.NickName ?? sid);
                if (string.IsNullOrEmpty(name)) name = sid;
                if (name.Length > 60) name = name.Substring(0, 60);
                // Find their Player → TeamID. PlayerManager.players is List<Player>;
                // each entry has IsLocal/TeamID/PlayerID + a CharacterData on the
                // same GameObject. Match by Photon ActorNumber via PhotonView.
                int peerTeamId = -1;
                foreach (var po in pm.players)
                {
                    if (po == null) continue;
                    var pv = po.GetComponent<PhotonView>();
                    if (pv == null || pv.Owner == null) continue;
                    if (pv.Owner.ActorNumber != pp.ActorNumber) continue;
                    peerTeamId = po.TeamID;
                    break;
                }
                // Cards from Photon cr_cards
                var pickList = new List<MatchTracker.CardPickData>();
                if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey(CARD_PROP_KEY))
                {
                    string raw = pp.CustomProperties[CARD_PROP_KEY]?.ToString() ?? "";
                    if (!string.IsNullOrEmpty(raw))
                    {
                        int order = 1;
                        foreach (var nm in raw.Split('|'))
                        {
                            string cn = ToTitleCase(nm.Trim());
                            cn = CardRarityLookup.GetCanonicalName(cn);
                            if (string.IsNullOrEmpty(cn)) continue;
                            pickList.Add(new MatchTracker.CardPickData
                            {
                                CardName = cn,
                                CardRarity = CardRarityLookup.GetRarity(cn),
                                PickOrder = order++,
                                RoundNumber = 1,
                            });
                        }
                    }
                }
                int fps = 0;
                if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey(FPS_PROP_KEY))
                {
                    try { fps = Convert.ToInt32(pp.CustomProperties[FPS_PROP_KEY]); } catch { }
                }
                // For the local player, prefer locally-tracked cards/FPS over the broadcast.
                if (pp.IsLocal)
                {
                    if (localCards != null && localCards.Count > 0) pickList = new List<MatchTracker.CardPickData>(localCards);
                    int myFps = LocalAvgFps;
                    if (myFps > 0) fps = myFps;
                }
                bySteam[sid] = (name, peerTeamId, pickList, fps);
            }

            if (bySteam.Count != 4)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] resolved {bySteam.Count}/4 players, aborting");
                return false;
            }

            // Reporter election: lowest Steam ID across all 4. (Same rule as 1v1.)
            string lowestSid = null;
            long lowestVal = long.MaxValue;
            foreach (var sid in bySteam.Keys)
            {
                if (long.TryParse(sid, out long v) && v < lowestVal) { lowestVal = v; lowestSid = sid; }
            }
            if (lowestSid == null) lowestSid = localSteamId;
            if (lowestSid != localSteamId)
            {
                Plugin.Log.LogInfo($"[2v2-REPORT] reporter is {lowestSid}, not me ({localSteamId}) — skipping");
                return true; // routed correctly; just not by us
            }

            // Group by in-game team_id. ROUNDS uses 0/1 for the 2 teams.
            var team0Sids = new List<string>();
            var team1Sids = new List<string>();
            foreach (var kv in bySteam)
            {
                if (kv.Value.teamId == 0) team0Sids.Add(kv.Key);
                else if (kv.Value.teamId == 1) team1Sids.Add(kv.Key);
            }
            if (team0Sids.Count != 2 || team1Sids.Count != 2)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] team split is {team0Sids.Count}/{team1Sids.Count}, aborting");
                return false;
            }
            // Convention: team1_in_db corresponds to in-game team_id=0 by default. We don't actually
            // know which DB team is which — but the server stores by player_id and the client computes
            // p1Rounds/p2Rounds via localTeamId. Map: t1 = team0 (where localTeamId==0 player lives)
            // → matches the existing p1/p2 convention. Within each team, sort by Steam ID so client
            // and server canonical orderings agree.
            team0Sids.Sort(StringComparer.Ordinal);
            team1Sids.Sort(StringComparer.Ordinal);

            int t1Rounds = p1Rounds, t2Rounds = p2Rounds;
            int t1Points = p1Points, t2Points = p2Points;
            int winnerTeam = (t1Rounds > t2Rounds) ? 1 : 2;

            string t1aSid = team0Sids[0], t1bSid = team0Sids[1];
            string t2aSid = team1Sids[0], t2bSid = team1Sids[1];

            ApiClient.ReportTeamMatch(
                seriesId: ApiClient.ActiveTeamSeriesId,
                t1aSteam: t1aSid, t1aName: bySteam[t1aSid].name, t1aCards: bySteam[t1aSid].cards,
                t1bSteam: t1bSid, t1bName: bySteam[t1bSid].name, t1bCards: bySteam[t1bSid].cards,
                t2aSteam: t2aSid, t2aName: bySteam[t2aSid].name, t2aCards: bySteam[t2aSid].cards,
                t2bSteam: t2bSid, t2bName: bySteam[t2bSid].name, t2bCards: bySteam[t2bSid].cards,
                t1Rounds: t1Rounds, t2Rounds: t2Rounds, t1Points: t1Points, t2Points: t2Points,
                photonRoomId: reportRoomId, region: photonRegion,
                durationSeconds: duration, startedAt: matchStartTime,
                reporterSteamId: localSteamId, isRanked: matchIsRanked, winnerTeam: winnerTeam,
                t1aFps: bySteam[t1aSid].fps, t1bFps: bySteam[t1bSid].fps,
                t2aFps: bySteam[t2aSid].fps, t2bFps: bySteam[t2bSid].fps
            );
            Plugin.Log.LogInfo($"[2v2-REPORT] submitted: t1={t1aSid},{t1bSid} t2={t2aSid},{t2bSid} winner=T{winnerTeam}");
            return true;
        }

        /// <summary>Maps a Photon player to a Steam ID. ROUNDS publishes the Steam
        /// ID under the `u_id` custom prop (with `unity_id` as a legacy fallback);
        /// UserId is also Steam-set for Steam-launched clients.</summary>
        private static string ResolvePhotonSteamId(Photon.Realtime.Player pp)
        {
            try
            {
                var props = pp.CustomProperties;
                if (props != null)
                {
                    if (props.ContainsKey("u_id"))
                    {
                        string s = props["u_id"]?.ToString();
                        if (!string.IsNullOrEmpty(s) && long.TryParse(s, out _)) return s;
                    }
                    if (props.ContainsKey("unity_id"))
                    {
                        string s = props["unity_id"]?.ToString();
                        if (!string.IsNullOrEmpty(s) && long.TryParse(s, out _)) return s;
                    }
                }
                if (!string.IsNullOrEmpty(pp.UserId) && long.TryParse(pp.UserId, out _)) return pp.UserId;
            }
            catch { }
            return $"photon_{pp.ActorNumber}";
        }

        // Promoted: lets CompetitiveUI gate the chat-input T key so we don't swallow movement
        // input during fighting. False during pick phase / between rounds / not in match / dead.
        public static bool LocalAliveInCombatNow { get; private set; }

        // ── Achievement health/death polling ─────────────────────
        private static void PollAchievementState()
        {
            if (!isTracking) { LocalAliveInCombatNow = false; return; }
            bool localAliveInCombat = false;
            try
            {
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                foreach (var playerObj in pm.players)
                {
                    if (playerObj == null) continue;
                    var pv = playerObj.GetComponent<PhotonView>();
                    if (pv == null || !pv.IsMine) continue;

                    var data = playerObj.GetComponent<CharacterData>();
                    if (data == null) break;

                    // Player is alive and in active gameplay (not card pick / transition)
                    if (!data.dead && data.health > 0)
                        localAliveInCombat = true;

                    // Damage check: health < MaxHealth while alive and playing
                    if (!data.dead && data.health > 0 && data.health < data.MaxHealth)
                    {
                        if (!achTookDamage)
                            Plugin.Log.LogInfo("[ACH] Player took damage");
                        achTookDamage = true;
                    }

                    // Death check: data.dead transitioned to true
                    if (data.dead && !lastDeadState)
                    {
                        achDied = true;
                    }
                    lastDeadState = data.dead;

                    // Phoenix check: remainingRespawns < respawns
                    var stats = data.stats;
                    if (stats != null && stats.respawns > 0)
                    {
                        if (stats.remainingRespawns < stats.respawns)
                        {
                            if (!achPhoenixUsed)
                                Plugin.Log.LogInfo("[ACH] Phoenix life consumed");
                            achPhoenixUsed = true;
                        }
                    }
                    break;
                }
            }
            catch { }

            // Sync our exposed flag — true ONLY when we're truly in combat (not pick / dead / menu).
            LocalAliveInCombatNow = localAliveInCombat && !inPickPhase;

            // Input tracking — ONLY during active combat AND not in pick phase.
            // CharacterData persists with !dead && health>0 during the card-pick UI, so
            // localAliveInCombat alone is insufficient. The inPickPhase flag is driven by
            // "PICK PHASE" / "MOVE PLAYERS END" log markers in OnUnityLog.
            if (localAliveInCombat && !inPickPhase)
            {
                if (!achFiredShot && Input.GetMouseButton(0))
                {
                    achFiredShot = true;
                    Plugin.Log.LogInfo("[ACH] Player fired a shot");
                }
                // Anti-cheat counters — increment on KeyDown so we get one per click, not one per frame held.
                // GetMouseButton(0)/(1) above covers held-state for achievements; ButtonDown gives discrete events.
                if (Input.GetMouseButtonDown(0)) LocalShotsThisMatch++;
                if (Input.GetMouseButtonDown(1)) LocalBlocksThisMatch++;
                // v1.29 input-rate metric: active-combat seconds + discrete key events.
                // anyKeyDown covers keyboard AND mouse buttons (one tick per frame with
                // any new press). Chat/menu focus excluded below via the same gate as
                // the movement flag so typing doesn't count as gameplay input.
                LocalActiveSecondsThisMatch += Time.deltaTime;
                // Skip key-down sampling while the chat overlay has focus — typing
                // "wasd" in a Discord-bridged message previously false-flagged
                // Immovable Object. Same gate applies to Pacifist's mouse-shot
                // detection above, but mouse buttons aren't generally used while
                // typing so it's a non-issue. Same for the F5 menu.
                bool typingInChat = false;
                try { typingInChat = CompetitiveUI.IsChatInputOpen || NativeUI.IsOpen; } catch { }
                if (!typingInChat && Input.anyKeyDown) LocalKeysThisMatch++;
                if (!typingInChat && !achMoved && (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.A) ||
                    Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.D) ||
                    Input.GetKey(KeyCode.Space) || Input.GetKey(KeyCode.UpArrow) ||
                    Input.GetKey(KeyCode.DownArrow) || Input.GetKey(KeyCode.LeftArrow) ||
                    Input.GetKey(KeyCode.RightArrow)))
                {
                    achMoved = true;
                    Plugin.Log.LogInfo("[ACH] Player moved");
                }
            }
        }

        private static void EvaluateAchievements(bool localWon)
        {
            try
            {
                int localR = localTeamId == 0 ? p1Rounds : p2Rounds;
                int oppR = localTeamId == 0 ? p2Rounds : p1Rounds;

                // Only evaluate on proper game completions (someone reached roundsToWin)
                if (localR < roundsToWin && oppR < roundsToWin)
                {
                    Plugin.Log.LogInfo($"[ACH] Skipping — incomplete game ({localR}-{oppR}, need {roundsToWin})");
                    return;
                }

                bool swept = localWon && oppR == 0;
                string steamId = localSteamId;

                // Collect local card names (normalized)
                var cardNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var cardCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
                foreach (var c in localCards)
                {
                    string cn = c.CardName ?? "";
                    cardNames.Add(cn);
                    if (cardCounts.ContainsKey(cn)) cardCounts[cn]++;
                    else cardCounts[cn] = 1;
                }
                foreach (var c in preMatchCards)
                {
                    string cn = c.CardName ?? "";
                    cardNames.Add(cn);
                    if (cardCounts.ContainsKey(cn)) cardCounts[cn]++;
                    else cardCounts[cn] = 1;
                }

                // 1. Untouchable — won without taking any damage
                if (localWon && !achTookDamage)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: Untouchable — PASSED");
                    ApiClient.UnlockAchievement(steamId, "untouchable");
                }

                // 2-5. Card-specific 5-0 sweeps
                if (swept)
                {
                    // Check multiple name variants for each card
                    if (cardNames.Contains("Sneaky") || cardNames.Contains("Sneaky Bullets"))
                        ApiClient.UnlockAchievement(steamId, "silent_assassin");
                    if (cardNames.Contains("Mayhem"))
                        ApiClient.UnlockAchievement(steamId, "total_mayhem");
                    if (cardNames.Contains("Glass Cannon") || cardNames.Contains("Glasscannon"))
                        ApiClient.UnlockAchievement(steamId, "fragile_perfection");
                    if (cardNames.Contains("Chase"))
                        ApiClient.UnlockAchievement(steamId, "no_escape");
                }

                // 6. Rise from the Ashes — 5-0 with Phoenix, never lost a life
                bool hasPhoenix = cardNames.Contains("Phoenix");
                if (swept && hasPhoenix && !achPhoenixUsed && !achDied)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: Rise from the Ashes — PASSED");
                    ApiClient.UnlockAchievement(steamId, "rise_from_the_ashes");
                }

                // 7. The Comeback Kid — won after being down 0-4
                if (localWon && achWasDown04)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: The Comeback Kid — PASSED");
                    ApiClient.UnlockAchievement(steamId, "the_comeback_kid");
                }

                // 8. Stacked Deck — 5+ copies of one card
                foreach (var kvp in cardCounts)
                {
                    if (kvp.Value >= 5)
                    {
                        Plugin.Log.LogInfo($"[ACH] Evaluating: Stacked Deck — PASSED ({kvp.Key} x{kvp.Value})");
                        ApiClient.UnlockAchievement(steamId, "stacked_deck");
                        break;
                    }
                }

                // 9. Regicide — now handled server-side after series completion
                // (pendingRegicideCheck flag is still set but consumed/cleared by ApiClient)
                if (matchIsRanked && localWon && opponentSteamId == SID_STEAM_ID)
                    pendingRegicideCheck = true;

                // 10. Pacifist — won without firing a single shot
                if (localWon && !achFiredShot)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: Pacifist — PASSED");
                    ApiClient.UnlockAchievement(steamId, "pacifist");
                }

                // 11. Immovable Object — won without moving or jumping
                if (localWon && !achMoved)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: Immovable Object — PASSED");
                    ApiClient.UnlockAchievement(steamId, "immovable_object");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[ACH] Achievement evaluation error: {ex.Message}");
            }
        }

        // Regicide flag — consumed in ApiClient when series_status == "completed"
        public static bool pendingRegicideCheck = false;

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

            // Pick-phase tracking for input-gating (Pacifist / Immovable Object).
            // ROUNDS log sequence each round:
            //   "Round over" / "Point over" → "PICK PHASE" → "MOVE PLAYERS END" → combat.
            if (message.StartsWith("PICK PHASE"))
            {
                if (!inPickPhase) Plugin.Log.LogInfo("[ACH] Pick phase entered — input gating disabled");
                inPickPhase = true;
            }
            else if (message.StartsWith("MOVE PLAYERS END"))
            {
                if (inPickPhase) Plugin.Log.LogInfo("[ACH] Combat begins — input gating enabled");
                inPickPhase = false;
                // Fire OnMatchStarted at the START of combat (not after the first death) so
                // the cosmetic trail attaches immediately and the "RANKED — Recording" notice
                // appears as soon as movement begins. The score-based trigger in PollGameState
                // remains as a safety net for replays / edge cases that skip the log marker.
                if (!isTracking)
                {
                    try { OnMatchStarted(); } catch (Exception ex) { Plugin.Log.LogWarning($"[ACH] early start hook: {ex.Message}"); }
                }
                // Auto-close the F5 competitive menu so it doesn't intercept clicks during combat
                try { if (NativeUI.IsOpen) NativeUI.Close(); } catch { }
            }
            else if (message.StartsWith("Round over") || message.StartsWith("Point over"))
            {
                // Defensive: belt-and-suspenders in case PICK PHASE fires without MOVE PLAYERS END
                inPickPhase = false;
            }

            // The game logs "Picking Card: CardName(Clone)" only for the LOCAL player
            if (message.StartsWith("Picking Card: "))
            {
                string raw = message.Substring("Picking Card: ".Length);
                string cardName = ToTitleCase(raw.Replace("(Clone)", "").Trim());
                cardName = CardRarityLookup.GetCanonicalName(cardName); // normalize to canonical

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
                _lastLocalPickedCardName = cardName;  // for Harmony offer-fallback path
                Plugin.Log.LogInfo($"[POLL] Card: Local picked {cardName} [#{pickCountThisMatch}]");

                // Pass-tracking safety net: the first pick of each match routes through a
                // different ROUNDS code path that doesn't fire CardChoice.RPCA_DoEndPick, so
                // our Harmony offer-loop never sees it. That consistently left every match
                // with one missing was_picked=true row, which read as "100% pass rate" in
                // card stats for that card. If no offer row exists yet for this (round,
                // card, picked=true), synthesize one here.
                bool alreadyRecorded = false;
                for (int i = 0; i < localOffers.Count; i++)
                {
                    var o = localOffers[i];
                    if (o.WasPicked && o.RoundNumber == currentRound && o.CardName == cardName)
                    { alreadyRecorded = true; break; }
                }
                if (!alreadyRecorded)
                {
                    localOffers.Add(new MatchTracker.CardOfferData
                    {
                        CardName = cardName,
                        RoundNumber = currentRound,
                        WasPicked = true,
                    });
                    Plugin.Log.LogInfo($"[POLL] Synthesized picked offer for {cardName} round={currentRound} (Harmony EndPick didn't fire)");
                }

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
            // Canonicalize: without this, opponent card names landed in match_cards raw
            // (e.g. "Chillingpresence", "Drillammo", "Prisitne Perseverence") while our
            // OWN picks went through GetCanonicalName → the DB split cards into near-
            // duplicate rows whenever an opponent happened to report them. Fixed by always
            // normalizing at every write site.
            cardName = ToTitleCase(cardName);
            cardName = CardRarityLookup.GetCanonicalName(cardName);

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
                            cn = CardRarityLookup.GetCanonicalName(cn);
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

        /// <summary>True iff at least one non-local player in the current Photon
        /// room has published a cr_* custom property — our mod's signature.
        /// Cards, trails, FPS, body colors, nametags, etc. all set their own
        /// cr_* keys at room-join / match-start time, so by the time this is
        /// evaluated (a few frames after combat begins) any peer running the
        /// mod will have at least one of them. Vanilla players have none.</summary>
        public static bool OpponentHasMod()
        {
            try
            {
                if (!PhotonNetwork.InRoom) return false;
                var players = PhotonNetwork.PlayerList;
                if (players == null) return false;
                foreach (var p in players)
                {
                    if (p == null || p.IsLocal) continue;
                    var props = p.CustomProperties;
                    if (props == null) continue;
                    foreach (var key in props.Keys)
                    {
                        string k = key as string;
                        if (k != null && k.StartsWith("cr_", StringComparison.Ordinal)) return true;
                    }
                }
            }
            catch { }
            return false;
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

        // Trail teardown on any match-state reset — next OnMatchStarted re-attaches.
        private static void ResetMatchStateWithTrail() { TrailCosmetic.OnMatchEnd(); PlayerColorCosmetic.OnMatchEnd(); try { PlayerEffectCosmetic.OnMatchEnd(); } catch { } ResetMatchState(); }

        private static void ResetMatchState()
        {
            isTracking = false;
            gameOverReported = false;
            wasGameInProgress = false;
            pcolorRoomApplied = false;
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
            localOffers.Clear();
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

            // Reset DC tracking
            opponentWasPresent = false;
            opponentDCReported = false;

            // Reset achievement tracking
            achTookDamage = false;
            achPhoenixUsed = false;
            achDied = false;
            achMaxOpponentRounds = 0;
            achWasDown04 = false;
            lastDeadState = false;
            lastRemainingRespawns = -1;
            achFiredShot = false;
            achMoved = false;
            inPickPhase = false;
            pendingRegicideCheck = false;
            LocalShotsThisMatch = 0;
            LocalBlocksThisMatch = 0;
            LocalKeysThisMatch = 0;
            LocalActiveSecondsThisMatch = 0f;
            LocalBulletsFiredThisMatch = 0;
            LocalBulletsHitThisMatch = 0;
            LocalBlocksActivatedThisMatch = 0;
            LocalBlocksSuccessfulThisMatch = 0;
            LocalBlockRawAbsorbs = 0;
            LocalBlockDedupeDrops = 0;
            LastBlockActivatedTime = -999f;
            LastBlockSuccessfulTime = -999f;
            LastBlockAbsorbTime = -999f;
            LastLocalHitTime = -999f;
            LastBlockMissTime = -999f;
            LastBlockEventLabel = "";
            fpsFrameCount = 0;
            fpsTimeAccum = 0f;
            fpsBroadcastTimer = 0f;
            opponentAvgFps = 0;
            _hitsRemaining = 0;
            _lastBlockSuccessTime = -999f;

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
        public static bool LeavingForRanked { get; set; } = false;
        public static string LocalSteamId => localSteamId;
        public static string LocalDisplayName => localDisplayName;
        public static string OpponentDisplayName => opponentDisplayName;
        public static string OpponentSteamId => opponentSteamId;
        public static int P1Rounds => p1Rounds;
        public static int P2Rounds => p2Rounds;
        public static int P1Points => p1Points;
        public static int P2Points => p2Points;
        public static int LocalTeamId => localTeamId;
        public static int CurrentRound => currentRound;

        /// <summary>
        /// Called by the CardChoice.RPCA_DoEndPick Harmony hook for each card the local
        /// player was OFFERED (cardIDs[]). wasPicked = (cardID == targetCardID).
        /// One row per (round, card) — multiple offers in the same round get separate rows.
        /// </summary>
        public static void OnLocalCardOffered(string cardName, bool wasPicked, int round)
        {
            if (string.IsNullOrEmpty(cardName)) return;
            localOffers.Add(new MatchTracker.CardOfferData
            {
                CardName = cardName,
                RoundNumber = round,
                WasPicked = wasPicked,
            });
            if (wasPicked) _lastLocalPickedCardName = cardName;
        }

        // Current size of the offers buffer — used as a "before the pick loop" snapshot so
        // the Harmony hook can detect whether any new rows were added, and whether any were
        // marked wasPicked=true. Lets us fall back to injecting a synthetic picked row when
        // cardIDs[] resolution fails for the chosen card (the Silence pass%=100% bug).
        public static int LocalOffersCount => localOffers.Count;
        public static bool LocalOffersPickedIn(int fromIndex)
        {
            if (fromIndex < 0) fromIndex = 0;
            for (int i = fromIndex; i < localOffers.Count; i++)
                if (localOffers[i].WasPicked) return true;
            return false;
        }

        // Last card name the local player picked (canonical), captured either by the
        // Unity-log "Picking Card:" handler or the Harmony EndPick patch. Used by the
        // pass-tracking fallback when the regular cardIDs[] loop can't identify the picked card.
        private static string _lastLocalPickedCardName;
        public static string LastLocalPickedCardName => _lastLocalPickedCardName;
    }
}
