using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Text;
using HarmonyLib;
using Photon.Pun;
using RealtimePlayer = Photon.Realtime.Player;

namespace CompetitiveRounds
{
    /// <summary>
    /// Observational diagnostics for remote PhotonView serialization. The receive hook
    /// never skips or mutates a packet: it mirrors PUN's missing-view predicate for the
    /// orphan counter, then measures local arrival gaps against the sender timestamp.
    /// </summary>
    internal static class NetworkReplicaDiagnostics
    {
        internal const string JitterDiagKey = "NetworkReplicaDiagnostics-jitter";
        internal const string GameSummaryDiagKey = "NetworkReplicaDiagnostics-game-summary";

        private const int MaxTrackedActors = 32;
        private const int MaxActorsPerSummary = 10;
        private const int MaxDistinctOrphanViews = 4096;
        private const int MaxMeasuredGapMs = 60000;
        private const int ArrivalGapLogThresholdMs = 300;
        private const int JitterLogThresholdMs = 150;
        private const int JitterLogMaximumPerRoom = 16;
        private const int GameSummaryLogMaximumPerRoom = 128;

        private static readonly Dictionary<int, ActorStats> Actors =
            new Dictionary<int, ActorStats>();
        private static readonly HashSet<int> RoomOrphanViews =
            new HashSet<int>(MaxDistinctOrphanViews);
        private static readonly HashSet<int> GameOrphanViews =
            new HashSet<int>(MaxDistinctOrphanViews);

        private static bool _roomActive;
        private static bool _gameActive;
        private static bool _gameEnded;
        private static bool _gamePartial;
        private static bool _battleActive;
        private static bool _spectatorActivationAllowed;
        private static bool _jitterLogBudgetSpent;
        private static Photon.Realtime.Room _observedRoom;
        private static bool _roomOrphanViewsOverflowed;
        private static bool _gameOrphanViewsOverflowed;
        private static int _roomStartedAtMs;
        private static int _gameStartedAtMs;
        private static int _gameEndedAtMs;
        private static int _gameOrdinal;
        private static long _roomOrphans;
        private static long _gameOrphans;
        private static long _gameOrphansAtScore;
        private static int _gameOrphanViewsAtScore;
        private static long _roomDroppedActorEvents;
        private static long _gameDroppedActorEvents;

        [ThreadStatic]
        private static bool _warningCandidate;
        [ThreadStatic]
        private static int _warningCandidateViewId;
        [ThreadStatic]
        private static int _warningCandidateActor;
        [ThreadStatic]
        private static bool _warningCandidateCommitted;
        [ThreadStatic]
        private static bool _warningCandidateEligible;

        // ── lag-332 v6 §1.1: call-scoped receive context ─────────────────
        // Set by Observe for the ONE view PUN is dispatching, consumed once by
        // the movement Postfix (NetworkSeatTelemetry) after validating the
        // view id and room generation, cleared by the OnSerializeRead
        // Finalizer on EVERY exit (orphan / group / prefix / delta rejection,
        // sibling-prefix suppression, movement exception).
        [ThreadStatic] private static bool _ctxValid;
        [ThreadStatic] private static int _ctxViewId;
        [ThreadStatic] private static int _ctxActor;
        [ThreadStatic] private static int _ctxRoomGeneration;
        [ThreadStatic] private static int _ctxNetworkTime;
        [ThreadStatic] private static long _ctxArrivalTick;
        [ThreadStatic] private static int _ctxArrivalGapMs;
        [ThreadStatic] private static int _ctxExcessMs;
        [ThreadStatic] private static bool _ctxSampled;
        [ThreadStatic] private static bool _ctxQuarantined;
        private static int _roomGeneration;
        internal static int RoomGeneration => _roomGeneration;
        // [NET-PROF] self-profiler (r1 MEDIUM 8): Stopwatch ticks spent inside
        // the observer + movement hooks this game, so the instrument's own cost
        // is in the bundle next to what it measures.
        private static long _hookTicksGame;
        private static long _hookCallsGame;
        // Per-frame hook cost, drained by NetworkSeatTelemetry.TickFrame as the
        // "netcb" component of the frame's time (r2 MEDIUM 8).
        private static long _hookTicksFrame;
        internal static long DrainFrameHookTicks() { long t = _hookTicksFrame; _hookTicksFrame = 0; return t; }
        internal static void AddHookCost(long ticks) { _hookTicksGame += ticks; _hookTicksFrame += ticks; _hookCallsGame++; }
        internal static void ResetHookCost() { _hookTicksGame = 0; _hookCallsGame = 0; _hookTicksFrame = 0; }
        /// <summary>The observer's own battle gate — the spectator seat's ONLY
        /// battle signal (its GM writers are suppressed), used by the seat
        /// frame sampler when the local seat is a spectator (r2 MEDIUM 7).</summary>
        internal static bool BattleActive => _battleActive;
        internal static string HookCostLine()
        {
            double ms = _hookTicksGame * 1000.0 / Stopwatch.Frequency;
            return "[NET-PROF] hookCalls=" + _hookCallsGame.ToString(CultureInfo.InvariantCulture)
                + " hookMs=" + ms.ToString("F1", CultureInfo.InvariantCulture)
                + " perCallUs=" + (_hookCallsGame > 0 ? (ms * 1000.0 / _hookCallsGame).ToString("F2", CultureInfo.InvariantCulture) : "0");
        }

        internal static void ClearReceiveContext()
        {
            _ctxValid = false;
            _ctxSampled = false;
            _ctxQuarantined = false;
            _ctxViewId = 0;
            _ctxActor = 0;
        }

        /// <summary>Commit one Player-stream sample to the actor's windows and
        /// emit the bounded [NET-JITTER] line. Shared by the spectator legacy
        /// path (Observe) and the fighter view-confirmed path
        /// (RecordMovementSample).</summary>
        private static void CommitTiming(ActorStats actor, int actorNumber, int networkTime, long arrivalTick, out GapSample sample)
        {
            GapSample roomSample;
            actor.Room.Record(networkTime, arrivalTick, out roomSample);
            sample = roomSample;
            bool sampled = roomSample.Valid;
            if (_gameActive)
            {
                actor.Game.Record(networkTime, arrivalTick, out sample);
                sampled = sample.Valid;
            }
            _ctxSampled = sampled;
            _ctxArrivalGapMs = sampled ? sample.ArrivalGapMs : 0;
            _ctxExcessMs = sampled ? sample.DeliveryExcessMs : 0;

            if (sampled && sample.ArrivalGapMs >= ArrivalGapLogThresholdMs &&
                sample.DeliveryExcessMs >= JitterLogThresholdMs &&
                !_jitterLogBudgetSpent)
            {
                if (VanillaFixSupport.TryReserveDiag(
                    JitterDiagKey, JitterLogMaximumPerRoom))
                {
                    VanillaFixSupport.WriteReservedDiag(
                        "[NET-JITTER] actor=" + actorNumber.ToString(CultureInfo.InvariantCulture) +
                        " arrivalGap=" + sample.ArrivalGapMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                        " senderGap=" + sample.SenderGapMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                        " excess=" + sample.DeliveryExcessMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                        " game=" + _gameOrdinal.ToString(CultureInfo.InvariantCulture));
                }
                else
                {
                    // Avoid even a dictionary lock after the fixed room
                    // budget is known exhausted; room edges clear both.
                    _jitterLogBudgetSpent = true;
                }
            }
        }

        /// <summary>Reporter-side observation of the opponent's stream for the
        /// match report (v6 §1.4): the single remote actor with the most
        /// observed views this game (1v1 = the opponent).</summary>
        internal struct ObsSnapshot
        {
            public long Gap300, Gap750, Gap1500, Excess150, PayloadEqualGaps, ReceiverFrameGaps, PhoenixIntervals, Batches;
            public int MaxGapMs, MaxExcessMs;
        }

