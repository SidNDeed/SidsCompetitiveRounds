using System;
using System.Collections;
using System.Collections.Generic;
using ExitGames.Client.Photon;
using Photon.Pun;
using Photon.Realtime;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 2 — mid-game state sync.
    ///
    /// The joining-boundary decision (design §5.3): admit the Photon actor
    /// immediately, render NOTHING until the next completed battle boundary.
    /// Photon's room cache replays the fighter bodies (PhotonNetwork
    /// Instantiate events are AddToRoomCache), and the movement/projectile
    /// streams flow live — what a late joiner can never passively recover is
    /// the current map, score and exact decks. Those arrive through this
    /// protocol.
    ///
    /// ── PROTOCOL ────────────────────────────────────────────────────────
    /// Two Photon events, reliable, never cached, never acknowledged:
    ///
    ///   EVT_REQUEST (spectator -> master): [PROTO, seq]
    ///   EVT_SNAPSHOT (master -> ONE spectator, TargetActors):
    ///       [PROTO, seq, mode, phase, sceneName, levelId,
    ///        fighterActors[], fighterSteamIds[], fighterPlayerIds[],
    ///        fighterTeamIds[], fighterNames[],
    ///        scoreRounds[], scorePoints[],           (indexed by TeamID)
    ///        decksFlat[], deckOffsets[],             (per-fighter slices)
    ///        reserved]
    ///
    /// Flat parallel arrays of Photon-native primitives — deliberately no
    /// manual JSON (#61/#156: hand-sliced JSON over user-controlled strings
    /// is how display names break parsers; Photon serializes string[]/int[]
    /// natively and cannot be confused by a bracket in a nickname).
    ///
    /// NO player ever waits for any of this (design §5.4): a lost snapshot
    /// leaves the spectator black and retrying; the master answers
    /// fire-and-forget from an event handler.
    ///
    /// ── ACTIVATION ──────────────────────────────────────────────────────
    /// The boundary observation is MapManager.RPCA_CallInNewMapAndMovePlayers
    /// (an ordinary RpcTarget.All RPC the spectator receives while in-room —
    /// V/MapManager.cs:88-106). Every point transition fires it, so it
    /// arrives within one point of joining. At each observed call-in the
    /// spectator requests a FRESH snapshot: at that moment the round's picks
    /// are final (RoundTransition picks BEFORE the map call-in), so the deck
    /// slice is stable, and the map the call-in names is the map the
    /// response describes. Apply decks, verify bodies, activate.
    ///
    /// While Active, every subsequent call-in triggers the same reconcile —
    /// which is what heals the rematch case for free: vanilla FullReset runs
    /// inside the GM lifecycle the spectator suppresses, so fighter replicas
    /// keep game-1 card effects into game 2 unless somebody resets them.
    /// The reconcile sees "snapshot deck is not an extension of what I
    /// applied" and does a full reset+replay (the #211 residue-field
    /// machinery, mirrored from FfaMode's rolling replay).
    ///
    /// Live picks BETWEEN boundaries apply through vanilla's own
    /// ApplyCardStats.RPCA_Pick (the card object is a cached Photon
    /// instantiate, so the spectator has it). Pre-activation those RPCs are
    /// suppressed (SpectatorPatches) — the boundary snapshot carries them —
    /// so nothing double-applies.
    /// </summary>
    internal static class SpectatorSync
    {
        // Photon custom event codes (0-199). 47 = PoisonSync. Chosen far
        // from it; grep for "RaiseEvent" before adding neighbours.
        internal const byte EVT_REQUEST = 51;
        internal const byte EVT_SNAPSHOT = 52;

        internal enum Stage { None, Synchronizing, Applying, Active }
        internal static Stage CurrentStage { get; private set; } = Stage.None;

        // ── boundary fence, published ────────────────────────────────────
        //
        // A boundary reconcile OWNS every fighter body while it runs: it
        // resets them, replays a deck onto them and then verifies the result.
        // Anything else that mutates a body or a card bar in that window
        // fails that verification and costs the spectator a boundary (three
        // failed deck reconstructions leave the session outright). Any code
        // outside this class that touches replica card state on a spectator
        // seat must therefore fence on the same pair of generations this
        // class fences its own coroutines on:
        //   BoundaryGeneration        — bumped on every session join/leave.
        //   BoundaryAttemptGeneration — bumped by every scheduled boundary;
        //                               a newer boundary supersedes older work.
        // Published for FfaMode's spectator between-games flush, which owns
        // the FFA half of the same job and previously fenced only on its own
        // TransitionGeneration.
        internal static bool BoundaryApplyInFlight => CurrentStage == Stage.Applying;
        internal static int BoundaryGeneration => _boundaryGeneration;
        internal static int BoundaryAttemptGeneration => _boundaryAttemptGen;

        /// <summary>True when either boundary generation has moved past the
        /// captured pair — the caller's work has been superseded and must
        /// abort rather than land on bodies a newer reconcile owns.</summary>
        internal static bool BoundaryFenceMoved(int gen, int attemptGen)
            => gen != _boundaryGeneration || attemptGen != _boundaryAttemptGen;

        /// <summary>Sticky per-session activation flag (Aug 10 design review
        /// find 6): once the first boundary apply succeeds, the fullscreen
        /// blackout and the Synchronizing-stage cache sweeps are RETIRED for
        /// the session — a later failed reconcile shows the live scene with a
        /// "Syncing" note instead of flashing black and must never bury live
        /// objects. Reset only on session join/leave.</summary>
        internal static bool HasEverActivated { get; private set; }

        // ── spectator-side view of the watched match ─────────────────────
        internal static string WatchedMode { get; private set; } = "";
        internal static string WatchedPhase { get; private set; } = "";
        internal static string[] FighterNames { get; private set; } = new string[0];
        internal static int[] FighterTeams { get; private set; } = new int[0];
        // Steam ids in the same order as FighterNames — the HUD matches the
        // live-series feeds against these for the SERIES score (playtest
        // #169d: the top bar only showed the current game's rounds).
        internal static string[] FighterSteamIds { get; private set; } = new string[0];

        private static bool _hooked;
        private static bool _haveInfo;
        private static int _seq;
        private static int _awaitBoundarySeq = -1;
        private static object[] _boundaryResponse;
        private static int _boundaryGeneration;       // invalidates stale coroutines (#186 ticket pattern)

        // Pre-first-apply vanilla residue baselines per actor (#211): captured
        // BEFORE the first card lands so a reset can restore true defaults.
        // (Applied-deck state is deliberately NOT tracked here — the body's
        // own currentCards is the ground truth, see CurrentDeckNames.)
        private static readonly Dictionary<int, Residue> _residue = new Dictionary<int, Residue>();

        private struct Residue
        {
            public float gravityForce;
            public float regeneration;
            public int jumps;
            public float ammoReg;
            public GameObject projectile;
            public bool captured;
        }

        // ── wiring ───────────────────────────────────────────────────────

        /// <summary>Idempotent. Called from Plugin.Awake alongside
        /// PoisonSync.Hook so the handler exists before any room join.</summary>
        internal static void Hook()
        {
            if (_hooked) return;
            try
            {
                PhotonNetwork.NetworkingClient.EventReceived += OnEvent;
                _hooked = true;
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[SPECTATE] event hook failed: " + ex.Message); }
        }

        /// <summary>Called from the OnJoinedRoom spectator branch.</summary>
        internal static void OnJoinedSpectatorRoom()
        {
            try
            {
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                if (!string.Equals(room, SpectatorSession.PendingRoom, StringComparison.Ordinal))
                {
                    // Wrong room — a stale join landed. Leave immediately.
                    Plugin.Log?.LogWarning($"[SPECTATE] joined unexpected room — leaving");
                    LeaveToMenu("wrong room");
                    return;
                }
                Plugin.Log?.LogInfo($"[SPECTATE] in room as spectator (actors={PhotonNetwork.CurrentRoom?.PlayerCount ?? 0})");
                // A spectator is kickable BY DESIGN (r10 find 3): honor the
                // master's cooperative close for this session's lifetime.
                // Fighters keep the flag false — see Plugin.Awake's note.
                try { PhotonNetwork.EnableCloseConnection = true; } catch { }
                CurrentStage = Stage.Synchronizing;
                HasEverActivated = false;
                _haveInfo = false;
                _awaitBoundarySeq = -1;
                _boundaryResponse = null;
                _boundaryGeneration++;
                _residue.Clear();
                _boundaryFailStreak = 0;
                _deckFailStreak = 0;
                _lastSeenEpoch = int.MinValue;
                _roundLatched = false;
                _seqCo = null;
                _pendingBoundaryMapId = -1;
                _flushDeferred = false;
                _lastCommandedScene = "";
                _mapLoadGen = 0;
                _loadInFlight = false;
                _activeLoadScene = "";
                _queuedLoadScene = "";
                _cloneGenAtAwake.Clear();
                _lastObservedBoundaryMapId = -1;
                SpectatorViewState.Reset();

                // ── Clock + lifecycle ownership (Aug 10 root cause D1/D1b) ──
                // The spectator joins outside every vanilla game-entry path,
                // so TimeHandler.gameStartTime is 0 (timeScale 0: bullets,
                // IK, wobble followers and gravity all freeze while streams
                // arrive at real time), and GameManager.isPlaying is false —
                // which makes vanilla Map.Awake drop the client into GM_Test
                // test-map mode on the FIRST map load (isTestingMap
                // contamination + a handler that teleport-revives dead
                // fighter replicas at random spawns 2.5s after every death).
                // Pin all of it here, and re-assert from MaintenanceLoop —
                // the FFA engine already does the DoSpeedUp half of this for
                // its own spectators; this is the missing GM-mode sibling.
                PinSpectatorClockAndLifecycle("join");

                // ── Join-replay quarantine (design-review find 5) ──────────
                // Photon replays the room cache (the fighters' whole prior
                // sitting of map objects + cards) right after this callback.
                // Arm the tag window: PhotonMapObject.Awake tags parentless
                // clones while armed; their Start is then suppressed + buried
                // + locally unregistered REGARDLESS of when it runs (Awake
                // and Start can straddle a later live map load, so a
                // Start-time currentMap test is not an exact classifier).
                _replayTagged.Clear();
                _replayQuarantineArmed = true;
                _replayBuried = 0;

                // Observe-only client: watched picks must never sit in the
                // fighter pick buffer (design-review find 12).
                try { CardChoiceEndPickPatch.ClearPending(); } catch { }

                // The GM object hosts the PunRPC receivers the spectator
                // observes (RPCA_NextRound and friends). Vanilla only
                // activates it through RPCA_FoundGame, which fired long
                // before we joined — activate it directly; every lifecycle
                // entry point is suppressed by SpectatorPatches.
                try
                {
                    var gm = UnityEngine.Object.FindObjectOfType<GM_ArmsRace>(true);
                    if (gm != null && !gm.gameObject.activeSelf) gm.gameObject.SetActive(true);
                }
                catch { }

                // Playtest #169a: GM activation above ran GM_ArmsRace.Start,
                // which may have shown the join prompt before our patch was
                // consulted on an older flow — hide unconditionally (belt;
                // the ShowJoinGameText prefix is the suspenders).
                try { UIHandler.instance?.HideJoinGameText(); } catch { }

                // Room-cache replay hygiene happens in MaintenanceLoop, NOT
                // here (Codex r5 finds 1+2): Photon delivers the cached
                // instantiates AFTER this callback returns, so a synchronous
                // sweep here sees an empty scene and latches nothing. The
                // loop buries everything continuously while Synchronizing.

                if (Plugin.Instance != null)
                {
                    Plugin.Instance.StartCoroutine(InfoLoop(_boundaryGeneration));
                    Plugin.Instance.StartCoroutine(HeartbeatLoop(_boundaryGeneration));
                    Plugin.Instance.StartCoroutine(MaintenanceLoop(_boundaryGeneration));
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogError($"[SPECTATE] OnJoinedSpectatorRoom: {ex.Message}");
                LeaveToMenu("join setup failed");
            }
        }

        /// <summary>Called on room exit (OnLeftRoom / session end).</summary>
        internal static void OnLeftSpectatorRoom()
        {
            try { PhotonNetwork.EnableCloseConnection = false; } catch { }
            CurrentStage = Stage.None;
            HasEverActivated = false;
            _haveInfo = false;
            _awaitBoundarySeq = -1;
            _boundaryResponse = null;
            _boundaryGeneration++;         // kills every in-flight coroutine
            _residue.Clear();
            _boundaryFailStreak = 0;
            _deckFailStreak = 0;
            _lastSeenEpoch = int.MinValue;
            _roundLatched = false;
            _seqCo = null;
            _pendingBoundaryMapId = -1;
            _flushDeferred = false;
            _lastCommandedScene = "";
            _mapLoadGen = 0;
            _loadInFlight = false;
            _activeLoadScene = "";
            _queuedLoadScene = "";
            _cloneGenAtAwake.Clear();
            _lastObservedBoundaryMapId = -1;
            _replayQuarantineArmed = false;
            _replayTagged.Clear();
            _replayBuried = 0;
            WatchedMode = "";
            WatchedPhase = "";
            FighterNames = new string[0];
            FighterTeams = new int[0];
            SpectatorViewState.Reset();
            try { CardChoiceEndPickPatch.ClearPending(); } catch { }
        }

        // ── clock + lifecycle pinning (D1/D1b) ───────────────────────────

        /// <summary>Pin the vanilla state a spectator's suppressed lifecycle
        /// would otherwise leave broken. Idempotent; called at join and
        /// re-asserted every maintenance tick (nothing legitimate un-pins any
        /// of these on a spectator, so a blind re-assert cannot fight another
        /// writer). Restoration on leave is NOT needed: leaving spectate goes
        /// through NetworkRestart, which reloads the scene fresh.</summary>
        private static void PinSpectatorClockAndLifecycle(string why)
        {
            try
            {
                var th = TimeHandler.instance;
                if (th != null)
                {
                    if (th.gameStartTime < 1f)
                    {
                        th.gameStartTime = 1f;
                        Plugin.Log?.LogInfo($"[SPECTATE] armed gameStartTime ({why})");
                    }
                    // No slow-mo is ever mirrored on a spectator (design
                    // review cut F1.3): with GM PlayerDied suppressed nothing
                    // should lower this, so any sub-1 value is a missed path —
                    // snap it back rather than strand the clock (#276).
                    if (th.gameOverTime < 1f) th.gameOverTime = 1f;
                }
            }
            catch { }
            try
            {
                if (GameManager.instance != null && !GameManager.instance.isPlaying)
                {
                    GameManager.instance.isPlaying = true;
                    Plugin.Log?.LogInfo($"[SPECTATE] forced GameManager.isPlaying ({why}) — Map.Awake GM_Test trap defused");
                }
            }
            catch { }
            try
            {
                if (MapManager.instance != null && MapManager.instance.isTestingMap)
                {
                    MapManager.instance.isTestingMap = false;
                    Plugin.Log?.LogWarning($"[SPECTATE] cleared isTestingMap contamination ({why})");
                }
            }
            catch { }
            try
            {
                // A GM_Test that slipped through (activated before the pin
                // landed) must be shut down — its PlayerDied handler
                // teleport-revives dead fighter replicas at random spawns.
                var gt = GM_Test.instance;
                if (gt != null && gt.gameObject.activeSelf)
                {
                    gt.gameObject.SetActive(false);
                    Plugin.Log?.LogWarning($"[SPECTATE] deactivated stray GM_Test ({why})");
                }
            }
            catch { }
        }

        // ── join-replay quarantine (design-review find 5) ─────────────────

        private static bool _replayQuarantineArmed;
        private static int _replayBuried;
        private static readonly HashSet<int> _replayTagged = new HashSet<int>();

        internal static bool ReplayQuarantineArmed => _replayQuarantineArmed;

        /// <summary>Tag a parentless PhotonMapObject clone seen during the
        /// armed window (called from its Awake postfix). The TAG decides its
        /// Start suppression — not the armed state at Start time.</summary>
        internal static void TagReplayObject(int instanceId)
        {
            if (_replayQuarantineArmed) _replayTagged.Add(instanceId);
        }

        internal static bool IsReplayTagged(int instanceId)
            => _replayTagged.Contains(instanceId);

        internal static void CountReplayBuried() { _replayBuried++; }

        /// <summary>Disarm at the first LIVE map flow (RPCA_LoadLevel or a
        /// call-in): everything cache-replayed has been delivered by then.</summary>
        internal static void DisarmReplayQuarantine(string why)
        {
            if (!_replayQuarantineArmed) return;
            _replayQuarantineArmed = false;
            Plugin.Log?.LogInfo($"[SPECTATE] join-replay quarantine disarmed ({why}) — buried {_replayBuried} cached object(s) at source");
            // Aug 11 (bug 197): the 1s maintenance sweep needs a tick INSIDE
            // the Synchronizing window to bury cache-replayed CARD husks
            // (cards are structurally outside the PhotonMapObject at-source
            // quarantine), and a fast join can collapse that window to zero —
            // NotNic: join → replay burst → call-in → ACTIVE with no tick
            // between, so his card table survived unburied for the whole
            // sitting. The disarm is the one point that provably runs AFTER
            // the entire cache replay has been delivered and BEFORE first
            // activation — sweep synchronously here, window size be damned.
            if (!HasEverActivated)
            {
                try { SweepCardObjects("cached"); } catch { }
                try { SweepStaleMapObjects(); } catch { }
            }
        }

        /// <summary>Aug 10 r2 find 3: a LIVE (untagged) map-object clone can
        /// arrive while the spectator's local map is still null (we joined
        /// after the load RPC; the direct local load is in flight). Running
        /// vanilla Start then would NRE and leave a registered orphan view —
        /// the exact collision debt this batch closes. Defer: wait for the
        /// local map, then re-invoke Start (the prefix passes it to vanilla
        /// once currentMap exists). Timeout = treat as husk (bury + clean),
        /// which is exactly what the old code did to EVERYTHING.</summary>
        // ── map-load coordinator (Aug 10 r4 blocker 1) ─────────────────
        // VERIFIED VANILLA MODEL (MapManager.cs:139-191): RPCA_LoadLevel only
        // STARTS the additive scene load; currentLevelID and currentMap both
        // advance ATOMICALLY in OnLevelFinishedLoading — so
        // `currentLevelID == mapId` IS the settling test. Map.levelID is NOT
        // scene identity: OnLevelFinishedLoading assigns it from the OLD
        // currentLevelID before advancing, making it a shared READINESS
        // TOKEN (LoadedForAll compares fighters' reports against it). The
        // only observable "a load is in flight toward scene S" signal is the
        // RPCA_LoadLevel ARG — recorded here by the load postfix.
        private static string _lastCommandedScene = "";
        private static int _mapLoadGen;

        private static void NoteMapLoadCommanded(string sceneName)
        {
            if (string.IsNullOrEmpty(sceneName)) return;
            if (string.Equals(sceneName, _lastCommandedScene, StringComparison.Ordinal)) return;
            _lastCommandedScene = sceneName;
            _mapLoadGen++;
        }

        internal static string LastCommandedScene => _lastCommandedScene;

        // ── load serializer (Aug 10 r5 blocker 1) ────────────────────
        // Vanilla RPCA_LoadLevel subscribes OnLevelFinishedLoading PER CALL;
        // two loads in flight double-subscribe the handler, which can wrap
        // one scene twice, schedule a bogus unload and leave the second load
        // with no handler at all (independently demonstrated in a 2v2 log's
        // duplicate-completion failure). On a spectator — chronically behind
        // the fighters — overlap is routine, so loads are SERIALIZED: one
        // active load; the latest DIFFERENT target queues and launches from
        // the completion hook; same-target duplicates drop while active.
        private static bool _loadInFlight;
        private static string _activeLoadScene = "";
        private static string _queuedLoadScene = "";

        // NO TTL, deliberately (Aug 10 r7: the 20s TTL + expiry watchdog
        // produced two consecutive rounds of HIGH findings — expiry could
        // strand the queue, and TTL re-admission raced the stale-handler
        // cleanup. The model it guarded against — a valid additive
        // LoadScene that never completes — is one VANILLA itself does not
        // handle either (no fighter recovery exists). Deleted per the
        // #310 rule: liveness recovery now lives at the RECONCILE level
        // (TickReconcileLiveness), which owns decidable state.)
        internal static bool MapLoadInFlight => _loadInFlight;

        /// <summary>RPCA_LoadLevel PREFIX gate (spectator only). True = let
        /// vanilla start the load; false = suppressed (queued or duplicate).</summary>
        internal static bool GateMapLoad(string sceneName)
        {
            try
            {
                if (string.IsNullOrEmpty(sceneName)) return false;
                if (!MapLoadInFlight)
                {
                    _loadInFlight = true;
                    _activeLoadScene = sceneName;
                    _queuedLoadScene = "";
                    NoteMapLoadCommanded(sceneName);
                    return true;
                }
                if (string.Equals(sceneName, _activeLoadScene, StringComparison.Ordinal))
                {
                    // Re-command of the ACTIVE scene: the newest target IS
                    // the active load, so anything queued is now stale (r6
                    // find 2: Y active, Z queued, Y re-commanded — launching
                    // stale Z at Y's completion stranded the spectator on the
                    // wrong map). Clearing a queued Z must ALSO advance the
                    // clone generation (r7 find 3): Z's already-arrived
                    // clones were stamped with Y's generation and would
                    // otherwise start under Y, corrupting its accounting.
                    // The bump buries them — and may bury some of Y's own
                    // deferred clones too, which is the SAFE direction
                    // (missing pieces beat misparented ones).
                    if (!string.IsNullOrEmpty(_queuedLoadScene))
                    {
                        _queuedLoadScene = "";
                        _mapLoadGen++;
                    }
                    return false;
                }
                _queuedLoadScene = sceneName;   // latest different target wins
                Plugin.Log?.LogInfo($"[SPECTATE] queued map load behind the active one");
                return false;
            }
            catch { return true; }
        }

        /// <summary>OnLevelFinishedLoading POSTFIX (spectator only): the
        /// active load settled — pin local readiness to the settled map's
        /// own token (r5 find 2: with inbound fighter reports suppressed,
        /// this scalar is fully spectator-owned) and launch any queued load
        /// through the gate.</summary>
        internal static void OnMapLoadCompleted()
        {
            try
            {
                _loadInFlight = false;
                _activeLoadScene = "";
                PinLocalMapReadiness("load completed");
                LaunchQueuedLoad();
            }
            catch { }
        }

        private static void LaunchQueuedLoad()
        {
            if (string.IsNullOrEmpty(_queuedLoadScene)) return;
            string next = _queuedLoadScene;
            _queuedLoadScene = "";
            Plugin.Log?.LogInfo($"[SPECTATE] launching queued map load");
            try { MapManager.instance?.RPCA_LoadLevel(next); } catch { }
        }

        /// <summary>Reconcile-liveness tick (r7 restructure): if an observed
        /// boundary's attempt died (16s map wait expired while its load was
        /// still queued/slow) the spectator would otherwise stay dark until
        /// the NEXT natural boundary — forever, pre-activation, if the game
        /// ends first. When the settled map IS the last observed boundary's
        /// map and no attempt is running, re-schedule the reconcile. The
        /// attempt then passes its map wait instantly and proceeds to the
        /// snapshot. Post-activation the next boundary self-heals, so this
        /// only fires pre-activation.</summary>
        internal static void TickReconcileLiveness()
        {
            try
            {
                if (HasEverActivated) return;
                if (CurrentStage != Stage.Synchronizing) return;   // an attempt holds Applying
                if (_lastObservedBoundaryMapId < 0) return;
                if (SpectatorSession.LeaveRequested) return;
                var mm = MapManager.instance;
                if (mm == null || mm.currentLevelID != _lastObservedBoundaryMapId) return;
                if (!MapSettledOnCommanded()) return;
                Plugin.Log?.LogInfo($"[SPECTATE] reconcile liveness: re-scheduling boundary {_lastObservedBoundaryMapId}");
                ScheduleBoundary(_lastObservedBoundaryMapId);
            }
            catch { }
        }

        private static int _lastObservedBoundaryMapId = -1;

        /// <summary>Local readiness scalar := the settled map's OWN levelID
        /// (vanilla's readiness token). Inbound RPCA_ReportMapLoaded is
        /// suppressed on spectators (r5 find 2: a slow fighter's report
        /// carries the token of ITS load lineage, which after our direct
        /// load can differ from ours — an overwrite left LoadedForAll false
        /// forever and every clone kinematic).</summary>
        internal static void PinLocalMapReadiness(string why)
        {
            try
            {
                var mm = MapManager.instance;
                var cm = mm != null ? mm.currentMap : null;
                if (mm == null || cm == null || cm.Map == null) return;
                if (mm.otherPlayersMostRecentlyLoadedLevel != cm.Map.levelID)
                {
                    mm.otherPlayersMostRecentlyLoadedLevel = cm.Map.levelID;
                    Plugin.Log?.LogInfo($"[SPECTATE] readiness pinned to token {cm.Map.levelID} ({why})");
                }
            }
            catch { }
        }

        /// <summary>True when the current map wrapper's SCENE is the last
        /// commanded one (no load in flight). With no command ever observed,
        /// any settled map counts — the steady state for a spectator that
        /// joined long after the last transition.</summary>
        internal static bool MapSettledOnCommanded()
        {
            try
            {
                var mm = MapManager.instance;
                var cm = mm != null ? mm.currentMap : null;
                if (cm == null || cm.Map == null) return false;
                if (string.IsNullOrEmpty(_lastCommandedScene)) return true;
                return string.Equals(cm.Scene.name, _lastCommandedScene, StringComparison.Ordinal);
            }
            catch { return false; }
        }

        // Live-clone identity is stamped at AWAKE (r5 find 4: sampling the
        // generation at Start is too late — a newer command arriving in the
        // Awake->Start gap would bind the clone to the WRONG map).
        private static readonly Dictionary<int, int> _cloneGenAtAwake = new Dictionary<int, int>();

        internal static void StampLiveCloneGen(int instanceId)
        {
            try
            {
                // ACCEPTED RESIDUAL (r6 find 3, bound corrected per r7 find
                // 4): the no-command-known branch binds blindly to the NEXT
                // command. If the spectator missed this clone's own load RPC
                // AND the next observed command is already a LATER map
                // (backlogged double transition), EVERY such clone — there
                // can be several — starts under that later map, decrementing
                // its missingObjects early and standing as an extra/kinematic
                // piece until that map unloads. Spectator-local, one map's
                // lifetime, self-healing at its unload — which is the
                // pre-batch baseline behavior for ALL clones, all the time.
                _cloneGenAtAwake[instanceId] =
                    string.IsNullOrEmpty(_lastCommandedScene) ? _mapLoadGen + 1 : _mapLoadGen;
            }
            catch { }
        }

        internal static void DeferMapObjectStart(PhotonMapObject o)
        {
            try
            {
                if (Plugin.Instance == null || o == null)
                {
                    if (o != null) SafeBuryAndClean(o.gameObject);
                    return;
                }
                // BIND the clone to the load generation it can legitimately
                // settle under (r4 blocker 1): the one stamped at ITS OWN
                // Awake (r5 find 4), falling back to now — the CURRENT gen
                // when a load is in flight, or the NEXT one when nothing was
                // commanded yet (mid-transition join: the boundary's direct
                // load names this clone's map). A command beyond that means
                // this clone's map is gone — bury, never parent it later.
                int allowedGen;
                if (_cloneGenAtAwake.TryGetValue(o.GetInstanceID(), out allowedGen))
                    _cloneGenAtAwake.Remove(o.GetInstanceID());
                else
                    allowedGen = string.IsNullOrEmpty(_lastCommandedScene) ? _mapLoadGen + 1 : _mapLoadGen;
                Plugin.Instance.StartCoroutine(DeferredMapObjectStart(o, _boundaryGeneration, allowedGen));
            }
            catch { }
        }

        private static IEnumerator DeferredMapObjectStart(PhotonMapObject o, int gen, int allowedGen)
        {
            float t0 = Time.unscaledTime;
            while (Time.unscaledTime - t0 < 15f)
            {
                if (gen != _boundaryGeneration) yield break;   // session over — OnLeft cleans up
                if (o == null || o.gameObject == null) yield break;
                if (_mapLoadGen > allowedGen) break;           // superseded — bury below
                if (MapSettledOnCommanded())
                {
                    // Re-invoke vanilla Start (publicized): the prefix sees a
                    // settled map now and lets it through — correct
                    // parenting, correct missingObjects accounting.
                    try { o.Start(); } catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] deferred map-object start: {ex.Message}"); }
                    yield break;
                }
                yield return null;
            }
            if (o != null && o.gameObject != null)
            {
                Plugin.Log?.LogWarning("[SPECTATE] deferred map object superseded/timed out — burying as husk");
                SafeBuryAndClean(o.gameObject);
            }
        }

        /// <summary>Bury + locally unregister, in the ONLY safe order (Aug 10
        /// r2 find 6): the view array must be captured while the object is
        /// still ACTIVE — SetActive(false) runs OnDisable callbacks that can
        /// detach or destroy child views, and a post-disable traversal would
        /// miss them, leaving registry debt.</summary>
        internal static void SafeBuryAndClean(GameObject go)
        {
            try
            {
                PhotonView[] views = null;
                try { views = go.GetComponentsInChildren<PhotonView>(true); } catch { }
                go.SetActive(false);
                if (views != null) SafeLocalCleanViews(views);
            }
            catch { }
        }

        // ── local view hygiene (design-review find 4) ─────────────────────

        /// <summary>Locally unregister every PhotonView on a buried husk so a
        /// rematch's recycled view IDs cannot collide with it (the proven
        /// game-2 desync: 348-432 "PhotonView ID duplicate" errors). IDENTITY
        /// SAFE: PUN's LocalCleanPhotonView removes by ID without checking
        /// which instance the registry holds — if the registry already maps
        /// this ID to a DIFFERENT (live) view, removing would unregister the
        /// live one. In that case only mark the husk removed so its own
        /// destruction can never evict the live entry either. No Object.
        /// Destroy anywhere (#94), no network op.</summary>
        private static void SafeLocalCleanViews(PhotonView[] views)
        {
            for (int i = 0; i < views.Length; i++)
            {
                var v = views[i];
                if (v == null) continue;
                try
                {
                    var cur = PhotonNetwork.GetPhotonView(v.ViewID);
                    if (cur != null && !ReferenceEquals(cur, v))
                    {
                        v.removedFromLocalViewList = true;   // publicized
                        continue;
                    }
                    PhotonNetwork.LocalCleanPhotonView(v);
                }
                catch { }
            }
        }

        /// <summary>User-initiated or server-forced leave. ORDER IS THE FIX
        /// for Codex r1 find 2: the session (and with it every suppression
        /// guard and the staged role property) stays ALIVE until the room
        /// exit is actually observed — OnLeftRoom runs EndSession, which
        /// clears the properties once outside the room. Ending eagerly here
        /// opened a window where the still-in-room client ran fighter paths,
        /// and left cr_spec permanently staged (the next FIGHTER room would
        /// classify us spectator). Fighter-safe by construction — our leave
        /// is filtered out of their teardown by Spectator_LeaveIsInvisible.</summary>
        internal static void LeaveToMenu(string reason)
        {
            Plugin.Log?.LogInfo($"[SPECTATE] leaving ({reason})");
            SpectatorSession.RequestLeave();
            try { ApiClient.SpectateLeaveNotify(); } catch { }
            // Kill our own loops/coroutines now (they must not act during the
            // exit) but keep the SESSION alive for the guards.
            _boundaryGeneration++;
            try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }
            // If we were never in a room (joiner-phase failure), there is no
            // exit to observe — end immediately; TickPendingClear covers the
            // rest.
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode)
                {
                    SpectatorSession.EndSession(reason);
                    OnLeftSpectatorRoom();
                }
            }
            catch { }
        }

        // ── spectator: request loops ─────────────────────────────────────

        private static IEnumerator InfoLoop(int gen)
        {
            float started = Time.unscaledTime;
            while (gen == _boundaryGeneration && SpectatorSession.IsLocalSpectator)
            {
                if (_haveInfo) yield break;
                if (Time.unscaledTime - started > 90f)
                {
                    // 90s in a room with a silent master: the game is likely
                    // over or the master can't speak the protocol. Leave —
                    // blackout forever helps nobody (design §3.6 failure table).
                    LeaveToMenu("no snapshot response");
                    yield break;
                }
                SendRequest(++_seq);
                yield return new WaitForSecondsRealtime(6f);
            }
        }

        /// <summary>Spectator housekeeping tick (playtest #169 items a/b/d).
        ///
        /// GHOST CARDS (a): pick-phase card objects are Photon-instantiated
        /// (room-cached), but vanilla destroys the unpicked ones LOCALLY
        /// (RemoveAfterSeconds in IDoEndPick) — the cache entry survives, so
        /// every late joiner gets the whole card table replayed at its parked
        /// world position, forever. Fighters never see this (they ran the
        /// destroy); only we do. SetActive(false) locally — never Destroy, the
        /// objects are Photon-owned (#94) — which also removes their colliders
        /// from our local bullet sim (the BulletPush NREs in bug 169, and the
        /// shoot-to-pick hazard the ApplyCardStats.Pick patch backstops).
        ///
        /// COSMETICS (b): the fighter-side reapply loop runs from the fighter
        /// join path we deliberately skip — this is the read-only equivalent.
        ///
        /// SERIES SCORE (d): refresh the live-series feeds so the HUD can show
        /// the series tally next to the game score.</summary>
        private static IEnumerator MaintenanceLoop(int gen)
        {
            float lastCosmetics = -999f, lastSeries = -999f;
            while (gen == _boundaryGeneration && SpectatorSession.IsLocalSpectator && PhotonNetwork.InRoom)
            {
                // Re-assert the clock/lifecycle pins every tick (D1/D1b) —
                // cheap, idempotent, and the only defense against a path we
                // missed lowering the clock or re-arming GM_Test.
                try { PinSpectatorClockAndLifecycle("tick"); } catch { }
                // Reconcile liveness (r7 restructure — replaces the load
                // TTL watchdog; see TickReconcileLiveness).
                try { TickReconcileLiveness(); } catch { }

                // Cache-replay hygiene ONLY while dark (Codex r5): cards and
                // map pieces present during Synchronizing are stale replays;
                // anything spawning during Applying (the incoming map) or
                // Active (live picks) is real and must stay visible. AND only
                // before the first activation (Aug 10 find 6): a later failed
                // reconcile re-enters Synchronizing, where these sweeps would
                // bury LIVE objects.
                if (CurrentStage == Stage.Synchronizing && !HasEverActivated)
                {
                    try { SweepCardObjects("cached"); } catch { }
                    SweepStaleMapObjects();
                }
                if (Time.unscaledTime - lastCosmetics > 6f)
                {
                    lastCosmetics = Time.unscaledTime;
                    try
                    {
                        foreach (var pp in RoomActors.ActiveFighters())
                        {
                            if (pp == null) continue;
                            try { PlayerColorCosmetic.ReapplyForActor(pp.ActorNumber); } catch { }
                            try { TrailCosmetic.ReattachForActor(pp.ActorNumber); } catch { }
                            try { PlayerEffectCosmetic.ReapplyForActor(pp.ActorNumber); } catch { }
                        }
                    }
                    catch { }
                }
                if (Time.unscaledTime - lastSeries > 15f)
                {
                    lastSeries = Time.unscaledTime;
                    try { ApiClient.FetchActiveSeries(); } catch { }
                    try { ApiClient.FetchActiveTeamSeries(); } catch { }
                }
                // 1s while dark (bounds how long stale colliders can eat
                // replicated bullets), 2s once live.
                yield return new WaitForSecondsRealtime(CurrentStage == Stage.Synchronizing ? 1f : 2f);
            }
        }

        /// <summary>Bury every Photon card object in the scene. Callers pick
        /// the moment: the 1s maintenance tick + the quarantine disarm run it
        /// pre-activation ("cached" — the replayed pick tables of the room's
        /// past), and the +3s post-call-in fence runs it live ("leftover" —
        /// cards whose local destruction never got scheduled, bug 197). A
        /// LIVE pick phase is never on screen at either moment: activation
        /// happens at a call-in and every pick window precedes its call-in,
        /// so spectators still watch real picks (playtest #2d). No id
        /// bookkeeping at all — ViewIDs recycle (r5 find 8).</summary>
        private static void SweepCardObjects(string label)
        {
            var infos = UnityEngine.Object.FindObjectsOfType<CardInfo>();
            int hidden = 0;
            for (int i = 0; i < infos.Length; i++)
            {
                var ci = infos[i];
                if (ci == null || ci.gameObject == null) continue;
                if (!ci.gameObject.activeInHierarchy) continue;
                // ViewID > 0 excludes CardSnapshot's local render clones (r1
                // find 4: their PhotonView is ViewID-0 and pending same-frame
                // destroy — burying one forces the native-card capture to
                // retry). Networked pick cards always carry a real id.
                var pv = ci.GetComponent<PhotonView>();
                if (pv == null || pv.ViewID <= 0) continue;
                // Bury + local unregister (Aug 10 find 4/D2): buried card
                // husks' views collide with the rematch's recycled IDs
                // exactly like map objects do (View 1002 Bullet_Base vs
                // ghost Quick Shot in both spectator logs). Capture-then-
                // deactivate order lives inside the helper (r2 find 6).
                SafeBuryAndClean(ci.gameObject);
                hidden++;
            }
            if (hidden > 0)
                Plugin.Log?.LogInfo($"[SPECTATE] hid {hidden} {label} card object(s)");
        }

        /// <summary>Playtest #2f: the room cache also replays every networked
        /// MAP piece (crates, saws) from EVERY map this room has played — the
        /// fighters destroyed theirs locally as maps changed, so only a
        /// (re)joining spectator gets the whole graveyard, stacked and
        /// permanent. Called ONLY while Synchronizing (Codex r5 rework: the
        /// cached replay lands after OnJoinedRoom, inside this window):
        /// buries everything including the current map's pieces — we are
        /// black anyway, and activation happens at a CALL-IN, i.e. a fresh
        /// map whose pieces arrive as NEW live instantiates while we are in
        /// Applying, where this never runs. SetActive(false) locally, never
        /// Destroy (#94).</summary>
        private static void SweepStaleMapObjects()
        {
            try
            {
                // Aug 10 rework (design-review D2 + doubles race): the old
                // indiscriminate burial (a) could bury an INCOMING live map's
                // copy before its Start ran — missingObjects never decrements,
                // Map.StartMatch never fires, placeholders go immortal and the
                // rope joints the dead one ("double boxes on strings") — and
                // (b) left every buried husk's PhotonView registered, which is
                // the proven game-2 view-ID collision storm. New rules:
                //   * placeholders (authored children, photonSpawned false
                //     with a parent) are NEVER touched — vanilla's accounting
                //     needs them;
                //   * pre-Start clones (no parent, photonSpawned false) are
                //     skipped this tick — the next 1s tick classifies them
                //     (their Start either parents them under the live map or
                //     the replay quarantine already buried them at source);
                //   * networked copies parented under the CURRENT map are
                //     LIVE — skip;
                //   * everything else (orphans whose Start threw during the
                //     cache replay, copies of older maps) is buried AND
                //     locally unregistered.
                Transform liveMapRoot = null;
                try
                {
                    var cm = MapManager.instance != null ? MapManager.instance.currentMap : null;
                    if (cm != null && cm.Map != null) liveMapRoot = cm.Map.transform;
                }
                catch { }

                var objs = UnityEngine.Object.FindObjectsOfType<PhotonMapObject>();
                int hidden = 0;
                for (int i = 0; i < objs.Length; i++)
                {
                    var o = objs[i];
                    if (o == null || o.gameObject == null) continue;
                    if (!o.gameObject.activeInHierarchy) continue;
                    bool isCopy = false;
                    try { isCopy = o.photonSpawned; } catch { }   // publicized
                    if (!isCopy) continue;   // placeholder or pre-Start clone
                    if (liveMapRoot != null && o.transform.IsChildOf(liveMapRoot)) continue;   // live
                    SafeBuryAndClean(o.gameObject);
                    hidden++;
                }
                if (hidden > 0)
                    Plugin.Log?.LogInfo($"[SPECTATE] hid {hidden} stale networked map object(s) from the room cache");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] map-object sweep: {ex.Message}"); }
        }

        private static IEnumerator HeartbeatLoop(int gen)
        {
            while (gen == _boundaryGeneration && SpectatorSession.IsLocalSpectator && PhotonNetwork.InRoom)
            {
                yield return new WaitForSecondsRealtime(15f);
                if (gen != _boundaryGeneration || !SpectatorSession.IsLocalSpectator) yield break;
                // Fire-and-forget: ApiClient invokes OnHeartbeatRejected on a
                // definitive server "no" (revoked/expired/game over). Network
                // blips are NOT rejections — the lease outlives a lost beat.
                try { ApiClient.SpectateHeartbeat(); } catch { }

                // Local liveness: if every fighter has gone, the match is
                // over regardless of what the server still lists.
                try
                {
                    if (RoomActors.ActiveFighterCount() == 0)
                    {
                        LeaveToMenu("all fighters left");
                        yield break;
                    }
                }
                catch { }
            }
        }

        /// <summary>ApiClient calls this when the server definitively rejects
        /// the lease (revoked by opt-out, expired, game ended).</summary>
        internal static void OnHeartbeatRejected(string why)
        {
            if (!SpectatorSession.IsLocalSpectator) return;
            try { CompetitiveUI.ShowNotification(I18n.Tr("Spectator session ended."), Color.yellow, 5f); } catch { }
            LeaveToMenu($"lease rejected: {why}");
        }

        private static void SendRequest(int seq)
        {
            try
            {
                bool ok = PhotonNetwork.RaiseEvent(
                    EVT_REQUEST,
                    new object[] { (byte)SpectatorSession.PROTOCOL, seq },
                    new RaiseEventOptions { Receivers = ReceiverGroup.MasterClient },
                    SendOptions.SendReliable);
                if (!ok) Plugin.Log?.LogWarning("[SPECTATE] snapshot request raise returned false");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] request send: {ex.Message}"); }
        }

        // ── boundary observation ─────────────────────────────────────────

        /// <summary>Called from the MapManager.RPCA_CallInNewMapAndMovePlayers
        /// Postfix on the SPECTATOR client only. Each call-in is a boundary:
        /// picks are final, a known map is entering, bodies are about to be
        /// moved/revived.</summary>
        internal static void OnCallInObserved(int mapId)
        {
            if (!SpectatorSession.IsLocalSpectator) return;
            // Boundaries are rejected outright once a leave is requested (r3
            // find 8): the generation fence only covers coroutines that
            // already started, not a call-in queued during the exit window.
            if (SpectatorSession.LeaveRequested) return;
            // A call-in ends the observed round-transition: re-open the
            // round-observation latch (find 9's dedupe window) and, if the
            // join-replay window was somehow still armed, close it — live map
            // flow has provably begun. These side effects live ONLY here —
            // the deferred re-issue path calls ScheduleBoundary directly (r3
            // find 7: re-entering this method cleared a NEWER round latch).
            _roundLatched = false;
            DisarmReplayQuarantine("call-in");
            // Aug 11 playtest item 1: a call-in means the pick phase is OVER,
            // but on a spectator the only vanilla CardChoiceVisuals.Hide
            // rides PlayerManager.Move's tail — downstream of the map-settle
            // spin — and the point sequence's own Show (DoWinSequence's tail)
            // can land AFTER it under dispatch backlog. Retire both at RPC
            // receipt so the picker avatar can never float over the next
            // battle, and fence a leftover-card sweep for cards whose local
            // destruction never got scheduled (bug 197's permanence class).
            RetireBoundaryPickDisplay();
            if (Plugin.Instance != null)
                Plugin.Instance.StartCoroutine(LeftoverCardSweep(_boundaryGeneration));
            _lastObservedBoundaryMapId = mapId;
            ScheduleBoundary(mapId);
        }

        /// <summary>Stop the running point sequence (it is the only
        /// spectator-side Show source) and hide the pick-phase avatar. Both
        /// idempotent; a later legitimate Show cancels the pending DelayHide
        /// via vanilla's own StopAllCoroutines.</summary>
        private static void RetireBoundaryPickDisplay()
        {
            try
            {
                var pv = PointVisualizer.instance;
                if (_seqCo != null && pv != null)
                {
                    try { pv.StopCoroutine(_seqCo); } catch { }
                    try { pv.Close(); } catch { }
                }
                _seqCo = null;
            }
            catch { }
            try
            {
                var vis = CardChoiceVisuals.instance;
                if (vis != null && vis.isShowinig) vis.Hide();
            }
            catch { }
        }

        /// <summary>Bug 197 backstop: a card whose IDoEndPick never scheduled
        /// its RemoveAfterSeconds is invisible to vanilla's ClearObjects
        /// forever (it only destroys ACTIVE RemoveAfterSeconds carriers).
        /// Healthy cards self-destroy by pick-end +~1.7s and every pick
        /// window precedes its call-in, so anything still active at call-in
        /// +3s with no NEWER round observed is a leftover by construction.
        /// The round-latch fence covers the fast-round case where the next
        /// pick phase could already be on screen at +3s — that boundary's
        /// own sweep picks up the slack.</summary>
        private static IEnumerator LeftoverCardSweep(int gen)
        {
            yield return new WaitForSecondsRealtime(3f);
            if (gen != _boundaryGeneration) yield break;
            if (!SpectatorSession.IsLocalSpectator) yield break;
            if (RoundObservationLatched) yield break;
            try { SweepCardObjects("leftover"); } catch { }
        }

        /// <summary>Side-effect-free reconcile scheduler (r3 find 7). Every
        /// real call-in supersedes the in-flight attempt via the attempt
        /// generation (r3 find 4) — a stale attempt must never local-load an
        /// OLD map over the newer one or apply a stale snapshot.</summary>
        private static void ScheduleBoundary(int mapId)
        {
            if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
            if (CurrentStage == Stage.None) return;
            _boundaryAttemptGen++;
            if (CurrentStage == Stage.Applying)
            {
                // NEVER discard a newer boundary (r2 find 4): latest-wins;
                // the superseded attempt notices the generation bump at its
                // next resume and its finally re-issues this one.
                _pendingBoundaryMapId = mapId;
                return;
            }
            if (Plugin.Instance == null) return;
            Plugin.Instance.StartCoroutine(BoundaryAttempt(mapId, _boundaryGeneration, _boundaryAttemptGen));
        }

        // Latest call-in observed while an attempt was mid-flight (r2 find 4).
        private static int _pendingBoundaryMapId = -1;
        // Bumped by every scheduled boundary: an attempt whose gen is stale
        // has been superseded and must exit without counting a failure.
        private static int _boundaryAttemptGen;

        // ── round observation latch + between-points display ─────────────

        // Vanilla dedupes duplicate RPCA_NextRound broadcasts with
        // isTransitioning, which lives in the machine the spectator
        // suppresses (find 9). One observed round per call-in, with a TTL so
        // a missed call-in cannot eat the next game's first round.
        private static bool _roundLatched;
        private static float _roundLatchedAt;

        internal static bool RoundObservationLatched
            => _roundLatched && Time.unscaledTime - _roundLatchedAt < 20f;

        internal static void LatchRoundObservation()
        {
            _roundLatched = true;
            _roundLatchedAt = Time.unscaledTime;
        }

        // One replaceable sequence handle (find 9): never StopAllCoroutines
        // on the shared PointVisualizer — stop exactly our previous sequence
        // and normalize its overlay before starting the next.
        private static Coroutine _seqCo;

        /// <summary>Drive vanilla's own between-points display from the
        /// observed score (item 2: spectators used to get a hard black flash
        /// here and never saw the score orbs fighters see). Display-only.
        /// DoWinSequence is 1v1-shaped (its tail shows the loser's pick
        /// visualizer via a team-id-as-player-index call) — team modes and
        /// game-ending rounds get the plain point sequence / a notification
        /// instead (find 8).</summary>
        internal static void PlayPointSequence(bool conversion, bool gameOver,
                                               int visP1, int visP2, int p1r, int p2r,
                                               int winningTeamID)
        {
            try
            {
                var pv = PointVisualizer.instance;
                if (gameOver)
                {
                    // Retire any running sequence FIRST (r2 find 7): a fast
                    // decisive kill mid-sequence would otherwise leave the
                    // orb overlay animating over the victory notification.
                    if (_seqCo != null && pv != null)
                    {
                        try { pv.StopCoroutine(_seqCo); } catch { }
                        try { pv.Close(); } catch { }
                        _seqCo = null;
                    }
                    string who = FighterNamesForTeam(winningTeamID);
                    if (who.Length > 0)
                        CompetitiveUI.ShowNotification(I18n.TrF("Game over - {0} wins", who), Color.green, 6f);
                    return;
                }
                // Vanilla's pip logic hardcodes the 2-point round shape (r2
                // find 5: values > 1 render "ROUND", so a 3-point room's
                // second point mis-renders). Custom thresholds skip the
                // sequence — the HUD score line is threshold-aware.
                if (SpectatorViewState.PointsToWinRound != 2) return;
                if (pv == null || !pv.gameObject.activeInHierarchy) return;
                if (_seqCo != null)
                {
                    try { pv.StopCoroutine(_seqCo); } catch { }
                    _seqCo = null;
                    try { pv.Close(); } catch { }   // publicized — vanilla's own overlay reset
                }
                bool orangeWinner = winningTeamID == 0;
                bool oneVone = WatchedMode == "1v1"
                               && FighterTeams != null && FighterTeams.Length == 2;
                if (conversion && oneVone)
                    _seqCo = pv.StartCoroutine(pv.DoWinSequence(visP1, visP2, p1r, p2r, orangeWinner));
                else
                    _seqCo = pv.StartCoroutine(pv.DoSequence(visP1, visP2, orangeWinner));
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] point sequence: {ex.Message}"); }
        }

        // ── between-games flush (Aug 12 item 9a) ─────────────────────────
        //
        // The problem: on a spectator seat NOTHING clears card state at a game
        // boundary until the NEXT boundary reconcile, which is the call-in at
        // the END of game 2's pick phase. Every vanilla clear lives behind
        // GM_ArmsRace.IDoRematch (ResetCardBards, PlayerManager.ResetCharacters
        // -> Player.FullReset), reached only from the rematch popup, and the
        // spectator suppresses GameOverTransition — so the popup, and with it
        // every clear, never happens (#312: a suppressed lifecycle keeps
        // whichever half already ran). Meanwhile game 2's picks ARE applied
        // live through vanilla RPCA_Pick the moment they land, and its
        // CardBarHandler.AddCard stacks them on top of game 1's bar. The Tab
        // board adds them to game 1's too, because its baseline is written by
        // the Player.FullReset postfix that just established never runs here,
        // and ClearCardBaselines is only called from GameStateWatcher's
        // Left-room branch, which the spectator quiesce returns before (#353).
        // Net effect, and exactly the report: for the whole of game 2's pick
        // phase the fighters look like they are carrying game 1's cards plus
        // new ones.
        //
        // The fix is to do at game over what the fighters themselves do at
        // game over: reset the bodies and clear the bars. Not just the
        // DISPLAY — the replicas really are still carrying game 1's applied
        // stats, so hiding the icons alone would leave a body that is wrong
        // and now also looks right. Because this clears cards for real,
        // CurrentDeckNames keeps reporting the truth and the next boundary's
        // pre-scan still compares real state against the snapshot: it sees an
        // empty deck, treats the snapshot as an extension, and applies it.
        internal static void OnGameOverObserved()
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
                // Pre-activation the boundary machinery owns every body and
                // the screen is covered anyway — nothing to flush and nothing
                // that would be seen.
                if (!HasEverActivated) return;
                if (Plugin.Instance == null) return;
                // A reconcile in flight already owns these bodies; resetting
                // underneath it would fail its own post-apply verification and
                // cost a boundary (three failed deck reconstructions leave the
                // session). It must not be DROPPED, though: that apply is
                // landing a snapshot the master answered while game 1 was
                // still live, so on its own it leaves game 1's deck in place
                // and game 2's live picks stack straight onto it for the whole
                // of the next pick phase — the exact stale-card state this
                // flush exists to prevent. Wait the apply out instead.
                if (CurrentStage == Stage.Applying)
                {
                    if (_flushDeferred) return;   // one waiter is enough
                    _flushDeferred = true;
                    Plugin.Instance.StartCoroutine(
                        DeferredGameOverFlush(_boundaryGeneration, _boundaryAttemptGen, _lastSeenEpoch));
                    return;
                }
                Plugin.Instance.StartCoroutine(BetweenGamesFlush(_boundaryGeneration, _boundaryAttemptGen));
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] game-over flush: {ex.Message}"); }
        }

        // A game-over observed while a boundary apply owned the bodies. One
        // waiter at a time; cleared when it resolves. Also cleared on session
        // join/leave so a coroutine killed with its host can never leave the
        // deferral permanently armed.
        private static bool _flushDeferred;

        /// <summary>Hold the between-games flush until the boundary apply that
        /// owns the bodies has finished, then run it.
        ///
        /// Three ways this resolves, and only the first one flushes:
        ///
        /// 1. The apply ends with the epoch it started from — the master's
        ///    snapshot predated the fighters' own rematch reset, so the deck
        ///    on screen is still game 1's and the flush is exactly right.
        /// 2. The apply ends with a CHANGED epoch — its snapshot was answered
        ///    after the fighters reset, so it already replayed the new game's
        ///    deck from scratch (BoundaryAttempt's forceReset path). Flushing
        ///    now would wipe a deck that is already correct, so this drops.
        /// 3. A newer boundary supersedes us (attempt generation moved), or
        ///    the session ends (boundary generation moved) — the reconcile
        ///    that took over is authoritative and re-applies from its own
        ///    fresh snapshot.
        ///
        /// The wall-clock cap is a safety net for a stage that never leaves
        /// Applying, NOT a timeout on the apply. Every wait inside
        /// BoundaryAttempt is itself bounded and its finally always drops the
        /// stage out of Applying, so a real attempt resolves this through
        /// 1/2/3 first — but that worst case is already ~43s (16s map + 2x8s
        /// snapshot + 8s bodies + the deck replay), so the cap has to sit well
        /// clear of it or it would fire on a legitimately slow boundary and
        /// drop a flush that was about to run. Waiting longer costs nothing
        /// now that case 2 covers the flush going stale. If the cap ever does
        /// fire, the next boundary heals the deck anyway — its epoch has
        /// changed by then, which forces a full reset+replay.</summary>
        private static IEnumerator DeferredGameOverFlush(int gen, int attemptGen, int epochAtGameOver)
        {
            try
            {
                float t0 = Time.unscaledTime;
                while (Time.unscaledTime - t0 < 90f)
                {
                    if (gen != _boundaryGeneration) yield break;
                    if (attemptGen != _boundaryAttemptGen) yield break;   // a boundary took over
                    if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) yield break;
                    if (CurrentStage != Stage.Applying)
                    {
                        if (_lastSeenEpoch != epochAtGameOver)
                        {
                            Plugin.Log?.LogInfo("[SPECTATE] between-games flush not needed — "
                                + "the boundary apply carried the rematch reset");
                            yield break;
                        }
                        if (Plugin.Instance != null)
                            Plugin.Instance.StartCoroutine(BetweenGamesFlush(gen, attemptGen));
                        yield break;
                    }
                    yield return null;
                }
                Plugin.Log?.LogWarning("[SPECTATE] between-games flush abandoned — "
                    + "a boundary apply held the bodies for 90s");
            }
            finally { _flushDeferred = false; }
        }

        private static IEnumerator BetweenGamesFlush(int gen, int attemptGen)
        {
            // Clear the bars first: they are per-TEAM, so this must be one
            // global pass rather than per body (playtest #169e).
            try
            {
                var bars = CardBarHandler.instance != null ? CardBarHandler.instance.cardBars : null;
                if (bars != null)
                    for (int b = 0; b < bars.Length; b++)
                        try { bars[b].ClearBar(); } catch { }
            }
            catch { }

            // Zero-character invariant (design §3.3): a spectator creates no
            // local player, so every entry here is a fighter replica.
            int reset = 0;
            try
            {
                var players = PlayerManager.instance?.players;
                if (players != null)
                    for (int i = 0; i < players.Count; i++)
                    {
                        var p = players[i];
                        if (p == null || p.data == null || p.data.view == null) continue;
                        var owner = p.data.view.Owner;
                        ResetBodyToVanilla(p, owner != null ? owner.ActorNumber : -1);
                        reset++;
                    }
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] game-over reset: {ex.Message}"); }

            // #278: Object.Destroy is END-OF-FRAME, so the zombie/ChildRPC
            // sweep must not run in the same frame as the FullReset that
            // scheduled the teardown — it would see every card component
            // still alive and scrub nothing.
            yield return null;
            if (gen != _boundaryGeneration) yield break;
            if (attemptGen != _boundaryAttemptGen) yield break;   // a boundary took over
            if (!SpectatorSession.IsLocalSpectator) yield break;
            try { GMArmsRaceStartGameBlockResetPatch.RunSweep("spectator between-games flush"); } catch { }
            Plugin.Log?.LogInfo($"[SPECTATE] between-games flush: {reset} body/bodies reset, card bars cleared");
        }

        private static string FighterNamesForTeam(int teamId)
        {
            try
            {
                var names = FighterNames; var teams = FighterTeams;
                if (names == null || teams == null || names.Length != teams.Length) return "";
                var sb = new System.Text.StringBuilder(32);
                for (int i = 0; i < names.Length; i++)
                {
                    if (teams[i] != teamId) continue;
                    if (sb.Length > 0) sb.Append(" + ");
                    sb.Append(SpectatorHud.PlainName(names[i]));
                }
                return sb.ToString();
            }
            catch { return ""; }
        }

        // Consecutive failed DECK reconstructions specifically (Codex r2
        // find 8: map/snapshot/body timeouts are transient and keep
        // retrying; only deck failures indicate an unrecoverable build
        // mismatch). Three in a row = leave rather than blackout forever.
        private static int _boundaryFailStreak;
        private static int _deckFailStreak;
        // Last game epoch seen from the master (slot 15). A change means the
        // fighters ran a rematch reset we never execute locally — every deck
        // must be rebuilt from scratch, even when it LOOKS like an extension
        // (Codex r1 find 11: an identical opening deck otherwise keeps
        // game-1 runtime state).
        private static int _lastSeenEpoch = int.MinValue;

        private static IEnumerator BoundaryAttempt(int mapId, int gen, int attemptGen)
        {
            var prior = CurrentStage;
            CurrentStage = Stage.Applying;
            bool ok = false;
            bool applied = false;
            // Superseded = a NEWER boundary was scheduled (r3 find 4). The
            // attempt must exit before any further local load/snapshot/deck
            // work, and its finally must not count it as a failure.
            bool superseded = false;
            try
            {
                // 1. Wait for the named map to be the loaded one locally. The
                // load RPC normally precedes the call-in inside the same
                // transition; if we joined mid-transition and missed it, load
                // the scene DIRECTLY (the local-only path vanilla itself uses,
                // V/MapManager.cs:187-192 — Codex r1 find 17) and wait again.
                float t0 = Time.unscaledTime;
                bool triedLocalLoad = false;
                while (Time.unscaledTime - t0 < 16f)
                {
                    if (gen != _boundaryGeneration) yield break;
                    if (attemptGen != _boundaryAttemptGen) { superseded = true; break; }
                    bool loaded = false;
                    try
                    {
                        // `currentLevelID == mapId` IS the settling test —
                        // currentLevelID and currentMap advance atomically in
                        // OnLevelFinishedLoading (r4 blocker 1 corrected r3's
                        // model: Map.levelID is a readiness token, NOT scene
                        // identity, and never equals the new map's id).
                        var mmr = MapManager.instance;
                        var cmr = mmr != null ? mmr.currentMap : null;
                        loaded = mmr != null && mmr.currentLevelID == mapId
                                 && cmr != null && cmr.Map != null;
                    }
                    catch { }
                    if (loaded) { ok = true; break; }
                    // 0.75s grace, not 8 (Aug 10 r2 find 3): the missed-load
                    // window is when the master's live instantiates arrive
                    // against a null local map — every second here is a
                    // second of deferred PhotonMapObject starts. The grace
                    // only exists so an in-flight vanilla load RPC (queued in
                    // the same dispatch as the call-in) can land first.
                    if (!triedLocalLoad && Time.unscaledTime - t0 > 0.75f)
                    {
                        triedLocalLoad = true;
                        try
                        {
                            var mm = MapManager.instance;
                            if (mm != null && mm.levels != null && mapId >= 0 && mapId < mm.levels.Length)
                            {
                                // NEVER fallback-load while ANY load is in
                                // flight (r5 blocker 1: a stale boundary's
                                // fallback would queue its OLD map behind the
                                // newer command). The serializer gate makes a
                                // duplicate same-scene call harmless, but a
                                // stale different-scene call must not even
                                // reach the queue.
                                if (MapLoadInFlight
                                    || string.Equals(LastCommandedScene, mm.levels[mapId], StringComparison.Ordinal))
                                {
                                    Plugin.Log?.LogInfo($"[SPECTATE] map {mapId} — a load is in flight, waiting");
                                }
                                else
                                {
                                    Plugin.Log?.LogInfo($"[SPECTATE] map {mapId} missing locally — direct local load");
                                    mm.RPCA_LoadLevel(mm.levels[mapId]);
                                }
                            }
                        }
                        catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] local map load: {ex.Message}"); }
                    }
                    yield return null;
                }
                if (superseded) yield break;
                if (!ok)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] boundary map {mapId} never loaded locally");
                    yield break;
                }

                // Local vanilla readiness (r3 find 3): LoadedForAll() reads a
                // scalar fed by the FIGHTERS' load reports. If we joined
                // after those unbuffered RPCs (or direct-loaded), the scalar
                // is stale, Map.StartMatch never runs, placeholders are never
                // swapped and live clones stay kinematic. Mirror the value
                // LOCALLY — no network op (our own report stays suppressed);
                // later fighter reports overwrite it consistently.
                // Readiness is pinned to the settled map's own token (the
                // shared helper — r5 find 2 moved ownership of the scalar
                // fully to the spectator: inbound fighter reports are now
                // suppressed, so nothing can overwrite this with a token
                // from a different load lineage).
                PinLocalMapReadiness($"boundary {mapId}");

                // 2. Fresh snapshot for THIS boundary (retry once).
                ok = false;
                for (int attempt = 0; attempt < 2 && !ok; attempt++)
                {
                    int seq = ++_seq;
                    _awaitBoundarySeq = seq;
                    _boundaryResponse = null;
                    SendRequest(seq);
                    float t1 = Time.unscaledTime;
                    while (Time.unscaledTime - t1 < 8f)
                    {
                        if (gen != _boundaryGeneration) yield break;
                        if (attemptGen != _boundaryAttemptGen) { superseded = true; break; }
                        if (_boundaryResponse != null) { ok = true; break; }
                        yield return null;
                    }
                    if (superseded) break;
                }
                if (superseded) yield break;
                if (!ok)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] no boundary snapshot — staying dark until next boundary");
                    yield break;
                }

                var snap = _boundaryResponse;
                _boundaryResponse = null;
                _awaitBoundarySeq = -1;

                // 3. The response must describe the map we are entering — a
                // stale answer must not gate THIS boundary's decks.
                int snapLevel = (int)snap[5];
                if (snapLevel != mapId)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] snapshot level {snapLevel} != boundary {mapId} — skipped");
                    yield break;
                }

                // 4. ALL roster bodies must exist BEFORE decks are applied
                // (Codex r1 find 9: a body that appears after the apply pass
                // would activate with default stats).
                var actors = (int[])snap[6];
                float t2 = Time.unscaledTime;
                bool bodies = false;
                while (Time.unscaledTime - t2 < 8f)
                {
                    if (gen != _boundaryGeneration) yield break;
                    if (attemptGen != _boundaryAttemptGen) { superseded = true; break; }
                    bodies = AllBodiesPresent(actors);
                    if (bodies) break;
                    yield return null;
                }
                if (superseded) yield break;
                if (!bodies)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] fighter bodies missing at boundary — staying dark");
                    yield break;
                }

                // 5. FFA score seed: REMOVED (Aug 11 review r3 find 2). Every
                // accepted snapshot — including this boundary response — is
                // seeded at receipt in the response parser; re-applying THIS
                // (by now up to 8s old, having waited for bodies) snapshot
                // here could overwrite a newer round delta wholesale, and a
                // terminal round has no later boundary to heal that.

                // 6. Rematch epoch: a changed epoch forces full reset+replay.
                int epoch = 0;
                try { epoch = Convert.ToInt32(snap[15]); } catch { }
                bool forceReset = _lastSeenEpoch != int.MinValue && epoch != _lastSeenEpoch;

                // 7. Apply decks, ALL-OR-NOTHING with post-verification.
                applied = true;
                _lastApplyOk = false;
                yield return ApplyDecks(snap, gen, attemptGen, forceReset);
                if (gen != _boundaryGeneration) yield break;
                if (attemptGen != _boundaryAttemptGen) { superseded = true; yield break; }
                if (!_lastApplyOk)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] deck reconstruction failed — staying dark");
                    yield break;
                }
                _lastSeenEpoch = epoch;

                if (CurrentStage == Stage.Applying)
                {
                    bool firstActivation = prior != Stage.Active;
                    CurrentStage = Stage.Active;
                    HasEverActivated = true;
                    _boundaryFailStreak = 0;
                    _deckFailStreak = 0;

                    // Seed the GM's own score fields from the snapshot
                    // (playtest #2c: the vanilla crown reads gm.p1Rounds/
                    // p1Points directly and saw an eternal 0-0). GM modes
                    // only; FFA has no 2-team crown.
                    try
                    {
                        var mode0 = snap[2] as string ?? "";
                        var sr = snap[11] as int[];
                        var sp = snap[12] as int[];
                        var gm = GM_ArmsRace.instance;
                        if (mode0 != "ffa" && gm != null && sr != null && sp != null)
                        {
                            gm.p1Rounds = sr.Length > 0 ? sr[0] : 0;
                            gm.p2Rounds = sr.Length > 1 ? sr[1] : 0;
                            gm.p1Points = sp.Length > 0 ? sp[0] : 0;
                            gm.p2Points = sp.Length > 1 ? sp[1] : 0;
                            // Crown init (Codex r5 find 3) — see the observe
                            // patch for why this must be called explicitly.
                            try { UnityEngine.Object.FindObjectOfType<GameCrownHandler>()?.PointOver(); } catch { }
                        }
                    }
                    catch { }

                    // Cosmetic start hooks (playtest #2a): the fighter flow
                    // runs these from OnMatchStarted/round starts, both
                    // suppressed here — and the spectator quiesce used to
                    // TEAR THEM DOWN via OnMatchEnd. All three are read-side
                    // walks (DelayedApplyAll/DelayedAttachAll apply REMOTE
                    // props to bodies; local publishes are spectator-guarded
                    // inside the publishers). Re-run at every boundary — the
                    // fighter flow re-runs them per round for the same
                    // reason (respawned bodies lose sprite tints).
                    try { PlayerColorCosmetic.OnMatchStart(); } catch { }
                    try { PlayerEffectCosmetic.OnMatchStart(); } catch { }
                    try { TrailCosmetic.OnMatchStart(); } catch { }

                    if (firstActivation)
                    {
                        Plugin.Log?.LogInfo("[SPECTATE] ACTIVE — rendering from this battle");
                        try { CompetitiveUI.ShowNotification(I18n.Tr("Now spectating."), Color.green, 4f); } catch { }
                    }
                }
            }
            finally
            {
                if (gen == _boundaryGeneration && CurrentStage == Stage.Applying)
                {
                    if (superseded)
                    {
                        // Superseded is NOT failed (r3 find 4): a newer
                        // boundary owns the reconcile now — restore the prior
                        // stage so its attempt can start, and count nothing
                        // (three fast points during deck applies must never
                        // read as a build mismatch).
                        CurrentStage = prior;
                    }
                    else
                    {
                        // FAILED attempt: NEVER restore Active (Codex r2 find
                        // 8 — a failed rematch reconstruction was re-exposing
                        // mixed old/new decks). Back to the blackout; the
                        // next boundary (or the leave below) resolves it.
                        CurrentStage = Stage.Synchronizing;
                        _boundaryFailStreak++;
                        if (applied && !_lastApplyOk) _deckFailStreak++;
                        if (_deckFailStreak >= 3)
                        {
                            // Repeated DECK failures = build mismatch
                            // (unknown cards, mod skew) — unrecoverable;
                            // map/snapshot timeouts keep retrying instead.
                            Plugin.Log?.LogWarning("[SPECTATE] three failed deck reconstructions — leaving");
                            LeaveToMenu("deck reconstruction failed");
                        }
                    }
                }
                // A boundary observed while THIS attempt was applying is
                // re-issued now (r2 find 4) through the SIDE-EFFECT-FREE
                // scheduler (r3 find 7: re-entering OnCallInObserved cleared
                // a newer round latch and re-disarmed the quarantine).
                if (gen == _boundaryGeneration && _pendingBoundaryMapId >= 0
                    && SpectatorSession.IsLocalSpectator)
                {
                    int next = _pendingBoundaryMapId;
                    _pendingBoundaryMapId = -1;
                    Plugin.Log?.LogInfo($"[SPECTATE] re-issuing boundary {next} deferred during apply");
                    ScheduleBoundary(next);
                }
            }
        }

        private static bool AllBodiesPresent(int[] actors)
        {
            try
            {
                if (actors == null) return false;
                for (int i = 0; i < actors.Length; i++)
                    if (FindBodyByActor(actors[i]) == null) return false;
                return true;
            }
            catch { return false; }
        }

        private static bool ActorDeparted(int actorNumber)
        {
            try
            {
                var room = PhotonNetwork.CurrentRoom;
                return room == null || room.GetPlayer(actorNumber) == null;
            }
            catch { return false; }
        }

        private static Player FindBodyByActor(int actorNumber)
        {
            try
            {
                var players = PlayerManager.instance?.players;
                if (players == null) return null;
                for (int i = 0; i < players.Count; i++)
                {
                    var p = players[i];
                    if (p == null || p.data == null || p.data.view == null) continue;
                    var owner = p.data.view.Owner;
                    if (owner != null && owner.ActorNumber == actorNumber) return p;
                }
            }
            catch { }
            return null;
        }

        // ── deck application ─────────────────────────────────────────────

        // Set by ApplyDecks before it finishes: true only when every fighter's
        // verified deck matches the snapshot exactly (iterators cannot return
        // values; the generation guard keeps stale writers out).
        private static bool _lastApplyOk;

        /// <summary>The body's CURRENT applied deck, read from vanilla state
        /// (Codex r1 find 10): on a spectator client, currentCards is fed by
        /// exactly two writers — live vanilla RPCA_Pick applies and our own
        /// replay — so it IS the ground truth, where a private bookkeeping
        /// list silently misses the live picks and double-applies them.</summary>
        private static List<string> CurrentDeckNames(Player body)
        {
            var names = new List<string>();
            try
            {
                var cards = body.data?.currentCards;
                if (cards == null) return names;
                int skip = TabStatsOverlay.CardBaselineFor(body);
                for (int i = skip; i < cards.Count; i++)
                    if (cards[i] != null) names.Add(cards[i].gameObject.name);
            }
            catch { }
            return names;
        }

        private static IEnumerator ApplyDecks(object[] snap, int gen, int attemptGen, bool forceReset)
        {
            _lastApplyOk = false;
            int[] actors; string[] decksFlat; int[] offsets;
            try
            {
                actors = (int[])snap[6];
                decksFlat = (string[])snap[13];
                offsets = (int[])snap[14];
                if (actors == null || decksFlat == null || offsets == null || offsets.Length != actors.Length + 1)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] malformed deck slices — skipping apply");
                    yield break;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[SPECTATE] deck parse: {ex.Message}");
                yield break;
            }

            // PRE-RESOLVE the full manifest (Codex r1 find 9): an unknown
            // card anywhere = build mismatch = the whole boundary fails
            // BEFORE any body is touched. No partial decks, ever.
            for (int k = 0; k < decksFlat.Length; k++)
            {
                if (!string.IsNullOrEmpty(decksFlat[k]) && ResolveCard(decksFlat[k]) == null)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] unknown card '{decksFlat[k]}' — build mismatch, no decks applied");
                    yield break;
                }
            }

            // PRE-SCAN for a GLOBAL reset (playtest #169e): the vanilla card
            // bars are per-TEAM, and nothing on a spectator ever clears them
            // (the clearing lives in the suppressed GM lifecycle) — so a
            // rematch stacked game-2 replays on top of game-1's bar (orange
            // showed 8 cards). When ANY body needs a reset, reset ALL bodies
            // and clear the bars first; each OFFLINE_Pick replay then rebuilds
            // the bars to exactly the verified decks. Per-body resets with
            // per-team bars cannot be correct in team modes (clearing a bar
            // for body B wipes teammate A's just-replayed entries).
            bool globalReset = forceReset;
            if (!globalReset)
            {
                for (int i = 0; i < actors.Length && !globalReset; i++)
                {
                    var body0 = FindBodyByActor(actors[i]);
                    if (body0 == null) continue;
                    var have0 = CurrentDeckNames(body0);
                    int cnt = 0;
                    for (int k = offsets[i]; k < offsets[i + 1] && k < decksFlat.Length; k++)
                        if (!string.IsNullOrEmpty(decksFlat[k])) cnt++;
                    if (cnt < have0.Count) { globalReset = true; break; }
                    int idx = offsets[i];
                    for (int k = 0; k < have0.Count; k++)
                    {
                        while (idx < offsets[i + 1] && string.IsNullOrEmpty(decksFlat[idx])) idx++;
                        if (idx >= offsets[i + 1]
                            || !string.Equals(have0[k], decksFlat[idx], StringComparison.Ordinal))
                        { globalReset = true; break; }
                        idx++;
                    }
                }
            }
            // COMMIT POINT (r4 find 2 + r5 find 6): supersession is honored
            // up to here and NOT past it — the bar clear below is the FIRST
            // visible mutation, so the check must precede it (a stale
            // attempt that cleared bars and then bailed left them empty if
            // the successor boundary failed).
            if (attemptGen != _boundaryAttemptGen) yield break;

            if (globalReset)
            {
                try
                {
                    var bars = CardBarHandler.instance != null ? CardBarHandler.instance.cardBars : null;
                    if (bars != null)
                        for (int b = 0; b < bars.Length; b++)
                            try { bars[b].ClearBar(); } catch { }
                }
                catch { }
            }

            for (int i = 0; i < actors.Length; i++)
            {
                if (gen != _boundaryGeneration) yield break;
                int actor = actors[i];
                var body = FindBodyByActor(actor);
                if (body == null)
                {
                    // Bodies were verified present before this ran. If the
                    // ACTOR left the room mid-manifest (r5 find 5: routine in
                    // FFA), skip them and keep applying the survivors —
                    // aborting left every later actor on a stale deck. A
                    // still-connected actor with no body remains a hard fail.
                    bool actorPresent = false;
                    try
                    {
                        var room = PhotonNetwork.CurrentRoom;
                        actorPresent = room != null && room.GetPlayer(actor) != null;
                    }
                    catch { }
                    if (!actorPresent)
                    {
                        Plugin.Log?.LogInfo($"[SPECTATE] actor {actor} left mid-apply — skipping their deck");
                        continue;
                    }
                    Plugin.Log?.LogWarning($"[SPECTATE] body for actor {actor} vanished mid-apply");
                    yield break;
                }

                var target = new List<string>();
                for (int k = offsets[i]; k < offsets[i + 1] && k < decksFlat.Length; k++)
                    if (!string.IsNullOrEmpty(decksFlat[k])) target.Add(decksFlat[k]);

                var have = CurrentDeckNames(body);

                bool isExtension = !globalReset && target.Count >= have.Count;
                if (isExtension)
                {
                    for (int k = 0; k < have.Count; k++)
                        if (!string.Equals(have[k], target[k], StringComparison.Ordinal)) { isExtension = false; break; }
                }

                bool applyFailed = false;
                if (isExtension)
                {
                    for (int k = have.Count; k < target.Count; k++)
                    {
                        if (gen != _boundaryGeneration) yield break;
                        if (!ApplyOne(body, actor, target[k])) { applyFailed = true; break; }
                        // #225: NEVER two applies in one frame — 16 vanilla
                        // cards self-destruct when two copies apply same-frame.
                        yield return null;
                    }
                }
                else
                {
                    // Deck shrank/reordered (FFA roll-off) or epoch changed
                    // (rematch): full reset+replay with residue restore (#211).
                    yield return ResetAndReplay(body, actor, target, gen);
                    if (gen != _boundaryGeneration) yield break;
                }

                // An actor who LEFT the room during their own multi-frame
                // apply must not abort the manifest for everyone after them
                // (r6 find 4 — the pre-turn skip only covered departures
                // BEFORE the iteration). Departed = skip; still-connected
                // failures stay hard.
                if (applyFailed)
                {
                    if (ActorDeparted(actor))
                    {
                        Plugin.Log?.LogInfo($"[SPECTATE] actor {actor} left during their deck apply — skipping");
                        continue;
                    }
                    yield break;
                }

                // VERIFY (r1 find 9): the body's rendered deck must now equal
                // the snapshot exactly, in order.
                var now = CurrentDeckNames(body);
                bool match = now.Count == target.Count;
                if (match)
                    for (int k = 0; k < now.Count; k++)
                        if (!string.Equals(now[k], target[k], StringComparison.Ordinal)) { match = false; break; }
                if (!match)
                {
                    if (ActorDeparted(actor))
                    {
                        Plugin.Log?.LogInfo($"[SPECTATE] actor {actor} left before deck verify — skipping");
                        continue;
                    }
                    Plugin.Log?.LogWarning($"[SPECTATE] deck verify failed for actor {actor} " +
                                           $"(have {now.Count}, want {target.Count})");
                    yield break;
                }
            }
            _lastApplyOk = true;
        }

        private static bool ApplyOne(Player body, int actor, string cardName)
        {
            try
            {
                var prefab = ResolveCard(cardName);
                if (prefab == null)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] unknown card '{cardName}' for actor {actor}");
                    return false;
                }
                if (!_residue.ContainsKey(actor)) CaptureResidue(body, actor);
                FfaMode.SpectatorApplyCard(body, prefab);
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[SPECTATE] apply '{cardName}': {ex.Message}");
                return false;
            }
        }

        private static CardInfo ResolveCard(string cardName)
        {
            try
            {
                var cards = CardChoice.instance?.cards;
                if (cards == null) return null;
                foreach (var c in cards)
                    if (c != null && c.gameObject.name == cardName) return c;
            }
            catch { }
            return null;
        }

        private static void CaptureResidue(Player body, int actor)
        {
            var r = new Residue();
            try
            {
                try { var g = body.GetComponent<Gravity>(); if (g != null) r.gravityForce = g.gravityForce; } catch { }
                try { var hh = body.GetComponent<HealthHandler>(); if (hh != null) r.regeneration = hh.regeneration; } catch { }
                try { var cd = body.GetComponent<CharacterData>(); if (cd != null) r.jumps = cd.jumps; } catch { }
                try
                {
                    var holding = body.data.GetComponent<Holding>();
                    var gun = holding != null && holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                    if (gun != null)
                    {
                        var ammo = gun.GetComponentInChildren<GunAmmo>();
                        if (ammo != null) r.ammoReg = ammo.ammoReg;
                        if (gun.projectiles != null && gun.projectiles.Length > 0)
                            r.projectile = gun.projectiles[0].objectToSpawn;
                    }
                }
                catch { }
                r.captured = true;
            }
            catch { }
            _residue[actor] = r;
        }

        /// <summary>The #211 pattern, spectator-local: FullReset + residue
        /// restore + currentCards clear + one teardown frame + zombie scrub,
        /// then frame-yielding replay. Mirrors FfaMode.RollingResetAndReplay
        /// (kept separate: that one is entangled with FFA's own baseline and
        /// card-bar state, and cross-mode state sharing is how stale-slot
        /// bugs happen, #149).</summary>
        /// <summary>The SYNCHRONOUS half of a card reset: vanilla FullReset,
        /// the #211 residue fields FullReset does not restore, the currentCards
        /// clear vanilla never does (#138), and the Tab-board baseline. Shared
        /// by the boundary replay and by the between-games flush (item 9a) so
        /// the two can never drift — a body reset by one is in exactly the
        /// state the other expects.</summary>
        private static void ResetBodyToVanilla(Player body, int actor)
        {
            try
            {
                body.FullReset();
                Residue r;
                if (_residue.TryGetValue(actor, out r) && r.captured)
                {
                    try { var g = body.GetComponent<Gravity>(); if (g != null) g.gravityForce = r.gravityForce; } catch { }
                    try { var hh = body.GetComponent<HealthHandler>(); if (hh != null) hh.regeneration = r.regeneration; } catch { }
                    try { var cd = body.GetComponent<CharacterData>(); if (cd != null) cd.jumps = r.jumps; } catch { }
                    try
                    {
                        var holding = body.data.GetComponent<Holding>();
                        var gun = holding != null && holding.holdable != null ? holding.holdable.GetComponent<Gun>() : null;
                        if (gun != null)
                        {
                            var ammo = gun.GetComponentInChildren<GunAmmo>();
                            if (ammo != null) ammo.ammoReg = r.ammoReg;
                            if (gun.projectiles != null && gun.projectiles.Length > 0)
                                gun.projectiles[0].objectToSpawn = r.projectile;
                            gun.dontAllowAutoFire = false;
                        }
                    }
                    catch { }
                }
                try { body.data.currentCards.Clear(); } catch { }
                try { TabStatsOverlay.RecordCardBaseline(body); } catch { }
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] reset actor {actor}: {ex.Message}"); }
        }

        private static IEnumerator ResetAndReplay(Player body, int actor, List<string> target, int gen)
        {
            ResetBodyToVanilla(body, actor);

            // One frame for ResetStats' Object.Destroy teardown (#278: Destroy
            // is END-OF-FRAME; a same-frame scrub sees everything still alive
            // and cleans nothing), then the #92/#103 zombie/ChildRPC sweep.
            yield return null;
            if (gen != _boundaryGeneration) yield break;
            try { GMArmsRaceStartGameBlockResetPatch.RunSweep("spectator deck reset"); } catch { }

            foreach (var name in target)
            {
                if (gen != _boundaryGeneration) yield break;
                if (!ApplyOne(body, actor, name)) yield break;   // all-or-nothing; caller verifies
                yield return null;   // #225
            }
        }

        // ── event dispatch ───────────────────────────────────────────────

        private static void OnEvent(EventData e)
        {
            try
            {
                if (e.Code == EVT_REQUEST) HandleRequest(e);
                else if (e.Code == EVT_SNAPSHOT) HandleSnapshot(e);
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] event handler: {ex.Message}"); }
        }

        // ── master side: answer snapshot requests ────────────────────────

        // Master-side spectator admission state (Codex r1 find 3): an actor
        // may claim the role, but it gets STATE only after the server has
        // validated its lease. ActorNumber -> last server confirmation time;
        // reset on room change. A validation is a PERISHABLE fact (r2 find
        // 7): revalidation runs every 60s, and a verdict older than the TTL
        // means the server stopped confirming (revoked lease, transport
        // dead) — the seat closes rather than persisting forever.
        private static readonly Dictionary<int, float> _validatedAt = new Dictionary<int, float>();
        private static readonly Dictionary<int, float> _spectatorFirstSeen = new Dictionary<int, float>();
        private static readonly Dictionary<int, float> _lastAnswerAt = new Dictionary<int, float>();
        private const float VALIDATION_TTL_SECONDS = 300f;   // 5 missed revalidations

        internal static void MasterResetSpectatorState()
        {
            _validatedAt.Clear();
            _spectatorFirstSeen.Clear();
            _lastAnswerAt.Clear();
        }

        /// <summary>ApiClient's validate parse reports each verdict here.</summary>
        internal static void MasterNoteValidated(int actorNumber, bool ok)
        {
            if (ok) _validatedAt[actorNumber] = Time.unscaledTime;
            else _validatedAt.Remove(actorNumber);
        }

        private static bool IsValidatedFresh(int actorNumber)
        {
            float at;
            return _validatedAt.TryGetValue(actorNumber, out at)
                   && Time.unscaledTime - at < VALIDATION_TTL_SECONDS;
        }

        /// <summary>Master notes a spectator actor the moment it ENTERS (Aug
        /// 10 r2 find 9: seeding first-seen only from the sweep stretched the
        /// never-validated eviction to 120-180s; seeded at entry, the 90s
        /// deadline is real again). Also the entry-time protocol gate (r2
        /// blocker 2): an actor whose cr_spec VALUE is not the supported
        /// protocol is closed immediately — presence-based classification
        /// keeps it a spectator (suppressed everywhere) until the close
        /// lands.</summary>
        internal static void MasterNoteSpectatorEntered(Photon.Realtime.Player sp)
        {
            try
            {
                if (sp == null || !PhotonNetwork.IsMasterClient) return;
                if (SpectatorSession.IsLocalSpectator) return;
                int a = sp.ActorNumber;
                if (!_spectatorFirstSeen.ContainsKey(a))
                    _spectatorFirstSeen[a] = Time.unscaledTime;
                int proto = RoomActors.SpectatorProtocolOf(sp);
                if (proto != SpectatorSession.PROTOCOL)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] close requested for spectator actor {a} — incompatible protocol {proto} (need {SpectatorSession.PROTOCOL}; cooperative)");
                    RoomActors.CooperativeClose(sp);
                }
            }
            catch { }
        }

        /// <summary>Kick spectator actors that never validated, or whose
        /// validation went stale (fail CLOSED — a seat the server no longer
        /// confirms is not a seat). Called from the fighter-side ticker.</summary>
        internal static void MasterSweepUnvalidated()
        {
            try
            {
                if (!PhotonNetwork.InRoom || !PhotonNetwork.IsMasterClient) return;
                if (SpectatorSession.IsLocalSpectator) return;
                // Unauthorized non-spectator actors are re-closed on this
                // cadence too (r9 find 4: a close issued during a master
                // handoff window is rejected by the target as coming from a
                // non-master — the sweep is the retry, and a NEW master runs
                // it within one cadence).
                try
                {
                    var all = PhotonNetwork.PlayerList;
                    if (all != null && RoomActors.RosterFrozen)
                    {
                        for (int i = 0; i < all.Length; i++)
                        {
                            var a0 = all[i];
                            if (a0 == null || a0.IsLocal) continue;
                            if (RoomActors.IsSpectator(a0)) continue;
                            if (!RoomActors.IsUnauthorized(a0)) continue;
                            RoomActors.RecordRejected(a0);
                            Plugin.Log?.LogWarning($"[SPECTATE] close requested for unauthorized actor {a0.ActorNumber} (sweep, cooperative)");
                            RoomActors.CooperativeClose(a0);
                        }
                    }
                }
                catch { }
                foreach (var sp in RoomActors.Spectators())
                {
                    int a = sp.ActorNumber;
                    // Wrong-protocol seats close regardless of validation
                    // state (r2 blocker 2 backstop — the entry hook covers
                    // the normal path; this catches a master handoff where
                    // the new master never saw the entry).
                    if (RoomActors.SpectatorProtocolOf(sp) != SpectatorSession.PROTOCOL)
                    {
                        Plugin.Log?.LogWarning($"[SPECTATE] close requested for incompatible-protocol spectator actor {a} (cooperative)");
                        RoomActors.CooperativeClose(sp);
                        _spectatorFirstSeen.Remove(a);
                        _validatedAt.Remove(a);
                        continue;
                    }
                    if (IsValidatedFresh(a)) continue;
                    bool wasValidated = _validatedAt.ContainsKey(a);
                    float first;
                    if (!wasValidated && !_spectatorFirstSeen.TryGetValue(a, out first))
                    {
                        _spectatorFirstSeen[a] = Time.unscaledTime;
                        continue;
                    }
                    bool overdue = wasValidated
                        || Time.unscaledTime - _spectatorFirstSeen[a] > 90f;
                    if (overdue)
                    {
                        Plugin.Log?.LogWarning($"[SPECTATE] close requested for {(wasValidated ? "stale-validated" : "never-validated")} spectator actor {a} (cooperative)");
                        RoomActors.CooperativeClose(sp);
                        _spectatorFirstSeen.Remove(a);
                        _validatedAt.Remove(a);
                    }
                }
            }
            catch { }
        }

        private static void HandleRequest(EventData e)
        {
            if (!PhotonNetwork.InRoom || !PhotonNetwork.IsMasterClient) return;
            if (SpectatorSession.IsLocalSpectator) return;   // a spectator-master answers nothing
            var a = e.CustomData as object[];
            if (a == null || a.Length < 2) return;
            if (!(a[0] is byte) || (byte)a[0] != SpectatorSession.PROTOCOL) return;
            int seq;
            try { seq = (int)a[1]; } catch { return; }

            // Only classified spectators are answered. The classification is
            // the pre-join property (immutable, #287) — an unauthorized actor
            // gets silence, not state.
            Photon.Realtime.Player sender = null;
            try { sender = PhotonNetwork.CurrentRoom.GetPlayer(e.Sender); } catch { }
            if (sender == null || !RoomActors.IsSpectator(sender)) return;

            // VALIDATED actors only (r1 find 3), and only while the server
            // keeps confirming (r2 find 7). The requester's own retry loop
            // absorbs the validation round-trip (~2s).
            if (!IsValidatedFresh(e.Sender)) return;

            // Per-sender answer throttle: a request flood must not turn the
            // master into a snapshot factory (r1 find 3, spam arm).
            float last;
            if (_lastAnswerAt.TryGetValue(e.Sender, out last)
                && Time.unscaledTime - last < 2f) return;
            _lastAnswerAt[e.Sender] = Time.unscaledTime;

            var snap = BuildSnapshot(seq);
            if (snap == null) return;
            try
            {
                PhotonNetwork.RaiseEvent(
                    EVT_SNAPSHOT, snap,
                    new RaiseEventOptions { TargetActors = new[] { e.Sender } },
                    SendOptions.SendReliable);
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] snapshot send: {ex.Message}"); }
        }

        private static object[] BuildSnapshot(int seq)
        {
            try
            {
                string room = PhotonNetwork.CurrentRoom?.Name ?? "";
                string mode = ModeFromRoom(room);
                if (mode == "") return null;   // not a mode we snapshot

                bool battle = false;
                try { battle = GameManager.instance != null && GameManager.instance.battleOngoing; } catch { }
                string phase = battle ? "battle" : "transition";

                string scene = "";
                int levelId = -1;
                try
                {
                    var mm = MapManager.instance;
                    if (mm != null)
                    {
                        levelId = mm.currentLevelID;
                        if (levelId >= 0 && mm.levels != null && levelId < mm.levels.Length)
                            scene = mm.levels[levelId] ?? "";
                    }
                }
                catch { }

                var fighters = RoomActors.ActiveFighters();
                int n = fighters.Length;
                var actors = new int[n];
                var steamIds = new string[n];
                var playerIds = new int[n];
                var teamIds = new int[n];
                var names = new string[n];
                var decks = new List<string>();
                var offsets = new int[n + 1];

                for (int i = 0; i < n; i++)
                {
                    var f = fighters[i];
                    actors[i] = f.ActorNumber;
                    steamIds[i] = RoomActors.SteamIdOf(f);
                    names[i] = f.NickName ?? "";
                    playerIds[i] = -1;
                    teamIds[i] = -1;
                    offsets[i] = decks.Count;
                    var body = FindBodyByActor(f.ActorNumber);
                    if (body != null)
                    {
                        playerIds[i] = body.PlayerID;
                        teamIds[i] = body.TeamID;
                        AppendCurrentDeck(decks, body, mode);
                    }
                }
                offsets[n] = decks.Count;

                // Scores by TeamID. GM modes: two teams from GM fields. FFA:
                // one team per fighter, FfaMode's tables.
                int maxTeam = 1;
                for (int i = 0; i < n; i++) if (teamIds[i] > maxTeam) maxTeam = teamIds[i];
                var scoreRounds = new int[maxTeam + 1];
                var scorePoints = new int[maxTeam + 1];
                if (mode == "ffa")
                {
                    for (int t = 0; t <= maxTeam; t++)
                    {
                        scoreRounds[t] = FfaMode.RoundsFor(t);
                        scorePoints[t] = FfaMode.PointsFor(t);
                    }
                }
                else
                {
                    try
                    {
                        var gm = GM_ArmsRace.instance;
                        if (gm != null)
                        {
                            scoreRounds[0] = gm.p1Rounds;
                            scorePoints[0] = gm.p1Points;
                            if (maxTeam >= 1) { scoreRounds[1] = gm.p2Rounds; scorePoints[1] = gm.p2Points; }
                        }
                    }
                    catch { }
                }

                // Session series tally, fighter-array order (item 3 / Aug 10
                // find 11): STRICT 1v1 with exactly two identified fighters
                // only — every other shape sends -1 sentinels the client
                // treats as "hide the line". Values come from the master's
                // room-scoped counters (fed only by local game-over outcomes,
                // reset only on room join — never from report callbacks).
                int sw0 = -1, sw1 = -1;
                try
                {
                    if (mode == "1v1" && n == 2)
                    {
                        string mySid = "";
                        try { mySid = MatchTracker.LocalSteamId ?? ""; } catch { }
                        int myIdx = !string.IsNullOrEmpty(mySid) && steamIds[0] == mySid ? 0
                                  : !string.IsNullOrEmpty(mySid) && steamIds[1] == mySid ? 1 : -1;
                        if (myIdx >= 0)
                        {
                            int w = GameStateWatcher.RoomSeriesWinsLocal;
                            int l = GameStateWatcher.RoomSeriesLossesLocal;
                            sw0 = myIdx == 0 ? w : l;
                            sw1 = myIdx == 0 ? l : w;
                        }
                    }
                }
                catch { }

                return new object[]
                {
                    (byte)SpectatorSession.PROTOCOL, seq, mode, phase, scene, levelId,
                    actors, steamIds, playerIds, teamIds, names,
                    scoreRounds, scorePoints,
                    decks.ToArray(), offsets,
                    // Game epoch: bumps at every game-over on this client, so
                    // a rematch reset is visible to the spectator as a value
                    // change (Codex r1 find 11). Only CHANGE matters — a
                    // master handoff shifting the absolute value just costs
                    // one redundant reset+replay.
                    GameStateWatcher.SessionMatchCountValue,
                    sw0, sw1
                };
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[SPECTATE] BuildSnapshot: {ex.Message}");
                return null;
            }
        }

        private static void AppendCurrentDeck(List<string> sink, Player body, string mode)
        {
            try
            {
                if (mode == "ffa")
                {
                    // FFA rolling decks: FfaMode's authoritative list is the
                    // ground truth (currentCards accumulates removed cards).
                    var names = FfaMode.SpectatorDeckNames(body.PlayerID);
                    if (names != null) { sink.AddRange(names); return; }
                }
                // GM modes: currentCards minus the rematch baseline (#138 —
                // vanilla never clears the list across rematches).
                var cards = body.data?.currentCards;
                if (cards == null) return;
                int skip = TabStatsOverlay.CardBaselineFor(body);
                for (int i = skip; i < cards.Count; i++)
                    if (cards[i] != null) sink.Add(cards[i].gameObject.name);
            }
            catch { }
        }

        private static string ModeFromRoom(string room)
        {
            if (string.IsNullOrEmpty(room)) return "";
            if (room.StartsWith("ranked_")) return "1v1";
            if (room.StartsWith("team_")) return "2v2";
            if (room.StartsWith("ovt_")) return "1v2";
            if (room.StartsWith("ffa_")) return "ffa";
            // Private/code RANKED 1v1s are in scope (Sid, Aug 7) — the same
            // predicate the attest ticker uses, so the master answers
            // snapshots exactly where fighters attest. sct- tournament rooms
            // stay out of scope end-to-end (Codex r2 find 19).
            try { if (GameStateWatcher.RankedCodeRoom1v1InProgress) return "1v1"; } catch { }
            return "";
        }

        // ── spectator side: consume snapshots ────────────────────────────

        private static void HandleSnapshot(EventData e)
        {
            if (!SpectatorSession.IsLocalSpectator) return;
            var a = e.CustomData as object[];
            if (a == null || a.Length < 16) return;
            if (!(a[0] is byte) || (byte)a[0] != SpectatorSession.PROTOCOL) return;

            // Only the CURRENT master may describe the match to us.
            try
            {
                var m = PhotonNetwork.MasterClient;
                if (m == null || m.ActorNumber != e.Sender) return;
            }
            catch { return; }

            int seq;
            try { seq = (int)a[1]; } catch { return; }

            try
            {
                WatchedMode = a[2] as string ?? "";
                WatchedPhase = a[3] as string ?? "";
                FighterNames = a[10] as string[] ?? new string[0];
                FighterTeams = a[9] as int[] ?? new int[0];
                FighterSteamIds = a[7] as string[] ?? new string[0];

                // Score for the HUD (works for both HUD shapes: 1v1/2v2/1v2
                // uses team 0/1; FFA renders its own list from these arrays).
                var rounds = a[11] as int[];
                var points = a[12] as int[];
                if (rounds != null && rounds.Length >= 1)
                {
                    SpectatorViewState.RecordScore(
                        -1,
                        points != null && points.Length > 0 ? points[0] : 0,
                        points != null && points.Length > 1 ? points[1] : 0,
                        rounds.Length > 0 ? rounds[0] : 0,
                        rounds.Length > 1 ? rounds[1] : 0);
                }
                // Aug 11 review r2 find 1: seed FFA's incremental score
                // tables from EVERY accepted snapshot, not only the boundary
                // apply — a spectator joining during a game's FINAL battle
                // gets this immediate snapshot but no boundary before game
                // over, so SpectatorObserveRound's decisive-round detection
                // incremented from zero, missed the winner announcement and
                // left kills/pointsTotal unreset for the rematch. Same seed
                // as the boundary site; SpectatorSeedScores self-gates on
                // the spectator role and overwrites wholesale (idempotent).
                try
                {
                    if (WatchedMode == "ffa")
                        FfaMode.SpectatorSeedScores(rounds, points);
                }
                catch { }

                // Session series tally (item 3): CLEAR before parse (find 11 —
                // a newer master's values must not survive a later, shorter
                // snapshot from an older master), then accept only a strict
                // well-formed 1v1 payload.
                SpectatorViewState.RecordSessionSeries(-1, -1);
                try
                {
                    if (a.Length >= 18 && WatchedMode == "1v1")
                    {
                        int s0 = Convert.ToInt32(a[16]);
                        int s1 = Convert.ToInt32(a[17]);
                        var act = a[6] as int[];
                        if (s0 >= 0 && s1 >= 0 && act != null && act.Length == 2)
                            SpectatorViewState.RecordSessionSeries(s0, s1);
                    }
                }
                catch { }
                _haveInfo = true;

                if (seq == _awaitBoundarySeq)
                    _boundaryResponse = a;
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] snapshot parse: {ex.Message}"); }
        }
    }
}
