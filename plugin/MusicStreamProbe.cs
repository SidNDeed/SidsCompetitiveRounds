using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Threading;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.Profiling;

namespace CompetitiveRounds
{
    /// <summary>Music v7 measurement spike, v2 (music-v7-design.md §2). Measures
    /// STREAMED decode (DownloadHandlerAudioClip.streamAudio = true) on a seat.
    ///
    /// Keys, both in [Music]: `StreamProbe` (bool, default false) enables it,
    /// `StreamProbeRun` = "&lt;albumSku&gt;:&lt;trackIdx&gt;[:stress|:churn]" says
    /// what to measure. Set both and restart, and the command RUNS — it is not
    /// adopted as an inert baseline, which is what made the whole probe
    /// unreachable on a player seat (review r9). While enabled the probe
    /// re-reads the config file itself every 2 s, so a new command starts a new
    /// run and turning the key off ends a live one. A command that is refused
    /// is not retried until it changes or the key is toggled.
    ///
    /// Per run it logs [MUSIC-PROBE] records: seat context and any music owner
    /// already sounding (custom music REFUSES the run; vanilla is reported),
    /// cold/warm open cost (request, GetContent, the whole completion block,
    /// Play → first non-zero buffer, and the largest frame from request start
    /// through two frames after completion), wrap-aware playback drift against
    /// the DSP clock (accumulated drift is the underrun measure; a stall is a
    /// ≥ 60 ms jump — three DSP buffers, the 21 ms quantum is noise, learning
    /// #475), consecutive all-zero output buffers from an OnAudioFilterRead tap
    /// (isPlaying is a flag, not output), the longest gap BETWEEN callbacks and
    /// the audio actually delivered against the wall time it was expected in —
    /// a callback the audio thread never reaches supplies no zero buffer at
    /// all, so counting arrivals alone reads a starved run as clean (review
    /// r9) — managed/native/process memory before the request, after open,
    /// during play and after cleanup, and a scripted control sequence (seek
    /// running, pause + seek paused + resume, loop off → natural end, loop
    /// wrap) each judged pass/fail. ":stress" = 600 s plus up to 7 busy threads
    /// (ProcessorCount - 1, capped) for 60 s; ":churn" = ten open/close cycles
    /// then the memory samples. The probe never touches MusicEngine state, and
    /// stops if the normal engine starts sounding at any point in a run.
    ///
    /// Lifetime: the host GameObject is HideAndDontSave; if anything destroys it
    /// (its tap's OnDestroy flags it, and a Unity fake-null source is checked
    /// too) every retained handle is released — never treated as idle.</summary>
    internal static class MusicStreamProbe
    {
        // ── gate ─────────────────────────────────────────────────────────
        /// <summary>Opt-in per seat through the [Music] StreamProbe config key —
        /// default false, so nothing here runs for anyone who has not asked for
        /// it.
        ///
        /// It was BROADCAST IDENTITY ONLY, which is why the question this probe
        /// exists to answer went unanswered: the one seat that could run it is
        /// the one seat whose numbers nobody disputes. The open disagreement is
        /// about PLAYER hardware — learning #460 records streamed playback
        /// skipping audibly on a CPU-contended seat, while the v2 spike measured
        /// 4.3 ms GetContent and no underrun at 50-140 fps on this one — and a
        /// gate no player seat can pass cannot settle it. Design review dV2
        /// refused a compiled account allowlist, correctly: a personal
        /// identifier must not ship in source or in the DLL. A config key is not
        /// one.
        ///
        /// Every other refusal the reviews put here STANDS: never inside an
        /// online room (a second music owner during someone's match), and
        /// ":stress" only inside an offline Sandbox round, re-checked every tick
        /// and cancelled on exit.</summary>
        private static bool SeatAllowed()
        {
            try { return Plugin.MusicProbeEnabled != null && Plugin.MusicProbeEnabled.Value; }
            catch { return false; }
        }

        private const float CONFIG_RELOAD_SECONDS = 2f;
        private static float _nextReloadAt;

        /// <summary>Re-read the config FILE. This is the probe's own reload,
        /// on its own throttle, with no seat condition and no dependency on
        /// another tick's ordering.
        ///
        /// Config.Bind reads the file once, at launch, and the only other
        /// reload in the mod belongs to the broadcast-seat levers. So on a
        /// player seat both keys were frozen at their launch values — and
        /// because a run also required the value to CHANGE after launch, the
        /// probe could never start on exactly the hardware it exists to
        /// measure (review r9). Two things fix that: this, and the launch
        /// command now being executed rather than adopted as a baseline.
        ///
        /// Called ONLY while the probe is enabled, so a seat that never turns
        /// it on never touches the disk. That is why enabling it takes a
        /// restart, which is what the key's own description says.</summary>
        private static void ReloadIfDue(float now)
        {
            if (now < _nextReloadAt) return;
            _nextReloadAt = now + CONFIG_RELOAD_SECONDS;
            try { Plugin.ConfigFileForLevers?.Reload(); } catch { }
        }

