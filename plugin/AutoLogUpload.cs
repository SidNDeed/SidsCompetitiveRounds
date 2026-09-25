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

        // ── The two switches, and the transport (v1.41.0 beta round 2, finding 4) ──
        //
        // An automatic upload needs BOTH of the player's permissions: this
        // feature's own setting (Enabled) and the global data consent
        // (Plugin.DataConsentGranted). Every question this file asks about them
        // goes through the two delegates below: the room-exit gates, the gates
        // at dispatch, and the dispatched request's abortIf, which asks the
        // same two questions once a frame for as long as the request is open.
        // So withdrawing EITHER one mid-transfer aborts the transfer. It used
        // to be the setting alone: consent revoked while the setting stayed on
        // let an upload already on the wire finish.
        //
        // They are delegates, and so is the send, for the consent sentinel
        // (RunConsentSentinel, at the end of this class). It has to revoke
        // consent in the middle of a transfer, and the player's real consent
        // is not something a self-test may write: it is saved to the cfg, and
        // ApiClient.OnConsentChanged answers a revoke by turning ranked off and
        // dropping the local caches. So for the length of one synchronous call
        // the sentinel points these three at its own switches and its own stub
        // transport, and it restores all three in a finally. Nothing else
        // assigns them.
        private static Func<bool> _enabledNow = () => Enabled;
        private static Func<bool> _consentNow = () => Plugin.DataConsentGranted;

        private delegate void AutoLogSender(byte[] body, Action<bool, long, string> done, Func<bool> abortIf);
        private static AutoLogSender _send =
            (body, done, abortIf) => ApiClient.SubmitAutoLogBody(body, done, abortIf: abortIf);

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

                if (!_enabledNow()) { NoteSkip("the setting is off"); return; }
                if (!_consentNow()) { NoteSkip("data reporting is not consented"); return; }
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
        /// bundle per frame and hands it to Dispatch.</summary>
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
            Dispatch(r);
        }

        /// <summary>MAIN THREAD. Does the only two things that could not be
        /// done on the worker: the dedup compare against the last upload, and
        /// starting the request. Its own member so the consent sentinel runs
        /// THIS code on a synthetic bundle, never a copy of it.</summary>
        private static void Dispatch(BundleResult r)
        {
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
                // The setting can be turned off, consent revoked or the session
                // lost while the bundle was being built. Re-check rather than
                // inherit the answer from the frame the room closed on.
                if (!_enabledNow()) { NoteSkip("the setting was turned off while the bundle was being built"); return; }
                if (!_consentNow()) { NoteSkip("data reporting is not consented"); return; }
                if (_endpointAbsent || _inFlight) return;
                if (r.Hash == _lastUploadedHash)
                {
                    NoteSkip("the log is byte-identical to the one already uploaded");
                    return;
                }

                int chars = r.Chars, scrubbed = r.Scrubbed, hash = r.Hash;
                string mode = r.Mode;
                _inFlight = true;
                _send(r.Body,
                    (ok, code, resp) =>
                    {
                        _inFlight = false;
                        if (!ok && resp == ApiClient.RequestCancelledMarker)
                        {
                            // The player withdrew permission while this was on
                            // the wire (turned the setting off, or revoked data
                            // consent: round 2 finding 4), and the transfer was
                            // ABORTED rather than completed-and-discarded. That
                            // is what makes the consent's "nothing is sent while
                            // this is off" true of a dispatched request and not
                            // only of a future one (Codex client r2 MEDIUM).
                            //
                            // Neither the debounce nor the dedup hash is
                            // written: nothing was accepted, so a later
                            // re-enable must not be made to wait five minutes
                            // for an upload that never happened, and the
                            // unsent bundle must not be remembered as sent.
                            Plugin.Log.LogInfo("[AUTO-LOG] upload cancelled — "
                                + (_enabledNow() ? "data consent was revoked" : "the setting was turned off")
                                + " mid-transfer");
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
                    // It asks the gates' own two questions through the same
                    // two delegates: the setting alone let a transfer outlive
                    // a revoked data consent (round 2 finding 4).
                    abortIf: () => !_enabledNow() || !_consentNow());
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

        // ── Consent sentinel (v1.41.0 beta round 2, finding 4) ─────────────────
        //
        // Runs Dispatch, the code a finished bundle takes, on synthetic bundles
        // against a stub transport that polls the real abortIf once a "frame",
        // as PostRequestRaw does. Two transfers: on one the player revokes data
        // consent at frame 3 with the setting left on (the report's case); on
        // the other the setting goes off at frame 3 with consent left granted.
        // Each must run unaborted while both switches are on, abort on the
        // frame the switch goes, and then take the RequestCancelledMarker
        // branch: the in-flight flag clears and neither the debounce nor the
        // dedup hash is written. A third bundle, handed over with consent
        // already revoked, must not reach the transport at all: the gates and
        // the in-flight check ask the same two questions.
        //
        // Nothing is sent: the stub is the only transport the sentinel's
        // dispatches can reach, installed first and removed last. Nothing is
        // persisted: every static Dispatch can write is saved first and
        // restored in the finally, and the player's real setting and consent
        // are read, never written. What does reach the log is the cancellation
        // branch's own "[AUTO-LOG] upload cancelled" line, once per transfer:
        // it is that branch running, and the verdict line follows it.

        internal const string ConsentSentinelTag = "[AUTO-LOG-CONSENT-SENTINEL]";

        /// <summary>A debounce value no answer arm can write: every arm but the
        /// cancellation writes Time.realtimeSinceStartup, which is never
        /// negative. Unchanged after the answer means the cancellation branch
        /// ran, not merely that an answer arrived.</summary>
        private const float SentinelDebounceProbe = -12345f;

        /// <summary>The dedup hash the sentinel plants. Its bundles hash one
        /// higher, so the dedup gate lets them through and the success arm
        /// would overwrite this with theirs.</summary>
        private const int SentinelHashProbe = 0x5E471;

        /// <summary>Returns the verdict line; `pass` is the verdict. MAIN
        /// THREAD, one synchronous call: no frame passes while the sentinel's
        /// switches and transport are installed, so a real upload's abortIf is
        /// never polled against them.</summary>
        internal static string RunConsentSentinel(out bool pass)
        {
            pass = true;
            int checks = 0;
            string detail = "";

            AutoLogSender realSend = _send;
            Func<bool> realEnabled = _enabledNow, realConsent = _consentNow;
            bool savedInFlight = _inFlight, savedAbsent = _endpointAbsent;
            float savedAt = _lastUploadAt, savedSkipAt = _skipLoggedAt;
            int savedHash = _lastUploadedHash;
            try
            {
                // The installed delegates answer what the switches say right
                // now, whichever state the player has them in. Read-only.
                checks++;
                if (realEnabled() != Enabled || realConsent() != Plugin.DataConsentGranted)
                { pass = false; detail += " live-switches:disagree"; }

                int sends = 0;
                Func<bool> abortIf = null;
                Action<bool, long, string> answer = null;
                _send = (body, done, predicate) => { sends++; answer = done; abortIf = predicate; };

                bool setting = true, consent = true;
                _enabledNow = () => setting;
                _consentNow = () => consent;

                foreach (string withdrawn in new[] { "consent", "setting" })
                {
                    setting = true; consent = true;
                    sends = 0; abortIf = null; answer = null;
                    _inFlight = false;
                    _endpointAbsent = false;
                    _lastUploadAt = SentinelDebounceProbe;
                    _lastUploadedHash = SentinelHashProbe;

                    Dispatch(SentinelBundle());
                    checks++;
                    if (sends != 1 || abortIf == null || answer == null || !_inFlight)
                    { pass = false; detail += " " + withdrawn + ":not-dispatched"; continue; }

                    int abortedAt = -1;
                    for (int frame = 0; frame < 6 && abortedAt < 0; frame++)
                    {
                        if (frame == 3)
                        {
                            if (withdrawn == "consent") consent = false;
                            else setting = false;
                        }
                        bool stop = false;
                        try { stop = abortIf(); } catch { }
                        if (stop) abortedAt = frame;
                    }
                    checks++;
                    if (abortedAt != 3)
                    { pass = false; detail += " " + withdrawn + ":aborted-at-" + abortedAt; continue; }

                    // What SubmitAutoLogBody hands back for an aborted request:
                    // no response (status 0) and the marker.
                    answer(false, 0, ApiClient.RequestCancelledMarker);
                    checks++;
                    if (_inFlight) { pass = false; detail += " " + withdrawn + ":still-in-flight"; }
                    checks++;
                    if (_lastUploadAt != SentinelDebounceProbe) { pass = false; detail += " " + withdrawn + ":debounce-written"; }
                    checks++;
                    if (_lastUploadedHash != SentinelHashProbe) { pass = false; detail += " " + withdrawn + ":hash-written"; }
                }

                // A bundle handed over after consent was revoked never reaches
                // the transport. NoteSkip's line for it is muted by priming its
                // 30 s throttle; the finally puts the throttle back.
                setting = true; consent = false;
                sends = 0;
                _inFlight = false;
                _skipLoggedAt = Time.realtimeSinceStartup;
                Dispatch(SentinelBundle());
                checks++;
                if (sends != 0 || _inFlight) { pass = false; detail += " gate:dispatched-without-consent"; }
            }
            catch (Exception ex)
            {
                pass = false;
                detail += " threw:" + ex.GetType().Name;
            }
            finally
            {
                _enabledNow = realEnabled;
                _consentNow = realConsent;
                _inFlight = savedInFlight;
                _endpointAbsent = savedAbsent;
                _lastUploadAt = savedAt;
                _skipLoggedAt = savedSkipAt;
                _lastUploadedHash = savedHash;
                _send = realSend;
            }
            return ConsentSentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + detail;
        }

        private static BundleResult SentinelBundle()
        {
            return new BundleResult
            {
                Body = new byte[] { (byte)'{', (byte)'}' },
                Hash = SentinelHashProbe + 1,
                Chars = 2,
                Scrubbed = 0,
                Mode = "sentinel",
            };
        }

        /// <summary>[Broadcast] TestAutoLogConsentSentinel's entry: runs the
        /// sentinel once and logs its line.</summary>
        internal static void DevConsentSentinelTest()
        {
            try
            {
                bool pass;
                string line = RunConsentSentinel(out pass);
                if (pass) Plugin.Log.LogInfo(line); else Plugin.Log.LogWarning(line);
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(ConsentSentinelTag + " FAIL: threw " + ex.Message);
            }
        }
    }
}
