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
                CurrentStage = Stage.Synchronizing;
                _haveInfo = false;
                _awaitBoundarySeq = -1;
                _boundaryResponse = null;
                _boundaryGeneration++;
                _residue.Clear();
                _boundaryFailStreak = 0;
                _deckFailStreak = 0;
                _lastSeenEpoch = int.MinValue;
                SpectatorViewState.Reset();

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
            CurrentStage = Stage.None;
            _haveInfo = false;
            _awaitBoundarySeq = -1;
            _boundaryResponse = null;
            _boundaryGeneration++;         // kills every in-flight coroutine
            _residue.Clear();
            _boundaryFailStreak = 0;
            _deckFailStreak = 0;
            _lastSeenEpoch = int.MinValue;
            WatchedMode = "";
            WatchedPhase = "";
            FighterNames = new string[0];
            FighterTeams = new int[0];
            SpectatorViewState.Reset();
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
                // Cache-replay hygiene ONLY while dark (Codex r5): cards and
                // map pieces present during Synchronizing are stale replays;
                // anything spawning during Applying (the incoming map) or
                // Active (live picks) is real and must stay visible.
                if (CurrentStage == Stage.Synchronizing)
                {
                    try { SweepPreActivationCards(); } catch { }
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

        /// <summary>Bury every Photon card object in the scene. Called ONLY
        /// while Stage == Synchronizing (Codex r5 rework): the cached replay
        /// of past pick phases lands seconds after join — squarely inside
        /// Synchronizing — and gets buried by the loop's next tick; a LIVE
        /// pick phase only ever happens while Active, where this never runs,
        /// so spectators still watch real picks (playtest #2d). No id
        /// bookkeeping at all — ViewIDs recycle (r5 find 8), and "visible
        /// while Active, buried while dark" needs none.</summary>
        private static void SweepPreActivationCards()
        {
            var infos = UnityEngine.Object.FindObjectsOfType<CardInfo>();
            int hidden = 0;
            for (int i = 0; i < infos.Length; i++)
            {
                var ci = infos[i];
                if (ci == null || ci.gameObject == null) continue;
                if (!ci.gameObject.activeInHierarchy) continue;
                if (ci.GetComponent<PhotonView>() == null) continue;
                ci.gameObject.SetActive(false);
                hidden++;
            }
            if (hidden > 0)
                Plugin.Log?.LogInfo($"[SPECTATE] hid {hidden} cached card object(s)");
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
                var objs = UnityEngine.Object.FindObjectsOfType<PhotonMapObject>();
                int hidden = 0;
                for (int i = 0; i < objs.Length; i++)
                {
                    var o = objs[i];
                    if (o == null || o.gameObject == null) continue;
                    if (!o.gameObject.activeInHierarchy) continue;
                    o.gameObject.SetActive(false);
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
            if (CurrentStage == Stage.None || CurrentStage == Stage.Applying) return;
            if (Plugin.Instance == null) return;
            Plugin.Instance.StartCoroutine(BoundaryAttempt(mapId, _boundaryGeneration));
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

        private static IEnumerator BoundaryAttempt(int mapId, int gen)
        {
            var prior = CurrentStage;
            CurrentStage = Stage.Applying;
            bool ok = false;
            bool applied = false;
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
                    bool loaded = false;
                    try { loaded = MapManager.instance != null && MapManager.instance.currentLevelID == mapId; } catch { }
                    if (loaded) { ok = true; break; }
                    if (!triedLocalLoad && Time.unscaledTime - t0 > 8f)
                    {
                        triedLocalLoad = true;
                        try
                        {
                            var mm = MapManager.instance;
                            if (mm != null && mm.levels != null && mapId >= 0 && mapId < mm.levels.Length)
                            {
                                Plugin.Log?.LogInfo($"[SPECTATE] map {mapId} missing locally — direct local load");
                                mm.RPCA_LoadLevel(mm.levels[mapId]);
                            }
                        }
                        catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] local map load: {ex.Message}"); }
                    }
                    yield return null;
                }
                if (!ok)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] boundary map {mapId} never loaded locally");
                    yield break;
                }

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
                        if (_boundaryResponse != null) { ok = true; break; }
                        yield return null;
                    }
                }
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
                    bodies = AllBodiesPresent(actors);
                    if (bodies) break;
                    yield return null;
                }
                if (!bodies)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] fighter bodies missing at boundary — staying dark");
                    yield break;
                }

                // 5. FFA: seed FfaMode's incremental score tables from the
                // snapshot — a late joiner otherwise counts from zero forever.
                try
                {
                    if ((snap[2] as string) == "ffa")
                        FfaMode.SpectatorSeedScores(snap[11] as int[], snap[12] as int[]);
                }
                catch { }

                // 6. Rematch epoch: a changed epoch forces full reset+replay.
                int epoch = 0;
                try { epoch = Convert.ToInt32(snap[15]); } catch { }
                bool forceReset = _lastSeenEpoch != int.MinValue && epoch != _lastSeenEpoch;

                // 7. Apply decks, ALL-OR-NOTHING with post-verification.
                applied = true;
                _lastApplyOk = false;
                yield return ApplyDecks(snap, gen, forceReset);
                if (gen != _boundaryGeneration) yield break;
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
                    // FAILED attempt: NEVER restore Active (Codex r2 find 8 —
                    // a failed rematch reconstruction was re-exposing mixed
                    // old/new decks). Back to the blackout; the next boundary
                    // (or the leave below) resolves it.
                    CurrentStage = Stage.Synchronizing;
                    _boundaryFailStreak++;
                    if (applied && !_lastApplyOk) _deckFailStreak++;
                    if (_deckFailStreak >= 3)
                    {
                        // Repeated DECK failures = build mismatch (unknown
                        // cards, mod skew) — unrecoverable; map/snapshot
                        // timeouts keep retrying instead.
                        Plugin.Log?.LogWarning("[SPECTATE] three failed deck reconstructions — leaving");
                        LeaveToMenu("deck reconstruction failed");
                    }
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

        private static IEnumerator ApplyDecks(object[] snap, int gen, bool forceReset)
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
                    // Bodies were verified present before this ran; one going
                    // null mid-apply (leave during transition) fails the pass.
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

                if (isExtension)
                {
                    for (int k = have.Count; k < target.Count; k++)
                    {
                        if (gen != _boundaryGeneration) yield break;
                        if (!ApplyOne(body, actor, target[k])) yield break;
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

                // VERIFY (r1 find 9): the body's rendered deck must now equal
                // the snapshot exactly, in order.
                var now = CurrentDeckNames(body);
                bool match = now.Count == target.Count;
                if (match)
                    for (int k = 0; k < now.Count; k++)
                        if (!string.Equals(now[k], target[k], StringComparison.Ordinal)) { match = false; break; }
                if (!match)
                {
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
        private static IEnumerator ResetAndReplay(Player body, int actor, List<string> target, int gen)
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

        /// <summary>Kick spectator actors that never validated, or whose
        /// validation went stale (fail CLOSED — a seat the server no longer
        /// confirms is not a seat). Called from the fighter-side ticker.</summary>
        internal static void MasterSweepUnvalidated()
        {
            try
            {
                if (!PhotonNetwork.InRoom || !PhotonNetwork.IsMasterClient) return;
                if (SpectatorSession.IsLocalSpectator) return;
                foreach (var sp in RoomActors.Spectators())
                {
                    int a = sp.ActorNumber;
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
                        Plugin.Log?.LogWarning($"[SPECTATE] kicking {(wasValidated ? "stale-validated" : "never-validated")} spectator actor {a}");
                        try { PhotonNetwork.CloseConnection(sp); } catch { }
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
                    GameStateWatcher.SessionMatchCountValue
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
                _haveInfo = true;

                if (seq == _awaitBoundarySeq)
                    _boundaryResponse = a;
            }
            catch (Exception ex) { Plugin.Log?.LogWarning($"[SPECTATE] snapshot parse: {ex.Message}"); }
        }
    }
}
