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
            Plugin.Instance.StartCoroutine(ConnectAndJoin());
        }

        private static IEnumerator ConnectAndJoin()
        {
            string room = SpectatorSession.PendingRoom;
            string region = SpectatorSession.PendingRegion;
            float started = Time.unscaledTime;
            Plugin.Log?.LogInfo($"[SPECTATE] joiner start (region={region})");

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
                    if (!SpectatorSession.IsLocalSpectator) { _running = false; yield break; }   // cancelled
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
                            || !string.Equals(SpectatorSession.PendingRoom, room, StringComparison.Ordinal))
                        {
                            Plugin.Log?.LogWarning("[SPECTATE] session ended/changed during connect — abandoning join");
                            return;
                        }
                        Plugin.Log?.LogInfo("[SPECTATE] connected to master — joining room");
                        PhotonNetwork.JoinRoom(room);
                    }
                    catch (Exception ex)
                    {
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
                if (!SpectatorSession.IsLocalSpectator) { _running = false; yield break; }   // cancelled elsewhere
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
        /// behaviour's OnJoinRoomFailed). Only reacts while a spectator
        /// session is pending.</summary>
        internal static void OnJoinRoomFailed(short code, string message)
        {
            if (!SpectatorSession.IsLocalSpectator) return;
            Fail($"Photon join refused ({code}): {message}");
        }
    }
}
