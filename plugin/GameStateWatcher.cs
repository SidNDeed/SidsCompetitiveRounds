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
    /// <summary>Bounded telemetry series that COMPRESSES instead of stopping
    /// (Stan bug 181 root cause — the old hard 128-sample cap was a 6:24
    /// recording ceiling every 2v2/FFA game overran). At the cap the series
    /// drops every other sample and doubles its stride, so it always spans
    /// the whole game in at most 128 entries: 6.4 min at 3s/sample, 12.8 at
    /// 6s, 25.6 at 12s... Renderers must scale the x-axis by the real match
    /// duration rather than assuming a fixed cadence. Shared by
    /// GameStateWatcher and FfaMode.</summary>
    internal sealed class DecimatedList<T>
    {
        public readonly List<T> Items = new List<T>();
        private int stride = 1;
        private int tick;

        public int Count => Items.Count;

        public void Add(T value)
        {
            if ((tick++ % stride) != 0) return;
            Items.Add(value);
            if (Items.Count >= 128)
            {
                int half = Items.Count / 2;
                for (int i = 0; i < half; i++) Items[i] = Items[i * 2];
                Items.RemoveRange(half, Items.Count - half);
                stride *= 2;
            }
        }

        public void Clear()
        {
            Items.Clear();
            stride = 1;
            tick = 0;
        }
    }

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
        private static readonly DecimatedList<int> localFpsTimeline = new DecimatedList<int>();   // decimates at cap
        private static int tlFrames = 0;
        private static float tlAccum = 0f;
        private static int bcFrames = 0;          // frames since last 3s broadcast (instantaneous fps)
        private static float bcAccum = 0f;
        private static int gstatsSeq = 0;         // monotonic broadcast counter (heartbeat)
        private static int lastBroadcastRecentFps = 0;
        private static readonly DecimatedList<int> oppFpsTimeline = new DecimatedList<int>();     // decimates at cap
        private static readonly DecimatedList<int> oppPingTimeline = new DecimatedList<int>();    // July 22 item 3: opp ping via gstats field 12
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
        // hover graphs. Own side sampled on the 3s cadence; opponent side per
        // cr_gstats seq-advance (same rhythm their other telemetry arrives on).
        // Advisory, never in the HMAC.
        //
        // Aug 8 (Stan bug 181 root cause): these were hard-capped at 128
        // samples — a 6:24 recording CEILING at the 3s cadence that every
        // 2v2/FFA game overran (prod averages 544s/643s), so graphs silently
        // ended a third of the way through the match while the totals kept
        // counting (41% summary vs 36% graph, off for every player). Now they
        // DECIMATE instead of stopping: at the cap the series drops every
        // other sample and doubles its stride, so it always spans the whole
        // game at bounded size. The renderers scale their x-axis by the real
        // match duration, so variable cadence is invisible to them.
        private static readonly DecimatedList<string> localHitTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> localBlockTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> oppHitTimeline = new DecimatedList<string>();
        private static readonly DecimatedList<string> oppBlockTimeline = new DecimatedList<string>();
        // Own fps at the 3s broadcast cadence — the 2v2 report ships this for
        // the local slot so all four players' fps series share one cadence
        // (the 1v1 report keeps using the 5s localFpsTimeline unchanged).
        private static readonly DecimatedList<int> localFps3sTimeline = new DecimatedList<int>();
        // Aug 7 item 3: own cumulative damage dealt on that SAME 3s cadence,
        // for the 2v2/1v2 reports. The 1v1 report keeps its own 5s
        // localDamageTimeline unchanged.
        private static readonly DecimatedList<int> localDamage3sTimeline = new DecimatedList<int>();
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
            public readonly DecimatedList<int> fps = new DecimatedList<int>();
            public readonly DecimatedList<int> ping = new DecimatedList<int>();
            public readonly DecimatedList<string> hit = new DecimatedList<string>();
            public readonly DecimatedList<string> block = new DecimatedList<string>();
            public readonly DecimatedList<int> damage = new DecimatedList<int>();   // Aug 7 item 3, cumulative
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
        /// <summary>Spectator snapshot epoch (SpectatorSync.BuildSnapshot):
        /// bumps at each game-over, so a rematch is visible as a change.</summary>
        public static int SessionMatchCountValue => sessionMatchCount;

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
        // Bug #91 comment 2: 1v2 games used to fall through to the CASUAL
        // session counters (the ovt guard made the ranked branch false, so the
        // else ran) and recorded no opponents at all. They get their own bucket.
        private static int sessionOvtWins = 0;
        private static int sessionOvtLosses = 0;
        // Bug #106: FFA games reach neither the polled OnGameOver path (banned
        // in ffa_ rooms) nor any session counter — Session Info showed nothing
        // after a whole FFA sitting. FFA gets its own pair (win = placed #1)
        // plus the placement list ("1,1,2,3") for the Session Info line.
        private static int sessionFfaWins = 0;
        private static int sessionFfaLosses = 0;
        private static readonly List<int> sessionFfaPlacements = new List<int>();
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

        // ── Aug 6 items 1+4: expanded combat telemetry (fed by CombatTelemetry.cs) ──
        // All reset in the same blocks as the counters above; all ride OUTSIDE
        // every HMAC canonical.
        public static float LocalDamageDealtThisMatch { get; private set; }
        public static float LocalMaxSingleHit { get; private set; }
        public static float LocalMaxHealthSeen { get; private set; }
        public static int LocalBestBounceKill { get; private set; }
        // Deaths observed LOCALLY for both seats (the reporter's observations
        // cover the opponent — #4, only one client reports). kind: 1 = out of
        // bounds, 2 = own bullet.
        public static int LocalDeaths { get; private set; }
        public static int LocalDeathsBoundary { get; private set; }
        public static int LocalDeathsOwnBullet { get; private set; }
        public static int OppDeathsObserved { get; private set; }
        public static int OppDeathsBoundaryObserved { get; private set; }
        public static int OppDeathsOwnBulletObserved { get; private set; }
        // Cumulative damage dealt sampled on the SAME 5s tick as
        // localFpsTimeline — the DPS chart's x-axis lines up with the FPS
        // chart for free. Opp side arrives via cr_gstats field 19 (cumulative,
        // sampled per seq advance ~3s).
        private static readonly DecimatedList<int> localDamageTimeline = new DecimatedList<int>();
        private static readonly DecimatedList<int> oppDamageTimeline = new DecimatedList<int>();
        /// <summary>True once ANY 22-field cr_gstats has been harvested from
        /// the peer this match. Codex round 1 (MEDIUM): without this, an
        /// 18-field (older) peer leaves the expanded Opp* fields at their
        /// reset ZEROES, and the reporter persists those zeroes as genuine
        /// observations alongside the real match duration — permanently
        /// depressing that player's ranked DPS average with data that was
        /// never measured. NULL-vs-zero is exactly the distinction #257
        /// exists for, so an unseen peer must report NOTHING, not 0.</summary>
        public static bool OppExpandedTelemetrySeen { get; private set; }
        public static float OppDamageDealt { get; private set; }
        public static float OppMaxSingleHit { get; private set; }
        public static float OppMaxHealthSeen { get; private set; }
        public static int OppBestBounceKill { get; private set; }

        public static void RecordLocalDamageDealt(float dmg)
        {
            if (dmg <= 0f || float.IsNaN(dmg) || float.IsInfinity(dmg)) return;
            if (dmg > 100000f) dmg = 100000f;   // sanity clamp (modded/degenerate)
            LocalDamageDealtThisMatch += dmg;
            if (dmg > LocalMaxSingleHit) LocalMaxSingleHit = dmg;
        }

        public static void RecordMaxHealthSample(float maxHealth)
        {
            if (maxHealth > LocalMaxHealthSeen && !float.IsInfinity(maxHealth) && maxHealth < 10000000f)
                LocalMaxHealthSeen = maxHealth;
        }

        public static void RecordBounceKill(int bounces)
        {
            if (bounces > LocalBestBounceKill && bounces < 100000) LocalBestBounceKill = bounces;
        }

        public static void RecordDeathObserved(bool isLocal, int kind)
        {
            if (isLocal)
            {
                LocalDeaths++;
                if (kind == 1) LocalDeathsBoundary++;
                else if (kind == 2) LocalDeathsOwnBullet++;
            }
            else
            {
                // In 2v2/1v2/FFA more than one non-local player dies; these
                // opp counters are only consumed by the 1v1 report, where
                // "not mine" IS the opponent. Other modes ignore them.
                OppDeathsObserved++;
                if (kind == 1) OppDeathsBoundaryObserved++;
                else if (kind == 2) OppDeathsOwnBulletObserved++;
            }
        }

        public static string LocalDamageTimelineCsv => string.Join(",", localDamageTimeline.Items);
        public static string OppDamageTimelineCsv => string.Join(",", oppDamageTimeline.Items);

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
        // 1v2 series tally (kept separate from the 1v1 BO3 counters above,
        // which deliberately never move in an ovt_ room). Surfaced so the
        // in-match HUD can show the real 1v2 score instead of a dead 0-0.
        public static int OvtSoloWins => ovtSoloWins;
        public static int OvtDuoWins => ovtDuoWins;
        // 1v2 session record (its own bucket — 1v2 is an unranked parallel
        // mode and must not move the 1v1 ranked or casual lines).
        public static int SessionOvtWins => sessionOvtWins;
        public static int SessionFfaWins => sessionFfaWins;
        public static int SessionFfaLosses => sessionFfaLosses;
        public static string SessionFfaPlacementsCsv
        {
            get
            {
                try { return string.Join(",", sessionFfaPlacements.ConvertAll(p => p.ToString()).ToArray()); }
                catch { return ""; }
            }
        }
        public static int SessionOvtLosses => sessionOvtLosses;
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
        /// "exists" response after a DC + reconnect, #33) so both the fighter
        /// HUD and the spectator room ledger pick up at the real score.</summary>
        public static bool AdoptSeriesScore(int myWins, int oppWins,
                                            int expectedRoomSeriesGeneration)
        {
            int roomSeriesGeneration = roomSeriesWinsLocal + roomSeriesLossesLocal;
            // Only the opening BO3 can carry games played before THIS room.
            // Later BO3s started here and are already fully represented by the
            // local room ledger; accepting a server seed there could re-phase a
            // new series with a delayed score from the one that just completed.
            if (expectedRoomSeriesGeneration != roomSeriesGeneration
                || roomSeriesGeneration != 0)
            {
                Plugin.Log.LogInfo($"[SESSION] Ignored resumed series score {myWins}-{oppWins} "
                                   + $"(room series generation sent={expectedRoomSeriesGeneration}, now={roomSeriesGeneration})");
                return false;
            }

            int seedWins = Mathf.Max(0, myWins);
            int seedLosses = Mathf.Max(0, oppWins);

            // INVARIANT: reconcile by REPLACING both current-BO3 projections
            // with the same component-wise floor; never += the server score.
            // A preflight callback may land after OnGameOver, so blind replace
            // would erase a real local result, while addition can double-count
            // a result the server response already includes. Max is monotonic
            // and idempotent. The queue-lock path applies before gameplay and
            // therefore adopts the exact server phase without this ambiguity.
            int mergedWins = Mathf.Max(roomGamesWonLocal, seedWins);
            int mergedLosses = Mathf.Max(roomGamesLostLocal, seedLosses);
            roomGamesWonLocal = mergedWins;
            roomGamesLostLocal = mergedLosses;
            currentSeriesGamesWon = mergedWins;
            currentSeriesGamesLost = mergedLosses;
            Plugin.Log.LogInfo($"[SESSION] Adopted resumed series score {mergedWins}-{mergedLosses} "
                               + $"(server {seedWins}-{seedLosses})");
            return true;
        }

        // ── Tournament context (bug 231, contract 1) ─────────────────────
        // Set by ApiClient's /series/preflight callback from the response's
        // "tournament" + "tournament_label" fields (both the "exists" and
        // "created" branches carry them), and seeded from room identity for
        // sct- rooms (whose game-1 preflight is skipped by the id-empty
        // gate). Rendered by CompetitiveUI.DrawMatchStatus as a gold line
        // ABOVE the "RANKED - Recording" banner. Per-ROOM state: cleared at
        // room join (fresh room) and at room exit next to
        // ActiveRankedSeriesId, so it can never leak into the next room
        // (#353). Deliberately NOT cleared in ResetMatchState — a tournament
        // BO3 spans several games in one room and the banner must survive
        // the per-game reset.
        private static bool tournamentMatch = false;
        private static string tournamentLabel = "";
        public static bool IsTournamentMatch => tournamentMatch;
        public static string TournamentLabel => tournamentLabel;
        public static void SetTournamentContext(bool isTournament, string label)
        {
            bool was = tournamentMatch;
            tournamentMatch = isTournament;
            // Sanitize ONCE here, never in the IMGUI draw path (#162 — the
            // label renders on every Repaint, so it must be stored ready to
            // draw with zero per-frame work). Em-dash -> ASCII hyphen: the
            // server's label style is "Async Tournament — Winners R2" and
            // non-ASCII glyph coverage is not guaranteed in every render
            // font (#47). Length cap keeps the line inside its fixed-width
            // banner rect (#199 — overflow paints over neighbors).
            string lbl = isTournament ? (label ?? "") : "";
            lbl = lbl.Replace('—', '-').Trim();
            if (lbl.Length > 52) lbl = lbl.Substring(0, 52);
            tournamentLabel = lbl;
            // Log only the false->true edge — the preflight legitimately
            // retries/re-arms (#101), and each response calls back here.
            if (isTournament && !was)
                Plugin.Log.LogInfo($"[POLL] Tournament match context set ({(tournamentLabel.Length > 0 ? tournamentLabel : "no label")})");
        }
        public static void ClearTournamentContext()
        {
            tournamentMatch = false;
            tournamentLabel = "";
        }

        // (The rated-continuation latch/handshake that lived here was CUT in
        // Codex tournament review r4 — see the KNOWN ISSUE comment on
        // PopUpHandler_StartPicking_Competitive_Patch in Plugin.cs for the
        // full history and why no seat-local or best-effort-replicated
        // predicate can safely widen the rematch auto-confirm. Do not
        // reintroduce without a real acknowledgment-barrier protocol.)

        // ── Resumed-series handoff from the QUEUE LOCK (bug 200) ────────────
        // The queue lock learns the resumed BO3 tally BEFORE the room is
        // joined, and the room-join branch below unconditionally zeroes the
        // tally ("Fresh room = new series") — so calling AdoptSeriesScore at
        // lock time would be wiped a moment later. Stash it here and consume it
        // inside that reset, which is the only ordering that survives.
        //
        // Keyed on the ROOM NAME the lock told us to join, NOT on the series id
        // alone: ActiveRankedSeriesId survives a failed join (it is cleared on
        // room LEAVE), so a series-id-only guard could paint a stale "1-0" onto
        // an unrelated room the player joined next — including a casual one.
        private static string pendingResumedRoom = "";
        private static int pendingResumedMyWins = 0;
        private static int pendingResumedOppWins = 0;

        /// <summary>Stage a resumed BO3 tally learned at queue-lock time, to be
        /// applied when (and only when) we actually join that room.</summary>
        public static void StashResumedSeriesScore(string roomName, int myWins, int oppWins)
        {
            if (string.IsNullOrEmpty(roomName)) return;
            pendingResumedRoom = roomName;
            pendingResumedMyWins = Mathf.Max(0, myWins);
            pendingResumedOppWins = Mathf.Max(0, oppWins);
            Plugin.Log.LogInfo($"[SESSION] Resumed series {pendingResumedMyWins}-{pendingResumedOppWins} staged for room {roomName}");
        }

        /// <summary>Consume the queue-lock stash, one-shot, and only for the
        /// exact room it was staged for.</summary>
        private static void TryConsumePendingResumedScore(string joinedRoom)
        {
            if (string.IsNullOrEmpty(pendingResumedRoom)) return;
            if (string.IsNullOrEmpty(joinedRoom) || joinedRoom != pendingResumedRoom)
            {
                // Joined a different room than the one this was staged for —
                // it can never apply. Drop it so it cannot leak into a later room.
                pendingResumedRoom = "";
                return;
            }
            int my = pendingResumedMyWins, opp = pendingResumedOppWins;
            pendingResumedRoom = "";   // one-shot, before the apply
            if (my > 0 || opp > 0)
                ApiClient.ApplyResumedSeriesScore(my, opp, RoomSeriesGeneration);
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
        private const string PP_SESSION_OVW           = "cr_session_ovt_wins";
        private const string PP_SESSION_OVL           = "cr_session_ovt_losses";
        private const string PP_SESSION_FFW           = "cr_session_ffa_wins";
        private const string PP_SESSION_FFL           = "cr_session_ffa_losses";
        private const string PP_SESSION_FFA_PLACES    = "cr_session_ffa_places";
        private const string PP_SESSION_WL_BY_OPP_FFA = "cr_session_wl_by_opp_ffa";
        private const string PP_SESSION_WL_BY_OPP     = "cr_session_wl_by_opp";
        // The 1v2 half of each per-opponent record lives in its OWN key rather
        // than widening the line format above (review find 2): an older build
        // parses that key with a strict 4-field check, so a 6-field write would
        // make it DROP every opponent row and then save the loss back.
        private const string PP_SESSION_WL_BY_OPP_1V2 = "cr_session_wl_by_opp_1v2";
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
                PlayerPrefs.SetInt(PP_SESSION_OVW, sessionOvtWins);
                PlayerPrefs.SetInt(PP_SESSION_OVL, sessionOvtLosses);
                PlayerPrefs.SetInt(PP_SESSION_FFW, sessionFfaWins);
                PlayerPrefs.SetInt(PP_SESSION_FFL, sessionFfaLosses);
                PlayerPrefs.SetString(PP_SESSION_FFA_PLACES, SessionFfaPlacementsCsv);
                // Encode WL dict: "name1=rW,rL,cW,cL|name2=..." — EXACTLY four
                // fields, unchanged, so an older build can still read it. The
                // 1v2 pair rides a separate key below.
                // Replace | = , in display names with safe placeholders before joining.
                var sbWl = new System.Text.StringBuilder();
                var sbWlV = new System.Text.StringBuilder();
                var sbWlF = new System.Text.StringBuilder();
                bool firstWl = true, firstWlV = true, firstWlF = true;
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
                    int vw = kv.Value.Length > 4 ? kv.Value[4] : 0;
                    int vl = kv.Value.Length > 5 ? kv.Value[5] : 0;
                    if (vw != 0 || vl != 0)
                    {
                        if (!firstWlV) sbWlV.Append('|');
                        sbWlV.Append(name).Append('=').Append(vw).Append(',').Append(vl);
                        firstWlV = false;
                    }
                    int fw = kv.Value.Length > 6 ? kv.Value[6] : 0;
                    int fl = kv.Value.Length > 7 ? kv.Value[7] : 0;
                    if (fw != 0 || fl != 0)
                    {
                        if (!firstWlF) sbWlF.Append('|');
                        sbWlF.Append(name).Append('=').Append(fw).Append(',').Append(fl);
                        firstWlF = false;
                    }
                }
                PlayerPrefs.SetString(PP_SESSION_WL_BY_OPP, sbWl.ToString());
                PlayerPrefs.SetString(PP_SESSION_WL_BY_OPP_1V2, sbWlV.ToString());
                PlayerPrefs.SetString(PP_SESSION_WL_BY_OPP_FFA, sbWlF.ToString());
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
                sessionOvtWins           = PlayerPrefs.GetInt(PP_SESSION_OVW, 0);
                sessionOvtLosses         = PlayerPrefs.GetInt(PP_SESSION_OVL, 0);
                sessionFfaWins           = PlayerPrefs.GetInt(PP_SESSION_FFW, 0);
                sessionFfaLosses         = PlayerPrefs.GetInt(PP_SESSION_FFL, 0);
                sessionFfaPlacements.Clear();
                foreach (var s in (PlayerPrefs.GetString(PP_SESSION_FFA_PLACES, "") ?? "").Split(','))
                    if (int.TryParse(s, out int pl) && pl > 0) sessionFfaPlacements.Add(pl);
                sessionWLByOpponent.Clear();
                foreach (var entry in (PlayerPrefs.GetString(PP_SESSION_WL_BY_OPP, "") ?? "").Split('|'))
                {
                    if (string.IsNullOrEmpty(entry)) continue;
                    int eq = entry.IndexOf('=');
                    if (eq <= 0) continue;
                    string name = entry.Substring(0, eq);
                    var parts = entry.Substring(eq + 1).Split(',');
                    // Tolerate 6 as well: a build between this one and v1.34.5
                    // briefly wrote the 1v2 pair inline before it moved to its
                    // own key.
                    if (parts.Length != 4 && parts.Length != 6) continue;
                    if (int.TryParse(parts[0], out int rw) && int.TryParse(parts[1], out int rl)
                        && int.TryParse(parts[2], out int cw) && int.TryParse(parts[3], out int cl))
                    {
                        int vw = 0, vl = 0;
                        if (parts.Length == 6)
                        {
                            int.TryParse(parts[4], out vw);
                            int.TryParse(parts[5], out vl);
                        }
                        sessionWLByOpponent[name] = new int[] { rw, rl, cw, cl, vw, vl };
                    }
                }
                // 1v2 half, keyed by the same (sanitized) display name.
                foreach (var entry in (PlayerPrefs.GetString(PP_SESSION_WL_BY_OPP_1V2, "") ?? "").Split('|'))
                {
                    if (string.IsNullOrEmpty(entry)) continue;
                    int eq = entry.IndexOf('=');
                    if (eq <= 0) continue;
                    string name = entry.Substring(0, eq);
                    var parts = entry.Substring(eq + 1).Split(',');
                    if (parts.Length != 2) continue;
                    if (!int.TryParse(parts[0], out int vw2) || !int.TryParse(parts[1], out int vl2)) continue;
                    int[] rec;
                    if (!sessionWLByOpponent.TryGetValue(name, out rec) || rec == null || rec.Length < 6)
                    {
                        var grown = new int[6];
                        if (rec != null) Array.Copy(rec, grown, Math.Min(rec.Length, 6));
                        sessionWLByOpponent[name] = rec = grown;
                    }
                    rec[4] = vw2; rec[5] = vl2;
                }
                // FFA half (bug #106), keyed by the same sanitized name.
                foreach (var entry in (PlayerPrefs.GetString(PP_SESSION_WL_BY_OPP_FFA, "") ?? "").Split('|'))
                {
                    if (string.IsNullOrEmpty(entry)) continue;
                    int eq = entry.IndexOf('=');
                    if (eq <= 0) continue;
                    string name = entry.Substring(0, eq);
                    var parts = entry.Substring(eq + 1).Split(',');
                    if (parts.Length != 2) continue;
                    if (!int.TryParse(parts[0], out int fw2) || !int.TryParse(parts[1], out int fl2)) continue;
                    int[] rec;
                    if (!sessionWLByOpponent.TryGetValue(name, out rec) || rec == null || rec.Length < 8)
                    {
                        var grown = new int[8];
                        if (rec != null) Array.Copy(rec, grown, Math.Min(rec.Length, 8));
                        sessionWLByOpponent[name] = rec = grown;
                    }
                    rec[6] = fw2; rec[7] = fl2;
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

        // One-shot latch for the spectator quiesce below.
        private static bool spectatorQuiesced = false;

        public static void Poll()
        {
            // Spectator lifecycle tick FIRST, before any early return (Codex
            // r2 find 2: placed after the spectator quiesce, the LeaveRequested
            // backstop was unreachable in exactly the stuck state it exists
            // for). Cheap flag checks.
            try { SpectatorSession.TickPendingClear(); } catch { }

            // SPECTATOR (design §3.5): the whole watcher sleeps — no room
            // watchdogs, no match tracking, no card/FPS/telemetry publishing,
            // no report paths. One reset on entry clears any fighter-session
            // state carried in from before the grant; everything stays down
            // until the session ends.
            if (RoomActors.LocalIsSpectator)
            {
                if (!spectatorQuiesced)
                {
                    spectatorQuiesced = true;
                    // Plain ResetMatchState — NOT the WithTrail variant
                    // (playtest #2a): the trail/color/effect OnMatchEnd calls
                    // revert cosmetics and stop the anim loops, and no fighter
                    // OnMatchStart ever runs on a spectator to restart them —
                    // which is why fighters rendered bare. SpectatorSync's
                    // activation runs the cosmetic start hooks instead.
                    try { ResetMatchState(); } catch { }
                    Plugin.Log.LogInfo("[SPECTATE] GameStateWatcher quiesced");
                }
                // The ONE thing a quiesced spectator still needs: without this
                // the runInBackground override never runs on an observer seat,
                // so alt-tabbing freezes the very seat the patch exists to keep
                // alive on any client whose Unity default is false.
                try { TickRunInBackground(); } catch { }
                return;
            }
            spectatorQuiesced = false;

            pollTimer += Time.deltaTime;
            if (pollTimer < 0.1f) return;
            pollTimer = 0f;

            PollRoomState();
            PollMatchState();
            if (isTracking) TryRefreshSharedGameToken();
            PollRoomlessGameScene();
            TickSpectateAttest();
        }

        // ── Spectator attestation ticker (design §6.3, fighter side) ─────
        // Every fighter independently attests the live room every 60s so the
        // server can list the game once ALL fighters agree; the master also
        // revalidates claimed spectator actors on the same cadence. Both are
        // fire-and-forget; nothing in the match waits on either.
        private static float lastSpectateAttestAt = -999f;
        private static float lastSpectateValidateAt = -999f;
        private static bool lastSpectateBattleState = false;
        // Master-seat edge for the validate cadence (design-review find 15: a
        // non-master's stamped timer starved a fresh master of validations
        // for up to 60s after a handoff).
        private static bool lastSpectateWasMaster = false;

        // Room-scoped 1v1 tally for the spectator snapshot (design-review
        // find 10). Reset ONLY on actual room join. The opening BO3's
        // roomGames* phase may be seeded by AdoptSeriesScore when the server
        // resumes a cross-room series; after that, local game-over outcomes
        // are the sole writer and the roomSeries* completed tally stays local.
        private static int roomSeriesWinsLocal = 0;
        private static int roomSeriesLossesLocal = 0;
        private static int roomGamesWonLocal = 0;
        private static int roomGamesLostLocal = 0;
        // The reliable Photon callback owns the score reset. The 10 Hz room
        // edge checks this marker before running its fallback reset, otherwise
        // it would wipe a resumed score consumed by the callback moments ago.
        private static string callbackResetScoreRoom = "";
        public static int RoomSeriesWinsLocal => roomSeriesWinsLocal;
        public static int RoomSeriesLossesLocal => roomSeriesLossesLocal;
        // Monotonic within a room because the two completed-series counters
        // reset only on room join. Captured by async score-adoption requests so
        // a response from the opening BO3 cannot mutate a later one.
        public static int RoomSeriesGeneration => roomSeriesWinsLocal + roomSeriesLossesLocal;

        /// <summary>Room-scoped spectate/attest edge state reset — called
        /// from the ACTUAL Photon room callbacks (Aug 10 r2 find 8: the 10 Hz
        /// poll's wasInRoom sampling can miss a leave+join inside one tick,
        /// letting room B inherit room A's battle edge and attest timer). The
        /// poll-side resets remain as backup.</summary>
        public static void ResetSpectateAttestEdges(bool alsoRoomTally)
        {
            lastSpectateAttestAt = -999f;
            lastSpectateValidateAt = -999f;
            lastSpectateBattleState = false;
            spectateAttestEdgePending = false;
            lastSpectateWasMaster = false;
            if (alsoRoomTally)
            {
                roomSeriesWinsLocal = 0;
                roomSeriesLossesLocal = 0;
                roomGamesWonLocal = 0;
                roomGamesLostLocal = 0;
                currentSeriesGamesWon = 0;
                currentSeriesGamesLost = 0;

                string joinedRoom = "";
                try { joinedRoom = PhotonNetwork.CurrentRoom?.Name ?? ""; } catch { }
                callbackResetScoreRoom = joinedRoom;
                // The callback cannot miss a fast leave+join between poll
                // samples. Consume after every score reset; the poll path
                // below remains the fallback when no callback marker exists.
                TryConsumePendingResumedScore(joinedRoom);
            }
            else callbackResetScoreRoom = "";
        }
        // Armed on a battle rising edge; cleared only when an attest SENDS.
        private static bool spectateAttestEdgePending = false;

        /// <summary>Sid (playtest, Aug 7): PRIVATE/code-room ranked 1v1s are
        /// spectatable too. True while this client is in a live RANKED
        /// 1v1 whose room is NOT queue-issued (the #286 population).
        /// matchIsRanked already requires a modded, consenting opponent
        /// (#121/#106), and attestation still requires BOTH fighters'
        /// strict sessions — so both clients are provably on spectator-
        /// aware builds before the game can be listed.</summary>
        public static bool RankedCodeRoom1v1InProgress
        {
            get
            {
                try
                {
                    if (!matchIsRanked || !isTracking) return false;
                    if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                    string rn = PhotonNetwork.CurrentRoom?.Name ?? "";
                    if (rn.StartsWith("ranked_", StringComparison.Ordinal)
                        || rn.StartsWith("team_", StringComparison.Ordinal)
                        || rn.StartsWith("ovt_", StringComparison.Ordinal)
                        || rn.StartsWith("ffa_", StringComparison.Ordinal)
                        || rn.StartsWith("sct-", StringComparison.Ordinal)) return false;
                    if (Diag2v2.IsActive()) return false;   // team-shaped rooms are out
                    return RoomActors.ActiveFighterCount() == 2;
                }
                catch { return false; }
            }
        }

        private static void TickSpectateAttest()
        {
            try
            {
                if (RoomActors.LocalIsSpectator) return;
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                // sct- (sync tournament) rooms ARE 1v1 rooms and attest as
                // such (Codex tournament r1 find 3: without this the mode map
                // rejected the prefix, so a sync tournament match could never
                // be listed — making "tournament games are mandatorily
                // spectatable" structurally unreachable for sync brackets).
                // The server accepts the prefix ONLY against the bracket
                // match's own photon_room_name mapping (fail-closed, no code-
                // room fallback trust). Seat reservation needs no bump here:
                // the QueueJoiner creates every sct- room with
                // fighterTarget + SEAT_CAP MaxPlayers like the queue rooms.
                string mode =
                    room.StartsWith("ranked_", StringComparison.Ordinal) ? "1v1"
                    : room.StartsWith("sct-", StringComparison.Ordinal) ? "1v1"
                    : room.StartsWith("team_", StringComparison.Ordinal) ? "2v2"
                    : room.StartsWith("ovt_", StringComparison.Ordinal) ? "1v2"
                    : room.StartsWith("ffa_", StringComparison.Ordinal) ? "ffa"
                    : "";
                bool codeRoom = false;
                if (mode.Length == 0)
                {
                    // Private/code ranked 1v1s (Sid, Aug 7 playtest request).
                    if (!RankedCodeRoom1v1InProgress) return;
                    mode = "1v1";
                    codeRoom = true;
                }
                if (!isTracking) return;        // only while a game is live

                // Code rooms are created by VANILLA with MaxPlayers=2 — the
                // master reserves the spectator seats and hides the room the
                // moment the ranked game is live (queue rooms get this at
                // creation). Runtime MaxPlayers/IsVisible changes are room
                // property ops the shipped Photon supports (design §4.1
                // option 2). Idempotent; master-only.
                if (codeRoom && PhotonNetwork.IsMasterClient)
                {
                    try
                    {
                        var cr = PhotonNetwork.CurrentRoom;
                        if (cr != null && cr.MaxPlayers < 2 + SpectatorSession.SEAT_CAP)
                        {
                            cr.MaxPlayers = (byte)(2 + SpectatorSession.SEAT_CAP);
                            cr.IsVisible = false;
                            Plugin.Log.LogInfo("[SPECTATE] reserved spectator seats on private ranked room");
                        }
                    }
                    catch (Exception ex) { Plugin.Log.LogWarning($"[SPECTATE] seat reserve: {ex.Message}"); }
                }

                // Master: revalidate claimed spectators (entry validation runs
                // from the enter callback; this closes mid-match revocation)
                // and kick any that never validated (fail closed, r1 find 3).
                // MASTER-ONLY cadence (Aug 10 design review finds 15 + fighter
                // lag): a non-master must not stamp the timer (a fresh master
                // would inherit it and withhold validations for up to 60s),
                // and the unvalidated-kick sweep belongs on the same 60s
                // cadence — it was accidentally running at the full 10 Hz
                // poll rate, allocating actor arrays on the master every tick.
                bool specMaster = PhotonNetwork.IsMasterClient;
                if (specMaster && !lastSpectateWasMaster)
                {
                    // Became master mid-room: the validation map is
                    // master-local state the old master took with it — reset
                    // and validate immediately so spectator snapshot requests
                    // are not rejected for the rest of the cadence window.
                    try { SpectatorSync.MasterResetSpectatorState(); } catch { }
                    lastSpectateValidateAt = -999f;
                }
                lastSpectateWasMaster = specMaster;
                if (specMaster && Time.unscaledTime - lastSpectateValidateAt > 60f)
                {
                    lastSpectateValidateAt = Time.unscaledTime;
                    try { ApiClient.SpectateValidateActors(); } catch { }
                    try { SpectatorSync.MasterSweepUnvalidated(); } catch { }
                }

                // Battle-phase EDGE detection runs BEFORE the throttle (Codex
                // r3: placed after it, the edge was unreachable during the
                // 60s window and a short battle never stamped last_battle_at).
                // The edge stays ARMED until an attest actually goes out
                // (Codex r4: stamping the throttle before roster validation
                // consumed the edge on an incomplete roster and the short
                // battle still never attested). Timer + edge are cleared at
                // the SEND site only.
                bool battle = false;
                try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                if (battle && !lastSpectateBattleState) spectateAttestEdgePending = true;
                lastSpectateBattleState = battle;

                if (!spectateAttestEdgePending && Time.unscaledTime - lastSpectateAttestAt < 60f) return;
                var fighters = RoomActors.ActiveFighters();
                int target;
                if (mode == "2v2") target = 4;
                else if (mode == "1v2") target = 3;
                else if (mode == "ffa")
                {
                    // LIVE fighter count, not cr_ffa_n (Codex r2 find 14): the
                    // locked size goes stale the moment a leaver drops out,
                    // and a roster/target mismatch silently stops attesting.
                    target = fighters.Length;
                }
                else target = 2;

                var sids = new List<string>(fighters.Length);
                foreach (var f in fighters)
                {
                    var s = RoomActors.SteamIdOf(f);
                    if (!string.IsNullOrEmpty(s)) sids.Add(s);
                }
                // Canonical roster string: sorted ordinal — every fighter must
                // produce the identical byte sequence (design §6.3).
                sids.Sort(StringComparer.Ordinal);
                if (sids.Count != target) return;   // roster incomplete — nothing to attest yet

                // Roster-freeze catch-up: code rooms never pass the
                // OnMatchStarted competitive gate (#286), so freeze here the
                // first time a complete attestable roster exists. Idempotent
                // for queue rooms (already frozen at match start).
                try { if (!RoomActors.RosterFrozen) RoomActors.FreezeFighterRoster(sids); } catch { }

                string sourceRef =
                    mode == "1v1" ? (ApiClient.ActiveRankedSeriesId ?? "")
                    : mode == "2v2" ? (ApiClient.ActiveTeamSeriesId ?? "")
                    : mode == "1v2" ? (ApiClient.ActiveOvt1v2SeriesId ?? "")
                    : (ApiClient.ActiveFfaLobbyId ?? "");
                string region = "";
                try { region = PhotonNetwork.CloudRegion?.Replace("/*", "") ?? ""; } catch { }
                int actor = -1;
                try { actor = PhotonNetwork.LocalPlayer?.ActorNumber ?? -1; } catch { }
                int cap = 0;
                try { cap = PhotonNetwork.CurrentRoom?.MaxPlayers ?? 0; } catch { }

                // SEND site: throttle + edge are consumed together, only on a
                // send that actually happens (r4 — validations above return
                // without consuming either).
                lastSpectateAttestAt = Time.unscaledTime;
                spectateAttestEdgePending = false;
                ApiClient.SpectateAttest(mode, sourceRef, room, region, actor, target, cap,
                                         battle ? "battle" : "transition",
                                         string.Join(",", sids.ToArray()));
            }
            catch { }
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
                    // Fighter count (census): a lone searcher + a spectator must
                    // not read as "full room, no game" and fire the requeue.
                    && RoomActors.ActiveFighterCount() >= 2
                    && GM_ArmsRace.instance == null)
                {
                    string rn = PhotonNetwork.CurrentRoom.Name ?? "";
                    var props = PhotonNetwork.CurrentRoom.CustomProperties;
                    bool modRoom = rn.StartsWith("ranked_") || rn.StartsWith("sct-") || rn.StartsWith("ovt_")
                                   || rn.StartsWith("ffa_")
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
                try { CompetitiveUI.ShowNotification("Matchmaking hiccup — putting you back in the Quick Match queue...", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
            }
            else
            {
                try { CompetitiveUI.ShowNotification("Connection was lost — returning to menu.", new Color(1f, 0.8f, 0.3f), 6f); } catch { }
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
                            try { CompetitiveUI.ShowNotificationCritical("Couldn't recover automatically - please restart matchmaking from the menu.", new Color(1f, 0.5f, 0.4f), 8f); } catch { }
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
                        try { CompetitiveUI.ShowNotification("Back in the Quick Match queue — searching for an opponent.", new Color(0.5f, 1f, 0.6f), 5f); } catch { }
                    }
                    catch (Exception ex)
                    {
                        Plugin.Log.LogWarning($"[QUICKPLAY-GUARD] requeue failed: {ex.Message}");
                        try { CompetitiveUI.ShowNotificationCritical("Couldn't recover automatically - please restart matchmaking from the menu.", new Color(1f, 0.5f, 0.4f), 8f); } catch { }
                    }
                    break;
            }
        }

        /// <summary>Per-Unity-frame tick; counts frames + accumulates real time so we
        /// can report a true average FPS for this match. Cheap (no allocations, no
        /// reflection); also broadcasts the running average via Photon every ~3s so
        /// the opponent can read it. Only active while a match is being tracked.</summary>
        private static bool _lastBattleForPoisonEdge;
        public static void TickFrame()
        {
            // [NET] telemetry BEFORE the spectator early-return — the
            // spectator seat needs the ping/fps/dispatch line most (bug 217:
            // the whole latency question was unanswerable from a bundle).
            try { NetDiag.Tick(); } catch { }
            // Battle-resume rising edge closes PoisonSync's boundary-orphan
            // window (bug 221 review r1: a flat window overshot into real
            // combat). Every seat, every mode — FfaMode sets battleOngoing in
            // its own transitions (#222), vanilla sets it everywhere else.
            bool battleNow = false;
            try { battleNow = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
            // Bug 235: serialization silence is meaningful only during active
            // combat. Falling edges clear timing baselines so pick/map/death
            // intervals cannot masquerade as peer stalls. A spectator suppresses
            // the local GM writers of battleOngoing; its validated reconcile /
            // observed-round edges drive the same gate from the diagnostics patch.
            try
            {
                if (!RoomActors.LocalIsSpectator)
                    NetworkReplicaDiagnostics.SetBattleActive(battleNow);
            }
            catch { }
            if (battleNow && !_lastBattleForPoisonEdge)
            {
                try { PoisonSync.NoteBattleResumed(); } catch { }
            }
            _lastBattleForPoisonEdge = battleNow;
            // Spectator: no local input tracking, no KPS/macro metrics, no
            // spawn-grace edges — there is no local fighter to measure.
            if (RoomActors.LocalIsSpectator) return;
            // Bug #119: rising-edge detector for the FFA spawn grace window.
            // Runs BEFORE the isTracking gate — the window opens the instant
            // vanilla re-enables the local player at the end of Move, which is
            // a per-frame edge (#120: sampling edges from the 10Hz poll drops
            // ~97% of them). Self-gated to FFA rooms.
            try { FfaMode.TickSpawnGrace(); } catch { }
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
                localFpsTimeline.Add((int)Math.Round(tlFrames / (double)tlAccum));
                // Aug 6 item 4: cumulative damage dealt on the same 5s grid,
                // so the DPS chart shares the FPS chart's x-axis. Same cap.
                localDamageTimeline.Add((int)LocalDamageDealtThisMatch);
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
                // FFA kills + damage-dealt, all players, same 3s x-axis as
                // hit/block so the /game chart panels line up (#127/#130).
                try { FfaMode.SampleTimelines(); } catch { }
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
            // AnyChatTyping, not just OUR box (bug #128 FINDING 8): a left-click
            // to place the caret in ROUNDS' own Enter chat was counting as a shot
            // fired, and bullets_fired is the accuracy DENOMINATOR (#137) — so
            // chatting mid-round quietly deflated hit%.
            bool typingInChat = false;
            try { typingInChat = CompetitiveUI.AnyChatTyping || NativeUI.IsOpen; } catch { }
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
                $"|{LocalMacroSuspectSeconds}|{LocalMacroPeakKeysPerSecond}|{LocalMacroPeakClicksPerSecond}|{LocalMacroPeakEventsPerSecond}|{MacroTimelineForPeer()}" +
                // Aug 6 items 1+4 — fields 19-22 (indexes 18-21): cumulative
                // damage dealt, max single hit, max health seen, best bounce
                // kill. Old clients ignore extras; parsers gate on Length.
                $"|{(int)LocalDamageDealtThisMatch}|{(int)LocalMaxSingleHit}|{(int)LocalMaxHealthSeen}|{LocalBestBounceKill}";
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
                if (recentFps > 0 && isTracking)
                    localFps3sTimeline.Add(recentFps);   // decimates at cap, never stops
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
                var players = RoomActors.ActiveFighters();   // census: only fighters carry gstats worth harvesting
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
                                // Aug 6 items 1+4: expanded telemetry (22-field clients).
                                if (parts.Length >= 22)
                                {
                                    OppExpandedTelemetrySeen = true;
                                    OppDamageDealt = int.Parse(parts[18]);
                                    OppMaxSingleHit = int.Parse(parts[19]);
                                    OppMaxHealthSeen = int.Parse(parts[20]);
                                    OppBestBounceKill = int.Parse(parts[21]);
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
                                        if (rf > 0) oppFpsTimeline.Add(rf);
                                        // Field 12 (July 22 item 3) — absent on 11-field clients.
                                        if (parts.Length >= 12)
                                        {
                                            int op = int.Parse(parts[11]);
                                            if (op > 0) oppPingTimeline.Add(op);
                                        }
                                        // Aug 6 item 4: opp cumulative damage-dealt series
                                        // (22-field clients), one sample per seq advance.
                                        if (parts.Length >= 22)
                                        {
                                            int od;
                                            if (int.TryParse(parts[18], out od)) oppDamageTimeline.Add(od);
                                        }
                                        // July 22 item 1: cumulative pair series.
                                        // Review [3]: regression = stale previous-game
                                        // sample got in first — restart the lists.
                                        int curFired;
                                        if (int.TryParse(parts[0], out curFired)
                                            && oppHitTimeline.Count > 0 && curFired < LastPairFirst(oppHitTimeline.Items))
                                        {
                                            oppHitTimeline.Clear();
                                            oppBlockTimeline.Clear();
                                        }
                                        oppHitTimeline.Add(parts[0] + ":" + parts[1]);
                                        // Bug 181 (Stan): v2 block pairs — "activated:
                                        // successful" (parts[2]:parts[3], on the wire since
                                        // day one). The old left value was damage TAKEN,
                                        // an unrelated quantity on a block-rate graph.
                                        if (parts.Length >= 4)
                                            oppBlockTimeline.Add(parts[2] + ":" + parts[3]);
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
                                    /* Codex round 2 (MEDIUM): the expanded
                                     * (22-field) telemetry has to be cleared
                                     * by this same new-game signal. Without
                                     * it, a quick rematch could finish before
                                     * the peer's next heartbeat and the
                                     * reporter would submit the PREVIOUS
                                     * game's damage, max-hit, max-health and
                                     * bounce record against the new match.
                                     * OppExpandedTelemetrySeen resets too, so
                                     * an unobserved peer correctly reports the
                                     * -1 "never observed" sentinel (-> NULL)
                                     * rather than a stale positive. */
                                    OppDamageDealt = 0f;
                                    OppMaxSingleHit = 0f;
                                    OppMaxHealthSeen = 0f;
                                    OppBestBounceKill = 0;
                                    OppExpandedTelemetrySeen = false;
                                    oppDamageTimeline.Clear();
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
            localHitTimeline.Add(LocalBulletsFiredThisMatch + ":" + LocalBulletsHitThisMatch);
            // Bug 181 (Stan): v2 block pairs — "activated:successful", the
            // real block-rate numerator/denominator (the old left value was
            // damage taken, an unrelated quantity on the same graph).
            localBlockTimeline.Add(LocalBlocksActivatedThisMatch + ":" + LocalBlocksSuccessfulThisMatch);
            // Aug 7 item 3: cumulative damage DEALT, same cadence as the pair
            // series above, so the 2v2/1v2 DPS chart shares their x-axis.
            localDamage3sTimeline.Add((int)LocalDamageDealtThisMatch);
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
                    && t.hit.Count > 0 && curFired < LastPairFirst(t.hit.Items))
                {
                    t.fps.Clear(); t.ping.Clear(); t.hit.Clear(); t.block.Clear(); t.damage.Clear();
                }
                int rf = int.Parse(parts[6]);
                if (rf > 0) t.fps.Add(rf);
                if (parts.Length >= 12)
                {
                    int op = int.Parse(parts[11]);
                    if (op > 0) t.ping.Add(op);
                }
                t.hit.Add(parts[0] + ":" + parts[1]);
                // Bug 181 (Stan): v2 block pairs (activated:successful).
                if (parts.Length >= 4)
                    t.block.Add(parts[2] + ":" + parts[3]);
                // Aug 7 item 3: field 19 (index 18) = the peer's cumulative
                // damage dealt. Same >=22 gate the 1v1 opp harvest uses (the
                // four expanded fields ship together). A pre-Aug-6 peer sends
                // none, so this list stays EMPTY rather than filling with
                // zeroes — "not recorded" must not read as "dealt none" (#257).
                if (parts.Length >= 22)
                {
                    int pd;
                    if (int.TryParse(parts[18], out pd)) t.damage.Add(pd);
                }
            }
            catch { }
        }

        /// <summary>Latest harvested telemetry for a peer by actor number, or null.
        /// Consumed by BuildTeamReportPayload when assembling per-slot telemetry
        /// — and note that peerTele is cleared per match, which is why that read
        /// happens at match end and never from the deferred submit.</summary>
        internal static bool TryGetPeerTelemetry(int actorNumber,
            out string fpsTl, out string pingTl, out string hitTl, out string blockTl,
            out string damageTl, out int[] counters)
        {
            fpsTl = pingTl = hitTl = blockTl = damageTl = null;
            counters = null;
            PeerTelemetry t;
            if (!peerTele.TryGetValue(actorNumber, out t) || string.IsNullOrEmpty(t.lastRaw)) return false;
            try
            {
                var parts = t.lastRaw.Split('|');
                if (parts.Length < 6) return false;
                fpsTl = string.Join(",", t.fps.Items);
                pingTl = string.Join(",", t.ping.Items);
                hitTl = string.Join(",", t.hit.Items);
                // "v2|" tags the activated:successful pair format so renderers
                // keep honest labels for legacy damage-taken rows (bug 181).
                blockTl = t.block.Count > 0 ? "v2|" + string.Join(",", t.block.Items) : "";
                // Empty for a peer that never published damage (pre-Aug-6
                // client) — the report must carry "" so the server can store
                // NULL, never a synthesised 0 (#257).
                damageTl = string.Join(",", t.damage.Items);
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

        // ── End-of-game BUILD stats (the hold-Tab overlay's 21 values) ─────
        //
        // TabStatsOverlay.CaptureBuildStats reads the LIVE Unity objects (Gun,
        // GunAmmo, CharacterStatModifiers, Block, HealthHandler), so the
        // snapshot has to be taken in the game-over frame itself: Player
        // .FullReset (the rematch path) and ResetMatchState wipe every one of
        // those, and the 2v2 report can run much later from the continuation
        // callback. Per #171 we never delay finalisation for telemetry and
        // never read state a reset may already have cleared — so: capture
        // once, synchronously, at game over; stash it; every report path
        // (including the deferred 2v2 one) reads the stash.
        //
        // Keyed by STEAM ID because that is the key all four report paths
        // already resolve (ResolvePhotonSteamId). A PlayerID-keyed stash would
        // need a second resolver, which is exactly how two keys drift apart.
        //
        // Lifetime: cleared at every match start (ResetPerMatchCombatCounters,
        // which BOTH OnMatchStarted and OnFfaMatchStarted call) and written
        // only while in the room during the live game — so it can never hand a
        // report a build from a previous game.
        //
        // The value is OPAQUE here. Only TabStatsOverlay builds or decodes it.
        private static readonly Dictionary<string, string> endStatsBySteam =
            new Dictionary<string, string>(6);
        private static string endStatsLocal;

        // The two Photon props a Steam ID can arrive under; see StashEndStats.
        private static readonly string[] END_STATS_ID_KEYS = { "u_id", "unity_id" };

        /// <summary>The end-of-game build stats captured for one player, or
        /// NULL when nothing was captured for them — an FFA leaver, a seat
        /// whose Steam ID never resolved, or a report finalised after the room
        /// was already gone.
        ///
        /// Callers must OMIT the field when this returns null rather than send
        /// "" or a row of dashes: the server stores NULL as "not recorded",
        /// which is not the same claim as a build of zeroes (#257).</summary>
        public static string EndStatsFor(string steamId)
        {
            if (string.IsNullOrEmpty(steamId)) return null;
            string wire;
            return endStatsBySteam.TryGetValue(steamId, out wire) ? wire : null;
        }

        /// <summary>The local seat's captured build. Same contract as
        /// EndStatsFor, and also reachable as EndStatsFor(localSteamId).</summary>
        public static string LocalEndStats { get { return endStatsLocal; } }

        /// <summary>One 2v2 game's report, fully resolved and frozen.
        ///
        /// The continuation-deferred 2v2 report (bug #70 self-heal) submits from
        /// an async callback that can land after game 2 has already started, and
        /// by then EVERY live input the report reads has moved on:
        ///
        ///   * matchIsRanked  — the teardown at the bottom of the block that
        ///     scheduled the deferral sets it false synchronously and
        ///     unconditionally, so a live read is deterministically wrong.
        ///   * the build stash, localCards, localFps3sTimeline / pingSamples /
        ///     localHitTimeline / localBlockTimeline / localDamage3sTimeline,
        ///     the Local*ThisMatch counters and peerTele — all cleared in place
        ///     by the next game's ResetPerMatchCombatCounters.
        ///   * the peers' cr_cards / cr_fps Photon props — game 2 overwrites
        ///     them with game 2's picks and frame rate.
        ///   * p1Rounds/p2Rounds/p1Points/p2Points and matchStartTime — game 2's
        ///     scores and start instant.
        ///   * RoomActors.ActiveFighters() and PlayerManager.players — a player
        ///     who leaves in between drops the census below four, which aborts
        ///     the report outright and loses that game's rating and gold.
        ///
        /// So the deferred path does not defer the REPORT; it defers only the
        /// SUBMIT. BuildTeamReportPayload resolves all of the above at match end
        /// while it is still true, and the callback supplies the one value it
        /// was waiting for and posts.
        ///
        /// EVERY field the wire call needs is owned here. The series id is
        /// deliberately NOT one of them: it is read live at submit time because
        /// obtaining it is the entire reason that path defers. Nothing else is.
        /// (Codex cold review finding 2; round 2 confirmed the first pass froze
        /// only rank/score/start/builds and left cards, telemetry and the roster
        /// live — and that its comment claimed otherwise.)</summary>
        private sealed class TeamReportPayload
        {
            public string RoomId;
            public string Region;
            public int DurationSeconds;
            public DateTime StartedAt;
            public bool IsRanked;
            public int T1Rounds, T2Rounds, T1Points, T2Points, WinnerTeam;
            public string ReporterSteam;
            /// <summary>False when the election picked someone else — the game
            /// is routed correctly, we are simply not the one posting it.</summary>
            public bool LocalIsReporter;
            // Slot order throughout: t1a, t1b, t2a, t2b.
            public string[] Steam = new string[4];
            public string[] Name = new string[4];
            public List<MatchTracker.CardPickData>[] Cards = new List<MatchTracker.CardPickData>[4];
            public int[] Fps = new int[4];
            public ApiClient.TeamTelemetry[] Tele = new ApiClient.TeamTelemetry[4];
            public string[] EndStats = new string[4];
        }

        /// <summary>Index one captured build under every spelling of its
        /// owner's id. ResolvePhotonSteamId validates numerically and falls
        /// back to "photon_N"; TryResolveOpponent stores the RAW u_id string
        /// with no validation at all. For a non-numeric platform id those two
        /// disagree, and the 1v1 lookup (which goes through opponentSteamId)
        /// would silently miss — so index both spellings.</summary>
        private static void StashEndStats(Dictionary<string, string> map,
                                          Photon.Realtime.Player owner, string wire)
        {
            string sid = ResolvePhotonSteamId(owner);
            if (!string.IsNullOrEmpty(sid)) map[sid] = wire;
            try
            {
                var props = owner.CustomProperties;
                if (props == null) return;
                foreach (var key in END_STATS_ID_KEYS)
                {
                    if (!props.ContainsKey(key)) continue;
                    string raw = props[key]?.ToString();
                    if (!string.IsNullOrEmpty(raw) && raw != sid) map[raw] = wire;
                }
            }
            catch { }
        }

        /// <summary>Snapshot every spawned player's build into the stash.
        /// Synchronous and allocation-light by design (one short string per
        /// player) so it can run in the game-over frame without delaying the
        /// report. Never throws out of a report path.</summary>
        private static void CaptureEndStats(string where)
        {
            try
            {
                // Out of the room there is nothing live to read: the 1v1
                // DC-win branch calls OnGameOver from the room-LEAVE handler,
                // so that is the normal case here. Deliberately does NOT clear
                // the stash — the snapshot taken at DC DETECTION, while the
                // room was still live, is that game's real build and has to
                // survive to the report.
                if (!PhotonNetwork.InRoom) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;

                var fresh = new Dictionary<string, string>(6);
                string mine = null;
                int captured = 0;
                foreach (var po in pm.players)
                {
                    // #222: departed players linger in PlayerManager.players in
                    // FFA and fake-null out — they have no build left to record.
                    if (po == null || po.data == null) continue;
                    string wire = TabStatsOverlay.CaptureBuildStats(po);
                    if (string.IsNullOrEmpty(wire)) continue;
                    var pv = po.GetComponent<PhotonView>();
                    // No owner = offline/sandbox, which is never reported. Note
                    // IsMine is true for EVERY view in offline mode, so the
                    // local seat is identified by Owner.IsLocal instead.
                    if (pv == null || pv.Owner == null) continue;
                    if (pv.Owner.IsLocal) mine = wire;
                    StashEndStats(fresh, pv.Owner, wire);
                    captured++;
                }

                // Nothing usable this time: keep whatever an earlier capture in
                // THIS game stashed rather than replacing real data with none.
                if (captured == 0) return;

                endStatsBySteam.Clear();
                foreach (var kv in fresh) endStatsBySteam[kv.Key] = kv.Value;
                endStatsLocal = mine;
                // The local seat's id comes from Steamworks, peers' from the
                // u_id prop. Index the local build under localSteamId as well,
                // so the 1v1 report — which looks its own side up by
                // localSteamId — cannot miss it if the two ever differ.
                if (!string.IsNullOrEmpty(mine) && !string.IsNullOrEmpty(localSteamId)
                    && localSteamId != "unknown")
                    endStatsBySteam[localSteamId] = mine;

                Plugin.Log.LogInfo($"[END-STATS] {where}: captured {captured} build snapshot(s)");
            }
            catch (Exception ex)
            {
                // Telemetry must never take a report path down.
                Plugin.Log.LogWarning($"[END-STATS] capture failed ({where}): {ex.Message}");
            }
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

        /// <summary>The runInBackground override, split out of PollRoomState so
        /// the SPECTATOR branch can call it too. Poll() early-returns for
        /// spectators well before PollRoomState — which is this override's only
        /// writer — so a spectator seat never got it. That defeats the whole
        /// point of the patch on any client whose Unity default is false: a
        /// spectator alt-tabbing gets exactly the frozen seat this fix exists to
        /// prevent. (Found while diagnosing bug 210; NOT that bug's cause — the
        /// reporter's own default was already true — but a real latent gap.)
        /// Idempotent and cheap: both arms are one-shot on a flag.</summary>
        private static void TickRunInBackground()
        {
            bool inRoom = PhotonNetwork.InRoom;
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
                // Room-exit edge, LOSSY BACKUP copy (review r4: a
                // leave+rejoin between poll samples never shows
                // InRoom==false here — the authoritative reset lives in
                // Plugin.OnLeftRoom, the callback that cannot miss).
                try { VanillaFixSupport.ResetDiag(StaleProjectileSweepPatch.DiagKey); } catch { }
            }
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
            // Body lives in TickRunInBackground so the spectator branch of
            // Poll() — which returns long before this method — gets it too.
            TickRunInBackground();

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
                                || rname.StartsWith("ovt_")
                                || FfaMode.EngineActive();
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
                // Spectate attest edge state is ROOM-scoped (design-review
                // find 14: joining room B <60s after leaving room A while
                // both battles were live produced no false->true edge, so B's
                // whole short first battle was never attested). Same for the
                // master-seat edge and the snapshot tally counters.
                lastSpectateAttestAt = -999f;
                lastSpectateValidateAt = -999f;
                lastSpectateBattleState = false;
                spectateAttestEdgePending = false;
                lastSpectateWasMaster = false;
                bool scoreResetByCallback = string.Equals(
                    callbackResetScoreRoom, photonRoomId, StringComparison.Ordinal);
                if (!scoreResetByCallback)
                {
                    roomSeriesWinsLocal = 0;
                    roomSeriesLossesLocal = 0;
                    roomGamesWonLocal = 0;
                    roomGamesLostLocal = 0;
                }
                try
                {
                    string pendingRoom = Plugin.PendingRankedRoom ?? "";
                    bool joinedOwnPendingRoom =
                        !string.IsNullOrEmpty(pendingRoom)
                        && string.Equals(photonRoomId, pendingRoom, StringComparison.Ordinal);
                    // Bug #112: only MOD-ISSUED competitive rooms end a 1v1
                    // search. Vanilla quickmatch/casual rooms (numeric Steam
                    // ids, constant region churn — learning #82) must NOT:
                    // searching ranked while playing casual is a supported
                    // pattern (LeavingForRanked yanks you out when it pops).
                    var joinProps = PhotonNetwork.CurrentRoom?.CustomProperties;
                    bool joinedCompetitiveRoom =
                        photonRoomId.StartsWith("ranked_") || photonRoomId.StartsWith("sct-")
                        || photonRoomId.StartsWith("ovt_") || photonRoomId.StartsWith("ffa_")
                        || photonRoomId.StartsWith("team_")
                        || (joinProps != null && joinProps.ContainsKey("cr_ff"));
                    if (!PhotonNetwork.OfflineMode
                        && joinedCompetitiveRoom
                        && ApiClient.CurrentQueueState == ApiClient.QueueState.Searching
                        && !joinedOwnPendingRoom)
                    {
                        ApiClient.LeaveQueue(GameStateWatcher.LocalSteamId);
                        CompetitiveUI.ShowNotification(
                            "Left 1v1 queue - you joined a game",
                            Color.yellow,
                            5f);
                        Plugin.Log.LogInfo(
                            $"[QUEUE] Left 1v1 queue after joining online room '{photonRoomId}'");
                    }
                    // Codex re-review find A: a PRE-ROOM 1v1 match (ready-up
                    // phase) must dissolve too, or the player holds two live
                    // commitments (1v1 popup + this game).
                    //
                    // Aug 9 bet audit r2 find 5: this used DeclineMatch, which
                    // puts BOTH rows back to 'searching' - so the player in
                    // this room kept polling and stayed matchable, the exact
                    // ghost the room-entry teardown exists to remove.
                    // LeaveQueue deletes OUR row; the server's own eviction
                    // resets the innocent partner.
                    else if (!PhotonNetwork.OfflineMode
                             && joinedCompetitiveRoom
                             && (ApiClient.CurrentQueueState == ApiClient.QueueState.Matched
                                 || ApiClient.CurrentQueueState == ApiClient.QueueState.ReadySent)
                             && !joinedOwnPendingRoom)
                    {
                        ApiClient.LeaveQueue(GameStateWatcher.LocalSteamId);
                        CompetitiveUI.ShowNotification(
                            "Left the 1v1 match queue - you joined a game",
                            Color.yellow,
                            5f);
                        Plugin.Log.LogInfo(
                            $"[QUEUE] Auto-declined pre-room 1v1 match after joining online room '{photonRoomId}'");
                    }
                    // Open FFA host-lobby membership + room entry, bug #132
                    // revision (Codex batch find 5 caught this hook still on
                    // the old rule): a CASUAL room may carry an open lobby
                    // seat — waiting in casual is Sid's design, and the Start
                    // countdown pulls the member out when the lobby fires.
                    // Only a COMPETITIVE room still evicts the seat (a lock
                    // firing mid-ranked-game would yank the player, #150).
                    // Our OWN lock transition clears OpenFfaLobbyId before
                    // the ffa_ room join, so this never fires on the lobby's
                    // own game.
                    if (!PhotonNetwork.OfflineMode
                        && joinedCompetitiveRoom
                        && !string.IsNullOrEmpty(ApiClient.OpenFfaLobbyId))
                    {
                        Plugin.Log.LogInfo(
                            $"[FFA-LOBBY] joined competitive room '{photonRoomId}' while in an open lobby — leaving the lobby");
                        // Pre-room cause: this is an open-lobby SEAT being
                        // abandoned, not an exit from the ffa_ room itself.
                        try { ApiClient.FfaLeaveQueue("seat_abandon"); } catch { }
                        CompetitiveUI.ShowNotification(
                            "Left your FFA lobby - you joined a competitive game",
                            Color.yellow,
                            5f);
                    }
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning(
                        $"[QUEUE] Failed to leave 1v1 queue on room join: {ex.Message}");
                }
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
                // Bug 231: tournament banner context is per-room, like the
                // flags above — a fresh room must never inherit it (#353).
                ClearTournamentContext();
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
                                || rname.StartsWith("ovt_")
                                || FfaMode.EngineActive();
                    if (isModIssued)
                    {
                        matchIsRanked = true;
                        opponentIsRanked = true;
                        Plugin.Log.LogInfo($"[POLL] mod-issued competitive room detected ({rname}) — matchIsRanked forced true");
                        // Bug 231: an sct- room IS a tournament match by
                        // construction (only the sync-tournament dispatcher
                        // issues that prefix), and its series pre-exists the
                        // room — the game-1 /series/preflight that would
                        // carry the tournament fields is skipped by the
                        // ActiveRankedSeriesId id-empty gate below. Seed the
                        // gold banner from room identity (generic label); a
                        // later preflight response (rematch series) upgrades
                        // or honestly clears it.
                        if (rname.StartsWith("sct-"))
                            SetTournamentContext(true, "");
                    }
                }
                catch { }
                seriesPreflightSent = false;
                lastOpponentRankCheck = -999f;
                // (#26) Re-arm the opponent-never-arrived watchdog for this room.
                rankedRoomStallHandled = false;
                rankedRoomStallWarned = false;
                rankedRoomEverFull = false;
                // Fresh room = new series. The reliable Photon callback
                // normally reset both score projections already; this is the
                // polled fallback when that callback marker is unavailable.
                // Session game / series tallies stay (they're cumulative).
                if (!scoreResetByCallback)
                {
                    currentSeriesGamesWon = 0;
                    currentSeriesGamesLost = 0;
                    // Bug 200: ...unless the queue lock staged a RESUMED
                    // series' tally for THIS room. Must run after zeroing.
                    TryConsumePendingResumedScore(photonRoomId);
                }
                ovtSoloWins = 0; ovtDuoWins = 0;   // review [4]: 1v2 banner tally
                // §7.1 (Codex mod-r1 F3 sweep): normally unreachable on the
                // broadcast seat (a spectator session quiesces this poll
                // before any join), but a ghost join landing after a
                // cancelled spectate can tick once here before the fence
                // restart completes — masked so that residual cannot leak
                // the credential.
                Plugin.Log.LogInfo(BroadcastMode.IsBroadcastIdentity
                    ? $"[POLL] Joined room: {BroadcastMode.SafeRoomDesc()} (region: (masked))"
                    : $"[POLL] Joined room: {photonRoomId} (region: {photonRegion})");
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
                // (The esc-menu leave guard arms from the Photon OnJoinedRoom
                // callback and the recurring tick below — no join-edge call
                // is needed here.)
            }

            if (inRoom && isTracking && oneVOneMatchAtStart)
                TryRefreshSharedGameToken();

            // Esc-menu leave confirm: the RECURRING keep-armed tick (Aug 12
            // review r2 find 3 — the join-edge callers alone cannot retry a
            // scan that failed, nor re-arm after the esc menu is rebuilt
            // mid-room). Cheap: armed-with-a-live-button returns immediately,
            // and a real rescan is throttled inside Arm(). Spectator seats
            // never reach here (Poll quiesces first).
            if (inRoom)
            {
                try
                {
                    if (CompetitiveRoomDetect.IsCompetitiveRoom())
                        EscMenuLeaveGuard.Arm();
                }
                catch { }
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
                        CompetitiveUI.ShowNotification("Left your game to join the queued match - no leave will be recorded.", new Color(0.4f, 0.8f, 1f));
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
                        CompetitiveUI.ShowNotification("Match canceled (disconnect)", new Color(1f, 0.7f, 0.3f));
                    }
                }

                Plugin.Log.LogInfo("[POLL] Left room");
                // Bug 199 adjacent: retract this fighter's spectate attestation
                // so the room stops being advertised the moment it dies, rather
                // than lingering for the 150s attest-freshness window and
                // handing clickers a "Game does not exist" join failure.
                // Spectators are excluded — they were never in the roster, so
                // the endpoint would just 403 them.
                if (!RoomActors.LocalIsSpectator)
                {
                    try { ApiClient.SpectateClose(photonRoomId); } catch { }
                }
                // A series id is only meaningful for the pairing it was preflighted
                // for. Carrying it across rooms would let the ranked-override at
                // report time force-rank a later casual game vs an unrelated
                // (possibly vanilla) opponent.
                ApiClient.ActiveRankedSeriesId = null;
                // Bug 231: the tournament banner context binds to the same
                // pairing/room as the series id — it dies here with it (#353).
                ClearTournamentContext();
                // Same rule for the 1v2 sitting: leaving the ovt_ room ends it.
                // Only the reporter's client clears these at series completion;
                // the other two would otherwise carry a stale series id + slot
                // to the menu, where the tab reads them as a pending lock.
                if ((photonRoomId ?? "").StartsWith("ovt_"))
                {
                    ApiClient.ActiveOvt1v2SeriesId = null;
                    try { Plugin.ClearPendingOvtSlot(); } catch { }
                }
                if ((photonRoomId ?? "").StartsWith("ffa_"))
                {
                    // Any member leaving ends the FFA lobby (fixed roster —
                    // the group can never re-reach N; Codex design find 4).
                    // FfaLeaveQueue closes/dissolves it server-side and clears
                    // ActiveFfaLobbyId + the pending slot. Idempotent when
                    // several members leave at sitting end.
                    // in_room_exit only when a game ACTUALLY STARTED here
                    // (round-10 find 4): occupancy of a never-filled room is
                    // not assembly, and tagging it would refuse the
                    // dissolution that frees the other seats.
                    try { ApiClient.FfaLeaveQueue(FfaMode.GameStartedInRoom ? "in_room_exit" : ""); } catch { }
                    try { Plugin.ClearPendingFfaSlot(); } catch { }
                    try { FfaMode.OnRoomLeft(); } catch { }
                }
                // Backup teardown for the esc-menu guard (the Photon
                // OnLeftRoom callback is primary). Attempts the restore —
                // Disarm catches its own failure; no-op when never armed.
                try { EscMenuLeaveGuard.Disarm(); } catch { }
                // Consume LeavingForRanked on EVERY observed room exit (lobby
                // impl round 6): the flag's meaning is "the NEXT room exit is
                // our deliberate leave-for-ranked". The tracking-gated scoring
                // branch above consumes it when a match was live; a pre/post-
                // game exit skipped that branch and left the flag set — where
                // it silently suppressed the NEXT genuine DC score and the
                // roomless-recovery watchdog. Single-shot by construction now.
                LeavingForRanked = false;
                // Spectate attest edge state dies with the room (find 14's
                // other half — a stale true battle state from THIS room must
                // not suppress the next room's first edge).
                lastSpectateAttestAt = -999f;
                lastSpectateValidateAt = -999f;
                lastSpectateBattleState = false;
                spectateAttestEdgePending = false;
                lastSpectateWasMaster = false;
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
                    || photonRoomId.StartsWith("ovt_") || photonRoomId.StartsWith("ffa_")))
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
                bool isFfaRoom = FfaMode.EngineActive();
                // FFA: up to 10 clients have to load in — the longest window.
                double bailAfter = isTournamentRoom ? 360 : (isFfaRoom ? 120 : (isOvtRoom ? 90 : 60));
                double warnAfter = isTournamentRoom ? 90 : (isFfaRoom ? 45 : (isOvtRoom ? 35 : 25));
                int fullAt = isFfaRoom ? Diag2v2.PlayersNeeded() : (isOvtRoom ? 3 : 2);
                int pc = 0;
                try { pc = RoomActors.ActiveFighterCount(); } catch { }   // census: fighters fill a room, spectators don't
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
                            : isFfaRoom
                            ? $"Waiting for all {fullAt} players to connect — hang tight..."
                            : "Opponent hasn't connected yet — hang tight...", new Color(1f, 0.8f, 0.3f), 6f);
                    }
                    if (waited >= bailAfter)
                    {
                        rankedRoomStallHandled = true;
                        Plugin.Log.LogWarning($"[QUEUE-STALL] Room {photonRoomId} never filled ({pc}/{fullAt}) after {(int)waited}s — returning to menu (no match started, no penalty)");
                        CompetitiveUI.ShowNotification(isTournamentRoom
                            ? "Your opponent never joined. Returning to menu - you stay ready, and the server forfeits the match to you if they don't show."
                            : isOvtRoom
                            ? "1v2 lobby never filled — returning to menu. Requeue when ready."
                            : isFfaRoom
                            ? "FFA lobby never filled — returning to menu. Requeue when ready."
                            : "Opponent failed to join — returning to menu. Requeue when ready.", new Color(1f, 0.5f, 0.4f), 10f);
                        // Leaving the ovt queue dissolves the never-filled lock
                        // server-side (cancels the series, resets the other two
                        // rows to searching) and clears the local lock state —
                        // otherwise the husk re-feeds this dead room forever.
                        // Cause deliberately NOT in_room_exit (round-9): the
                        // room never assembled — dissolution is the correct
                        // outcome, and the in-room fence must not veto it.
                        if (isOvtRoom) { try { ApiClient.OvtLeaveQueue("assembly_bail"); } catch { } }
                        if (isFfaRoom) { try { ApiClient.FfaLeaveQueue("assembly_bail"); } catch { } }
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
                    || rNameEager.StartsWith("ovt_") || FfaMode.EngineActive();
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
            //
            // Bug #91 item 2: this whole block is 1v1-shaped — in a multi-player
            // mode room (team_/cr_ff, ovt_, ffa_) it latched onto ONE arbitrary
            // peer, logged a contradictory "Match ranked: False" against the
            // forced-true room state, and its matchIsRanked write raced the
            // room-join forcing. Those rooms are definitionally mode-ranked at
            // join; skip the 1v1 check entirely there.
            bool rankCheckIsMultiMode = false;
            try
            {
                string rnRc = PhotonNetwork.CurrentRoom?.Name ?? "";
                var rpRc = PhotonNetwork.CurrentRoom?.CustomProperties;
                rankCheckIsMultiMode = rnRc.StartsWith("team_") || rnRc.StartsWith("ovt_")
                    || FfaMode.EngineActive() || (rpRc != null && rpRc.ContainsKey("cr_ff"));
            }
            catch { }
            if (inRoom && !rankCheckIsMultiMode && opponentSteamIdResolved
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
                    // Codex Grow-review find 1: this response can outlive the
                    // room it was asked in. Unbound, a stale response landing
                    // after a room change writes opponentIsRanked/matchIsRanked
                    // into the NEW room's context — and anything replicating
                    // that state (the Grow activation prop) would poison the
                    // new room. Bind response -> request and discard on any
                    // mismatch; the new room's own check cycle is independent.
                    string roomAtRequest = null;
                    try { roomAtRequest = PhotonNetwork.CurrentRoom?.Name; } catch { }
                    string oppAtRequest = opponentSteamId;
                    ApiClient.CheckOpponentRanked(opponentSteamId, (isRanked) =>
                    {
                        try
                        {
                            string roomNow = null;
                            try { roomNow = PhotonNetwork.CurrentRoom?.Name; } catch { }
                            if (!string.Equals(roomNow, roomAtRequest, StringComparison.Ordinal)
                                || !string.Equals(opponentSteamId, oppAtRequest, StringComparison.Ordinal))
                            {
                                Plugin.Log.LogInfo("[POLL] discarded stale opponent-ranked response (room/opponent changed since request)");
                                return;
                            }
                        }
                        catch { }
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
                    bool multiPlayerMode = rnDc.StartsWith("team_") || rnDc.StartsWith("ovt_")
                                           || FfaMode.EngineActive();
                    if (multiPlayerMode) { wasInRoom = inRoom; return; }

                    // Census: the OPPONENT is a fighter; a spectator must not
                    // set opponentWasPresent (that latch feeds the DC-win path)
                    // or keep playerCount above the ReportDisconnect gate.
                    int playerCount = RoomActors.ActiveFighterCount();
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
                        // The 1v1 DC-win report is finalised from the
                        // room-LEAVE handler below, where the players are
                        // already gone — this is the last frame that still
                        // holds the live build. Snapshot it now; OnGameOver's
                        // own capture no-ops out of the room and leaves this
                        // one standing.
                        CaptureEndStats("1v1 opponent DC");
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
                            // Critical: this is a one-shot ACTIONABLE cue with
                            // no retry (opponentDCReported latches), so it must
                            // not be dropped by a live critical window (Aug 12
                            // review r3) — the player would sit in a hung
                            // sitting with no instruction.
                            CompetitiveUI.ShowNotificationCritical(_dcMsg, new Color(1f, 0.65f, 0.2f), 10f);
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
                        else if (!matchIsRanked && opponentSteamIdResolved
                                 && !opponentSteamId.StartsWith("photon_"))
                        {
                            // Aug 6 item 1: casual rage-quit tracking. ANY
                            // midgame leave counts, including at 4-0 (Sid's
                            // explicit rule) — no meaningful-play or
                            // match-point gate like the ranked branch.
                            string _dcRoom = PhotonNetwork.CurrentRoom?.Name ?? "";
                            // Item 12: name the leaver. A vanilla quickplay
                            // opponent whose FIRST contact with any mod user is
                            // a rage-quit has no players row yet, so the server
                            // creates one from this report — with no name it is
                            // stored under the raw account id forever.
                            //
                            // opponentDisplayName is the name TryResolveOpponent
                            // already resolved and rich-text stripped at its one
                            // assignment site — no second resolution path here.
                            // Two guards on it: the schema caps display_name at
                            // 64, and "Opponent" is that resolver's own
                            // placeholder for a null NickName — shipping it would
                            // file every unnamed leaver under one fake shared
                            // name, which reads worse on a leaderboard than the
                            // honest raw account id.
                            string _dcLeaverName = (opponentDisplayName ?? "").Trim();
                            if (_dcLeaverName == "Opponent") _dcLeaverName = "";
                            if (_dcLeaverName.Length > 60) _dcLeaverName = _dcLeaverName.Substring(0, 60);
                            // Aug 13: name the GAME, not just the room. One
                            // Photon room hosts a whole sitting (production has
                            // rooms with 7 recorded matches), so "a match exists
                            // in this room" cannot answer "was the game they
                            // abandoned recorded?" — which is why the metric
                            // over-counts a between-games leave as a rage quit.
                            // This is the exact prefix the match report for THIS
                            // game will carry, from the same builder, so the
                            // survivor's two submissions agree by construction
                            // (both are ours, and the fallback branch keys on
                            // matchStartTime, which is stable mid-game — a
                            // vanilla opponent never negotiates a token, and a
                            // vanilla opponent is the entire population this
                            // stat measures).
                            //
                            // Omitted when the room name is unknown rather than
                            // sent half-formed: a prefix missing its room half
                            // matches no match row at all, and the server reads
                            // "no match" as "abandoned" — the very inflation
                            // this closes. No value at all falls back to the
                            // server's own ordering heuristic instead, which is
                            // imprecise rather than wrong in one direction.
                            string _dcGameId = string.IsNullOrEmpty(photonRoomId)
                                ? null : BuildGameReportIdPrefix();
                            Plugin.Log.LogInfo($"[DC] Casual midgame leave by {opponentDisplayName} at {localR}-{oppR} — reporting rage-quit (game={_dcGameId ?? "unknown"})");
                            ApiClient.ReportCasualDc(localSteamId, opponentSteamId, _dcRoom,
                                                     string.IsNullOrEmpty(_dcLeaverName) ? null : _dcLeaverName,
                                                     _dcGameId);
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
                    bool ffaRoom = roomName.StartsWith("ffa_");
                    if (ffaRoom)
                    {
                        // Capture the leaver's tallies for the FFA report
                        // (left_early) before Photon destroys their objects.
                        try
                        {
                            string luSid = null;
                            if (p.CustomProperties != null && p.CustomProperties.ContainsKey("u_id"))
                                luSid = p.CustomProperties["u_id"]?.ToString();
                            int luTeam = -1;
                            if (p.CustomProperties != null && p.CustomProperties.ContainsKey("t_id"))
                                int.TryParse(p.CustomProperties["t_id"]?.ToString(), out luTeam);
                            if (!string.IsNullOrEmpty(luSid) && luTeam >= 0)
                                FfaMode.RecordLeaver(luSid, name, luTeam);
                        }
                        catch { }
                        int remaining = RoomActors.ActiveFighterCount();   // census: fighters remaining
                        text = remaining >= 3
                            ? $"{whoTag} left the FFA — the game continues"
                            : $"{whoTag} disconnected or quit mid-game";
                        red = remaining < 3;
                    }
                    else
                    {
                        text = $"{whoTag} disconnected or quit mid-game";
                        red = true;
                    }
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
                Photon.Realtime.Player[] players = RoomActors.ActiveFighters();   // census: opponents are fighters
                if (players == null) return;

                foreach (var player in players)
                {
                    if (player == null || player.IsLocal) continue;

                    // NOTE: "Opponent" here is a PLACEHOLDER, not a name. The
                    // casual-DC reporter (item 12) filters that exact literal
                    // out before sending leaver_display_name, so it never
                    // becomes a real players row name — change the two
                    // together or that filter goes silently dead.
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
                    // Steam is not always ready this early: GetPersonaName can
                    // return empty (or, once, the id itself) before the Steam
                    // callbacks have run. Registering with that is how ~19
                    // players ended up displayed as raw 17-digit ids, and since
                    // most of them never played again nothing ever healed it.
                    // Keep the name empty rather than store a placeholder — the
                    // poller calls this again, so a real name lands shortly.
                    string persona = StripRichText(SteamFriends.GetPersonaName() ?? "");
                    if (!IsPlaceholderName(persona, localSteamId)) localDisplayName = persona;
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
        /// <summary>True when a name is missing or is just the Steam ID —
        /// i.e. nothing worth sending to the server as a display name. Mirrors
        /// _clean_display_name on the API side, including the 7656119 SteamID64
        /// prefix check so a player legitimately named with 17 digits is kept.
        /// </summary>
        internal static bool IsPlaceholderName(string name, string steamId)
        {
            string nm = (name ?? "").Trim();
            if (nm.Length == 0) return true;
            if (nm == (steamId ?? "").Trim()) return true;
            if (nm.Length == 17 && nm.StartsWith("7656119"))
            {
                bool allDigits = true;
                foreach (char c in nm) if (c < '0' || c > '9') { allDigits = false; break; }
                if (allDigits) return true;
            }
            return false;
        }

        private static void MaybeSyncRankedStateOnce()
        {
            if (_rankedSyncSent) return;
            if (string.IsNullOrEmpty(localSteamId) || localSteamId == "unknown") return;
            // Wait for a real display name before the FIRST server contact.
            // This call auto-registers the player, so firing it nameless is
            // precisely what created the raw-Steam-ID rows. IdentifyLocalPlayer
            // runs from the poller, so this retries on its own; the 30s bound
            // stops a player whose Steam name genuinely never resolves from
            // never syncing their ranked preference at all.
            if (IsPlaceholderName(localDisplayName, localSteamId)
                && Time.realtimeSinceStartup < 30f) return;
            try
            {
                bool wanted = Plugin.RankedEnabled != null && Plugin.RankedEnabled.Value;
                ApiClient.ToggleRanked(localSteamId, wanted, displayName: localDisplayName);
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
                    // locks once 2 points are scored in game 1.
                    // CADENCE, precisely (the old comment here said "only while we're in the
                    // first match of a series", which is wrong): curP1Rounds/curP2Rounds are
                    // rounds won in the CURRENT game, and GM_ArmsRace.ResetMatch zeroes them on
                    // every rematch — so this re-arms at the start of EVERY game and fires only
                    // during that game's ROUND 1, then stops for rounds 2-5. That is what caps
                    // the stored point sum at 2 (1-1) and makes the bet lock work.
                    // Bug 199 depends on this too: it is also the last last_activity_at stamp a
                    // game produces, so the liveness window must cover a whole game, not a round.
                    if (matchIsRanked && curP1Rounds == 0 && curP2Rounds == 0
                        && !string.IsNullOrEmpty(ApiClient.ActiveRankedSeriesId)
                        && !string.IsNullOrEmpty(LocalSteamId))
                    {
                        ApiClient.PostLivePoints(ApiClient.ActiveRankedSeriesId, LocalSteamId, curP1Points, curP2Points);
                    }
                    // Aug 9 (Sid): 2v2 closes on the SAME rule — 2 points in
                    // game 1 — so it needs the same channel. GM_ArmsRace's
                    // p1/p2 point fields ARE the two teams in a cr_ff room,
                    // and team_series' slot order is the same 0/1 the game
                    // uses, so the values map straight across. Game 1 only
                    // (rounds still 0-0), same traffic discipline as 1v1.
                    if (curP1Rounds == 0 && curP2Rounds == 0
                        && !string.IsNullOrEmpty(ApiClient.ActiveTeamSeriesId)
                        && !string.IsNullOrEmpty(LocalSteamId))
                    {
                        ApiClient.PostTeamLivePoints(ApiClient.ActiveTeamSeriesId, LocalSteamId,
                                                     curP1Points, curP2Points);
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
                var players = RoomActors.ActiveFighters();   // census: token capability is a two-FIGHTER consensus
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

        /// <summary>The STABLE half of this game's report id: "{room}_{token}",
        /// i.e. BuildReportRoomId with its "_r{score}" suffix removed.
        ///
        /// It exists because the score suffix is NOT stable within one game: a
        /// leave at 4-0 advances the awarded side to the terminal score before
        /// the report is filed (#179), so a value captured at leave time and the
        /// value the match row ends up carrying differ by a round. Anything that
        /// needs to say "this same game" across those two moments must compare
        /// on this prefix — see the casual-DC report, whose whole purpose is
        /// exactly that comparison.
        ///
        /// Extracted rather than duplicated: BuildReportRoomId now composes from
        /// it, so the two strings cannot drift apart in a later edit.</summary>
        private static string BuildGameReportIdPrefix()
        {
            TryRefreshSharedGameToken();
            string token = !string.IsNullOrEmpty(sharedGameToken)
                ? sharedGameToken
                : matchStartTime.ToString(
                    "HHmmss",
                    System.Globalization.CultureInfo.InvariantCulture);
            return $"{photonRoomId}_{token}";
        }

        private static string BuildReportRoomId(
            int reportP1Rounds = -1, int reportP2Rounds = -1)
        {
            int reportRoundTotal =
                reportP1Rounds >= 0 && reportP2Rounds >= 0
                    ? reportP1Rounds + reportP2Rounds
                    : p1Rounds + p2Rounds;
            return $"{BuildGameReportIdPrefix()}_r{reportRoundTotal}";
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
            // Spectator: never tracks a match (defense in depth — the GM
            // lifecycle that fires this is suppressed on a spectator).
            if (RoomActors.LocalIsSpectator) return;
            try { NetworkReplicaDiagnostics.OnGameStarted(); } catch { }
            // Freeze the fighter roster at match start (design §3.2, Codex r1
            // find 1): from here, a later actor is a spectator (role prop) or
            // unauthorized — never a new fighter. Competitive rooms only; a
            // casual quickplay room must keep vanilla late-join behaviour.
            try
            {
                if (CompetitiveRoomDetect.IsCompetitiveRoom())
                {
                    var ids = new List<string>();
                    foreach (var f in RoomActors.ActiveFighters())
                    {
                        var s = RoomActors.SteamIdOf(f);
                        if (!string.IsNullOrEmpty(s)) ids.Add(s);
                    }
                    if (ids.Count >= 2) RoomActors.FreezeFighterRoster(ids);
                }
            }
            catch { }
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
                    && !roomName.StartsWith("ffa_", StringComparison.Ordinal)
                    && !(roomProps?.ContainsKey("cr_ff") ?? false)
                    // Census: exactly two FIGHTERS — a spectator's Photon seat
                    // must not flip the 1v1 token path off (or on).
                    && RoomActors.ActiveFighterCount() == 2;
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
                                || rname.StartsWith("ovt_")
                                || FfaMode.EngineActive();
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
            ResetPerMatchCombatCounters();

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
                var players = RoomActors.ActiveFighters();   // census: cr_cards is a fighter property
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
            if (RoomActors.LocalIsSpectator) return;   // spectator: no result paths
            if (!isTracking || gameOverReported) return;
            gameOverReported = true;
            sessionMatchCount++;
            try { NetworkReplicaDiagnostics.OnGameEnded(); } catch { }

            // FIRST statement after the one-shot latch: snapshot every seat's
            // BUILD while the live objects still hold it (#171 — finalise from
            // the current frame, never wait on telemetry). Cheap and
            // synchronous; nothing below waits on it. Taking it here rather
            // than inside the report paths is load-bearing: every one of them
            // runs after this point in OnGameOver, and the 2v2 routing in
            // particular can be reached once the rematch teardown has already
            // run Player.FullReset.
            CaptureEndStats("1v1/2v2/1v2 game over");

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
            // Bug #91 item 2 (cosmetic): in a 1v2 room the old line named only
            // whichever single opponent the 1v1 poll latched onto ("YOU WON vs
            // Spirit!" — Nix invisible). Name every non-local participant there.
            string oppLabel = opponentDisplayName;
            try
            {
                if ((PhotonNetwork.CurrentRoom?.Name ?? "").StartsWith("ovt_")
                    && RoomActors.ActiveFighterCount() >= 3)   // census: label built from fighters
                {
                    var others = new List<string>();
                    foreach (var ppN in RoomActors.ActiveFighters())
                        if (ppN != null && !ppN.IsLocal)
                            others.Add(StripRichText(ppN.NickName ?? "?"));
                    if (others.Count > 0) oppLabel = string.Join(" + ", others);
                }
            }
            catch { }
            Plugin.Log.LogInfo(localWon
                ? $"[POLL] YOU WON vs {oppLabel}!"
                : $"[POLL] You lost to {oppLabel}");
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
            // Bug #91 comment 2: 1v2 recorded NO opponents ("just Casual W2-0").
            // The per-opponent builder was 2v2-only, so a 1v2 game fell back to
            // the single 1v1 opponentDisplayName and was then skipped entirely.
            // The body below already does the right thing for 1v2 unmodified:
            // t_id is published identically by the ovt pre-join (solo=0, both
            // duo=1), so the solo sees two plain opponent keys and a duo member
            // sees the solo as an opponent plus "w/ Partner". Only the gate
            // needed widening. >= 2 (not 3) so a DC-decided game still names
            // whoever is left.
            bool buildMultiKeys =
                   (sessionRoomIsCrFf && RoomActors.ActiveFighterCount() >= 4)
                || (sessionRoomIsOvt && RoomActors.ActiveFighterCount() >= 2);
            if (buildMultiKeys)
            {
                foreach (var pp in RoomActors.ActiveFighters())   // census: session keys name fighters only
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
                    string key = isTeammate ? "w/ " + nm : nm;
                    // Review find 3: the dict is keyed by DISPLAY NAME, so two
                    // opponents both called e.g. "Player" would collapse into a
                    // single row that this one game increments TWICE ("2W-0L"
                    // after one game). Disambiguate the duplicate instead.
                    if (oppKeys.Contains(key))
                    {
                        int dup = 2;
                        while (oppKeys.Contains($"{key} ({dup})")) dup++;
                        key = $"{key} ({dup})";
                    }
                    oppKeys.Add(key);
                }
            }
            if (oppKeys.Count == 0)
                oppKeys.Add(opponentDisplayName ?? "Unknown");

            // Per-opponent session record. Six slots: [rW, rL, cW, cL, vW, vL]
            // — 1v2 games land in their OWN pair (4/5) so they neither vanish
            // (the old `if (!sessionRoomIsOvt)` skip) nor get mislabelled as
            // casual. Records restored from PlayerPrefs may still be 4 long;
            // grow them in place rather than dropping the history.
            foreach (var oppKey in oppKeys)
            {
                int[] rec;
                if (!sessionWLByOpponent.TryGetValue(oppKey, out rec) || rec == null || rec.Length < 6)
                {
                    var grown = new int[6];
                    if (rec != null) Array.Copy(rec, grown, Math.Min(rec.Length, 6));
                    sessionWLByOpponent[oppKey] = rec = grown;
                }
                int bucket = sessionRoomIsOvt ? 4 : (matchIsRanked ? 0 : 2);
                if (localWon) rec[bucket]++; else rec[bucket + 1]++;
            }

            if (sessionRoomIsOvt)
            {
                // 1v2 is its own unranked mode: never the 1v1 ranked ladder
                // counters, never the BO3 HUD, and (bug #91) never "Casual".
                if (localWon) sessionOvtWins++; else sessionOvtLosses++;
            }
            else if (matchIsRanked)
            {
                if (localWon) sessionRankedWins++; else sessionRankedLosses++;
                // Room-scoped tally for the SPECTATOR snapshot (Aug 10 design
                // review find 10): a self-contained BO3 count on local
                // outcomes only. currentSeriesGames* below is entangled with
                // the async report callback's resets and must not be reused.
                // The opening roomGames* phase can be server-seeded on resume;
                // all later advancement happens here (both fighters run this
                // path), and resets happen only on actual room join. Display-only:
                // never reported, never signed, never near ratings or gold.
                // STRICT 1v1 writers only (r2 find 10: matchIsRanked is also
                // true for 2v2 cr_ff games flowing through this path — the
                // snapshot sender would hide them behind its own 1v1 gate,
                // but the counters themselves must not mutate either).
                if (!Diag2v2.IsActive())
                {
                    if (localWon) roomGamesWonLocal++; else roomGamesLostLocal++;
                    if (roomGamesWonLocal >= 2 || roomGamesLostLocal >= 2)
                    {
                        if (roomGamesWonLocal >= 2) roomSeriesWinsLocal++; else roomSeriesLossesLocal++;
                        roomGamesWonLocal = 0;
                        roomGamesLostLocal = 0;
                    }
                }
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
                    var players = RoomActors.ActiveFighters();   // census: reporter dedup keys on the FIGHTER's mod
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
                // ANY ffa_ room bans every other report path outright. The FFA
                // engine reports through OnFfaGameOver (its own pipeline) —
                // this polled OnGameOver should never even fire in FFA (the
                // vanilla p1/p2 fields stay 0 there), so reaching this line in
                // an ffa_ room means some 1v1-shaped branch misfired; routing
                // it anywhere would mint phantom 1v1/2v2 rows (#65/#106 class).
                if (FfaMode.EngineActive())
                {
                    Plugin.Log.LogWarning("[FFA-REPORT-ROUTE] polled OnGameOver fired in an ffa_ room — all non-FFA report paths banned");
                    EvaluateAchievements(localWon);
                    isTracking = false;
                    matchIsRanked = false;
                    return;
                }
                // Review HIGH: ANY ovt_ room bans the 1v1 fallback — the guard must
                // NOT be gated on PlayerList==3. An ovt_ room that (e.g. after a DC)
                // has 2 players at report time would otherwise fall through to the
                // 1v1 ReportMatch path and mint a phantom 1v1 ranked match/series
                // (#65/#106 class). Only ATTEMPT the 3-player report when full.
                if (rn1.StartsWith("ovt_") && shouldReport)
                {
                    bool sent = false;
                    // Census: exactly three FIGHTERS — a spectator must not
                    // suppress the whole 1v2 report (recon's exact-equality
                    // class: one extra actor = silent no-rating game).
                    if (RoomActors.ActiveFighterCount() == 3)
                        sent = TryReportOvtMatch(reportRoomId, duration);
                    if (!sent)
                        Plugin.Log.LogWarning($"[1v2-REPORT-ROUTE] ovt_ room, report not routed (fighters={RoomActors.ActiveFighterCount()}) — 1v1 fallback banned");
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
                    // Census: exactly four FIGHTERS (same exact-equality class
                    // as the 1v2 gate above).
                    && RoomActors.ActiveFighterCount() == 4)
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
                    // An earlier revision of this comment claimed the deferred report
                    // could still "resolve all four players" because Photon state stays
                    // alive through the between-games window. It cannot: the response may
                    // land after game 2 has begun, and a player who left in between drops
                    // the census below four and kills the report. Nothing is resolved
                    // late any more — see TeamReportPayload. Non-reporters early-return
                    // inside TryRequestContinuationSeries as usual.
                    if (shouldReport && roomIsCrFf && !hasSeries && playerListLen == 4)
                    {
                        Plugin.Log.LogWarning("[2v2-REPORT-ROUTE] no team series at match end — requesting continuation and deferring report");
                        // Resolve the ENTIRE report HERE and defer only the
                        // submit. Everything it reads — the four-fighter census,
                        // the roster, both teams' cards, all four telemetry
                        // blobs, the builds, the scores and the ranked flag —
                        // is either cleared by the next game's
                        // ResetPerMatchCombatCounters, overwritten by game 2's
                        // Photon props, or (matchIsRanked) zeroed by the
                        // teardown at the bottom of this very block before the
                        // callback can possibly run. TeamReportPayload lists
                        // them; nothing but the series id is read late.
                        var deferredPayload = BuildTeamReportPayload(reportRoomId, duration);
                        if (deferredPayload == null)
                            Plugin.Log.LogWarning("[2v2-REPORT-ROUTE] could not resolve this game at match end — still requesting the continuation (later games need it), but this game cannot be submitted");
                        TryRequestContinuationSeries(ok =>
                        {
                            if (!ok || string.IsNullOrEmpty(ApiClient.ActiveTeamSeriesId))
                            {
                                Plugin.Log.LogWarning("[2v2-REPORT-ROUTE] continuation retry failed — game not recorded");
                                return;
                            }
                            // Only the elected reporter reaches this callback at
                            // all (TryRequestContinuationSeries returns before
                            // firing it otherwise), but the payload carries the
                            // election result so the two can never disagree.
                            if (deferredPayload == null || !deferredPayload.LocalIsReporter) return;
                            SubmitTeamReport(deferredPayload);
                            Plugin.Log.LogInfo("[2v2-REPORT-ROUTE] deferred report submitted after continuation");
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
                // Build stats for this report's two seats:
                //   EndStatsFor(p1SteamId) -> player1.end_stats
                //   EndStatsFor(p2SteamId) -> player2.end_stats
                // Both may be null ("not recorded"); omit the JSON field then,
                // never send "" or dashes (#257). ADVISORY — the 7-field HMAC
                // canonical does not change.
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
                    localFpsTimeline: string.Join(",", localFpsTimeline.Items),
                    oppFpsTimeline: string.Join(",", oppFpsTimeline.Items),
                    localFreezeCount: localFreezeCount,
                    localFreezeFocusedCount: localFreezeFocusedCount,
                    localFreezeTotalSec: localFreezeTotalSec,
                    localPingAvg: pingSamples.Count > 0 ? (int)Math.Round(pingSamples.Average()) : 0,
                    localPingMax: pingSamples.Count > 0 ? pingSamples.Max() : 0,
                    // July 22 item 3: latency timelines for the history hover chart.
                    localPingTimeline: string.Join(",", pingSamples),
                    oppPingTimeline: string.Join(",", oppPingTimeline.Items),
                    oppPingAvg: oppPingTimeline.Count > 0 ? (int)Math.Round(oppPingTimeline.Items.Average()) : 0,
                    localRecvGapCount: localRecvGapCount,
                    localRecvGapMaxMs: localRecvGapMaxMs,
                    oppHbGapCount: oppHbGapCount,
                    oppFreezeCount: oppFreezeCount,
                    oppFreezeFocusedCount: oppFreezeFocusedCount,
                    oppRecvGapCount: oppRecvGapCount,
                    // July 22 item 1: cumulative Hit%/Block% pair timelines +
                    // per-point timestamps for the new hover graphs.
                    localHitTimeline: string.Join(",", localHitTimeline.Items),
                    oppHitTimeline: string.Join(",", oppHitTimeline.Items),
                    localBlockTimeline: localBlockTimeline.Count > 0
                        ? "v2|" + string.Join(",", localBlockTimeline.Items) : "",
                    oppBlockTimeline: oppBlockTimeline.Count > 0
                        ? "v2|" + string.Join(",", oppBlockTimeline.Items) : "",
                    pointTimes: string.Join(",", pointTimes),
                    // Aug 6 items 1+4: expanded combat telemetry.
                    localDamageDealt: LocalDamageDealtThisMatch,
                    // -1 = "this peer never sent expanded telemetry" (an
                    // older client). The server maps negatives to NULL so the
                    // averages divide by rows that actually carry the data.
                    oppDamageDealt: OppExpandedTelemetrySeen ? OppDamageDealt : -1f,
                    localMaxSingleHit: LocalMaxSingleHit,
                    oppMaxSingleHit: OppExpandedTelemetrySeen ? OppMaxSingleHit : -1f,
                    localMaxHealth: LocalMaxHealthSeen,
                    oppMaxHealth: OppExpandedTelemetrySeen ? OppMaxHealthSeen : -1f,
                    // Bounce-kill stat CUT (r4) — always report "not recorded".
                    localBestBounceKill: -1,
                    oppBestBounceKill: -1,
                    localDamageTimeline: LocalDamageTimelineCsv,
                    oppDamageTimeline: OppDamageTimelineCsv,
                    localDeaths: LocalDeaths,
                    localDeathsBoundary: LocalDeathsBoundary,
                    localDeathsOwnBullet: LocalDeathsOwnBullet,
                    oppDeaths: OppDeathsObserved,
                    oppDeathsBoundary: OppDeathsBoundaryObserved,
                    oppDeathsOwnBullet: OppDeathsOwnBulletObserved,
                    // Positional by SLOT, not viewer-relative. Either may be
                    // null ("not recorded"), which ApiClient omits entirely.
                    p1EndStats: EndStatsFor(p1SteamId),
                    p2EndStats: EndStatsFor(p2SteamId)
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
                // Census: gate AND iteration use the same fighter view — they
                // must convert together or disagree (recon structural hazard).
                var fighters = RoomActors.ActiveFighters();
                if (fighters.Length != 4) return;

                var sids = new string[4];
                var teams = new int[4];
                for (int i = 0; i < 4; i++)
                {
                    var pp = fighters[i];
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
                // Census: gate + iteration from one fighter view (see 2v2 twin).
                var fighters = RoomActors.ActiveFighters();
                if (fighters.Length != 3) return;
                var pm = PlayerManager.instance;
                if (pm == null || pm.players == null) return;
                var sids = new string[3]; var teams = new int[3];
                for (int i = 0; i < 3; i++)
                {
                    var pp = fighters[i]; if (pp == null) return;
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
            // Census: gate + roster from ONE fighter view (converted together
            // with the foreach below — recon structural hazard).
            var reportFighters = RoomActors.ActiveFighters();
            if (reportFighters.Length != 3) return false;
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return false;
            if (string.IsNullOrEmpty(ApiClient.ActiveOvt1v2SeriesId))
            {
                Plugin.Log.LogWarning("[1v2-REPORT] no active series id — cannot report");
                return false;
            }
            // Resolve each FIGHTER actor → Steam ID + in-game TeamID + cards + fps + damage series.
            var info = new Dictionary<string, (string name, int teamId, List<MatchTracker.CardPickData> cards, int fps, string dmgTl)>();
            foreach (var pp in reportFighters)
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
                // Aug 7 item 3: cumulative damage-dealt series on the 3s
                // cadence — own side from the local sampler, peers from their
                // cr_gstats heartbeat. 1v2 has no reporter-side damage table
                // (the local-damage tracker is dealer-side only, and the FFA
                // all-players tracker is FFA-gated), so a pre-Aug-6 peer simply
                // sends nothing and stays EMPTY = NULL server-side, not 0 (#257).
                string dmgTl = "";
                if (pp.IsLocal) { if (localCards != null && localCards.Count > 0) picks = new List<MatchTracker.CardPickData>(localCards); int myFps = LocalAvgFps; if (myFps > 0) fps = myFps; dmgTl = string.Join(",", localDamage3sTimeline.Items); }
                else if (TryGetPeerTelemetry(pp.ActorNumber, out _, out _, out _, out _, out string pDmg, out _)) dmgTl = pDmg ?? "";
                info[sid] = (name, teamId, picks, fps, dmgTl);
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

            // Build stats for the three seats:
            //   EndStatsFor(soloSid) -> solo.end_stats
            //   EndStatsFor(duoASid) -> duo_a.end_stats
            //   EndStatsFor(duoBSid) -> duo_b.end_stats
            // Any may be null ("not recorded") — omit the field then (#257).
            // ADVISORY — the 10-field 1v2 HMAC canonical does not change.
            ApiClient.ReportOvtMatch(
                ApiClient.ActiveOvt1v2SeriesId, reportRoomId, photonRegion, duration,
                soloSid, info[soloSid].name, info[soloSid].cards,
                duoASid, info[duoASid].name, info[duoASid].cards,
                duoBSid, info[duoBSid].name, info[duoBSid].cards,
                soloRounds, duoRounds, soloPoints, duoPoints,
                localSteamId, info[soloSid].fps, info[duoASid].fps, info[duoBSid].fps,
                info[soloSid].dmgTl, info[duoASid].dmgTl, info[duoBSid].dmgTl,
                soloEndStats: EndStatsFor(soloSid),
                duoAEndStats: EndStatsFor(duoASid),
                duoBEndStats: EndStatsFor(duoBSid));
            Plugin.Log.LogInfo($"[1v2-REPORT] submitted solo={soloSid} duo={duoASid},{duoBSid} {soloRounds}-{duoRounds}");
            return true;
        }

        // ── FFA reporting ────────────────────────────────────────────────

        /// <summary>Per-GAME combat/telemetry counter reset. Extracted from
        /// OnMatchStarted so the FFA game-start hook (which can't ride the
        /// vanilla match-start path — see OnFfaMatchStarted) resets exactly
        /// the same windows instead of a hand-copied subset that drifts.</summary>
        private static void ResetPerMatchCombatCounters()
        {
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
            localFps3sTimeline.Clear(); localDamage3sTimeline.Clear();
            pointTimes.Clear();
            LocalDamageTakenThisMatch = 0f;
            peerTele.Clear();
            // Aug 6 items 1+4: expanded combat telemetry resets.
            LocalDamageDealtThisMatch = 0f; LocalMaxSingleHit = 0f;
            LocalMaxHealthSeen = 0f; LocalBestBounceKill = 0;
            LocalDeaths = 0; LocalDeathsBoundary = 0; LocalDeathsOwnBullet = 0;
            OppDeathsObserved = 0; OppDeathsBoundaryObserved = 0; OppDeathsOwnBulletObserved = 0;
            localDamageTimeline.Clear(); oppDamageTimeline.Clear();
            OppDamageDealt = 0f; OppMaxSingleHit = 0f; OppMaxHealthSeen = 0f; OppBestBounceKill = 0;
            OppExpandedTelemetrySeen = false;
            // The end-of-game build stash belongs to exactly ONE game. This is
            // its only clear site, and BOTH game-start hooks (OnMatchStarted
            // and OnFfaMatchStarted) call this method — so a report can never
            // be handed a build from the previous game.
            //
            // It does NOT follow that a deferred report finds its own (an
            // earlier revision of this comment claimed it did): the
            // continuation-deferred 2v2 report fires from an async callback
            // that can land after game 2 has started, and it would then read
            // this cleared-and-refilled dictionary. That path resolves its
            // whole report before deferring instead — see TeamReportPayload.
            endStatsBySteam.Clear();
            endStatsLocal = null;
            CombatTelemetry.ClearMatchState();
        }

        /// <summary>FFA game START hook — called by FfaMode.OnGameStart for
        /// EVERY game including same-room rematches.
        ///
        /// Review find 1 (critical): the vanilla-driven match-start path can't
        /// serve FFA. OnMatchStarted is armed off the "MOVE PLAYERS END" log
        /// marker and refuses to re-arm while isTracking is true, and its
        /// score-based safety net reads the vanilla p1/p2 fields — which stay
        /// 0 forever in FFA. Without this hook, game 2 of an FFA sitting kept
        /// gameOverReported=true from game 1, so it was never reported at all
        /// and its telemetry window never reset.</summary>
        public static void OnFfaMatchStarted()
        {
            if (RoomActors.LocalIsSpectator) return;   // spectator: no tracking
            try { NetworkReplicaDiagnostics.OnGameStarted(); } catch { }
            // Roster freeze — same rule as OnMatchStarted (r1 find 1). Re-run
            // per game: FFA leavers shrink the roster between games.
            try
            {
                var ids = new List<string>();
                foreach (var f in RoomActors.ActiveFighters())
                {
                    var s = RoomActors.SteamIdOf(f);
                    if (!string.IsNullOrEmpty(s)) ids.Add(s);
                }
                if (ids.Count >= 2) RoomActors.FreezeFighterRoster(ids);
            }
            catch { }
            try
            {
                // Per-game latches (the ones OnFfaGameOver / the report path read).
                isTracking = true;
                gameOverReported = false;
                matchStartTime = DateTime.UtcNow;
                matchIsRanked = true;              // ffa_ rooms are mode-ranked
                oneVOneMatchAtStart = false;       // never the 1v1 token path
                macroEvidenceDispatched = false;
                opponentDCReported = false;
                inPickPhase = false;

                // Per-game telemetry/card windows.
                localCards.Clear();
                localOffers.Clear();
                broadcastCardNames.Clear();
                preMatchCards.Clear();
                preMatchPickCount = 0;
                pickCountThisMatch = 0;
                try
                {
                    var clearProps = new Hashtable();
                    clearProps[CARD_PROP_KEY] = "";
                    PhotonNetwork.LocalPlayer?.SetCustomProperties(clearProps);
                }
                catch { }

                ResetPerMatchCombatCounters();
                if (string.IsNullOrEmpty(localSteamId) || localSteamId == "unknown")
                    IdentifyLocalPlayer();
                // Sid2 in-game menu bleed: a rematch can start while someone
                // is still browsing the F5 page. Snapshot the overlay state
                // BEFORE closing (Codex review find 8 — Close() normalizes
                // the very state under investigation), then close.
                try { NativeUI.LogOverlayState($"ffa game {FfaMode.GameNumber} start (pre-close)"); } catch { }
                try { if (NativeUI.IsOpen) NativeUI.Close(); } catch { }
                Plugin.Log.LogInfo($"[FFA] === Game {FfaMode.GameNumber} started === (tracking armed)");
            }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA] OnFfaMatchStarted: {ex.Message}"); }
        }

        /// <summary>Bug #106: FFA session bookkeeping. Win = placed #1; every
        /// other roster member (leavers included) gets a per-opponent entry in
        /// slots 6/7 of the shared record. Placement list feeds the Session
        /// Info line ("placements 1,1,2").</summary>
        private static void RecordFfaSession(int myPlace, bool localWon, int myTeam)
        {
            if (localWon) sessionFfaWins++; else sessionFfaLosses++;
            if (myPlace > 0 && sessionFfaPlacements.Count < 200) sessionFfaPlacements.Add(myPlace);
            // Bug #123: the per-opponent record is PAIRWISE by placement, not a
            // copy of my own result. Previously one `localWon` boolean was
            // applied to every name in the room, so any game I didn't WIN
            // credited a loss against all of them — Sid placed 2nd once in a
            // 5-player sitting and the panel showed a loss vs all four
            // opponents instead of only vs the player who actually beat him.
            // The rule now matches the server's own semantics: it scores each
            // pair 1.0/0.0/0.5 by placement for Glicko, and pays XP off a
            // strictly-beaten count.
            var roster = new List<KeyValuePair<string, int>>();   // (deduped name, teamId)
            try
            {
                var names = new List<string>();
                // Duplicate display names get the same "(2)" disambiguation
                // as the 1v1 path (review find 16 — two opponents both named
                // "Player" would double-increment one record).
                string AddName(string raw)
                {
                    string nm = StripRichText(raw ?? "");
                    if (string.IsNullOrEmpty(nm)) return null;
                    if (names.Contains(nm))
                    {
                        int dup = 2;
                        while (names.Contains($"{nm} ({dup})")) dup++;
                        nm = $"{nm} ({dup})";
                    }
                    names.Add(nm);
                    return nm;
                }
                var pm = PlayerManager.instance;
                foreach (var pp in RoomActors.ActiveFighters())   // census: session records name fighters only
                {
                    if (pp == null || pp.IsLocal) continue;
                    // Resolve this actor's TeamID the same way the report path
                    // does. Without a team we cannot place them, and inventing
                    // a result is exactly the bug being fixed — skip instead.
                    int teamId = -1;
                    if (pm?.players != null)
                    {
                        foreach (var po in pm.players)
                        {
                            if (po == null || po.gameObject == null) continue;
                            var pv = po.GetComponent<PhotonView>();
                            if (pv?.Owner == null || pv.Owner.ActorNumber != pp.ActorNumber) continue;
                            teamId = po.TeamID; break;
                        }
                    }
                    if (teamId < 0)
                    {
                        Plugin.Log.LogWarning($"[SESSION] ffa: no team for actor {pp.ActorNumber} " +
                                              $"({pp.NickName}) — skipped");
                        continue;
                    }
                    string nm2 = AddName(pp.NickName);
                    if (nm2 != null) roster.Add(new KeyValuePair<string, int>(nm2, teamId));
                }
                foreach (var kvL in FfaMode.Leavers)
                {
                    // #227: a leaver only counts for the game they actually left
                    // during. The report path already filters on this; without it
                    // someone who quit in game 2 kept collecting a result for
                    // games 3..N they were never in — part of what Sid saw as
                    // "names I did not lose to".
                    if (kvL.Value.leftGameNumber != FfaMode.GameNumber) continue;
                    string nm3 = AddName(kvL.Value.displayName ?? "");
                    if (nm3 != null) roster.Add(new KeyValuePair<string, int>(nm3, kvL.Value.slot));
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[SESSION] ffa roster: {ex.Message}"); }

            if (myTeam >= 0)
            {
                foreach (var kv in roster)
                {
                    int cmp;
                    try { cmp = FfaMode.ComparePlacement(kv.Value, myTeam); }
                    catch { continue; }
                    if (cmp == 0) continue;   // exact tie: neither a win nor a loss
                    if (!sessionWLByOpponent.TryGetValue(kv.Key, out var rec) || rec == null || rec.Length < 8)
                    {
                        var grown = new int[8];
                        if (rec != null) Array.Copy(rec, grown, Math.Min(rec.Length, 8));
                        sessionWLByOpponent[kv.Key] = rec = grown;
                    }
                    if (cmp > 0) rec[6]++;    // they placed BELOW me -> a win for me
                    else rec[7]++;            // they placed ABOVE me -> a loss for me
                }
            }
            SaveSessionState();
        }

        /// <summary>Own-pick bookkeeping for the FFA pick phase. The silent
        /// apply path deliberately bypasses vanilla's "Picking Card:" log, so
        /// the standard intercept never fires — FfaMode calls this at
        /// ACCEPTED-RESULT time (ApplyManifestPick, Aug 11: recording at
        /// confirm time broadcast picks the reducer then rejected — bug 204's
        /// false "he has Defender"). Feeds localCards + the cr_cards
        /// broadcast; note the FFA REPORT does not read either (it uses
        /// FfaMode.PickHistoryFor) — these serve the non-FFA report shapes,
        /// achievements, and the cross-mode pick-history channel.</summary>
        public static void RecordFfaLocalPick(string cardName, int roundNumber)
        {
            try
            {
                string canonical = CardRarityLookup.GetCanonicalName(ToTitleCase(cardName));
                if (string.IsNullOrEmpty(canonical)) canonical = cardName;
                localCards.Add(new MatchTracker.CardPickData
                {
                    CardName = canonical,
                    CardRarity = CardRarityLookup.GetRarity(canonical),
                    PickOrder = localCards.Count + 1,
                    RoundNumber = Math.Max(1, roundNumber),
                });
                BroadcastCardPick(cardName);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[FFA] RecordFfaLocalPick: {ex.Message}"); }
        }

        /// <summary>FFA game over — called by FfaMode's round engine (the
        /// vanilla p1/p2 fields never move in FFA, so the polling game-over
        /// path can't fire). One-shot per game via gameOverReported.</summary>
        public static void OnFfaGameOver(int winnerTeam)
        {
            if (RoomActors.LocalIsSpectator) return;   // spectator: no result paths
            if (gameOverReported) return;
            gameOverReported = true;
            isTracking = false;    // the next game re-arms via OnFfaMatchStarted
            sessionMatchCount++;
            try { NetworkReplicaDiagnostics.OnGameEnded(); } catch { }

            // Same rule as OnGameOver: build snapshot first, in this frame.
            // FfaMode calls this synchronously from its point resolution, so
            // the players are still spawned and un-reset here; the next FFA
            // game's start hook clears the stash (#171).
            CaptureEndStats("FFA game over");

            BroadcastGstatsImmediate();
            try { PhotonNetwork.SendAllOutgoingCommands(); } catch { }

            // Local slot/team: in FFA TeamID == slot == PlayerID.
            int myTeam = -1;
            try
            {
                var pmL = PlayerManager.instance;
                if (pmL?.players != null)
                    foreach (var po in pmL.players)
                        if (po != null && po.gameObject != null && po.data?.view != null && po.data.view.IsMine)
                        { myTeam = po.TeamID; break; }
            }
            catch { }
            bool localWon = myTeam >= 0 && winnerTeam == myTeam;
            int myPlace = 1;
            try
            {
                // Competition ranking via the shared comparator (points, then
                // total half points, then kills — Sid's item 3 tie-breaks).
                // Leavers count too (Codex review find 7): their tallies stay
                // in the score dicts for the game they left, so a leaver who
                // outscored you still places above you — matching the
                // server's placement, which includes every roster member.
                var counted = new HashSet<int> { myTeam };
                var pmL2 = PlayerManager.instance;
                if (pmL2?.players != null)
                    foreach (var po in pmL2.players)
                    {
                        if (po == null || po.gameObject == null || po.TeamID == myTeam) continue;
                        if (!counted.Add(po.TeamID)) continue;
                        if (FfaMode.ComparePlacement(po.TeamID, myTeam) < 0) myPlace++;
                    }
                foreach (var kvL in FfaMode.Leavers)
                {
                    if (!counted.Add(kvL.Value.slot)) continue;
                    if (FfaMode.ComparePlacement(kvL.Value.slot, myTeam) < 0) myPlace++;
                }
            }
            catch { }
            Plugin.Log.LogInfo($"[POLL] === FFA Match Over === Winner: team {winnerTeam} " +
                               $"(you placed #{myPlace}{(localWon ? " - VICTORY" : "")})");
            // Session Info tally (bug #106): FFA never reaches the polled
            // OnGameOver path, so its session bookkeeping lives here.
            try { RecordFfaSession(myPlace, localWon, myTeam); } catch (Exception ex)
            { Plugin.Log.LogWarning($"[SESSION] ffa record failed: {ex.Message}"); }
            CompetitiveUI.ShowNotification(localWon
                ? "FFA VICTORY!"
                : $"FFA over - you placed #{myPlace}", localWon ? Color.green : new Color(0.7f, 0.85f, 1f), 6f);
            AccumulateSessionTime();
            SaveSessionState();

            int duration = (int)(DateTime.UtcNow - matchStartTime).TotalSeconds;
            if (duration <= 0 || duration > 86400)
                duration = (int)Math.Max(1f, Time.realtimeSinceStartup - FfaMode.MatchStartRealtime);
            // Per-game report room id: same shape the other modes use — the
            // per-game suffix is the server-side replay-dedup key.
            string reportRoomId = $"{photonRoomId}_{matchStartTime:HHmmss}_r{FfaMode.GameNumber}";
            try
            {
                if (!TryReportFfaMatch(reportRoomId, duration, winnerTeam))
                    Plugin.Log.LogWarning("[FFA-REPORT] report path did not run (see above)");
            }
            catch (Exception ex) { Plugin.Log.LogError($"[FFA-REPORT] {ex.Message}"); }
        }

        private static bool TryReportFfaMatch(string reportRoomId, int duration, int winnerTeam)
        {
            var pm = PlayerManager.instance;
            if (pm?.players == null) return false;
            string lobbyId = ApiClient.ActiveFfaLobbyId;
            if (string.IsNullOrEmpty(lobbyId))
            {
                Plugin.Log.LogWarning("[FFA-REPORT] no active lobby id — cannot report");
                return false;
            }

            var entries = new List<ApiClient.FfaReportPlayer>();
            var presentSteams = new List<string>();
            string winnerSteam = null;

            // Census: the FFA report roster is fighters only — a spectator
            // must never enter the present-player ledger (design §4.2).
            foreach (var pp in RoomActors.ActiveFighters())
            {
                if (pp == null) continue;
                string sid = ResolvePhotonSteamId(pp);
                if (string.IsNullOrEmpty(sid) || sid.StartsWith("photon_"))
                {
                    Plugin.Log.LogWarning($"[FFA-REPORT] couldn't resolve actor {pp.ActorNumber} — skipping them");
                    continue;
                }
                string name = StripRichText(pp.NickName ?? sid);
                if (string.IsNullOrEmpty(name)) name = sid;
                if (name.Length > 60) name = name.Substring(0, 60);
                int teamId = -1;
                foreach (var po in pm.players)
                {
                    if (po == null || po.gameObject == null) continue;
                    var pv = po.GetComponent<PhotonView>();
                    if (pv?.Owner == null || pv.Owner.ActorNumber != pp.ActorNumber) continue;
                    teamId = po.TeamID; break;
                }
                if (teamId < 0)
                {
                    Plugin.Log.LogWarning($"[FFA-REPORT] no in-game player for actor {pp.ActorNumber} — skipping");
                    continue;
                }
                int fps = 0;
                if (pp.CustomProperties != null && pp.CustomProperties.ContainsKey(FPS_PROP_KEY))
                {
                    try { fps = Convert.ToInt32(pp.CustomProperties[FPS_PROP_KEY]); } catch { }
                }
                ApiClient.TeamTelemetry tele = null;
                if (pp.IsLocal)
                {
                    if (LocalAvgFps > 0) fps = LocalAvgFps;
                    tele = new ApiClient.TeamTelemetry
                    {
                        fpsTimeline = string.Join(",", localFps3sTimeline.Items),
                        pingTimeline = string.Join(",", pingSamples),
                        pingAvg = pingSamples.Count > 0 ? (int)Math.Round(pingSamples.Average()) : 0,
                        hitTimeline = string.Join(",", localHitTimeline.Items),
                        blockTimeline = localBlockTimeline.Count > 0
                            ? "v2|" + string.Join(",", localBlockTimeline.Items) : "",
                        bulletsFired = LocalBulletsFiredThisMatch,
                        bulletsHit = LocalBulletsHitThisMatch,
                        blocksActivated = LocalBlocksActivatedThisMatch,
                        blocksSuccessful = LocalBlocksSuccessfulThisMatch,
                        keysPressed = LocalKeysThisMatch,
                        activeSeconds = LocalActiveSecondsThisMatch,
                    };
                }
                // FFA deliberately discards the peer's broadcast damage series:
                // the reporter computes every player's damage locally (vanilla
                // RPCs it to All — #127/#130), which is strictly better data,
                // and it ships at player level below as damageTimeline.
                else if (TryGetPeerTelemetry(pp.ActorNumber,
                             out string pFps, out string pPing, out string pHit, out string pBlock,
                             out _, out int[] pCounters))
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
                    tele = new ApiClient.TeamTelemetry
                    {
                        fpsTimeline = pFps, pingTimeline = pPing, pingAvg = pingAvg,
                        hitTimeline = pHit, blockTimeline = pBlock,
                        bulletsFired = pCounters[0], bulletsHit = pCounters[1],
                        blocksActivated = pCounters[2], blocksSuccessful = pCounters[3],
                        keysPressed = pCounters[4], activeSeconds = pCounters[5],
                    };
                }
                // Build stats: EndStatsFor(sid) -> this entry's end_stats.
                // ADVISORY — outside the "ffa:"-tagged HMAC canonical.
                entries.Add(new ApiClient.FfaReportPlayer
                {
                    steamId = sid, displayName = name, slot = teamId,
                    rounds = FfaMode.RoundsFor(teamId),
                    points = FfaMode.PointsTotalFor(teamId),
                    kills = FfaMode.KillsFor(teamId),
                    leftEarly = false, fps = fps,
                    cards = FfaMode.PickHistoryFor(teamId),
                    telemetry = tele,
                    // #127/#130: computed locally for EVERY player (vanilla RPCs
                    // damage to All), so these need no peer heartbeat.
                    damageDealt = FfaMode.DamageDealtFor(teamId),
                    killTimeline = FfaMode.KillTimelineFor(teamId),
                    damageTimeline = FfaMode.DamageTimelineFor(teamId),
                    endStats = EndStatsFor(sid),
                });
                presentSteams.Add(sid);
                if (teamId == winnerTeam) winnerSteam = sid;
            }

            // Leavers: recorded at leave time with their tallies (left_early).
            // EndStatsFor(kv.Key) is normally null for these — both their
            // Player object and their Photon owner are gone before the
            // game-over capture runs, so end_stats is honestly "not recorded".
            // A leave landing late enough that both survive the capture yields
            // their build at that moment, which is equally honest.
            foreach (var kv in FfaMode.Leavers)
            {
                if (presentSteams.Contains(kv.Key)) continue;
                entries.Add(new ApiClient.FfaReportPlayer
                {
                    steamId = kv.Key,
                    displayName = kv.Value.displayName,
                    slot = kv.Value.slot,
                    rounds = kv.Value.roundsWon,
                    points = kv.Value.pointsTotal,
                    kills = kv.Value.kills,
                    leftEarly = true, fps = 0,
                    // Absent = they left in an EARLIER game of the sitting;
                    // they hold their roster slot but were never in this
                    // game (server skips rating/XP). A leaver DURING this
                    // game is absent=false and still gets rated — leaving
                    // at 0 score must not dodge the loss.
                    absent = kv.Value.leftGameNumber != FfaMode.GameNumber,
                    // Field point total when they left — drives the server's
                    // early-leave grace (under 2 = nothing was decided yet, so
                    // no rating for them this game). Only meaningful for a
                    // leave from THIS game: a carried ghost's figure belongs to
                    // a game that already ended, so send -1 and let the server
                    // read it as "not reported".
                    gamePointsAtLeave = (kv.Value.leftGameNumber == FfaMode.GameNumber
                                         ? kv.Value.gamePointsAtLeave : -1),
                    cards = FfaMode.PickHistoryFor(kv.Value.slot),
                    telemetry = null,
                    // #127/#130: a player who left DURING this game still dealt
                    // real damage, and FfaMode keys it by slot and clears it per
                    // game — so this is their true figure, and correctly 0 for an
                    // `absent` ghost who was never in this game at all.
                    damageDealt = FfaMode.DamageDealtFor(kv.Value.slot),
                    killTimeline = FfaMode.KillTimelineFor(kv.Value.slot),
                    damageTimeline = FfaMode.DamageTimelineFor(kv.Value.slot),
                });
            }

            // Codex review find 6: a player who clinches the game and closes
            // the app before the report runs exists only in the Leavers set —
            // the PlayerList loop above never saw them, and an unresolved
            // winner aborted the whole report. Any entry (present or leaver)
            // whose slot matches the winning team is the winner.
            if (string.IsNullOrEmpty(winnerSteam))
                foreach (var e in entries)
                    if (e.slot == winnerTeam) { winnerSteam = e.steamId; break; }

            if (entries.Count < 2 || string.IsNullOrEmpty(winnerSteam))
            {
                Plugin.Log.LogWarning($"[FFA-REPORT] not reportable (entries={entries.Count}, winner={(winnerSteam ?? "unresolved")})");
                return false;
            }

            // Reporter election: lowest Steam ID among PRESENT players (all FFA
            // players carry the mod — the queue is the only entry path).
            string lowest = null; long lowVal = long.MaxValue;
            foreach (var sid in presentSteams)
                if (long.TryParse(sid, out long v) && v < lowVal) { lowVal = v; lowest = sid; }
            if (lowest == null) lowest = localSteamId;
            if (lowest != localSteamId)
            {
                Plugin.Log.LogInfo($"[FFA-REPORT] reporter is {lowest}, not me — skipping");
                return true;
            }

            ApiClient.ReportFfaMatch(lobbyId, reportRoomId, photonRegion, duration,
                entries, winnerSteam, localSteamId, FfaMode.TimelineString);
            Plugin.Log.LogInfo($"[FFA-REPORT] submitted lobby={lobbyId} n={entries.Count} winner={winnerSteam}");
            return true;
        }

        /// <summary>Resolve one 2v2 game into a frozen payload: census, roster,
        /// teams, cards, fps, telemetry, builds, scores, ranked flag and the
        /// reporter election. Every mutable per-match global the report needs is
        /// read exactly once, HERE, so the result may be held across an async
        /// gap — see TeamReportPayload.
        ///
        /// Null means the game is not reportable. The caller must NOT substitute
        /// a 1v1 fallback (#65/#106).</summary>
        private static TeamReportPayload BuildTeamReportPayload(string reportRoomId, int duration)
        {
            // Census: gate + roster from ONE fighter view (converted with the
            // photonPlayers assignment below — recon structural hazard).
            var reportFighters = RoomActors.ActiveFighters();
            if (reportFighters.Length != 4)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] aborting: fighters={reportFighters.Length} (expected 4)");
                return null;
            }

            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null)
            {
                Plugin.Log.LogWarning($"[2v2-REPORT] aborting: PlayerManager.instance={(pm == null ? "null" : "set")} pm.players={(pm?.players == null ? "null" : "set")}");
                return null;
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
            var photonPlayers = reportFighters;   // census: fighters only in the report roster
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
                    return null;
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
                        fpsTimeline = string.Join(",", localFps3sTimeline.Items),
                        pingTimeline = string.Join(",", pingSamples),
                        pingAvg = pingSamples.Count > 0 ? (int)Math.Round(pingSamples.Average()) : 0,
                        hitTimeline = string.Join(",", localHitTimeline.Items),
                        blockTimeline = localBlockTimeline.Count > 0
                            ? "v2|" + string.Join(",", localBlockTimeline.Items) : "",
                        // Aug 7 item 3: cumulative damage dealt on the same 3s
                        // grid as the three series above.
                        damageTimeline = string.Join(",", localDamage3sTimeline.Items),
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
                             out string pDamage, out int[] pCounters))
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
                        // Aug 7 item 3: only a peer running Aug-6-or-newer
                        // publishes this; older peers leave it empty, which the
                        // server must store as NULL, not 0 (#257).
                        damageTimeline = pDamage,
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
                return null;
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
                // Routed correctly, just not by us. A payload rather than null:
                // "someone else is posting this" is a SUCCESS for the caller,
                // and null is reserved for "not reportable at all".
                return new TeamReportPayload { ReporterSteam = lowestSid, LocalIsReporter = false };
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
                return null;
            }
            // Convention: team1_in_db corresponds to in-game team_id=0 by default. We don't actually
            // know which DB team is which — but the server stores by player_id and the client computes
            // p1Rounds/p2Rounds via localTeamId. Map: t1 = team0 (where localTeamId==0 player lives)
            // → matches the existing p1/p2 convention. Within each team, sort by Steam ID so client
            // and server canonical orderings agree.
            team0Sids.Sort(StringComparer.Ordinal);
            team1Sids.Sort(StringComparer.Ordinal);

            var slots = new string[] { team0Sids[0], team0Sids[1], team1Sids[0], team1Sids[1] };

            var payload = new TeamReportPayload
            {
                RoomId = reportRoomId,
                // Room-scoped, but frozen with the rest so that a reader of this
                // type never has to ask which fields are live and which are not.
                Region = photonRegion,
                DurationSeconds = duration,
                StartedAt = matchStartTime,
                IsRanked = matchIsRanked,
                T1Rounds = p1Rounds, T2Rounds = p2Rounds,
                T1Points = p1Points, T2Points = p2Points,
                WinnerTeam = (p1Rounds > p2Rounds) ? 1 : 2,
                ReporterSteam = localSteamId,
                LocalIsReporter = true,
            };
            for (int i = 0; i < 4; i++)
            {
                string sid = slots[i];
                payload.Steam[i] = sid;
                payload.Name[i] = bySteam[sid].name;
                payload.Cards[i] = bySteam[sid].cards;
                payload.Fps[i] = bySteam[sid].fps;
                payload.Tele[i] = teleBySid.TryGetValue(sid, out var tl) ? tl : null;
                // Builds come from the stash CaptureEndStats filled in the
                // game-over frame, never re-read from the live objects: by the
                // time even the synchronous path runs, a rematch teardown may
                // already have wiped them (#171).
                payload.EndStats[i] = EndStatsFor(sid);
            }
            return payload;
        }

        /// <summary>Post a resolved 2v2 game.
        ///
        /// The series id is the ONE value read live here, and deliberately so:
        /// the deferred path exists precisely because it did not have one yet.
        /// Everything else comes off the payload — see TeamReportPayload.
        ///
        /// ADVISORY — the 11-field 2v2 HMAC canonical does not change.</summary>
        private static void SubmitTeamReport(TeamReportPayload p)
        {
            ApiClient.ReportTeamMatch(
                seriesId: ApiClient.ActiveTeamSeriesId,
                t1aSteam: p.Steam[0], t1aName: p.Name[0], t1aCards: p.Cards[0],
                t1bSteam: p.Steam[1], t1bName: p.Name[1], t1bCards: p.Cards[1],
                t2aSteam: p.Steam[2], t2aName: p.Name[2], t2aCards: p.Cards[2],
                t2bSteam: p.Steam[3], t2bName: p.Name[3], t2bCards: p.Cards[3],
                t1Rounds: p.T1Rounds, t2Rounds: p.T2Rounds,
                t1Points: p.T1Points, t2Points: p.T2Points,
                photonRoomId: p.RoomId, region: p.Region,
                durationSeconds: p.DurationSeconds, startedAt: p.StartedAt,
                reporterSteamId: p.ReporterSteam, isRanked: p.IsRanked, winnerTeam: p.WinnerTeam,
                t1aFps: p.Fps[0], t1bFps: p.Fps[1], t2aFps: p.Fps[2], t2bFps: p.Fps[3],
                t1aTele: p.Tele[0], t1bTele: p.Tele[1], t2aTele: p.Tele[2], t2bTele: p.Tele[3],
                t1aEndStats: p.EndStats[0], t1bEndStats: p.EndStats[1],
                t2aEndStats: p.EndStats[2], t2bEndStats: p.EndStats[3]
            );
            Plugin.Log.LogInfo($"[2v2-REPORT] submitted: t1={p.Steam[0]},{p.Steam[1]} t2={p.Steam[2]},{p.Steam[3]} winner=T{p.WinnerTeam}");
        }

        /// <summary>Synchronous 2v2 report: resolve and post in one go. False =
        /// not reportable (the caller must not fall back to 1v1); true = routed,
        /// whether by us or by the elected reporter.</summary>
        private static bool TryReportTeamMatch(string reportRoomId, int duration)
        {
            var payload = BuildTeamReportPayload(reportRoomId, duration);
            if (payload == null) return false;
            if (!payload.LocalIsReporter)
            {
                Plugin.Log.LogInfo($"[2v2-REPORT] reporter is {payload.ReporterSteam}, not me ({localSteamId}) — skipping");
                return true;
            }
            SubmitTeamReport(payload);
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

                    // Aug 6 item 1: highest max-health reached this match
                    // (held-state read — poll cadence is fine, #120).
                    RecordMaxHealthSample(data.MaxHealth);

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
                // Skip while the chat overlay / F5 menu has focus — typing "wasd"
                // in a Discord-bridged message previously false-flagged Immovable
                // Object. Hoisted above the shot check for bug #128: the T chat is
                // now openable DURING combat, so a click that lands while the box
                // has focus fires no gun (GameManager.lockInput) and must not
                // count as "fired a shot" either — that would silently break a
                // Pacifist run for anyone who chats mid-round.
                bool typingInChat = false;
                try { typingInChat = CompetitiveUI.AnyChatTyping || NativeUI.IsOpen; } catch { }
                if (!typingInChat && !achFiredShot && Input.GetMouseButton(0))
                {
                    achFiredShot = true;
                    Plugin.Log.LogInfo("[ACH] Player fired a shot");
                }
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
                // Bug #101 was real but its remedy was far too broad, and the
                // comment that justified the width was FALSE (#351). The
                // accurate asymmetry: only INSTINCT's violation detectors are
                // gated on IsCompetitiveRoom (Plugin.cs's
                // CardChoiceVisuals_SetSelected patch + the
                // RPCA_SetCurrentSelected postfix), so only Instinct's
                // "untouched" flag can look falsely clean outside a
                // mod-issued room. Every OTHER tracker — achTookDamage,
                // achDied, achFiredShot, achMoved, achJumped, achWasDown04,
                // abyssalRoundsActivated, the card capture, and the live gun
                // read — is ungated and correct in every room. The old blanket
                // gate therefore threw away 86% of all 1v1 games and 48% of
                // RATED ones (30-day production figures), because
                // IsCompetitiveRoom only accepts the mod's own room-name
                // prefixes and the majority of play happens in 6-character
                // room codes and public quickplay (#286).
                //
                // Bug 209 is the proof: Stan won 5-4 in public quickplay with
                // Shields Up + Combine + Quick Reload — 1 max ammo, ~0.6s
                // reload, a genuine God Build — and his log shows
                // "[ACH] Skipping" seven times that evening while the
                // qualifier's own diagnostic line never printed once.
                //
                // What this gate actually needs to exclude is sandbox/offline,
                // not "rooms we did not name". OfflineMode must be explicit:
                // it leaves InRoom true at the menu (#122).
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode || RoomActors.LocalIsSpectator)
                {
                    Plugin.Log.LogInfo("[ACH] Skipping — not a live online game (offline/sandbox/spectator award nothing)");
                    return;
                }
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
                // THE one achievement that genuinely needs the competitive-room
                // gate (bug #101): its violation detectors are themselves
                // gated, so outside a mod-issued room achLeftmostViolated can
                // only ever look clean and Instinct would be handed out for
                // free. Keeping the narrow check HERE is what let the blanket
                // gate above be removed without reopening #101.
                if (localWon && !achLeftmostViolated && pickCountThisMatch >= 3)
                {
                    if (!CompetitiveRoomDetect.IsCompetitiveRoom())
                        Plugin.Log.LogInfo("[ACH] Instinct skipped — scroll detection only runs in mod-issued rooms");
                    else
                    {
                        Plugin.Log.LogInfo($"[ACH] Evaluating: Instinct — PASSED ({pickCountThisMatch} untouched picks)");
                        ApiClient.UnlockAchievement(steamId, "instinct");
                    }
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

            // Spectator: the whole log-driven tracker is quiescent (Aug 10
            // design review find 12 — this listener is registered
            // unconditionally, so the Poll() quiesce never covered it). Also
            // bug 193: the MOVE PLAYERS END branch below force-closes the F5
            // menu at every combat start, which a spectator browsing the menu
            // has no reason to suffer.
            try { if (SpectatorSession.IsLocalSpectator) return; } catch { }

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
                    // Bug #91 item 9: this is NORMAL ordering, not a failure —
                    // the Unity-log intercept always runs before the Harmony
                    // EndPick postfix, which then reconciles with this synth
                    // row (target match). The old "(Harmony EndPick didn't
                    // fire)" wording sent log readers hunting a phantom bug.
                    Plugin.Log.LogInfo($"[POLL] Synthesized picked offer for {cardName} round={currentRound} (log intercept ran first; EndPick reconciles)");
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
                // Bug 206 (Aug 11 FFA playtest): this poller is 1v1-shaped —
                // it latches the FIRST non-local fighter and diffs everyone
                // against ONE shared broadcast counter, so in an FFA room it
                // recorded only that one player's picks and, when they left,
                // diffed the NEXT fighter's list against the departed one's
                // counter (misattributed picks with wrong order). Nothing FFA
                // consumes opponentCards (FFA reports read
                // FfaMode.PickHistoryFor; the hold-Tab board reads
                // currentCards), and pick visibility in
                // FFA is now the manifest-apply toast in ApplyManifestPick —
                // so this channel is pure misinformation there. Gate it off.
                if (FfaMode.EngineActive()) return;
                if (opponentCardsViaHarmony) return; // Harmony provides cards, skip Photon polling

                Photon.Realtime.Player[] players = RoomActors.ActiveFighters();   // census: opponents are fighters
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
                // Census (recon standout): a SPECTATOR runs the mod and
                // carries cr_spec, so scanning all actors would return true
                // against a VANILLA opponent — every consumer of this
                // predicate would then be wrong. Fighters only.
                var players = RoomActors.ActiveFighters();
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

        internal static string StripRichText(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            return Regex.Replace(input, "<.*?>", "").Trim();
        }

        /* Aug 7 item 2 — INVARIANT casing. Twin of CardRarityLookup.ToTitleCase
         * in Plugin.cs; see the long note there. Short version: `ToLower()` on a
         * tr-TR client turns every capital I into U+0131 DOTLESS I, so this
         * method — which sits on EVERY card-name capture path (log line, Photon
         * cr_cards property, card-bar scan) — was minting locale-specific card
         * names that became separate DB rows. Migration 195 merges the strays. */
        private static string ToTitleCase(string input)
        {
            if (string.IsNullOrEmpty(input)) return input;
            // Convert "POISON BULLETS" or "poison bullets" to "Poison Bullets"
            var words = input.ToLowerInvariant().Split(' ');
            for (int i = 0; i < words.Length; i++)
            {
                if (words[i].Length > 0)
                    words[i] = char.ToUpperInvariant(words[i][0]) + words[i].Substring(1);
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
            localFps3sTimeline.Clear(); localDamage3sTimeline.Clear();
            pointTimes.Clear();
            LocalDamageTakenThisMatch = 0f;
            peerTele.Clear();
            // Aug 6 items 1+4: expanded combat telemetry resets.
            LocalDamageDealtThisMatch = 0f; LocalMaxSingleHit = 0f;
            LocalMaxHealthSeen = 0f; LocalBestBounceKill = 0;
            LocalDeaths = 0; LocalDeathsBoundary = 0; LocalDeathsOwnBullet = 0;
            OppDeathsObserved = 0; OppDeathsBoundaryObserved = 0; OppDeathsOwnBulletObserved = 0;
            localDamageTimeline.Clear(); oppDamageTimeline.Clear();
            OppDamageDealt = 0f; OppMaxSingleHit = 0f; OppMaxHealthSeen = 0f; OppBestBounceKill = 0;
            OppExpandedTelemetrySeen = false;
            CombatTelemetry.ClearMatchState();
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
