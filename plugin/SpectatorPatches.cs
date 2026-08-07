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
                // increment: winner points +1; at pointsToWinRound (2 in
                // every competitive room) the winner converts a round and
                // both points reset. Boundary snapshots overwrite with the
                // master's live values, correcting any drift.
                int p1p = p1PointsSet, p2p = p2PointsSet;
                int p1r = p1RoundsSet, p2r = p2RoundsSet;
                if (winningTeamID == 0) p1p++;
                else if (winningTeamID == 1) p2p++;
                if (winningTeamID == 0 && p1p >= 2) { p1r++; p1p = 0; p2p = 0; }
                else if (winningTeamID == 1 && p2p >= 2) { p2r++; p1p = 0; p2p = 0; }
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
            }
            catch { }
            return false;
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
                if (!RoomActors.IsSpectator(otherPlayer)) return true;   // inert
                Plugin.Log?.LogInfo($"[SPECTATE] spectator actor {otherPlayer.ActorNumber} left — suppressing vanilla match teardown");
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
                if (!RoomActors.IsSpectator(newPlayer)) return true;   // inert
                Plugin.Log?.LogInfo($"[SPECTATE] spectator actor {newPlayer.ActorNumber} joined — not a match-found event");
                return false;
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

                Plugin.Log?.LogWarning($"[SPECTATE] rejecting Player registration from " +
                    $"{(spectatorOwned ? "spectator" : "unauthorized")} actor {owner.ActorNumber}");
                try { player.gameObject.SetActive(false); } catch { }
                if (PhotonNetwork.IsMasterClient && unauthorized)
                {
                    try { PhotonNetwork.CloseConnection(owner); } catch { }
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