        /// <summary>POSITIVE evidence of a Sandbox round in progress. The
        /// Photon flags are not that evidence: `InRoom && OfflineMode` stays
        /// true at the post-Sandbox menu (review r9), and ":stress" starting
        /// seven busy workers there — with a queue poll or a room join a
        /// keystroke away — is exactly what the offline-Sandbox restriction
        /// exists to prevent. Asked at admission and on every tick.</summary>
        private static bool SandboxLive()
        {
            try
            {
                var gt = GM_Test.instance;
                if (gt == null || !gt.isActiveAndEnabled) return false;
                var gm = GameManager.instance;
                if (gm == null || !gm.isPlaying) return false;
                var mm = MainMenuHandler.instance;
                return mm == null || !mm.isOpen;
            }
            catch { return false; }
        }

        // ── run state ────────────────────────────────────────────────────
        private enum Mode { Normal, Stress, Churn }
        // _lastRun is the command this probe last STARTED, not the last
        // value it saw. The difference is the r9 HIGH: adopting the launch
        // value as a baseline and then demanding a change meant a seat that
        // set both keys and restarted never ran anything.
        private static string _lastRun, _key, _lastKeyOpened;
        // Every run has a number, so a tap destroyed late cannot flag a run
        // that started after it (r9 PLAUSIBLE).
        private static int _gen;
        // Wall time in which audio output was expected, for the delivery
        // comparison below.
        private static float _audioWallSeconds;
        // Bound on deferring the post-run collection while a room is live.
        private static float _cleanupGcDeadline;
        // Bounded mask across a scripted transition, instead of masking whole
        // steps that are supposed to be audible (r9 MEDIUM).
        private static float _maskUntil;
        private static Mode _mode;
        private static UnityWebRequest _req, _reqKeep;
        private static AudioClip _clip;
        private static GameObject _go;
        private static AudioSource _src;
        private static ProbeTap _tap;
        private static float _startRt, _openFrameMax, _frameMax, _nextLog, _endAt, _getContentMs, _requestMs, _openBlockMs;
        private static int _openLogFrame = -1;
        private static bool _openPending, _warm;
        private static long _playStartTicks;
        // drift reference (reset after every control action)
        private static double _dspRef;
        private static float _timeRef, _lastTime, _lastDrift, _stallMax, _driftPeak;
        private static int _wraps, _stalls;
        // memory
        private static long _mgd0, _nat0, _res0, _proc0;
        private static float _cleanupSampleAt = -1f, _cleanupGcAt = -1f;
        private static string _cleanupKey;
        // controls
        private static int _step;
        private static float _stepAt, _stepDeadline, _stepTarget;
        private static int _controlsPass, _controlsFail;
        // churn
        private static int _churnCycles;
        private static float _churnPlayUntil;
        // contention
        private static Thread[] _busy;
        private static volatile bool _busyRun;
        private static float _busyUntil, _busyStartAt;
        // release retry (r2 PLAUSIBLE: a throwing release must not lose the handle)
        private static readonly List<KeyValuePair<object, int>> _retry = new List<KeyValuePair<object, int>>();
        internal static volatile bool HostDestroyed;

        internal static void Tick()
        {
            try
            {
                if (Plugin.MusicProbeRun == null) return;
                float now = Time.realtimeSinceStartup;
                // Only while enabled: a seat with the probe off must not read
                // the config file every two seconds forever.
                if (SeatAllowed()) ReloadIfDue(now);
                float dt = Time.unscaledDeltaTime * 1000f;
                if (dt > _frameMax) _frameMax = dt;
                if ((_req != null || _openPending) && dt > _openFrameMax) _openFrameMax = dt;
                if (_retry.Count > 0) RetryReleases();
                if (_cleanupSampleAt > 0f && now >= _cleanupSampleAt) { _cleanupSampleAt = -1f; LogMemory("after_cleanup", _cleanupKey); }
                if (_busy != null && now >= _busyUntil) StopBusy();
                // r2 MEDIUM 3: a destroyed host (scene edge, or anything else)
                // leaves _src as a Unity fake-null while the streamed request
                // and clip are still retained — release, never idle.
                if (HostDestroyed || (_src == null && (_reqKeep != null || (object)_clip != null)))
                {
                    HostDestroyed = false;
                    if (_reqKeep != null || (object)_clip != null || (object)_src != null) { Stop("host destroyed"); return; }
                }
                if (_cleanupGcAt > 0f && now >= _cleanupGcAt)
                {
                    // r9 MEDIUM: NEVER inside a live match. Entering an online
                    // room ends the run and schedules this, and a full blocking
                    // collection five seconds later is a hitch in somebody's
                    // game. Deferred while a room is live, and abandoned if the
                    // room outlasts the window — a memory delta is worth
                    // nothing next to a stutter in a ranked round.
                    if (SeatContext() == "online-room")
                    {
                        if (now >= _cleanupGcDeadline)
                        {
                            _cleanupGcAt = -1f;
                            Plugin.Log?.LogInfo("[MUSIC-PROBE] cleanup collection abandoned — the room outlasted the window");
                        }
                        else _cleanupGcAt = now + 5f;
                    }
                    else
                    {
                        // dV2 MEDIUM 4: a settle point for the cleanup sample — the
                        // deferred native destroys have run by now and the managed
                        // side is collected, so the delta is a leak reading, not
                        // allocator noise.
                        _cleanupGcAt = -1f;
                        try { GC.Collect(); GC.WaitForPendingFinalizers(); } catch { }
                        LogMemory("after_cleanup_gc", _cleanupKey);
                    }
                }
                if (_req == null && _src == null)
                {
                    // Idle: the key has to be ON to start anything, and _last is
                    // dropped while it is off, so turning it back on adopts the
                    // current command as the baseline instead of replaying a
                    // stale one. Starting a run then needs a NEW value, exactly
                    // as it always did.
                    // The key going off drops the last-run memo, so turning
                    // it back on re-runs whatever command is set — which is the
                    // whole "set the key, get a measurement" path.
                    if (!SeatAllowed()) { _lastRun = null; return; }
                    string raw = (Plugin.MusicProbeRun.Value ?? "").Trim();
                    // Compared with what was RUN, never with what was last
                    // seen: the value present at launch is a command, not a
                    // baseline (review r9 HIGH). A command that Start refuses
                    // still counts as run, so a refusal does not spin — change
                    // the value or toggle the key to try it again.
                    if (raw.Length == 0 || raw == _lastRun) return;
                    _lastRun = raw;
                    Start(raw, now);
                    return;
                }
                // The key going false mid-run must END the run, not strand it:
                // returning early here would leave the request, clip, source and
                // host object retained with nothing left to release them.
                if (!SeatAllowed()) { Stop("probe key turned off"); return; }
                if (_req != null) { PumpRequest(now); return; }
                if (_src != null) PumpPlayback(now);
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[MUSIC-PROBE] tick threw: " + ex.Message);
                Stop("exception");
            }
        }

