using System;
using System.Collections;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 2 — the connect/join state
    /// machine for a spectator seat.
    ///
    /// Deliberately NOT the QueueJoiner: a spectator join is a DIRECT,
    /// region-pinned `PhotonNetwork.JoinRoom(exactName)` — never
    /// JoinOrCreateRoom (an expired game must FAIL to join, not create an
    /// empty room the spectator then sits in alone), and never the vanilla
    /// ForceRegionJoin (it drives the lobby-listing flow; spectatable rooms
    /// are joined by exact server-issued name, design §3.1).
    ///
    /// Ordering contract (each step gated on the previous):
    ///   1. Disconnect fully if connected (a live master-server connection
    ///      cannot be region-repinned in place).
    ///   2. Stage the pre-join role properties while Disconnected — the ONLY
    ///      state SpectatorSession.StagePreJoinProperties accepts (#287).
    ///   3. Region-pin (RegionSelector.region + m_ForceRegion, #49) and ride
    ///      NCH.DoActionWhenConnected to ConnectedToMasterServer (#21).
    ///   4. JoinRoom(exact name). OnJoinedRoom's spectator branch takes over.
    ///
    /// Every failure funnels through Fail(): end the session, tell the user,
    /// NetworkRestart back to the menu (the codebase's one honest
    /// abort-to-menu lever, #252c). No failure here can touch fighters —
    /// we are not in their room yet.
    /// </summary>
    internal static class SpectatorJoiner
    {
        private static bool _running;

        /// <summary>§3a ticket hook (#367 ownership token): a broadcast
        /// CancelAcquisition force-releases the latch after bumping the
        /// shared-flow generation. Any still-live coroutine from the old arc
        /// sees the stale generation on its next check and exits without
        /// touching the latch again. Never called by public spectate paths.</summary>
        internal static void ReleaseLatchForStaleTicket()
        {
            _running = false;
        }

        // ── join-op ownership (broadcast r2 find 1) ──────────────────────
        //
        // Photon's room-entry handoff spans states an enumeration cannot
        // safely cover (Joining -> DisconnectingFromMasterServer ->
        // ConnectingToGameServer -> auth -> Joining -> Joined): an accepted
        // enter op can still land while the client reads as "not room-bound".
        // So the op is OWNED explicitly: the flag is set immediately BEFORE
        // PhotonNetwork.JoinRoom and cleared only on the exact terminal
        // signals — OnJoinedRoom (success, any room: one op at a time),
        // OnJoinRoomFailed, full disconnect, or a synchronous send refusal.
        // CancelAcquisition's teardown, VerifyCancelClean, and this joiner's
        // own timeout tail all DEFER against it.
        private static bool _joinOpUnsettled;

        /// <summary>True while a spectate JoinRoom operation is dispatched
        /// but not yet terminally resolved. Teardown of the spectator role /
        /// staged props must never run while this holds.</summary>
        internal static bool JoinOpUnsettled => _joinOpUnsettled;

        private static void NoteJoinIssued()
        {
            _joinOpUnsettled = true;
            Plugin.Log?.LogInfo("[SPECTATE] join op issued");
        }

        /// <summary>Terminal settlement relay — called from the Photon
        /// callbacks (joined / join-failed / disconnected) and the refusal
        /// paths. Idempotent; no-op when no op is outstanding.</summary>
        internal static void NoteJoinSettled(string how)
        {
            if (!_joinOpUnsettled) return;
            _joinOpUnsettled = false;
            Plugin.Log?.LogInfo($"[SPECTATE] join op settled ({how})");
        }

        /// <summary>Watchdog budget for the whole connect+join sequence.
        /// Generous: disconnect drain + region connect + join is normally
        /// under 10s; 45s covers a slow relay without stranding the UI.</summary>
        private const float JOIN_TIMEOUT_SECONDS = 45f;

        /// <summary>Begin the join for the already-begun SpectatorSession.
        /// Caller must have called SpectatorSession.BeginSession first.</summary>
        internal static void StartJoin()
        {
            if (_running) { Plugin.Log?.LogWarning("[SPECTATE] joiner already running"); return; }
            if (!SpectatorSession.IsLocalSpectator || string.IsNullOrEmpty(SpectatorSession.PendingRoom))
            {
                Plugin.Log?.LogWarning("[SPECTATE] StartJoin without a session — ignored");
                return;
            }
            if (Plugin.Instance == null)
            {
                SpectatorSession.EndSession("no coroutine host");
                return;
            }
            _running = true;
            // §3a: capture the shared-flow generation for the whole arc —
            // consumed ONLY when the session is BROADCAST-OWNED (r2 find 3:
            // a PUBLIC join is structurally exempt from director-generation
            // invalidation; a director bump mid-join must never make a
            // human's joiner abandon its own live session). On non-broadcast
            // installs broadcastOwned is always false and the checks are
            // constant pass-throughs (#367 pattern).
            bool broadcastOwned = false;
            try { broadcastOwned = SpectatorSession.BroadcastOwned; } catch { }
            Plugin.Instance.StartCoroutine(ConnectAndJoin(BroadcastMode.SharedFlowGeneration, broadcastOwned));
        }

        private static bool ArcStale(int flowGen, bool broadcastOwned)
            => broadcastOwned && BroadcastMode.SharedFlowStale(flowGen);

        private static IEnumerator ConnectAndJoin(int flowGen, bool broadcastOwned)
        {
            string room = SpectatorSession.PendingRoom;
            string region = SpectatorSession.PendingRegion;
            float started = Time.unscaledTime;
            // §7.1: region is masked on the broadcast seat (the NCH diag patch
            // masks its region too — one policy for the whole seat).
            Plugin.Log?.LogInfo($"[SPECTATE] joiner start (region={(BroadcastMode.IsBroadcastIdentity ? "(masked)" : region)})");

            // Close menus so the room join doesn't land under an open ListMenu
            // (same courtesy the QueueJoiner extends).
            try { CharacterCreatorHandler.instance?.CloseMenus(); } catch { }
            try { MainMenuHandler.instance?.Close(); } catch { }

            // 1. Full disconnect. PhotonNetwork.Disconnect is async — wait for
            // the client to actually reach Disconnected before staging.
            bool wasConnected = false;
            try { wasConnected = PhotonNetwork.IsConnected; } catch { }
            if (wasConnected)
            {
                try { PhotonNetwork.Disconnect(); } catch { }
                while (true)
                {
                    if (!SpectatorSession.IsLocalSpectator
                        || ArcStale(flowGen, broadcastOwned)) { _running = false; yield break; }   // cancelled
                    bool done = false;
                    try
                    {
                        done = !PhotonNetwork.IsConnected
                               && PhotonNetwork.NetworkClientState == Photon.Realtime.ClientState.Disconnected;
                    }
                    catch { }
                    if (done) break;
                    if (Time.unscaledTime - started > 15f)
                    {
                        Fail("disconnect timed out");
                        yield break;
                    }
                    yield return null;
                }
            }

            // 2. Stage the role while Disconnected/PeerCreated — the only
            // window where the property provably rides the join payload (#287).
            string steamId = "";
            try { steamId = MatchTracker.LocalSteamId ?? ""; } catch { }
            if (!SpectatorSession.StagePreJoinProperties(steamId))
            {
                Fail("could not stage spectator role");
                yield break;
            }

            // 3. Region pin + connect (the #49 pattern the QueueJoiner uses).
            var nch = NetworkConnectionHandler.instance;
            if (nch == null)
            {
                Fail("no NetworkConnectionHandler");
                yield break;
            }
            try
            {
                if (!string.IsNullOrEmpty(region)) RegionSelector.region = region;
                nch.m_ForceRegion = true;
                // Clear any stale vanilla search context — the joiner owns the
                // connection now (same hygiene as the QueueJoiner, July 21 fix).
                try { nch.m_searchingType = (NetworkConnectionHandler.SearchingType)0; } catch { }
            }
            catch (Exception ex)
            {
                Fail($"region pin failed: {ex.Message}");
                yield break;
            }

            // 4. Connect, then DIRECT JoinRoom. The captured room doubles as
            // the cancellation token (the QueueJoiner pattern): EndSession or
            // a replacement grant clears/repoints it, and a canceled join must
            // not enter the dead room.
            try
            {
                nch.StartCoroutine(nch.DoActionWhenConnected(() =>
                {
                    try
                    {
                        if (!SpectatorSession.IsLocalSpectator
                            || ArcStale(flowGen, broadcastOwned)
                            || !string.Equals(SpectatorSession.PendingRoom, room, StringComparison.Ordinal))
                        {
                            Plugin.Log?.LogWarning("[SPECTATE] session ended/changed during connect — abandoning join");
                            return;
                        }
                        Plugin.Log?.LogInfo("[SPECTATE] connected to master — joining room");
                        // r2 find 1: own the op BEFORE dispatch; a refused
                        // send settles immediately (no op left the client).
                        NoteJoinIssued();
                        bool sent = PhotonNetwork.JoinRoom(room);
                        if (!sent) NoteJoinSettled("send refused");
                    }
                    catch (Exception ex)
                    {
                        NoteJoinSettled("dispatch threw");
                        Plugin.Log?.LogError($"[SPECTATE] JoinRoom threw: {ex.Message}");
                    }
                }));
            }
            catch (Exception ex)
            {
                Fail($"connect failed: {ex.Message}");
                yield break;
            }

            // 5. Watchdog. Success = in the exact target room (OnJoinedRoom's
            // spectator branch does the real work; we only stop watching).
            while (Time.unscaledTime - started < JOIN_TIMEOUT_SECONDS)
            {
                if (!SpectatorSession.IsLocalSpectator
                    || ArcStale(flowGen, broadcastOwned)) { _running = false; yield break; }   // cancelled elsewhere
                bool inTarget = false;
                try
                {
                    inTarget = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode
                               && string.Equals(PhotonNetwork.CurrentRoom?.Name, room, StringComparison.Ordinal);
                }
                catch { }
                if (inTarget)
                {
                    _running = false;
                    try { nch.m_ForceRegion = false; } catch { }
                    yield break;
                }
                yield return null;
            }
            // Stale-arc guard (§3a): a cancel landing on the exact budget
            // frame must not let this tail Fail() against a session the
            // director may already have replaced. Same-frame with Fail, so
            // there is no yield between check and use.
            if (ArcStale(flowGen, broadcastOwned)) { _running = false; yield break; }
            // r2 find 1 + r3 finds 1/3: the deferral below is BROADCAST-ONLY.
            // A public seat gets the exact pre-batch tail (immediate success
            // re-check, then Fail + notify + restart — no forced disconnect,
            // no extra blackout wait); its join-op flag still resolves via
            // the real terminal relays (Fail's NetworkRestart disconnects,
            // which fires OnDisconnected). On the BROADCAST seat a timeout
            // mid-handoff must not tear the role down while the accepted
            // enter op can still land: force the op dead (Disconnect closes
            // the socket) and wait for the TERMINAL callback. There is no
            // synthetic settlement (r3 find 1 — an elapsed-time clear is the
            // #367 ownership hole): if no terminal signal arrives, the op is
            // cleanup ambiguity and the director FAULTS (design §11
            // fault-early floor) — the bot replaces the ROUNDS process,
            // which is provably clean. The flag clears only via real
            // terminal signals or process death.
            if (broadcastOwned && _joinOpUnsettled)
            {
                Plugin.Log?.LogWarning("[SPECTATE] join timed out with the op unsettled — forcing disconnect and waiting for its terminal signal");
                try { PhotonNetwork.Disconnect(); } catch { }
                float settleStart = Time.unscaledTime;
                while (_joinOpUnsettled && Time.unscaledTime - settleStart < 10f)
                {
                    if (!SpectatorSession.IsLocalSpectator
                        || ArcStale(flowGen, broadcastOwned)) { _running = false; yield break; }
                    yield return null;
                }
                if (_joinOpUnsettled)
                {
                    Plugin.Log?.LogError("[SPECTATE] join op produced no terminal signal after forced disconnect — faulting the director (role/props untouched)");
                    try { BroadcastMode.FaultDirector("join_op_unsettled"); } catch { }
                    _running = false;
                    yield break;   // no Fail(): never tear the role down under an unsettled op
                }
            }
            // Success re-check BEFORE declaring timeout (Aug 10 r11 find 1:
            // PUN can dispatch the successful join on the exact frame the
            // watchdog budget lapses — the loop condition then fails without
            // running its own success check, and Fail() on a session that
            // actually JOINED tore down the statics before the room exit was
            // observed, latching session state into later fighter play).
            bool joinedAfterAll = false;
            try
            {
                joinedAfterAll = SpectatorSession.IsLocalSpectator
                                 && PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode
                                 && string.Equals(PhotonNetwork.CurrentRoom?.Name, room, StringComparison.Ordinal);
            }
            catch { }
            if (joinedAfterAll)
            {
                _running = false;
                try { nch.m_ForceRegion = false; } catch { }
                yield break;
            }
            Fail("join timed out — the game may have ended");
        }

        /// <summary>Every joiner failure lands here. Ends the session and
        /// returns to the menu. Never touches a fighter room — either we are
        /// not in a room, or we are in the WRONG room (leave it).</summary>
        internal static void Fail(string why)
        {
            _running = false;
            Plugin.Log?.LogWarning($"[SPECTATE] join failed: {why}");
            // Release the seat we will never occupy (Codex r2 find 12: an
            // unreleased lease from a failed join blocks this account's next
            // grant until heartbeat expiry).
            try { ApiClient.SpectateLeaveNotify(); } catch { }
            SpectatorSession.EndSession($"join failed: {why}");
            try { CompetitiveUI.ShowNotification(I18n.Tr("Could not join as spectator - the game may have ended."), Color.red, 6f); }
            catch { }
            try
            {
                var nch = NetworkConnectionHandler.instance;
                if (nch != null)
                {
                    nch.m_ForceRegion = false;
                    nch.NetworkRestart();
                }
            }
            catch { }
        }

        /// <summary>Photon join-failure callback relay (wired from the
        /// behaviour's OnJoinRoomFailed). Settlement bookkeeping runs FIRST,
        /// unconditionally (r2 find 1 — the op is terminally resolved whether
        /// or not a session still exists); the Fail teardown keeps its
        /// session gate.</summary>
        internal static void OnJoinRoomFailed(short code, string message)
        {
            NoteJoinSettled($"join refused ({code})");
            if (!SpectatorSession.IsLocalSpectator) return;
            Fail($"Photon join refused ({code}): {message}");
        }
    }
}