        internal static bool TryGetOpponentGameObs(out ObsSnapshot o)
        {
            o = default(ObsSnapshot);
            try
            {
                ActorStats best = null;
                foreach (ActorStats a in Actors.Values)
                    if (best == null || a.Game.Views > best.Game.Views) best = a;
                if (best == null || best.Game.Views == 0) return false;
                TimingWindow w = best.Game;
                o.Gap300 = w.Gap300; o.Gap750 = w.Gap750; o.Gap1500 = w.Gap1500;
                o.Excess150 = w.Jitter150; o.MaxGapMs = w.MaxArrivalGapMs; o.MaxExcessMs = w.MaxDeliveryExcessMs;
                o.PayloadEqualGaps = w.PayloadEqualGaps; o.ReceiverFrameGaps = w.ReceiverFrameGaps;
                o.PhoenixIntervals = w.PhoenixIntervals; o.Batches = w.Batches;
                return true;
            }
            catch { return false; }
        }

        // ── lag-332 v6 §1.2: accepted lifecycle transitions ──────────────

        /// <summary>An ACCEPTED active→inactive transition on a remote view
        /// (Die: dead false→true; Phoenix: isRespawning false→true). Normal
        /// death clears the baseline and cancels any open interval; Phoenix
        /// opens a quarantine interval closed only by an accepted Revive.</summary>
        internal static void OnAcceptedDeath(int ownerActor, int viewId, bool phoenix)
        {
            try
            {
                int localActor = 0;
                try { localActor = PhotonNetwork.LocalPlayer == null ? 0 : PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
                if (ownerActor <= 0 || ownerActor == localActor) return;
                ActorStats actor = GetOrCreateActor(ownerActor);
                if (actor == null) return;
                actor.Room.ClearBaseline();
                actor.Game.ClearBaseline();
                if (phoenix)
                {
                    actor.InactiveOpen = true;
                    actor.InactiveSinceTick = Stopwatch.GetTimestamp();
                }
                else
                {
                    actor.InactiveOpen = false;
                }
            }
            catch (Exception ex) { VanillaFixSupport.LogError("NetworkReplicaDiagnostics.AcceptedDeath", ex); }
        }

        internal static void OnAcceptedRevive(int ownerActor, int viewId)
        {
            try
            {
                int localActor = 0;
                try { localActor = PhotonNetwork.LocalPlayer == null ? 0 : PhotonNetwork.LocalPlayer.ActorNumber; } catch { }
                if (ownerActor <= 0 || ownerActor == localActor) return;
                ActorStats actor = GetOrCreateActor(ownerActor);
                if (actor == null) return;
                if (actor.InactiveOpen)
                {
                    long ms = (Stopwatch.GetTimestamp() - actor.InactiveSinceTick) * 1000L / Stopwatch.Frequency;
                    actor.InactiveOpen = false;
                    actor.Room.PhoenixIntervals++; actor.Room.PhoenixMs += ms;
                    if (_gameActive) { actor.Game.PhoenixIntervals++; actor.Game.PhoenixMs += ms; }
                }
                // The first post-revive sample becomes the baseline only.
                actor.Room.ClearBaseline();
                actor.Game.ClearBaseline();
                actor.HasLastPayload = false;
            }
            catch (Exception ex) { VanillaFixSupport.LogError("NetworkReplicaDiagnostics.AcceptedRevive", ex); }
        }

        /// <summary>The movement Postfix hands over the package vanilla just
        /// appended. Consumed ONCE against the call context: classifies the
        /// batch's gap (if any) as payload-equal (ALL EIGHT wire values inside
        /// PUN's own unchanged-tolerance — what an UnreliableOnChange sender
        /// stops sending for; it names no cause) and/or receiver-frame (our
        /// own frame covered most of the gap). Quarantined samples (Phoenix
        /// interval open) only count.</summary>
        // Mirrors PhotonNetwork.AlmostEquals(object, object) (decompile :3207-3249,
        // r4 LOW 11): exact Equals first, then the LIVE public precision fields,
        // strict `<` as in PunExtensions. RECEIVER-LOCAL (r5 LOW 13): these
        // statics are per process and never travel in the payload, so this
        // equals the SENDER's decision only while both seats run the same
        // precision (the defaults) — the contract this diagnostic assumes.
        private static bool VecEqual(UnityEngine.Vector3 a, UnityEngine.Vector3 b)
        {
            return a.Equals(b) || (a - b).sqrMagnitude < PhotonNetwork.PrecisionForVectorSynchronization;
        }
        private static bool VecEqual(UnityEngine.Vector2 a, UnityEngine.Vector2 b)
        {
            return a.Equals(b) || (a - b).sqrMagnitude < PhotonNetwork.PrecisionForVectorSynchronization;
        }
        private static bool FloatEqual(float a, float b)
        {
            return a.Equals(b) || Math.Abs(a - b) < PhotonNetwork.PrecisionForFloatSynchronization;
        }

        internal static void RecordMovementSample(int viewId, UnityEngine.Vector3 pos, UnityEngine.Vector2 vel, UnityEngine.Vector3 dir, UnityEngine.Vector3 aim,
                                                  bool holdJump, bool jump, float sinceGrounded, float timeDelta)
        {
            long t0 = Stopwatch.GetTimestamp();
            try
            {
                if (!_ctxValid || viewId == 0 || viewId != _ctxViewId) return;
                if (_ctxRoomGeneration != _roomGeneration) { _ctxValid = false; return; }
                _ctxValid = false;   // consumed once
                ActorStats actor;
                if (!Actors.TryGetValue(_ctxActor, out actor)) return;
                // r1 HIGH 3: bind the actor's Player movement view the first
                // time the movement Postfix confirms it; timing is keyed to it.
                if (actor.PlayerViewId == 0) actor.PlayerViewId = viewId;
                else if (actor.PlayerViewId != viewId) return;   // a second movement view for one actor: not the Player stream we track
                if (_ctxQuarantined)
                {
                    actor.Room.SamplesWhileInactive++;
                    if (_gameActive) actor.Game.SamplesWhileInactive++;
                    return;
                }
                // The timing commit happens HERE for fighter seats (deferred
                // from Observe until the view was confirmed).
                if (!SpectatorSession.IsLocalSpectator)
                {
                    GapSample sample;
                    CommitTiming(actor, _ctxActor, _ctxNetworkTime, _ctxArrivalTick, out sample);
                }
                // Payload equality (r1 MEDIUM 7 → r4 LOW 11 → r6 LOW 9): ALL EIGHT
                // wire values under THIS SEAT's live PUN element rules (exact
                // Equals; floats within PrecisionForFloatSynchronization; vectors
                // strict `<` on sqrMagnitude vs PrecisionForVectorSynchronization).
                // It reproduces the sender's decision only under the two stated
                // assumptions: equal precision on both seats (the statics are
                // process-local), and timeDelta compared as RECEIVED (post-clamp
                // to [0, 0.1]) where the sender compared the raw value. Reported
                // as payloadEqualGaps; it names no cause.
                bool equal = actor.HasLastPayload
                    && VecEqual(actor.LastPos, pos) && VecEqual(actor.LastVel, vel)
                    && VecEqual(actor.LastDir, dir) && VecEqual(actor.LastAim, aim)
                    && actor.LastHoldJump == holdJump && actor.LastJump == jump
                    && FloatEqual(actor.LastSinceGrounded, sinceGrounded) && FloatEqual(actor.LastTimeDelta, timeDelta);
                // r3 LOW 13: the comparison baseline advances ONLY on a sample the
                // timing window ACCEPTED (baseline or measured) — a rejected
                // reordered packet never becomes the next comparison's base.
                if (actor.Room.LastAccepted)
                {
                    actor.LastPos = pos; actor.LastVel = vel; actor.LastDir = dir; actor.LastAim = aim;
                    actor.LastHoldJump = holdJump; actor.LastJump = jump;
                    actor.LastSinceGrounded = sinceGrounded; actor.LastTimeDelta = timeDelta;
                    actor.HasLastPayload = true;
                }
                if (!_ctxSampled || _ctxArrivalGapMs < ArrivalGapLogThresholdMs) return;
                // r1 MEDIUM 6 / r2 MEDIUM 6: receiver-frame attribution compares
                // like quantities — the RECEIVER'S WALL GAP since its last Update
                // boundary (PUN dispatches in FixedUpdate at the start of the
                // resumed frame, where Time.unscaledDeltaTime is the FIXED step,
                // not the stall) against the DELIVERY EXCESS, 50 ms tolerance.
                int frameMs = NetworkSeatTelemetry.ReceiverWallGapMsNow();
                bool receiverFrame = _ctxExcessMs > 0 && frameMs >= _ctxExcessMs - 50;
                if (equal) { actor.Room.PayloadEqualGaps++; if (_gameActive) actor.Game.PayloadEqualGaps++; }
                if (receiverFrame) { actor.Room.ReceiverFrameGaps++; if (_gameActive) actor.Game.ReceiverFrameGaps++; }
            }
            catch (Exception ex) { VanillaFixSupport.LogError("NetworkReplicaDiagnostics.MovementSample", ex); }
            finally { AddHookCost(Stopwatch.GetTimestamp() - t0); }
        }

        internal static void OnRoomJoined()
        {
            try
            {
                if (PhotonNetwork.OfflineMode)
                {
                    ResetState();
                    VanillaFixSupport.ResetDiag(JitterDiagKey);
                    VanillaFixSupport.ResetDiag(GameSummaryDiagKey);
                    VanillaFixSupport.ResetDiag(ViewSummaryDiagKey);   // r4 MEDIUM 6: the per-room NET-VIEW budget resets on the same room edges
                    NetDiag.RebaseOrphanCounter();
                    return;
                }
                Photon.Realtime.Room currentRoom = PhotonNetwork.CurrentRoom;
                if (_roomActive && ReferenceEquals(_observedRoom, currentRoom))
                {
                    // Serialization can theoretically reach the observer after PUN
                    // installs CurrentRoom but before callbacks finish. Preserve those
                    // first packets instead of treating this callback as a new room.
                    VanillaFixSupport.ResetDiag(JitterDiagKey);
                    VanillaFixSupport.ResetDiag(GameSummaryDiagKey);
                    VanillaFixSupport.ResetDiag(ViewSummaryDiagKey);   // r4 MEDIUM 6: the per-room NET-VIEW budget resets on the same room edges
                    _jitterLogBudgetSpent = false;
                    return;
                }

                // A direct room-to-room transition should still have produced an
                // OnLeftRoom callback. If it did not, preserve the old room's data
                // before replacing it rather than silently merging two sittings.
                if (_roomActive)
                {
                    if (_gameActive)
                        EmitGameSummary(_gameEnded
                            ? "complete"
                            : (_gamePartial ? "partial-room-replaced" : "room-replaced"));
                    EmitRoomSummary("room-replaced");
                }

                ResetState();
                VanillaFixSupport.ResetDiag(JitterDiagKey);
                VanillaFixSupport.ResetDiag(GameSummaryDiagKey);
                VanillaFixSupport.ResetDiag(ViewSummaryDiagKey);   // r4 MEDIUM 6: the per-room NET-VIEW budget resets on the same room edges
                _jitterLogBudgetSpent = false;
                NetDiag.RebaseOrphanCounter();
                _roomActive = true;
                _observedRoom = currentRoom;
                _roomStartedAtMs = Environment.TickCount;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.RoomJoined", ex);
            }
        }

        internal static void OnRoomLeft()
        {
            try
            {
                if (_roomActive)
                {
                    if (_gameActive)
                        EmitGameSummary(_gameEnded
                            ? "complete"
                            : (_gamePartial ? "partial-room-exit" : "room-exit"));
                    EmitRoomSummary("room-exit");
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.RoomLeft", ex);
            }
            finally
            {
                ResetState();
                // Fixed key + reliable exit-edge reset: dynamic room keys grow the
                // dictionary and process-lifetime caps erase later-room evidence (#364).
                VanillaFixSupport.ResetDiag(JitterDiagKey);
                VanillaFixSupport.ResetDiag(GameSummaryDiagKey);
                VanillaFixSupport.ResetDiag(ViewSummaryDiagKey);   // r4 MEDIUM 6: the per-room NET-VIEW budget resets on the same room edges
                _jitterLogBudgetSpent = false;
                NetDiag.RebaseOrphanCounter();
            }
        }

        internal static void OnGameStarted()
        {
            try
            {
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                BeginGame(partial: false);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.GameStarted", ex);
            }
        }

        /// <summary>The observer seat has no local GM lifecycle. A validated
        /// snapshot is its first proof that a live/partial game can be
        /// counted — and the ONLY thing that arms the boundary/terminal
        /// observers below (round-4 finding 4: a live call-in racing the
        /// join's async snapshot response used to open a partial game with
        /// no snapshot evidence at all).</summary>
        private static bool _spectatorSnapshotSeen;

        internal static void SpectatorSnapshotAccepted()
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
                EnsureRoom();
                _spectatorSnapshotSeen = true;
                if (!_gameActive) BeginGame(partial: true);   // BeginGame opens the spectator seat telemetry (r3 MEDIUM 9)
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorSnapshot", ex);
            }
        }