        private static void Start(string raw, float now)
        {
            string[] parts = raw.Split(':');
            if (parts.Length < 2) { Plugin.Log?.LogWarning("[MUSIC-PROBE] bad lever '" + raw + "' (want sku:idx[:stress|:churn])"); return; }
            var album = MusicCatalog.Get(parts[0]);
            int idx;
            if (album == null || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out idx)
                || idx < 0 || idx >= album.Tracks.Length)
            { Plugin.Log?.LogWarning("[MUSIC-PROBE] unknown album/track '" + raw + "'"); return; }
            // r9 MEDIUM: a deferred cleanup belongs to the run that
            // scheduled it. Its memory baselines are about to be overwritten
            // by this run, so comparing against them would report this run's
            // allocations as the previous run's leak — and would force a
            // blocking collection in the middle of this one. Dropped, said so.
            if (_cleanupSampleAt > 0f || _cleanupGcAt > 0f)
                Plugin.Log?.LogInfo("[MUSIC-PROBE] pending cleanup for " + (_cleanupKey ?? "?")
                                    + " dropped — a new run started inside its window");
            _cleanupSampleAt = -1f; _cleanupGcAt = -1f;
            _gen++;
            _audioWallSeconds = 0f;
            _maskUntil = 0f;
            _mode = Mode.Normal;
            if (parts.Length > 2)
            {
                if (string.Equals(parts[2], "stress", StringComparison.OrdinalIgnoreCase)) _mode = Mode.Stress;
                else if (string.Equals(parts[2], "churn", StringComparison.OrdinalIgnoreCase)) _mode = Mode.Churn;
            }
            _key = parts[0] + ":" + idx.ToString(CultureInfo.InvariantCulture);
            // r2 LOW 3: every counter belongs to THIS run, reset before the
            // request so a failed open reports zeros, not the previous run.
            _stallMax = 0f; _stalls = 0; _wraps = 0; _driftPeak = 0f; _lastDrift = 0f; _frameMax = 0f;
            _controlsPass = 0; _controlsFail = 0; _churnCycles = 0; _getContentMs = 0f; _requestMs = 0f; _openBlockMs = 0f;
            // r2 MEDIUM 5: a second music owner makes every auditory reading
            // ambiguous. Custom music sounding = refuse; vanilla = report.
            bool custom = false;
            try { custom = MusicEngine.IsPlayingNow; } catch { }
            string vanilla = VanillaGuards();
            string ctx = SeatContext();
            string refuse = custom ? "custom-music-playing"
                : ctx == "online-room" ? "online-room"
                : (_mode == Mode.Stress && ctx != "sandbox") ? "stress-needs-offline-sandbox"
                : null;
            if (refuse != null)
            {
                Plugin.Log?.LogWarning("[MUSIC-PROBE] refused key=" + _key + " reason=" + refuse + " context=" + ctx + " vanilla_guards=" + vanilla);
                return;
            }
            Plugin.Log?.LogInfo("[MUSIC-PROBE] begin key=" + _key + " mode=" + _mode + " context=" + ctx + " vanilla_guards=" + vanilla
                + " cores=" + Environment.ProcessorCount + " (bots/opponents are the operator's responsibility; the log cannot see them)");
            LogMemory("baseline", _key);
            _mgd0 = GC.GetTotalMemory(false); _nat0 = NativeAlloc(); _res0 = NativeReserved(); _proc0 = ProcessPrivate();
            OpenRequest(album.Tracks[idx].OggFile, now);
        }

