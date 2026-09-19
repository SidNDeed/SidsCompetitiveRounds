using System;
using BepInEx.Configuration;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Opt-in automatic post-match log upload: when the player has turned the
    /// Settings toggle on, the same log bundle the bug form builds is sent once
    /// per qualifying room exit, so a report of "it broke last night" has a log
    /// behind it without asking anyone to remember to file one.
    ///
    /// DEFAULT OFF and a NEW config key. Config.Bind writes a default exactly
    /// once and never revisits it (#190), so this ships off for every install
    /// that has ever run the mod as well as for a fresh one; repurposing an
    /// existing key would have migrated nobody.
    ///
    /// The upload is gated on "a game actually ran in this room", which is
    /// observed directly (GameManager.battleOngoing was true at least once
    /// here) rather than inferred from the room's NAME — a room-name predicate
    /// excludes every privately hosted room-code game (#286), and the mod
    /// version field cannot tell a dev build from a release (#301). The mode
    /// string below DOES read the room prefix, and that is fine precisely
    /// because it is a triage LABEL on a row nobody branches on, not a gate.
    ///
    /// Failure directions, all chosen to expire rather than to block:
    ///  * the route is absent (404) — the DLL may ship before the server half,
    ///    so a missing route means "off at this backend": latch it, say so
    ///    once, and stop for the session;
    ///  * the server refuses (429 at its own 12-per-24h bucket, or any other
    ///    4xx) — terminal, never retried. ApiClient.SubmitAutoLog makes exactly
    ///    one attempt, so this is a property of the code and not a promise;
    ///  * the transport fails with no response — also terminal for this exit.
    ///    The next qualifying exit tries again; nothing queues, nothing
    ///    accumulates, and an offline sitting costs one request per match.
    /// </summary>
    internal static class AutoLogUpload
    {
        /// <summary>Minimum gap between two uploads from this process. The
        /// server has its own 12-per-24h bucket; this exists so a player who
        /// leaves and rejoins repeatedly spends neither their bucket nor their
        /// upstream on near-identical bundles.</summary>
        private const float MIN_UPLOAD_GAP_SECONDS = 300f;

        // Snapshot of the room we are in, refreshed by Tick. OnLeftRoom runs
        // after PhotonNetwork has already let go of the room, so every field
        // the body needs has to be captured while the room still exists.
        private static string _roomName = "";
        private static string _mode = "";
        private static string _opponentSteamId = "";
        private static string _seriesId = "";
        private static bool _gameRan;
        private static string _tickRoom = "";

        private static float _lastUploadAt = -99999f;
        private static int _lastUploadedHash;
        private static bool _endpointAbsent;
        private static bool _inFlight;
        private static float _skipLoggedAt = -99999f;

        private static bool _startupDone;
        private static ConfigEntry<bool> _selfTestLever;

        internal static bool Enabled
        {
            get
            {
                try { return Plugin.AutoLogUploadEnabled != null && Plugin.AutoLogUploadEnabled.Value; }
                catch { return false; }
            }
        }

        /// <summary>Per-frame upkeep from the always-on persistent tick, so no
        /// join path can forget it. Cheap: four reads and a boolean OR while in
        /// a room, one comparison while at the menu.</summary>
        internal static void Tick()
        {
            EnsureStartup();
            try
            {
                if (!PhotonNetwork.InRoom)
                {
                    _tickRoom = "";
                    return;
                }

                string room = "";
                try { room = PhotonNetwork.CurrentRoom != null ? (PhotonNetwork.CurrentRoom.Name ?? "") : ""; }
                catch { }

                if (room != _tickRoom)
                {
                    // A new room (including a leave+rejoin that landed between
                    // two samples, which is why the comparison is on the NAME
                    // and not on a boolean): everything below describes the
                    // room we are in now, so start it over.
                    _tickRoom = room;
                    _roomName = room;
                    _mode = ModeLabel(room);
                    _opponentSteamId = "";
                    _seriesId = "";
                    _gameRan = false;
                }

                if (!_gameRan)
                {
                    try { _gameRan = GameManager.instance != null && GameManager.instance.battleOngoing; }
                    catch { }
                }

                // Both of these are only readable while the room is live, and
                // both can arrive late in the match, so keep the freshest
                // non-empty value rather than the first one seen.
                try
                {
                    string opp = GameStateWatcher.OpponentSteamId;
                    if (!string.IsNullOrEmpty(opp) && opp != "unknown") _opponentSteamId = opp;
                }
                catch { }
                try
                {
                    string sid = ApiClient.SeriesIdForThisRoom();
                    if (!string.IsNullOrEmpty(sid)) _seriesId = sid;
                }
                catch { }
            }
            catch { }
        }

        /// <summary>Triage label only. Reads the room prefix, which would be
        /// the wrong basis for a GATE (#286) and is the right basis for a
        /// human-readable field: nothing branches on it, on either side.</summary>
        private static string ModeLabel(string room)
        {
            try
            {
                if (PhotonNetwork.OfflineMode) return "offline";
                if (string.IsNullOrEmpty(room)) return "unknown";
                if (room.StartsWith("ranked_", StringComparison.Ordinal)) return "1v1";
                if (room.StartsWith("team_", StringComparison.Ordinal)) return "2v2";
                if (room.StartsWith("ovt_", StringComparison.Ordinal)) return "1v2";
                if (room.StartsWith("ffa_", StringComparison.Ordinal)) return "ffa";
                if (room.StartsWith("sct-", StringComparison.Ordinal)) return "tournament";
                return "private";
            }
            catch { return "unknown"; }
        }

        /// <summary>Called from the RELIABLE room-exit callback. The room-state
        /// poll is not used: it turns false during Leaving and can miss a
        /// leave+rejoin entirely (#430b).</summary>
        internal static void OnRoomLeft()
        {
            bool gameRan = _gameRan;
            string mode = _mode, room = _roomName, opp = _opponentSteamId, series = _seriesId;
            // Room-bound state dies with the room whatever happens below, and
            // it dies FIRST, so no early return can carry it into the next one.
            _gameRan = false;
            _tickRoom = "";
            _roomName = ""; _mode = ""; _opponentSteamId = ""; _seriesId = "";

            try
            {
                if (_endpointAbsent) return;     // already said so, once, this session
                if (_inFlight) return;

                if (!Enabled) { NoteSkip("the setting is off"); return; }
                if (!Plugin.DataConsentGranted) { NoteSkip("data reporting is not consented"); return; }
                if (!gameRan) { NoteSkip("no game ran in that room"); return; }
                if (string.IsNullOrEmpty(SteamAuth.SessionToken)) { NoteSkip("no Steam session on this client"); return; }
                if (Time.realtimeSinceStartup - _lastUploadAt < MIN_UPLOAD_GAP_SECONDS)
                {
                    NoteSkip("within " + (int)MIN_UPLOAD_GAP_SECONDS + "s of the previous upload");
                    return;
                }

                string steamId = MatchTracker.LocalSteamId;
                string name = MatchTracker.LocalDisplayName ?? "";
                if (string.IsNullOrEmpty(steamId) || steamId == "unknown") { NoteSkip("no local Steam id"); return; }

                // BuildLogBundle SCRUBS; this is the only producer, and it is
                // the same text the bug form sends.
                string bundle = CompetitiveUI.BuildLogBundle();
                int scrubbed = CompetitiveUI.LastScrubReplacements;
                if (string.IsNullOrEmpty(bundle) || scrubbed < 0)
                {
                    Plugin.Log.LogWarning("[AUTO-LOG] not uploading: the log scrub did not complete");
                    return;
                }

                int hash = StableHash(bundle);
                if (hash == _lastUploadedHash)
                {
                    NoteSkip("the log is byte-identical to the one already uploaded");
                    return;
                }

                int chars = bundle.Length;
                _inFlight = true;
                ApiClient.SubmitAutoLog(steamId, name, mode, room, opp, series, bundle,
                    (ok, code, resp) =>
                    {
                        _inFlight = false;
                        // Every arm consumes the debounce, including refusals:
                        // a refused upload still cost a request, and re-asking
                        // thirty seconds later is how a bucket gets spent on
                        // nothing.
                        _lastUploadAt = Time.realtimeSinceStartup;
                        if (ok)
                        {
                            _lastUploadedHash = hash;
                            int stored = ApiClient.ExtractJsonIntPublic(resp ?? "", "log_bytes");
                            int number = ApiClient.ExtractJsonIntPublic(resp ?? "", "bug_number");
                            Plugin.Log.LogInfo($"[AUTO-LOG] uploaded: {stored:N0} bytes stored from {chars:N0} scrubbed chars, "
                                + $"scrub removed {scrubbed} local-identity string(s), mode={mode}, filed #{number}");
                            return;
                        }
                        if (code == 404)
                        {
                            // The route is not on this backend. That is an
                            // answer, not an error: the client can ship either
                            // side of the server half.
                            _endpointAbsent = true;
                            Plugin.Log.LogInfo("[AUTO-LOG] this server has no automatic-log route (404) — "
                                + "automatic uploads are off for this session");
                            return;
                        }
                        if (code == 429 || code == 409 || code == 413)
                        {
                            Plugin.Log.LogInfo($"[AUTO-LOG] server refused this upload (HTTP {code}) — "
                                + "terminal, not retried");
                            return;
                        }
                        Plugin.Log.LogWarning($"[AUTO-LOG] upload failed ({(code > 0 ? "HTTP " + code : "no response")}) — "
                            + "not retried; the next match tries again");
                    });
            }
            catch (Exception ex)
            {
                _inFlight = false;
                Plugin.Log.LogWarning("[AUTO-LOG] room-exit handling failed: " + ex.Message);
            }
        }

        /// <summary>The negative half of the acceptance signal. Every reason
        /// the upload did NOT happen says so out loud — "no [AUTO-LOG] line"
        /// would otherwise be indistinguishable from "the hook never ran"
        /// (#438). Throttled so a sitting of quick exits cannot flood the
        /// log.</summary>
        private static void NoteSkip(string why)
        {
            try
            {
                if (Time.realtimeSinceStartup - _skipLoggedAt < 30f) return;
                _skipLoggedAt = Time.realtimeSinceStartup;
                Plugin.Log.LogInfo("[AUTO-LOG] no upload for that room: " + why);
            }
            catch { }
        }

        /// <summary>FNV-1a over the bundle. Not a security hash — its only job
        /// is to tell "the same text again" from "new text", and a collision
        /// costs one skipped upload.</summary>
        private static int StableHash(string s)
        {
            unchecked
            {
                uint h = 2166136261;
                for (int i = 0; i < s.Length; i++)
                {
                    h ^= s[i];
                    h *= 16777619;
                }
                return (int)h;
            }
        }

        /// <summary>Once per process, from the first Tick: binds
        /// [Debug] AutoLogScrubSelfTest (the H2HRulesSelfTest lever's shape)
        /// and runs the scrub's own cases when it is true. The run logs and
        /// does nothing else — nothing is sent, shown or persisted.</summary>
        private static void EnsureStartup()
        {
            if (_startupDone) return;
            _startupDone = true;
            try
            {
                ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf != null)
                    _selfTestLever = cf.Bind(
                        "Debug", "AutoLogScrubSelfTest",
                        false,
                        "Development only: once at startup, run the log scrub over canned inputs (local paths in four separator spellings, a second account's path, a bare account name, and two inputs that must come back untouched) and log one [LOG-SCRUB] line per case plus a summary. Nothing is sent, shown or persisted.");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[LOG-SCRUB] self-test bind failed: " + ex.Message); }

            bool run = false;
            try { run = _selfTestLever != null && _selfTestLever.Value; } catch { }
            if (!run) return;
            try
            {
                var r = LogScrub.SelfTest();
                foreach (string line in r.Report.ToString().Split('\n'))
                    if (line.Length > 0) Plugin.Log?.LogInfo("[LOG-SCRUB] selftest " + line);
                Plugin.Log?.LogInfo($"[LOG-SCRUB] selftest summary: {r.Passed} passed, {r.Failed} failed");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[LOG-SCRUB] self-test failed to run: " + ex.GetType().Name); }
        }
    }
}