        /// <summary>Called from the already-one-shot GM/FFA observer terminal
        /// signals. Summary emission is deferred so post-score bullet tails stay
        /// in the game that produced them.</summary>
        internal static void SpectatorTerminalObserved()
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
                EnsureRoom();
                // Snapshot-gated (round-4 f4): no accepted snapshot means no
                // countable game to open or close.
                if (!_spectatorSnapshotSeen) return;
                if (!_gameActive) BeginGame(partial: true);
                OnGameEnded();
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorTerminal", ex);
            }
        }

        /// <summary>The first call-in after a terminal score is the next
        /// observer-visible game boundary. Nonterminal round call-ins are no-ops.</summary>
        internal static void SpectatorBoundaryObserved()
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator || SpectatorSession.LeaveRequested) return;
                EnsureRoom();
                // Only a real call-in authorizes the next reconcile to re-open
                // timing. A prior reconcile can otherwise finish after a newer
                // round-end and falsely arm the pick/map transition window.
                _spectatorActivationAllowed = true;
                // Snapshot-gated (round-4 f4): a call-in that outraces the
                // join's async snapshot response must not open a partial game
                // the diagnostic contract says needs snapshot evidence.
                if (!_spectatorSnapshotSeen) return;
                if (!_gameActive) BeginGame(partial: true);
                else if (_gameEnded) BeginGame(partial: false);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorBoundary", ex);
            }
        }

        /// <summary>Spectators suppress the participant writers of
        /// GameManager.battleOngoing. Their own verified activation/round
        /// observation edges provide the equivalent timing-only gate.</summary>
        internal static void SpectatorBattleActive(bool active)
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator) return;
                if (!active)
                {
                    // A round-end invalidates every earlier reconcile's eventual
                    // HasEverActivated=true write. The next call-in re-authorizes
                    // only the attempt scheduled for the next round.
                    _spectatorActivationAllowed = false;
                }
                else if (SpectatorSession.LeaveRequested ||
                         !_spectatorActivationAllowed)
                {
                    return;
                }
                SetBattleActive(active);
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorBattle", ex);
            }
        }

        private static void BeginGame(bool partial)
        {
            EnsureRoom();
            if (_gameActive)
            {
                // A superseded (never-ended) spectator game closes its seat
                // telemetry first so the reopen below is exactly-once.
                if (SpectatorSession.IsLocalSpectator && !_gameEnded) { try { NetworkSeatTelemetry.OnMatchEnded("spectator-superseded"); } catch { } }
                EmitGameSummary(_gameEnded ? "complete" : "superseded");
            }

            _gameOrdinal++;
            _gameActive = true;
            _gameEnded = false;
            _viewLinesEmitted = false;
            _gamePartial = partial;
            _battleActive = false;
            _gameStartedAtMs = Environment.TickCount;
            _gameEndedAtMs = 0;
            _gameOrphans = 0;
            _gameOrphansAtScore = 0;
            _gameOrphanViewsAtScore = 0;
            _gameDroppedActorEvents = 0;
            _gameOrphanViewsOverflowed = false;
            GameOrphanViews.Clear();
            foreach (ActorStats actor in Actors.Values) actor.ResetGame();
            // r2 MEDIUM 7 / r3 MEDIUM 9: EVERY spectator game boundary opens the
            // seat frame telemetry here — the one place spectator games begin —
            // so game 2+ records like game 1; OnGameEnded closes it symmetrically.
            if (SpectatorSession.IsLocalSpectator) { try { NetworkSeatTelemetry.OnMatchStarted(); } catch { } }
        }

        internal static void OnGameEnded()
        {
            try
            {
                if (_roomActive && _gameActive)
                {
                    // Keep the accounting window open through teardown. Bug 235
                    // contains dozens of orphan bullet tails between the score
                    // edge and the next game's start; closing here loses exactly
                    // the causal lifetime failures this probe is meant to count.
                    if (_gameEnded) return;
                    _gameEnded = true;
                    _gameEndedAtMs = Environment.TickCount;
                    _battleActive = false;
                    ClearAllBaselines();
                    EmitGameCheckpoint();
                    EmitViewLines("score");   // r4 LOW 9: the per-view evidence exists at the score edge, not only at a later boundary
                    // Spectator seats have no GameStateWatcher OnGameOver; close
                    // their frame sampling here (fighters close it themselves).
                    if (SpectatorSession.IsLocalSpectator) { try { NetworkSeatTelemetry.OnMatchEnded("spectator-game-ended"); } catch { } }
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.GameEnded", ex);
            }
        }

        /// <summary>Jitter is meaningful only while vanilla says combat is live.
        /// Pick/map/death intervals are expected serialization silences, so every
        /// falling edge clears timing baselines without erasing accumulated totals.</summary>
        internal static void SetBattleActive(bool active)
        {
            try
            {
                active = active && _gameActive && !_gameEnded;
                if (_battleActive == active) return;
                _battleActive = active;
                ClearAllBaselines();
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.BattleEdge", ex);
            }
        }

        /// <summary>Called before PUN's OnSerializeRead body. No control-flow return
        /// value and no ref arguments: this observer cannot suppress or alter vanilla.</summary>
        internal static void Observe(object[] data, RealtimePlayer sender, int networkTime)
        {
            long t0 = Stopwatch.GetTimestamp();
            try
            {
                _warningCandidate = false;
                _warningCandidateCommitted = false;
                _warningCandidateEligible = false;
                if (data == null || data.Length == 0 || !(data[0] is int)) return;
                if (PhotonNetwork.OfflineMode) return;
                bool joinedRoom = PhotonNetwork.InRoom;
                if (joinedRoom) EnsureRoom();
                // InRoom becomes false as soon as PUN enters Leaving, before
                // OnLeftRoom flushes the old room. Queued events can still hit
                // the wrapped warning during that window and belong to it.
                if (!joinedRoom && !_roomActive) return;
                _warningCandidateEligible = true;

                int viewId = (int)data[0];
                PhotonView view = PhotonNetwork.GetPhotonView(viewId);
                bool orphan = view == null; // exact predicate used by PUN's warning branch

                int actorNumber = sender == null ? 0 : sender.ActorNumber;
                int localActor = 0;
                try { localActor = PhotonNetwork.LocalPlayer == null ? 0 : PhotonNetwork.LocalPlayer.ActorNumber; }
                catch { }

                if (orphan)
                {
                    // Counting commits at the transpiled Debug.LogWarning call, not
                    // at this preliminary lookup. That makes the fighter counter
                    // exactly equal to warnings PUN actually emits even if another
                    // prefix later changes control flow or the view registry.
                    _warningCandidate = true;
                    _warningCandidateViewId = viewId;
                    _warningCandidateActor = actorNumber > 0 && actorNumber != localActor
                        ? actorNumber
                        : 0;
                    return;
                }

                // Use live OwnerActorNr, never creator arithmetic: ownership can be
                // transferred. Missing views belong to the orphan diagnostic only.
                if (!joinedRoom || !_battleActive || actorNumber <= 0 ||
                    actorNumber == localActor ||
                    view.OwnerActorNr != actorNumber) return;
                ActorStats actor = GetOrCreateActor(actorNumber);
                if (actor == null) return;

                // v6 §1.1/§1.2: publish the call context for the movement
                // Postfix of THIS view's deserialization (consumed once,
                // cleared by the Finalizer). A Phoenix-quarantined actor's
                // samples are counted, never fed to the gap baseline.
                long arrivalTick = Stopwatch.GetTimestamp();
                _ctxValid = true;
                _ctxViewId = viewId;
                _ctxActor = actorNumber;
                _ctxRoomGeneration = _roomGeneration;
                _ctxNetworkTime = networkTime;
                _ctxArrivalTick = arrivalTick;
                _ctxSampled = false;
                _ctxArrivalGapMs = 0;
                _ctxExcessMs = 0;
                _ctxQuarantined = actor.InactiveOpen;
                if (actor.InactiveOpen) return;

                // impl-review r1 HIGH 3: on FIGHTER seats the timing window is
                // committed ONLY when the movement Postfix confirms this view
                // is the actor's Player movement view (RecordMovementSample) —
                // a bullet or other view owned by the same actor must never
                // advance or dedupe the Player stream's baseline. Spectators run
                // no movement capture in Release A and keep the actor-keyed
                // legacy record (their diagnostics are bundle-only).
                if (!SpectatorSession.IsLocalSpectator) return;
                if (actor.PlayerViewId != 0 && viewId != actor.PlayerViewId) return;

                GapSample sample;
                CommitTiming(actor, actorNumber, networkTime, arrivalTick, out sample);
            }
            catch (Exception ex)
            {
                // The observer is deliberately fail-open. Even its diagnostic error
                // path must never change PUN's receive behavior.
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.Observe", ex);
            }
            finally { AddHookCost(Stopwatch.GetTimestamp() - t0); }
        }

        /// <summary>Replacement for the one warning call in PUN's orphan branch.
        /// The original message is always forwarded; diagnostics cannot mute it.</summary>
        internal static void CountAndForwardOrphanWarning(object message)
        {
            try
            {
                if (_warningCandidateEligible)
                {
                    if (!_warningCandidateCommitted) CommitOrphanCounts();
                    NetDiag.CountOrphanSerialization();
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.OrphanCount", ex);
            }
            finally
            {
                _warningCandidate = false;
                _warningCandidateCommitted = false;
                _warningCandidateEligible = false;
                UnityEngine.Debug.LogWarning(message);
            }
        }

        /// <summary>Runs after the existing spectator mute prefix. HarmonyX
        /// still invokes side-effect prefixes after one has returned false, and
        /// __runOriginal reports that aggregate decision. Commit only when the
        /// exact missing-view candidate was actually suppressed.</summary>
        internal static void CountSuppressedSpectatorOrphan(bool originalWillRun)
        {
            try
            {
                if (originalWillRun || !_warningCandidateEligible ||
                    !_warningCandidate || _warningCandidateCommitted ||
                    !SpectatorSession.IsLocalSpectator) return;
                CommitOrphanCounts();
                _warningCandidateCommitted = true;
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorOrphanCount", ex);
            }
        }

        private static void CommitOrphanCounts()
        {
            EnsureRoom();
            _roomOrphans++;
            if (_warningCandidate)
                TrackDistinct(RoomOrphanViews, _warningCandidateViewId,
                    ref _roomOrphanViewsOverflowed);
            if (_gameActive)
            {
                _gameOrphans++;
                if (_warningCandidate)
                    TrackDistinct(GameOrphanViews, _warningCandidateViewId,
                        ref _gameOrphanViewsOverflowed);
            }

            ActorStats actor = _warningCandidate && _warningCandidateActor > 0
                ? GetOrCreateActor(_warningCandidateActor)
                : null;
            if (actor != null) actor.RecordOrphan(_gameActive);
        }

        private static ActorStats GetOrCreateActor(int actorNumber)
        {
            if (actorNumber <= 0) return null;
            ActorStats actor;
            if (Actors.TryGetValue(actorNumber, out actor)) return actor;
            if (Actors.Count >= MaxTrackedActors)
            {
                _roomDroppedActorEvents++;
                if (_gameActive) _gameDroppedActorEvents++;
                return null;
            }
            actor = new ActorStats();
            Actors.Add(actorNumber, actor);
            return actor;
        }

        private static void EnsureRoom()
        {
            if (_roomActive) return;
            ResetState();
            NetDiag.RebaseOrphanCounter();
            _roomActive = true;
            _observedRoom = PhotonNetwork.CurrentRoom;
            _roomStartedAtMs = Environment.TickCount;
        }

        /// <summary>r3 MEDIUM 8: the actor block's timing basis is explicit on
        /// every line — fighter seats commit timing on the confirmed Player
        /// movement view only (v=2 player-view); spectator seats keep the
        /// actor-keyed legacy record (every owned view) until Release B's
        /// per-view capture. A miner must not compare the two as one unit.</summary>
        private static string TimingBasis()
        {
            return SpectatorSession.IsLocalSpectator ? " v=2 timing=actor-legacy" : " v=2 timing=player-view";
        }

        /// <summary>r3 MEDIUM 8: explicit per-VIEW evidence for fighter seats —
        /// one line per remote actor whose Player movement view was confirmed,
        /// carrying that view's own game window.</summary>
        private static bool _viewLinesEmitted;   // once per game (r4 LOW 9): score edge OR final, never both
        private static void EmitViewLines(string reason)
        {
            if (_viewLinesEmitted) return;
            _viewLinesEmitted = true;
            if (SpectatorSession.IsLocalSpectator || Actors.Count == 0) return;
            var actorNumbers = new List<int>(Actors.Keys);
            actorNumbers.Sort();
            foreach (int actorNumber in actorNumbers)
            {
                ActorStats actor = Actors[actorNumber];
                if (actor.PlayerViewId == 0) continue;
                TimingWindow w = actor.Game;
                if (w.Views == 0) continue;
                VanillaFixSupport.DiagLimited(
                    ViewSummaryDiagKey,
                    "[NET-VIEW] v=2 game=" + _gameOrdinal.ToString(CultureInfo.InvariantCulture) +
                    " reason=" + reason +
                    " actor=" + actorNumber.ToString(CultureInfo.InvariantCulture) +
                    " view=" + actor.PlayerViewId.ToString(CultureInfo.InvariantCulture) +
                    " batches=" + w.Batches.ToString(CultureInfo.InvariantCulture) +
                    " gap300=" + w.Gap300.ToString(CultureInfo.InvariantCulture) +
                    " gap750=" + w.Gap750.ToString(CultureInfo.InvariantCulture) +
                    " gap1500=" + w.Gap1500.ToString(CultureInfo.InvariantCulture) +
                    " maxGap=" + w.MaxArrivalGapMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                    " jit150=" + w.Jitter150.ToString(CultureInfo.InvariantCulture) +
                    " maxJit=" + w.MaxDeliveryExcessMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                    " reorder=" + w.Reordered.ToString(CultureInfo.InvariantCulture) +
                    " payloadEqualGaps=" + w.PayloadEqualGaps.ToString(CultureInfo.InvariantCulture) +
                    " rxFrameGaps=" + w.ReceiverFrameGaps.ToString(CultureInfo.InvariantCulture) +
                    " phoenix=" + w.PhoenixIntervals.ToString(CultureInfo.InvariantCulture) + "/" + w.PhoenixMs.ToString(CultureInfo.InvariantCulture) + "ms" +
                    " quarantined=" + w.SamplesWhileInactive.ToString(CultureInfo.InvariantCulture),
                    ViewSummaryLogMaximumPerRoom);
            }
        }
        private const string ViewSummaryDiagKey = "net-view";
        private const int ViewSummaryLogMaximumPerRoom = 64;

        private static void EmitGameSummary(string reason)
        {
            if (_gameEnded)
            {
                EmitGameTailSummary(reason);
            }
            else
            {
                LogGameLine(
                    "[NET-GAME]", "final", reason,
                    ElapsedMs(_gameStartedAtMs), 0);
            }
            EmitViewLines(reason);
            _gameActive = false;
            _gameEnded = false;
            _gamePartial = false;
            _battleActive = false;
            _gameEndedAtMs = 0;
        }

        private static void EmitGameCheckpoint()
        {
            _gameOrphansAtScore = _gameOrphans;
            _gameOrphanViewsAtScore = GameOrphanViews.Count;
            LogGameLine(
                "[NET-GAME]",
                "score",
                "score-edge-tail-pending",
                ElapsedBetweenMs(_gameStartedAtMs, _gameEndedAtMs),
                0);
        }

        private static void EmitGameTailSummary(string reason)
        {
            long tailOrphans = _gameOrphans - _gameOrphansAtScore;
            if (tailOrphans < 0) tailOrphans = 0;
            int newViews = GameOrphanViews.Count - _gameOrphanViewsAtScore;
            if (newViews < 0) newViews = 0;
            string newViewsText = _gameOrphanViewsOverflowed
                ? "unknown"
                : newViews.ToString(CultureInfo.InvariantCulture);
            VanillaFixSupport.DiagLimited(
                GameSummaryDiagKey,
                "[NET-GAME-TAIL]" + TimingBasis() + " game=" + _gameOrdinal.ToString(CultureInfo.InvariantCulture) +
                " reason=" + reason +
                " tail=" + ElapsedMs(_gameEndedAtMs).ToString(CultureInfo.InvariantCulture) + "ms" +
                " orphanSer=+" + tailOrphans.ToString(CultureInfo.InvariantCulture) +
                " orphanViewsNew=" + newViewsText +
                " orphanSerFinal=" + _gameOrphans.ToString(CultureInfo.InvariantCulture) +
                " orphanViewsFinal=" + DistinctText(
                    GameOrphanViews.Count, _gameOrphanViewsOverflowed) +
                ActorSummary(game: true),
                GameSummaryLogMaximumPerRoom);
        }

        private static void LogGameLine(
            string prefix, string phase, string reason, int duration, int tailDuration)
        {
            VanillaFixSupport.DiagLimited(
                GameSummaryDiagKey,
                prefix + TimingBasis() + " game=" + _gameOrdinal.ToString(CultureInfo.InvariantCulture) +
                " phase=" + phase +
                " reason=" + reason +
                " partial=" + (_gamePartial ? "true" : "false") +
                " duration=" + duration.ToString(CultureInfo.InvariantCulture) + "ms" +
                " tail=" + tailDuration.ToString(CultureInfo.InvariantCulture) + "ms" +
                " orphanSer=" + _gameOrphans.ToString(CultureInfo.InvariantCulture) +
                " orphanViews=" + DistinctText(GameOrphanViews.Count, _gameOrphanViewsOverflowed) +
                " droppedActorEvents=" + _gameDroppedActorEvents.ToString(CultureInfo.InvariantCulture) +
                ActorSummary(game: true),
                GameSummaryLogMaximumPerRoom);
        }

        private static void EmitRoomSummary(string reason)
        {
            int elapsed = ElapsedMs(_roomStartedAtMs);
            Plugin.Log?.LogInfo(
                "[NET-ROOM]" + TimingBasis() + " reason=" + reason +
                " duration=" + elapsed.ToString(CultureInfo.InvariantCulture) + "ms" +
                " games=" + _gameOrdinal.ToString(CultureInfo.InvariantCulture) +
                " orphanSer=" + _roomOrphans.ToString(CultureInfo.InvariantCulture) +
                " orphanViews=" + DistinctText(RoomOrphanViews.Count, _roomOrphanViewsOverflowed) +
                " droppedActorEvents=" + _roomDroppedActorEvents.ToString(CultureInfo.InvariantCulture) +
                ActorSummary(game: false));
        }

        private static string ActorSummary(bool game)
        {
            if (Actors.Count == 0) return " actors=none";

            var actorNumbers = new List<int>(Actors.Keys);
            actorNumbers.Sort();
            var text = new StringBuilder(160);
            text.Append(" actors=");
            bool wrote = false;
            int writtenActors = 0;
            int omitted = 0;
            foreach (int actorNumber in actorNumbers)
            {
                ActorStats actor = Actors[actorNumber];
                TimingWindow window = game ? actor.Game : actor.Room;
                long orphans = game ? actor.GameOrphans : actor.RoomOrphans;
                if (game && window.Views == 0 && orphans == 0) continue;
                if (writtenActors >= MaxActorsPerSummary)
                {
                    omitted++;
                    continue;
                }
                if (wrote) text.Append(';');
                wrote = true;
                writtenActors++;
                text.Append('a').Append(actorNumber.ToString(CultureInfo.InvariantCulture));
                text.Append("{views=").Append(window.Views.ToString(CultureInfo.InvariantCulture));
                text.Append(",batches=").Append(window.Batches.ToString(CultureInfo.InvariantCulture));
                text.Append(",gap300=").Append(window.Gap300.ToString(CultureInfo.InvariantCulture));
                text.Append(",gap750=").Append(window.Gap750.ToString(CultureInfo.InvariantCulture));
                text.Append(",gap1500=").Append(window.Gap1500.ToString(CultureInfo.InvariantCulture));
                text.Append(",maxGap=").Append(window.MaxArrivalGapMs.ToString(CultureInfo.InvariantCulture)).Append("ms");
                text.Append(",jit150=").Append(window.Jitter150.ToString(CultureInfo.InvariantCulture));
                text.Append(",maxJit=").Append(window.MaxDeliveryExcessMs.ToString(CultureInfo.InvariantCulture)).Append("ms");
                text.Append(",reorder=").Append(window.Reordered.ToString(CultureInfo.InvariantCulture));
                // v6 §1.1/§1.2: gap classification — payloadEqualGaps = gaps that
                // ended with a payload inside PUN's unchanged-tolerance (what an
                // UnreliableOnChange sender stops sending for); rxFrameGaps =
                // gaps whose delivery excess this seat's own frame covered;
                // Phoenix intervals are quarantined lifecycle. None of these is
                // a leg attribution.
                text.Append(",playerView=").Append(actor.PlayerViewId.ToString(CultureInfo.InvariantCulture));
                text.Append(",payloadEqualGaps=").Append(window.PayloadEqualGaps.ToString(CultureInfo.InvariantCulture));
                text.Append(",rxFrameGaps=").Append(window.ReceiverFrameGaps.ToString(CultureInfo.InvariantCulture));
                text.Append(",phoenix=").Append(window.PhoenixIntervals.ToString(CultureInfo.InvariantCulture));
                text.Append('/').Append(window.PhoenixMs.ToString(CultureInfo.InvariantCulture)).Append("ms");
                text.Append(",quarantined=").Append(window.SamplesWhileInactive.ToString(CultureInfo.InvariantCulture));
                text.Append(",orphan=").Append(orphans.ToString(CultureInfo.InvariantCulture)).Append('}');
            }
            if (!wrote) text.Append("none");
            if (omitted > 0)
                text.Append(";...+").Append(omitted.ToString(CultureInfo.InvariantCulture));
            return text.ToString();
        }

        private static void ClearAllBaselines()
        {
            foreach (ActorStats actor in Actors.Values)
            {
                actor.Room.ClearBaseline();
                actor.Game.ClearBaseline();
            }
        }

        private static void TrackDistinct(HashSet<int> set, int viewId, ref bool overflowed)
        {
            if (set.Count < MaxDistinctOrphanViews)
            {
                set.Add(viewId);
                return;
            }
            if (!set.Contains(viewId)) overflowed = true;
        }

        private static string DistinctText(int count, bool overflowed)
        {
            return (overflowed ? ">=" : string.Empty) +
                   count.ToString(CultureInfo.InvariantCulture);
        }

        private static int ElapsedMs(int startedAtMs)
        {
            return ElapsedBetweenMs(startedAtMs, Environment.TickCount);
        }

        private static int ElapsedBetweenMs(int startedAtMs, int endedAtMs)
        {
            int elapsed = unchecked(endedAtMs - startedAtMs);
            return elapsed < 0 ? 0 : elapsed;
        }

        private static void ResetState()
        {
            _roomGeneration++;   // v6 §1.1: invalidates any stale receive context
            NetworkSeatTelemetry.OnRoomChanged();
            _roomActive = false;
            _gameActive = false;
            _gameEnded = false;
            _gamePartial = false;
            _battleActive = false;
            _spectatorActivationAllowed = false;
            _spectatorSnapshotSeen = false;
            _jitterLogBudgetSpent = false;
            _observedRoom = null;
            _roomOrphanViewsOverflowed = false;
            _gameOrphanViewsOverflowed = false;
            _roomStartedAtMs = 0;
            _gameStartedAtMs = 0;
            _gameEndedAtMs = 0;
            _gameOrdinal = 0;
            _roomOrphans = 0;
            _gameOrphans = 0;
            _gameOrphansAtScore = 0;
            _gameOrphanViewsAtScore = 0;
            _roomDroppedActorEvents = 0;
            _gameDroppedActorEvents = 0;
            Actors.Clear();
            RoomOrphanViews.Clear();
            GameOrphanViews.Clear();
        }

        private sealed class ActorStats
        {
            internal readonly TimingWindow Room = new TimingWindow();
            internal readonly TimingWindow Game = new TimingWindow();
            internal long RoomOrphans;
            internal long GameOrphans;
            // v6 §1.2 lifecycle: an open Phoenix quarantine interval.
            internal bool InactiveOpen;
            internal long InactiveSinceTick;
            // r1 HIGH 3: the actor's Player movement view — timing is keyed to
            // it on fighter seats; 0 until the movement Postfix confirms it.
            internal int PlayerViewId;
            // v6 §1.1 payload-equality baseline (all EIGHT wire values — r3 MEDIUM 11).
            internal bool HasLastPayload;
            internal UnityEngine.Vector3 LastPos;
            internal UnityEngine.Vector2 LastVel;
            internal UnityEngine.Vector3 LastDir;
            internal UnityEngine.Vector3 LastAim;
            internal bool LastHoldJump, LastJump;          // r3 MEDIUM 11: PUN compares every element
            internal float LastSinceGrounded, LastTimeDelta;

            internal void RecordOrphan(bool gameActive)
            {
                RoomOrphans++;
                if (gameActive) GameOrphans++;
            }

            internal void ResetGame()
            {
                Game.Reset();
                GameOrphans = 0;
                InactiveOpen = false;
                HasLastPayload = false;
                // PlayerViewId is per ROOM (actor views persist across games).
            }
        }

        private sealed class TimingWindow
        {
            internal long Views;
            internal long Batches;
            internal long Gap300;
            internal long Gap750;
            internal long Gap1500;
            internal long Jitter150;
            internal long Reordered;
            internal int MaxArrivalGapMs;
            internal int MaxDeliveryExcessMs;
            // v6 §1.1/§1.2 classification counters.
            internal long PayloadEqualGaps;
            internal long ReceiverFrameGaps;
            internal long PhoenixIntervals;
            internal long PhoenixMs;
            internal long SamplesWhileInactive;
            internal bool LastAccepted;   // r3 LOW 13: the last Record call advanced the baseline (baseline or measured)

            private bool _hasBaseline;
            private int _lastNetworkTime;
            private int _lastSeenNetworkTime;
            private long _lastArrivalTick;

            internal void Record(int networkTime, long arrivalTick, out GapSample sample)
            {
                Views++;
                sample = default(GapSample);
                LastAccepted = false;

                if (!_hasBaseline)
                {
                    _hasBaseline = true;
                    LastAccepted = true;
                    _lastNetworkTime = networkTime;
                    _lastSeenNetworkTime = networkTime;
                    _lastArrivalTick = arrivalTick;
                    Batches++;
                    return;
                }

                if (networkTime == _lastSeenNetworkTime) return; // another view in this batch
                _lastSeenNetworkTime = networkTime;

                int senderGap = unchecked(networkTime - _lastNetworkTime);
                // An older unreliable batch is not a new timing baseline. Timestamp
                // wrap remains a small positive subtraction and passes this gate.
                if (senderGap <= 0)
                {
                    Reordered++;
                    return;
                }

                long arrivalTicks = arrivalTick - _lastArrivalTick;
                int arrivalGap = arrivalTicks < 0
                    ? -1
                    : (int)Math.Min(int.MaxValue,
                        arrivalTicks * 1000L / Stopwatch.Frequency);

                _lastNetworkTime = networkTime;
                _lastArrivalTick = arrivalTick;
                Batches++;
                LastAccepted = true;
                if (arrivalGap < 0 || arrivalGap > MaxMeasuredGapMs ||
                    senderGap > MaxMeasuredGapMs) return;

                if (arrivalGap >= 300) Gap300++;
                if (arrivalGap >= 750) Gap750++;
                if (arrivalGap >= 1500) Gap1500++;
                if (arrivalGap > MaxArrivalGapMs) MaxArrivalGapMs = arrivalGap;

                int deliveryExcess = arrivalGap - senderGap;
                if (deliveryExcess < 0) deliveryExcess = 0;
                if (deliveryExcess >= JitterLogThresholdMs) Jitter150++;
                if (deliveryExcess > MaxDeliveryExcessMs)
                    MaxDeliveryExcessMs = deliveryExcess;

                sample = new GapSample(arrivalGap, senderGap, deliveryExcess);
            }

            internal void Reset()
            {
                Views = 0;
                Batches = 0;
                Gap300 = 0;
                Gap750 = 0;
                Gap1500 = 0;
                Jitter150 = 0;
                Reordered = 0;
                MaxArrivalGapMs = 0;
                MaxDeliveryExcessMs = 0;
                PayloadEqualGaps = 0;
                ReceiverFrameGaps = 0;
                PhoenixIntervals = 0;
                PhoenixMs = 0;
                SamplesWhileInactive = 0;
                LastAccepted = false;
                _hasBaseline = false;
                _lastNetworkTime = 0;
                _lastSeenNetworkTime = 0;
                _lastArrivalTick = 0;
            }

            internal void ClearBaseline()
            {
                _hasBaseline = false;
                _lastNetworkTime = 0;
                _lastSeenNetworkTime = 0;
                _lastArrivalTick = 0;
            }
        }

        private struct GapSample
        {
            internal readonly bool Valid;
            internal readonly int ArrivalGapMs;
            internal readonly int SenderGapMs;
            internal readonly int DeliveryExcessMs;

            internal GapSample(int arrivalGapMs, int senderGapMs, int deliveryExcessMs)
            {
                Valid = true;
                ArrivalGapMs = arrivalGapMs;
                SenderGapMs = senderGapMs;
                DeliveryExcessMs = deliveryExcessMs;
            }
        }
    }

    /// <summary>Bug 235: observe PUN's exact orphan-warning site on every seat.
    /// The old counter lived only in a spectator-only suppression prefix, so fighter
    /// logs reported +0 while PUN emitted thousands of missing-view warnings.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSerializationObserverPatch
    {
        private const string MissingViewWarningFragment =
            ". We have no such PhotonView! Ignore this if you're joining or leaving a room. State: ";

        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(PhotonNetwork),
                "OnSerializeRead",
                new[] { typeof(object[]), typeof(RealtimePlayer), typeof(int), typeof(short) });
            if (method == null)
                throw new Exception("PhotonNetwork.OnSerializeRead(object[], Player, int, short) not found - network replica diagnostics have no target");
            return method;
        }

        // Higher than the spectator mute's Priority.First prefix. This observer is
        // void/no-ref and cannot skip the original; positional binds avoid Harmony's
        // per-packet object[] __args allocation on this receive hot path (#364).
        [HarmonyPrefix]
        [HarmonyPriority(Priority.First + 1)]
        private static void Prefix(object[] __0, RealtimePlayer __1, int __2)
        {
            NetworkReplicaDiagnostics.Observe(__0, __1, __2);
        }

        // v6 §1.1: the receive context is cleared on EVERY exit of the
        // original (every early return, the sibling mute's suppression, a
        // movement exception) — and the exception, if any, is returned
        // unchanged so this observer can never swallow a PUN fault.
        [HarmonyFinalizer]
        private static Exception Finalizer(Exception __exception)
        {
            try { NetworkReplicaDiagnostics.ClearReceiveContext(); } catch { }
            return __exception;
        }

        // Existing spectator mute is Priority.First. HarmonyX evaluates all
        // side-effect prefixes, so this runs immediately after it and observes
        // the aggregate skip decision without changing that decision.
        [HarmonyPrefix]
        [HarmonyPriority(Priority.First - 1)]
        private static void AfterSpectatorMute(bool __runOriginal)
        {
            NetworkReplicaDiagnostics.CountSuppressedSpectatorOrphan(__runOriginal);
        }

        [HarmonyTranspiler]
        private static IEnumerable<CodeInstruction> Transpiler(
            IEnumerable<CodeInstruction> instructions)
        {
            var result = new List<CodeInstruction>(instructions);
            MethodInfo originalWarning = AccessTools.Method(
                typeof(UnityEngine.Debug), "LogWarning", new[] { typeof(object) });
            MethodInfo replacement = AccessTools.Method(
                typeof(NetworkReplicaDiagnostics),
                nameof(NetworkReplicaDiagnostics.CountAndForwardOrphanWarning));
            if (originalWarning == null || replacement == null)
                throw new Exception("orphan warning methods could not be resolved");

            int fragmentCount = 0;
            int warningCallCount = 0;
            int warningCallIndex = -1;
            for (int i = 0; i < result.Count; i++)
            {
                if (result[i].operand is string text &&
                    string.Equals(text, MissingViewWarningFragment,
                        StringComparison.Ordinal))
                    fragmentCount++;
                if (Equals(result[i].operand, originalWarning))
                {
                    warningCallCount++;
                    warningCallIndex = i;
                }
            }

            // OnSerializeRead currently has one missing-view LogWarning; its other
            // branches use LogError/Log. Both anchors must stay unique so a PUN
            // update fails attach loudly instead of counting a different warning.
            if (fragmentCount != 1 || warningCallCount != 1 || warningCallIndex < 0)
                throw new Exception(
                    "PhotonNetwork.OnSerializeRead orphan warning IL drifted " +
                    "(fragment=" + fragmentCount.ToString(CultureInfo.InvariantCulture) +
                    ", calls=" + warningCallCount.ToString(CultureInfo.InvariantCulture) + ")");

            result[warningCallIndex].operand = replacement;
            return result;
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSerializationObserver", exception);
        }
    }

    /// <summary>Spectator GM lifecycle is suppressed, but this method is called
    /// only after the observer has computed a terminal score from the fighter RPC.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorGmTerminalPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(SpectatorSync), nameof(SpectatorSync.OnGameOverObserved), Type.EmptyTypes);
            if (method == null)
                throw new Exception("SpectatorSync.OnGameOverObserved() not found - spectator network diagnostics have no GM terminal signal");
            return method;
        }

        [HarmonyPrefix]
        private static void Prefix()
        {
            NetworkReplicaDiagnostics.SpectatorTerminalObserved();
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorGmTerminal", exception);
        }
    }

    /// <summary>FFA's private observer terminal detector is already one-shot.
    /// Capture only its false-to-true transition instead of duplicating score math.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorFfaTerminalPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(FfaMode), "SpectatorCheckGameOver", Type.EmptyTypes);
            if (method == null)
                throw new Exception("FfaMode.SpectatorCheckGameOver() not found - spectator network diagnostics have no FFA terminal signal");
            return method;
        }

        [HarmonyPrefix]
        private static void Prefix(bool ___spectatorGameOverAnnounced, out bool __state)
        {
            __state = ___spectatorGameOverAnnounced;
        }

        [HarmonyPostfix]
        private static void Postfix(bool __state, bool ___spectatorGameOverAnnounced)
        {
            if (!__state && ___spectatorGameOverAnnounced)
                NetworkReplicaDiagnostics.SpectatorTerminalObserved();
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorFfaTerminal", exception);
        }
    }

    /// <summary>After a terminal score, the next fighter-issued map call-in is
    /// the spectator's first reliable new-game boundary. Other round call-ins
    /// are ignored by the diagnostics state machine.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorBoundaryPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(SpectatorSync), nameof(SpectatorSync.OnCallInObserved),
                new[] { typeof(int) });
            if (method == null)
                throw new Exception("SpectatorSync.OnCallInObserved(int) not found - spectator network diagnostics have no game boundary signal");
            return method;
        }

        [HarmonyPostfix]
        private static void Postfix()
        {
            NetworkReplicaDiagnostics.SpectatorBoundaryObserved();
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorBoundary", exception);
        }
    }

    /// <summary>The spectator reconcile sets this property true only after the
    /// commanded map, current-master snapshot, bodies and decks have all applied.
    /// It is the observer seat's battle-resume edge on every round.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorActivationPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.PropertySetter(
                typeof(SpectatorSync), nameof(SpectatorSync.HasEverActivated));
            if (method == null)
                throw new Exception("SpectatorSync.HasEverActivated setter not found - spectator jitter has no battle-resume signal");
            return method;
        }

        [HarmonyPostfix]
        private static void Postfix(bool __0)
        {
            NetworkReplicaDiagnostics.SpectatorBattleActive(__0);
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorActivation", exception);
        }
    }

    /// <summary>The deduped spectator round latch is set as soon as a fighter's
    /// NextRound RPC arrives, before the transition. It closes timing baselines
    /// without relying on the suppressed local GM state machine.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorRoundEndPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(SpectatorSync), nameof(SpectatorSync.LatchRoundObservation),
                Type.EmptyTypes);
            if (method == null)
                throw new Exception("SpectatorSync.LatchRoundObservation() not found - spectator jitter has no round-end signal");
            return method;
        }

        [HarmonyPrefix]
        private static void Prefix()
        {
            NetworkReplicaDiagnostics.SpectatorBattleActive(false);
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorRoundEnd", exception);
        }
    }

    /// <summary>A current-master protocol snapshot is the observer seat's first
    /// trustworthy proof that a partial game accounting window can be armed.</summary>
    [HarmonyPatch]
    internal static class NetworkReplicaSpectatorSnapshotPatch
    {
        private static MethodBase TargetMethod()
        {
            MethodInfo method = AccessTools.Method(
                typeof(SpectatorSync), "HandleSnapshot",
                new[] { typeof(ExitGames.Client.Photon.EventData) });
            if (method == null)
                throw new Exception("SpectatorSync.HandleSnapshot(EventData) not found - spectator network diagnostics cannot arm partial games");
            return method;
        }

        [HarmonyPostfix]
        private static void Postfix(ExitGames.Client.Photon.EventData __0)
        {
            try
            {
                if (!SpectatorSession.IsLocalSpectator || __0 == null) return;
                object[] data = __0.CustomData as object[];
                if (data == null || data.Length < 16 ||
                    !(data[0] is byte) || (byte)data[0] != SpectatorSession.PROTOCOL ||
                    !(data[1] is int)) return;
                RealtimePlayer master = PhotonNetwork.MasterClient;
                if (master == null || master.ActorNumber != __0.Sender) return;
                NetworkReplicaDiagnostics.SpectatorSnapshotAccepted();

                // A late-joining spectator can first learn the decisive score
                // from this snapshot, after the live terminal RPC has already
                // passed. GM uses the local GM threshold. FFA needs its OWN
                // replay here (round-5 finding 1): FfaMode's seeded-score
                // detector fires SYNCHRONOUSLY inside HandleSnapshot — BEFORE
                // this postfix arms _spectatorSnapshotSeen — and its one-shot
                // terminal latch will not fire again, so without this replay a
                // terminal-at-join FFA game opened a partial window that never
                // closed and merged the next game's diagnostics into it.
                string mode = data[2] as string ?? string.Empty;
                int[] rounds = data[11] as int[];
                if (rounds != null && !string.IsNullOrEmpty(mode))
                {
                    int roundsToWin;
                    if (string.Equals(mode, "ffa", StringComparison.Ordinal))
                    {
                        roundsToWin = FfaMode.RoundsToWin;
                        if (roundsToWin <= 0) roundsToWin = 5;
                    }
                    else
                    {
                        GM_ArmsRace gm = GM_ArmsRace.instance;
                        if (gm == null)
                            gm = UnityEngine.Object.FindObjectOfType<GM_ArmsRace>(true);
                        roundsToWin = gm != null && gm.roundsToWinGame > 0 ? gm.roundsToWinGame : 5;
                    }
                    for (int i = 0; i < rounds.Length; i++)
                    {
                        if (rounds[i] < roundsToWin) continue;
                        NetworkReplicaDiagnostics.SpectatorTerminalObserved();
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                VanillaFixSupport.LogError("NetworkReplicaDiagnostics.SpectatorSnapshotHook", ex);
            }
        }

        [HarmonyCleanup]
        private static Exception Cleanup(MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            return VanillaFixSupport.Cleanup("NetworkReplicaSpectatorSnapshot", exception);
        }
    }
}
