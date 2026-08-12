using System;
using System.Collections;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 1 — the zero-character seat.
    ///
    /// These patches make a spectator client a PASSIVE observer: it owns no
    /// character, never answers a sync barrier, never reports a map load,
    /// never starts the game-mode lifecycle. Everything is gated on
    /// `SpectatorSession.IsLocalSpectator`, which is false in every shipped
    /// build until the join path sets it — so with no spectator these are
    /// pure pass-throughs (design §4.5, the inertness proof).
    ///
    /// Per-class Harmony registration (Plugin.cs:648-666) means a target
    /// that fails to resolve costs only its own class — but a silently
    /// unattached patch is a forever-no-op (#83), so GREP THE STARTUP LOG
    /// for "Failed to patch Spectator" before trusting any of this.
    ///
    /// ── WHY EACH ONE EXISTS (all cited to the decompile) ───────────────
    ///
    /// GM_ArmsRace.WaitForSyncUp is NOT an all-actor barrier: it broadcasts
    /// RPCO_RequestSyncUp to Others and completes on the FIRST returned
    /// RPCM_ReturnSyncUp (V/GM_ArmsRace.cs:171-194). So a spectator that
    /// ANSWERS can release a fighter earlier than the other fighter would
    /// have, changing transition timing on a ranked match. A spectator that
    /// stays silent is invisible to it. Silence is therefore the whole
    /// contract — never "reply faster", never "reply correctly".
    ///
    /// Map readiness (V/Map.cs:38-41 LoadedForAll) is one scalar equality
    /// fed by every client's ReportMapLoaded — a spectator report can
    /// satisfy it before a real fighter has loaded. The spectator consumes
    /// fighter reports but must never emit one.
    ///
    /// PlayerAssigner.LateUpdate polls local input and calls CreatePlayer
    /// (V/PlayerAssigner.cs:46-93) — that is the "press Space to join" path
    /// that RWF suppresses for its lobby. Both are guarded so no keypress
    /// can ever spawn a spectator body.
    /// </summary>
    internal static class SpectatorPatchSupport
    {
        /// <summary>One place every gate reads, so the condition cannot
        /// drift between patches.</summary>
        internal static bool Suppress
        {
            get
            {
                try { return SpectatorSession.IsLocalSpectator; }
                catch { return false; }
            }
        }

        internal static void Log(string what)
        {
            try { Plugin.Log?.LogInfo($"[SPECTATE] suppressed {what}"); } catch { }
        }

        /// <summary>An already-finished IEnumerator, for replacing a
        /// coroutine the spectator must not run.</summary>
        internal static IEnumerator Empty()
        {
            yield break;
        }
    }

    // ── Sync barriers: receive, never answer ─────────────────────────────

    /// <summary>Never answer a sync-up request. See the class comment: the
    /// barrier completes on the FIRST reply, so answering would release a
    /// fighter early.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCO_RequestSyncUp")]
    internal static class Spectator_NoSyncReply_Patch
    {
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            return false;   // silently drop — the fighters answer each other
        }
    }

    /// <summary>Defence in depth: if a spectator ever reaches a local
    /// WaitForSyncUp (it should not — it runs no GM lifecycle), complete it
    /// immediately rather than hanging forever waiting for a reply that is
    /// addressed to fighters.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "WaitForSyncUp")]
    internal static class Spectator_SyncUpNoWait_Patch
    {
        private static bool Prefix(ref IEnumerator __result)
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            __result = SpectatorPatchSupport.Empty();
            return false;
        }
    }

    /// <summary>Never report a map as loaded — `Map.LoadedForAll` is a
    /// single scalar equality, so a spectator's report can satisfy it
    /// before a fighter has actually finished loading.</summary>
    [HarmonyPatch(typeof(MapManager), "ReportMapLoaded")]
    internal static class Spectator_NoMapReport_Patch
    {
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            return false;
        }
    }

    // ── Zero-character invariant ─────────────────────────────────────────

    /// <summary>Kill the "press Space to join" polling on a spectator.
    /// Vanilla LateUpdate reads local input and calls CreatePlayer while
    /// joining is enabled (V/PlayerAssigner.cs:46-93).</summary>
    [HarmonyPatch(typeof(PlayerAssigner), "LateUpdate")]
    internal static class Spectator_NoAssignerPoll_Patch
    {
        private static bool Prefix()
        {
            return !SpectatorPatchSupport.Suppress;
        }
    }

    /// <summary>Hard backstop on the spawn itself. Any path that reaches
    /// CreatePlayer on a spectator client — vanilla polling, our own
    /// force-start helpers, a mode's auto-spawn — is refused here.
    ///
    /// NOTE this is a SECOND Prefix on CreatePlayer: the existing one in
    /// Plugin.cs guards the not-in-a-room NRE (#82). Harmony runs both;
    /// either returning false skips vanilla, which is the desired
    /// composition. This one is declared with priority First so the
    /// spectator refusal is decided before any slot/team logic runs.</summary>
    [HarmonyPatch(typeof(PlayerAssigner), "CreatePlayer")]
    internal static class Spectator_NoCreatePlayer_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            SpectatorPatchSupport.Log("PlayerAssigner.CreatePlayer");
            return false;
        }
    }

    // ── Game-mode lifecycle: observe, never drive ────────────────────────

    /// <summary>A spectator's local PlayerManager fills with REPLICATED
    /// fighter bodies (that is how it renders the match), and each
    /// registration invokes PlayerManager.PlayerJoined, which vanilla
    /// GM_ArmsRace.PlayerJoined counts to decide whether to StartGame
    /// (V/GM_ArmsRace.cs:131-169). On a spectator that would start a
    /// SECOND, local, wrong game. Suppress the callback entirely.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerJoined")]
    internal static class Spectator_NoGmPlayerJoined_Patch
    {
        private static bool Prefix()
        {
            return !SpectatorPatchSupport.Suppress;
        }
    }

    /// <summary>Never start the local game-mode lifecycle. Priority.First:
    /// FfaMode replaces the same methods for ffa_ rooms — the spectator's
    /// refusal must deterministically beat the FFA replacement, or an FFA
    /// rematch would run the whole game-start flow on the spectator.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "StartGame")]
    internal static class Spectator_NoStartGame_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            SpectatorPatchSupport.Log("GM_ArmsRace.StartGame");
            return false;
        }
    }

    /// <summary>Same for the coroutine form (which also runs on same-room
    /// rematches — vanilla's IDoRematch calls DoStartGame directly, #138).</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "DoStartGame")]
    internal static class Spectator_NoDoStartGame_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(ref IEnumerator __result)
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            __result = SpectatorPatchSupport.Empty();
            return false;
        }
    }

    /// <summary>Defense-in-depth for bug 203: GameOverTransition is the ONLY
    /// caller of GameOverRematch, whose "REMATCH?" DisplayScreenTextLoop has
    /// no reachable clearer on an observer seat (the only StopScreenTextLoop
    /// callers in game+mod are IDoRematch and the offline-only DoContinue,
    /// both reachable solely through GetRematchYesNo — and the spectator's
    /// PopUpHandler gate, itself correct, never invokes that callback; note
    /// DoRestart does NOT clear the text either, it NetworkRestarts). Its
    /// only two callers are participant paths (vanilla GM_ArmsRace.GameOver
    /// and FfaMode.HandleNextRound), both already gated on observer seats —
    /// suppressing the funnel too closes the stuck-popup class for every
    /// path, found or not (#338). Winner feedback on an FFA observer comes
    /// from SpectatorObserveRound's decisive-conversion announcement; in GM
    /// modes from the observer prefix's PlayPointSequence.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "GameOverTransition")]
    internal static class Spectator_NoGameOverTransition_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(ref IEnumerator __result)
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            SpectatorPatchSupport.Log("GM_ArmsRace.GameOverTransition");
            __result = SpectatorPatchSupport.Empty();
            return false;
        }
    }

    /// <summary>Round/point accounting: record the score for the spectator's
    /// own HUD, but do NOT run vanilla's state machine (which overwrites
    /// scores, increments a winner, fires GameManager.GameOver and starts
    /// transitions — V/GM_ArmsRace.cs:515-585). The spectator's view is
    /// driven by observation, not by simulating the match itself.</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound")]
    internal static class Spectator_ObserveNextRound_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(GM_ArmsRace __instance,
                                   int losingTeamID, int winningTeamID,
                                   int p1PointsSet, int p2PointsSet,
                                   int p1RoundsSet, int p2RoundsSet)
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            // FFA (Codex r1 find 8): NEVER let the participant transition
            // engine run on a spectator — HandleNextRound drives visibility,
            // revives, the pick cycle and the report path, and a late joiner
            // has no cycle bookkeeping to run it against. Apply the master's
            // score delta through the narrow observer instead; map load,
            // call-in and body moves arrive via the master's own RPCs.
            try
            {
                // One observed round per call-in (Aug 10 review find 9, moved
                // ABOVE the FFA branch by Aug 11 review r2 find 2): vanilla
                // dedupes duplicate/bunched round broadcasts with
                // isTransitioning, which lives in the suppressed machine, and
                // the FFA observer previously returned before this latch —
                // a duplicate broadcast double-incremented the FFA observer
                // score and could falsely announce a win. The latch clears at
                // every observed call-in (both modes ride the master's map
                // RPCs) with a 20s TTL backstop, so consecutive legitimate
                // rounds are never eaten.
                if (SpectatorSync.RoundObservationLatched) return false;
                SpectatorSync.LatchRoundObservation();
            }
            catch { }
            try
            {
                if (FfaMode.EngineActive())
                {
                    FfaMode.SpectatorObserveRound(winningTeamID);
                    return false;
                }
            }
            catch { }
            try
            {
                // The RPC args are PRE-increment (vanilla RPCA_NextRound
                // assigns them and THEN increments the winner — Codex r2 find
                // 16: recording them raw displayed every score one event
                // stale, including the final one). Mirror vanilla's own
                // increment, using the LIVE thresholds (host-configurable in
                // private rooms — never hardcode). Boundary snapshots
                // overwrite with the master's values, correcting any drift.
                int ptw = __instance.pointsToWinRound; if (ptw <= 0) ptw = 2;
                int rtw = __instance.roundsToWinGame; if (rtw <= 0) rtw = 5;
                SpectatorViewState.RecordPointsToWin(ptw);

                int p1p = p1PointsSet, p2p = p2PointsSet;
                int p1r = p1RoundsSet, p2r = p2RoundsSet;
                if (winningTeamID == 0) p1p++;
                else if (winningTeamID == 1) p2p++;
                // RAW post-increment points for the visual sequence (find 7:
                // passing the normalized 0-0 to DoWinSequence rendered empty
                // HALF pips on every round win).
                int visP1 = p1p, visP2 = p2p;
                bool conversion = false;
                if (winningTeamID == 0 && p1p >= ptw) { conversion = true; p1r++; p1p = 0; p2p = 0; }
                else if (winningTeamID == 1 && p2p >= ptw) { conversion = true; p2r++; p1p = 0; p2p = 0; }
                bool gameOver = conversion
                    && (winningTeamID == 0 ? p1r : p2r) >= rtw;

                SpectatorViewState.RecordScore(winningTeamID, p1p, p2p, p1r, p2r);
                // Mirror into the GM's own score fields (playtest #2c): the
                // vanilla CROWN reads gm.p1Rounds/p1Points directly
                // (V/GameCrownHandler.cs:26-41), so with the state machine
                // suppressed it saw an eternal 0-0 and never appeared.
                // Display-only on a spectator — nothing else consumes these
                // fields here because every consumer is suppressed.
                __instance.p1Points = p1p;
                __instance.p2Points = p2p;
                __instance.p1Rounds = p1r;
                __instance.p2Rounds = p2r;
                // Codex r5 find 3: the crown initializes through
                // gm.pointOverAction (vanilla fires it inside the suppressed
                // state machine) — with currentCrownHolder stuck at -1 its
                // LateUpdate returns forever. PointOver() is public and reads
                // the fields we just mirrored; it handles both the first
                // PlayIn and later transfers.
                try { UnityEngine.Object.FindObjectOfType<GameCrownHandler>()?.PointOver(); } catch { }

                // Between-points display (item 2): vanilla's own score-orb
                // sequence, driven from the observed values. Replaces the
                // hard black reconcile flash spectators used to get here.
                SpectatorSync.PlayPointSequence(conversion, gameOver, visP1, visP2, p1r, p2r, winningTeamID);
            }
            catch { }
            return false;
        }
    }

    /// <summary>Aug 10 root cause D1: GM_ArmsRace.PlayerDied runs on every
    /// replicated round-ending kill (its subscription is made in OnEnable,
    /// and the spectator activates the GM object for its RPC receivers). It
    /// calls TimeHandler.DoSlowDown() — whose every restore lives in the
    /// suppressed transitions, so the spectator's clock ratcheted down at the
    /// first kill and stayed there: slow-motion bullets, frozen IK/wobble
    /// followers ("nametags lag"), stair-stepping bodies. It also carries an
    /// IsMasterClient branch that would broadcast a REAL RPCA_NextRound from
    /// a spectator during a master-handoff window. Suppress the whole method;
    /// score observation rides the fighters' own RPCA_NextRound instead.
    /// This is the missing GM-mode sibling of FfaMode's existing spectator
    /// gate (FfaMode.cs "Codex r2 find 9").</summary>
    [HarmonyPatch(typeof(GM_ArmsRace), "PlayerDied")]
    internal static class Spectator_NoGmPlayerDied_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix()
        {
            return !SpectatorPatchSupport.Suppress;
        }
    }

    /// <summary>Aug 11 r3 HIGH — an OBSERVER seat must be structurally unable
    /// to originate a death. Vanilla DoDamage broadcasts RPCA_Die(All) /
    /// RPCA_Die_Phoenix from ANY replica whose local health crosses zero
    /// (HealthHandler.cs:286-294, no ownership check), and a spectator's
    /// replica health can diverge from the fighters' (degraded local bullet
    /// sim against buried objects; the poison display path's bounded stale
    /// residual) — so a legitimate later hit could cross zero HERE while the
    /// real fighter survives, killing them for everyone. Forcing lethal=false
    /// makes vanilla's own clamp (health >= 1) run first and the death branch
    /// unreachable, for EVERY damage path on this seat. Real deaths still
    /// render: fighters' seats broadcast the die RPCs, which call the death
    /// path directly, never through DoDamage. Fighter seats untouched.</summary>
    [HarmonyPatch(typeof(HealthHandler), "DoDamage")]
    internal static class Spectator_NonLethalDamage_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static void Prefix(ref bool lethal)
        {
            try { if (RoomActors.LocalIsSpectator) lethal = false; } catch { }
        }
    }

    /// <summary>Aug 10 root cause D1b: with GameManager.isPlaying false,
    /// vanilla Map.Awake activates GM_Test (test-map mode). GM_Test.OnEnable
    /// subscribes a PlayerDied handler that teleport-revives dead fighter
    /// replicas at random spawns 2.5s after every death, sets
    /// isTestingMap = true, and force-starts the clock. The isPlaying pin in
    /// SpectatorSync prevents the activation; this is the belt for any path
    /// that still enables it — with OnEnable suppressed, GM_Test's
    /// subscriptions are never made (its OnDisable Delegate.Remove of a
    /// never-added handler is a harmless no-op).</summary>
    [HarmonyPatch(typeof(GM_Test), "OnEnable")]
    internal static class Spectator_NoGmTest_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            SpectatorPatchSupport.Log("GM_Test.OnEnable");
            return false;
        }
    }

    /// <summary>Join-replay quarantine, tag half (Aug 10 review find 5): a
    /// parentless PhotonMapObject clone seen while the window is armed is a
    /// cache-replayed husk. Tag it at Awake — the TAG (not the armed state at
    /// Start time) decides suppression, because Awake and a deferred Start
    /// can straddle a later live map load.</summary>
    [HarmonyPatch(typeof(PhotonMapObject), "Awake")]
    internal static class Spectator_ReplayTag_Patch
    {
        private static void Postfix(PhotonMapObject __instance)
        {
            try
            {
                if (!SpectatorPatchSupport.Suppress) return;
                if (__instance == null || __instance.transform.parent != null) return;
                if (SpectatorSync.ReplayQuarantineArmed)
                {
                    SpectatorSync.TagReplayObject(__instance.GetInstanceID());
                    return;
                }
                // LIVE clone: stamp its map-load generation NOW (r5 find 4 —
                // sampling at Start is too late; a newer command in the
                // Awake->Start gap would bind it to the wrong map).
                SpectatorSync.StampLiveCloneGen(__instance.GetInstanceID());
            }
            catch { }
        }
    }

    /// <summary>Join-replay quarantine, suppression half (root cause D2): a
    /// tagged husk's vanilla Start would NRE against the missing map (the
    /// 323/763-exception join walls in both spectator logs) and leave a
    /// REGISTERED PhotonView that collides with the rematch's recycled view
    /// IDs (the proven game-2 desync). Bury + locally unregister at source
    /// instead; vanilla never runs.</summary>
    [HarmonyPatch(typeof(PhotonMapObject), "Start")]
    internal static class Spectator_ReplayQuarantine_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(PhotonMapObject __instance)
        {
            try
            {
                if (!SpectatorPatchSupport.Suppress) return true;
                if (__instance == null) return true;
                if (SpectatorSync.IsReplayTagged(__instance.GetInstanceID()))
                {
                    SpectatorSync.SafeBuryAndClean(__instance.gameObject);
                    SpectatorSync.CountReplayBuried();
                    return false;
                }
                // LIVE clone with no local map yet (Aug 10 r2 find 3: we
                // joined after the load RPC and the direct local load is
                // still in flight): vanilla Start would NRE and leave a
                // registered orphan view. Defer it until the map exists —
                // the defer coroutine re-invokes Start, which passes through
                // here again with a live map and runs vanilla normally.
                if (__instance.transform.parent == null)
                {
                    // SETTLED on the last COMMANDED SCENE (r4 blocker 1): the
                    // in-flight signal is the RPCA_LoadLevel arg we record —
                    // Map.levelID is vanilla's readiness token, never scene
                    // identity, so no field equality can express this. While
                    // a load is in flight, vanilla Start would parent this
                    // clone under the OUTGOING map, which dies with its
                    // unload and corrupts the new map's accounting.
                    if (!SpectatorSync.MapSettledOnCommanded())
                    {
                        SpectatorSync.DeferMapObjectStart(__instance);
                        return false;
                    }
                }
                return true;
            }
            catch { return true; }
        }
    }

    /// <summary>Aug 10 r3 find 5: vanilla PhotonMapObject.Update carries the
    /// LAST master-only sender the spectator's authority suppression missed —
    /// during a transient spectator-master window, a local PLACEHOLDER's
    /// Update would PhotonNetwork.Instantiate real networked map pieces at
    /// every fighter. Replace the body for spectators: identical local
    /// accounting (counter, waitingToBeRemoved, missingObjects), never the
    /// instantiate branch. All fields publicized.</summary>
    [HarmonyPatch(typeof(PhotonMapObject), "Update")]
    internal static class Spectator_NoMapObjectAuthority_Patch
    {
        private static bool Prefix(PhotonMapObject __instance)
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            try
            {
                var o = __instance;
                if (o == null) return false;
                if (o.waitingToBeRemoved || o.photonSpawned) return false;
                o.counter += Mathf.Clamp(Time.deltaTime, 0f, 0.1f);
                var map = o.map;
                bool gate = false;
                try
                {
                    gate = (PhotonNetwork.OfflineMode && o.counter > 1f && map != null && map.hasEntered)
                           || (map != null && map.hasEntered && map.LoadedForAll());
                }
                catch { }
                if (gate)
                {
                    // Vanilla would PhotonNetwork.Instantiate here when
                    // master — the one thing a spectator must never do.
                    map.missingObjects++;
                    o.waitingToBeRemoved = true;
                }
            }
            catch { }
            return false;
        }
    }

    /// <summary>Map-load serializer gate (r5 blocker 1): vanilla subscribes
    /// its completion handler PER RPCA_LoadLevel call, so overlapping loads
    /// double-subscribe and corrupt the wrapper handoff. On a spectator this
    /// PREFIX permits one active load, queues the latest different target
    /// (launched from the completion hook below), and drops duplicates. It
    /// also closes the join-replay window — live map flow has begun — and
    /// records the commanded scene (the RPC arg is the ONLY observable
    /// "load in flight toward S" signal).</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_LoadLevel")]
    internal static class Spectator_MapLoadGate_Patch
    {
        [HarmonyPriority(Priority.First)]
        private static bool Prefix(string sceneName)
        {
            try
            {
                if (!SpectatorPatchSupport.Suppress) return true;
                SpectatorSync.DisarmReplayQuarantine("map load");
                return SpectatorSync.GateMapLoad(sceneName);
            }
            catch { return true; }
        }
    }

    /// <summary>Completion hook for the serializer: pins local readiness to
    /// the settled map's token and launches any queued load.</summary>
    [HarmonyPatch(typeof(MapManager), "OnLevelFinishedLoading")]
    internal static class Spectator_MapLoadCompleted_Patch
    {
        private static void Postfix()
        {
            try
            {
                if (SpectatorPatchSupport.Suppress)
                    SpectatorSync.OnMapLoadCompleted();
            }
            catch { }
        }
    }

    /// <summary>r5 find 2: a slow fighter's RPCA_ReportMapLoaded carries the
    /// readiness token of ITS load lineage. After the spectator direct-loads
    /// a missed map, its local token can legitimately differ — the report
    /// would overwrite the pinned scalar, LoadedForAll would stay false and
    /// every networked clone would stay kinematic. The spectator's readiness
    /// scalar is fully self-owned (pinned at each load completion); inbound
    /// reports are dropped. Fighters are untouched.</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_ReportMapLoaded")]
    internal static class Spectator_NoInboundMapReports_Patch
    {
        private static bool Prefix()
        {
            return !SpectatorPatchSupport.Suppress;
        }
    }

    // ── Master-only senders: inert on a spectator even mid-handoff ───────

    /// <summary>A spectator can be Photon master for a beat (old master left;
    /// our SetMasterClient handoff is one round-trip away). MapManager's
    /// master-gated senders would fire real map RPCs at every fighter in
    /// that window. The RPCA_* RECEIVERS stay untouched — the spectator must
    /// keep consuming the fighters' map flow.</summary>
    [HarmonyPatch(typeof(MapManager), "LoadNextLevel")]
    internal static class Spectator_NoMapAuthority_Load_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    [HarmonyPatch(typeof(MapManager), "CallInNewMapAndMovePlayers")]
    internal static class Spectator_NoMapAuthority_CallIn_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    [HarmonyPatch(typeof(MapManager), "CallInNewMap")]
    internal static class Spectator_NoMapAuthority_CallInBare_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    // ── Leave handling ───────────────────────────────────────────────────

    /// <summary>THE requirement that makes spectating safe for players: a
    /// spectator leaving must be invisible to the match.
    ///
    /// Vanilla NetworkConnectionHandler.OnPlayerLeftRoom unconditionally
    /// ends the match for EVERYONE (#209) — that is correct for a fighter
    /// in 1v1/2v2/1v2 and already suppressed by FFA. When the DEPARTED
    /// actor is a spectator, the entire cascade must not run: no
    /// DoDisconnect, no DC win, no leaver bookkeeping.
    ///
    /// Runs on PLAYER clients (not gated on Suppress) — it is the one
    /// player-side patch in this file, and it is inert whenever the
    /// departing actor is not a spectator, which is every room today.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerLeftRoom")]
    internal static class Spectator_LeaveIsInvisible_Patch
    {
        private static bool Prefix(Photon.Realtime.Player otherPlayer)
        {
            try
            {
                if (otherPlayer == null) return true;
                // A departure tears the match down ONLY for a genuine
                // fighter. The load-bearing tests are the PROP-DERIVED pair
                // (r9): no-u_id and impostor-duplicate are computed
                // identically on every seat from replicated data, so the
                // suppression can never split across clients whatever their
                // local roster-freeze timing (the r8 failure). The local
                // caches (rejected/unauthorized) only ADD suppression on
                // seats that know more — a benign asymmetry, because extra
                // suppression converges to the vanilla outcome when the real
                // fighters act.
                bool nonFighter = RoomActors.IsSpectator(otherPlayer)
                                  || (RoomActors.ReplicatedIdentityGuaranteed()
                                      && !RoomActors.HasReplicatedFighterIdentity(otherPlayer))
                                  || RoomActors.IsImpostorReplicated(otherPlayer)
                                  || RoomActors.IsRejected(otherPlayer)
                                  || RoomActors.IsUnauthorized(otherPlayer);
                if (!nonFighter) return true;   // inert
                Plugin.Log?.LogInfo($"[SPECTATE] non-fighter actor {otherPlayer.ActorNumber} left — suppressing vanilla match teardown");
                return false;
            }
            catch { return true; }   // never break vanilla's leave path
        }
    }

    /// <summary>Vanilla emits RPCA_FoundGame off a raw
    /// `PhotonNetwork.PlayerList.Length == 2` check
    /// (V/NetworkConnectionHandler.cs:524-540). An arriving SPECTATOR must
    /// never trigger match-found behaviour. Player-side; inert when the
    /// entrant is a fighter.</summary>
    [HarmonyPatch(typeof(NetworkConnectionHandler), "OnPlayerEnteredRoom")]
    internal static class Spectator_EntryIsNotMatchFound_Patch
    {
        private static bool Prefix(Photon.Realtime.Player newPlayer)
        {
            try
            {
                if (newPlayer == null) return true;
                if (RoomActors.IsSpectator(newPlayer))
                {
                    Plugin.Log?.LogInfo($"[SPECTATE] spectator actor {newPlayer.ActorNumber} joined — not a match-found event");
                    return false;
                }
                // Unauthorized entrant: record the rejection HERE too —
                // callback dispatch order vs Plugin's IInRoomCallbacks is
                // undefined, and the cache must exist before the master's
                // CloseConnection produces the departure (blocker 2).
                if (RoomActors.IsUnauthorized(newPlayer))
                {
                    RoomActors.RecordRejected(newPlayer);
                    Plugin.Log?.LogInfo($"[SPECTATE] unauthorized actor {newPlayer.ActorNumber} joined — not a match-found event");
                    return false;
                }
                return true;   // inert
            }
            catch { return true; }
        }
    }

    // ── PHASE 2: boundary observation + pre-activation quarantine ────────

    /// <summary>The activation boundary (design §5.3): every point/round
    /// transition fires this RPC at every client, spectator included. The
    /// Postfix ONLY observes — vanilla's own coroutine (wait for map, enter,
    /// clear objects, move players) still runs on the spectator, which is
    /// what revives and repositions the fighter replicas for free.</summary>
    [HarmonyPatch(typeof(MapManager), "RPCA_CallInNewMapAndMovePlayers")]
    internal static class Spectator_BoundaryObserver_Patch
    {
        private static void Postfix(int mapID)
        {
            try
            {
                if (SpectatorPatchSupport.Suppress)
                    SpectatorSync.OnCallInObserved(mapID);
            }
            catch { }
        }
    }

    /// <summary>Pre-activation card quarantine (design §5.7): a live pick
    /// arriving between join and activation would be applied ONCE here and
    /// AGAIN by the boundary snapshot that includes it. Suppress the live
    /// RPC until Active; after activation the vanilla path keeps decks
    /// current and the boundary reconcile is a provable no-op.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "RPCA_Pick")]
    internal static class Spectator_PreActivationPickQuarantine_Patch
    {
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            if (SpectatorSync.CurrentStage == SpectatorSync.Stage.Active) return true;
            SpectatorPatchSupport.Log("pre-activation RPCA_Pick");
            return false;
        }
    }

    // ── Zero-character invariant, ALL clients (design §3.3) ──────────────

    /// <summary>Registration firewall. Runs on EVERY client (not gated on
    /// Suppress): a Player replica owned by a spectator actor — or, once a
    /// roster is frozen, by any actor outside it — must never enter
    /// PlayerManager.players, where every character loop would treat it as
    /// a combatant. The replica is disabled locally, never destroyed (#94:
    /// never Object.Destroy a Photon-owned object), and the master closes
    /// the offending connection.
    ///
    /// Inert today: no actor carries the role property and no roster is
    /// frozen, so the guard never fires.</summary>
    [HarmonyPatch(typeof(PlayerManager), "RegisterPlayer")]
    internal static class Spectator_RegistrationFirewall_Patch
    {
        private static bool Prefix(Player player)
        {
            try
            {
                if (player == null || player.data == null || player.data.view == null) return true;
                var owner = player.data.view.Owner;
                if (owner == null) return true;                 // offline/local — vanilla's problem
                bool spectatorOwned = RoomActors.IsSpectator(owner);
                bool unauthorized = !spectatorOwned && RoomActors.IsUnauthorized(owner);
                if (!spectatorOwned && !unauthorized) return true;   // inert path

                // Cache the rejection locally (additive suppression; the
                // cross-client leave rule is prop-derived, r9).
                if (unauthorized) RoomActors.RecordRejected(owner);

                Plugin.Log?.LogWarning($"[SPECTATE] rejecting Player registration from " +
                    $"{(spectatorOwned ? "spectator" : "unauthorized")} actor {owner.ActorNumber}");
                try { player.gameObject.SetActive(false); } catch { }
                if (PhotonNetwork.IsMasterClient && unauthorized)
                {
                    RoomActors.CooperativeClose(owner);   // best-effort (r9 find 1)
                }
                return false;
            }
            catch { return true; }
        }
    }

    // ── PHASE 3: side-effect shutdown ────────────────────────────────────

    /// <summary>Steam/platform achievements can be reached by REPLICATED
    /// gameplay on a client with no local fighter (the calls are static —
    /// V/FriendlyFoe.Platform/PlatformManager.cs:33-48). A spectator must
    /// never unlock anything from a match it is only watching.</summary>
    [HarmonyPatch(typeof(FriendlyFoe.Platform.PlatformManager), "UnlockAchievement")]
    internal static class Spectator_NoPlatformUnlock_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    [HarmonyPatch(typeof(FriendlyFoe.Platform.PlatformManager), "ProgressAchievement")]
    internal static class Spectator_NoPlatformProgress_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    /// <summary>Vanilla Esc handling calls PlayerManager.SetInputActive and
    /// can NetworkRestart during loading (V/EscapeMenuHandler.cs:23-43) —
    /// both wrong for a spectator. The spectator HUD owns the Esc key
    /// (leave menu) for the whole session.</summary>
    [HarmonyPatch(typeof(EscapeMenuHandler), "Update")]
    internal static class Spectator_NoVanillaEscMenu_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    /// <summary>Playtest #169a: activating the GM object runs GM_ArmsRace.Start,
    /// which shows the big "PRESS JUMP TO JOIN" prompt
    /// (V/GM_ArmsRace.cs:98) — and the ONLY hide site is DoStartGame
    /// (:211), which the spectator suppresses, so the prompt stayed on
    /// screen forever. A spectator can never join, so it never shows it.</summary>
    [HarmonyPatch(typeof(UIHandler), "ShowJoinGameText")]
    internal static class Spectator_NoJoinPrompt_Patch
    {
        private static bool Prefix() { return !SpectatorPatchSupport.Suppress; }
    }

    /// <summary>Playtest #169 defense-in-depth: ghost pick-cards (see
    /// SpectatorSync.SweepGhostCards) carry ApplyCardStats with a live
    /// Pick() path — vanilla's shoot-to-pick handler could fire from the
    /// spectator's LOCAL bullet simulation hitting a ghost card, and
    /// Pick() sends a REAL RPCA_Pick to every fighter. Nothing on a
    /// spectator may ever call Pick; our own replay uses OFFLINE_Pick,
    /// which does not route through here.</summary>
    [HarmonyPatch(typeof(ApplyCardStats), "Pick")]
    internal static class Spectator_NoCardPickRpc_Patch
    {
        private static bool Prefix()
        {
            if (!SpectatorPatchSupport.Suppress) return true;
            SpectatorPatchSupport.Log("ApplyCardStats.Pick (ghost-card pick blocked)");
            return false;
        }
    }
}
