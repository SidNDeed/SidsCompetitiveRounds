using ExitGames.Client.Photon;
using Photon.Pun;
using Steamworks;
using System;
using System.Collections.Generic;
using System.Linq;
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
        // Read-only view for patches that gate diagnostics on "a match is live".
        public static bool IsTracking => isTracking;
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

        // ── July 21 item 2: FPS/lag exploit telemetry ─────────────────────
        // Per-match FPS timelines (own = 5s buckets, opponent = their 3s
        // broadcast samples), freeze events (window-drag stalls the main
        // thread; the resume frame carries the whole gap), Photon ping
        // aggregates, receive-gap events (deliberate NIC-cut "ghost" tell)
        // and opponent-heartbeat gaps (victim-side view of the same). All
        // advisory — never in the HMAC, never auto-invalidating.
        private static readonly List<int> localFpsTimeline = new List<int>();   // cap 90 (7.5 min)
        private static int tlFrames = 0;
        private static float tlAccum = 0f;
        private static int bcFrames = 0;          // frames since last 3s broadcast (instantaneous fps)
        private static float bcAccum = 0f;
        private static int gstatsSeq = 0;         // monotonic broadcast counter (heartbeat)
        private static int lastBroadcastRecentFps = 0;
        private static readonly List<int> oppFpsTimeline = new List<int>();     // cap 128 (511 chars worst case)
        private static readonly List<int> oppPingTimeline = new List<int>();    // July 22 item 3: opp ping via gstats field 12
        private static int lastOppGstatsSeq = -1;
        private static float lastOppSeqAdvanceTime = -1f;
        private static int localFreezeCount = 0;
        private static int localFreezeFocusedCount = 0;   // resumed WITH focus = window-drag signature
        private static float localFreezeTotalSec = 0f;
        private static readonly List<int> pingSamples = new List<int>();        // 3s cadence, aggregates reported
        private static int localRecvGapCount = 0;
        private static int localRecvGapMaxMs = 0;
        private static bool _recvGapOpen = false;
        private static int oppHbGapCount = 0;
        private static bool _oppHbGapOpen = false;
        private static int oppFreezeCount = 0;            // opponent's own counters via cr_gstats
        private static int oppFreezeFocusedCount = 0;
        private static int oppRecvGapCount = 0;
        private static long _lastTickStopwatchMs = -1;
        private static readonly System.Diagnostics.Stopwatch _tickStopwatch = System.Diagnostics.Stopwatch.StartNew();

        // July 22 item 1 — cumulative Hit%/Block% timelines for the new history
        // hover graphs. Own side sampled on the 3s cadence as "fired:hit" and
        // "dmgTakenInt:blocksSucc" pairs; opponent side sampled per cr_gstats
        // seq-advance (same rhythm their other telemetry arrives on). Damage
        // taken includes DOT ticks — unfilterable at TakeDamage (learning
        // #137), acceptable for a trend graph. Advisory, never in the HMAC.
        private static readonly List<string> localHitTimeline = new List<string>();    // cap 128
        private static readonly List<string> localBlockTimeline = new List<string>();  // cap 128
        private static readonly List<string> oppHitTimeline = new List<string>();      // cap 128
        private static readonly List<string> oppBlockTimeline = new List<string>();    // cap 128
        // Own fps at the 3s broadcast cadence — the 2v2 report ships this for
        // the local slot so all four players' fps series share one cadence
        // (the 1v1 report keeps using the 5s localFpsTimeline unchanged).
        private static readonly List<int> localFps3sTimeline = new List<int>();        // cap 128
        public static float LocalDamageTakenThisMatch { get; private set; }
        // Seconds-since-match-start per matchPointTimeline entry, kept in
        // LOCKSTEP with it (only appended when TimelineAppend actually
        // appended) so graph markers can't drift from the score pairs.
        private static readonly List<int> pointTimes = new List<int>();                // cap 64

        // July 22 item 7 — per-actor telemetry harvest for 4/3-player rooms
        // (2v2/1v2). The single-opponent fields above stay 1v1-shaped; this
        // dict keeps EVERY non-local peer's series so the 2v2 reporter can
        // ship all four players' telemetry. Keyed by Photon ActorNumber.
        private class PeerTelemetry
        {
            public int lastSeq = -1;
            public string lastRaw = "";
            public readonly List<int> fps = new List<int>();
            public readonly List<int> ping = new List<int>();
            public readonly List<string> hit = new List<string>();
            public readonly List<string> block = new List<string>();
        }
        private static readonly Dictionary<int, PeerTelemetry> peerTele = new Dictionary<int, PeerTelemetry>();

        // Pre-match card picks (cards picked before isTracking = true)
        // These get moved into localCards when OnMatchStarted fires
        private static List<MatchTracker.CardPickData> preMatchCards = new List<MatchTracker.CardPickData>();
        private static int preMatchPickCount = 0;

        // Room info
        private static string photonRoomId = "";
        private static string photonRegion = "";
        // The Photon master publishes one token per game. Both clients then
        // build the same durable report ID even when their local clocks cross
        // a second boundary at match start.
        private const string GAME_TOKEN_PROP_KEY = "cr_game_token";
        private const string GAME_TOKEN_CAP_PROP_KEY = "cr_game_token_v";
        private static string sharedGameToken = "";
        private static string previousGameToken = "";
        private static int matchStartServerTimestamp;

        // Game over
        private static bool gameOverReported = false;
        // Capture the mode while the room is still full. A disconnect can
        // shrink PlayerList before OnGameOver, but it must not erase the
        // surviving participant's exact input evidence.
        private static bool oneVOneMatchAtStart = false;
        private static bool macroEvidenceDispatched = false;

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
        // Review [4]: 1v2 per-sitting game tally (banner suppression only —
        // the 1v1 currentSeriesGames* counters deliberately skip ovt rooms).
        private static int ovtSoloWins = 0;
        private static int ovtDuoWins = 0;
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
        private static bool achJumped = false;             // jump keys (W/Space/Up) pressed during match (v1.30 Grounded)
        // v1.30 "Instinct": true once the player scrolls the card-pick selection
        // away from the left-most card during any of their picks this match.
        // Set from Plugin's RPCA_SetCurrentSelected postfix (local picker only).
        public static bool achLeftmostViolated = false;
        // v1.30 "Into the Deep End" (July 12 spec): Abyssal Countdown must be
        // ACTIVATED every round. Plugin's AbyssalCountdown.RPCA_Activate postfix
        // calls OnAbyssalActivatedLocal for the local player's activations; the
        // rounds-change branch flushes the per-round flag into the counter.
        private static int abyssalRoundsActivated = 0;
        private static bool abyssalActivatedThisRound = false;
        public static void OnAbyssalActivatedLocal()
        {
            if (!abyssalActivatedThisRound)
            {
                abyssalActivatedThisRound = true;
                Plugin.Log.LogInfo("[ACH] Abyssal activated this round");
            }
        }
        // Anti-cheat: per-match counts of the LOCAL player's combat inputs. Sent in the match report
        // so the server can flag a reporter who just sat idle the whole match (botting / AFK farming).
        // Counters reset in OnMatchStarted alongside the achievement flags.
        public static int LocalShotsThisMatch { get; private set; }
        public static int LocalBlocksThisMatch { get; private set; }
        // v1.29 — input-rate metrics for the Compare tab ("avg inputs/sec").
        // Events = discrete gameplay key and mouse-button downs during active
        // combat. Seconds = wall time actually spent alive in combat (pick phase /
        // death / menus excluded). Reset with the other per-match counters.
        public static int LocalKeysThisMatch { get; private set; }
        // #50 macro detector: count of 1-second windows whose gameplay-key event
        // rate exceeded MACRO_EVENTS_PER_SEC. Advisory — reported with the match.
        public static int LocalMacroSuspectSeconds { get; private set; }
        public static int LocalMacroPeakKeysPerSecond { get; private set; }
        public static int LocalMacroPeakClicksPerSecond { get; private set; }
        public static int LocalMacroPeakEventsPerSecond { get; private set; }
        public static string LocalMacroTimeline => string.Join(",", inputSuspectWindows.ToArray());
        public static float LocalActiveSecondsThisMatch { get; private set; }
        // v1.23 — hit/block lifetime counters.
        //   bullets_fired  — sum of Gun.numberOfProjectiles across every Gun.Attack call by the
        //                    local player (counts individual pellets/bullets, not trigger pulls;
        //                    auto-fire weapons firing 20 rounds count 20, not 1)
        //   bullets_hit    — damage events dealt to an opposing player by a real projectile
        //                    (damagingWeapon has a ProjectileHit component — excludes DOT ticks,
        //                    explosion splash, card-effect damage). Bounded per match by the
        //                    _hitsRemaining gate so bullets_hit ≤ bullets_fired always.
        //   blocks_activated  — user right-click blocks that fired off-cooldown (TryBlock)
        //   blocks_successful — right-click activations whose block (or Echo/ShieldCharge
        //                       follow-on) absorbed a projectile; max 1 per activation,
        //                       so succ <= act structurally (July 21 item 1 spec)
        public static int LocalBulletsFiredThisMatch { get; private set; }
        public static int LocalBulletsHitThisMatch { get; private set; }
        public static int LocalBlocksActivatedThisMatch { get; private set; }
        public static int LocalBlocksSuccessfulThisMatch { get; private set; }

        // First-fire-per-match log lines let us confirm Harmony patches attach and fire without
        // spamming on every event. Reset in OnMatchStarted alongside the counters.
        private static bool _loggedFirstFire, _loggedFirstHit, _loggedFirstBlockAct, _loggedFirstBlockOk;
        private static bool _loggedHitBudgetDrop;
        private static bool BlockDebugEnabled =>
            Plugin.ShowBlockDebug != null && Plugin.ShowBlockDebug.Value;

        // July 21 item 1 (Stan's spec): max ONE success credit per right-click
        // activation. Starts TRUE so an absorb arriving before any counted
        // activation can never credit — succ <= act becomes structural (the old
        // 1.0s time-dedup let Abyssal-style auto-absorbs produce succ > act).
        private static bool _activationSuccessCredited = true;

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
            // Bug #77 (Stan's manual count: hits understated by ~1 per round
            // won): NO inPickPhase gate here. The round-ending kill blow runs
            // vanilla's RPCA_DoHit body -> death -> round over -> "PICK
            // PHASE" logged (which flips inPickPhase=true via the log hook)
            // BEFORE our Postfix executes — so the old gate silently dropped
            // exactly the kill shot of every round. A real bullet impact is a
            // hit regardless of phase; nothing can be FIRED during the pick
            // phase anyway (the fired-side gate stays), so this can't inflate.
            if (!isTracking) return;
            if (_hitsRemaining <= 0)
            {
                // Budget exhausted = more counted impacts than trigger pulls
                // (splash/echo artifacts). Keep detailed diagnostics opt-in and
                // emit at most once per match so combat never becomes log I/O.
                if (BlockDebugEnabled && !_loggedHitBudgetDrop)
                {
                    _loggedHitBudgetDrop = true;
                    Plugin.Log.LogInfo($"[HIT-DROP] budget exhausted (fired={LocalBulletsFiredThisMatch} hit={LocalBulletsHitThisMatch})");
                }
                return;
            }
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
            _activationSuccessCredited = false;   // each right-click arms exactly one success credit
            if (!BlockDebugEnabled)
            {
                if (!_loggedFirstBlockAct) { _loggedFirstBlockAct = true; Plugin.Log.LogInfo("[STATS] first block activation this match"); }
                return;
            }
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
            // July 22 item 1: cumulative damage taken feeds the Block% graph.
            if (damage > 0f && damage < 10000f) LocalDamageTakenThisMatch += damage;
            if (!BlockDebugEnabled) return;
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
        public static void OnLocalBlockSuccessful(bool userChain)
        {
            if (!isTracking || inPickPhase) return;
            LocalBlockRawAbsorbs++;
            bool debug = BlockDebugEnabled;
            if (debug) LastBlockAbsorbTime = Time.time;
            if (!userChain)
            {
                // Abyssal BlinkStep / ExtraBlock / Shields Up wiring / revive
                // blocks — no right-click origin, counts NOWHERE (Stan's spec).
                LocalBlockDedupeDrops++;
                if (debug)
                {
                    LastBlockEventLabel = "ABSORB (auto-block, not counted)";
                    Plugin.Log.LogInfo($"[BLOCK-DBG] ABSORB-NONUSER  raw={LocalBlockRawAbsorbs}  credited={LocalBlocksSuccessfulThisMatch}");
                }
                return;
            }
            if (_activationSuccessCredited)
            {
                // This right-click already earned its 1 credit (multi-pellet
                // absorb, or the initial block AND its echo both absorbing).
                LocalBlockDedupeDrops++;
                if (debug)
                {
                    LastBlockEventLabel = "ABSORB (already credited)";
                    Plugin.Log.LogInfo($"[BLOCK-DBG] ABSORB-DEDUP  raw={LocalBlockRawAbsorbs}  credited={LocalBlocksSuccessfulThisMatch}");
                }
                return;
            }
            _activationSuccessCredited = true;
            LocalBlocksSuccessfulThisMatch++;
            if (debug)
            {
                LastBlockSuccessfulTime = Time.time;
                LastBlockEventLabel = $"SUCCESSFUL #{LocalBlocksSuccessfulThisMatch}";
                Plugin.Log.LogInfo($"[BLOCK-DBG] SUCCESS    act={LocalBlocksActivatedThisMatch}  succ={LocalBlocksSuccessfulThisMatch}  raw={LocalBlockRawAbsorbs}  drops={LocalBlockDedupeDrops}");
            }
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
        // One tally per series, whichever path observes the completion first.
        // The server-confirmed path only runs on the REPORTER (lower Steam ID
        // reports), so the other player's session series count sat at 0-0 all
        // session (SpyD's report). The local BO3-threshold path below now also
        // counts, and this flag keeps the two from double-counting.
        private static bool sessionSeriesCounted = false;
        public static void IncrementSessionRankedSeries(bool won)
        {
            if (sessionSeriesCounted)
            {
                currentSeriesGamesWon = 0;
                currentSeriesGamesLost = 0;
                return;
            }
            sessionSeriesCounted = true;
            if (won) sessionRankedSeriesWins++; else sessionRankedSeriesLosses++;
            // Series ended -> reset the per-series game counter so the next
            // BO3 starts at 0-0 in the HUD.
            currentSeriesGamesWon = 0;
            currentSeriesGamesLost = 0;
            // Keep the HUD's lifetime "Total Series" H2H tally live: bump the
            // cached count and re-arm the server fetch for reconciliation.
            try { ApiClient.OnSeriesCompletedVsOpponent(opponentSteamId, won); } catch { }
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
        // One-shot per room so the toast can't spam on preflight retries.
        private static bool casualDowngradeNotified = false;
        public static void DowngradeToCasual(string reason)
        {
            bool wasRanked = matchIsRanked;
            matchIsRanked = false;
            if (wasRanked)
                Plugin.Log.LogInfo($"[POLL] Match downgraded to CASUAL ({reason})");
            // Bug #47: the toast must fire even when matchIsRanked was still false
            // (the eager preflight usually resolves BEFORE the opponent mod-check
            // flips the flag, so the old early-return swallowed the notification
            // and nobody learned their opponent had ranked disabled until they
            // noticed games missing from their history).
            if (casualDowngradeNotified) return;
            casualDowngradeNotified = true;
            try
            {
                string opp = string.IsNullOrEmpty(opponentDisplayName) ? "your opponent" : opponentDisplayName;
                CompetitiveUI.QueueNotification(
                    $"CASUAL match — {opp} has Ranked disabled (fix: F5 top row - Enable)",
                    new Color(0.85f, 0.8f, 0.5f), 12f);
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
            if (isTracking) TryRefreshSharedGameToken();
            PollRoomlessGameScene();
        }

        // ── Bug #79 / July 21 item 3: dead-matchmaking detection + AUTO-REQUEUE ──
        // Yesterday's watchdogs waited 30-45s then bailed to the MENU; Sid: way
        // too slow, and players want back in the QUEUE. New shape: detect the
        // dead state within ~1-12s (three predicates below), then run a small
        // state machine that kills any in-flight region sweep, NetworkRestarts
        // to a clean menu scene (the persistent host behaviour survives the
        // reload), and re-invokes vanilla's own QuickMatch() — the exact method
        // the menu button calls. Vanilla's invite pipeline proves restart-first
        // is mandatory: QuickMatch from a stale scene hangs WaitForConnect
        // forever (isConnectedToMaster never sets while still joined).
        //
        // Predicates (all excluded while: OfflineMode, mod pending room/slots,
        // LeavingForRanked, a live match, escape menu open, vanilla restart in
        // flight, or the machine already running):
        //   A. roomless game scene + sweep coroutine running  → 1s confirm
        //   B. roomless game scene, connection state STABLE 1.5s (a live sweep
        //      never sits still — prod logs show constant state churn) → 3s
        //   C. full vanilla room, 2+ players, game never started → 12s
        //      (legit window is ~3s: RPCA_FoundGame + 2.5s jingle)
        // Non-quickplay contexts (room codes, host, invite) skip the requeue
        // and get the old fast return-to-menu instead.
        private enum RqPhase { Idle, KillSweep, Restarting, AwaitMenu, Settle, Queue }
        private static RqPhase rqPhase = RqPhase.Idle;
        private static float rqPhaseAt;
        private static bool rqQuickmatch;          // detected context was vanilla quickplay
        private static bool rqForcedGoToMenu;
        private static int rqAttemptsWindow;
        private static float rqWindowStart = -1f;
        private static float roomlessSince = -1f;
        private static float fullRoomNoGameSince = -1f;
        private static object _lastClientState;
        private static float _clientStateChangedAt;

        private static void PollRoomlessGameScene()
        {
            try
            {
                if (rqPhase != RqPhase.Idle) { TickRequeueMachine(); return; }

                // Shared exclusions — any true resets all detection timers.
                bool excluded = PhotonNetwork.OfflineMode
                                || !string.IsNullOrEmpty(Plugin.PendingRankedRoom)
                                || Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0
                                || LeavingForRanked
                                || isTracking;
                try { excluded = excluded || EscapeMenuHandler.isEscMenu; } catch { }
                try { excluded = excluded || (NetworkConnectionHandler.instance != null && NetworkConnectionHandler.instance.m_restarting); } catch { }
                if (excluded) { roomlessSince = -1f; fullRoomNoGameSince = -1f; return; }

                // Track connection-state stability (predicate B discriminator).
                try
                {
                    var st = PhotonNetwork.NetworkClientState;
                    if (!st.Equals(_lastClientState)) { _lastClientState = st; _clientStateChangedAt = Time.unscaledTime; }
                }
                catch { }

                // A + B: game scene alive with no room.
                bool roomless = GM_ArmsRace.instance != null && !PhotonNetwork.InRoom;
                if (!roomless) roomlessSince = -1f;
                else
                {
                    if (roomlessSince < 0f) roomlessSince = Time.unscaledTime;
                    float held = Time.unscaledTime - roomlessSince;
                    bool sweep = QuickplayChurnAbandonGuardPatch.SweepActive;
                    bool stateStable = Time.unscaledTime - _clientStateChangedAt >= 1.5f;
                    if ((sweep && held >= 1f) || (!sweep && stateStable && held >= 3f))
                    {
                        FireRequeue(sweep ? "roomless+sweep" : "roomless-stable");
                        return;
                    }
                }

                // C: full vanilla room, game never started.
                bool fullNoGame = false;
                if (PhotonNetwork.InRoom && PhotonNetwork.CurrentRoom != null
                    && PhotonNetwork.CurrentRoom.PlayerCount >= 2
                    && GM_ArmsRace.instance == null)
                {
                    string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                    var props = PhotonNetwork.CurrentRoom.CustomProperties;
                    bool modRoom = rn.StartsWith("ranked_") || rn.StartsWith("sct-") || rn.StartsWith("ovt_")
                                   || (props != null && props.ContainsKey("cr_ff"));
                    fullNoGame = !modRoom;
                }
                if (!fullNoGame) { fullRoomNoGameSince = -1f; return; }
                if (fullRoomNoGameSince < 0f) { fullRoomNoGameSince = Time.unscaledTime; return; }
                if (Time.unscaledTime - fullRoomNoGameSince >= 12f)
                    FireRequeue("full-room-no-game");
            }
            catch { roomlessSince = -1f; fullRoomNoGameSince = -1f; }
        }

        private static void FireRequeue(string why)
        {
            roomlessSince = -1f; fullRoomNoGameSince = -1f;
            // Context fork: only vanilla quickplay searches get auto-requeued.
            int searching = 0;
            try { searching = (int)NetworkConnectionHandler.instance.m_searchingType; } catch { }
            rqQuickmatch = searching == 1
                           && (Plugin.AutoRequeueOnMatchmakingBug == null || Plugin.AutoRequeueOnMatchmakingBug.Value);
            // Loop cap: max 2 auto-requeues per rolling 5 minutes, else a
            // region/Photon outage would ping-pong the player forever.
            if (rqQuickmatch)
            {
                if (rqWindowStart < 0f || Time.unscaledTime - rqWindowStart > 300f)
                {
                    rqWindowStart = Time.unscaledTime; rqAttemptsWindow = 0;
                }
                if (++rqAttemptsWindow > 2)
                {
                    rqQuickmatch = false;
                    Plugin.Log.LogWarning("[QUICKPLAY-GUARD] requeue loop cap hit — returning to menu instead");
                    try { CompetitiveUI.ShowNotification("Matchmaking keeps failing - returning to menu. Please try again in a minute.", new Color(1f, 0.5f, 0.4f), 8f); } catch { }
                }
            }
            Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] dead matchmaking state ({why}) — {(rqQuickmatch ? "auto-requeue" : "returning to menu")}");
            if (rqQuickmatch)
            {
                try { CompetitiveUI.ShowNotification("Matchmaking bug detected - putting you back in the quickplay queue...", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
            }
            else
            {
                try { CompetitiveUI.ShowNotification("Connection was lost - returning to menu.", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
            }
            rqForcedGoToMenu = false;
            rqPhase = RqPhase.KillSweep;
            rqPhaseAt = Time.unscaledTime;
        }

        private static void TickRequeueMachine()
        {
            float now = Time.unscaledTime;
            // Abort if the mod's ranked flow claimed the connection mid-recovery.
            if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom) || Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0)
            {
                Plugin.Log.LogInfo("[QUICKPLAY-GUARD] requeue aborted — mod pending room armed");
                rqPhase = RqPhase.Idle;
                return;
            }
            switch (rqPhase)
            {
                case RqPhase.KillSweep:
                    QuickplayChurnAbandonGuardPatch.AbortSweep = true;
                    if (!QuickplayChurnAbandonGuardPatch.SweepActive || now - rqPhaseAt > 1f)
                    {
                        bool alreadyRestarting = false;
                        try { alreadyRestarting = NetworkConnectionHandler.instance != null && NetworkConnectionHandler.instance.m_restarting; } catch { }
                        if (alreadyRestarting)
                        {
                            // Pre-existing hung restart (the bug-#37 forever state):
                            // m_restarting is consumed and NetworkRestart would no-op.
                            // Disconnect + direct scene reload instead.
                            Plugin.Log.LogWarning("[QUICKPLAY-GUARD] vanilla restart already hung — Disconnect + GoToMenu fallback");
                            try { PhotonNetwork.Disconnect(); } catch { }
                            try { GameManager.instance.GoToMenu(); } catch { }
                            rqForcedGoToMenu = true;
                        }
                        else
                        {
                            try { NetworkConnectionHandler.instance.NetworkRestart(); } catch { }
                        }
                        rqPhase = RqPhase.AwaitMenu; rqPhaseAt = now;
                    }
                    break;

                case RqPhase.AwaitMenu:
                    bool menuReady = false;
                    try
                    {
                        menuReady = GM_ArmsRace.instance == null
                                    && !PhotonNetwork.InRoom
                                    && !PhotonNetwork.IsConnected
                                    && NetworkConnectionHandler.instance != null
                                    && !NetworkConnectionHandler.instance.m_restarting
                                    && MainMenuHandler.instance != null;
                    }
                    catch { }
                    if (menuReady) { rqPhase = RqPhase.Settle; rqPhaseAt = now; }
                    else if (now - rqPhaseAt > 12f)
                    {
                        if (!rqForcedGoToMenu)
                        {
                            Plugin.Log.LogWarning("[QUICKPLAY-GUARD] restart didn't land in 12s — Disconnect + GoToMenu fallback");
                            try { PhotonNetwork.Disconnect(); } catch { }
                            try { GameManager.instance.GoToMenu(); } catch { }
                            rqForcedGoToMenu = true;
                            rqPhaseAt = now;   // fresh 12s for the fallback
                        }
                        else
                        {
                            Plugin.Log.LogWarning("[QUICKPLAY-GUARD] recovery failed — giving up");
                            try { CompetitiveUI.ShowNotification("Couldn't recover automatically - please restart matchmaking from the menu.", new Color(1f, 0.5f, 0.4f), 8f); } catch { }
                            rqPhase = RqPhase.Idle;
                        }
                    }
                    break;

                case RqPhase.Settle:
                    if (now - rqPhaseAt >= 0.7f) { rqPhase = RqPhase.Queue; rqPhaseAt = now; }
                    break;

                case RqPhase.Queue:
                    rqPhase = RqPhase.Idle;
                    if (!rqQuickmatch) break;   // non-quickplay context: menu is the destination
                    try
                    {
                        if (PhotonNetwork.InRoom || PhotonNetwork.OfflineMode || GM_ArmsRace.instance != null) break;
                        try { CharacterCreatorHandler.instance?.CloseMenus(); } catch { }
                        try { MainMenuHandler.instance?.Close(); } catch { }
                        NetworkConnectionHandler.instance.QuickMatch();   // the real menu-button path
                        Plugin.Log.LogInfo("[QUICKPLAY-GUARD] re-entered quickplay queue after dead-state recovery");
                        try { CompetitiveUI.ShowNotification("Back in the quickplay queue - searching for an opponent.", new Color(0.5f, 1f, 0.6f), 5f); } catch { }
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] requeue failed: {ex.Message}");
                        try { CompetitiveUI.ShowNotification("Couldn't recover automatically - please restart matchmaking from the menu.", new Color(1f, 0.5f, 0.4f), 8f); } catch { }
                    }
                    break;
            }
        }

        /// <summary>Per-Unity-frame tick; counts frames + accumulates real time so we
        /// can report a true average FPS for this match. Cheap (no allocations, no
        /// reflection); also broadcasts the running average via Photon every ~3s so
        /// the opponent can read it. Only active while a match is being tracked.</summary>
        public static void TickFrame()
        {
            if (!isTracking) { _lastTickStopwatchMs = -1; return; }
            float dt = Time.unscaledDeltaTime;
            // July 21 item 2 — freeze detection BEFORE the dt>1 skip (that skip
            // used to discard exactly the evidence). unscaledDeltaTime carries
            // the gap on the resume frame; the independent Stopwatch cross-checks
            // any engine smoothing. Focused resume = window-drag signature.
            long nowMs = _tickStopwatch.ElapsedMilliseconds;
            if (_lastTickStopwatchMs >= 0)
            {
                float wallGap = (nowMs - _lastTickStopwatchMs) / 1000f;
                float gap = Math.Max(dt, wallGap);
                if (gap > 0.5f && !inPickPhase)
                {
                    localFreezeCount++;
                    localFreezeTotalSec += gap;
                    bool focused = false;
                    try { focused = Application.isFocused; } catch { }
                    if (focused) localFreezeFocusedCount++;
                    Plugin.Log.LogInfo($"[FREEZE-DIAG] gap={gap:F2}s dt={dt:F2} wall={wallGap:F2} focused={focused} n={localFreezeCount}");
                }
            }
            _lastTickStopwatchMs = nowMs;
            if (dt <= 0f || dt > 1f) return; // skip pause / first-frame outliers (freeze recorded above)
            fpsFrameCount++;
            fpsTimeAccum += dt;
            fpsBroadcastTimer += dt;
            // 5s fps timeline bucket (own side)
            tlFrames++; tlAccum += dt;
            if (tlAccum >= 5f)
            {
                if (localFpsTimeline.Count < 90)
                    localFpsTimeline.Add((int)Math.Round(tlFrames / (double)tlAccum));
                tlFrames = 0; tlAccum = 0f;
            }
            bcFrames++; bcAccum += dt;
            if (fpsBroadcastTimer >= 3f)
            {
                fpsBroadcastTimer = 0f;
                BroadcastFps();
                PollOpponentFps();
                SampleConnectionQuality();
                SampleOwnStatTimelines();
            }
            TickInputSampling(dt);
        }

        // July 21 item 2: Photon ping + receive-gap + opponent-heartbeat
        // sampling on the 3s cadence. Receive-gap >2s = our socket went silent
        // (the cheater-side NIC-cut tell); opp gstats seq frozen >8s while the
        // peer stays in PlayerList = victim-side view of the opponent's cut.
        private static void SampleConnectionQuality()
        {
            try
            {
                if (PhotonNetwork.OfflineMode || !PhotonNetwork.InRoom || !PhotonNetwork.IsConnected) return;
                int ping = PhotonNetwork.GetPing();
                if (ping > 0 && pingSamples.Count < 200) pingSamples.Add(ping);
                var client = PhotonNetwork.NetworkingClient;
                var peer = client != null ? client.LoadBalancingPeer : null;
                if (peer != null)
                {
                    // ConnectionTime and TimestampOfLastSocketReceive share the SAME
                    // per-peer Stopwatch base (peerBase.timeInt) — this is exactly what
                    // Photon's own VitalStatsToString / disconnect-timeout compute.
                    // (LocalTimeInMilliSeconds is Environment.TickCount — a DIFFERENT
                    // clock; mixing them read as system-uptime and fired falsely.)
                    int silent = peer.ConnectionTime - peer.TimestampOfLastSocketReceive;
                    if (silent > 2000)
                    {
                        if (!_recvGapOpen)
                        {
                            _recvGapOpen = true; localRecvGapCount++;
                            Plugin.Log.LogInfo($"[LAG-DIAG] recv gap open silent={silent}ms n={localRecvGapCount}");
                        }
                        if (silent > localRecvGapMaxMs) localRecvGapMaxMs = silent;
                    }
                    else _recvGapOpen = false;
                }
                if (lastOppGstatsSeq >= 0 && lastOppSeqAdvanceTime > 0f)
                {
                    float since = Time.unscaledTime - lastOppSeqAdvanceTime;
                    if (since > 8f)
                    {
                        if (!_oppHbGapOpen)
                        {
                            _oppHbGapOpen = true; oppHbGapCount++;
                            Plugin.Log.LogInfo($"[LAG-DIAG] opp heartbeat gap {since:F1}s n={oppHbGapCount}");
                        }
                    }
                    else _oppHbGapOpen = false;
                }
            }
            catch { }
        }

        // ── Per-frame input metrics (bug #50) ─────────────────────────────
        // Unity's GetKeyDown / GetMouseButtonDown / anyKeyDown are per-FRAME edge
        // triggers. The old sampling lived inside the 10 Hz poll, so it saw only
        // the frames the poll happened to land on: whole games recorded ~8 active
        // seconds and ~30 keys (proven in prod data — 294s game, 7.7s / 31 keys).
        // Sampling must run every frame; the combat gate (LocalAliveInCombatNow,
        // refreshed by the poll at 10 Hz) is plenty fresh for gating.
        //
        // Counted events per Sid's #50 spec: WASD + arrows + Space + left/right
        // click — gameplay inputs only (move / jump / shoot / block), never menu
        // keys, so KPS reads as combat input speed.
        private const int MACRO_EVENTS_PER_SEC = 25; // sustained superhuman rate
        private static float inputBucketTimer = 0f;
        private static int inputBucketCount = 0;
        private static int inputBucketKeyCount = 0;
        private static int inputBucketClickCount = 0;
        private static long inputBucketStartedAtMs = -1;
        // Compact suspect-only entries: elapsedSecond:keyRate:clickRate. Forty-
        // eight windows stay comfortably inside the 1024-character DB field.
        private static readonly List<string> inputSuspectWindows = new List<string>();
        private static float lastMacroLogAt = -999f;

        private static void TickInputSampling(float dt)
        {
            // Combat gate: alive, not pick phase / transitions (same flag the
            // achievements use). Reset the macro bucket across gaps so a burst
            // straddling a round transition can't join two half-buckets.
            if (!LocalAliveInCombatNow)
            {
                inputBucketTimer = 0f;
                inputBucketCount = 0;
                inputBucketKeyCount = 0;
                inputBucketClickCount = 0;
                inputBucketStartedAtMs = -1;
                return;
            }
            bool typingInChat = false;
            try { typingInChat = CompetitiveUI.IsChatInputOpen || NativeUI.IsOpen; } catch { }
            if (typingInChat)
            {
                inputBucketTimer = 0f;
                inputBucketCount = 0;
                inputBucketKeyCount = 0;
                inputBucketClickCount = 0;
                inputBucketStartedAtMs = -1;
                return;
            }

            LocalActiveSecondsThisMatch += dt;

            int keyDowns = 0;
            int clickDowns = 0;
            if (Input.GetKeyDown(KeyCode.W)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.A)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.S)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.D)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.Space)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.UpArrow)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.DownArrow)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.LeftArrow)) keyDowns++;
            if (Input.GetKeyDown(KeyCode.RightArrow)) keyDowns++;
            if (Input.GetMouseButtonDown(0))
            {
                clickDowns++;
                LocalShotsThisMatch++;
                if (!achFiredShot)
                {
                    achFiredShot = true;
                    Plugin.Log.LogInfo("[ACH] Player fired a shot");
                }
            }
            if (Input.GetMouseButtonDown(1))
            {
                clickDowns++;
                LocalBlocksThisMatch++;
            }
            int downs = keyDowns + clickDowns;
            if (downs > 0) LocalKeysThisMatch += downs;

            // Macro detector (#50): consecutive ~1-second buckets; a bucket beyond
            // MACRO_EVENTS_PER_SEC is past sustained human speed. Advisory
            // counter only — reported with the match, flagged server-side.
            long nowMs = _tickStopwatch.ElapsedMilliseconds;
            if (inputBucketStartedAtMs < 0) inputBucketStartedAtMs = nowMs;
            inputBucketTimer = (nowMs - inputBucketStartedAtMs) / 1000f;
            inputBucketCount += downs;
            inputBucketKeyCount += keyDowns;
            inputBucketClickCount += clickDowns;
            if (inputBucketTimer >= 1f)
            {
                float seconds = Mathf.Max(0.001f, inputBucketTimer);
                int keyRate = Mathf.RoundToInt(inputBucketKeyCount / seconds);
                int clickRate = Mathf.RoundToInt(inputBucketClickCount / seconds);
                int eventRate = Mathf.RoundToInt(inputBucketCount / seconds);
                if (keyRate > LocalMacroPeakKeysPerSecond) LocalMacroPeakKeysPerSecond = keyRate;
                if (clickRate > LocalMacroPeakClicksPerSecond) LocalMacroPeakClicksPerSecond = clickRate;
                if (eventRate > LocalMacroPeakEventsPerSecond) LocalMacroPeakEventsPerSecond = eventRate;
                if (eventRate >= MACRO_EVENTS_PER_SEC)
                {
                    LocalMacroSuspectSeconds++;
                    // Retain the most recent windows: end-of-match bursts are
                    // the most useful evidence and must not be displaced by a
                    // long macro-heavy opening.
                    if (inputSuspectWindows.Count >= 48)
                        inputSuspectWindows.RemoveAt(0);
                    int elapsed = Mathf.Max(0, Mathf.RoundToInt(LocalActiveSecondsThisMatch));
                    inputSuspectWindows.Add($"{elapsed}:{keyRate}:{clickRate}");
                    if (Time.realtimeSinceStartup - lastMacroLogAt > 10f)
                    {
                        lastMacroLogAt = Time.realtimeSinceStartup;
                        Plugin.Log.LogWarning($"[INPUT] macro-suspect second: {eventRate}/s gameplay events ({keyRate} keys/s, {clickRate} clicks/s; total suspect s: {LocalMacroSuspectSeconds})");
                    }
                    // The elected reporter may be the other player. Publish each
                    // threshold-breaking window immediately so the last 1-2
                    // seconds of a match cannot sit behind the normal 3s cadence.
                    BroadcastGstatsImmediate();
                }
                inputBucketTimer = 0f;
                inputBucketCount = 0;
                inputBucketKeyCount = 0;
                inputBucketClickCount = 0;
                inputBucketStartedAtMs = nowMs;
            }
        }

        // Item 4 (v1.30): opponent per-game combat stats, sniffed from their
        // cr_gstats Photon prop (same rhythm as FPS — they publish every ~3s
        // while the match runs, we keep the latest). "fired|hit|blkAct|blkSucc|keys|activeSecs".
        private const string GSTATS_PROP_KEY = "cr_gstats";
        public static int OppStatBulletsFired { get; private set; }
        public static int OppStatBulletsHit { get; private set; }
        public static int OppStatBlocksActivated { get; private set; }
        public static int OppStatBlocksSuccessful { get; private set; }
        public static int OppStatKeysPressed { get; private set; }
        public static float OppStatActiveSeconds { get; private set; }
        public static int OppStatMacroSuspectSeconds { get; private set; }
        public static int OppStatMacroPeakKeysPerSecond { get; private set; }
        public static int OppStatMacroPeakClicksPerSecond { get; private set; }
        public static int OppStatMacroPeakEventsPerSecond { get; private set; }
        public static string OppStatMacroTimeline { get; private set; } = "";

        private static string MacroTimelineForPeer()
        {
            int count = Math.Min(16, inputSuspectWindows.Count);
            if (count <= 0) return "";
            int start = inputSuspectWindows.Count - count;
            var sb = new System.Text.StringBuilder(count * 12);
            for (int i = 0; i < count; i++)
            {
                if (i > 0) sb.Append(',');
                sb.Append(inputSuspectWindows[start + i]);
            }
            return sb.ToString();
        }

        private static string BuildGstatsPayload(int recentFps, bool advanceSequence)
        {
            if (advanceSequence) gstatsSeq++;
            int curPing = 0;
            try
            {
                if (!PhotonNetwork.OfflineMode && PhotonNetwork.IsConnected)
                    curPing = PhotonNetwork.GetPing();
            }
            catch { }
            return
                $"{LocalBulletsFiredThisMatch}|{LocalBulletsHitThisMatch}|{LocalBlocksActivatedThisMatch}|{LocalBlocksSuccessfulThisMatch}|{LocalKeysThisMatch}|{LocalActiveSecondsThisMatch.ToString("F0", System.Globalization.CultureInfo.InvariantCulture)}" +
                $"|{recentFps}|{gstatsSeq}|{localFreezeCount}|{localFreezeFocusedCount}|{localRecvGapCount}|{curPing}|{(int)LocalDamageTakenThisMatch}" +
                $"|{LocalMacroSuspectSeconds}|{LocalMacroPeakKeysPerSecond}|{LocalMacroPeakClicksPerSecond}|{LocalMacroPeakEventsPerSecond}|{MacroTimelineForPeer()}";
        }

        private static void BroadcastGstatsImmediate()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.LocalPlayer == null) return;
                var props = new Hashtable();
                // Keep the heartbeat sequence stable. PollOpponentFps parses the
                // macro fields before its seq gate, so the changed payload still
                // updates exact evidence without adding fake FPS/heartbeat samples.
                // Preserve the most recent real FPS sample. Replacing the
                // property with zero here can erase that sample before a peer
                // observes the sequence which owns it.
                props[GSTATS_PROP_KEY] = BuildGstatsPayload(lastBroadcastRecentFps, false);
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
            }
            catch { }
        }

        private static void BroadcastFps()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.LocalPlayer == null) return;
                var props = new Hashtable();
                int avg = LocalAvgFps;
                if (avg > 0) props[FPS_PROP_KEY] = avg;
                // Per-game combat stats ride the same publish (item 4) — the
                // reporter includes the opponent's numbers in the match report
                // so both sides of the history row can show hit/block/KPS.
                // July 21 item 2: fields 7-11 = recentFps (3s window), seq
                // (heartbeat), freezeCount, freezeFocusedCount, recvGapCount.
                // Old clients parse >=6 and ignore extras (verified).
                int recentFps = bcAccum > 0.5f ? (int)Math.Round(bcFrames / (double)bcAccum) : 0;
                bcFrames = 0; bcAccum = 0f;
                if (recentFps > 0) lastBroadcastRecentFps = recentFps;
                if (recentFps > 0 && isTracking && localFps3sTimeline.Count < 128)
                    localFps3sTimeline.Add(recentFps);
                // Field 12 = instantaneous ping; field 13 = cumulative damage
                // taken. Append-only ordering keeps old clients compatible.
                props[GSTATS_PROP_KEY] = BuildGstatsPayload(recentFps, true);
                if (props.Count > 0)
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
                // First non-local mod-reporting peer stays the single "opponent"
                // for the 1v1-shaped fields; EVERY peer is harvested into the
                // per-actor dict for 4/3-player reports (July 22 item 7).
                bool primaryTaken = false;
                foreach (var p in players)
                {
                    if (p == null || p.IsLocal || p.CustomProperties == null) continue;
                    bool sawModProps = false;
                    if (p.CustomProperties.ContainsKey(GSTATS_PROP_KEY))
                    {
                        sawModProps = true;
                        string raw = p.CustomProperties[GSTATS_PROP_KEY] as string ?? "";
                        HarvestPeerTelemetry(p.ActorNumber, raw);
                        if (!primaryTaken)
                        {
                            try
                            {
                                var parts = raw.Split('|');
                                if (parts.Length >= 6)
                                {
                                    OppStatBulletsFired = int.Parse(parts[0]);
                                    OppStatBulletsHit = int.Parse(parts[1]);
                                    OppStatBlocksActivated = int.Parse(parts[2]);
                                    OppStatBlocksSuccessful = int.Parse(parts[3]);
                                    OppStatKeysPressed = int.Parse(parts[4]);
                                    OppStatActiveSeconds = float.Parse(parts[5], System.Globalization.CultureInfo.InvariantCulture);
                                }
                                // Fields 14-18 carry the peer's macro evidence.
                                // Without them only the elected reporter's own
                                // input windows survive into the match report.
                                if (parts.Length >= 18)
                                {
                                    OppStatMacroSuspectSeconds = int.Parse(parts[13]);
                                    OppStatMacroPeakKeysPerSecond = int.Parse(parts[14]);
                                    OppStatMacroPeakClicksPerSecond = int.Parse(parts[15]);
                                    OppStatMacroPeakEventsPerSecond = int.Parse(parts[16]);
                                    OppStatMacroTimeline = parts[17] ?? "";
                                }
                                // July 21 item 2: extended telemetry (new clients only).
                                if (parts.Length >= 11)
                                {
                                    int seq = int.Parse(parts[7]);
                                    if (seq != lastOppGstatsSeq)
                                    {
                                        lastOppGstatsSeq = seq;
                                        lastOppSeqAdvanceTime = Time.unscaledTime;
                                        int rf = int.Parse(parts[6]);
                                        if (rf > 0 && oppFpsTimeline.Count < 128) oppFpsTimeline.Add(rf);
                                        // Field 12 (July 22 item 3) — absent on 11-field clients.
                                        if (parts.Length >= 12)
                                        {
                                            int op = int.Parse(parts[11]);
                                            if (op > 0 && oppPingTimeline.Count < 128) oppPingTimeline.Add(op);
                                        }
                                        // July 22 item 1: cumulative pair series.
                                        // Review [3]: regression = stale previous-game
                                        // sample got in first — restart the lists.
                                        int curFired;
                                        if (int.TryParse(parts[0], out curFired)
                                            && oppHitTimeline.Count > 0 && curFired < LastPairFirst(oppHitTimeline))
                                        {
                                            oppHitTimeline.Clear();
                                            oppBlockTimeline.Clear();
                                        }
                                        if (oppHitTimeline.Count < 128)
                                            oppHitTimeline.Add(parts[0] + ":" + parts[1]);
                                        // Field 13 (dmg taken) — absent on 12-field clients;
                                        // no mixed-shape pairs, so skip block entirely then.
                                        if (parts.Length >= 13 && oppBlockTimeline.Count < 128)
                                            oppBlockTimeline.Add(parts[12] + ":" + parts[3]);
                                    }
                                    oppFreezeCount = int.Parse(parts[8]);
                                    oppFreezeFocusedCount = int.Parse(parts[9]);
                                    oppRecvGapCount = int.Parse(parts[10]);
                                }
                                else if (parts.Length >= 6 && parts[0] == "0" && parts[1] == "0")
                                {
                                    // Review [3]: the peer's 6-field match-start reset
                                    // ("0|0|0|0|0|0") never reaches the >=11 branch —
                                    // treat it as the new-game signal so a stale
                                    // previous-game sample can't survive it.
                                    if (oppHitTimeline.Count > 0 || oppBlockTimeline.Count > 0)
                                    {
                                        oppHitTimeline.Clear();
                                        oppBlockTimeline.Clear();
                                    }
                                    OppStatMacroSuspectSeconds = 0;
                                    OppStatMacroPeakKeysPerSecond = 0;
                                    OppStatMacroPeakClicksPerSecond = 0;
                                    OppStatMacroPeakEventsPerSecond = 0;
                                    OppStatMacroTimeline = "";
                                }
                            }
                            catch { }
                        }
                    }
                    if (p.CustomProperties.ContainsKey(FPS_PROP_KEY))
                    {
                        sawModProps = true;
                        if (!primaryTaken)
                        {
                            try { opponentAvgFps = Convert.ToInt32(p.CustomProperties[FPS_PROP_KEY]); }
                            catch { }
                        }
                    }
                    if (sawModProps) primaryTaken = true;
                }
            }
            catch { }
        }

        // Review [3]: first field ("fired" / "dmgTaken") of the last appended
        // cumulative pair, or -1 when the list is empty. Cumulative counters
        // only grow within a game — a lower incoming value means the sample we
        // hold is from the PREVIOUS game (rematch race: the peer's reset
        // broadcast can land ~3s after our OnMatchStarted cleared the lists).
        private static int LastPairFirst(List<string> pairs)
        {
            if (pairs.Count == 0) return -1;
            string last = pairs[pairs.Count - 1];
            int ci = last.IndexOf(':');
            int v;
            if (ci > 0 && int.TryParse(last.Substring(0, ci), out v)) return v;
            return -1;
        }

        // July 22 item 1: own cumulative pair samples on the 3s cadence.
        private static void SampleOwnStatTimelines()
        {
            if (localHitTimeline.Count < 128)
                localHitTimeline.Add(LocalBulletsFiredThisMatch + ":" + LocalBulletsHitThisMatch);
            if (localBlockTimeline.Count < 128)
                localBlockTimeline.Add((int)LocalDamageTakenThisMatch + ":" + LocalBlocksSuccessfulThisMatch);
        }

        // July 22 item 7: per-actor cumulative harvest (all peers, any room —
        // consumed by the 2v2 reporter; trivial memory in 1v1 rooms).
        private static void HarvestPeerTelemetry(int actorNumber, string raw)
        {
            try
            {
                var parts = raw.Split('|');
                if (parts.Length < 8)
                {
                    // Review [3]: the 6-field "0|0|0|0|0|0" match-start reset
                    // is the new-game signal — drop any stale entry so the new
                    // game's harvest (and lastRaw counters) start clean.
                    if (parts.Length >= 6 && parts[0] == "0" && parts[1] == "0")
                        peerTele.Remove(actorNumber);
                    return; // otherwise: needs the seq heartbeat (field 8)
                }
                PeerTelemetry t;
                if (!peerTele.TryGetValue(actorNumber, out t))
                {
                    t = new PeerTelemetry();
                    peerTele[actorNumber] = t;
                }
                t.lastRaw = raw;
                int seq = int.Parse(parts[7]);
                if (seq == t.lastSeq) return;
                t.lastSeq = seq;
                // Review [3]: cumulative regression = stale previous-game
                // sample seeded this entry (rematch race) — restart it.
                int curFired;
                if (int.TryParse(parts[0], out curFired)
                    && t.hit.Count > 0 && curFired < LastPairFirst(t.hit))
                {
                    t.fps.Clear(); t.ping.Clear(); t.hit.Clear(); t.block.Clear();
                }
                int rf = int.Parse(parts[6]);
                if (rf > 0 && t.fps.Count < 128) t.fps.Add(rf);
                if (parts.Length >= 12)
                {
                    int op = int.Parse(parts[11]);
                    if (op > 0 && t.ping.Count < 128) t.ping.Add(op);
                }
                if (t.hit.Count < 128) t.hit.Add(parts[0] + ":" + parts[1]);
                if (parts.Length >= 13 && t.block.Count < 128)
                    t.block.Add(parts[12] + ":" + parts[3]);
            }
            catch { }
        }

        /// <summary>Latest harvested telemetry for a peer by actor number, or null.
        /// Consumed by TryReportTeamMatch when assembling per-slot telemetry.</summary>
        internal static bool TryGetPeerTelemetry(int actorNumber,
            out string fpsTl, out string pingTl, out string hitTl, out string blockTl,
            out int[] counters)
        {
            fpsTl = pingTl = hitTl = blockTl = null;
            counters = null;
            PeerTelemetry t;
            if (!peerTele.TryGetValue(actorNumber, out t) || string.IsNullOrEmpty(t.lastRaw)) return false;
            try
            {
                var parts = t.lastRaw.Split('|');
                if (parts.Length < 6) return false;
                fpsTl = string.Join(",", t.fps);
                pingTl = string.Join(",", t.ping);
                hitTl = string.Join(",", t.hit);
                blockTl = string.Join(",", t.block);
                counters = new int[] {
                    int.Parse(parts[0]), int.Parse(parts[1]),
                    int.Parse(parts[2]), int.Parse(parts[3]),
                    int.Parse(parts[4]),
                    (int)float.Parse(parts[5], System.Globalization.CultureInfo.InvariantCulture)
                };
                return true;
            }
            catch { return false; }
        }

        // Item 4: per-game scoring timeline for the history hover graph. Each
        // entry is cumulative "p1Total:p2Total" where total = rounds*2 + points
        // (monotonic across round resets). Reporter-side; capped at 64 events.
        private static readonly List<string> matchPointTimeline = new List<string>();
        // Returns true only when an entry was actually appended — the caller
        // pushes the matching pointTimes stamp on true, keeping the two lists
        // in lockstep (dedup/cap drops must drop the timestamp too, or the
        // graph markers drift off the score pairs).
        private static bool TimelineAppend(int p1r, int p1p, int p2r, int p2p)
        {
            if (matchPointTimeline.Count >= 64) return false;
            // pts>=2 only occurs at game end (the winning point lands and the game
            // stops before the round-conversion reset) — those 2 points are already
            // counted in the rounds figure, so zero them or the final graph step
            // double-counts a whole round (same bug as the "6-x" score display).
            if (p1p >= 2) p1p = 0;
            if (p2p >= 2) p2p = 0;
            string entry = $"{p1r * 2 + p1p}:{p2r * 2 + p2p}";
            if (matchPointTimeline.Count > 0 && matchPointTimeline[matchPointTimeline.Count - 1] == entry) return false;
            matchPointTimeline.Add(entry);
            return true;
        }

        // July 22 item 1: stamp the moment a timeline entry landed, in seconds
        // since match start (marker X positions on the hover graphs).
        private static void StampPointTime()
        {
            if (pointTimes.Count >= 64) return;
            int secs = 0;
            try { secs = (int)Math.Max(0, (DateTime.UtcNow - matchStartTime).TotalSeconds); }
            catch { }
            pointTimes.Add(secs);
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
                                || rname.StartsWith("sct-")
                                || rname.StartsWith("ovt_");
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
                // Capability negotiation keeps mixed-version rooms on the
                // local-time report-ID fallback. A shared token is advertised
                // only when both 1v1 participants understand it.
                try
                {
                    var existingRoomProps =
                        PhotonNetwork.CurrentRoom?.CustomProperties;
                    if (existingRoomProps != null
                        && existingRoomProps.ContainsKey(GAME_TOKEN_PROP_KEY))
                    {
                        string existingRaw =
                            existingRoomProps[GAME_TOKEN_PROP_KEY]?.ToString()
                            ?? "";
                        int separator = existingRaw.IndexOf(':');
                        string existingToken = separator > 0
                            ? existingRaw.Substring(0, separator) : existingRaw;
                        if (Regex.IsMatch(existingToken, @"^\d{6}$"))
                            previousGameToken = existingToken;
                    }
                    if (PhotonNetwork.LocalPlayer != null)
                    {
                        var capProps = new Hashtable();
                        // Player properties persist across Photon rooms. Bind
                        // the capability to this room + actor assignment so a
                        // stale value (including a same-room reconnect) cannot
                        // make the master publish before the peer has joined.
                        capProps[GAME_TOKEN_CAP_PROP_KEY] =
                            photonRoomId + ":"
                            + PhotonNetwork.LocalPlayer.ActorNumber.ToString(
                                System.Globalization.CultureInfo.InvariantCulture);
                        PhotonNetwork.LocalPlayer.SetCustomProperties(capProps);
                    }
                }
                catch { }
                playersIdentified = false;
                opponentSteamIdResolved = false;
                opponentRankChecked = false;
                opponentIsRanked = false;
                matchIsRanked = false;
                casualDowngradeNotified = false;
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
                                    || rname.StartsWith("sct-")
                                || rname.StartsWith("ovt_");
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
                ovtSoloWins = 0; ovtDuoWins = 0;   // review [4]: 1v2 banner tally
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

            if (inRoom && isTracking && oneVOneMatchAtStart)
                TryRefreshSharedGameToken();

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

                    // If this client is the leaver while the opponent already
                    // has a reportable DC-win lead, preserve its exact local
                    // macro sample before ResetMatchState clears the counters.
                    if (oppRounds >= 4
                        && oppRounds > localRounds)
                        TryDispatchMacroEvidence();
                    else if (!opponentDCReported
                        && localRounds >= 4
                        && oppRounds >= 4)
                    {
                        // This client is the one leaving a tied match. The
                        // remaining opponent will persist the awarded 5-4, so
                        // send our exact sampler against that same final score.
                        int evidenceP1Rounds = p1Rounds;
                        int evidenceP2Rounds = p2Rounds;
                        if (localTeamId == 0) evidenceP2Rounds = 5;
                        else if (localTeamId == 1) evidenceP1Rounds = 5;
                        TryDispatchMacroEvidence(
                            null, evidenceP1Rounds, evidenceP2Rounds);
                    }

                    if (LeavingForRanked)
                    {
                        // We initiated the leave for a ranked match — cancel, don't count
                        Plugin.Log.LogInfo($"[POLL] === {matchType} Canceled === Left for ranked queue at {localRounds}-{oppRounds} (not counted)");
                        CompetitiveUI.ShowNotification("Left match for ranked queue", new Color(0.4f, 0.8f, 1f));
                        LeavingForRanked = false;
                    }
                    else if (opponentDCReported
                        && localRounds >= 4 && oppRounds >= 4)
                    {
                        // Both at match point and someone DC'd — give the win to the
                        // local player (the one still in the room). Closes the
                        // 4-4 DC exploit (where the DC'er would otherwise get the win
                        // because they had ≥4 rounds at disconnect time).
                        Plugin.Log.LogInfo($"[POLL] === {matchType} DC Win (4-4 tiebreak) === Opponent DC'd at {localRounds}-{oppRounds}");
                        int winnerTeam = localTeamId;
                        // Persist the awarded tiebreak in the report itself.
                        // A tied 4-4 body is invalid and also prevents exact
                        // macro evidence from correlating to the recorded win.
                        if (winnerTeam == 0) p1Rounds = 5;
                        else if (winnerTeam == 1) p2Rounds = 5;
                        OnGameOver(winnerTeam);
                    }
                    else if (opponentDCReported && localRounds >= 4)
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
                // A series id is only meaningful for the pairing it was preflighted
                // for. Carrying it across rooms would let the ranked-override at
                // report time force-rank a later casual game vs an unrelated
                // (possibly vanilla) opponent.
                ApiClient.ActiveRankedSeriesId = null;
                // Same rule for the 1v2 sitting: leaving the ovt_ room ends it.
                // Only the reporter's client clears these at series completion;
                // the other two would otherwise carry a stale series id + slot
                // to the menu, where the tab reads them as a pending lock.
                if ((photonRoomId ?? "").StartsWith("ovt_"))
                {
                    ApiClient.ActiveOvt1v2SeriesId = null;
                    try { Plugin.ClearPendingOvtSlot(); } catch { }
                }
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
            if (inRoom && !rankedRoomStallHandled
                && (photonRoomId.StartsWith("ranked_") || photonRoomId.StartsWith("sct-")
                    || photonRoomId.StartsWith("ovt_")))
            {
                // Tournament rooms get a much longer solo window: the opponent
                // has a 5-10 min no-show grace server-side, so bailing at 60s
                // would bounce us out while they're still legitimately loading
                // in. 6 min covers the grace; after that the server has already
                // forfeited them and there's nobody to wait for. (item 3)
                // 1v2 rooms need THREE arrivals and have no server assembly
                // timeout (the 2v2 spawn-confirm machinery doesn't exist for
                // ovt), so this watchdog is the only thing standing between a
                // no-show and two players waiting forever — slightly longer
                // window since two other clients have to load in.
                bool isTournamentRoom = photonRoomId.StartsWith("sct-");
                bool isOvtRoom = photonRoomId.StartsWith("ovt_");
                double bailAfter = isTournamentRoom ? 360 : (isOvtRoom ? 90 : 60);
                double warnAfter = isTournamentRoom ? 90 : (isOvtRoom ? 35 : 25);
                int fullAt = isOvtRoom ? 3 : 2;
                int pc = 0;
                try { pc = PhotonNetwork.CurrentRoom?.PlayerCount ?? 0; } catch { }
                if (pc >= fullAt) rankedRoomEverFull = true;
                if (!rankedRoomEverFull && !isTracking)
                {
                    double waited = (DateTime.UtcNow - roomJoinTime).TotalSeconds;
                    if (!rankedRoomStallWarned && waited >= warnAfter)
                    {
                        rankedRoomStallWarned = true;
                        CompetitiveUI.ShowNotification(isTournamentRoom
                            ? "Opponent hasn't connected yet — they have a few minutes of grace. Hang tight..."
                            : isOvtRoom
                            ? "Waiting for all 3 players to connect — hang tight..."
                            : "Opponent hasn't connected yet — hang tight...", new Color(1f, 0.8f, 0.3f), 6f);
                    }
                    if (waited >= bailAfter)
                    {
                        rankedRoomStallHandled = true;
                        Plugin.Log.LogWarning($"[QUEUE-STALL] Room {photonRoomId} never filled ({pc}/{fullAt}) after {(int)waited}s — returning to menu (no match started, no penalty)");
                        CompetitiveUI.ShowNotification(isTournamentRoom
                            ? "Opponent never showed — their no-show forfeit should be recorded. Returning to menu."
                            : isOvtRoom
                            ? "1v2 lobby never filled — returning to menu. Requeue when ready."
                            : "Opponent failed to join — returning to menu. Requeue when ready.", new Color(1f, 0.5f, 0.4f), 10f);
                        // Leaving the ovt queue dissolves the never-filled lock
                        // server-side (cancels the series, resets the other two
                        // rows to searching) and clears the local lock state —
                        // otherwise the husk re-feeds this dead room forever.
                        if (isOvtRoom) { try { ApiClient.OvtLeaveQueue(); } catch { } }
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
                // never 1v1-preflight there. Same for 1v2 (ovt_) rooms: the
                // ovt series exists from the queue lock, and a 1v1 preflight
                // here spawned phantom ranked_series rows pairing arbitrary
                // trio members (proven in the July 17 first live 1v2 session:
                // six phantom series — the one 1v1 path #146/#149 didn't
                // gate). ranked_* / sct-* rooms ARE allowed (v1.28.3, #36):
                // series 1 already has ActiveRankedSeriesId from the
                // queue/tournament flow (so the id-empty gate above skips
                // them), but REMATCH series in the same room need this
                // preflight to exist before game 1 ends or they're born
                // bet-locked. Server side is idempotent find-or-create.
                bool is2v2Eager = inCrFfEager || rNameEager.StartsWith("team_")
                    || rNameEager.StartsWith("ovt_");
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
                        // Same for 1v2 (ovt_) rooms — six phantom series in the
                        // July 17 first live session came through this site.
                        bool inOvtRoom = false;
                        try { inOvtRoom = (PhotonNetwork.CurrentRoom?.Name ?? "").StartsWith("ovt_"); } catch { }
                        if (matchIsRanked && !inCrFf && !inOvtRoom && !seriesPreflightSent
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
                    // Review MEDIUM: this is a 1v1-only leave-% path. In a multi-player
                    // mod room (2v2 team_ / 1v2 ovt_) it would fire ReportDisconnect
                    // against whichever single opponentSteamId the poll latched onto —
                    // a phantom 1v1 leave incident. Those modes have their own DC
                    // handling; skip the 1v1 path entirely for them.
                    string rnDc = PhotonNetwork.CurrentRoom?.Name ?? "";
                    bool multiPlayerMode = rnDc.StartsWith("team_") || rnDc.StartsWith("ovt_");
                    if (multiPlayerMode) { wasInRoom = inRoom; return; }

                    int playerCount = PhotonNetwork.PlayerList?.Length ?? 0;
                    if (playerCount >= 2)
                        opponentWasPresent = true;

                    // The opponent is back (Photon rejoin after a blip). Clear the
                    // latch: a stale one lets THIS client take the 4-4 DC-win branch
                    // when IT later leaves, i.e. the leaver awards itself the win —
                    // the exact exploit that branch exists to close. Only a genuine
                    // return to 2 players clears it, so the normal
                    // "opponent left, then I left" sequence (count stays 1) is
                    // unaffected.
                    if (playerCount >= 2 && opponentDCReported)
                    {
                        opponentDCReported = false;
                        Plugin.Log.LogInfo("[POLL] Opponent returned to the room — cleared stale DC latch");
                    }

                    if (opponentWasPresent && playerCount <= 1 && !opponentDCReported)
                    {
                        opponentDCReported = true;
                        int localR = localTeamId == 0 ? p1Rounds : p2Rounds;
                        int oppR = localTeamId == 0 ? p2Rounds : p1Rounds;
                        int totalPts = p1Points + p2Points;
                        int seriesGames = p1Rounds + p2Rounds; // games already won this series

                        // July 22 item 2 (bug #81): tell the remaining player what
                        // happens next, right at detection — previously the only
                        // toast fired after THEY quit out, mid menu-transition.
                        // The vanilla game hangs on the absent picker (NRE storm),
                        // so Esc-to-menu is the actionable advice.
                        try
                        {
                            string _dcName = string.IsNullOrEmpty(opponentDisplayName) ? "Opponent" : opponentDisplayName;
                            string _dcMsg = localR >= 4
                                ? $"{_dcName} disconnected at {localR}-{oppR} — leave to the menu, you get the win"
                                : $"{_dcName} disconnected at {localR}-{oppR} — leave to the menu, game won't be counted";
                            CompetitiveUI.ShowNotification(_dcMsg, new Color(1f, 0.65f, 0.2f), 10f);
                        }
                        catch { }

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

        /// <summary>July 22 item 2 (bug #81): universal "player left" banner.
        /// Called from Cr2v2DiagCallbacks.OnPlayerLeftRoom BEFORE its mode gate,
        /// so every mode (casual/ranked/2v2/1v2) and every remaining seat gets
        /// it. Display-only — no report path runs here. Suppressed outside a
        /// live match unless an unfinished 1v1 series is in progress (clean
        /// post-game leaves and lobby churn stay silent).</summary>
        public static void NotifyPlayerLeftRoom(Photon.Realtime.Player p)
        {
            try
            {
                if (p == null || PhotonNetwork.OfflineMode) return;   // learning #122
                string roomName = PhotonNetwork.CurrentRoom?.Name ?? "";
                bool ovtRoom = roomName.StartsWith("ovt_");
                bool teamRoom = ovtRoom || roomName.StartsWith("team_")
                                || (PhotonNetwork.CurrentRoom?.CustomProperties?.ContainsKey("cr_ff") ?? false);
                bool seriesInProgress = !ovtRoom
                                        && CurrentSeriesGamesWon + CurrentSeriesGamesLost >= 1
                                        && CurrentSeriesGamesWon < 2 && CurrentSeriesGamesLost < 2;
                // Review [4]: ovt rooms track their own tally (the 1v1
                // counters skip them) — gate on the live series id too so a
                // completed sitting's post-series leaves stay silent-ish.
                bool ovtSeriesInProgress = ovtRoom
                                           && !string.IsNullOrEmpty(ApiClient.ActiveOvt1v2SeriesId)
                                           && ovtSoloWins + ovtDuoWins >= 1
                                           && ovtSoloWins < 2 && ovtDuoWins < 2;
                bool midGame = isTracking && !gameOverReported;
                if (!midGame && !seriesInProgress && !ovtSeriesInProgress) return;

                // Resolve a display name: styled NickName stripped, then the
                // cached 1v1 opponent name via u_id, then a neutral fallback.
                string name = "";
                try { name = StripRichText(p.NickName ?? ""); } catch { }
                if (string.IsNullOrEmpty(name))
                {
                    string sid = null;
                    if (p.CustomProperties != null && p.CustomProperties.ContainsKey("u_id"))
                        sid = p.CustomProperties["u_id"]?.ToString();
                    if (!string.IsNullOrEmpty(sid) && sid == opponentSteamId && !string.IsNullOrEmpty(opponentDisplayName))
                        name = opponentDisplayName;
                }
                if (string.IsNullOrEmpty(name)) name = "A player";
                if (name.Length > 24) name = name.Substring(0, 24);

                // Teammate vs opponent wording in team modes (t_id published at
                // ready_join by both 2v2 and 1v2 clients).
                bool isTeammate = false;
                try
                {
                    var myProps = PhotonNetwork.LocalPlayer?.CustomProperties;
                    if (p.CustomProperties != null && myProps != null
                        && p.CustomProperties.ContainsKey("t_id") && myProps.ContainsKey("t_id"))
                        isTeammate = p.CustomProperties["t_id"]?.ToString() == myProps["t_id"]?.ToString();
                }
                catch { }

                // Photon can't distinguish a quit from a connection drop on the
                // observer's seat — neutral wording. Exception: a peer that
                // flagged cr_lv_rk left deliberately for a ranked match.
                bool leftForRanked = false;
                try
                {
                    leftForRanked = p.CustomProperties != null && p.CustomProperties.ContainsKey("cr_lv_rk")
                                    && p.CustomProperties["cr_lv_rk"]?.ToString() == "1";
                }
                catch { }

                string whoTag = isTeammate ? $"Your teammate <b>{name}</b>" : $"<b>{name}</b>";
                string text;
                bool red;
                if (leftForRanked)
                {
                    text = $"{whoTag} left to join a ranked match";
                    red = false;
                }
                else if (midGame)
                {
                    text = $"{whoTag} disconnected or quit mid-game";
                    red = true;
                }
                else if (ovtSeriesInProgress)
                {
                    text = $"{whoTag} left — 1v2 series unfinished";
                    red = false;
                }
                else
                {
                    // Review [13]: between games of a 1v1 series, only the
                    // tracked OPPONENT leaving is news — a bystander joining
                    // and leaving the room (quickplay/private churn) must not
                    // be bannered with the series score. Team rooms keep the
                    // no-identity behavior (any of the 3 peers matters).
                    if (!teamRoom)
                    {
                        string lu = null;
                        if (p.CustomProperties != null && p.CustomProperties.ContainsKey("u_id"))
                            lu = p.CustomProperties["u_id"]?.ToString();
                        bool isTrackedOpp =
                            (!string.IsNullOrEmpty(lu) && lu == opponentSteamId)
                            || (!string.IsNullOrEmpty(opponentDisplayName)
                                && name == StripRichText(opponentDisplayName));
                        if (!isTrackedOpp) return;
                    }
                    text = $"{whoTag} left — series unfinished ({CurrentSeriesGamesWon}-{CurrentSeriesGamesLost})";
                    red = false;
                }
                Plugin.Log.LogInfo($"[LEAVER-BANNER] {text.Replace("<b>", "").Replace("</b>", "")} (midGame={midGame} series={seriesInProgress} teammate={isTeammate})");
                CompetitiveUI.ShowLeaverBanner(text, red);
            }
            catch { }
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

        /// <summary>Public retry hook for LocalSteamId resolution (v1.30, bug #51).
        /// IdentifyLocalPlayer historically ran only at plugin init + room joins —
        /// a client that lost the startup Steamworks race and then sat in menus
        /// kept LocalSteamId at "unknown" all session, so its presence pings and
        /// queue-count calls carried no steam id and the player never counted as
        /// online. The presence loop calls this each tick until resolution.</summary>
        public static void EnsureIdentityResolved()
        {
            if (!string.IsNullOrEmpty(localSteamId) && localSteamId != "unknown") return;
            IdentifyLocalPlayer();
        }

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
                    if (TimelineAppend(curP1Rounds, curP1Points, curP2Rounds, curP2Points))
                        StampPointTime();
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
                    if (TimelineAppend(curP1Rounds, curP1Points, curP2Rounds, curP2Points))
                        StampPointTime();
                    // Deep End bookkeeping: a round just completed — bank whether
                    // Abyssal fired during it, reset for the next round.
                    if (abyssalActivatedThisRound) { abyssalRoundsActivated++; abyssalActivatedThisRound = false; }

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

        private static bool BothPlayersSupportSharedGameToken()
        {
            try
            {
                var players = PhotonNetwork.PlayerList;
                string expectedRoom =
                    PhotonNetwork.CurrentRoom?.Name ?? "";
                if (players == null
                    || players.Length != 2
                    || string.IsNullOrEmpty(expectedRoom))
                    return false;
                foreach (var player in players)
                {
                    if (player == null || player.CustomProperties == null)
                        return false;
                    string expectedCapability =
                        expectedRoom + ":"
                        + player.ActorNumber.ToString(
                            System.Globalization.CultureInfo.InvariantCulture);
                    if (!player.CustomProperties.ContainsKey(
                            GAME_TOKEN_CAP_PROP_KEY)
                        || (player.CustomProperties[
                            GAME_TOKEN_CAP_PROP_KEY]?.ToString() ?? "")
                            != expectedCapability)
                        return false;
                }
                return true;
            }
            catch { return false; }
        }

        private static void TryPublishSharedGameToken()
        {
            if (!oneVOneMatchAtStart
                || !string.IsNullOrEmpty(sharedGameToken)
                || matchStartServerTimestamp == 0
                || !BothPlayersSupportSharedGameToken())
                return;
            try
            {
                if (!PhotonNetwork.IsMasterClient
                    || PhotonNetwork.CurrentRoom == null)
                    return;

                string previous = "";
                var roomProps = PhotonNetwork.CurrentRoom.CustomProperties;
                if (roomProps != null
                    && roomProps.ContainsKey(GAME_TOKEN_PROP_KEY))
                {
                    string raw = roomProps[GAME_TOKEN_PROP_KEY]?.ToString() ?? "";
                    int separator = raw.IndexOf(':');
                    previous = separator > 0 ? raw.Substring(0, separator) : raw;
                }

                string token;
                do
                {
                    uint randomBits = BitConverter.ToUInt32(
                        Guid.NewGuid().ToByteArray(), 0);
                    token = (randomBits % 1000000u).ToString(
                        "D6",
                        System.Globalization.CultureInfo.InvariantCulture);
                }
                while (token == previous || token == previousGameToken);

                var props = new Hashtable();
                props[GAME_TOKEN_PROP_KEY] =
                    token + ":" + matchStartServerTimestamp.ToString(
                        System.Globalization.CultureInfo.InvariantCulture);
                if (!PhotonNetwork.CurrentRoom.SetCustomProperties(props))
                    return;
                sharedGameToken = token;
            }
            catch { }
        }

        private static void BeginSharedGameToken()
        {
            // A joining player may have captured the room's stale prior-game
            // token before publishing its room-bound capability. Preserve that
            // guard when it has not adopted a shared token in this sitting yet.
            if (!string.IsNullOrEmpty(sharedGameToken))
                previousGameToken = sharedGameToken;
            sharedGameToken = "";
            matchStartServerTimestamp = 0;
            if (!oneVOneMatchAtStart) return;
            // Record the common Photon clock even if this client has not yet
            // observed both capability properties. The master may already see
            // both and publish; this lets a non-master adopt that token later.
            try { matchStartServerTimestamp = PhotonNetwork.ServerTimestamp; }
            catch { return; }
            TryPublishSharedGameToken();
        }

        private static void TryRefreshSharedGameToken()
        {
            if (!oneVOneMatchAtStart
                || !string.IsNullOrEmpty(sharedGameToken))
                return;
            try
            {
                var props = PhotonNetwork.CurrentRoom?.CustomProperties;
                if (props != null
                    && props.ContainsKey(GAME_TOKEN_PROP_KEY))
                {
                    string raw = props[GAME_TOKEN_PROP_KEY]?.ToString() ?? "";
                    string[] parts = raw.Split(':');
                    int publishedAt;
                    if (parts.Length == 2
                        && Regex.IsMatch(parts[0], @"^\d{6}$")
                        && parts[0] != previousGameToken
                        && int.TryParse(
                            parts[1],
                            System.Globalization.NumberStyles.Integer,
                            System.Globalization.CultureInfo.InvariantCulture,
                            out publishedAt))
                    {
                        // Token freshness is established by the previous-token
                        // guard. Do not compare the two clients' hook times:
                        // one Unity main thread can enter the match >10s later
                        // even though Photon delivered the correct room token.
                        sharedGameToken = parts[0];
                        return;
                    }
                }
            }
            catch { }
            // The master may have missed the peer's capability property on the
            // exact game-start frame. Retry while the match is live so current
            // clients converge on a shared exact report ID.
            TryPublishSharedGameToken();
        }

        private static string BuildReportRoomId(
            int reportP1Rounds = -1, int reportP2Rounds = -1)
        {
            TryRefreshSharedGameToken();
            string token = !string.IsNullOrEmpty(sharedGameToken)
                ? sharedGameToken
                : matchStartTime.ToString(
                    "HHmmss",
                    System.Globalization.CultureInfo.InvariantCulture);
            int reportRoundTotal =
                reportP1Rounds >= 0 && reportP2Rounds >= 0
                    ? reportP1Rounds + reportP2Rounds
                    : p1Rounds + p2Rounds;
            return $"{photonRoomId}_{token}_r{reportRoundTotal}";
        }

        // Anti-cheat telemetry must NEVER be able to abort a match report. All
        // three call sites run on the critical path — two in the room-leave block
        // (before wasInRoom is updated) and one inside OnGameOver ABOVE the report
        // routing, with gameOverReported already latched. An escaping exception
        // there would silently drop a real ranked game, so contain everything here
        // and let every caller stay a plain call.
        private static void TryDispatchMacroEvidence(
            string reportRoomId = null,
            int reportP1Rounds = -1, int reportP2Rounds = -1)
        {
            try
            {
                DispatchMacroEvidenceCore(reportRoomId, reportP1Rounds, reportP2Rounds);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(
                    $"[MACRO-EVIDENCE] dispatch failed (match reporting unaffected): {ex.Message}");
            }
        }

        private static void DispatchMacroEvidenceCore(
            string reportRoomId,
            int reportP1Rounds, int reportP2Rounds)
        {
            int finalP1Rounds =
                reportP1Rounds >= 0 ? reportP1Rounds : p1Rounds;
            int finalP2Rounds =
                reportP2Rounds >= 0 ? reportP2Rounds : p2Rounds;
            if (macroEvidenceDispatched
                || !oneVOneMatchAtStart
                || LocalMacroSuspectSeconds < 10
                || finalP1Rounds == finalP2Rounds
                || (localTeamId != 0 && localTeamId != 1)
                || string.IsNullOrEmpty(localSteamId)
                || string.IsNullOrEmpty(opponentSteamId)
                || opponentSteamId.StartsWith("photon_")
                || (photonRoomId ?? "").IndexOf(
                    "offline", StringComparison.OrdinalIgnoreCase) >= 0)
                return;
            try
            {
                if (PhotonNetwork.OfflineMode) return;
            }
            catch { }

            string p1SteamId = localTeamId == 0
                ? localSteamId : opponentSteamId;
            string p2SteamId = localTeamId == 0
                ? opponentSteamId : localSteamId;
            int duration = Math.Max(
                0, (int)(DateTime.UtcNow - matchStartTime).TotalSeconds);
            string durableRoomId = string.IsNullOrEmpty(reportRoomId)
                ? BuildReportRoomId(finalP1Rounds, finalP2Rounds)
                : reportRoomId;
            bool usedSharedGameToken =
                !string.IsNullOrEmpty(sharedGameToken);

            // Snapshot the primitives before any room/reset mutation. The API
            // client persists the signed body before its first network attempt.
            macroEvidenceDispatched = true;
            ApiClient.ReportMacroEvidence(
                p1SteamId, p2SteamId, finalP1Rounds, finalP2Rounds,
                durableRoomId, matchStartTime, duration,
                usedSharedGameToken, localSteamId,
                LocalMacroSuspectSeconds,
                LocalMacroPeakKeysPerSecond,
                LocalMacroPeakClicksPerSecond,
                LocalMacroPeakEventsPerSecond,
                LocalMacroTimeline);
        }

        private static void OnMatchStarted()
        {
            isTracking = true;
            gameOverReported = false;
            macroEvidenceDispatched = false;
            // Match-scoped DC latch — must reset per GAME, not only on room leave
            // (learning #27). Rematches reuse the room, so a latch set during
            // game 1 would otherwise still be true in game 2 and let a LEAVER
            // take the 4-4 DC-win branch (which now also persists a 5-4 score).
            opponentDCReported = false;
            matchStartTime = DateTime.UtcNow;
            try
            {
                string roomName = PhotonNetwork.CurrentRoom?.Name ?? "";
                var roomProps = PhotonNetwork.CurrentRoom?.CustomProperties;
                oneVOneMatchAtStart =
                    !PhotonNetwork.OfflineMode
                    && !roomName.StartsWith("ovt_", StringComparison.Ordinal)
                    && !roomName.StartsWith("team_", StringComparison.Ordinal)
                    && !(roomProps?.ContainsKey("cr_ff") ?? false)
                    && PhotonNetwork.PlayerList != null
                    && PhotonNetwork.PlayerList.Length == 2;
            }
            catch { oneVOneMatchAtStart = false; }
            BeginSharedGameToken();

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
                                || rname.StartsWith("sct-")
                                || rname.StartsWith("ovt_");
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

                // 2v2 continuation (recording-gap fix): in a cr_ff room with no active
                // team series — the previous BO3 completed and they kept playing — the
                // reporter opens a fresh series so games 4+ of the sitting record as
                // ranked. Also self-heals a lost series-1 id (server returns the live one).
                if (inCrFfStart && string.IsNullOrEmpty(ApiClient.ActiveTeamSeriesId))
                {
                    TryRequestContinuationSeries();
                }

                // 1v2 continuation (recording-gap fix, review CONFIRMED — the endpoint
                // had no client caller): in an ovt_ room with no active series, the
                // reporter opens a fresh series so games 2+ of the sitting record.
                bool inOvtStart = (PhotonNetwork.CurrentRoom?.Name ?? "").StartsWith("ovt_");
                if (inOvtStart && string.IsNullOrEmpty(ApiClient.ActiveOvt1v2SeriesId))
                {
                    TryRequestOvtContinuationSeries();
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
            achJumped = false;
            // achLeftmostViolated is deliberately NOT reset here (bug #60).
            // OnMatchStarted fires at the START OF COMBAT — which is AFTER the
            // game's initial card-pick phase (GM_ArmsRace.DoStartGame runs a
            // pick for every player before TimeHandler.StartGame). Resetting
            // here wiped any "scrolled the selection" violation from those
            // pre-match picks, so a player could inspect every card on the
            // first pick and still earn Instinct. The flag resets in
            // ResetMatchState() (game over / room reset), which always runs
            // before the next game's pick phase.
            abyssalRoundsActivated = 0;
            abyssalActivatedThisRound = false;
            inPickPhase = false;
            pendingRegicideCheck = false;
            LocalShotsThisMatch = 0;
            LocalBlocksThisMatch = 0;
            LocalKeysThisMatch = 0;
            LocalMacroSuspectSeconds = 0;
            LocalMacroPeakKeysPerSecond = 0;
            LocalMacroPeakClicksPerSecond = 0;
            LocalMacroPeakEventsPerSecond = 0;
            inputSuspectWindows.Clear();
            inputBucketTimer = 0f;
            inputBucketCount = 0;
            inputBucketKeyCount = 0;
            inputBucketClickCount = 0;
            inputBucketStartedAtMs = -1;
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
            // July 21 item 2: per-match telemetry resets.
            localFpsTimeline.Clear(); tlFrames = 0; tlAccum = 0f;
            bcFrames = 0; bcAccum = 0f; lastBroadcastRecentFps = 0;
            oppFpsTimeline.Clear(); oppPingTimeline.Clear(); lastOppGstatsSeq = -1; lastOppSeqAdvanceTime = -1f;
            localFreezeCount = 0; localFreezeFocusedCount = 0; localFreezeTotalSec = 0f;
            pingSamples.Clear(); localRecvGapCount = 0; localRecvGapMaxMs = 0; _recvGapOpen = false;
            oppHbGapCount = 0; _oppHbGapOpen = false;
            oppFreezeCount = 0; oppFreezeFocusedCount = 0; oppRecvGapCount = 0;
            _lastTickStopwatchMs = -1;
            _hitsRemaining = 0;
            _activationSuccessCredited = true;
            BlockChain.Reset();
            _loggedFirstFire = _loggedFirstHit = _loggedFirstBlockAct = _loggedFirstBlockOk = false;
            _loggedHitBudgetDrop = false;
            // July 22 item 1/7: hit/block timelines + point stamps + per-actor harvest.
            localHitTimeline.Clear(); localBlockTimeline.Clear();
            oppHitTimeline.Clear(); oppBlockTimeline.Clear();
            localFps3sTimeline.Clear();
            pointTimes.Clear();
            LocalDamageTakenThisMatch = 0f;
            peerTele.Clear();

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
                    props[GSTATS_PROP_KEY] = "0|0|0|0|0|0";
                    PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                }
            }
            catch { }

            // Item 4: fresh per-game scoring timeline + opponent-stat snapshot.
            matchPointTimeline.Clear();
            OppStatBulletsFired = 0; OppStatBulletsHit = 0;
            OppStatBlocksActivated = 0; OppStatBlocksSuccessful = 0;
            OppStatKeysPressed = 0; OppStatActiveSeconds = 0f;
            OppStatMacroSuspectSeconds = 0;
            OppStatMacroPeakKeysPerSecond = 0;
            OppStatMacroPeakClicksPerSecond = 0;
            OppStatMacroPeakEventsPerSecond = 0;
            OppStatMacroTimeline = "";

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

            // Best-effort peer handoff before reporter election. Exact local
            // suspect evidence also follows its own signed API path below, so
            // correctness never depends on waiting while match state can reset.
            BroadcastGstatsImmediate();
            try { PhotonNetwork.SendAllOutgoingCommands(); } catch { }
            PollOpponentFps();

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
            // 2v2 it's the two ENEMY-team players. The teammate is recorded
            // under a "w/ " key so Session Info reads "w/ Stan 2-0" instead of
            // "vs Stan 2-0" (bug #56 — the old loop added every non-self player
            // as an opponent, teammate included). Team identity comes from the
            // t_id custom prop set at queue lock; a player whose prop is missing
            // falls back to "opponent" (matches the old behavior).
            var oppKeys = new List<string>();
            bool sessionRoomIsCrFf = false;
            // Review HIGH: 1v2 (ovt_) games must NOT pollute the 1v1 session tally,
            // the 1v1 BO3 "Series: X-Y" HUD, or the 1v1 session ranked W/L — those
            // are 1v1-ladder surfaces and 1v2 is a separate (unscored) mode with its
            // own tab. Detect ovt_ and skip the 1v1-specific mutations below.
            bool sessionRoomIsOvt = (PhotonNetwork.CurrentRoom?.Name ?? "").StartsWith("ovt_");
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
                    nm = StripRichText(nm);
                    int ppTeam = -1;
                    try
                    {
                        if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey("t_id"))
                            ppTeam = System.Convert.ToInt32(pp.CustomProperties["t_id"]);
                    }
                    catch { }
                    bool isTeammate = ppTeam >= 0 && localTeamId >= 0 && ppTeam == localTeamId;
                    oppKeys.Add(isTeammate ? "w/ " + nm : nm);
                }
            }
            if (oppKeys.Count == 0)
                oppKeys.Add(opponentDisplayName ?? "Unknown");

            // 1v2 games skip the 1v1 session W/L-by-opponent dict + the counters
            // below (they're 1v1-panel data). The 1v2 tab has its own leaderboard.
            if (!sessionRoomIsOvt)
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

            if (matchIsRanked && !sessionRoomIsOvt)
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
                    // A new BO3 starts here — re-arm the session series tally.
                    sessionSeriesCounted = false;
                }
                if (localWon) currentSeriesGamesWon++; else currentSeriesGamesLost++;
                // Count the series locally the moment this game decides it (first
                // to 2). Both clients reach this, so the non-reporting player's
                // session series tally is no longer stuck at 0-0. Idempotent: the
                // reporter's server-confirmed call finds it already counted.
                if (currentSeriesGamesWon >= 2 || currentSeriesGamesLost >= 2)
                {
                    bool seriesWon = currentSeriesGamesWon >= 2;
                    if (!sessionSeriesCounted)
                    {
                        sessionSeriesCounted = true;
                        if (seriesWon) sessionRankedSeriesWins++; else sessionRankedSeriesLosses++;
                        // Review find: this local BO3-decision path is the one
                        // that actually fires in the normal flow on BOTH clients
                        // (the reporter's server-confirmed call arrives later and
                        // dedupes out on sessionSeriesCounted) — so the lifetime
                        // H2H "Total Series" bump must live HERE, not only in
                        // IncrementSessionRankedSeries where it was unreachable.
                        try { ApiClient.OnSeriesCompletedVsOpponent(opponentSteamId, seriesWon); } catch { }
                        Plugin.Log.LogInfo($"[SESSION] Ranked series tally (local BO3 decision): {sessionRankedSeriesWins}-{sessionRankedSeriesLosses}");
                        SaveSessionState();
                    }
                }
            }
            else
            {
                if (localWon) sessionCasualWins++; else sessionCasualLosses++;
            }

            // Review [4]: 1v2 series tally for the leaver banner — the 1v1
            // counters above deliberately skip ovt rooms, which made the
            // between-games banner silent there. Solo = the singleton ROUNDS
            // team (same detection TryReportOvtMatch trusts); team 0 maps to
            // p1Rounds.
            if (sessionRoomIsOvt)
            {
                try
                {
                    if (ovtSoloWins >= 2 || ovtDuoWins >= 2) { ovtSoloWins = 0; ovtDuoWins = 0; }
                    var pmOvt = PlayerManager.instance;
                    int t0 = 0, t1 = 0;
                    if (pmOvt != null && pmOvt.players != null)
                        foreach (var poOvt in pmOvt.players)
                        {
                            if (poOvt == null) continue;
                            if (poOvt.TeamID == 0) t0++; else if (poOvt.TeamID == 1) t1++;
                        }
                    int soloTeam = t0 == 1 ? 0 : (t1 == 1 ? 1 : -1);
                    if (soloTeam >= 0)
                    {
                        bool team0Won = p1Rounds > p2Rounds;
                        if ((soloTeam == 0) == team0Won) ovtSoloWins++; else ovtDuoWins++;
                    }
                }
                catch { }
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

            // The Photon-master token is shared by both participants and stays
            // stable in the durable outbox. The local-time fallback preserves
            // mixed-version compatibility.
            string reportRoomId = BuildReportRoomId();

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

            // Every 1v1 client independently submits its own threshold-breaking
            // windows. This immutable snapshot is persisted before networking.
            if (!isOfflineMatch)
                TryDispatchMacroEvidence(reportRoomId);

            // ── 2v2 routing ────────────────────────────────────────
            // If this room has 4 players AND we have an active team series id, route through
            // the 2v2 match report instead of 1v1. The reporter (lowest Steam ID across the 4)
            // assembles the canonical t1a/t1b/t2a/t2b ordering by sorting each team's Steam IDs
            // — server canonicalizes the same way at lock, so the 11-field HMAC byte-matches.
            // ── 1v2 routing (ovt_ rooms, 3 players) ────────────────────
            // Solo vs duo is read straight from in-game team sizes (the team
            // with ONE player is the solo), so no external side state is needed.
            // Handled before the 2v2 route; on success we return.
            try
            {
                string rn1 = PhotonNetwork.CurrentRoom?.Name ?? "";
                // Review HIGH: ANY ovt_ room bans the 1v1 fallback — the guard must
                // NOT be gated on PlayerList==3. An ovt_ room that (e.g. after a DC)
                // has 2 players at report time would otherwise fall through to the
                // 1v1 ReportMatch path and mint a phantom 1v1 ranked match/series
                // (#65/#106 class). Only ATTEMPT the 3-player report when full.
                if (rn1.StartsWith("ovt_") && shouldReport)
                {
                    bool sent = false;
                    if (PhotonNetwork.PlayerList != null && PhotonNetwork.PlayerList.Length == 3)
                        sent = TryReportOvtMatch(reportRoomId, duration);
                    if (!sent)
                        Plugin.Log.LogWarning($"[1v2-REPORT-ROUTE] ovt_ room, report not routed (players={PhotonNetwork.PlayerList?.Length ?? -1}) — 1v1 fallback banned");
                    EvaluateAchievements(localWon);
                    isTracking = false;
                    matchIsRanked = false;
                    return;
                }
            }
            catch (Exception ex) { Plugin.Log.LogError($"[1v2] routing error: {ex.Message}"); }

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
                    // Bug #70 self-heal: a reportable 2v2 game ended with no series id —
                    // the game-start continuation request failed (server error / network
                    // blip), which used to drop the game entirely. Re-request the
                    // continuation NOW and submit this game once the series id lands.
                    // Room + duration are captured; Photon state is still alive during
                    // the between-games window, so the deferred TryReportTeamMatch can
                    // resolve all four players. Non-reporters early-return inside
                    // TryRequestContinuationSeries as usual.
                    if (shouldReport && roomIsCrFf && !hasSeries && playerListLen == 4)
                    {
                        Plugin.Log.LogWarning("[2v2-REPORT-ROUTE] no team series at match end — requesting continuation and deferring report");
                        string deferredRoom = reportRoomId;
                        int deferredDuration = duration;
                        TryRequestContinuationSeries(ok =>
                        {
                            if (ok && !string.IsNullOrEmpty(ApiClient.ActiveTeamSeriesId))
                            {
                                bool sent = TryReportTeamMatch(deferredRoom, deferredDuration);
                                Plugin.Log.LogInfo($"[2v2-REPORT-ROUTE] deferred report after continuation: sent={sent}");
                            }
                            else Plugin.Log.LogWarning("[2v2-REPORT-ROUTE] continuation retry failed — game not recorded");
                        });
                    }
                    else
                    {
                        Plugin.Log.LogWarning($"[2v2-REPORT-ROUTE] BLOCKING 1v1 fallback in 2v2 context: shouldReport={shouldReport} hasSeries={hasSeries} playerListLen={playerListLen} cr_ff={roomIsCrFf} — match will not be reported");
                    }
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

            // Bug #47: matchIsRanked races (opponent props lost on join, /mod/check
            // vs preflight-registration race) can leave the FIRST game of a sitting
            // flagged casual while a live ranked series for this exact pairing
            // already exists (our own preflight created/found it — that required
            // both players ranked-enabled). The series id is the durable signal;
            // trust it over the racy flag so game 1 counts. Server-side mirrors
            // this with a mod-pair upgrade at submit time for old clients.
            if (shouldReport && !matchIsRanked
                && !string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)
                && OpponentHasMod())
            {
                Plugin.Log.LogInfo($"[REPORT-ROUTE] forcing isRanked=true: live series {ApiClient.ActiveRankedSeriesId} exists for this pairing (flag lost a race)");
                matchIsRanked = true;
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
                    // July 21 item 1 (Stan's spec): activations = user right-clicks only
                    // (TryBlock's sole caller is Block.Update on input); successes = max 1
                    // per activation, credited when the right-click block OR its Echo/
                    // ShieldCharge follow-on absorbs. Pure auto-blocks (Abyssal, Shields
                    // Up wiring) count nowhere. LocalBlocksThisMatch (mouse-only) remains
                    // the anti-cheat advisory signal.
                    localBlocksActivated: LocalBlocksActivatedThisMatch,
                    localBlocksSuccessful: LocalBlocksSuccessfulThisMatch,
                    localAvgFps: LocalAvgFps,
                    opponentAvgFps: OpponentAvgFps,
                    localKeysPressed: LocalKeysThisMatch,
                    localActiveSeconds: LocalActiveSecondsThisMatch,
                    localMacroSuspectSeconds: LocalMacroSuspectSeconds,
                    localMacroPeakKps: LocalMacroPeakKeysPerSecond,
                    localMacroPeakCps: LocalMacroPeakClicksPerSecond,
                    localMacroPeakEps: LocalMacroPeakEventsPerSecond,
                    localMacroTimeline: LocalMacroTimeline,
                    oppMacroSuspectSeconds: OppStatMacroSuspectSeconds,
                    oppMacroPeakKps: OppStatMacroPeakKeysPerSecond,
                    oppMacroPeakCps: OppStatMacroPeakClicksPerSecond,
                    oppMacroPeakEps: OppStatMacroPeakEventsPerSecond,
                    oppMacroTimeline: OppStatMacroTimeline,
                    // Item 4 (v1.30): opponent's per-game combat stats (their
                    // client publishes cr_gstats every ~3s; we ship the latest
                    // snapshot) + the cumulative scoring timeline for the
                    // history hover graph.
                    oppBulletsFired: OppStatBulletsFired,
                    oppBulletsHit: OppStatBulletsHit,
                    oppBlocksActivated: OppStatBlocksActivated,
                    oppBlocksSuccessful: OppStatBlocksSuccessful,
                    oppKeysPressed: OppStatKeysPressed,
                    oppActiveSeconds: OppStatActiveSeconds,
                    pointTimeline: string.Join(",", matchPointTimeline.ToArray()),
                    // July 21 item 2: FPS/lag telemetry (advisory, non-HMAC).
                    localFpsTimeline: string.Join(",", localFpsTimeline),
                    oppFpsTimeline: string.Join(",", oppFpsTimeline),
                    localFreezeCount: localFreezeCount,
                    localFreezeFocusedCount: localFreezeFocusedCount,
                    localFreezeTotalSec: localFreezeTotalSec,
                    localPingAvg: pingSamples.Count > 0 ? (int)Math.Round(pingSamples.Average()) : 0,
                    localPingMax: pingSamples.Count > 0 ? pingSamples.Max() : 0,
                    // July 22 item 3: latency timelines for the history hover chart.
                    localPingTimeline: string.Join(",", pingSamples),
                    oppPingTimeline: string.Join(",", oppPingTimeline),
                    oppPingAvg: oppPingTimeline.Count > 0 ? (int)Math.Round(oppPingTimeline.Average()) : 0,
                    localRecvGapCount: localRecvGapCount,
                    localRecvGapMaxMs: localRecvGapMaxMs,
                    oppHbGapCount: oppHbGapCount,
                    oppFreezeCount: oppFreezeCount,
                    oppFreezeFocusedCount: oppFreezeFocusedCount,
                    oppRecvGapCount: oppRecvGapCount,
                    // July 22 item 1: cumulative Hit%/Block% pair timelines +
                    // per-point timestamps for the new hover graphs.
                    localHitTimeline: string.Join(",", localHitTimeline.ToArray()),
                    oppHitTimeline: string.Join(",", oppHitTimeline.ToArray()),
                    localBlockTimeline: string.Join(",", localBlockTimeline.ToArray()),
                    oppBlockTimeline: string.Join(",", oppBlockTimeline.ToArray()),
                    pointTimes: string.Join(",", pointTimes)
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
        private static float lastContinuationRequestTime = -999f;

        /// <summary>Game-start hook for a cr_ff room with no active series: the reporter
        /// (lowest Steam ID) opens a continuation series so games past the first BO3 record
        /// as ranked. Best-effort — if the lineup can't be resolved yet it retries next
        /// game. Team comes from the t_id custom property (set at queue-lock; no spawn
        /// needed). 8s debounce so an in-flight request isn't re-fired.</summary>
        private static void TryRequestContinuationSeries(Action<bool> onDone = null)
        {
            try
            {
                if (UnityEngine.Time.time - lastContinuationRequestTime < 8f) return;
                if (PhotonNetwork.PlayerList == null || PhotonNetwork.PlayerList.Length != 4) return;

                var sids = new string[4];
                var teams = new int[4];
                for (int i = 0; i < 4; i++)
                {
                    var pp = PhotonNetwork.PlayerList[i];
                    if (pp == null) return;
                    string sid = ResolvePhotonSteamId(pp);
                    if (string.IsNullOrEmpty(sid) || sid.StartsWith("photon_")) return;
                    int team = -1;
                    if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey("t_id"))
                    { try { team = Convert.ToInt32(pp.CustomProperties["t_id"]); } catch { } }
                    if (team != 0 && team != 1) return;
                    sids[i] = sid; teams[i] = team;
                }

                var team0 = new List<string>();
                var team1 = new List<string>();
                for (int i = 0; i < 4; i++) { if (teams[i] == 0) team0.Add(sids[i]); else team1.Add(sids[i]); }
                if (team0.Count != 2 || team1.Count != 2) return;

                // Reporter election: lowest Steam ID among the four (same as the report path).
                string lowest = null; long lowestVal = long.MaxValue;
                foreach (var s in sids) { if (long.TryParse(s, out long v) && v < lowestVal) { lowestVal = v; lowest = s; } }
                if (lowest != localSteamId) return;  // only the reporter opens it; server is idempotent

                team0.Sort(StringComparer.Ordinal);
                team1.Sort(StringComparer.Ordinal);
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                lastContinuationRequestTime = UnityEngine.Time.time;
                Plugin.Log.LogInfo($"[2v2-CONTINUATION] requesting continuation (t0={team0[0]},{team0[1]} t1={team1[0]},{team1[1]})");
                ApiClient.RequestContinuationSeries(localSteamId, room, photonRegion,
                    team0[0], team0[1], team1[0], team1[1], onDone);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[2v2-CONTINUATION] resolve error: {ex.Message}"); }
        }

        private static float lastOvtContinuationRequestTime = -999f;
        /// <summary>Open a fresh 1v2 series at game start when the three keep playing
        /// past a completed BO3. Solo/duo read from in-game team sizes; only the
        /// reporter (lowest Steam ID) opens it (server is idempotent).</summary>
        private static void TryRequestOvtContinuationSeries()
        {
            try
            {
                if (UnityEngine.Time.time - lastOvtContinuationRequestTime < 8f) return;
                if (PhotonNetwork.PlayerList == null || PhotonNetwork.PlayerList.Length != 3) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                var sids = new string[3]; var teams = new int[3];
                for (int i = 0; i < 3; i++)
                {
                    var pp = PhotonNetwork.PlayerList[i]; if (pp == null) return;
                    string sid = ResolvePhotonSteamId(pp);
                    if (string.IsNullOrEmpty(sid) || sid.StartsWith("photon_")) return;
                    int team = -1;
                    foreach (var po in pm.players)
                    { if (po == null) continue; var pv = po.GetComponent<PhotonView>(); if (pv == null || pv.Owner == null || pv.Owner.ActorNumber != pp.ActorNumber) continue; team = po.TeamID; break; }
                    if (team < 0) return;
                    sids[i] = sid; teams[i] = team;
                }
                // Group by team; singleton = solo.
                var byTeam = new Dictionary<int, List<string>>();
                for (int i = 0; i < 3; i++) { if (!byTeam.ContainsKey(teams[i])) byTeam[teams[i]] = new List<string>(); byTeam[teams[i]].Add(sids[i]); }
                if (byTeam.Count != 2) return;
                string solo = null; var duo = new List<string>();
                foreach (var kv in byTeam) { if (kv.Value.Count == 1) solo = kv.Value[0]; else duo = kv.Value; }
                if (solo == null || duo.Count != 2) return;
                duo.Sort(StringComparer.Ordinal);
                // Reporter election: lowest Steam ID.
                string lowest = null; long lowVal = long.MaxValue;
                foreach (var s in sids) { if (long.TryParse(s, out long v) && v < lowVal) { lowVal = v; lowest = s; } }
                if (lowest != localSteamId) return;
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                lastOvtContinuationRequestTime = UnityEngine.Time.time;
                Plugin.Log.LogInfo($"[1v2-CONTINUATION] requesting (solo={solo} duo={duo[0]},{duo[1]})");
                ApiClient.RequestOvtContinuationSeries(localSteamId, room, photonRegion, solo, duo[0], duo[1]);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[1v2-CONTINUATION] resolve error: {ex.Message}"); }
        }

        /// <summary>Report a finished 1v2 game. Solo vs duo is determined purely
        /// from in-game team SIZES — the team with one Player is the solo, the
        /// other two are the duo — so no external side state is needed. Reporter
        /// is the lowest Steam ID of the three; others route correctly but no-op.</summary>
        private static bool TryReportOvtMatch(string reportRoomId, int duration)
        {
            if (PhotonNetwork.PlayerList == null || PhotonNetwork.PlayerList.Length != 3) return false;
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return false;
            if (string.IsNullOrEmpty(ApiClient.ActiveOvt1v2SeriesId))
            {
                Plugin.Log.LogWarning("[1v2-REPORT] no active series id — cannot report");
                return false;
            }
            // Resolve each Photon actor → Steam ID + in-game TeamID + cards + fps.
            var info = new Dictionary<string, (string name, int teamId, List<MatchTracker.CardPickData> cards, int fps)>();
            foreach (var pp in PhotonNetwork.PlayerList)
            {
                if (pp == null) continue;
                string sid = ResolvePhotonSteamId(pp);
                if (string.IsNullOrEmpty(sid) || sid.StartsWith("photon_")) { Plugin.Log.LogWarning($"[1v2-REPORT] couldn't resolve actor {pp.ActorNumber}"); return false; }
                string name = StripRichText(pp.NickName ?? sid); if (string.IsNullOrEmpty(name)) name = sid; if (name.Length > 60) name = name.Substring(0, 60);
                int teamId = -1;
                foreach (var po in pm.players)
                {
                    if (po == null) continue; var pv = po.GetComponent<PhotonView>();
                    if (pv == null || pv.Owner == null || pv.Owner.ActorNumber != pp.ActorNumber) continue;
                    teamId = po.TeamID; break;
                }
                var picks = new List<MatchTracker.CardPickData>();
                if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey(CARD_PROP_KEY))
                {
                    string raw = pp.CustomProperties[CARD_PROP_KEY]?.ToString() ?? "";
                    if (!string.IsNullOrEmpty(raw)) { int order = 1; foreach (var nm in raw.Split('|')) { string cn = CardRarityLookup.GetCanonicalName(ToTitleCase(nm.Trim())); if (string.IsNullOrEmpty(cn)) continue; picks.Add(new MatchTracker.CardPickData { CardName = cn, CardRarity = CardRarityLookup.GetRarity(cn), PickOrder = order++, RoundNumber = 1 }); } }
                }
                int fps = 0; if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey(FPS_PROP_KEY)) { try { fps = Convert.ToInt32(pp.CustomProperties[FPS_PROP_KEY]); } catch { } }
                if (pp.IsLocal) { if (localCards != null && localCards.Count > 0) picks = new List<MatchTracker.CardPickData>(localCards); int myFps = LocalAvgFps; if (myFps > 0) fps = myFps; }
                info[sid] = (name, teamId, picks, fps);
            }
            if (info.Count != 3) { Plugin.Log.LogWarning($"[1v2-REPORT] resolved {info.Count}/3 players"); return false; }

            // Group by in-game team; the singleton team is the solo.
            var byTeam = new Dictionary<int, List<string>>();
            foreach (var kv in info) { if (!byTeam.ContainsKey(kv.Value.teamId)) byTeam[kv.Value.teamId] = new List<string>(); byTeam[kv.Value.teamId].Add(kv.Key); }
            if (byTeam.Count != 2) { Plugin.Log.LogWarning($"[1v2-REPORT] expected 2 teams, got {byTeam.Count}"); return false; }
            int soloTeam = -1, duoTeam = -1;
            foreach (var kv in byTeam) { if (kv.Value.Count == 1) soloTeam = kv.Key; else if (kv.Value.Count == 2) duoTeam = kv.Key; }
            if (soloTeam < 0 || duoTeam < 0) { Plugin.Log.LogWarning("[1v2-REPORT] not a 1+2 split"); return false; }

            string soloSid = byTeam[soloTeam][0];
            var duo = byTeam[duoTeam]; duo.Sort(StringComparer.Ordinal);
            string duoASid = duo[0], duoBSid = duo[1];

            // Reporter election: lowest Steam ID.
            string lowest = null; long lowVal = long.MaxValue;
            foreach (var sid in info.Keys) { if (long.TryParse(sid, out long v) && v < lowVal) { lowVal = v; lowest = sid; } }
            if (lowest == null) lowest = localSteamId;
            if (lowest != localSteamId) { Plugin.Log.LogInfo($"[1v2-REPORT] reporter is {lowest}, not me — skipping"); return true; }

            // Rounds: solo's team maps to p1Rounds if it's ROUNDS team 0, else p2Rounds.
            int soloRounds = soloTeam == 0 ? p1Rounds : p2Rounds;
            int duoRounds  = soloTeam == 0 ? p2Rounds : p1Rounds;
            int soloPoints = soloTeam == 0 ? p1Points : p2Points;
            int duoPoints  = soloTeam == 0 ? p2Points : p1Points;

            ApiClient.ReportOvtMatch(
                ApiClient.ActiveOvt1v2SeriesId, reportRoomId, photonRegion, duration,
                soloSid, info[soloSid].name, info[soloSid].cards,
                duoASid, info[duoASid].name, info[duoASid].cards,
                duoBSid, info[duoBSid].name, info[duoBSid].cards,
                soloRounds, duoRounds, soloPoints, duoPoints,
                localSteamId, info[soloSid].fps, info[duoASid].fps, info[duoBSid].fps);
            Plugin.Log.LogInfo($"[1v2-REPORT] submitted solo={soloSid} duo={duoASid},{duoBSid} {soloRounds}-{duoRounds}");
            return true;
        }

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
            // July 22 item 7: per-player telemetry blobs keyed by steam id —
            // local slot from own counters, peers from the cr_gstats harvest.
            var teleBySid = new Dictionary<string, ApiClient.TeamTelemetry>();

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
                    teleBySid[sid] = new ApiClient.TeamTelemetry
                    {
                        fpsTimeline = string.Join(",", localFps3sTimeline),
                        pingTimeline = string.Join(",", pingSamples),
                        pingAvg = pingSamples.Count > 0 ? (int)Math.Round(pingSamples.Average()) : 0,
                        hitTimeline = string.Join(",", localHitTimeline.ToArray()),
                        blockTimeline = string.Join(",", localBlockTimeline.ToArray()),
                        bulletsFired = LocalBulletsFiredThisMatch,
                        bulletsHit = LocalBulletsHitThisMatch,
                        blocksActivated = LocalBlocksActivatedThisMatch,
                        blocksSuccessful = LocalBlocksSuccessfulThisMatch,
                        keysPressed = LocalKeysThisMatch,
                        activeSeconds = LocalActiveSecondsThisMatch,
                    };
                }
                else if (TryGetPeerTelemetry(pp.ActorNumber,
                             out string pFps, out string pPing, out string pHit, out string pBlock,
                             out int[] pCounters))
                {
                    int pingAvg = 0;
                    try
                    {
                        var pings = new List<int>();
                        foreach (var s in (pPing ?? "").Split(','))
                            if (int.TryParse(s, out int v) && v > 0) pings.Add(v);
                        if (pings.Count > 0) pingAvg = (int)Math.Round(pings.Average());
                    }
                    catch { }
                    teleBySid[sid] = new ApiClient.TeamTelemetry
                    {
                        fpsTimeline = pFps,
                        pingTimeline = pPing,
                        pingAvg = pingAvg,
                        hitTimeline = pHit,
                        blockTimeline = pBlock,
                        bulletsFired = pCounters[0],
                        bulletsHit = pCounters[1],
                        blocksActivated = pCounters[2],
                        blocksSuccessful = pCounters[3],
                        keysPressed = pCounters[4],
                        activeSeconds = pCounters[5],
                    };
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
                t2aFps: bySteam[t2aSid].fps, t2bFps: bySteam[t2bSid].fps,
                t1aTele: teleBySid.TryGetValue(t1aSid, out var _ta) ? _ta : null,
                t1bTele: teleBySid.TryGetValue(t1bSid, out var _tb) ? _tb : null,
                t2aTele: teleBySid.TryGetValue(t2aSid, out var _tc) ? _tc : null,
                t2bTele: teleBySid.TryGetValue(t2bSid, out var _td) ? _td : null
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

            // Input tracking — discrete key/click COUNTS moved to TickInputSampling
            // (per-frame; the *Down APIs are frame-edge triggers and missed ~97% of
            // events at this 10 Hz cadence — bug #50). Only HELD-state achievement
            // edges remain here: GetKey/GetMouseButton read held state, which a
            // 10 Hz sample sees reliably.
            if (localAliveInCombat && !inPickPhase)
            {
                if (!achFiredShot && Input.GetMouseButton(0))
                {
                    achFiredShot = true;
                    Plugin.Log.LogInfo("[ACH] Player fired a shot");
                }
                // Skip while the chat overlay / F5 menu has focus — typing "wasd"
                // in a Discord-bridged message previously false-flagged Immovable
                // Object.
                bool typingInChat = false;
                try { typingInChat = CompetitiveUI.IsChatInputOpen || NativeUI.IsOpen; } catch { }
                if (!typingInChat && !achMoved && (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.A) ||
                    Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.D) ||
                    Input.GetKey(KeyCode.Space) || Input.GetKey(KeyCode.UpArrow) ||
                    Input.GetKey(KeyCode.DownArrow) || Input.GetKey(KeyCode.LeftArrow) ||
                    Input.GetKey(KeyCode.RightArrow)))
                {
                    achMoved = true;
                    Plugin.Log.LogInfo("[ACH] Player moved");
                }
                // Grounded (v1.30): jump keys only — W/Space/Up all jump in ROUNDS.
                if (!typingInChat && !achJumped && (Input.GetKey(KeyCode.Space)
                    || Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)))
                {
                    achJumped = true;
                    Plugin.Log.LogInfo("[ACH] Player jumped");
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

                // 12. Grounded (v1.30) — won without ever jumping. Same active-
                // combat gating as Immovable (learning #28) via the shared
                // sampler; strictly easier than Immovable but still a real bit.
                if (localWon && !achJumped)
                {
                    Plugin.Log.LogInfo("[ACH] Evaluating: Grounded — PASSED");
                    ApiClient.UnlockAchievement(steamId, "grounded");
                }

                // 13. Instinct (v1.30) — won having taken the LEFT-MOST card on
                // every pick without ever scrolling the selection. Violation flag
                // is set by the RPCA_SetCurrentSelected postfix; require at least
                // 3 picks so a 1-pick stomp doesn't hand it out.
                if (localWon && !achLeftmostViolated && pickCountThisMatch >= 3)
                {
                    Plugin.Log.LogInfo($"[ACH] Evaluating: Instinct — PASSED ({pickCountThisMatch} untouched picks)");
                    ApiClient.UnlockAchievement(steamId, "instinct");
                }
                // July 21 (Instinct verify): re-arm for the NEXT game of the sitting.
                // ResetMatchState only runs on room-leave, so a game-1 scroll used to
                // block Instinct for every same-room rematch. Clearing here — after
                // this game's evaluation consumed the flag — keeps the bug-#60 rule
                // (never clear in OnMatchStarted; pre-match pick violations survive):
                // the next game's pre-match picks happen after this point.
                achLeftmostViolated = false;

                // 14. God Build (July 12 spec; renamed from Unkillable, v1.32) — the real god-build qualifier is
                // the GUN STATE at game end, not a card-name proxy: exactly 1 max
                // ammo, reload cycle <= 1s, Shields Up in the build, and the win.
                if (localWon && (cardNames.Contains("Shields Up") || cardNames.Contains("ShieldsUp")))
                {
                    try
                    {
                        var pm = PlayerManager.instance;
                        Player me = null;
                        if (pm != null && pm.players != null)
                            foreach (var p in pm.players)
                                if (p != null && p.data != null && p.data.view != null && p.data.view.IsMine) { me = p; break; }
                        var ga = me != null && me.data.weaponHandler != null && me.data.weaponHandler.gun != null
                            ? me.data.weaponHandler.gun.GetComponentInChildren<GunAmmo>(true) : null;
                        if (ga != null)
                        {
                            float reloadSecs = (ga.reloadTime + ga.reloadTimeAdd) * ga.reloadTimeMultiplier;
                            Plugin.Log.LogInfo($"[ACH] God Build check: maxAmmo={ga.maxAmmo} reload={reloadSecs:F2}s");
                            if (ga.maxAmmo <= 1 && reloadSecs <= 1.0f)
                            {
                                Plugin.Log.LogInfo("[ACH] Evaluating: God Build — PASSED");
                                ApiClient.UnlockAchievement(steamId, "god_build");
                            }
                        }
                    }
                    catch (Exception gex) { Plugin.Log.LogWarning($"[ACH] God Build check failed: {gex.Message}"); }
                }

                // 15. Into the Deep End (July 12 spec) — Abyssal Countdown as the
                // FIRST pick, and the ability ACTIVATED in every round of the game.
                if (localWon)
                {
                    string firstPick = preMatchCards.Count > 0 ? preMatchCards[0].CardName
                                      : (localCards.Count > 0 ? localCards[0].CardName : "");
                    bool abyssalFirst = firstPick == "Abyssal Countdown" || firstPick == "AbyssalCountdown";
                    if (abyssalFirst)
                    {
                        int roundsActivated = abyssalRoundsActivated + (abyssalActivatedThisRound ? 1 : 0);
                        int totalRounds = localR + oppR;
                        Plugin.Log.LogInfo($"[ACH] Deep End check: activated {roundsActivated}/{totalRounds} rounds");
                        if (totalRounds > 0 && roundsActivated >= totalRounds)
                        {
                            Plugin.Log.LogInfo("[ACH] Evaluating: Into the Deep End — PASSED");
                            ApiClient.UnlockAchievement(steamId, "deep_end");
                        }
                    }
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
            oneVOneMatchAtStart = false;
            macroEvidenceDispatched = false;
            sharedGameToken = "";
            previousGameToken = "";
            matchStartServerTimestamp = 0;
            wasGameInProgress = false;
            pcolorRoomApplied = false;
            // Room over — drop the Tab-board card baselines (bug #64); the Player
            // objects they key on are destroyed with the room.
            try { TabStatsOverlay.ClearCardBaselines(); } catch { }
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
            achJumped = false;
            achLeftmostViolated = false;
            abyssalRoundsActivated = 0;
            abyssalActivatedThisRound = false;
            inPickPhase = false;
            pendingRegicideCheck = false;
            LocalShotsThisMatch = 0;
            LocalBlocksThisMatch = 0;
            LocalKeysThisMatch = 0;
            LocalMacroSuspectSeconds = 0;
            LocalMacroPeakKeysPerSecond = 0;
            LocalMacroPeakClicksPerSecond = 0;
            LocalMacroPeakEventsPerSecond = 0;
            inputSuspectWindows.Clear();
            inputBucketTimer = 0f;
            inputBucketCount = 0;
            inputBucketKeyCount = 0;
            inputBucketClickCount = 0;
            inputBucketStartedAtMs = -1;
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
            // July 21 item 2: per-match telemetry resets.
            localFpsTimeline.Clear(); tlFrames = 0; tlAccum = 0f;
            bcFrames = 0; bcAccum = 0f; lastBroadcastRecentFps = 0;
            oppFpsTimeline.Clear(); oppPingTimeline.Clear(); lastOppGstatsSeq = -1; lastOppSeqAdvanceTime = -1f;
            localFreezeCount = 0; localFreezeFocusedCount = 0; localFreezeTotalSec = 0f;
            pingSamples.Clear(); localRecvGapCount = 0; localRecvGapMaxMs = 0; _recvGapOpen = false;
            oppHbGapCount = 0; _oppHbGapOpen = false;
            oppFreezeCount = 0; oppFreezeFocusedCount = 0; oppRecvGapCount = 0;
            _lastTickStopwatchMs = -1;
            _hitsRemaining = 0;
            _activationSuccessCredited = true;
            BlockChain.Reset();
            _loggedHitBudgetDrop = false;
            // July 22 item 1/7: hit/block timelines + point stamps + per-actor harvest.
            localHitTimeline.Clear(); localBlockTimeline.Clear();
            oppHitTimeline.Clear(); oppBlockTimeline.Clear();
            localFps3sTimeline.Clear();
            pointTimes.Clear();
            LocalDamageTakenThisMatch = 0f;
            peerTele.Clear();
            OppStatMacroSuspectSeconds = 0;
            OppStatMacroPeakKeysPerSecond = 0;
            OppStatMacroPeakClicksPerSecond = 0;
            OppStatMacroPeakEventsPerSecond = 0;
            OppStatMacroTimeline = "";

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
        /// <summary>Like IsInRoom but false for Sandbox / offline practice.
        /// Photon's OfflineMode simulates a room, and ROUNDS keeps that offline
        /// "room" alive at the main menu after leaving Sandbox — so anything
        /// gating UI on "in a game" via IsInRoom stays stuck after a Sandbox
        /// visit (bug #46: the ranked Disable button vanished until relaunch).</summary>
        public static bool IsInOnlineRoom
        {
            get
            {
                if (!wasInRoom) return false;
                try { return !PhotonNetwork.OfflineMode; } catch { return true; }
            }
        }
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
