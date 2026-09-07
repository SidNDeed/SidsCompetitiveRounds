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
    /// r9). Those two numbers are scoped to the SOURCE callback path: the tap
    /// sits on the probe's own AudioSource, so they say whether Unity kept
    /// pulling audio out of it, and a dropout introduced downstream of the tap
    /// — mixer, output device, driver — leaves them clean. The run also
    /// records managed/native/process memory before the request, after open
    /// and during play, and a scripted control sequence (seek running, pause +
    /// seek paused + resume, loop off → natural end, loop wrap) each judged
    /// pass/fail. ":stress" = 600 s plus up to 7 busy threads (ProcessorCount
    /// - 1, capped) for 60 s; ":churn" = ten bind/unbind cycles on the same
    /// key. The probe never touches MusicEngine playback state (it reports its
    /// opens to the engine's residency line), and stops if the normal engine
    /// starts sounding at any point in a run.
    ///
    /// Opens (design v3 branch D, D11): a key is requested at most ONCE per
    /// process and its request + clip are RETAINED until the process exits —
    /// never disposed, never destroyed (a streamed clip reads its request's
    /// buffer). A later run or churn cycle on the same key RE-SELECTS the
    /// retained clip on a fresh source (`warm=1`, `reselect`), so request_ms
    /// and getcontent_ms are then the first open's. Memory rows (D8):
    /// d_native_per_open_mb on a first open (bound OggSize x 1.5 + 1 MB),
    /// d_native_reopen_mb on a re-selection (0 +/- 0.5 MB — a second request
    /// would show here as +MBs), both measured at the `opened` line and folded
    /// into `end`, which is written at the stop and is the run's last row
    /// (#564). No post-cleanup sample exists: nothing is cleaned up.
    ///
    /// Lifetime: the host GameObject is HideAndDontSave; if anything destroys it
    /// (its tap's OnDestroy flags it, and a Unity fake-null source is checked
    /// too) the run ends: the source, tap and host object are released, or
    /// abandoned after four attempts and logged (`[MUSIC-PROBE] handle
    /// abandoned`) — never treated as idle. The retained pair stays.</summary>
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
        private static string _lastRun, _key;
        // Every run has a number, so a tap destroyed late cannot flag a run
        // that started after it (r9 PLAUSIBLE).
        private static int _gen;
        // Wall time in which audio output was expected, for the delivery
        // comparison below.
        private static float _audioWallSeconds;

        /// <summary>Starvation totals for the RUN, not for the current tap.
        /// The tap is destroyed and rebuilt on every churn cycle and its Reset
        /// zeroes both counters, while _audioWallSeconds accrues across the
        /// whole run — comparing one against the other measured the bookkeeping
        /// rather than the audio path. CloseObjects folds the outgoing tap into
        /// these before releasing it, so the run owns the totals and the tap
        /// stays a per-instance collector.</summary>
        private static long _runMaxGapTicks;
        private static long _runFramesDelivered;
        private static int _runSilentRunMax;
        /// <summary>Tap delivery at the seek that sets up the natural end; -1
        /// while there is no such baseline.</summary>
        private static long _framesAtEndSeek = -1L;
        /// <summary>Design v2 §2.3.6 `time_at_death`: the source's last
        /// observed position while it was still playing after the end seek.
        /// isPlaying flips first and `time` reads 0 once the source has
        /// stopped, so the playhead has to be sampled BEFORE the death; -1
        /// while nothing was sampled.</summary>
        private static float _timeAtDeath = -1f;
        /// <summary>Whether ANY tap existed during this run. `-1` on the end
        /// line means no measurement was ever taken; a run whose tap reported a
        /// clean zero must not print the same marker.</summary>
        private static bool _runHadTap;
        /// <summary>r3 M4 (F3): cycles whose tap was still inside a callback
        /// when the bounded quiesce wait ran out. The fold that followed may
        /// have missed a run, so the bar cannot be shown to hold: a bar row.</summary>
        private static int _runTapQuiesceTimeouts;
        // Bounded mask across a scripted transition, instead of masking whole
        // steps that are supposed to be audible (r9 MEDIUM).
        private static float _maskUntil;
        private static Mode _mode;
        /// <summary>D11: a key is opened at most ONCE per process; its request
        /// and clip are retained here until the process exits — never
        /// disposed, never destroyed (a streamed clip reads its request's
        /// buffer). A later run or churn cycle on the key re-selects the
        /// retained clip on a fresh source; request_ms/getcontent_ms are the
        /// first open's. A request that never produced a clip is retained
        /// clip-less and the key is refused from then on.</summary>
        private sealed class RetainedOpen { public UnityWebRequest Req; public AudioClip Clip; public float RequestMs, GetContentMs; }
        private static readonly Dictionary<string, RetainedOpen> _opened = new Dictionary<string, RetainedOpen>(StringComparer.Ordinal);
        private static UnityWebRequest _req;   // this run's first-open request while in flight; retained from the stop or GetContent on
        private static AudioClip _clip;        // the run's clip — the retained one
        private static long _oggSize;          // catalog size of the run's file (the per-open bound)
        private static long _natOpen0 = -1L;   // native counter just before this open (the request, or the bind on a re-selection)
        private static string _nativeOpenRow;  // the run's first `opened` memory row, folded into the end record
        private static bool _nativeOpenPass;
        private static GameObject _go;
        private static AudioSource _src;
        private static ProbeTap _tap;
        private static float _startRt, _openFrameMax, _frameMax, _nextLog, _endAt, _getContentMs, _requestMs, _openBlockMs;
        private static int _openLogFrame = -1;
        private static bool _openPending, _warm;
        private static long _playStartTicks;
        // §2.4 / §7 2-9 PASS bar (impl2 r1 M4): retained across the run for the
        // end line's verdict (BarVerdict) — every row of the bar is judged there
        // except the memory row (D8: d_native_per_open_mb / d_native_reopen_mb),
        // judged at the `opened` line where it is measured and folded into the
        // end line by FinishEndRecord.
        private static float _firstSampleMs = -1f;   // -1 = no audible sample was ever observed
        private static float _deficitPeakMs;          // max of DeficitMs() sampled every playing tick
        private static bool _controlsDone;            // the scripted sequence reached its summary line
        // impl2 r2 M4: the start stamp of EVERY silent run of >= 2 buffers in
        // the run (folded from each tap's ring by CloseObjects), plus the
        // count the ring could not stamp. Each is judged against the scripted
        // windows in Stop — the longest run alone let a later, unscripted run
        // of equal length hide behind a scripted one's stamp.
        private static readonly List<long> _runSilentRunStarts = new List<long>();
        private static int _runSilentRunsUnstamped;
        // Scripted windows [from, to] in Stopwatch ticks: Play, each seek /
        // resume / restart, and the natural end. A silent run that STARTS
        // inside one is "at a scripted seek" (§2.4); one outside fails the bar.
        private static readonly List<KeyValuePair<long, long>> _scriptedWindows = new List<KeyValuePair<long, long>>();
        // impl2 r2 M4 / #564: the `end` record is the runner's stop signal, so
        // it is written only when its bar is FINAL. Under D every row is final
        // at the stop (the memory row was measured at the open): Stop builds
        // the record and FinishEndRecord appends the memory row and writes the
        // line at once — the last row of the run.
        private static string _endRecord;
        private static List<string> _endBar;   // null = churn (no bar)
        // Wall accrual after a Play/UnPause: the first accruing tick charges
        // the time since that call, not the whole frame (which began before
        // it) — with the deficit now judged per tick, a one-frame overcharge
        // at every start would read as starvation.
        private static long _wallFromTicks;
        private static bool _wallAccruing;
        // drift reference (reset after every control action)
        private static double _dspRef;
        private static float _timeRef, _lastTime, _lastDrift, _stallMax, _driftPeak;
        private static int _wraps, _stalls;
        // memory
        private static long _mgd0, _nat0, _res0, _proc0;
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
        // release retry (r2 PLAUSIBLE: a throwing release must not lose the
        // handle): the initial attempt plus three on later ticks, then the
        // handle is abandoned and said so (impl2 r2 LOW).
        private struct RetryHandle { public object Handle; public int Attempts; public string What; }
        private static readonly List<RetryHandle> _retry = new List<RetryHandle>();
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
                if (_busy != null && now >= _busyUntil) StopBusy();
                // r2 MEDIUM 3: a destroyed host (scene edge, or anything else)
                // leaves _src as a Unity fake-null while the run's clip is still
                // bound — the run ends (its retained pair stays, D11), never idle.
                if (HostDestroyed || (_src == null && (object)_clip != null))
                {
                    HostDestroyed = false;
                    if ((object)_clip != null || (object)_src != null) { Stop("host destroyed"); return; }
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
                // The key going false mid-run must END the run (Stop: the
                // source stops, the tap and the host object are destroyed, the
                // end record is written) rather than strand it mid-flight. The
                // request and the clip are retained either way (D11): a
                // disabled run keeps them on the key's record, by design.
                if (!SeatAllowed()) { Stop("probe key turned off"); return; }
                if (_req != null) { PumpRequest(now); return; }
                if (_src != null) PumpPlayback(now);
            }
            catch (Exception ex)
            {
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] tick threw: " + ex.Message);   // R4: a throwing logger must not skip the Stop
                Stop("exception");
            }
        }

        private static void Start(string raw, float now)
        {
            string[] parts = raw.Split(':');
            if (parts.Length < 2) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] bad lever '" + raw + "' (want sku:idx[:stress|:churn])"); return; }
            var album = MusicCatalog.Get(parts[0]);
            int idx;
            if (album == null || !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out idx)
                || idx < 0 || idx >= album.Tracks.Length)
            { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] unknown album/track '" + raw + "'"); return; }
            // A misspelled suffix used to run the DEFAULT mode silently, so an
            // operator asked for a stress run, got a two-minute normal one, and
            // the log said mode=Normal in a line nobody re-reads. The lever is a
            // diagnostic instruction; one that cannot be carried out is refused
            // out loud, and refused HERE, before the run takes any state — the
            // generation bump below belongs to a run that is actually going to
            // happen.
            Mode wanted = Mode.Normal;
            if (parts.Length > 3)
            {
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] too many fields in '" + raw + "' (want sku:idx[:stress|:churn])");
                return;
            }
            if (parts.Length > 2)
            {
                if (string.Equals(parts[2], "stress", StringComparison.OrdinalIgnoreCase)) wanted = Mode.Stress;
                else if (string.Equals(parts[2], "churn", StringComparison.OrdinalIgnoreCase)) wanted = Mode.Churn;
                else
                {
                    MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] unknown mode '" + parts[2] + "' in '" + raw + "' (want stress or churn)");
                    return;
                }
            }
            string key = parts[0] + ":" + idx.ToString(CultureInfo.InvariantCulture);
            // r2 MEDIUM 5: a second music owner makes every auditory reading
            // ambiguous. Custom music sounding = refuse; vanilla = report.
            //
            // ASKED HERE, before anything moves. It used to sit below the
            // generation bump, so a command refused for context still
            // invalidated the previous run's outgoing tap's generation — the
            // comment above the mode check claimed that mutation belonged to a
            // run that was going to happen, and for this refusal it did not.
            // It reads `wanted` rather than `_mode` for the same reason:
            // `_mode` is not this command's mode until the run is admitted.
            //
            // An UNREADABLE seat context is a refusal too. SeatContext returns
            // "?" when the Photon read throws, and "?" is not "online-room" —
            // so a context the probe could not establish used to be admitted,
            // which is the fail-open direction on the one question this guard
            // exists to answer.
            bool custom = false;
            try { custom = MusicEngine.IsPlayingNow; } catch { }
            string vanilla = VanillaGuards();
            string ctx = SeatContext();
            string refuse = custom ? "custom-music-playing"
                : ctx == "online-room" ? "online-room"
                : ctx == "?" ? "seat-context-unreadable"
                : (wanted == Mode.Stress && ctx != "sandbox") ? "stress-needs-offline-sandbox"
                : null;
            if (refuse != null)
            {
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] refused key=" + key + " reason=" + refuse + " context=" + ctx + " vanilla_guards=" + vanilla);
                return;
            }
            _gen++;
            _audioWallSeconds = 0f;
            _runMaxGapTicks = 0L;
            _runFramesDelivered = 0L;
            _runSilentRunMax = 0;
            _framesAtEndSeek = -1L;
            _timeAtDeath = -1f;
            _maskUntil = 0f;
            _mode = wanted;
            _key = key;
            _runHadTap = false;
            _runTapQuiesceTimeouts = 0;
            // r2 LOW 3: every counter belongs to THIS run, reset before the
            // request so a failed open reports zeros, not the previous run.
            _stallMax = 0f; _stalls = 0; _wraps = 0; _driftPeak = 0f; _lastDrift = 0f; _frameMax = 0f;
            _controlsPass = 0; _controlsFail = 0; _churnCycles = 0; _getContentMs = 0f; _requestMs = 0f; _openBlockMs = 0f;
            _firstSampleMs = -1f; _deficitPeakMs = 0f; _controlsDone = false; _runSilentRunStarts.Clear(); _runSilentRunsUnstamped = 0; _scriptedWindows.Clear();
            _wallFromTicks = 0L; _wallAccruing = false;
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] begin key=" + _key + " mode=" + _mode + " context=" + ctx + " vanilla_guards=" + vanilla
                + " cores=" + Environment.ProcessorCount + " (bots/opponents are the operator's responsibility; the log cannot see them)");
            // R17 (impl r3): the baselines are sampled ONCE, here, and the
            // baseline row prints these stored values; a -1 stays -1 for the
            // run (every later native delta prints `unmeasured`).
            _mgd0 = GC.GetTotalMemory(false); _nat0 = NativeAlloc(); _res0 = NativeReserved(); _proc0 = ProcessPrivate();
            LogMemory("baseline", _key);
            _oggSize = album.Tracks[idx].OggSize;
            _nativeOpenRow = null; _nativeOpenPass = false;
            BeginOpen(album.Tracks[idx], now);
        }

        /// <summary>Photon's own room-entry edge.
        ///
        /// The playback tick asks RefusalNow every frame, but a join can land
        /// AFTER that tick has already read "menu", and the probe's private
        /// source then stays audible for the rest of the frame and into the
        /// next one. "Never runs inside an online room" has to be true at the
        /// edge rather than at the next poll.
        ///
        /// Offline rooms raise this callback too — Photon's offline mode
        /// simulates the join — and the Sandbox is where this probe is meant to
        /// run, so an offline join is not an end. A read that throws is treated
        /// as online: the run ending early costs a measurement, and the other
        /// direction costs somebody else's match.</summary>
        internal static void OnRoomJoined()
        {
            try
            {
                bool online;
                try { online = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode; }
                catch { online = true; }
                if (!online) return;
                if (_req != null || _openPending || (object)_src != null) Stop("entered online room");
            }
            catch { }
        }

        /// <summary>The three conditions that end a run, asked as one
        /// question so no caller can ask a subset of them. The playback tick
        /// asked all three and the open path asked only the first, which meant
        /// a run could reach Play() with custom music already sounding or with
        /// a stress run outside the Sandbox it is confined to.
        ///
        /// FAILS CLOSED on an unreadable context. `SeatContext` returns "?" when
        /// the Photon read throws, and "?" is not "online-room" — so the old
        /// comparison treated a context the probe could not establish as
        /// evidence that it was not in a match. A context nobody can read is
        /// not one an online room can be excluded from.</summary>
        private static string RefusalNow()
        {
            string ctx = SeatContext();
            if (ctx == "online-room") return "entered online room";
            if (ctx == "?") return "seat context unreadable";
            if (_mode == Mode.Stress && ctx != "sandbox") return "left sandbox";
            try { if (MusicEngine.IsPlayingNow) return "custom music started"; }
            catch { }
            return null;
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

        /// <summary>D11: the open. A key already opened in this process is
        /// RE-SELECTED — no request, no GetContent: its retained clip is bound
        /// to a fresh source and the first open's request_ms/getcontent_ms
        /// stand. A first open makes the ONE request the key will ever get
        /// (reported to the engine's residency line) and PumpRequest completes
        /// it. False = refused (nothing was started).</summary>
        private static bool BeginOpen(MusicTrackDef track, float now)
        {
            _startRt = now;
            _openFrameMax = 0f; _openPending = false;
            _natOpen0 = NativeAlloc();
            if (_opened.TryGetValue(_key, out var kept))
            {
                _warm = true;
                _requestMs = kept.RequestMs; _getContentMs = kept.GetContentMs;
                if ((object)kept.Clip == null || kept.Clip == null)
                {
                    MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] refused key=" + _key + " reason=retained-open-has-no-clip (opened once already; a key is never requested twice)");
                    return false;
                }
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] reselect key=" + _key + " mode=" + _mode + " (retained pair; request_ms/getcontent_ms are the first open's)");
                BindAndPlay(kept.Clip, now, null);
                return true;
            }
            string path = MusicAssets.PathFor(track.OggFile);
            if (path == null) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] file not ready for " + _key + " (full tier not installed?)"); return false; }
            string url;
            try { url = new Uri(path).AbsoluteUri; }
            catch { url = "file:///" + path.Replace('\\', '/'); }
            _warm = false;
            // R8: the key's record exists BEFORE any allocation (state:
            // attempting — no request, no clip). An allocation that throws
            // leaves it clip-less, i.e. refused (D-m), so a later command for
            // the same key never allocates again; probe_opens counts records.
            var rec = new RetainedOpen();
            _opened[_key] = rec;
            long bytes = 0L;
            string failed = null;
            try
            {
                _req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
                var dh = _req.downloadHandler as DownloadHandlerAudioClip;
                if (dh != null) dh.streamAudio = true;
                _req.SendWebRequest();
                bytes = track.OggSize;
            }
            catch (Exception ex) { failed = ex.Message; }
            MusicEngine.NoteProbeOpen(_key, bytes);   // D11: probe_opens= on the residency line — the record, whatever the allocation did (R11: no engine baseline seeding)
            if (failed != null)
            {
                rec.Req = _req; _req = null;   // a request that exists is retained on the record (D-m); nothing is disposed
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] request failed key=" + _key + ": " + failed + " (record kept clip-less; key refused from now on)");
                return false;
            }
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] request key=" + _key + " stream=1 mode=" + _mode + " warm=0");
            return true;
        }

        /// <summary>D11/R8: the pair fills the key's record — the record was
        /// written at BeginOpen, before the allocation — once per key,
        /// whatever GetContent returned, and clip-less for a request the run
        /// ended before it completed (InProgress at teardown is the retain
        /// class). A record that already holds a request or a clip is never
        /// overwritten; nothing ever leaves the store.</summary>
        private static void RetainOpen(UnityWebRequest req, AudioClip clip)
        {
            if (_key == null) return;
            if (!_opened.TryGetValue(_key, out var rec)) { rec = new RetainedOpen(); _opened[_key] = rec; }
            if (rec.Req != null || (object)rec.Clip != null) return;
            rec.Req = req; rec.Clip = clip; rec.RequestMs = _requestMs; rec.GetContentMs = _getContentMs;
        }

        private static void PumpRequest(float now)
        {
            // r9 MEDIUM: the refusal has to come BEFORE the work. Entering an
            // online room while the request was in flight used to reach
            // GetContent() and Play() on this tick, with the playback tick
            // noticing only afterwards — a second music source audible inside
            // somebody's match for a frame or more.
            string refuseOpen = RefusalNow();
            if (refuseOpen != null) { Stop(refuseOpen); return; }
            if (!_req.isDone)
            {
                if (now - _startRt > 30f) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] request timeout (request retained, key refused from now on)"); Stop("timeout"); }   // R4 class: no logger ahead of a Stop may skip it
                return;
            }
            if (!string.IsNullOrEmpty(_req.error))
            {
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] request error: " + _req.error + " (request retained, key refused from now on)");
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
            AudioClip clip = null;
            try { clip = DownloadHandlerAudioClip.GetContent(_req); }
            catch (Exception ex) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] GetContent threw: " + ex.Message); }   // R4 class: the record below must be filled whatever the logger does
            sw.Stop();
            _getContentMs = (float)sw.Elapsed.TotalMilliseconds;
            // D11: the pair is retained from here whatever GetContent returned.
            var req = _req; _req = null;
            RetainOpen(req, clip);
            if (clip == null) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] GetContent returned no clip (request retained, key refused from now on)"); Stop("null clip"); return; }
            BindAndPlay(clip, now, block);
        }

        /// <summary>The completion block's tail: host + source construction
        /// and Play on the clip — a first open's, after GetContent, or a
        /// re-selection's (then the block starts here). Refusal is asked AGAIN
        /// immediately before the first audible sample: the streamed handle
        /// open and the host construction are not free, so the answer from the
        /// top of the tick is milliseconds old — and this is the one line
        /// where being wrong is audible in somebody else's match. Nothing has
        /// played yet, so Stop simply releases what was built.</summary>
        private static void BindAndPlay(AudioClip clip, float now, Stopwatch block)
        {
            if (block == null) block = Stopwatch.StartNew();
            _clip = clip;
            _go = new GameObject("SCR_MusicProbe") { hideFlags = HideFlags.HideAndDontSave };
            _src = _go.AddComponent<AudioSource>();
            _src.clip = _clip; _src.loop = true; _src.playOnAwake = false; _src.volume = 0.5f;
            _tap = _go.AddComponent<ProbeTap>();
            _tap.Reset();
            _tap.Gen = _gen;
            HostDestroyed = false;
            string refuseAtPlay = RefusalNow();
            if (refuseAtPlay != null) { Stop(refuseAtPlay); return; }
            _playStartTicks = Stopwatch.GetTimestamp();
            NoteScriptedWindow(0f);   // the buffers before the first sample are scripted silence
            _wallFromTicks = _playStartTicks;
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
                // D8: the memory row, measured here (three frames after the
                // completion block) against the counter sampled just before
                // this open. A first open pays the request buffer plus FMOD's
                // stream state: bound OggSize x 1.5 + 1 MB. A re-selection
                // binds a retained clip and must cost nothing: 0 +/- 0.5 MB —
                // a second request would show here as +MBs (D3). Judged where
                // it is measured; a bar row on the broadcast seat only (impl2
                // r1 M4: the seat that can exclude other activity). R17: the
                // row's baseline was sampled just before this open and is not
                // resampled; a counter unreadable on either side prints the
                // row as unmeasured, which is a failed bar row, never a pass.
                long nat = NativeAlloc();
                bool natAvail = nat >= 0 && _natOpen0 >= 0;
                long d = natAvail ? nat - _natOpen0 : 0L;
                double dMb = d / 1048576.0;
                string rowName = _warm ? "d_native_reopen_mb" : "d_native_per_open_mb";
                double boundMb = _warm ? 0.5 : _oggSize / 1048576.0 * 1.5 + 1.0;
                bool pass = natAvail && (_warm ? Math.Abs(dMb) <= boundMb : dMb <= boundMb);
                string boundText = _warm ? "+/-0.5" : F1((float)boundMb);
                string verdict = !natAvail ? "unmeasured" : !BroadcastMode.IsBroadcastIdentity ? "measured-only" : pass ? "pass" : "FAIL";
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] opened key=" + _key + " warm=" + (_warm ? 1 : 0)
                    + " request_ms=" + F0(_requestMs) + " getcontent_ms=" + F1(_getContentMs) + " open_block_ms=" + F1(_openBlockMs)
                    + " open_frame_max_ms=" + F1(_openFrameMax)
                    + " loadState=" + _clip.loadState + " loadType=" + _clip.loadType
                    + " length_s=" + F1(_clip.length) + " freq=" + _clip.frequency + " ch=" + _clip.channels
                    + " " + rowName + "=" + (natAvail ? Dmb(d) : "unmeasured") + " bound=" + boundText + " verdict=" + verdict);
                // The end record carries the run's LAST opened row: the only
                // one of a normal/stress run, the tenth re-selection's of a
                // churn run (each cycle prints its own line above).
                _nativeOpenRow = rowName + "=" + (!natAvail ? "unmeasured"
                    : !BroadcastMode.IsBroadcastIdentity ? Dmb(d) + "(measured-only)"
                    : pass ? Dmb(d)
                    : Dmb(d) + ">" + boundText);
                _nativeOpenPass = pass;
                LogMemory("after_open", _key);
            }
            // Context is re-checked every tick: an online room ends any run, and
            // leaving the offline Sandbox ends a stress run (busy threads must
            // never overlap a live match).
            // r9 MEDIUM: exclusive ownership is not a start-time property.
            // The normal engine can be paused or mid-load at admission and
            // resume after it, and then two of this mod's music sources are
            // audible at once and every auditory reading is ambiguous. Asked
            // every tick, together with the seat context and the stress
            // confinement — see RefusalNow.
            string refuseNow = RefusalNow();
            if (refuseNow != null) { Stop(refuseNow); return; }
            // H2. silent_run counts zero-filled buffers that ARRIVED; a
            // callback the audio thread never reached supplies no buffer at
            // all, so a starved run reads clean. Accumulate the wall time in
            // which output was expected — the tap's own delivered-frame count
            // is compared against it in the record below.
            // Gated on the PAUSE mask, not the content mask: across the
            // post-seek window the source is playing and callbacks are owed, so
            // that wall time belongs in the expectation the delivery count is
            // compared against. Gating it on the content mask would excuse the
            // very interval the split above exists to measure.
            if (_tap != null && !_tap.CallbacksPaused && _src.isPlaying)
            {
                if (_wallAccruing) _audioWallSeconds += Time.unscaledDeltaTime;
                else
                {
                    float since = (float)((Stopwatch.GetTimestamp() - _wallFromTicks) / (double)Stopwatch.Frequency);
                    _audioWallSeconds += Mathf.Clamp(since, 0f, Time.unscaledDeltaTime);
                    _wallAccruing = true;
                }
            }
            else _wallAccruing = false;
            // impl2 r1 M4 (§7 2-9): the peak deficit is retained per tick, not
            // only at the 5 s records — a transient starvation between two
            // records is exactly what the row exists to catch. Read from the
            // same expression as the end line's figure.
            { float d = DeficitMs(); if (d > _deficitPeakMs) _deficitPeakMs = d; }
            float t = _src.time;
            float len = _clip.length;
            // Wrap-aware: a drop of more than half the clip is a loop wrap.
            if (t < _lastTime - len * 0.5f) _wraps++;
            _lastTime = t;
            // Step 3 ALONE is the pause. Step 4 is the RESUMED source: audible,
            // and the step whose whole purpose is to verify that the resume
            // took — so suppressing its drift and stalls hid a resume-only
            // stall and then reset the reference it would have been measured
            // against. `resuming` exists because isPlaying can lag UnPause by a
            // tick, and an unexpected-stop verdict there would pre-empt step
            // 4's own judgement, which is the designed detector.
            bool paused = _step == 3;
            bool resuming = _step == 4;
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
                _firstSampleMs = (float)ms;
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] started key=" + _key + " first_sample_ms=" + F1((float)ms));
            }
            if (_mode == Mode.Stress && _busy == null && _busyStartAt > 0f && now >= _busyStartAt) StartBusy(now);
            if (_mode == Mode.Churn) { PumpChurn(now); return; }
            PumpControls(now, t, len);
            if (_src == null) return;   // a control step may have stopped the run
            // Re-derive AFTER the control step: the first VM run paused the
            // source in step 2 and the stale `paused` read it as an unexpected
            // stop one line later.
            paused = _step == 3;
            resuming = _step == 4;
            // r9 MEDIUM: steps 4 and 5 are AUDIBLE — playing after the resume,
            // and playing toward the end of the track — so masking them hid
            // every zero buffer in the two steps the measurement most cares
            // about. Only the scripted pause is masked, plus a bounded window
            // after each seek/pause/resume where a buffer boundary can legally
            // be silent.
            if (_tap != null)
            {
                // CallbacksPaused is NOT set here. It is a transition, taken
                // by MaskCallbacks at the Pause/UnPause call itself — a poll
                // one frame later attributes every callback in between to the
                // wrong side. The post-seek window still gets callbacks and
                // only excuses their content, so a missed one inside it is
                // still measured, and that one IS a per-frame condition.
                _tap.SilenceExpected = _step == 3 || now < _maskUntil;
            }
            bool ended = !_src.isPlaying && !paused && !resuming && _step != 5;
            if (now >= _nextLog || now >= _endAt)
            {
                _nextLog = now + 5f;
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] play key=" + _key + " t=" + F1(t) + " wraps=" + _wraps
                    + " drift_ms=" + F0(drift * 1000f) + " drift_peak_ms=" + F0(_driftPeak * 1000f)
                    + " stalls=" + _stalls + " stall_max_ms=" + F0(_stallMax * 1000f)
                    + " silent_run=" + _tap.SilentRun + " silent_run_max=" + _tap.SilentRunMax + " buffers=" + _tap.Buffers
                    + " audio_gap_max_ms=" + F1(MaxGapMs()) + " audio_deficit_ms=" + F0(DeficitMs()) + " audio_deficit_peak_ms=" + F0(_deficitPeakMs)
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
                    if (len < 20f) { MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] controls key=" + _key + " skipped (track shorter than 20 s)"); _step = 7; return; }
                    _stepTarget = len - 8f;
                    NoteScriptedWindow(0f);
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
                    if (_wraps >= 1) { Judge("loop_wrap", true, "wrapped at t=" + F1(t)); _src.Pause(); MaskCallbacks(true); _stepTarget = _src.time; _stepAt = now; _step = 3; return; }
                    if (now > _stepDeadline) { Judge("loop_wrap", false, "no wrap within 9 s, t=" + F1(t)); _src.Pause(); MaskCallbacks(true); _stepTarget = _src.time; _stepAt = now; _step = 3; }
                    return;
                case 3:
                    if (now - _stepAt < 3f) return;
                    Judge("pause_holds", Mathf.Abs(_src.time - _stepTarget) < 0.05f && !_src.isPlaying, "t=" + F1(_src.time) + " retained=" + F1(_stepTarget) + " playing=" + (_src.isPlaying ? 1 : 0));
                    _src.time = 10f;
                    NoteScriptedWindow(0f);
                    MaskCallbacks(false);
                    _wallFromTicks = Stopwatch.GetTimestamp();
                    _src.UnPause();
                    // The drift reference is from before the pause and the
                    // seek, so it is meaningless now. Step 4 is AUDIBLE and its
                    // drift is measured (it used to be suppressed as though it
                    // were part of the pause), which needs a reference taken
                    // here rather than three steps ago.
                    ResetDriftRef();
                    _maskUntil = now + 0.5f;
                    _stepAt = now;
                    _step = 4;
                    return;
                case 4:
                    if (now - _stepAt < 1f) return;
                    Judge("seek_paused_resume", _src.isPlaying && Mathf.Abs(_src.time - (10f + (now - _stepAt))) < 0.5f, "t=" + F1(_src.time) + " want~" + F1(10f + (now - _stepAt)));
                    _src.loop = false;
                    NoteScriptedWindow(0f);
                    _src.time = len - 5f;
                    _maskUntil = now + 0.5f;
                    ResetDriftRef();
                    // Delivery baseline for the end judgement below: elapsed
                    // wall time says only that five seconds passed, which a
                    // source stopped by something else also satisfies.
                    _framesAtEndSeek = (object)_tap != null ? _tap.FramesDelivered : -1L;
                    _timeAtDeath = -1f;
                    _stepAt = now; _stepDeadline = now + 7f;
                    _step = 5;
                    return;
                case 5:
                    if (_src.isPlaying) _timeAtDeath = _src.time;   // last position seen alive (§2.3.6)
                    if (!_src.isPlaying)
                    {
                        // The natural end is scripted silence too: the buffers
                        // up to half a second before the observed stop.
                        NoteScriptedWindow(0.5f);
                        // r9 MEDIUM: the seek was to len-5, so a genuine
                        // natural end arrives about five seconds later. An
                        // immediate !isPlaying is a source that stopped for
                        // some other reason and proves nothing — it used to
                        // pass with no elapsed-time evidence at all.
                        float elapsed = now - _stepAt;
                        // Three facts, not one. The seek was to len-5, so a
                        // genuine end arrives about five seconds later: too
                        // early is a source that stopped for another reason,
                        // too late is one that stopped for another reason after
                        // the end should already have come. And the tap must
                        // have been handed roughly those five seconds of audio,
                        // which is the only evidence here that the PLAYHEAD
                        // reached the end rather than the clock reaching 4.5.
                        float owed = EndRunSeconds();
                        bool timed = elapsed >= 4.5f && elapsed <= 6.5f;
                        // NOT "unknown counts as played". The delivered figure
                        // is the only evidence here that the PLAYHEAD reached
                        // the end rather than the clock reaching 4.5, so a run
                        // that cannot produce it has not shown what this
                        // control tests — and a source stopping five seconds
                        // after the seek for any other reason satisfies the
                        // timing alone. An unavailable tap is a broken probe
                        // run, which is worth failing loudly.
                        bool played = owed >= 4f;
                        Judge("natural_end", timed && played,
                              "isPlaying=0 after " + F1(elapsed) + " s (want 4.5-6.5 from len-5), "
                              + "delivered=" + (owed < 0f ? "unavailable" : F1(owed)) + " s (want >= 4), t=" + F1(_src.time));
                        // §2.3.6: the last position seen alive must sit inside the
                        // engine's 4 s natural window (MusicEngine.EOF_WINDOW_SEC),
                        // or a streamed clip's real end is classified premature
                        // there. The position is sampled once per tick, so the
                        // gap includes up to one frame of playback.
                        Judge("time_at_death", _timeAtDeath >= 0f && len - _timeAtDeath <= 4f,
                              "t=" + (_timeAtDeath < 0f ? "unavailable" : F1(_timeAtDeath)) + " len=" + F1(len)
                              + " gap=" + (_timeAtDeath < 0f ? "?" : F1(len - _timeAtDeath)) + " (want <= 4)");
                        _src.loop = true; _src.time = 0f;
                        NoteScriptedWindow(0f);
                        MaskCallbacks(false);   // the natural end is an intended silence, not a gap
                        _wallFromTicks = Stopwatch.GetTimestamp();
                        _src.Play();
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
                    _controlsDone = true;
                    MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] controls key=" + _key + " pass=" + _controlsPass + " fail=" + _controlsFail);
                    _step = 7;
                    return;
                default:
                    return;
            }
        }

        /// <summary>The scripted pause mask, set at the call that causes it
        /// rather than by the next tick's poll.
        ///
        /// Two faults, one shape. The flag used to be assigned once per frame
        /// from `_step`, AFTER `PumpControls` had already called `Pause()` or
        /// `UnPause()` — so a callback in between was attributed to the wrong
        /// side: one after UnPause and before the clear was dropped although it
        /// delivered real audio, and one after the pause and before the set was
        /// counted as content the run had asked for. And on the way OUT of a
        /// healthy pause nothing cleared the callback clock, because clearing
        /// it lived in the callback that a healthy pause never receives — so
        /// the first callback after a three-second pause reported a
        /// three-second gap, in the field that exists to find dropouts.
        ///
        /// Entering, the flag is set AFTER the pause call: a callback still in
        /// flight delivered real audio and is counted. Leaving, it is cleared
        /// BEFORE the resume call, which cannot lose one, because a paused
        /// source produces none — and the clock is cleared with it, so the
        /// first callback of the resumed source starts a fresh interval
        /// instead of measuring the pause.</summary>
        private static void MaskCallbacks(bool paused)
        {
            var tap = _tap;
            if ((object)tap == null) return;
            if (paused) { tap.CallbacksPaused = true; return; }
            tap.LastCallbackTicks = 0;
            tap.CallbacksPaused = false;
        }

        private static void Judge(string name, bool ok, string detail)
        {
            if (ok) _controlsPass++; else _controlsFail++;
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] control key=" + _key + " " + name + "=" + (ok ? "pass" : "FAIL") + " " + detail);
        }

        private static void PumpChurn(float now)
        {
            if (now < _churnPlayUntil) return;
            _churnCycles++;
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] churn key=" + _key + " cycle=" + _churnCycles + " getcontent_ms=" + F1(_getContentMs) + " open_block_ms=" + F1(_openBlockMs) + " request_ms=" + F0(_requestMs));
            if (_churnCycles >= 10) { Stop("churn done"); return; }
            // D11: this cycle's source, tap and host object go without ending
            // the run; the retained pair is re-selected onto a fresh source.
            CloseObjects();
            MusicTrackDef track = null;
            try { var parts = _key.Split(':'); var album = MusicCatalog.Get(parts[0]); track = album.Tracks[int.Parse(parts[1], CultureInfo.InvariantCulture)]; } catch { }
            if (track == null || !BeginOpen(track, now)) { Stop("churn reselect failed"); return; }
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
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] busy key=" + _key + " threads=" + n + " for 60 s");
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
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] busy key=" + _key + " released");   // R4: teardown logging is swallow-all
        }

        // ── memory ───────────────────────────────────────────────────────
        private static long NativeAlloc() { try { return Profiler.GetTotalAllocatedMemoryLong(); } catch { return -1; } }
        private static long NativeReserved() { try { return Profiler.GetTotalReservedMemoryLong(); } catch { return -1; } }
        private static long ProcessPrivate() { try { return Process.GetCurrentProcess().PrivateMemorySize64; } catch { return -1; } }

        /// <summary>R17: the run's native baselines (_nat0/_res0) are sampled
        /// once at Start, before the run's first allocation, and never
        /// resampled; a counter that read -1 on either side prints that
        /// native field as `unmeasured`, never a delta against -1.</summary>
        private static void LogMemory(string phase, string key)
        {
            bool baseline = phase == "baseline";   // the stored samples, never a second read
            long mgd = baseline ? _mgd0 : GC.GetTotalMemory(false), nat = baseline ? _nat0 : NativeAlloc(), res = baseline ? _res0 : NativeReserved(), proc = baseline ? _proc0 : ProcessPrivate();
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, "[MUSIC-PROBE] mem key=" + key + " phase=" + phase
                + " managed_mb=" + Mb(mgd) + " native_alloc_mb=" + (nat < 0 ? "unmeasured" : Mb(nat)) + " native_reserved_mb=" + Mb(res) + " process_private_mb=" + (proc > 0 ? Mb(proc) : "?")
                + (phase == "baseline" ? "" : " d_managed_mb=" + Dmb(mgd - _mgd0) + " d_native_alloc_mb=" + DmbOr(nat, _nat0) + " d_native_reserved_mb=" + DmbOr(res, _res0) + " d_process_mb=" + (proc > 0 && _proc0 > 0 ? Dmb(proc - _proc0) : "?")));
        }

        // ── teardown ─────────────────────────────────────────────────────
        /// <summary>Per-run objects only — the source (stopped), the tap and
        /// the host object (destroyed). The retained pair (request, clip) is
        /// never passed here (D11): no dispose exists in this file.</summary>
        private static void Release(object h, string what)
        {
            try
            {
                if (h is AudioSource s) { s.Stop(); return; }
                if (h is Component c) { UnityEngine.Object.Destroy(c); return; }
                if (h is UnityEngine.Object o) { UnityEngine.Object.Destroy(o); return; }
            }
            catch (Exception ex)
            {
                // Keep the handle for a bounded retry rather than dropping it:
                // three more attempts on later ticks, then abandoned and logged.
                // R4: the handle is kept BEFORE any logging, and the logger is
                // swallow-all — a throw in either cannot abort the teardown.
                _retry.Add(new RetryHandle { Handle = h, Attempts = 1, What = what });
                MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] release failed (" + what + "): " + ex.Message);
            }
        }

        private static void RetryReleases()
        {
            for (int i = _retry.Count - 1; i >= 0; i--)
            {
                var r = _retry[i];
                _retry.RemoveAt(i);
                try
                {
                    if (r.Handle is UnityEngine.Object o) { if (o != null) UnityEngine.Object.Destroy(o); }
                }
                catch (Exception ex)
                {
                    r.Attempts++;
                    if (r.Attempts < 4) _retry.Add(r);
                    else MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] handle abandoned after 4 attempts (" + r.What + "): " + ex.Message + " — this handle is NOT released");
                }
            }
        }

        private static void CloseObjects()
        {
            // r3 M4 (F3): STOP FIRST, QUIESCE, THEN FOLD. The fold used to
            // read the silent-run count and ring while the source still
            // played, so the audio thread could deliver the qualifying second
            // zero buffer of an unscripted run after the read and before
            // Stop — a run missing from the snapshot, and a `bar=pass` over
            // it. Now the source is stopped, the tap is disarmed with a full
            // fence and the main thread waits (bounded) for any callback
            // already inside the tap to leave; only then are the counters
            // and the ring folded, so every run the tap ever stamped is in
            // them. A Stop that throws keeps its handle for the retry as
            // before; the disarm alone ends the recording either way.
            if ((object)_src != null) Release(_src, "source");
            if ((object)_tap != null)
            {
                if (!QuiesceTap(_tap))
                {
                    _runTapQuiesceTimeouts++;
                    MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Warning, "[MUSIC-PROBE] tap still inside a callback " + TAP_QUIESCE_MS + " ms after the disarm — the fold below may miss a run; counted against the bar");
                }
                // Fold BEFORE the release, or a churn cycle's gaps and delivered
                // frames leave with the tap that recorded them.
                if (_tap.MaxGapTicks > _runMaxGapTicks) _runMaxGapTicks = _tap.MaxGapTicks;
                if (_tap.SilentRunMax > _runSilentRunMax) _runSilentRunMax = _tap.SilentRunMax;
                // impl2 r2 M4: every silent run of >= 2 buffers is judged, not
                // just the longest — the tap's start stamps join the run's
                // list here (classification against the scripted windows is
                // the main thread's, in Stop). Runs past the ring were counted
                // but not stamped; they cannot be shown scripted, so they fail.
                int runs = _tap.SilentRunCount;
                int stamped = Math.Min(runs, ProbeTap.SilentRunRing);
                for (int i = 0; i < stamped; i++) _runSilentRunStarts.Add(_tap.SilentRunStartTicks[i]);
                _runSilentRunsUnstamped += runs - stamped;
                _runHadTap = true;
                _runFramesDelivered += _tap.FramesDelivered;
            }
            if ((object)_tap != null) Release(_tap, "tap");
            if ((object)_go != null) Release(_go, "host");
            // D11: the request and the clip are the retained pair — never
            // released, never destroyed. A request still in flight at the stop
            // (timeout, refusal) is retained too, clip-less.
            if (_req != null) { RetainOpen(_req, null); _req = null; }
            _src = null; _tap = null; _go = null; _clip = null;
            HostDestroyed = false;
        }

        private const int TAP_QUIESCE_MS = 20;

        /// <summary>r3 M4 (F3): disarms the tap and confirms, on the main
        /// thread, that no callback is still writing. Dekker-shaped with the
        /// tap's OnAudioFilterRead: the audio side marks InCallback with a
        /// full fence BEFORE it reads Armed; this side writes Armed and
        /// fences BEFORE it reads InCallback — so a callback that saw Armed
        /// set is seen here as in flight and waited out, and one that starts
        /// after the fence sees Armed clear and writes nothing but the mark.
        /// The wait is bounded (a callback's work is a zero scan over one
        /// buffer, microseconds); false past the bound is a bar failure, not
        /// a hang. No allocation on either side.</summary>
        private static bool QuiesceTap(ProbeTap tap)
        {
            tap.Armed = false;
            Thread.MemoryBarrier();
            long deadline = Stopwatch.GetTimestamp() + Stopwatch.Frequency * TAP_QUIESCE_MS / 1000L;
            while (Volatile.Read(ref tap.InCallback) != 0)
            {
                if (Stopwatch.GetTimestamp() > deadline) return false;
                Thread.Yield();
            }
            return true;
        }

        private static void Stop(string why)
        {
            // RELEASE FIRST. The record below builds a string, formats six
            // numbers and calls into the logger; a throw anywhere in it used to
            // strand the tap, the host object and up to seven spinning
            // background threads, because every release sat underneath it.
            // Every tap number is run-scoped and CloseObjects folds the
            // outgoing tap into the run totals AFTER stopping the source and
            // quiescing the tap (r3 M4), so they are complete — and final —
            // only after it; nothing is read off the tap before that.
            // Run-scoped, like the gap and the deficit: in churn mode the tap
            // is rebuilt every cycle, and the last cycle's number is not the
            // run's. -1 stays the "no tap ever existed" marker — and it is
            // decided by whether one ever existed, not by whether the number
            // is zero. A churn cycle whose tap reported a clean zero used to
            // come out as -1, i.e. as no measurement at all, which is the
            // opposite reading of the best possible result.
            if (_busy != null) StopBusy();
            _openPending = false;
            CloseObjects();
            int silentRunMax = _runHadTap ? _runSilentRunMax : -1;
            // The bar is judged AFTER CloseObjects: the run totals (delivered
            // frames, gaps, every silent run's start) are folded there.
            // impl2 r2 M4: every silent run of >= 2 buffers must have STARTED
            // inside a scripted window — judged here, on the main thread, with
            // every window of the run known; a run the tap counted but could
            // not stamp cannot be shown scripted and counts against the bar.
            int silentRuns = _runSilentRunStarts.Count + _runSilentRunsUnstamped;
            int unscripted = _runSilentRunsUnstamped;
            for (int i = 0; i < _runSilentRunStarts.Count; i++) if (!SilentRunIsScripted(_runSilentRunStarts[i])) unscripted++;
            // Every row is final here (D8, #564): the memory row was measured
            // at this run's `opened` line, nothing is cleaned up later, so the
            // `end` record — the runner's stop signal — is built and written
            // now, as the run's last row, with a verdict no later measurement
            // could retract.
            _endBar = BarVerdict(why, silentRunMax, unscripted);
            _endRecord = "[MUSIC-PROBE] end key=" + _key + " why=" + why + " mode=" + _mode + " wraps=" + _wraps
                + " stalls=" + _stalls + " stall_max_ms=" + F0(_stallMax * 1000f) + " drift_peak_ms=" + F0(_driftPeak * 1000f)
                + " silent_run_max=" + silentRunMax + " silent_runs=" + silentRuns + " silent_runs_unscripted=" + unscripted + " tap_quiesce_timeouts=" + _runTapQuiesceTimeouts
                + " audio_gap_max_ms=" + F1(MaxGapMs()) + " audio_deficit_ms=" + F0(DeficitMs()) + " audio_deficit_peak_ms=" + F0(_deficitPeakMs)
                + " open_block_ms=" + F1(_openBlockMs) + " first_sample_ms=" + (_firstSampleMs < 0f ? "?" : F1(_firstSampleMs))
                + " controls_pass=" + _controlsPass + " controls_fail=" + _controlsFail + " controls_done=" + (_controlsDone ? 1 : 0)
                + " time_at_death=" + (_timeAtDeath < 0f ? "?" : F1(_timeAtDeath));
            FinishEndRecord(_nativeOpenRow ?? (_warm ? "d_native_reopen_mb" : "d_native_per_open_mb") + "=unmeasured(run ended before its open settled)", _nativeOpenRow != null && _nativeOpenPass);
        }

        /// <summary>Writes the `end` record with its FINAL bar, at the stop
        /// (D8, #564: the memory row was measured at the open, nothing is
        /// pending, and this is the run's last row). `row` is the memory row —
        /// `d_native_per_open_mb=<mb>` on a first open, `d_native_reopen_mb=
        /// <mb>` on a re-selection, or an unmeasured marker — printed on EVERY
        /// seat; `pass` false adds it to the bar on the broadcast seat only,
        /// where it is a bar row (impl2 r1 M4: judged where it is measured;
        /// elsewhere other activity is not excluded, so the figure prints as
        /// measured-only). Churn runs carry no bar. A no-op when nothing is
        /// pending.</summary>
        private static void FinishEndRecord(string row, bool pass)
        {
            string rec = _endRecord;
            if (rec == null) return;
            _endRecord = null;
            var fails = _endBar;
            _endBar = null;
            string bar;
            if (fails == null) bar = "n/a(churn)";
            else
            {
                if (!pass && BroadcastMode.IsBroadcastIdentity) fails.Add(row);
                bar = fails.Count == 0 ? "pass" : "FAIL[" + string.Join(",", fails.ToArray()) + "]";
            }
            MusicEngine.SafeLog(BepInEx.Logging.LogLevel.Info, rec + " " + row + " bar=" + bar);   // R4
        }

        /// <summary>The longest interval between two consecutive audio
        /// callbacks, in ms. This is the measurement silent_run cannot make:
        /// a callback that never happens leaves no buffer to inspect.</summary>
        private static float MaxGapMs()
        {
            long ticks = _runMaxGapTicks;
            if ((object)_tap != null && _tap.MaxGapTicks > ticks) ticks = _tap.MaxGapTicks;
            if (ticks <= 0) return 0f;
            return (float)(ticks * 1000.0 / Stopwatch.Frequency);
        }

        /// <summary>Wall time in which output was expected, minus the audio the
        /// tap was actually handed, in ms. Positive means Unity fell behind in
        /// pulling from this source; a starved run shows it even when every
        /// buffer that did arrive was full of sound. Scoped to the source
        /// callback, which is where the tap is: this cannot see a dropout added
        /// downstream of it by the mixer or the output device.</summary>
        private static float DeficitMs()
        {
            int rate = 0;
            try { rate = AudioSettings.outputSampleRate; } catch { }
            if (rate <= 0) return 0f;
            long frames = _runFramesDelivered + ((object)_tap != null ? _tap.FramesDelivered : 0L);
            float delivered = (float)(frames / (double)rate);
            return (_audioWallSeconds - delivered) * 1000f;
        }

        /// <summary>Seconds of audio the tap was handed since the seek to
        /// len-5, or -1 when it cannot be established (no tap, no baseline, or
        /// no sample rate).
        ///
        /// NEGATIVE IS A FAILING ANSWER, not a neutral one, and this sentence
        /// used to say the opposite (r13 LOW). The natural-end control asks
        /// whether the PLAYHEAD reached the end of the clip; the only evidence
        /// of that available here is the audio the tap was handed, because the
        /// timing window alone is satisfied by a source that stopped five
        /// seconds after the seek for any other reason. A run that cannot
        /// produce the figure has not shown what the control tests, so the
        /// caller requires `>= 4` and an unavailable measurement fails it. That
        /// is a broken probe run reported as broken -- the outcome this file
        /// prefers over a control that passes on no evidence.</summary>
        private static float EndRunSeconds()
        {
            if (_framesAtEndSeek < 0L || (object)_tap == null) return -1f;
            long delivered = _tap.FramesDelivered - _framesAtEndSeek;
            if (delivered <= 0L) return 0f;
            int rate = 0;
            try { rate = AudioSettings.outputSampleRate; } catch { }
            if (rate <= 0) return -1f;
            return (float)(delivered / (double)rate);
        }

        /// <summary>A scripted window opens now: [now - backSec, now + 1 s].
        /// Every Play / seek / resume / restart calls this before the action;
        /// the natural end calls it with half a second of look-back, because
        /// its silent buffers precede the observed stop.</summary>
        private static void NoteScriptedWindow(float backSec)
        {
            long now = Stopwatch.GetTimestamp();
            long back = (long)(backSec * Stopwatch.Frequency);
            _scriptedWindows.Add(new KeyValuePair<long, long>(now - back, now + Stopwatch.Frequency));
        }

        private static bool SilentRunIsScripted(long startTicks)
        {
            if (startTicks == 0L) return false;
            for (int i = 0; i < _scriptedWindows.Count; i++)
                if (startTicks >= _scriptedWindows[i].Key && startTicks <= _scriptedWindows[i].Value) return true;
            return false;
        }

        /// <summary>The §2.4 + §7 2-9 PASS bar (impl2 r1 M4), judged at the
        /// stop for every row it can judge; the memory row (D8:
        /// d_native_per_open_mb on a first open, d_native_reopen_mb on a
        /// re-selection) was measured at the `opened` line and is appended by
        /// FinishEndRecord, which writes the end line with the FINAL verdict
        /// as the run's last row (#564). Every row is
        /// enforced: a run that did not reach its budget, a control sequence
        /// that did not complete, or a first sample never observed cannot
        /// pass; every silent run of >= 2 buffers must have started inside a
        /// scripted window (`unscripted` counts those that did not); the
        /// time_at_death bound is a control (§2.3.6) and rides the controls
        /// row. Churn runs have no bar (null).</summary>
        private static List<string> BarVerdict(string why, int silentRunMax, int unscripted)
        {
            if (_mode == Mode.Churn) return null;
            var fail = new List<string>();
            if (why != "budget") fail.Add("ended=" + why);
            if (_stalls != 0) fail.Add("stalls=" + _stalls);
            if (_driftPeak * 1000f > 60f) fail.Add("drift_peak=" + F0(_driftPeak * 1000f) + ">60");
            if (silentRunMax < 0 || silentRunMax > 2) fail.Add("silent_run_max=" + silentRunMax + (silentRunMax < 0 ? "(no tap)" : ">2"));
            if (unscripted > 0) fail.Add("silent_runs_unscripted=" + unscripted);
            if (_runTapQuiesceTimeouts > 0) fail.Add("tap_quiesce_timeouts=" + _runTapQuiesceTimeouts);
            if (MaxGapMs() > 100f) fail.Add("audio_gap_max=" + F1(MaxGapMs()) + ">100");
            if (DeficitMs() > 100f) fail.Add("audio_deficit_end=" + F0(DeficitMs()) + ">100");
            if (_deficitPeakMs > 100f) fail.Add("audio_deficit_peak=" + F0(_deficitPeakMs) + ">100");
            if (!_controlsDone) fail.Add("controls=incomplete");
            else if (_controlsFail != 0) fail.Add("controls_fail=" + _controlsFail);
            if (_openBlockMs > 20f) fail.Add("open_block=" + F1(_openBlockMs) + ">20");
            if (_firstSampleMs < 0f) fail.Add("first_sample=none");
            else if (_firstSampleMs > 50f) fail.Add("first_sample=" + F1(_firstSampleMs) + ">50");
            return fail;
        }

        private static string F0(float v) { return v.ToString("F0", CultureInfo.InvariantCulture); }
        private static string F1(float v) { return v.ToString("F1", CultureInfo.InvariantCulture); }
        private static string Mb(long b) { return b < 0 ? "unmeasured" : (b / 1048576.0).ToString("F1", CultureInfo.InvariantCulture); }
        private static string Dmb(long b) { return (b / 1048576.0).ToString("+0.0;-0.0;0.0", CultureInfo.InvariantCulture); }
        private static string DmbOr(long now, long baseline) { return now < 0 || baseline < 0 ? "unmeasured" : Dmb(now - baseline); }   // R17

        /// <summary>Audio-thread tap on the probe source's output: counts
        /// buffers, the current and longest run of all-zero buffers, and the
        /// Stopwatch tick of the first non-zero sample. Written on the audio
        /// thread; the mid-run polls on the main thread are diagnostic (torn
        /// reads tolerated), the fold at the stop is complete — it runs after
        /// QuiesceTap has disarmed the tap and seen no callback in flight
        /// (r3 M4). OnDestroy flags the host so the owner releases what it
        /// still holds.</summary>
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
            /// <summary>impl2 r2 M4: the Stopwatch stamp of the FIRST buffer of
            /// EVERY silent run that reached two buffers, in a ring allocated
            /// once with the tap — the audio thread only stores a stamp and
            /// bumps the count, never allocates or classifies; CloseObjects
            /// folds the ring into the run and Stop judges each stamp against
            /// the scripted windows. SilentRunCount keeps counting past the
            /// ring; the unstamped remainder cannot be shown scripted and
            /// fails the bar. The longest run's stamp alone let a later run of
            /// equal length hide behind it (the `>`-only maximum).</summary>
            public const int SilentRunRing = 64;
            public readonly long[] SilentRunStartTicks = new long[SilentRunRing];
            public volatile int SilentRunCount;
            private long _silentRunStartTicks;
            /// <summary>r3 M4 (F3): the tap records only while ARMED. Reset
            /// arms it last (the volatile write publishes the cleared fields
            /// with it); QuiesceTap clears it, fences, and waits for
            /// InCallback — set with a full fence at the top of every
            /// callback, before Armed is read, and cleared at its exit — to
            /// read zero, so the fold that follows sees every write the tap
            /// ever made and no callback writes after it. InCallback is
            /// deliberately not reset: a callback may be inside the mark.</summary>
            public volatile bool Armed;
            public int InCallback;
            public void Reset()
            {
                Buffers = 0; SilentRun = 0; SilentRunMax = 0;
                FirstSampleTicks = 0; FirstSampleLogged = false;
                LastCallbackTicks = 0; MaxGapTicks = 0; FramesDelivered = 0;
                SilentRunCount = 0; _silentRunStartTicks = 0;
                CallbacksPaused = false; SilenceExpected = false;
                Armed = true;
            }
            /// <summary>The scripted PAUSE, where Unity stops calling the
            /// filter at all. Nothing is measured across it: no delivery, no
            /// gap, no silence.
            ///
            /// The callback clock is cleared in TWO places and both are needed.
            /// Here, for a callback that does arrive while the flag is set. And
            /// on the main thread in MaskCallbacks, at the resume, for the
            /// HEALTHY case — where no callback arrives at all, so nothing on
            /// this thread runs and the pre-pause stamp would otherwise survive
            /// to be differenced against the first resumed callback and
            /// reported as a three-second dropout.</summary>
            public volatile bool CallbacksPaused;

            /// <summary>A bounded window after each seek/pause/resume where a
            /// buffer boundary can legally be silent. The source is PLAYING
            /// across it, so callbacks are still expected — only their CONTENT
            /// is excused. The second VM run counted that expected silence as
            /// silent_run_max=143, and masking it whole then hid the opposite
            /// fault: a callback that never arrived inside those 0.5 s left no
            /// gap and no missing delivery either, so starvation in the window
            /// was invisible. Content and cadence are two different questions
            /// and this masks only the first. It does NOT cover steps 4 and 5,
            /// which are audible and are the point.</summary>
            public volatile bool SilenceExpected;
            private void OnAudioFilterRead(float[] data, int channels)
            {
                // r3 M4 (F3): mark in-flight (full fence) BEFORE reading Armed
                // — see QuiesceTap; the disarmed path writes nothing else.
                Interlocked.Exchange(ref InCallback, 1);
                try
                {
                    if (!Armed) return;
                    Record(data, channels);
                }
                finally { Interlocked.Exchange(ref InCallback, 0); }
            }
            private void Record(float[] data, int channels)
            {
                if (CallbacksPaused) { SilentRun = 0; LastCallbackTicks = 0; return; }
                long stamp = Stopwatch.GetTimestamp();
                long prev = LastCallbackTicks;
                LastCallbackTicks = stamp;
                if (prev != 0)
                {
                    long gap = stamp - prev;
                    if (gap > MaxGapTicks) MaxGapTicks = gap;
                }
                FramesDelivered += channels > 0 ? data.Length / channels : data.Length;
                Buffers++;
                // Cadence and delivery are recorded above whatever the content
                // mask says; only the zero-run accounting below is excused.
                if (SilenceExpected) { SilentRun = 0; return; }
                bool silent = true;
                for (int i = 0; i < data.Length; i++) { if (data[i] != 0f) { silent = false; break; } }
                if (silent)
                {
                    if (SilentRun == 0) _silentRunStartTicks = stamp;
                    SilentRun++;
                    if (SilentRun > SilentRunMax) SilentRunMax = SilentRun;
                    // The run became a run (two buffers): stamp its start once.
                    if (SilentRun == 2)
                    {
                        int n = SilentRunCount;
                        if (n < SilentRunRing) SilentRunStartTicks[n] = _silentRunStartTicks;
                        SilentRunCount = n + 1;
                    }
                }
                else { SilentRun = 0; if (FirstSampleTicks == 0) FirstSampleTicks = Stopwatch.GetTimestamp(); }
            }
            private void OnDestroy() { if (Gen == _gen) HostDestroyed = true; }
        }
    }
}