        private static string SeatContext()
        {
            try
            {
                if (PhotonNetwork.InRoom && PhotonNetwork.OfflineMode)
                    return SandboxLive() ? "sandbox" : "offline-idle";
                if (PhotonNetwork.InRoom) return "online-room";
                return "menu";
            }
            catch { return "?"; }
        }

        private static string VanillaGuards()
        {
            try
            {
                // Reflection only (same surface MusicEngine's oracle reads): the
                // probe must not add a compile-time dependency on the wrapper.
                var t = AccessTools.TypeByName("SoundImplementation.SoundMusicManager") ?? AccessTools.TypeByName("SoundMusicManager");
                if (t == null) return "no-type";
                object mgr = null;
                var pInst = AccessTools.Property(t, "Instance");
                if (pInst != null) mgr = pInst.GetValue(null, null);
                else { var fInst = AccessTools.Field(t, "Instance"); if (fInst != null) mgr = fInst.GetValue(null); }
                if (mgr == null) return "no-manager";
                var fMenu = AccessTools.Field(t, "musicMainMenuPlaying");
                var fIngame = AccessTools.Field(t, "musicIngamePlaying");
                string m = fMenu != null && fMenu.GetValue(mgr) is bool b1 && b1 ? "1" : "0";
                string g = fIngame != null && fIngame.GetValue(mgr) is bool b2 && b2 ? "1" : "0";
                return "menu=" + m + ",ingame=" + g;
            }
            catch { return "?"; }
        }

