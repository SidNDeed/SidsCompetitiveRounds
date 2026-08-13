using System;
using ExitGames.Client.Photon;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 0 — local spectator session
    /// state and the pre-join property staging contract.
    ///
    /// Everything here is STATIC by design: a pending spectator join has to
    /// survive GameObject destruction and scene changes exactly like the
    /// existing pending-room statics do (#22), and NetworkRestart tears down
    /// coroutine hosts mid-flight (#249) — so no state that decides whether
    /// we are a spectator may live on a component.
    ///
    /// PHASE 0 SCOPE: this file establishes the contract (role property,
    /// session statics, staging rules) and the local-role flag that
    /// RoomActors reads. It does NOT yet join rooms, suppress spawning, or
    /// render — those are Phases 1-3. Nothing here has any effect until
    /// something sets IsLocalSpectator, so it is inert in the shipped build.
    /// </summary>
    /// <summary>
    /// ── RESIDUAL RISK REGISTER (accepted after Codex rounds 1-2) ────────
    /// These are DELIBERATE scope limits, not oversights. Each was weighed
    /// against what a Photon-cloud mod can actually enforce (#277: when a
    /// reviewer keeps returning to a spot, weaken the claim rather than
    /// pretend the mechanism exists). The design doc §6.6 states the
    /// underlying limit: possession of a room name cannot be
    /// cryptographically rejected at the Photon layer.
    ///
    /// 1. Actor identity is first-bind, not proven: an attacker holding BOTH
    ///    the unpublished room name AND a victim's live lease timing can win
    ///    the bind race. They gain: watching a match. They could already
    ///    join any room by name pre-spectator; the frozen roster +
    ///    registration firewall means they can never FIGHT. Accepted.
    /// 2. A modified spectator that /leave-s its lease but keeps its Photon
    ///    seat is snapshot-fed until the master's validation TTL (5 min)
    ///    closes it (cooperatively — physical eviction is best-effort).
    ///    Betting policy note (superseded Aug 9): spectators MAY bet by
    ///    ruling; the score-based close windows are the information gate, so
    ///    a lingering seat gains nothing a non-spectator lacks. Accepted.
    /// 3. Diagnostic logs outside the spectator files (NetworkRestart diag,
    ///    queue joiner, 2v2 diag) still print room names — a pre-existing
    ///    pattern shared with fighters' own logs and bug bundles. Spectator
    ///    code itself logs only room hashes. Accepted.
    /// 4. Sub-second races between an in-flight queue POST and a WATCH click
    ///    are not fenced (commitment checks run before grant and again in
    ///    its callback; the residual window is one HTTP round-trip).
    /// 5. FFA spawn-shuffle inputs (gameNumber/pointsTotal) are not
    ///    snapshotted — a late spectator can compute a different spawn
    ///    permutation for one transition until owner streams correct it.
    ///    Cosmetic; FFA spectate is playtest-gated.
    /// 6. spectate_games rows have no explicit end event — liveness decays
    ///    via last_attest_at/last_battle_at staleness (#276: absence of
    ///    renewal frees; nothing needs a cleanup path to fire).
    /// </summary>
    internal static class SpectatorSession
    {
        /// <summary>Wire protocol version for the spectator role. Bumped when
        /// the snapshot/lease contract changes incompatibly; a fighter room
        /// can then refuse an incompatible spectator instead of admitting one
        /// that would mis-render or mis-handshake.
        /// 2 (Aug 10): the desync/safety batch — protocol-1 clients carry the
        /// PlayerDied/master-window RPC hazard, the poison roster-quarantine
        /// misfire and unregistered husk views, so mixed rooms are excluded
        /// (design-review blocker 3). The server floor moves in lockstep.</summary>
        internal const int PROTOCOL = 2;

        /// <summary>Sid's decision (Aug 6): 4 spectator seats per game.
        /// Rooms are created with MaxPlayers = fighters + SEAT_CAP.</summary>
        internal const int SEAT_CAP = 4;

        /// <summary>THE local role flag. Read by RoomActors.LocalIsSpectator
        /// and by every suppression guard. Set only by the spectator join
        /// path, cleared only by EndSession().</summary>
        internal static bool IsLocalSpectator { get; private set; }

        // Pending grant — statics, per #22.
        internal static string PendingRoom { get; private set; } = "";
        internal static string PendingRegion { get; private set; } = "";
        internal static string GrantId { get; private set; } = "";
        internal static string LeaseToken { get; private set; } = "";
        internal static string WatchingGameId { get; private set; } = "";
        internal static float SessionStartedAt { get; private set; }

        /// <summary>Set when the session is asked to end but the room exit
        /// has not been observed yet. A standing INTENT, not a request
        /// (#252e): every later signal bends toward OUT until the exit is
        /// confirmed.</summary>
        internal static bool LeaveRequested { get; private set; }

        // Fighter display metadata from the games-list entry we granted
        // against (playtest #2b): roster-aligned arrays. Display-only.
        internal static string[] WatchedRoster { get; private set; } = new string[0];
        internal static string[] WatchedNames { get; private set; } = new string[0];
        internal static string[] WatchedTitles { get; private set; } = new string[0];
        internal static string[] WatchedRatings { get; private set; } = new string[0];

        /// <summary>Per-title colours, roster-aligned, pipe-joined exactly like
        /// WatchedTitles. Aug 12 item 9b: the HUD rendered every title in one
        /// hardcoded ochre because the games-list entry carried the title TEXT
        /// and not its colour — every other title surface in the mod renders
        /// `[Title]` in the title's own colour. Optional on the wire: unless the
        /// array arrives roster-aligned it is dropped entirely (see
        /// SetWatchedMeta), so a client running ahead of the server field
        /// renders exactly as before instead of breaking.</summary>
        internal static string[] WatchedTitleColors { get; private set; } = new string[0];

        /// <summary>NO DEFAULT on titleColorsPsv, deliberately: it shipped as an
        /// optional parameter, the one caller kept passing four arguments, and
        /// the whole colour feature was a silent no-op that still compiled.
        /// Required, so omitting it is a build error instead.</summary>
        internal static void SetWatchedMeta(string rosterCsv, string namesCsv, string titlesPsv,
                                            string ratingsCsv, string titleColorsPsv)
        {
            try
            {
                WatchedRoster = (rosterCsv ?? "").Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                WatchedNames = (namesCsv ?? "").Split(new[] { ", " }, StringSplitOptions.None);
                WatchedTitles = (titlesPsv ?? "").Split('|');
                WatchedRatings = (ratingsCsv ?? "").Split(',');
                // Colours are positional, so a length that does not match the
                // roster is not a partial array to index into — it is an array
                // whose positions mean something else. Dropping it lands every
                // title on the grey fallback (what a server without the field
                // already gives); keeping it would paint one fighter's title
                // in another fighter's colour. Covers both the older-server
                // case (field absent) and a stray '|' inside a colour.
                var tc = (titleColorsPsv ?? "").Split('|');
                WatchedTitleColors = tc.Length == WatchedRoster.Length ? tc : new string[0];
            }
            catch { }
        }

        /// <summary>Begin a spectator session from a server grant. Returns
        /// false (and changes nothing) if the client is in any state where
        /// spectating would fight an existing commitment — the caller must
        /// surface that to the user rather than silently cancelling their
        /// queue/match (design §3.1).</summary>
        internal static bool BeginSession(string room, string region, string grantId,
                                          string leaseToken, string gameId, out string refusal)
        {
            refusal = "";
            try
            {
                if (string.IsNullOrEmpty(room)) { refusal = "no room"; return false; }
                if (IsLocalSpectator) { refusal = "already spectating"; return false; }
                // #122: OfflineMode lingers InRoom at the menu after Sandbox,
                // so gate on a genuine ONLINE room.
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode)
                {
                    refusal = "leave your current game first";
                    return false;
                }
                // Codex r1 find 6: an in-flight FIGHTER commitment must win.
                // A pending queue room / lock slot means a ranked join can
                // land any second — beginning a spectate session here would
                // race it (and if the queue join wins after our cr_spec
                // staging, the fighter enters ranked marked as a spectator).
                if (!string.IsNullOrEmpty(Plugin.PendingRankedRoom)
                    || Plugin.Pending2v2Slot >= 0
                    || Plugin.PendingOvtSlot >= 0
                    || Plugin.PendingFfaSlot >= 0)
                {
                    refusal = "a match is being prepared - leave the queue first";
                    return false;
                }
                PendingRoom = room;
                PendingRegion = region ?? "";
                GrantId = grantId ?? "";
                LeaseToken = leaseToken ?? "";
                WatchingGameId = gameId ?? "";
                LeaveRequested = false;
                SessionStartedAt = Time.unscaledTime;
                IsLocalSpectator = true;
                // Room name is a join credential — never log it whole (Codex
                // r1 find 4; logs travel inside bug-report bundles).
                Plugin.Log?.LogInfo($"[SPECTATE] session begin room#{room.GetHashCode():X8} region={PendingRegion} game={WatchingGameId}");
                return true;
            }
            catch (Exception ex)
            {
                refusal = ex.Message;
                return false;
            }
        }

        /// <summary>Mark the session as leaving. Idempotent. The flag is
        /// consumed at the observed room exit, not here — a lost ack must
        /// not strand the client in a half-spectating state (#249).</summary>
        internal static void RequestLeave()
        {
            if (!IsLocalSpectator) return;
            LeaveRequested = true;
            Plugin.Log?.LogInfo("[SPECTATE] leave requested");
        }

        /// <summary>True when EndSession ran while the client was still in a
        /// room (or otherwise unable to clear the staged role) — the property
        /// clear is retried from the watcher tick until it lands. Without
        /// this, cr_spec persists onto the NEXT room this client joins as a
        /// FIGHTER, and every peer would classify them spectator (Codex r1
        /// find 2 — the worst state this system can produce).</summary>
        private static bool _pendingPropClear;

        /// <summary>Fully end the session and drop every static. Safe to call
        /// unconditionally (e.g. from a room-exit observer).</summary>
        internal static void EndSession(string reason)
        {
            if (!IsLocalSpectator && string.IsNullOrEmpty(PendingRoom)) return;
            bool wasSpectating = IsLocalSpectator;
            Plugin.Log?.LogInfo($"[SPECTATE] session end ({reason})");
            // Flag teardown must be independent of the role flag and of the
            // room-exit observation (r11 find 1: a Fail() racing a same-frame
            // successful join cleared the role before the exit was observed,
            // so OnLeftSpectatorRoom's clear never ran and the cooperative-
            // close opt-in leaked into later FIGHTER sessions). EndSession
            // runs in every teardown path; clearing here closes them all.
            try { Photon.Pun.PhotonNetwork.EnableCloseConnection = false; } catch { }
            IsLocalSpectator = false;
            LeaveRequested = false;
            PendingRoom = "";
            PendingRegion = "";
            GrantId = "";
            LeaseToken = "";
            WatchingGameId = "";
            SessionStartedAt = 0f;
            WatchedRoster = new string[0];
            WatchedNames = new string[0];
            WatchedTitles = new string[0];
            WatchedRatings = new string[0];
            WatchedTitleColors = new string[0];
            _pendingPropClear = true;
            TickPendingClear();
            try { RoomActors.Reset(); } catch { }
            // Bug 204: the spectator quiesce skips GameStateWatcher's
            // Left-room branch — the ONLY other caller of FfaMode.OnRoomLeft()
            // — so FFA counters written during a spectate (game/cycle from the
            // formerly-ungated pick loop, score tables from the observer path)
            // survived into the next room this client joined AS A FIGHTER.
            // Spirit spectated game A, joined the next room one game AHEAD,
            // and the ahead-only drift adoption made him permanently invisible
            // to the pick manifest ("no cards" for a player holding Defender).
            // The prefix gates remove the counter WRITER; this removes the
            // leak path itself, whichever teardown route ends the session.
            // Mostly local statics, plus one Photon call: OnRoomLeft clears
            // the cr_ffa_pk player prop via SetCustomProperties — in-room
            // that is a legitimate clear, out-of-room a local merge (#287).
            // A fighter session can never reach here: wasSpectating requires
            // IsLocalSpectator.
            if (wasSpectating)
                try { FfaMode.OnRoomLeft(); } catch { }
        }

        /// <summary>Retry the staged-role clear until the client is out of the
        /// room. Called from EndSession and every GameStateWatcher.Poll tick
        /// (cheap flag check). Also the leave-flow backstop: if a requested
        /// leave never observes its room exit (NetworkRestart raced, callback
        /// lost), a session stuck LeaveRequested outside a room is ended
        /// here rather than never.</summary>
        internal static void TickPendingClear()
        {
            try
            {
                if (IsLocalSpectator && LeaveRequested
                    && (!PhotonNetwork.InRoom || PhotonNetwork.OfflineMode))
                {
                    // The room exit happened but nothing observed it. Run the
                    // sync teardown too (Aug 10 r2 hardening): the normal
                    // OnLeftRoom path pairs these, and the backstop must not
                    // leave sync statics (quarantine tags, latches, pending
                    // boundary) behind. Both are idempotent.
                    EndSession("leave completed (tick backstop)");
                    try { SpectatorSync.OnLeftSpectatorRoom(); } catch { }
                    return;
                }
                if (!_pendingPropClear) return;
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return;   // still leaving
                // Only a SUCCESSFUL clear retires the flag (Codex r2 find 2:
                // an unconditional reset let a swallowed failure strand
                // cr_spec on the local player forever).
                if (ClearStagedProperties()) _pendingPropClear = false;
            }
            catch { }
        }

        // ── pre-join property staging (#287) ─────────────────────────────

        /// <summary>Stage the spectator role onto the LOCAL player before
        /// joining. Two rules are load-bearing and non-obvious (#287):
        ///
        /// (1) REFUSE while InRoom. Setting the property from inside a room
        ///     is the racy path — it becomes an ordinary eventually-consistent
        ///     property update rather than part of the join payload.
        /// (2) Only stage while the client is Disconnected/PeerCreated.
        ///     `!InRoom` is ALSO true mid-join, and a merge landing after the
        ///     join operation's property snapshot but before room entry is
        ///     present LOCALLY and never delivered to peers — a silently
        ///     false-capable client, which is the worst possible state for a
        ///     role that gates gameplay suppression on every OTHER client.
        ///
        /// Outside a room, SetCustomProperties takes the local-merge branch
        /// (no network op) and LoadBalancingClient snapshots
        /// LocalPlayer.CustomProperties into the join operation, so every
        /// peer learns the role in the same payload that announces us.
        /// </summary>
        internal static bool StagePreJoinProperties(string localSteamId)
        {
            try
            {
                if (PhotonNetwork.InRoom)
                {
                    Plugin.Log?.LogWarning("[SPECTATE] refusing to stage role while in a room (#287)");
                    return false;
                }
                // Codex round 2 (finding 19): the comment above permits only
                // Disconnected/PeerCreated, and the code then also accepted
                // ConnectedToMasterServer — a state a client is STILL IN while
                // a JoinRoom operation is already queued. Staging there can
                // land after Photon has snapshotted the join properties,
                // producing the single worst outcome for this role: locally
                // present, never delivered to peers, so every other client
                // classifies the actor as a FIGHTER. Code now matches the
                // contract. Phase 2's joiner must stage BEFORE it calls
                // ConnectToRegion/JoinRoom, which is the correct order anyway.
                var state = PhotonNetwork.NetworkClientState;
                if (state != Photon.Realtime.ClientState.Disconnected
                    && state != Photon.Realtime.ClientState.PeerCreated)
                {
                    Plugin.Log?.LogWarning($"[SPECTATE] not staging role in state {state} (mid-join risk, #287)");
                    return false;
                }
                // Codex round 2 (finding 12): CLEAR the fighter-only properties
                // in the same merge. Photon player properties persist across
                // rooms (#182), so a client that just left a 2v2 still carries
                // p_id / t_id / cr_cards / cr_fps and the report-capability
                // markers. Staging the spectator role on top of those produces
                // an actor advertising BOTH roles — and several of the mod's
                // own lookups key off exactly those fighter keys. Nulling a key
                // is how Photon deletes it.
                //
                // The lease property carries the LEASE ID (an opaque handle),
                // NEVER the raw token: player properties are readable by every
                // actor in the room, and the token is the proof-of-grant the
                // server holds a hash of (Codex spectator r1 finds 3+4). The
                // id identifies; the strict session authenticates.
                //
                // Cosmetic keys are cleared too (r1 find 13): cr_face/color/
                // trail/effect persist across rooms and would ride our join
                // payload into the watched room, where fighter clients would
                // render them for an actor that has no body.
                var props = new Hashtable
                {
                    { RoomActors.SPEC_PROP, PROTOCOL },
                    { RoomActors.SPEC_LEASE_PROP, GrantId ?? "" },
                    { "p_id", null },
                    { "t_id", null },
                    { "cr_cards", null },
                    { "cr_fps", null },
                    { "cr_gstats", null },
                    { "cr_face", null },
                    { "cr_pcolor_sku", null },
                    { "cr_pcolor_color", null },
                    { "cr_trail_sku", null },
                    { "cr_trail_color", null },
                    { "cr_trail_price", null },
                    { "cr_effect_sku", null },
                    { "cr_nametag_glow", null },
                    { "cr_nametag_typeface", null },
                };
                if (!string.IsNullOrEmpty(localSteamId)) props["u_id"] = localSteamId;
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                Plugin.Log?.LogInfo($"[SPECTATE] staged role pre-join (protocol {PROTOCOL}, state {state})");
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[SPECTATE] staging failed: {ex.Message}");
                return false;
            }
        }

        /// <summary>Drop the role + fighter-only leftovers. The role property
        /// must NEVER be cleared while still in the room — that would try to
        /// convert a live spectator actor into a fighter, which the
        /// immutable-classification rule forbids (design §3.2). This is
        /// therefore only called on session end, outside the room.</summary>
        private static bool ClearStagedProperties()
        {
            try
            {
                if (PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode) return false;   // never mid-room
                if (PhotonNetwork.LocalPlayer == null) return false;
                var props = new Hashtable
                {
                    { RoomActors.SPEC_PROP, null },
                    { RoomActors.SPEC_LEASE_PROP, null },
                };
                PhotonNetwork.LocalPlayer.SetCustomProperties(props);
                // Outside a room this is a pure local merge; verify the keys
                // are actually gone before declaring victory (r2 find 2).
                var now = PhotonNetwork.LocalPlayer.CustomProperties;
                return now == null
                       || (!now.ContainsKey(RoomActors.SPEC_PROP)
                           && !now.ContainsKey(RoomActors.SPEC_LEASE_PROP));
            }
            catch { return false; }
        }
    }
}
