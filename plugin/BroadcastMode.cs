using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// SCR Broadcast (design ai-collab/broadcast-architecture.md v8) — the
    /// DIRECTOR that turns the spectator system into an unattended broadcast
    /// seat, plus the always-on service-account fences and log masking.
    ///
    /// Three independent layers live here, with three different gates:
    ///
    ///   1. §2c CLIENT FENCE — keyed to IDENTITY ONLY (local steam id in
    ///      BroadcastAccounts). Always on; `Broadcast.Enabled` cannot turn it
    ///      off. The account must never fight: it leaves any online room it
    ///      holds without a spectator session, and every fighter-path funnel
    ///      (queue joins, bets, chat send, match reports) early-returns via
    ///      FenceBlocksFighterPath().
    ///   2. §7.1 LOG MASKING — keyed to IDENTITY ONLY, same reason. Room
    ///      credentials (and deterministic derivatives — a 32-bit hash is a
    ///      brute-force verifier over the small room-code space, r2-F2) never
    ///      reach this seat's logs; SafeRoomDesc() is the one token source.
    ///   3. §3a DIRECTOR — keyed to identity AND `Broadcast.Enabled`. A state
    ///      machine driven by Step() from the persistent behaviour's Update
    ///      (#16/#17: never a coroutine on a destructible host — Step survives
    ///      NetworkRestart by construction).
    ///
    /// The §3b status LEASE (C:\broadcast\state\status.json) is written ~1/s
    /// while the director is enabled; the VM bot consumes it. It never carries
    /// the room name or region.
    ///
    /// Inertness proof for every other install: BroadcastAccounts contains
    /// only the broadcast bot's steam id, so IsBroadcastIdentity is false on
    /// every player's machine and all three layers are pass-through; the
    /// config default is false besides.
    /// </summary>
    internal static class BroadcastMode
    {
        // ── identity ─────────────────────────────────────────────────────

        /// <summary>The service/broadcast accounts (§2c). Server twin:
        /// SPECTATE_BROADCAST_STEAM_IDS in main.py — keep in lockstep.</summary>
        private static readonly string[] BroadcastAccounts = { "76561198709950406" };

        private static bool _identityLatched;

        /// <summary>True when this client runs under a broadcast account.
        /// LATCHED once seen (§7.1: masking latches to identity; a config
        /// flip mid-session cannot unmask). Steam identity cannot change
        /// without a relaunch, so latching loses nothing.</summary>
        internal static bool IsBroadcastIdentity
        {
            get
            {
                if (_identityLatched) return true;
                try
                {
                    string sid = MatchTracker.LocalSteamId;
                    if (string.IsNullOrEmpty(sid)) return false;
                    for (int i = 0; i < BroadcastAccounts.Length; i++)
                        if (string.Equals(BroadcastAccounts[i], sid, StringComparison.Ordinal))
                        {
                            _identityLatched = true;
                            return true;
                        }
                }
                catch { }
                return false;
            }
        }

        /// <summary>r3 finding 10 (idle-throttle gate): any non-Idle director
        /// state — granting, joining, watching, leaving, recovering — means
        /// this seat is NOT out of play. Regular players' director never
        /// starts, so this is permanently false off the broadcast seat.</summary>
        internal static bool DirectorBusy => _state != State.Idle;

        /// <summary>Director gate: identity AND the config flag. The §2c fence
        /// and §7.1 masking deliberately do NOT use this (identity only).</summary>
        internal static bool DirectorActive
        {
            get
            {
                try { return IsBroadcastIdentity && Plugin.BroadcastEnabled != null && Plugin.BroadcastEnabled.Value; }
                catch { return false; }
            }
        }

        // ── §2c fence (b): fighter-path funnels ──────────────────────────

        /// <summary>One identity check for every fighter-path funnel (§2c):
        /// queue/lobby joins, bet submission, chat send, match reports. The
        /// server enforces the same policy authoritatively (layers 1-3); this
        /// is the client half so the account never even asks. Returns true =
        /// caller must early-return.</summary>
        internal static bool FenceBlocksFighterPath(string what)
        {
            if (!IsBroadcastIdentity) return false;
            try { Plugin.Log?.LogInfo($"[BROADCAST] §2c fence blocked fighter path: {what}"); } catch { }
            return true;
        }

        // ── §7.1 masking ─────────────────────────────────────────────────

        private static string _corrToken = "";
        private static float _corrSessionStamp = -1f;

        /// <summary>§7.1: the ONE safe room descriptor for broadcast-seat
        /// logs. Returns the PUBLIC game id when a spectator session has one,
        /// else a random per-session correlation token — never the room name
        /// and never a deterministic derivative of it (r2-F2). The token
        /// regenerates when the session changes (keyed on SessionStartedAt),
        /// so lines from different sessions cannot be correlated into one.</summary>
        internal static string SafeRoomDesc()
        {
            try
            {
                string gid = SpectatorSession.WatchingGameId;
                if (!string.IsNullOrEmpty(gid)) return "game:" + gid;
                float stamp = 0f;
                try { stamp = SpectatorSession.SessionStartedAt; } catch { }
                if (_corrToken.Length == 0 || stamp != _corrSessionStamp)
                {
                    _corrSessionStamp = stamp;
                    _corrToken = Guid.NewGuid().ToString("N").Substring(0, 8);
                }
                return "room#" + _corrToken;
            }
            catch { return "room#?"; }
        }

        // ── shared-flow ticket generation (#367 pattern) ─────────────────
        //
        // The public spectate flow keeps its own latches (spectateGrantInFlight,
        // SpectatorJoiner._running). Under the director those latches become
        // ticket-OWNED: callbacks capture this generation at dispatch and a
        // CancelAcquisition bump makes every captured copy stale — stale
        // callbacks no-op and release their latch. When no ticket ever exists
        // (every non-broadcast install) the generation never moves, every
        // staleness check passes, and the public paths behave identically.

        private static int _sharedFlowGen;
        internal static int SharedFlowGeneration => _sharedFlowGen;
        internal static bool SharedFlowStale(int gen) => gen != _sharedFlowGen;

        // ── director state ───────────────────────────────────────────────

        private enum State
        {
            Idle,
            Granting,
            Joining,
            AwaitingActivation,
            Watching,
            Leaving,
            Cancelling,   // CancelAcquisition's bounded verify phase (§3a)
            Recover,
            Faulted,
        }

        /// <summary>§3a: the acquisition ticket. Owns one grant->join->
        /// activation arc; every budget and quarantine key hangs off it.</summary>
        private sealed class SpectateAcquisition
        {
            public string TicketId;
            public string GameId;
            public string Incarnation;
            public int FlowGenAtStart;
            /// <summary>Owner token of the grant dispatch this ticket caused
            /// (ApiClient grant seq; 0 = never dispatched). CancelAcquisition
            /// CAS-releases the grant latch against THIS token only, so a
            /// successor public grant's latch is never clobbered (r1 F6).</summary>
            public int GrantSeq;
            public float StartedAt;
            public float PhaseStartedAt;
            /// <summary>W7 latch: the activation-edge report note already ran
            /// for THIS ticket (D1 f8 — once per ticket, at the first Watching
            /// tick). A rotation back onto the same game is a new ticket and
            /// gets a fresh note; this arc can never double-note.</summary>
            public bool ReportNoted;
        }

        private static State _state = State.Idle;
        private static SpectateAcquisition _ticket;
        /// <summary>Last target payload for the game the ticket points at —
        /// the HUD's metadata source (§4: never the public games cache).</summary>
        internal static ApiClient.BroadcastTargetInfo CurrentTargetMeta { get; private set; }

        private static float _nextPollAt;
        private static bool _pollInFlight;
        private static float _activatedAt = -1f;

        // LEAVING budget bookkeeping (90s: 0 invoke / 30 re-invoke / 60
        // Disconnect / 90 FAULTED — §3a r2-F4).
        private static float _leaveStartedAt;
        private static bool _leaveReinvoked;
        private static bool _leaveDisconnected;
        private static bool _leavingDueToFailure;

        // CANCELLING verify (20s -> FAULTED). _cancelUnwindDone=false means
        // the teardown is DEFERRED because a room-bound Photon op (a JoinRoom
        // carrying our staged cr_spec) is still in flight — see r1 F1.
        private static float _cancelStartedAt;
        private static string _cancelReason = "";
        private static bool _cancelUnwindDone;

        // RECOVER backoff (30s -> IDLE).
        private static float _recoverUntil;

        private static string _faultReason = "";

        // Last SpectatorSync.LeaveToMenu reason observed (via NoteSessionLeave)
        // — how the director classifies a session death it did not order.
        private static string _lastLeaveReason = "";

        // §2c fence (a) throttle.
        private static float _nextFenceKickAt;

        // ── quarantine / exclusion table (§2a r6-B2 + §3a r5-F4) ─────────

        private sealed class ExclusionEntry
        {
            public string Incarnation;
            public string GameId;
            public string Reason;
            public float ExpiresAt;
        }

        private const int EXCLUDE_MAX = 8;                    // §2a bound
        private const float PRE_ROOM_BLACKLIST_SECONDS = 60f; // §3a RECOVER
        private const float QUARANTINE_FIRST_SECONDS = 60f;   // §3a r5-F4
        private const float QUARANTINE_REPEAT_SECONDS = 600f;
        private static readonly List<ExclusionEntry> _exclusions = new List<ExclusionEntry>();
        // Incarnation -> post-room offense count (escalation key). Exact
        // incarnation, never bare game id (§2a CR-2): a stale quarantine of
        // incarnation K must not suppress a healthy K+1 of the same game.
        private static readonly Dictionary<string, int> _quarantineOffenses =
            new Dictionary<string, int>(StringComparer.Ordinal);

        // Distinct game ids failing post-room with no normal session between
        // (§3a r5-F4: 3 distinct -> the pathology is the SEAT -> FAULTED).
        private static readonly List<string> _consecPostRoomFailGames = new List<string>();

        // Budgets (§3a).
        private const float GRANTING_BUDGET = 15f;
        private const float JOINING_BUDGET = 50f;
        private const float ACTIVATION_BUDGET = 150f;
        private const float LEAVE_REINVOKE_AT = 30f;
        private const float LEAVE_DISCONNECT_AT = 60f;
        private const float LEAVE_FAULT_AT = 90f;
        private const float CANCEL_VERIFY_BUDGET = 20f;
        private const float RECOVER_BACKOFF = 30f;
        private const float POLL_INTERVAL = 10f;
        // r3 find 2: a broadcast grant request still on the wire past this is
        // an owned operation that will not settle — cleanup ambiguity, so the
        // director FAULTS (design §11 fault-early floor) instead of ever
        // reopening admission by clock. > the 20s transport timeout with
        // margin, so it cannot race a request that is merely slow.
        private const float TRANSPORT_FAULT_SECONDS = 60f;

        // ── Step ─────────────────────────────────────────────────────────

        /// <summary>Driven every frame from CompetitiveRoundsBehaviour.Update
        /// (the persistent watcher path). Self-gating and cheap when idle:
        /// one latched-identity check for 99.99% of installs.</summary>
        internal static void Step()
        {
            try
            {
                if (!IsBroadcastIdentity) return;

                FenceTick();   // §2c(a): identity-only, config-independent

                bool enabled = DirectorActive;
                if (!enabled)
                {
                    // Director off: never start anything new, but finish any
                    // in-flight unwind safely (a mid-session config flip must
                    // not strand a half-torn state). No lease writes while
                    // disabled (§3b: "while enabled") — the bot's staleness
                    // ladder owns that signal.
                    // W7: the report engine's clock (Tick) only runs while
                    // enabled, so a config flip mid-report would otherwise
                    // freeze the overlay on screen forever — hide it here.
                    // The entry stays queued (Interrupt contract) and replays
                    // when the director is re-enabled.
                    try { if (PostSessionReport.Active) PostSessionReport.Interrupt(); } catch { }
                    if (_state == State.Idle || _state == State.Faulted) return;
                    if (_state == State.Watching || _state == State.AwaitingActivation)
                        EnterLeaving("director disabled", invokeLeave: true, dueToFailure: false);
                    else if (_state == State.Granting || _state == State.Joining)
                        CancelAcquisition("director disabled");
                    TickDirector();
                    return;
                }

                TickDirector();
                // W7 report engine heartbeat (ai-collab/streaming-design-d1-
                // deltas.md): ticked between the director and the lease write
                // so the lease this frame reflects this frame's report state.
                // directorIdleNoTicket is the engine's ONLY play condition —
                // reports run over the main menu between sittings, never
                // beside any acquisition arc. Locally guarded so an engine
                // throw can never cost this frame's lease write.
                try { PostSessionReport.Tick(_state == State.Idle && _ticket == null); } catch { }
                TickLease();
            }
            catch { /* Step must never throw into the persistent Update */ }
        }

        // ── §2c fence (a): never sit in a room as a non-spectator ────────

        /// <summary>r1 F2: the fence evaluated AT THE JOIN CALLBACK, before
        /// any fighter setup (face publish, 2v2 GM activation/force-start)
        /// can run. Called as the FIRST statement of the central
        /// OnJoinedRoom handler; FenceTick below stays as the periodic
        /// backup. Returns true = the caller must return immediately.</summary>
        internal static bool OnJoinedRoomFence()
        {
            try
            {
                if (!IsBroadcastIdentity) return false;
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return false;
                if (SpectatorSession.IsLocalSpectator) return false;
                Plugin.Log?.LogWarning($"[BROADCAST] §2c fence: joined {SafeRoomDesc()} without a spectator session — aborting before fighter setup");
                try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }
                return true;
            }
            catch { return false; }
        }

        private static void FenceTick()
        {
            try
            {
                if (Time.realtimeSinceStartup < _nextFenceKickAt) return;
                if (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode) return;
                if (SpectatorSession.IsLocalSpectator) return;
                _nextFenceKickAt = Time.realtimeSinceStartup + 5f;
                // §2c: the broadcast identity holds an online room WITHOUT an
                // active spectator session — leave before any fighter setup
                // can complete. NetworkRestart is the codebase's one honest
                // abort-to-menu lever (#252c); its m_restarting latch makes
                // the retry cadence safe.
                Plugin.Log?.LogWarning($"[BROADCAST] §2c fence: in {SafeRoomDesc()} without a spectator session — leaving");
                try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }
            }
            catch { }
        }

        // ── director core ────────────────────────────────────────────────

        private static void TickDirector()
        {
            float now = Time.realtimeSinceStartup;
            // r3 find 2 escalation: a grant request that never produced its
            // terminal callback is an unsettleable owned op — FAULT rather
            // than reopen admission by clock (process replacement is what
            // clears every in-flight request). Checked in every non-faulted
            // state because the owning ticket may already be gone.
            if (_state != State.Faulted)
            {
                try
                {
                    if (ApiClient.BroadcastGrantTransportStuckBeyond(TRANSPORT_FAULT_SECONDS))
                        EnterFaulted("grant_transport_unsettled");
                }
                catch { }
            }
            switch (_state)
            {
                case State.Idle:
                    TickIdle(now);
                    break;
                case State.Granting:
                    TickGranting(now);
                    break;
                case State.Joining:
                    TickJoining(now);
                    break;
                case State.AwaitingActivation:
                    TickAwaitingActivation(now);
                    break;
                case State.Watching:
                    TickWatching(now);
                    break;
                case State.Leaving:
                    TickLeaving(now);
                    break;
                case State.Cancelling:
                    TickCancelling(now);
                    break;
                case State.Recover:
                    if (now >= _recoverUntil) SetState(State.Idle, "backoff over");
                    break;
                case State.Faulted:
                    // Terminal (§3a r2-F4): no grants, no leaves. The lease
                    // keeps publishing state="faulted" with an advancing seq;
                    // the bot fails the feed closed and replaces the process.
                    break;
            }
        }

        private static void SetState(State s, string why)
        {
            if (_state == s) return;
            // FAULTED is terminal (§3a r2-F4): no transition may leave it —
            // NotePostRoomFailure can fault mid-handler and its CALLER's next
            // transition (EnterLeaving/CancelAcquisition) must not resurrect
            // the director. Only a process replacement resumes.
            if (_state == State.Faulted) return;
            _state = s;
            try { Plugin.Log?.LogInfo($"[BROADCAST] -> {s} ({why})"); } catch { }
        }

        private static void TickIdle(float now)
        {
            // A session the director did not create (someone at the VM used
            // the public WATCH flow) is left alone — never acquire over it.
            if (SpectatorSession.IsLocalSpectator) return;
            // r1 F5: a pending PUBLIC grant must also block acquisition — our
            // RequestSpectateGrant would silently early-return on its latch
            // and the ticket would then adopt whatever session THAT grant
            // creates. Wait until the seat is provably free.
            if (ApiClient.SpectateGrantInFlight) return;
            // r2 find 4: an UNRESOLVED broadcast grant request (latch already
            // CAS-freed by a cancel, HTTP still on the wire for up to 20s)
            // must also block: a newer grant reaching the server first would
            // be revoke-and-replaced by the delayed straggler.
            if (ApiClient.BroadcastGrantTransportUnsettled) return;
            // r4 find 1: a PUBLIC watch's timed-out-but-unsettled JoinRoom op
            // on this seat must also block admission — Fail() restored the
            // public seat's pre-batch recovery, but until a real terminal
            // signal clears the op, a successor acquisition could race the
            // late-landing join (the r2-F1 split-role window from Idle).
            if (SpectatorJoiner.JoinOpUnsettled) return;
            if (now < _nextPollAt || _pollInFlight) return;
            if (!IdentityAndSessionReady()) { _nextPollAt = now + 5f; return; }
            SendPoll(currentGameId: null, activationAge: -1f, preActivation: false);
        }

        /// <summary>r1 F5 + r2 find 3: session ownership is TICKET-EXACT, not
        /// game-id-matching. A session is ours only when it was created by
        /// THIS ticket's own grant dispatch (SpectatorSession.BroadcastOwned
        /// + OwnerGrantSeq == ticket.GrantSeq). A public WATCH that happens
        /// to target the same game is still FOREIGN and is never adopted.</summary>
        private static bool SessionIsOurs(SpectateAcquisition t)
        {
            try
            {
                return t != null && t.GrantSeq != 0
                       && SpectatorSession.IsLocalSpectator
                       && SpectatorSession.BroadcastOwned
                       && SpectatorSession.OwnerGrantSeq == t.GrantSeq;
            }
            catch { return false; }
        }

        private static bool SessionIsForeign(SpectateAcquisition t)
        {
            try
            {
                return t != null && SpectatorSession.IsLocalSpectator && !SessionIsOurs(t);
            }
            catch { return false; }
        }

        /// <summary>r1 F5: a PUBLIC session owns the seat. Invalidate OUR arc
        /// only — never its session, lease, or latches (they were never ours;
        /// the CAS tokens make even a mistaken release a no-op). IDLE stays
        /// passive while the foreign session lives. The generation bump here
        /// is safe for the public flow BY CONSTRUCTION (r2 find 3): the
        /// joiner consumes generation invalidation only for BROADCAST-OWNED
        /// sessions, and the grant stale-discard only for broadcast-ticket
        /// dispatches — a public join structurally cannot consume it.</summary>
        private static void AbandonToForeignSession(string why)
        {
            Plugin.Log?.LogWarning($"[BROADCAST] abandoning ticket — a public session owns the seat ({why})");
            _sharedFlowGen++;
            RetireTicket(why);
            EnterRecover("foreign session: " + why);
        }

        private static void TickGranting(float now)
        {
            var t = _ticket;
            if (t == null) { SetState(State.Idle, "no ticket"); return; }
            if (SessionIsForeign(t)) { AbandonToForeignSession("granting"); return; }
            if (SessionIsOurs(t))
            {
                t.PhaseStartedAt = now;
                SetState(State.Joining, "session began");
                return;
            }
            float elapsed = now - t.PhaseStartedAt;
            // The grant flow ended (or never started) without a session:
            // RequestSpectateGrant sets its latch synchronously, so latch-down
            // + no-session after a grace tick means refused/failed. GrantSeq
            // 0 = the dispatch itself was refused (latch held / precheck).
            if (elapsed > 0.5f && (t.GrantSeq == 0 || !ApiClient.SpectateGrantInFlight))
            {
                PreRoomFailure("grant_refused");
                return;
            }
            if (elapsed > GRANTING_BUDGET)
            {
                PreRoomFailure("grant_timeout");
                return;
            }
            MaybeAcqProgressPoll(now, "granting");
        }

        private static void TickJoining(float now)
        {
            var t = _ticket;
            if (t == null) { SetState(State.Idle, "no ticket"); return; }
            if (SessionIsForeign(t)) { AbandonToForeignSession("joining"); return; }
            if (!SpectatorSession.IsLocalSpectator)
            {
                // The joiner Fail()ed: it already released the lease, ended
                // the session and returned to the menu. Record + verify.
                PreRoomFailure("join_failed");
                return;
            }
            bool inRoom = false;
            try { inRoom = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode; } catch { }
            if (inRoom)
            {
                t.PhaseStartedAt = now;
                SetState(State.AwaitingActivation, "room entered");
                return;
            }
            if (now - t.PhaseStartedAt > JOINING_BUDGET)
            {
                AddExclusion(t.GameId, t.Incarnation, "join_timeout", PRE_ROOM_BLACKLIST_SECONDS);
                CancelAcquisition("join_timeout");
                return;
            }
            MaybeAcqProgressPoll(now, "joining");
        }

        private static void TickAwaitingActivation(float now)
        {
            var t = _ticket;
            if (t == null) { SetState(State.Idle, "no ticket"); return; }
            if (SessionIsForeign(t)) { AbandonToForeignSession("awaiting_activation"); return; }
            if (!SpectatorSession.IsLocalSpectator)
            {
                // Codex r3 (CONFIRMED HIGH): the causal classification
                // applies HERE too — a genuine fighter leaving while we
                // await the first boundary (a late join landing near the
                // sitting's natural end) yanks this seat through the same
                // vanilla cascade as a watching-phase organic end, and
                // unconditional failure here fed the 3-strike seat fault.
                // Same evidence rule as TickWatching: unannotated death +
                // fresh fighter-departure stamp = organic — no quarantine,
                // no streak increment. Deliberately does NOT clear the
                // streak (unlike the watching-phase organic end): a seat
                // that never activated has demonstrated nothing, so the
                // strictest reading of "no normal session between" stands.
                // Explicit failure reasons and stampless deaths keep the
                // pre-activation failure semantics unchanged.
                bool organicPreActivation =
                    IsUnannotatedRoomExit(_lastLeaveReason)
                    && _fighterLeftAt >= 0f
                    && now - _fighterLeftAt <= FIGHTER_EXIT_CASCADE_WINDOW;
                if (organicPreActivation)
                {
                    RetireTicket("sitting ended before activation: "
                        + (string.IsNullOrEmpty(_lastLeaveReason) ? "left room" : _lastLeaveReason));
                    SetState(State.Idle, "sitting ended pre-activation");
                    _nextPollAt = now + 2f;
                    return;
                }
                // Session died before activation (sync failure path already
                // tore it down and left the room).
                NotePostRoomFailure(t, string.IsNullOrEmpty(_lastLeaveReason) ? "session_died" : _lastLeaveReason);
                CancelAcquisition("session died pre-activation");
                return;
            }
            if (SpectatorSession.LeaveRequested)
            {
                // A session-side leave is already in flight (LeaveToMenu ran).
                bool failure = IsFailureLeaveReason(_lastLeaveReason);
                if (failure) NotePostRoomFailure(t, _lastLeaveReason);
                EnterLeaving("session-side leave: " + _lastLeaveReason, invokeLeave: false, dueToFailure: failure);
                return;
            }
            if (SpectatorSync.HasEverActivated)
            {
                _activatedAt = now;
                t.PhaseStartedAt = now;
                SetState(State.Watching, "activated");
                return;
            }
            if (now - t.PhaseStartedAt > ACTIVATION_BUDGET)
            {
                // §3a: an in-room session that never activates must be EXITED,
                // not blacklisted from outside — quarantine + leave.
                NotePostRoomFailure(t, "activation_timeout");
                EnterLeaving("activation timeout", invokeLeave: true, dueToFailure: true);
                return;
            }
            MaybeAcqProgressPoll(now, "awaiting_activation");
        }

        private static void TickWatching(float now)
        {
            var t = _ticket;
            if (t == null) { SetState(State.Idle, "no ticket"); return; }
            if (SessionIsForeign(t)) { AbandonToForeignSession("watching"); return; }
            if (!SpectatorSession.IsLocalSpectator)
            {
                // Session ended and the exit was already observed.
                bool failure = IsFailureLeaveReason(_lastLeaveReason);
                // Codex rounds 1+2 (both CONFIRMED HIGH, opposite
                // directions): an UNANNOTATED room exit ("left room" / the
                // tick backstop / nothing recorded) cannot be classified by
                // name (r1: always-organic deletes the 3-strike seat-fault
                // bound for a seat that keeps dropping) nor by watch
                // duration (r2: a legitimate LATE-JOIN sitting ending 20-80s
                // after activation is observationally identical to a short
                // seat failure). The CAUSAL evidence discriminates exactly:
                // an organic end IS vanilla's DoDisconnect cascade, and its
                // precursor — a genuine FIGHTER leaving the room — is
                // observed on this seat seconds before the yank
                // (Spectator_LeaveIsInvisible_Patch stamps it). Fighter
                // departure observed recently => organic, whatever the
                // watch length; not observed => seat-side death, full
                // failure semantics (quarantine + streak). Explicit reasons
                // keep their name-based classification untouched. Accepted
                // residual: a seat-side drop landing within the 15s window
                // of an UNRELATED fighter leave (e.g. FFA mid-game leaver
                // whose cascade is suppressed) misses one streak increment —
                // a coincidence, not a systematic bypass.
                if (IsUnannotatedRoomExit(_lastLeaveReason))
                    failure = !(_fighterLeftAt >= 0f
                                && now - _fighterLeftAt <= FIGHTER_EXIT_CASCADE_WINDOW);
                if (failure)
                {
                    NotePostRoomFailure(t, _lastLeaveReason);
                    CancelAcquisition("session died watching");
                }
                else
                {
                    _consecPostRoomFailGames.Clear();
                    RetireTicket("session over: " + _lastLeaveReason);
                    SetState(State.Idle, "session over");
                    _nextPollAt = now + 2f;
                }
                return;
            }
            if (SpectatorSession.LeaveRequested)
            {
                bool failure = IsFailureLeaveReason(_lastLeaveReason);
                if (failure) NotePostRoomFailure(t, _lastLeaveReason);
                EnterLeaving("session-side leave: " + _lastLeaveReason, invokeLeave: false, dueToFailure: failure);
                return;
            }
            // W7 activation-edge feed (D1 f8: a ReportEntry is created ONLY
            // at the Watching-activation edge, never at BeginAcquisition).
            // R1 f6: the entry MAY be identity-less — on the autonomous
            // broadcast seat SpectatorSession.WatchedRoster is ALWAYS empty
            // (only the F5-fed CachedSpectateGames grant path populates it,
            // and F5 stays closed), so the note fires regardless and the
            // report-status poll fills roster/names server-side. This is
            // the first HEALTHY Watching tick: placed after the death/leave
            // branches so a dead session is never noted. Latched per ticket
            // BEFORE the call — safe because NoteActivatedForReport has no
            // roster gate; its only skip is the deliberate 1v2/ovt
            // exclusion (D1 f11), and PostSessionReport.NotePairActivated
            // accepts identity-less entries.
            if (!t.ReportNoted && SpectatorSync.HasEverActivated)
            {
                t.ReportNoted = true;
                NoteActivatedForReport(t);
            }
            if (now >= _nextPollAt && !_pollInFlight)
                SendPoll(currentGameId: t.GameId, activationAge: Mathf.Max(0f, now - _activatedAt), preActivation: false);
        }

        private static void TickLeaving(float now)
        {
            bool stillHeld = false;
            try
            {
                stillHeld = SpectatorSession.IsLocalSpectator
                            || (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode);
            }
            catch { }
            if (!stillHeld)
            {
                bool failure = _leavingDueToFailure;
                if (!failure) _consecPostRoomFailGames.Clear();
                RetireTicket("leave complete");
                if (failure) EnterRecover("post-room failure");
                else { SetState(State.Idle, "leave complete"); _nextPollAt = now + 2f; }
                return;
            }
            float elapsed = now - _leaveStartedAt;
            if (elapsed > LEAVE_FAULT_AT)
            {
                EnterFaulted("leave budget exhausted (90s)");
            }
            else if (elapsed > LEAVE_DISCONNECT_AT && !_leaveDisconnected)
            {
                _leaveDisconnected = true;
                Plugin.Log?.LogWarning("[BROADCAST] leave escalation: PhotonNetwork.Disconnect()");
                // Never force-clear spectator state while in-room — the props
                // clear on the disconnect path (§3a r2-F4).
                try { PhotonNetwork.Disconnect(); } catch { }
            }
            else if (elapsed > LEAVE_REINVOKE_AT && !_leaveReinvoked)
            {
                _leaveReinvoked = true;
                Plugin.Log?.LogWarning("[BROADCAST] leave escalation: re-invoking LeaveToMenu");
                try { SpectatorSync.LeaveToMenu("broadcast leave retry"); } catch { }
            }
        }

        /// <summary>Photon client states in which a room operation (JoinRoom /
        /// leave) is in flight or settled-in-room. While one is pending, the
        /// staged cr_spec has already ridden the op — tearing the role down
        /// would let a late success land in the FIGHTER branch while peers
        /// classify us spectator (r1 F1).</summary>
        private static bool RoomBoundClientState()
        {
            try
            {
                switch (PhotonNetwork.NetworkClientState)
                {
                    case Photon.Realtime.ClientState.Joining:
                    case Photon.Realtime.ClientState.Joined:
                    case Photon.Realtime.ClientState.Leaving:
                    case Photon.Realtime.ClientState.ConnectingToGameServer:
                    case Photon.Realtime.ClientState.ConnectedToGameServer:
                        return true;
                }
            }
            catch { }
            return false;
        }

        /// <summary>r2 find 1: the full deferral predicate. The state
        /// enumeration above cannot cover Photon's whole room-entry handoff
        /// (DisconnectingFromMasterServer, the game-server auth phases read
        /// as "not room-bound" while an accepted enter op is still in
        /// flight) — so the authoritative half is the joiner's OWNED
        /// join-op flag, set immediately before JoinRoom and cleared only on
        /// exact success/failure/disconnect. The enumeration stays as belt
        /// for non-join room-bound states (e.g. Leaving).</summary>
        private static bool RoomOpUnsettled()
        {
            try { if (SpectatorJoiner.JoinOpUnsettled) return true; } catch { }
            return RoomBoundClientState();
        }

        private static void TickCancelling(float now)
        {
            bool inRoom = false;
            try { inRoom = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode; } catch { }
            if (inRoom)
            {
                // Room entry raced the cancel — abort it; the in-room exit
                // path owns the teardown from here (§3a r3-F2). With the F1
                // deferral the session is still ALIVE here, so this is a
                // normal spectator leave, and OnJoinedRoom took the spectator
                // branch (never fighter setup).
                EnterLeaving("room entry raced cancel: " + _cancelReason, invokeLeave: true, dueToFailure: true);
                return;
            }
            if (!_cancelUnwindDone)
            {
                // r1 F1 + r2 find 1: the join op was still in flight at
                // cancel time. Wait for it to resolve (success -> the InRoom
                // branch above; failure/disconnect -> the settlement relays
                // clear the ownership flag) before touching role/props. The
                // 20s budget below bounds an op that never resolves.
                if (RoomOpUnsettled())
                {
                    if (now - _cancelStartedAt > CANCEL_VERIFY_BUDGET)
                        EnterFaulted($"cancel unwind never settled ({_cancelReason})");
                    return;
                }
                RunCancelTeardown();
                _cancelUnwindDone = true;
                return;   // verify from the next tick
            }
            if (VerifyCancelClean())
            {
                RetireTicket("cancel verified");
                EnterRecover(_cancelReason);
                return;
            }
            if (now - _cancelStartedAt > CANCEL_VERIFY_BUDGET)
                EnterFaulted($"cancel verify failed ({_cancelReason})");
        }

        // ── transitions / primitives ─────────────────────────────────────

        private static void BeginAcquisition(ApiClient.BroadcastTargetInfo target, float now)
        {
            // W7: a live sitting always outranks a replayed report — hide any
            // on-screen report the instant an acquisition starts. The entry
            // stays queued and replays from the start (Interrupt contract).
            // FIRST statement, so no acquisition step can ever race a report
            // still painting over the screen the join needs.
            try { PostSessionReport.Interrupt(); } catch { }
            _ticket = new SpectateAcquisition
            {
                TicketId = Guid.NewGuid().ToString("N").Substring(0, 12),
                GameId = target.game_id,
                Incarnation = target.incarnation,
                FlowGenAtStart = _sharedFlowGen,
                StartedAt = now,
                PhaseStartedAt = now,
            };
            CurrentTargetMeta = target;
            _lastLeaveReason = "";
            _fighterLeftAt = -1f;   // per-arc evidence; a prior sitting's stamp must not vouch
            SetState(State.Granting, $"target game={target.game_id}");
            // The broadcast dispatch returns its grant OWNER TOKEN (r1 F6):
            // 0 = never dispatched (precheck refused), which TickGranting
            // fails fast on. Only this token can force-release the latch.
            try { _ticket.GrantSeq = ApiClient.RequestSpectateGrantForBroadcast(target.game_id); }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[BROADCAST] grant dispatch threw: {ex.Message}");
            }
        }

        /// <summary>§3a r3-F2: ONE primitive unwinds the whole acquisition —
        /// lease release, continuation invalidation (generation bump), latch
        /// release, m_ForceRegion clear, staged-prop clear via the session's
        /// own pending-clear retry, session teardown via the out-of-room
        /// path — then hands off to CANCELLING for the bounded verify.
        /// Room entry racing the cancel diverts to LEAVING instead.</summary>
        private static void CancelAcquisition(string reason)
        {
            if (_state == State.Faulted) return;   // terminal: no unwind actions either
            // r1 F5: a PUBLIC session owning the seat must never be torn down
            // by OUR cancel — abandon the ticket instead.
            if (SessionIsForeign(_ticket)) { AbandonToForeignSession("cancel: " + reason); return; }
            _cancelReason = reason;
            bool inRoom = false;
            try { inRoom = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode; } catch { }
            if (inRoom)
            {
                EnterLeaving("cancel with room entry: " + reason, invokeLeave: true, dueToFailure: true);
                return;
            }

            Plugin.Log?.LogInfo($"[BROADCAST] CancelAcquisition({reason})");

            // 1. Best-effort lease release (no-op when no lease was granted;
            //    a grant response still in flight is handled by its own
            //    stale-generation check, which releases the late lease by id).
            //    The global lease here is OURS or empty by the foreign guard
            //    above, so the global-clearing notify is correct (r1 F6).
            try { ApiClient.SpectateLeaveNotify(); } catch { }

            // 2. Invalidate every shared-flow continuation and release the
            //    latches (stale callbacks no-op — #367 ownership token). The
            //    grant-latch release CASes on the ticket's own dispatch token,
            //    so a successor public grant's latch is untouchable (r1 F6).
            _sharedFlowGen++;
            try { ApiClient.ReleaseSpectateGrantLatchForStaleTicket(_ticket != null ? _ticket.GrantSeq : 0); } catch { }
            try { SpectatorJoiner.ReleaseLatchForStaleTicket(); } catch { }

            // 3. Region pin clear.
            try
            {
                var nch = NetworkConnectionHandler.instance;
                if (nch != null) nch.m_ForceRegion = false;
            }
            catch { }

            _cancelStartedAt = Time.realtimeSinceStartup;

            // 4+5. Session/prop teardown — DEFERRED while a room-bound Photon
            //      op is unsettled (r1 F1 + r2 find 1: the OWNED join-op flag
            //      covers the handoff states the enumeration cannot): the
            //      staged cr_spec already rode a dispatched JoinRoom, and
            //      clearing the role now would let a late success run FIGHTER
            //      setup while peers classify us spectator. TickCancelling
            //      finishes the unwind once the op terminally resolves.
            if (RoomOpUnsettled())
            {
                _cancelUnwindDone = false;
                SetState(State.Cancelling, reason + " (room op in flight — teardown deferred)");
                return;
            }
            RunCancelTeardown();
            _cancelUnwindDone = true;
            SetState(State.Cancelling, reason);
        }

        /// <summary>The teardown half of CancelAcquisition: session end via
        /// the existing out-of-room path (arms the staged-prop pending-clear
        /// retry), sync statics, then back to the menu if the joiner had
        /// touched the connection. Idempotent — the deferred path may find
        /// the joiner's own Fail() already ran all of it.</summary>
        private static void RunCancelTeardown()
        {
            bool hadSession = false;
            try { hadSession = SpectatorSession.IsLocalSpectator; } catch { }
            try { SpectatorSession.EndSession("broadcast cancel: " + _cancelReason); } catch { }
            try { SpectatorSync.OnLeftSpectatorRoom(); } catch { }
            if (hadSession)
            {
                try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }
            }
        }

        /// <summary>The §3a verify: not in a room, no session, staged props
        /// confirmed clear, Photon client state not room-bound, and NO
        /// unsettled join op (r2 find 1 — an unresolved enter operation must
        /// never be certified clean).</summary>
        private static bool VerifyCancelClean()
        {
            try
            {
                if (SpectatorJoiner.JoinOpUnsettled) return false;
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return false;
                if (SpectatorSession.IsLocalSpectator) return false;
                var lp = PhotonNetwork.LocalPlayer;
                if (lp != null && lp.CustomProperties != null)
                {
                    var props = lp.CustomProperties;
                    if (props.ContainsKey(RoomActors.SPEC_PROP)
                        || props.ContainsKey(RoomActors.SPEC_LEASE_PROP)) return false;
                }
                var s = PhotonNetwork.NetworkClientState;
                switch (s)
                {
                    case Photon.Realtime.ClientState.Joining:
                    case Photon.Realtime.ClientState.Joined:
                    case Photon.Realtime.ClientState.Leaving:
                    case Photon.Realtime.ClientState.ConnectingToGameServer:
                    case Photon.Realtime.ClientState.ConnectedToGameServer:
                        return false;   // room-bound = not sane for a cancelled acquisition
                }
                return true;
            }
            catch { return false; }
        }

        private static void EnterLeaving(string reason, bool invokeLeave, bool dueToFailure)
        {
            if (_state == State.Faulted) return;   // terminal: no leaves (§3a r2-F4)
            _leaveStartedAt = Time.realtimeSinceStartup;
            _leaveReinvoked = false;
            _leaveDisconnected = false;
            _leavingDueToFailure = dueToFailure;
            SetState(State.Leaving, reason);
            if (invokeLeave)
            {
                try { SpectatorSync.LeaveToMenu("broadcast: " + reason); } catch { }
            }
        }

        private static void EnterRecover(string reason)
        {
            if (_state == State.Faulted) return;   // terminal
            _recoverUntil = Time.realtimeSinceStartup + RECOVER_BACKOFF;
            SetState(State.Recover, reason);
        }

        private static void EnterFaulted(string reason)
        {
            if (_state == State.Faulted) return;   // first fault reason wins
            _faultReason = reason;
            // r4 find 2: FAULTED must invalidate every pending pre-session
            // continuation — a grant callback that resumes after a long frame
            // stall would otherwise see its generation as current and call
            // BeginSession/StartJoin under a terminal director. The bump
            // makes every in-flight broadcast-owned continuation stale; the
            // process replacement then clears whatever remains.
            unchecked { _sharedFlowGen++; }
            SetState(State.Faulted, reason);
            try { Plugin.Log?.LogError($"[BROADCAST] FAULTED: {reason} — director halted; bot replaces the process"); } catch { }
        }

        /// <summary>Fault escalation entry for owned-operation ambiguity
        /// detected OUTSIDE the director's own tick (r3 find 1: the joiner's
        /// join op that produced no terminal signal after a forced
        /// disconnect). FAULTED is the design's pre-approved fault-early
        /// floor (§11): no synthetic settlement, no role teardown — the bot
        /// replaces the ROUNDS process, which is provably clean. No-op off
        /// the broadcast identity.</summary>
        internal static void FaultDirector(string reason)
        {
            if (!IsBroadcastIdentity) return;
            EnterFaulted(reason);
        }

        private static void RetireTicket(string why)
        {
            if (_ticket == null) return;
            // W7: every ticket retirement — organic sitting end, cancel
            // verified, leave complete, foreign abandon, pre-activation end —
            // is the director-side "stopped watching this pair" stamp for the
            // report queue. Keyed by game id; the engine no-ops for a game it
            // never noted (a ticket that died before activation).
            try { PostSessionReport.NoteTargetGone(_ticket.GameId); } catch { }
            // Bumping the generation on retirement is cheap insurance: any
            // straggler callback from the finished arc no-ops instead of
            // acting on the next one. Never reached on non-broadcast installs.
            _sharedFlowGen++;
            Plugin.Log?.LogInfo($"[BROADCAST] ticket retired ({why})");
            _ticket = null;
            CurrentTargetMeta = null;
        }

        private static void PreRoomFailure(string reason)
        {
            var t = _ticket;
            if (t != null) AddExclusion(t.GameId, t.Incarnation, reason, PRE_ROOM_BLACKLIST_SECONDS);
            CancelAcquisition(reason);
        }

        /// <summary>§3a r5-F4 post-room quarantine: escalating per-incarnation
        /// duration, plus the seat-level budget — 3 DISTINCT games failing
        /// post-room consecutively means the pathology is the seat.</summary>
        private static void NotePostRoomFailure(SpectateAcquisition t, string reason)
        {
            if (t == null) return;
            int offenses;
            _quarantineOffenses.TryGetValue(t.Incarnation, out offenses);
            offenses++;
            _quarantineOffenses[t.Incarnation] = offenses;
            float secs = offenses >= 2 ? QUARANTINE_REPEAT_SECONDS : QUARANTINE_FIRST_SECONDS;
            AddExclusion(t.GameId, t.Incarnation, SanitizeReason(reason), secs);
            if (!_consecPostRoomFailGames.Contains(t.GameId))
                _consecPostRoomFailGames.Add(t.GameId);
            Plugin.Log?.LogWarning($"[BROADCAST] post-room failure #{offenses} game={t.GameId} ({reason}) — quarantined {secs:F0}s; distinct-fail streak {_consecPostRoomFailGames.Count}/3");
            if (_consecPostRoomFailGames.Count >= 3)
                EnterFaulted("3 distinct games failed post-room consecutively");
        }

        /// <summary>How recently a genuine FIGHTER's departure must have been
        /// observed for an unannotated room exit to classify as the organic
        /// end of the sitting. Vanilla's cascade (OnPlayerLeftRoom ->
        /// DoDisconnect -> our yank) completes in ~1-5s; the slack covers
        /// slow frames without letting an unrelated leave minutes earlier
        /// vouch for a seat-side drop.</summary>
        private const float FIGHTER_EXIT_CASCADE_WINDOW = 15f;

        // Stamped by Spectator_LeaveIsInvisible_Patch when a genuine
        // fighter's departure is observed on this seat — the causal
        // precursor of the vanilla cascade (#209) that yanks a spectator
        // out of an ended sitting. Cleared per acquisition arc.
        private static float _fighterLeftAt = -1f;

        /// <summary>Evidence hook: a genuine (non-spectator) actor left the
        /// room this seat is in. Inert off the broadcast identity.</summary>
        internal static void NoteFighterLeftRoom()
        {
            if (!IsBroadcastIdentity) return;
            _fighterLeftAt = Time.realtimeSinceStartup;
        }

        /// <summary>True for session-death reasons that carry NO diagnosis:
        /// the bare room-exit observer ("left room"), its tick backstop, or
        /// nothing recorded at all. These classify by the fighter-departure
        /// evidence in TickWatching rather than by name.</summary>
        private static bool IsUnannotatedRoomExit(string reason)
        {
            return string.IsNullOrEmpty(reason)
                || reason.StartsWith("left room", StringComparison.Ordinal)
                || reason.StartsWith("leave completed", StringComparison.Ordinal);
        }

        /// <summary>Session-leave reasons that count as post-room FAILURES
        /// (quarantine + streak) vs normal ends. The strings are
        /// SpectatorSync's own LeaveToMenu reasons — see NoteSessionLeave.</summary>
        private static bool IsFailureLeaveReason(string reason)
        {
            if (string.IsNullOrEmpty(reason)) return true;   // unexplained death = failure
            if (reason.StartsWith("broadcast", StringComparison.Ordinal)) return false; // our own orders
            return reason.StartsWith("no snapshot response", StringComparison.Ordinal)
                || reason.StartsWith("deck reconstruction failed", StringComparison.Ordinal)
                || reason.StartsWith("join setup failed", StringComparison.Ordinal)
                || reason.StartsWith("wrong room", StringComparison.Ordinal);
        }

        /// <summary>Observation hook called by SpectatorSync.LeaveToMenu with
        /// its reason string. Inert (one latched-bool check) off the
        /// broadcast identity.</summary>
        internal static void NoteSessionLeave(string reason)
        {
            if (!IsBroadcastIdentity) return;
            _lastLeaveReason = reason ?? "";
        }

        /// <summary>Fallback recorder for session deaths that never went
        /// through LeaveToMenu — vanilla's DoDisconnect cascade yanks the
        /// spectator seat too when a fighter leaves the room, and that is how
        /// nearly every sitting ORGANICALLY ends (Plugin.OnLeftRoom then runs
        /// EndSession("left room") with no reason recorded anywhere). An
        /// empty reason classifies as "unexplained death = post-room
        /// failure", so every normal sitting end fed the 3-strike seat fault
        /// and the bot killed ROUNDS every third sitting (Aug 18, the 17:10
        /// double replacement). Only fills an EMPTY slot: a LeaveToMenu
        /// reason (the richer, failure-classifiable one) always wins, and
        /// BeginAcquisition clears the slot per arc so nothing goes stale.
        /// NOTE the recorded "left room" is NOT inherently benign — the
        /// classifier additionally requires the fighter-departure evidence
        /// (NoteFighterLeftRoom / FIGHTER_EXIT_CASCADE_WINDOW in
        /// TickWatching; Codex Aug 18 r1+r2: without causal evidence a seat
        /// dropping on its own must keep failure semantics or the 3-strike
        /// bound dies). Inert off the broadcast identity.</summary>
        internal static void NoteSessionLeaveFallback(string reason)
        {
            if (!IsBroadcastIdentity) return;
            if (string.IsNullOrEmpty(_lastLeaveReason))
                _lastLeaveReason = reason ?? "";
        }

        // ── W7 post-session report feed (ai-collab/streaming-design-d1-deltas.md) ──

        /// <summary>Activation-edge note for the post-session report queue
        /// (D1 f8: a ReportEntry is created ONLY here — identity is
        /// game_id + incarnation). ALWAYS calls NotePairActivated for a
        /// non-1v2 sitting (R1 f6): on the autonomous broadcast seat
        /// SpectatorSession.WatchedRoster is ALWAYS empty (only the F5-fed
        /// CachedSpectateGames grant path populates it, and F5 stays closed),
        /// so roster/names/ratings are best-effort — session watch meta when
        /// roster-aligned, target-poll meta otherwise, EMPTY arrays when
        /// unknown. PostSessionReport accepts identity-less entries; the
        /// report-status poll fills roster/names/mode/started_at server-side
        /// (the R1 f6+f8 identity-fill contract). Called once per ticket
        /// from TickWatching (ReportNoted latch — latching before the call
        /// is safe because the only enqueue skips are the deliberate 1v2/ovt
        /// exclusion (D1 f11) and PostSessionReport's full-queue refusal when
        /// all 16 entries are protected — a state that means 16 sittings
        /// already await reporting, where losing a 17th is acceptable).</summary>
        private static void NoteActivatedForReport(SpectateAcquisition t)
        {
            try
            {
                if (t == null) return;
                var meta = CurrentTargetMeta;
                bool metaMatches = meta != null
                                   && string.Equals(meta.game_id, t.GameId, StringComparison.Ordinal);
                string mode = metaMatches ? (meta.mode ?? "") : "";
                if (mode.Length == 0)
                {
                    try { mode = SpectatorSync.WatchedMode ?? ""; } catch { }
                }
                // D1 f11: 1v2 is excluded from reports entirely — skip both
                // spellings the mode field has carried ("1v2" / "ovt").
                if (string.Equals(mode, "1v2", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(mode, "ovt", StringComparison.OrdinalIgnoreCase))
                    return;

                // R1 f6: EMPTY is the NORMAL autonomous-seat value — proceed
                // to the NotePairActivated call regardless; identity is
                // filled server-side by the report-status poll. Never add a
                // roster-emptiness return here.
                string[] roster;
                try { roster = SpectatorSession.WatchedRoster ?? new string[0]; }
                catch { roster = new string[0]; }

                // Names: the session's watch meta when roster-ALIGNED, else
                // the target-poll meta. Alignment is the validity test —
                // SetWatchedMeta's empty-CSV split yields [""], never a
                // usable array (same rule WatchedTitleColors already uses).
                string[] names = null;
                try
                {
                    var wn = SpectatorSession.WatchedNames;
                    if (wn != null && roster.Length > 0 && wn.Length == roster.Length) names = wn;
                }
                catch { }
                if (names == null)
                    names = metaMatches && meta.names != null ? meta.names.ToArray() : new string[0];

                float[] ratings = ParseReportRatings(roster.Length, metaMatches ? meta : null);

                PostSessionReport.NotePairActivated(t.GameId, t.Incarnation, mode, roster, names, ratings);
            }
            catch (Exception ex)
            {
                try { Plugin.Log?.LogWarning($"[BROADCAST] report activation note failed: {ex.Message}"); } catch { }
            }
        }

        /// <summary>Ratings for the report note: the session watch-meta CSV
        /// (display strings, e.g. "1523" — SpectatorHud renders them raw)
        /// parsed invariant when roster-aligned; the target-poll meta's
        /// numeric ratings otherwise; empty when neither is usable (the
        /// engine treats unknown as 0 — A6 contract).</summary>
        private static float[] ParseReportRatings(int rosterLen, ApiClient.BroadcastTargetInfo metaOrNull)
        {
            try
            {
                var raw = SpectatorSession.WatchedRatings;
                if (raw != null && rosterLen > 0 && raw.Length == rosterLen)
                {
                    var parsed = new float[raw.Length];
                    bool any = false;
                    for (int i = 0; i < raw.Length; i++)
                    {
                        float v;
                        if (float.TryParse((raw[i] ?? "").Trim(),
                                           System.Globalization.NumberStyles.Float,
                                           System.Globalization.CultureInfo.InvariantCulture, out v))
                        {
                            parsed[i] = v;
                            any = true;
                        }
                    }
                    if (any) return parsed;
                }
                if (metaOrNull != null && metaOrNull.ratings != null && metaOrNull.ratings.Count > 0)
                {
                    var fromMeta = new float[metaOrNull.ratings.Count];
                    for (int i = 0; i < fromMeta.Length; i++) fromMeta[i] = (float)metaOrNull.ratings[i];
                    return fromMeta;
                }
            }
            catch { }
            return new float[0];
        }

        // ── target poll (§2a) ────────────────────────────────────────────

        private static bool IdentityAndSessionReady()
        {
            try
            {
                string sid = MatchTracker.LocalSteamId;
                if (string.IsNullOrEmpty(sid) || sid == "unknown") return false;
                return !string.IsNullOrEmpty(SteamAuth.SessionToken);
            }
            catch { return false; }
        }

        /// <summary>Pre-activation states poll WITHOUT current= (the server's
        /// acquisition-progress lease renews on every acq poll only in the
        /// not-current branch — verified against main.py broadcast_target;
        /// sending current= pre-activation would starve the progress lease
        /// and rotate the selector away mid-join).</summary>
        private static void MaybeAcqProgressPoll(float now, string phase)
        {
            if (now < _nextPollAt || _pollInFlight) return;
            var t = _ticket;
            if (t == null) return;
            SendPoll(currentGameId: null, activationAge: -1f, preActivation: true, acqPhase: phase, acqAge: now - t.StartedAt);
        }

        private static void SendPoll(string currentGameId, float activationAge, bool preActivation,
                                     string acqPhase = null, float acqAge = 0f)
        {
            float now = Time.realtimeSinceStartup;
            _nextPollAt = now + POLL_INTERVAL;
            if (!IdentityAndSessionReady()) return;
            _pollInFlight = true;
            var ticketAtSend = _ticket;
            try
            {
                ApiClient.FetchBroadcastTarget(
                    currentGameId,
                    activationAge,
                    preActivation ? (ticketAtSend != null ? ticketAtSend.TicketId : "") : null,
                    preActivation ? acqPhase : null,
                    preActivation ? acqAge : -1f,
                    BuildExcludeCsv(),
                    (ok, resp) =>
                    {
                        _pollInFlight = false;
                        if (!ok || resp == null) return;
                        HandlePollResponse(resp, ticketAtSend);
                    });
            }
            catch (Exception ex)
            {
                _pollInFlight = false;
                Plugin.Log?.LogWarning($"[BROADCAST] target poll dispatch: {ex.Message}");
            }
        }

        private static void HandlePollResponse(ApiClient.BroadcastTargetResponse resp,
                                               SpectateAcquisition ticketAtSend)
        {
            try
            {
                // A response for a different arc (or after a state change) is
                // display-refresh only, never a transition input.
                if (_ticket != ticketAtSend) return;

                if (_state == State.Idle)
                {
                    if (resp.target == null) return;
                    if (!DirectorActive) return;
                    if (SpectatorSession.IsLocalSpectator) return;   // foreign session appeared mid-poll
                    if (ApiClient.SpectateGrantInFlight) return;     // r1 F5: a public grant started mid-poll
                    if (ApiClient.BroadcastGrantTransportUnsettled) return;   // r2 find 4
                    if (IsExcluded(resp.target.incarnation)) return; // belt: server already applied exclude=
                    BeginAcquisition(resp.target, Time.realtimeSinceStartup);
                    return;
                }

                if (_state == State.Watching && _ticket != null)
                {
                    // Refresh the HUD/lease metadata while the target is us.
                    if (resp.target != null
                        && string.Equals(resp.target.game_id, _ticket.GameId, StringComparison.Ordinal))
                        CurrentTargetMeta = resp.target;

                    if (resp.hasCurrent && !resp.currentStillEligible)
                    {
                        EnterLeaving("server verdict: " + resp.currentReason, invokeLeave: true, dueToFailure: false);
                        return;
                    }
                    if (resp.target != null
                        && !string.Equals(resp.target.game_id, _ticket.GameId, StringComparison.Ordinal))
                    {
                        // Rotation moved on. Leave; the next IDLE poll
                        // acquires the new target.
                        // W7: stamp the abandoned pair's sitting-end at the
                        // rotation decision itself — RetireTicket restamps at
                        // leave-complete seconds later, which merely refreshes
                        // the same entry (NoteTargetGone is idempotent per id).
                        try { PostSessionReport.NoteTargetGone(_ticket.GameId); } catch { }
                        EnterLeaving("rotation switch", invokeLeave: true, dueToFailure: false);
                        return;
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[BROADCAST] poll handling: {ex.Message}");
            }
        }

        // ── exclusion table ──────────────────────────────────────────────

        private static void AddExclusion(string gameId, string incarnation, string reason, float seconds)
        {
            if (string.IsNullOrEmpty(incarnation)) return;
            float now = Time.realtimeSinceStartup;
            PruneExclusions(now);
            for (int i = _exclusions.Count - 1; i >= 0; i--)
                if (string.Equals(_exclusions[i].Incarnation, incarnation, StringComparison.Ordinal))
                    _exclusions.RemoveAt(i);
            _exclusions.Add(new ExclusionEntry
            {
                Incarnation = incarnation,
                GameId = gameId ?? "",
                Reason = SanitizeReason(reason),
                ExpiresAt = now + seconds,
            });
            while (_exclusions.Count > EXCLUDE_MAX) _exclusions.RemoveAt(0);
        }

        private static bool IsExcluded(string incarnation)
        {
            if (string.IsNullOrEmpty(incarnation)) return false;
            float now = Time.realtimeSinceStartup;
            for (int i = 0; i < _exclusions.Count; i++)
                if (_exclusions[i].ExpiresAt > now
                    && string.Equals(_exclusions[i].Incarnation, incarnation, StringComparison.Ordinal))
                    return true;
            return false;
        }

        private static void PruneExclusions(float now)
        {
            for (int i = _exclusions.Count - 1; i >= 0; i--)
                if (_exclusions[i].ExpiresAt <= now) _exclusions.RemoveAt(i);
        }

        /// <summary>Wire format (§2a, matches the authored server parser
        /// exactly — main.py _broadcast_exclusions rsplit(":", 2)):
        /// "incarnation:reason:ttlSeconds,..." — reason must stay colon-free.</summary>
        private static string BuildExcludeCsv()
        {
            float now = Time.realtimeSinceStartup;
            PruneExclusions(now);
            if (_exclusions.Count == 0) return "";
            var sb = new StringBuilder(96);
            for (int i = 0; i < _exclusions.Count; i++)
            {
                var e = _exclusions[i];
                int ttl = Mathf.CeilToInt(e.ExpiresAt - now);
                if (ttl <= 0) continue;
                if (sb.Length > 0) sb.Append(',');
                sb.Append(e.Incarnation).Append(':').Append(e.Reason).Append(':').Append(ttl);
            }
            return sb.ToString();
        }

        private static string SanitizeReason(string reason)
        {
            if (string.IsNullOrEmpty(reason)) return "unknown";
            var sb = new StringBuilder(reason.Length);
            for (int i = 0; i < reason.Length && sb.Length < 32; i++)
            {
                char c = reason[i];
                if ((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_') sb.Append(c);
                else if (c >= 'A' && c <= 'Z') sb.Append(char.ToLowerInvariant(c));
                else if (c == ' ' || c == '-') sb.Append('_');
            }
            return sb.Length == 0 ? "unknown" : sb.ToString();
        }

        // ── §3b status lease ─────────────────────────────────────────────

        private static readonly string InstanceId = Guid.NewGuid().ToString("N");
        private static long _leaseSeq;
        private static float _nextLeaseWriteAt;
        private static bool _leaseDirEnsured;
        private static bool _leaseWriteWarned;
        private static readonly StringBuilder _leaseSb = new StringBuilder(512);

        // Series-score cache (5s TTL — mirrors SpectatorHud.SeriesLine but
        // emits the plain "w1-w2" the bot's overlay wants, not localized UI).
        private static string _cachedSeriesScore = "";
        private static float _seriesScoreCachedAt = -999f;

        private static void TickLease()
        {
            float now = Time.realtimeSinceStartup;
            if (now < _nextLeaseWriteAt) return;
            _nextLeaseWriteAt = now + 1f;
            try
            {
                WriteStatusFile();
            }
            catch (Exception ex)
            {
                // Never throw out of Step; one warn per session, then quiet.
                if (!_leaseWriteWarned)
                {
                    _leaseWriteWarned = true;
                    Plugin.Log?.LogWarning($"[BROADCAST] status lease write failed: {ex.Message}");
                }
            }
        }

        private static string LeaseStateString()
        {
            switch (_state)
            {
                case State.Idle:
                    // D1 CUT (ai-collab/streaming-design-d1-deltas.md,
                    // f14/f15/f16): NO new lease state for reports. While a
                    // post-session report is on screen the lease publishes
                    // plain "watching" so the bot HOLDS the Live scene. The
                    // director's INTERNAL state machine is untouched (still
                    // Idle), so the session-lifecycle classifiers (#381/#383)
                    // see nothing new — they key on real session events, not
                    // this label. Includes the F5 pause (Active with a null
                    // screen kind): the scene must not flap while the
                    // operator pokes the menu.
                    try { if (PostSessionReport.Active) return "watching"; } catch { }
                    return "idle";
                case State.Granting: return "granting";
                case State.Joining: return "joining";
                case State.AwaitingActivation: return "awaiting_activation";
                case State.Watching: return "watching";
                case State.Leaving: return "leaving";
                case State.Cancelling: return "cancelling";
                case State.Recover: return "recover";
                case State.Faulted: return "faulted";
                default: return "idle";
            }
        }

        private static void WriteStatusFile()
        {
            string path = null;
            try { path = Plugin.BroadcastStatusPath != null ? Plugin.BroadcastStatusPath.Value : null; } catch { }
            if (string.IsNullOrEmpty(path)) return;

            var meta = CurrentTargetMeta;
            bool haveGame = _ticket != null && meta != null
                            && string.Equals(meta.game_id, _ticket.GameId, StringComparison.Ordinal);

            BuildLeaseJson(haveGame, meta);

            if (!_leaseDirEnsured)
            {
                try
                {
                    string dir = Path.GetDirectoryName(path);
                    if (!string.IsNullOrEmpty(dir)) Directory.CreateDirectory(dir);
                }
                catch { }
                _leaseDirEnsured = true;
            }

            // Atomic publish (§3b): temp file in the same directory, then
            // File.Replace — the reader never sees a torn write. First write
            // (no destination yet) falls back to Move.
            string tmp = path + ".tmp";
            File.WriteAllText(tmp, _leaseSb.ToString());
            try { File.Replace(tmp, path, null); }
            catch (FileNotFoundException) { File.Move(tmp, path); }
        }

        private static void BuildLeaseJson(bool haveGame, ApiClient.BroadcastTargetInfo meta)
        {
            _leaseSeq++;
            var sb = _leaseSb;
            sb.Length = 0;
            sb.Append("{\"schema_version\":1");
            sb.Append(",\"instance_id\":\"").Append(InstanceId).Append('"');
            sb.Append(",\"seq\":").Append(_leaseSeq);
            sb.Append(",\"state\":\"").Append(LeaseStateString()).Append('"');
            if (_state == State.Faulted && _faultReason.Length > 0)
                sb.Append(",\"fault_reason\":\"").Append(LeaseEscape(_faultReason)).Append('"');
            sb.Append(",\"game_id\":\"").Append(haveGame ? LeaseEscape(meta.game_id) : "").Append('"');
            sb.Append(",\"mode\":\"").Append(haveGame ? LeaseEscape(meta.mode) : "").Append('"');
            sb.Append(",\"names\":[");
            if (haveGame && meta.names != null)
                for (int i = 0; i < meta.names.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append('"').Append(LeaseEscape(meta.names[i])).Append('"');
                }
            sb.Append(']');
            sb.Append(",\"ratings\":[");
            if (haveGame && meta.ratings != null)
                for (int i = 0; i < meta.ratings.Count; i++)
                {
                    if (i > 0) sb.Append(',');
                    sb.Append(meta.ratings[i].ToString("0.#", System.Globalization.CultureInfo.InvariantCulture));
                }
            sb.Append(']');
            sb.Append(",\"is_tournament\":").Append(haveGame && meta.is_tournament ? "true" : "false");
            sb.Append(",\"series_score\":\"").Append(LeaseEscape(ComputeSeriesScore())).Append('"');
            sb.Append(",\"phase\":\"").Append(haveGame ? LeaseEscape(meta.phase) : "").Append('"');
            // W7 report payload (D1 deltas f14/f15/f19): rides ONLY while a
            // report is VISIBLY on screen — state Idle AND the engine Active
            // AND a screen actually showing. Idle means no ticket, so haveGame
            // is false above: game_id/mode stay "" (today's never-fabricate
            // rule) and names[]/ratings[] stay EMPTY — no title composition
            // during reports (D1 f16; the bot's compose_title returns None on
            // empty names and platform titles keep the last live game's
            // text). The F5 pause nulls CurrentScreenKind (D1 f13): dropping
            // report_screen resets the bot's 3s-stable capture gate, so all
            // three fields are omitted together.
            try
            {
                if (_state == State.Idle && PostSessionReport.Active)
                {
                    string screen = PostSessionReport.CurrentScreenKind;
                    if (!string.IsNullOrEmpty(screen))
                    {
                        sb.Append(",\"report_screen\":\"").Append(LeaseEscape(screen)).Append('"');
                        sb.Append(",\"report_total_elo\":").Append(PostSessionReport.CurrentTotalElo);
                        sb.Append(",\"report_id\":\"").Append(LeaseEscape(PostSessionReport.CurrentReportId)).Append('"');
                    }
                }
            }
            catch { }
            // NEVER room_name / region (§3b/§7.1).
            sb.Append('}');
        }

        /// <summary>Full JSON escaping (#100: every control char escaped, not
        /// just the common four — names are hostile input).</summary>
        private static string LeaseEscape(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '"') sb.Append("\\\"");
                else if (c == '\\') sb.Append("\\\\");
                else if (c < 0x20) sb.Append("\\u").Append(((int)c).ToString("x4"));
                else sb.Append(c);
            }
            return sb.ToString();
        }

        // ── Stream-info fold-in (Aug 17, living Discord stream post) ─────
        // The VM bot advertises stream live-ness in a SIBLING file of the
        // status lease; this seat folds it into the authenticated
        // /broadcast/target poll so the SERVER can run the #scr-ranked-
        // streaming living-post state machine. The bot has no credentials by
        // design — the mod's steam session is the only channel off the VM.
        private static float _streamInfoReadAt = -999f;
        private static bool _streamInfoLive;
        private static string _streamInfoSession = "";
        private static string _streamInfoTwitchVod = "";
        private static string _streamInfoYoutubeVod = "";

        [Serializable]
        private class StreamInfoFile
        {
            public int schema_version;
            public bool live;
            public string session_id;
            // Direct VOD links resolved by the VM bot while live (Aug 18 —
            // the server's stream-ended post links them). Flat string
            // fields parse for free via JsonUtility (#73); absent in older
            // files -> null -> treated as empty.
            public string twitch_vod;
            public string youtube_vod;
            public double updated_wall;
        }

        internal static bool StreamInfoLive
        { get { RefreshStreamInfo(); return _streamInfoLive; } }
        internal static string StreamInfoSession
        { get { RefreshStreamInfo(); return _streamInfoSession ?? ""; } }
        internal static string StreamInfoTwitchVod
        { get { RefreshStreamInfo(); return _streamInfoTwitchVod ?? ""; } }
        internal static string StreamInfoYoutubeVod
        { get { RefreshStreamInfo(); return _streamInfoYoutubeVod ?? ""; } }

        private static void RefreshStreamInfo()
        {
            float now = Time.realtimeSinceStartup;
            if (now - _streamInfoReadAt < 10f) return;
            _streamInfoReadAt = now;
            _streamInfoLive = false;
            _streamInfoSession = "";
            _streamInfoTwitchVod = "";
            _streamInfoYoutubeVod = "";
            try
            {
                string statusPath = Plugin.BroadcastStatusPath != null ? Plugin.BroadcastStatusPath.Value : null;
                if (string.IsNullOrEmpty(statusPath)) return;
                string dir = System.IO.Path.GetDirectoryName(statusPath);
                if (string.IsNullOrEmpty(dir)) return;
                string p = System.IO.Path.Combine(dir, "stream-info.json");
                if (!System.IO.File.Exists(p)) return;
                var parsed = JsonUtility.FromJson<StreamInfoFile>(System.IO.File.ReadAllText(p));
                if (parsed == null || !parsed.live) return;
                // Freshness gate: a dead bot must not pin the Discord post
                // "live" forever. The bot heartbeat-rewrites every 30s while
                // live; same machine, so no steady-state skew — but a wall
                // clock can STEP (NTP correction), and a far-future stamp
                // would otherwise read "fresh" for the whole step size
                // (round-2 f11). Reject both directions.
                double nowWall = (DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds;
                if (parsed.updated_wall <= 0
                    || nowWall - parsed.updated_wall > 120
                    || parsed.updated_wall - nowWall > 120) return;
                _streamInfoLive = true;
                _streamInfoSession = parsed.session_id ?? "";
                // Only carried while live and only sane-looking https URLs
                // (the server re-validates against strict per-platform
                // patterns before they can reach the Discord post — this is
                // just the cheap client half so junk never even rides the
                // poll, #159: the server gate is the real one).
                string tv = parsed.twitch_vod ?? "";
                string yv = parsed.youtube_vod ?? "";
                _streamInfoTwitchVod = tv.Length <= 120 && tv.StartsWith("https://", StringComparison.Ordinal) ? tv : "";
                _streamInfoYoutubeVod = yv.Length <= 120 && yv.StartsWith("https://", StringComparison.Ordinal) ? yv : "";
            }
            catch { }
        }

        /// <summary>Plain "w1-w2" series tally for the lease, matched against
        /// the live-series feeds the spectator maintenance loop already
        /// refreshes. Empty when no series row matches (normal for casual /
        /// FFA / feed lag).</summary>
        private static string ComputeSeriesScore()
        {
            if (Time.realtimeSinceStartup - _seriesScoreCachedAt < 5f) return _cachedSeriesScore;
            _seriesScoreCachedAt = Time.realtimeSinceStartup;
            _cachedSeriesScore = "";
            try
            {
                var sids = SpectatorSync.FighterSteamIds;
                if (sids == null || sids.Length < 2) return _cachedSeriesScore;
                string mode = SpectatorSync.WatchedMode;
                if (mode == "1v1")
                {
                    var list = ApiClient.CachedActiveSeries;
                    if (list != null)
                        foreach (var s in list)
                        {
                            if (s == null) continue;
                            bool a = false, b = false;
                            foreach (var sid in sids)
                            {
                                if (sid == s.p1_steam_id) a = true;
                                else if (sid == s.p2_steam_id) b = true;
                            }
                            if (a && b)
                            {
                                bool flipped = sids.Length > 0 && sids[0] == s.p2_steam_id;
                                int w1 = flipped ? s.p2_wins : s.p1_wins;
                                int w2 = flipped ? s.p1_wins : s.p2_wins;
                                _cachedSeriesScore = w1 + "-" + w2;
                                break;
                            }
                        }
                }
                else if (mode == "2v2")
                {
                    var list = ApiClient.CachedActiveTeamSeries;
                    if (list != null)
                        foreach (var s in list)
                        {
                            if (s == null) continue;
                            int hits = 0;
                            foreach (var sid in sids)
                                if (sid == s.t1a_steam || sid == s.t1b_steam
                                    || sid == s.t2a_steam || sid == s.t2b_steam) hits++;
                            if (hits >= 3)
                            {
                                _cachedSeriesScore = s.t1_wins + "-" + s.t2_wins;
                                break;
                            }
                        }
                }
            }
            catch { _cachedSeriesScore = ""; }
            return _cachedSeriesScore;
        }
    }
}