        private static bool OpenRequest(string oggFile, float now)
        {
            string path = MusicAssets.PathFor(oggFile);
            if (path == null) { Plugin.Log?.LogWarning("[MUSIC-PROBE] file not ready for " + _key + " (full tier not installed?)"); return false; }
            string url;
            try { url = new Uri(path).AbsoluteUri; }
            catch { url = "file:///" + path.Replace('\\', '/'); }
            _warm = string.Equals(_lastKeyOpened, _key, StringComparison.Ordinal);
            _req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
            var dh = _req.downloadHandler as DownloadHandlerAudioClip;
            if (dh != null) dh.streamAudio = true;
            _openFrameMax = 0f; _openPending = false;
            _req.SendWebRequest();
            _startRt = now;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] request key=" + _key + " stream=1 mode=" + _mode + " warm=" + (_warm ? 1 : 0));
            return true;
        }

        private static void PumpRequest(float now)
        {
            // r9 MEDIUM: the refusal has to come BEFORE the work. Entering an
            // online room while the request was in flight used to reach
            // GetContent() and Play() on this tick, with the playback tick
            // noticing only afterwards — a second music source audible inside
            // somebody's match for a frame or more.
            if (SeatContext() == "online-room") { Stop("entered online room"); return; }
            if (!_req.isDone)
            {
                if (now - _startRt > 30f) { Plugin.Log?.LogWarning("[MUSIC-PROBE] request timeout"); Stop("timeout"); }
                return;
            }
            if (!string.IsNullOrEmpty(_req.error))
            {
                Plugin.Log?.LogWarning("[MUSIC-PROBE] request error: " + _req.error);
                Stop("error");
                return;
            }
            _requestMs = (now - _startRt) * 1000f;
            // r2 MEDIUM 6: the open is the WHOLE completion block — GetContent,
            // host + source construction and Play — and the frame it lands in
            // shows up as the next frame's delta, so open_frame_max keeps
            // accumulating for two more frames before the record is written.
            var block = Stopwatch.StartNew();
            var sw = Stopwatch.StartNew();
            _clip = DownloadHandlerAudioClip.GetContent(_req);
            sw.Stop();
            _getContentMs = (float)sw.Elapsed.TotalMilliseconds;
            _reqKeep = _req; _req = null;
            if (_clip == null) { Plugin.Log?.LogWarning("[MUSIC-PROBE] GetContent returned null"); Stop("null clip"); return; }
            _lastKeyOpened = _key;
            _go = new GameObject("SCR_MusicProbe") { hideFlags = HideFlags.HideAndDontSave };
            _src = _go.AddComponent<AudioSource>();
            _src.clip = _clip; _src.loop = true; _src.playOnAwake = false; _src.volume = 0.5f;
            _tap = _go.AddComponent<ProbeTap>();
            _tap.Reset();
            _tap.Gen = _gen;
            HostDestroyed = false;
            _playStartTicks = Stopwatch.GetTimestamp();
            _src.Play();
            block.Stop();
            _openBlockMs = (float)block.Elapsed.TotalMilliseconds;
            ResetDriftRef();
            _step = _mode == Mode.Churn ? -1 : 0;
            _stepAt = now + 20f;
            _nextLog = now + 5f;
            float budget = _mode == Mode.Stress ? 600f : 120f;
            if (_mode == Mode.Churn) { _churnPlayUntil = now + 1f; budget = 30f; }
            _endAt = now + budget;
            if (_mode == Mode.Stress) _busyStartAt = now + 60f;
            _openPending = true;
            // +3, not +2: the metric is "two FULL following frames", and
            // +2 observes the completion frame and one complete frame after it
            // (r9 LOW).
            _openLogFrame = Time.frameCount + 3;
        }

        private static void ResetDriftRef()
        {
            _dspRef = AudioSettings.dspTime;
            _timeRef = _src.time;
            _lastTime = _timeRef;
            _lastDrift = 0f;
            _wraps = 0;
        }

        private static void PumpPlayback(float now)
        {
            if (_openPending && Time.frameCount >= _openLogFrame)
            {
                _openPending = false;
                Plugin.Log?.LogInfo("[MUSIC-PROBE] opened key=" + _key + " warm=" + (_warm ? 1 : 0)
                    + " request_ms=" + F0(_requestMs) + " getcontent_ms=" + F1(_getContentMs) + " open_block_ms=" + F1(_openBlockMs)
                    + " open_frame_max_ms=" + F1(_openFrameMax)
                    + " loadState=" + _clip.loadState + " loadType=" + _clip.loadType
                    + " length_s=" + F1(_clip.length) + " freq=" + _clip.frequency + " ch=" + _clip.channels);
                LogMemory("after_open", _key);
            }
            // Context is re-checked every tick: an online room ends any run, and
            // leaving the offline Sandbox ends a stress run (busy threads must
            // never overlap a live match).
            string ctxNow = SeatContext();
            if (ctxNow == "online-room") { Stop("entered online room"); return; }
            if (_mode == Mode.Stress && ctxNow != "sandbox") { Stop("left sandbox"); return; }
            // r9 MEDIUM: exclusive ownership is not a start-time property. The
            // normal engine can be paused or mid-load at admission and resume
            // after it, and then two of this mod's music sources are audible at
            // once and every auditory reading is ambiguous. Re-asked every
            // tick, exactly like the context above.
            bool customNow = false;
            try { customNow = MusicEngine.IsPlayingNow; } catch { }
            if (customNow) { Stop("custom music started"); return; }
            // H2. silent_run counts zero-filled buffers that ARRIVED; a
            // callback the audio thread never reached supplies no buffer at
            // all, so a starved run reads clean. Accumulate the wall time in
            // which output was expected — the tap's own delivered-frame count
            // is compared against it in the record below.
            if (_tap != null && !_tap.SilenceExpected && _src.isPlaying)
                _audioWallSeconds += Time.unscaledDeltaTime;
            float t = _src.time;
            float len = _clip.length;
            // Wrap-aware: a drop of more than half the clip is a loop wrap.
            if (t < _lastTime - len * 0.5f) _wraps++;
            _lastTime = t;
            bool paused = _step == 3 || _step == 4;   // scripted pause window: the clock is expected to stand still
            float drift = 0f;
            if (!paused && _src.isPlaying)
            {
                float expected = _timeRef + (float)(AudioSettings.dspTime - _dspRef);
                float unwrapped = t + _wraps * len;
                drift = expected - unwrapped;
                float jump = drift - _lastDrift;
                if (jump > 0.06f) { _stalls++; if (jump > _stallMax) _stallMax = jump; }
                _lastDrift = drift;
                if (drift > _driftPeak) _driftPeak = drift;
            }
            if (_tap != null && _tap.FirstSampleTicks != 0 && !_tap.FirstSampleLogged)
            {
                _tap.FirstSampleLogged = true;
                double ms = (_tap.FirstSampleTicks - _playStartTicks) * 1000.0 / Stopwatch.Frequency;
                Plugin.Log?.LogInfo("[MUSIC-PROBE] started key=" + _key + " first_sample_ms=" + F1((float)ms));
            }
            if (_mode == Mode.Stress && _busy == null && _busyStartAt > 0f && now >= _busyStartAt) StartBusy(now);
            if (_mode == Mode.Churn) { PumpChurn(now); return; }
            PumpControls(now, t, len);
            if (_src == null) return;   // a control step may have stopped the run
            // Re-derive AFTER the control step: the first VM run paused the
            // source in step 2 and the stale `paused` read it as an unexpected
            // stop one line later.
            paused = _step == 3 || _step == 4;
            // r9 MEDIUM: steps 4 and 5 are AUDIBLE — playing after the resume,
            // and playing toward the end of the track — so masking them hid
            // every zero buffer in the two steps the measurement most cares
            // about. Only the scripted pause is masked, plus a bounded window
            // after each seek/pause/resume where a buffer boundary can legally
            // be silent.
            if (_tap != null) _tap.SilenceExpected = _step == 3 || now < _maskUntil;
            bool ended = !_src.isPlaying && !paused && _step != 5;
            if (now >= _nextLog || now >= _endAt)
            {
                _nextLog = now + 5f;
                Plugin.Log?.LogInfo("[MUSIC-PROBE] play key=" + _key + " t=" + F1(t) + " wraps=" + _wraps
                    + " drift_ms=" + F0(drift * 1000f) + " drift_peak_ms=" + F0(_driftPeak * 1000f)
                    + " stalls=" + _stalls + " stall_max_ms=" + F0(_stallMax * 1000f)
                    + " silent_run=" + _tap.SilentRun + " silent_run_max=" + _tap.SilentRunMax + " buffers=" + _tap.Buffers
                    + " audio_gap_max_ms=" + F1(MaxGapMs()) + " audio_deficit_ms=" + F0(DeficitMs())
                    + " frame_max_ms=" + F1(_frameMax) + " fps=" + (Time.smoothDeltaTime > 0f ? F0(1f / Time.smoothDeltaTime) : "?")
                    + " busy=" + (_busy != null ? 1 : 0) + " playing=" + (_src.isPlaying ? 1 : 0) + " step=" + _step + " context=" + SeatContext());
                _frameMax = 0f;
                LogMemory("during", _key);
            }
            if (ended) Stop("stopped unexpectedly");
            else if (now >= _endAt) Stop("budget");
        }

        // Scripted control sequence (§2.2 controls). Steps:
        // 0 wait 20 s → 1 seek running to len-8 (expect wrap ≤ 9 s) → 2 verify wrap →
        // 3 pause 3 s (clock must stand still) → 4 seek paused to 10 s, resume, verify →
        // 5 loop off + seek len-5, expect natural end ≤ 7 s → 6 restart loop=true → 7 done.
        private static void PumpControls(float now, float t, float len)
        {
            switch (_step)
            {
                case 0:
                    if (now < _stepAt) return;
                    if (len < 20f) { Plugin.Log?.LogInfo("[MUSIC-PROBE] controls key=" + _key + " skipped (track shorter than 20 s)"); _step = 7; return; }
                    _stepTarget = len - 8f;
                    _src.time = _stepTarget;
                    _maskUntil = now + 0.5f;
                    _stepAt = now; _stepDeadline = now + 9f;
                    _step = 1;
                    return;
                case 1:
                    if (now - _stepAt < 0.5f) return;
                    Judge("seek_running", Mathf.Abs(_src.time - (_stepTarget + (now - _stepAt))) < 0.5f, "t=" + F1(_src.time) + " want~" + F1(_stepTarget + (now - _stepAt)));
                    ResetDriftRef();
                    _step = 2;
                    return;
                case 2:
                    if (_wraps >= 1) { Judge("loop_wrap", true, "wrapped at t=" + F1(t)); _src.Pause(); _stepTarget = _src.time; _stepAt = now; _step = 3; return; }
                    if (now > _stepDeadline) { Judge("loop_wrap", false, "no wrap within 9 s, t=" + F1(t)); _src.Pause(); _stepTarget = _src.time; _stepAt = now; _step = 3; }
                    return;
                case 3:
                    if (now - _stepAt < 3f) return;
                    Judge("pause_holds", Mathf.Abs(_src.time - _stepTarget) < 0.05f && !_src.isPlaying, "t=" + F1(_src.time) + " held=" + F1(_stepTarget) + " playing=" + (_src.isPlaying ? 1 : 0));
                    _src.time = 10f;
                    _src.UnPause();
                    _maskUntil = now + 0.5f;
                    _stepAt = now;
                    _step = 4;
                    return;
                case 4:
                    if (now - _stepAt < 1f) return;
                    Judge("seek_paused_resume", _src.isPlaying && Mathf.Abs(_src.time - (10f + (now - _stepAt))) < 0.5f, "t=" + F1(_src.time) + " want~" + F1(10f + (now - _stepAt)));
                    _src.loop = false;
                    _src.time = len - 5f;
                    _maskUntil = now + 0.5f;
                    ResetDriftRef();
                    _stepAt = now; _stepDeadline = now + 7f;
                    _step = 5;
                    return;
                case 5:
                    if (!_src.isPlaying)
                    {
                        // r9 MEDIUM: the seek was to len-5, so a genuine
                        // natural end arrives about five seconds later. An
                        // immediate !isPlaying is a source that stopped for
                        // some other reason and proves nothing — it used to
                        // pass with no elapsed-time evidence at all.
                        float elapsed = now - _stepAt;
                        Judge("natural_end", elapsed >= 4.5f,
                              "isPlaying=0 after " + F1(elapsed) + " s (want >= 4.5 from len-5), t=" + F1(_src.time));
                        _src.loop = true; _src.time = 0f; _src.Play();
                        _maskUntil = now + 0.5f;
                        ResetDriftRef();
                        _step = 6;
                        return;
                    }
                    if (now > _stepDeadline)
                    {
                        Judge("natural_end", false, "still playing after 7 s, t=" + F1(_src.time) + " (loop=false should have ended)");
                        _src.loop = true; ResetDriftRef(); _step = 6;
                    }
                    return;
                case 6:
                    Plugin.Log?.LogInfo("[MUSIC-PROBE] controls key=" + _key + " pass=" + _controlsPass + " fail=" + _controlsFail);
                    _step = 7;
                    return;
                default:
                    return;
            }
        }

        private static void Judge(string name, bool ok, string detail)
        {
            if (ok) _controlsPass++; else _controlsFail++;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] control key=" + _key + " " + name + "=" + (ok ? "pass" : "FAIL") + " " + detail);
        }

        private static void PumpChurn(float now)
        {
            if (now < _churnPlayUntil) return;
            _churnCycles++;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] churn key=" + _key + " cycle=" + _churnCycles + " getcontent_ms=" + F1(_getContentMs) + " open_block_ms=" + F1(_openBlockMs) + " request_ms=" + F0(_requestMs));
            if (_churnCycles >= 10) { Stop("churn done"); return; }
            // close this cycle's objects without ending the run, then reopen
            CloseObjects();
            string oggFile = null;
            try { var parts = _key.Split(':'); var album = MusicCatalog.Get(parts[0]); oggFile = album.Tracks[int.Parse(parts[1], CultureInfo.InvariantCulture)].OggFile; } catch { }
            if (oggFile == null || !OpenRequest(oggFile, now)) { Stop("churn reopen failed"); return; }
            _churnPlayUntil = now + 1f;
        }

        // ── contention (stress only) ─────────────────────────────────────
        private static void StartBusy(float now)
        {
            int n = Math.Max(1, Math.Min(7, Environment.ProcessorCount - 1));
            _busy = new Thread[n];
            _busyRun = true;
            for (int i = 0; i < n; i++)
            {
                _busy[i] = new Thread(BusyLoop) { IsBackground = true, Name = "SCR_MusicProbeBusy" + i };
                _busy[i].Start();
            }
            _busyUntil = now + 60f;
            _busyStartAt = -1f;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] busy key=" + _key + " threads=" + n + " for 60 s");
        }

        private static void BusyLoop()
        {
            double x = 1.0001;
            while (_busyRun) { for (int i = 0; i < 100000; i++) x = x * 1.0000001 + 0.000001; if (x > 1e300) x = 1.0001; }
        }

        private static void StopBusy()
        {
            _busyRun = false;
            _busy = null;
            Plugin.Log?.LogInfo("[MUSIC-PROBE] busy key=" + _key + " released");
        }

        // ── memory ───────────────────────────────────────────────────────
        private static long NativeAlloc() { try { return Profiler.GetTotalAllocatedMemoryLong(); } catch { return -1; } }
        private static long NativeReserved() { try { return Profiler.GetTotalReservedMemoryLong(); } catch { return -1; } }
        private static long ProcessPrivate() { try { return Process.GetCurrentProcess().PrivateMemorySize64; } catch { return -1; } }

        private static void LogMemory(string phase, string key)
        {
            long mgd = GC.GetTotalMemory(false), nat = NativeAlloc(), res = NativeReserved(), proc = ProcessPrivate();
            Plugin.Log?.LogInfo("[MUSIC-PROBE] mem key=" + key + " phase=" + phase
                + " managed_mb=" + Mb(mgd) + " native_alloc_mb=" + Mb(nat) + " native_reserved_mb=" + Mb(res) + " process_private_mb=" + (proc > 0 ? Mb(proc) : "?")
                + (phase == "baseline" ? "" : " d_managed_mb=" + Dmb(mgd - _mgd0) + " d_native_alloc_mb=" + Dmb(nat - _nat0) + " d_native_reserved_mb=" + Dmb(res - _res0) + " d_process_mb=" + (proc > 0 && _proc0 > 0 ? Dmb(proc - _proc0) : "?")));
        }

        // ── teardown ─────────────────────────────────────────────────────
        private static void Release(object h, string what)
        {
            try
            {
                if (h is AudioSource s) { s.Stop(); return; }
                if (h is Component c) { UnityEngine.Object.Destroy(c); return; }
                if (h is UnityEngine.Object o) { UnityEngine.Object.Destroy(o); return; }
                if (h is UnityWebRequest r) { r.Dispose(); return; }
            }
            catch (Exception ex)
            {
                // Keep the handle for a bounded retry rather than dropping it.
                Plugin.Log?.LogWarning("[MUSIC-PROBE] release failed (" + what + "): " + ex.Message);
                _retry.Add(new KeyValuePair<object, int>(h, 1));
            }
        }

        private static void RetryReleases()
        {
            for (int i = _retry.Count - 1; i >= 0; i--)
            {
                var kv = _retry[i];
                _retry.RemoveAt(i);
                try
                {
                    if (kv.Key is UnityEngine.Object o) { if (o != null) UnityEngine.Object.Destroy(o); }
                    else if (kv.Key is UnityWebRequest r) r.Dispose();
                }
                catch (Exception ex)
                {
                    if (kv.Value < 3) _retry.Add(new KeyValuePair<object, int>(kv.Key, kv.Value + 1));
                    else Plugin.Log?.LogWarning("[MUSIC-PROBE] release abandoned after 3 attempts: " + ex.Message);
                }
            }
        }

        private static void CloseObjects()
        {
            if ((object)_src != null) Release(_src, "source");
            if ((object)_tap != null) Release(_tap, "tap");
            if ((object)_go != null) Release(_go, "host");
            if ((object)_clip != null) Release(_clip, "clip");
            if (_req != null) Release(_req, "request");
            if (_reqKeep != null) Release(_reqKeep, "streamed request");
            _src = null; _tap = null; _go = null; _clip = null; _req = null; _reqKeep = null;
            HostDestroyed = false;
        }

        private static void Stop(string why)
        {
            Plugin.Log?.LogInfo("[MUSIC-PROBE] end key=" + _key + " why=" + why + " mode=" + _mode + " wraps=" + _wraps
                + " stalls=" + _stalls + " stall_max_ms=" + F0(_stallMax * 1000f) + " drift_peak_ms=" + F0(_driftPeak * 1000f)
                + " silent_run_max=" + ((object)_tap != null ? _tap.SilentRunMax : -1)
                + " audio_gap_max_ms=" + F1(MaxGapMs()) + " audio_deficit_ms=" + F0(DeficitMs())
                + " controls_pass=" + _controlsPass + " controls_fail=" + _controlsFail);
            if (_busy != null) StopBusy();
            _openPending = false;
            CloseObjects();
            _cleanupKey = _key;
            _cleanupSampleAt = Time.realtimeSinceStartup + 2f;
            _cleanupGcAt = Time.realtimeSinceStartup + 5f;
            _cleanupGcDeadline = Time.realtimeSinceStartup + 120f;
        }

        /// <summary>The longest interval between two consecutive audio
        /// callbacks, in ms. This is the measurement silent_run cannot make:
        /// a callback that never happens leaves no buffer to inspect.</summary>
        private static float MaxGapMs()
        {
            if ((object)_tap == null || _tap.MaxGapTicks <= 0) return 0f;
            return (float)(_tap.MaxGapTicks * 1000.0 / Stopwatch.Frequency);
        }

        /// <summary>Wall time in which output was expected, minus the audio the
        /// tap was actually handed, in ms. Positive means the audio path fell
        /// behind the clock; a starved run shows it even when every buffer that
        /// did arrive was full of sound.</summary>
        private static float DeficitMs()
        {
            if ((object)_tap == null) return 0f;
            int rate = 0;
            try { rate = AudioSettings.outputSampleRate; } catch { }
            if (rate <= 0) return 0f;
            float delivered = (float)(_tap.FramesDelivered / (double)rate);
            return (_audioWallSeconds - delivered) * 1000f;
        }

        private static string F0(float v) { return v.ToString("F0", CultureInfo.InvariantCulture); }
        private static string F1(float v) { return v.ToString("F1", CultureInfo.InvariantCulture); }
        private static string Mb(long b) { return b < 0 ? "?" : (b / 1048576.0).ToString("F1", CultureInfo.InvariantCulture); }
        private static string Dmb(long b) { return (b / 1048576.0).ToString("+0.0;-0.0;0.0", CultureInfo.InvariantCulture); }

        /// <summary>Audio-thread tap on the probe source's output: counts
        /// buffers, the current and longest run of all-zero buffers, and the
        /// Stopwatch tick of the first non-zero sample. Written on the audio
        /// thread, read on the main thread (diagnostic: torn reads tolerated).
        /// OnDestroy flags the host so the owner releases what it still holds.</summary>
        private sealed class ProbeTap : MonoBehaviour
        {
            public volatile int Buffers, SilentRun, SilentRunMax;
            public long FirstSampleTicks;
            public bool FirstSampleLogged;
            /// <summary>The run this tap belongs to. A tap whose destruction
            /// threw is kept for a bounded retry, and its eventual OnDestroy
            /// would otherwise flag a run that started afterwards (r9
            /// PLAUSIBLE).</summary>
            public int Gen;
            /// <summary>Audio-thread clock of the last callback, the longest
            /// interval between two consecutive ones, and the audio frames
            /// actually handed to the output. These are what a MISSED callback
            /// shows up in: it supplies no zero-filled buffer, so silent_run
            /// stays at zero however starved the path is (review r9).</summary>
            public long LastCallbackTicks, MaxGapTicks, FramesDelivered;
            public void Reset()
            {
                Buffers = 0; SilentRun = 0; SilentRunMax = 0;
                FirstSampleTicks = 0; FirstSampleLogged = false;
                LastCallbackTicks = 0; MaxGapTicks = 0; FramesDelivered = 0;
            }
            /// <summary>Set by the main thread for the scripted pause and for a
            /// bounded window after each seek/pause/resume: the callback keeps
            /// running with zero buffers there, and the second VM run counted
            /// that expected silence as silent_run_max=143. It does NOT cover
            /// steps 4 and 5, which are audible and are the point.</summary>
            public volatile bool SilenceExpected;
            private void OnAudioFilterRead(float[] data, int channels)
            {
                // A masked span is not measured at all: no silence, no gap, no
                // delivery. Clearing the callback clock stops the far side of
                // the mask from reading as one enormous gap.
                if (SilenceExpected) { SilentRun = 0; LastCallbackTicks = 0; return; }
                long stamp = Stopwatch.GetTimestamp();
                long prev = LastCallbackTicks;
                LastCallbackTicks = stamp;
                if (prev != 0)
                {
                    long gap = stamp - prev;
                    if (gap > MaxGapTicks) MaxGapTicks = gap;
                }
                FramesDelivered += channels > 0 ? data.Length / channels : data.Length;
                bool silent = true;
                for (int i = 0; i < data.Length; i++) { if (data[i] != 0f) { silent = false; break; } }
                Buffers++;
                if (silent) { SilentRun++; if (SilentRun > SilentRunMax) SilentRunMax = SilentRun; }
                else { SilentRun = 0; if (FirstSampleTicks == 0) FirstSampleTicks = Stopwatch.GetTimestamp(); }
            }
            private void OnDestroy() { if (Gen == _gen) HostDestroyed = true; }
        }
    }
}
