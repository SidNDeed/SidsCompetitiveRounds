using System;
using HarmonyLib;
using Photon.Pun;
using Photon.Realtime;
using SoundImplementation;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// The MENU ADMISSION snapshot (lag-332 design v6 §2.1), kept after Sept 7
    /// design v2 §7 Item 2 removed the click decode it was built for: music is
    /// streamed now (DownloadHandlerAudioClip.streamAudio = true), so no click
    /// decodes anything and this class no longer gates the music engine's
    /// file opens. Two readers remain: ClickAdmissible (EmojiSprites' safe
    /// state for its own sprite decode) and AtAdmissibleMenu (MusicEngine's
    /// Previous and uncached-preview branches). The snapshot is still the
    /// right shape for them because Steam-invite acceptance, queue enrollment
    /// and the public WATCH flow begin their join several ticks before ANY
    /// engine-visible state changes (Photon stays ConnectedToMasterServer,
    /// the menu stays open, nothing is loading); a reader wants the snapshot
    /// identical and admissible on two DISTINCT earlier frames as well as at
    /// the moment it asks.
    /// </summary>
    internal static class MusicAdmission
    {
        internal struct Snapshot
        {
            public bool MenuOpen, Loading, GmPlaying, GmTestLive, GmArmsLive, MgrPresent;
            public int SceneCount, ActiveBuildIndex;
            public int PhotonState;
            public bool Enrollment, SpectateGrant, BroadcastGrant, JoinOp, SteamJoin;
            public bool PendingRoom, QueueBusy, Spectator, BroadcastBusy;
            public int Frame;
            public bool Admissible;
            public string Reason;

            public bool SameAs(in Snapshot o)
            {
                return MenuOpen == o.MenuOpen && Loading == o.Loading && GmPlaying == o.GmPlaying
                    && GmTestLive == o.GmTestLive && GmArmsLive == o.GmArmsLive && MgrPresent == o.MgrPresent
                    && SceneCount == o.SceneCount && ActiveBuildIndex == o.ActiveBuildIndex
                    && PhotonState == o.PhotonState && Enrollment == o.Enrollment
                    && SpectateGrant == o.SpectateGrant && BroadcastGrant == o.BroadcastGrant
                    && JoinOp == o.JoinOp && SteamJoin == o.SteamJoin && PendingRoom == o.PendingRoom
                    && QueueBusy == o.QueueBusy && Spectator == o.Spectator && BroadcastBusy == o.BroadcastBusy
                    && Admissible == o.Admissible;
            }

            public string Describe()
            {
                return $"frame={Frame} menu={MenuOpen} loading={Loading} gmPlaying={GmPlaying} gmTest={GmTestLive} gmArms={GmArmsLive}"
                    + $" scenes={SceneCount}/{ActiveBuildIndex} photon={PhotonState} enroll={Enrollment} specGrant={SpectateGrant}"
                    + $" bcastGrant={BroadcastGrant} joinOp={JoinOp} steamJoin={SteamJoin} pendingRoom={PendingRoom}"
                    + $" queueBusy={QueueBusy} spectator={Spectator} bcastBusy={BroadcastBusy} mgr={MgrPresent}"
                    + $" admissible={Admissible}{(Admissible ? "" : " (" + Reason + ")")}";
            }
        }

        // Two prior observations on distinct frames + the current one. The
        // ClickAdmissible compares all three (design v6 §2.1: "identical complete
        // snapshot on two DISTINCT prior frames", frame count is metadata and
        // never part of equality).
        private static Snapshot _prev1, _prev2, _current;
        private static bool _havePrev1, _havePrev2;

        /// <summary>Steam invite acceptance calls SteamMatchmaking.JoinLobby
        /// immediately and only closes the menu in the asynchronous
        /// OnLobbyEnter callback (ClientSteamLobby.cs:239-244 / 442-456) —
        /// the one join intent no engine-visible state exposes. Set by the
        /// JoinLobby prefix below, cleared by OnLobbyEnter, bounded at 30 s so
        /// a lost callback cannot deny the menu forever.</summary>
        internal static float SteamLobbyJoinUnsettledUntil = -1f;

        internal static void Tick()
        {
            try
            {
                var snap = Compute();
                if (_current.Frame == snap.Frame) return;   // duplicate hosts: one observation per frame
                if (_havePrev1) { _prev2 = _prev1; _havePrev2 = true; }
                _prev1 = _current; _havePrev1 = _current.Frame > 0;
                _current = snap;
            }
            catch (Exception ex)
            {
                // Any accessor throw = unknown = deny (fail-closed).
                _current = new Snapshot { Frame = Time.frameCount, Admissible = false, Reason = "snapshot-threw: " + ex.Message };
            }
        }

        /// <summary>The click precondition: the CURRENT snapshot (recomputed
        /// now, not the tick's copy) is admissible and identical to the two
        /// most recent PRIOR distinct-frame observations — which must be the
        /// two frames immediately preceding this one, including the tick's
        /// own observation of the current frame when it already ran.
        /// impl-review r1 HIGH 2: comparing against _prev1/_prev2 alone let a
        /// UI callback that runs BEFORE the host's Update skip the observation
        /// of frame N-1 (held in _current), so an unsafe N-1 was invisible.
        /// Returns the current snapshot for the caller's log.</summary>
        internal static bool ClickAdmissible(out Snapshot now, out string why)
        {
            now = default;
            why = null;
            try
            {
                now = Compute();
                if (!now.Admissible) { why = now.Reason; return false; }
                Snapshot a, b;   // the two prior observations, newest first
                if (_current.Frame == now.Frame)
                {
                    // The tick already observed this frame: prior = _prev1, _prev2.
                    if (!_havePrev1 || !_havePrev2) { why = "no stable history"; return false; }
                    a = _prev1; b = _prev2;
                }
                else
                {
                    // The tick has not run this frame yet: _current IS frame N-1.
                    if (_current.Frame <= 0 || !_havePrev1) { why = "no stable history"; return false; }
                    a = _current; b = _prev1;
                }
                if (!(a.Frame < now.Frame && b.Frame < a.Frame)) { why = "history frames not distinct"; return false; }
                if (a.Frame != now.Frame - 1 || b.Frame != now.Frame - 2) { why = "history frames not consecutive"; return false; }
                if (!a.Admissible || !b.Admissible) { why = "prior frame not admissible"; return false; }
                if (!now.SameAs(a) || !now.SameAs(b)) { why = "snapshot changed within the stability window"; return false; }
                return true;
            }
            catch (Exception ex) { why = "click-snapshot threw: " + ex.Message; return false; }
        }

        /// <summary>Menu-context test for non-decode decisions (Previous's
        /// "at the menu" branch, an uncached preview click): recomputed NOW
        /// (r5 LOW 12 — the tick's copy can be a frame stale during a
        /// menu-to-game transition). Any accessor throw = not at the menu.</summary>
        internal static bool AtAdmissibleMenu
        {
            get { try { return Compute().Admissible; } catch { return false; } }
        }

        private static Snapshot Compute()
        {
            var s = new Snapshot { Frame = Time.frameCount, Admissible = true, Reason = "" };
            float rt = Time.realtimeSinceStartup;

            var mm = MainMenuHandler.instance;
            s.MenuOpen = mm != null && mm.isOpen;
            var ls = LoadingScreen.instance;
            s.Loading = ls != null && ls.IsLoading;
            var gm = GameManager.instance;
            s.GmPlaying = gm == null || gm.isPlaying;   // no manager = unknown = playing (deny)
            var gt = GM_Test.instance;
            s.GmTestLive = gt != null && gt.isActiveAndEnabled;
            var ga = GM_ArmsRace.instance;
            s.GmArmsLive = ga != null && ga.isActiveAndEnabled;
            s.SceneCount = UnityEngine.SceneManagement.SceneManager.sceneCount;
            s.ActiveBuildIndex = UnityEngine.SceneManagement.SceneManager.GetActiveScene().buildIndex;
            s.PhotonState = (int)PhotonNetwork.NetworkClientState;
            s.Enrollment = ApiClient.EnrollmentTransportActive;
            s.SpectateGrant = ApiClient.SpectateGrantInFlight;
            s.BroadcastGrant = ApiClient.BroadcastGrantTransportUnsettled;
            s.JoinOp = SpectatorJoiner.JoinOpUnsettled;
            s.SteamJoin = SteamLobbyJoinUnsettledUntil > rt;
            s.PendingRoom = !string.IsNullOrEmpty(Plugin.PendingRankedRoom);
            s.QueueBusy = ApiClient.CurrentQueueState != ApiClient.QueueState.Idle
                || ApiClient.CurrentTeamQueueState != ApiClient.TeamQueueState.Idle
                || ApiClient.IsOvtQueuePolling
                || ApiClient.IsFfaQueuePolling
                || !string.IsNullOrEmpty(ApiClient.ActiveFfaLobbyId);
            s.Spectator = SpectatorSession.IsLocalSpectator;
            s.BroadcastBusy = BroadcastMode.AcquisitionBusy;
            s.MgrPresent = SoundMusicManager.Instance != null;

            string deny = null;
            if (!s.MenuOpen) deny = "menu not open";
            else if (s.Loading) deny = "loading screen";
            else if (s.GmPlaying) deny = "game playing";
            else if (s.GmTestLive) deny = "GM_Test live";
            else if (s.GmArmsLive) deny = "GM_ArmsRace live";
            else if (s.SceneCount != 1 || s.ActiveBuildIndex != 0) deny = "not the lone menu scene";
            else if (!PhotonStateAllowed(s.PhotonState)) deny = "photon state " + s.PhotonState;
            else if (s.Enrollment) deny = "queue enrollment in flight";
            else if (s.SpectateGrant) deny = "spectate grant in flight";
            else if (s.BroadcastGrant) deny = "broadcast grant unsettled";
            else if (s.JoinOp) deny = "spectator join op unsettled";
            else if (s.SteamJoin) deny = "steam lobby join unsettled";
            else if (s.PendingRoom) deny = "pending room";
            else if (s.QueueBusy) deny = "queue busy";
            else if (s.Spectator) deny = "spectator";
            else if (s.BroadcastBusy) deny = "broadcast acquisition";
            else if (!s.MgrPresent) deny = "no music manager";
            if (deny != null) { s.Admissible = false; s.Reason = deny; }
            return s;
        }

        // The four idle ClientState members (Disconnected, PeerCreated,
        // ConnectedToMasterServer, JoinedLobby — compared by NAME; Photon's
        // numeric values are irrelevant here); every other state
        // (authenticating, joining, joined, leaving, connecting, name-server
        // transitions) denies. A lingering post-Sandbox Joined denies too —
        // documented fail-closed (design v6 §2.1).
        private static bool PhotonStateAllowed(int st)
        {
            return st == (int)ClientState.Disconnected
                || st == (int)ClientState.PeerCreated
                || st == (int)ClientState.ConnectedToMasterServer
                || st == (int)ClientState.JoinedLobby;
        }
    }

    /// <summary>Steam-invite intent latch (design v6 §2.1). ClientSteamLobby is
    /// the game's own class (Assembly-CSharp, publicized), so the private
    /// methods bind by name; a missing target throws at patch time (loud —
    /// learning #83) rather than silently leaving the latch dead.</summary>
    [HarmonyPatch]
    internal static class MusicAdmission_SteamLobbyLatchPatch
    {
        [HarmonyPatch(typeof(Landfall.Network.ClientSteamLobby), "JoinLobby")]
        [HarmonyPrefix]
        private static void JoinLobbyPrefix()
        {
            try { MusicAdmission.SteamLobbyJoinUnsettledUntil = Time.realtimeSinceStartup + 30f; } catch { }
        }

        [HarmonyPatch(typeof(Landfall.Network.ClientSteamLobby), "OnLobbyEnter")]
        [HarmonyPostfix]
        private static void OnLobbyEnterPostfix()
        {
            try { MusicAdmission.SteamLobbyJoinUnsettledUntil = -1f; } catch { }
        }
    }
}
