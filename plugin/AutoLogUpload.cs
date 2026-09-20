using System;
using System.Text;
using System.Threading;
using BepInEx.Configuration;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Opt-in automatic post-match log upload: when the player has turned the
    /// Settings toggle on, the same log bundle the bug form builds is sent
    /// after a qualifying room exit, so a report of "it broke last night" has a
    /// log behind it without asking anyone to remember to file one.
    ///
    /// AT MOST ONE REQUEST PER QUALIFYING EXIT, and usually none. "Once per
    /// qualifying room exit" read as a floor as well as a ceiling, and it is
    /// only the ceiling (Codex client r2). An exit sends nothing when the
    /// toggle is off, when data reporting is not consented, when no game ran,
    /// when there is no Steam session, inside the 300 s debounce, while a
    /// previous bundle is still being built or a previous upload is still in
    /// flight, when the finished bundle is byte-identical to the one already
    /// accepted, or once a 404 has latched uploads off for the session. Every
    /// one of those prints its own reason through NoteSkip, because "no
    /// [AUTO-LOG] line" must never be the same observation as "the hook never
    /// ran" (#438).
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
    ///
    /// NOTHING PROPORTIONAL TO THE LOG RUNS ON THE GAME THREAD (Codex r1 HIGH,
    /// this file's old line 184). The room-exit handler used to call
    /// CompetitiveUI.BuildLogBundle() inline, which read three log files whole,
    /// ran five string passes over the result and JSON-escaped it — a visible
    /// freeze at every qualifying exit, and seconds long for a player whose
    /// LogOutput.log has grown to tens of megabytes. The work is now split:
    ///
    ///   MAIN THREAD, at room exit: the gates below (a dozen field reads),
    ///   CompetitiveUI.CaptureLogBundleInputs() (three path computations and
    ///   one audio snapshot) and starting a thread. All O(1).
    ///
    ///   WORKER THREAD: the bounded tail reads, the assembly, the scrub, the
    ///   JSON body and the UTF-8 encoding. ApiClient.ReadLogTail now SEEKS to
    ///   the last N bytes, so the disk input is bounded before the read as well
    ///   as after it — a 40 MB log costs 3.5 MB of reading, not 40.
    ///
    ///   MAIN THREAD, on the next Tick after the worker finishes: the dedup
    ///   compare and handing the finished byte[] to the upload handler. The
    ///   largest single act is that hand-off.
    ///
    /// The worker is a background thread, so it cannot hold the process open,
    /// and it touches no engine API — everything it reads is either a parameter
    /// or a local. One at a time: _bundling is the gate, and a second exit
    /// while a bundle is being built simply says so and skips.
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

        // ── worker hand-off ──────────────────────────────────────────────
        // _bundling is written on the main thread only (set before the worker
        // starts, cleared on the main thread when the result is consumed or
        // the start fails), so it is a plain bool. Everything the worker
        // PRODUCES is published under _gate and read under _gate, which is
        // both the mutual exclusion and the memory barrier — a volatile bool
        // plus unsynchronised fields would publish the flag before the
        // payload on a weak model.
        private static readonly object _gate = new object();
        private static bool _bundling;
        private static BundleResult _ready;

        /// <summary>What the worker hands back. Immutable once published.</summary>
        private sealed class BundleResult
        {
            internal byte[] Body;          // the finished, UTF-8 encoded POST body
            internal int Hash;             // FNV-1a over the bundle TEXT (dedup key)
            internal int Chars;            // bundle length, for the acceptance line
            internal int Scrubbed;         // replacements, or -1 when the scrub failed
            internal string Mode;          // carried so the acceptance line stays truthful
            internal string Diagnostic;    // ComposeLogBundle's line, logged on the main thread
            internal string Failure;       // non-null = do not send; this is why
        }

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
            // The worker's hand-off point. FIRST, and outside the in-room
            // early return: a bundle is built BECAUSE we left a room, so the
            // frame it finishes on is almost never a frame we are in one.
            PumpFinishedBundle();
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
                if (_bundling) { NoteSkip("the previous room's bundle is still being built"); return; }

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

                // EVERY Unity/Photon read the bundle needs, taken HERE, while
                // we are still on the game thread. Past this point the worker
                // sees nothing but the values it was handed.
                var inputs = CompetitiveUI.CaptureLogBundleInputs();
                string modVersion = Plugin.ModVersion;
                string gameVersion = ApiClient.SafeApplicationVersion();

                _bundling = true;
                StartBundleWorker(inputs, steamId, name, modVersion, gameVersion, mode, room, opp, series);
            }
            catch (Exception ex)
            {
                _bundling = false;
                _inFlight = false;
                Plugin.Log.LogWarning("[AUTO-LOG] room-exit handling failed: " + ex.Message);
            }
        }

        /// <summary>The worker. Reads, assembles, scrubs, escapes and encodes —
        /// all of it off the game thread — then publishes one BundleResult.
        ///
        /// It logs NOTHING: BepInEx's log sinks are not documented thread-safe
        /// and a diagnostic written from here would interleave with the game's
        /// own lines. Every sentence it wants to say travels back in the result
        /// and is written on the main thread by PumpFinishedBundle.</summary>
        private static void StartBundleWorker(CompetitiveUI.LogBundleInputs inputs,
                                              string steamId, string name,
                                              string modVersion, string gameVersion,
                                              string mode, string room, string opp, string series)
        {
            var t = new Thread(() =>
            {
                var result = new BundleResult { Mode = mode };
                try
                {
                    int scrubbed; string diagnostic;
                    string bundle = CompetitiveUI.ComposeLogBundle(inputs, out scrubbed, out diagnostic);
                    result.Diagnostic = diagnostic;
                    result.Scrubbed = scrubbed;
                    if (string.IsNullOrEmpty(bundle) || scrubbed < 0)
                    {
                        result.Failure = "the log scrub did not complete";
                    }
                    else
                    {
                        result.Chars = bundle.Length;
                        result.Hash = StableHash(bundle);
                        string body = ApiClient.BuildAutoLogBody(steamId, name, modVersion, gameVersion,
                                                                 mode, room, opp, series, bundle);
                        result.Body = Encoding.UTF8.GetBytes(body);
                    }
                }
                catch (Exception ex)
                {
                    // The type name only: an exception MESSAGE from a file read
                    // can carry the path that produced it, and this one has not
                    // been through the scrub.
                    result.Failure = "the bundle could not be built (" + ex.GetType().Name + ")";
                }
                lock (_gate) { _ready = result; }
            });
            t.IsBackground = true;          // must never hold the process open
            t.Name = "SCR-AutoLogBundle";
            try { t.Start(); }
            catch (Exception ex)
            {
                _bundling = false;
                Plugin.Log.LogWarning("[AUTO-LOG] could not start the bundle thread: " + ex.Message);
            }
        }

        /// <summary>MAIN THREAD, from Tick. Consumes at most one finished
        /// bundle per frame and does the only two things that could not be
        /// done on the worker: the dedup compare against the last upload, and
        /// starting the request.</summary>
        private static void PumpFinishedBundle()
        {
            BundleResult r;
            lock (_gate)
            {
                r = _ready;
                _ready = null;
            }
            if (r == null) return;
            _bundling = false;

            try
            {
                if (!string.IsNullOrEmpty(r.Diagnostic))
                {
                    if (r.Scrubbed < 0) Plugin.Log.LogError(r.Diagnostic);
                    else Plugin.Log.LogInfo(r.Diagnostic);
                }
                if (r.Failure != null || r.Body == null)
                {
                    Plugin.Log.LogWarning("[AUTO-LOG] not uploading: " + (r.Failure ?? "no body was produced"));
                    return;
                }
                // The setting can be turned off, or the session lost, while the
                // bundle was being built. Re-check rather than inherit the
                // answer from the frame the room closed on.
                if (!Enabled) { NoteSkip("the setting was turned off while the bundle was being built"); return; }
                if (!Plugin.DataConsentGranted) { NoteSkip("data reporting is not consented"); return; }
                if (_endpointAbsent || _inFlight) return;
                if (r.Hash == _lastUploadedHash)
                {
                    NoteSkip("the log is byte-identical to the one already uploaded");
                    return;
                }

                int chars = r.Chars, scrubbed = r.Scrubbed, hash = r.Hash;
                string mode = r.Mode;
                _inFlight = true;
                ApiClient.SubmitAutoLogBody(r.Body,
                    (ok, code, resp) =>
                    {
                        _inFlight = false;
                        if (!ok && resp == ApiClient.RequestCancelledMarker)
                        {
                            // The player turned the setting off while this was
                            // on the wire, and the transfer was ABORTED rather
                            // than completed-and-discarded. That is what makes
                            // the consent's "nothing is sent while this is off"
                            // true of a dispatched request and not only of a
                            // future one (Codex client r2 MEDIUM).
                            //
                            // Neither the debounce nor the dedup hash is
                            // written: nothing was accepted, so a later
                            // re-enable must not be made to wait five minutes
                            // for an upload that never happened, and the
                            // unsent bundle must not be remembered as sent.
                            Plugin.Log.LogInfo("[AUTO-LOG] upload cancelled — the setting was turned off mid-transfer");
                            return;
                        }
                        // Every other arm consumes the debounce, including
                        // refusals: a refused upload still cost a request, and
                        // re-asking thirty seconds later is how a bucket gets
                        // spent on nothing.
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
                    },
                    // Polled once a frame for as long as the request is open.
                    // This is the whole of "never while this is off": the
                    // gates above stop a NEW dispatch, and this one stops a
                    // dispatched transfer the moment permission is withdrawn.
                    abortIf: () => !Enabled);
            }
            catch (Exception ex)
            {
                _inFlight = false;
                Plugin.Log.LogWarning("[AUTO-LOG] handing the finished bundle over failed: " + ex.Message);
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
