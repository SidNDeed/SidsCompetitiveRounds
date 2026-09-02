// The contract lists `internal enum MusicMode` beside the class and both
// sibling spellings landed in the same wave: CompetitiveUI compares
// MusicEngine.MusicMode.Custom (nested) while NativeUI takes a bare MusicMode
// parameter (top-level). The enum is nested (the canonical home) and this
// global alias makes the bare spelling resolve to the SAME type everywhere.
global using MusicMode = CompetitiveRounds.MusicEngine.MusicMode;

using System;
using System.Collections.Generic;
using System.Text;
using HarmonyLib;
using SoundImplementation;
using UnityEngine;
using UnityEngine.Audio;
using UnityEngine.Networking;

namespace CompetitiveRounds
{
    /// <summary>
    /// Custom music playback engine (ai-collab/music-feature design v2 as
    /// amended by v3; module-contracts.md is the binding surface).
    ///
    /// Architecture in one paragraph: an explicit MODE MACHINE with a single
    /// transition owner (Reconcile). Modes split into two OWNERSHIP CLASSES —
    /// engine-owned {Custom, MutedByChoice, Preview} and non-owned {Vanilla,
    /// Loading, Fault}. The invariant every edge honors [G5]: leaving the
    /// engine-owned class stops the plugin sources (success-checked; a
    /// throwing Stop is hard-silenced and terminates in durable Fault),
    /// releases the vanilla suppression prefixes, and RE-ENTERS vanilla music
    /// for the CURRENT context (menu → PlayMainMenu, round → PlayIngame(false),
    /// pick → PlayIngame(true)) — never waiting for vanilla's next natural
    /// call, because in the menu there may be none [F11]; a re-entry call
    /// that fails is retried from the tick until it lands [I1-residual].
    /// Loading is vanilla-audible ALWAYS, including when reached from Custom
    /// on playable-set loss.
    ///
    /// Vanilla interop facts this file depends on (scout-audio-engine.md, all
    /// decompile-verified): SoundMusicManager is SCENE-LOCAL (poll Instance
    /// identity; reacquire on change); PlayIngame(isCard:true) arrives EVERY
    /// FRAME during a pick (edge-dedupe); PlayIngame's first statement is
    /// PlayAmbience() and PlayMainMenu's is StopAmbience(), so a suppressing
    /// prefix must mirror those calls or ambience breaks; StopAllMusic() only
    /// kills MUSIC voices (ambience is keyed to the manager transform, not the
    /// music transform) and resets the replay-guard flags so vanilla restarts
    /// cleanly when we release.
    ///
    /// Timing is REALTIME everywhere (Time.unscaledDeltaTime /
    /// Time.realtimeSinceStartup) — TimeHandler.deltaTime crawls on the
    /// spectator seat (#332); Sonigon itself is realtime, so this matches the
    /// engine we are standing in for.
    /// </summary>
    internal static class MusicEngine
    {
        // ── contract enum (nested — CompetitiveUI.cs already references
        //    MusicEngine.MusicMode.Custom, so the nesting is load-bearing) ──

        internal enum MusicMode { Vanilla, Loading, Custom, MutedByChoice, Preview, Fault }

        private enum Ctx { Menu, Round, Pick }

        /// <summary>Track address: albumSku + track index. Sku
        /// MusicCatalog.VANILLA_SKU addresses the runtime-enumerated vanilla
        /// combat album.</summary>
        private struct TrackRef : IEquatable<TrackRef>
        {
            public string Sku;
            public int Idx;
            public TrackRef(string sku, int idx) { Sku = sku; Idx = idx; }
            public bool Equals(TrackRef o) => Idx == o.Idx && string.Equals(Sku, o.Sku, StringComparison.Ordinal);
            public override string ToString() => Sku + "/" + Idx;
        }

        private sealed class VanillaTrack
        {
            public string RawName;
            public string Title;
            public AudioClip Clip;
        }

        /// <summary>One loaded (or loading) disk clip. The UnityWebRequest is
        /// HELD for the life of the entry — DownloadHandlerAudioClip owns the
        /// clip it produced, so disposing the request could kill a clip
        /// mid-play. Clips load FULLY BUFFERED (streamAudio=false): the whole
        /// pack is ~26MB compressed, buffering removes the disk-IO underruns
        /// players reported as light skipping, and it makes AudioSource.time
        /// seeks exact for the seek bar. Static (survives host respawn) per
        /// the hazards list.</summary>
        private sealed class ClipEntry
        {
            public string Key;
            public UnityWebRequest Req;
            public AudioClip Clip;
            public bool Failed;
        }

        private sealed class PreviewSnapshot
        {
            public bool StopIntent, Paused, VanillaPreferred, ManualTakeover;
            public TrackRef? Current;
            public float ResumePositionSec;
        }

        /// <summary>ALL session playback state in ONE durable static object
        /// [F19]: a respawned host rehydrates from it, and the suppression
        /// prefixes read it while the host is mid-respawn. Nothing
        /// playback-related lives on the MonoBehaviour.</summary>
        private sealed class EngineState
        {
            public MusicMode mode = MusicMode.Vanilla;
            public bool suppress;                       // prefixes return false (skip vanilla) while true
            public Ctx ctx = Ctx.Menu;                  // last context observed by the prefixes
            public bool ctxDirty;

            // Fault machinery [G13]. faultPending is the prefix-latched flag —
            // a plain durable static field that survives respawns and scene
            // loads. It is consumed at ReconcileCore/Tick entry (faultDurable
            // published BEFORE pending clears [I7]) or by an explicit user
            // transport retry; faultDurable pins the desired mode at Fault
            // until such a retry.
            public volatile bool faultPending;
            public bool faultDurable;
            public string faultReason = "";
            // [I1-residual] a failed vanilla re-entry (manager mid-scene-load,
            // throwing Play*) is never claimed done: this flag arms a tick
            // retry that re-issues the context call until it lands. Durable
            // static — a durable Fault keeps retrying across host respawns.
            public bool vanillaReentryPending;

            // Transport intent [F14] — no sticky boolean latch; these inputs
            // are what Reconcile recomputes the mode from.
            public bool stopIntent;                     // Stop pressed (or playlist ran out with loop off)
            public bool paused;                         // PlayPause toggle while Custom
            public bool vanillaPreferred;               // the "Use vanilla music" first-class control
            public bool manualTakeover;                 // set by Play/Skip/PlayTrack, cleared by UseVanilla/session end

            // Queue / playback position.
            public List<TrackRef> queue = new List<TrackRef>();
            public int queueIndex = -1;
            public TrackRef? current;
            public float resumePositionSec;
            public bool currentStarted;
            public float currentStartedRt;
            public bool currentPrematureRetried;        // [I1] one in-place resume per track; a second premature stop = durable Fault
            public bool currentEnded;                   // [N6c] current's clip FINISHED — it is a queue cursor, not a playable: readiness must not count it and EnsureMainPlaying advances off it, never replays
            public bool mainPausedByUs;                 // Pause()d (menu park / preview / PlayPause) — NOT ended
            public float customSilentSinceRt = -1f;     // [R1/R2] realtime the engine entered "Custom, unpaused, nothing audible"; -1 = not in it. Bounds the forbidden state (see TickPlayback).
            public string queueSignature;               // selection+shuffle+broadcast fingerprint; null forces rebuild

            // Derived, refreshed by Reconcile (read by the side-effect-free
            // suppression decision, so they must stay plain cached bools).
            public bool selectionNonEmpty;
            public bool hasReadyTrack;
            public bool menuParked;                     // non-owned ONLY because the menu is uncovered; round entry resumes
            public MusicMode menuParkedMode = MusicMode.Vanilla; // [I18] the ownership class parked away (Custom/MutedByChoice)
            public bool menuSilenced;                   // [Batch-2 §3] menu-scoped MutedByChoice via MenuMusicMode="silent" (diagnostic)

            // Card-phase duck (isCard edges, realtime-smoothed).
            public bool duckWanted;
            public float duckLevel;

            // Preview (generation-fenced temporary owner [F13][G10]).
            public int previewGen;
            public TrackRef? previewTrack;
            public PreviewSnapshot previewSnapshot;
            public bool previewStarted;
            public float previewStartedRt;

            // Vanilla catalog (runtime-observed [F21][G14]).
            public List<VanillaTrack> vanillaTracks = new List<VanillaTrack>();
            public AudioClip menuThemeClip;
            public string menuThemeTitle = "";
            public int managerInstanceId;
            public string vanillaLogSignature = "";

            // Mixer routing.
            public AudioMixerGroup musicGroup;
            public bool mixerRouted;
            public float fallbackGain = 1f;
            public float fallbackRefreshRt = -999f;

            // Broadcast edge bookkeeping.
            public bool broadcastHeld;

            // Deselected-set cache (raw string → parsed set).
            public string deselectedRaw;
            public HashSet<string> deselected = new HashSet<string>(StringComparer.Ordinal);

            public bool everHosted;
        }

        private static readonly EngineState S = new EngineState();
        private static readonly Dictionary<string, ClipEntry> Clips = new Dictionary<string, ClipEntry>(StringComparer.Ordinal);
        private static readonly HashSet<string> OnceKeys = new HashSet<string>(StringComparer.Ordinal);
        private static readonly System.Random Rng = new System.Random();

        private static MusicEngineHost _host;
        private static bool _initialized;
        private static bool _patchDead;      // suppression prefixes failed to attach (#83) — engine may never own
        private static bool _quitting;
        private static bool _inReconcile;
        private static bool _reconcileQueued;
        private static string _reconcileQueuedReason;
        private static float _managerPollRt = -999f;
        private static float _loadingKickRt = -999f;
        private static float _reenterRetryRt = -999f;
        private static bool _lastMenuCovered;
        private static string _lastMenuModeSetting;
        private static bool _lastBroadcastPredicate;

        /// <summary>Set by MusicSuppressionPatch's [HarmonyCleanup] once the
        /// class patched without exception (the PoisonSync.PatchesLive
        /// pattern). Initialize verifies it (#83).</summary>
        internal static bool SuppressionPatchLive;

        private const string VANILLA_ARTIST = "Karl Flodin";
        private const string VANILLA_ALBUM = "ROUNDS OST";
        private const float DUCK_LPF_HZ = 900f;
        private const float OPEN_LPF_HZ = 22000f;
        private const float DUCK_VOLUME = 0.5f;
        private const float DUCK_SMOOTH_TAU = 0.2f;
        private const float PREVIEW_MAX_SECONDS = 45f;  // snippets are 30s; hard cap so a stalled stream can't hold Preview forever
        // [R1/R2] How long Custom may hold suppression with nothing audible
        // before the engine dislodges whatever is stuck. The legitimate window
        // is sub-frame (Custom is entered only with a ready track, and
        // EnsureMainPlaying starts it in the same call), so this is pure
        // headroom — generous enough that no healthy start can trip it, short
        // enough that an unattended broadcast seat never sits in silence.
        private const float CUSTOM_SILENCE_BOUND_SEC = 8f;

        // ── public contract surface ──────────────────────────────────────

        internal static MusicMode Mode => S.mode;

        /// <summary>Broadcast credit gate: the broadcast predicate holds AND a
        /// CUSTOM track is actually sounding right now.</summary>
        internal static bool BroadcastMusicLive
        {
            get
            {
                try
                {
                    var s = S;
                    if (!BroadcastPredicate() || s.mode != MusicMode.Custom || s.paused) return false;
                    if (!s.current.HasValue || IsVanillaSku(s.current.Value.Sku)) return false;
                    var h = _host;
                    return h != null && h.Main != null && h.Main.isPlaying;
                }
                catch { return false; }
            }
        }

        /// <summary>[N21] Exact truth for the Music tab's mode line: is the
        /// current MutedByChoice specifically the menu-silent rule (Reconcile's
        /// menu branch), as opposed to a user Stop? Lets NativeUI point at
        /// Settings only when Settings is actually the cause.</summary>
        internal static bool MenuSilencedNow
        {
            get { try { return S.menuSilenced; } catch { return false; } }
        }

        /// <summary>Bootstrap (Plugin.DoInitialize, after MusicAssets.Initialize
        /// so tier trees are resolved before any AudioSource exists).</summary>
        internal static void Initialize()
        {
            if (_initialized) return;
            _initialized = true;
            try
            {
                if (Plugin.modDisabled) { _patchDead = true; return; }
                // #83: a diag/suppression patch can silently fail to attach.
                // Without the prefixes the engine can never suppress, so it
                // must never enter an engine-owned mode (both owners would
                // play). Vanilla music is untouched either way — fail open.
                if (!SuppressionPatchLive)
                {
                    _patchDead = true;
                    Plugin.Log?.LogError("[MUSIC] suppression prefixes did NOT attach — custom music disabled this session (vanilla music untouched)");
                }
                try { Application.quitting += () => _quitting = true; } catch { }
                try { MusicEntitlements.Changed += OnEntitlementsChanged; } catch (Exception ex) { LogOnce("ent-sub", "[MUSIC] entitlement subscribe failed: " + ex.Message, true); }
                SpawnHost();
                // [I1] no host = no tick = no repair loop — never pretend.
                if (_host == null) EnterDurableFaultNoThrow("host-spawn-failed");
                Reconcile("initialize");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogError($"[MUSIC] Initialize failed: {ex.Message}");
            }
        }

        // ── selection ────────────────────────────────────────────────────

        internal static bool IsSelected(string albumSku, int trackIdx)
        {
            try { RefreshDeselectedCache(); return !S.deselected.Contains(albumSku + "/" + trackIdx); }
            catch { return true; }
        }

        internal static void SetSelected(string albumSku, int trackIdx, bool on)
        {
            try
            {
                RefreshDeselectedCache();
                string key = albumSku + "/" + trackIdx;
                bool changed = on ? S.deselected.Remove(key) : S.deselected.Add(key);
                if (!changed) return;
                PersistDeselected();
                S.queueSignature = null;
                Reconcile("selection-change");
            }
            catch (Exception ex) { LogOnce("setsel", "[MUSIC] SetSelected failed: " + ex.Message, true); }
        }

        /// <summary>[Batch-2 item 2] Album master toggle read: true when ANY of
        /// the album's tracks is selected (vanilla album = the combat tracks
        /// only; the menu theme is never selectable [G14]).</summary>
        internal static bool IsAlbumEnabled(string sku)
        {
            try
            {
                RefreshDeselectedCache();
                var s = S;
                int n = AlbumTrackCount(sku);
                for (int i = 0; i < n; i++)
                    if (!s.deselected.Contains(sku + "/" + i)) return true;
                return false;
            }
            catch { return true; }
        }

        /// <summary>[Batch-2 item 2] Album master toggle write: batch
        /// select/deselect EVERY track of the album — one persistence write +
        /// one Reconcile, never per-track (the per-track path would fire an
        /// engine transition per row).</summary>
        internal static void SetAlbumSelected(string sku, bool on)
        {
            try
            {
                RefreshDeselectedCache();
                var s = S;
                int n = AlbumTrackCount(sku);
                if (n <= 0) return;   // unknown sku / vanilla album not yet enumerated
                bool changed = false;
                for (int i = 0; i < n; i++)
                {
                    string key = sku + "/" + i;
                    if (on ? s.deselected.Remove(key) : s.deselected.Add(key)) changed = true;
                }
                if (!changed) return;
                PersistDeselected();
                s.queueSignature = null;
                Reconcile("album-toggle");
            }
            catch (Exception ex) { LogOnce("setalb", "[MUSIC] SetAlbumSelected failed: " + ex.Message, true); }
        }

        private static int AlbumTrackCount(string sku)
        {
            if (IsVanillaSku(sku)) return S.vanillaTracks.Count;
            var a = MusicCatalog.Get(sku);
            return (a != null && a.Tracks != null) ? a.Tracks.Length : 0;
        }

        // ── transport ────────────────────────────────────────────────────

        internal static void PlayPause()
        {
            if (!_initialized) return;
            try
            {
                ClearFaultForUserAction("PlayPause");   // [I7] preview-ending transports still retry Fault
                if (S.previewTrack.HasValue) { StopPreviewAndRestoreInternal("transport"); return; }
                var s = S;
                if (s.mode == MusicMode.Custom)
                {
                    s.paused = !s.paused;
                    if (s.paused) { if (!PauseMain()) EnterDurableFaultNoThrow("pause failed"); }   // [I1-residual]
                    else Reconcile("play-pause");
                    return;
                }
                s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.manualTakeover = true;
                // [N6c] resuming onto an ENDED current (loop-off run-out, or
                // a load-gap park) is a transport intent: walk on Skip-style —
                // wrap/fresh-cycle allowed — so Play after a playlist end
                // restarts the playlist instead of instantly re-running out.
                if (s.currentEnded) AdvanceToNext(userSkip: true);
                Reconcile("play");
            }
            catch (Exception ex) { LogOnce("pp", "[MUSIC] PlayPause failed: " + ex.Message, true); }
        }

        /// <summary>Deliberate silence: MutedByChoice (engine owns, plays
        /// nothing, suppression stays) — distinct from Fault [F14].</summary>
        internal static void Stop()
        {
            if (!_initialized) return;
            try
            {
                ClearFaultForUserAction("Stop");        // [I7] preview-ending transports still retry Fault
                if (S.previewTrack.HasValue) { StopPreviewAndRestoreInternal("stop"); return; }
                S.stopIntent = true; S.paused = false;
                Reconcile("stop");
            }
            catch (Exception ex) { LogOnce("stop", "[MUSIC] Stop failed: " + ex.Message, true); }
        }

        internal static void Skip()
        {
            if (!_initialized) return;
            try
            {
                if (S.previewTrack.HasValue) StopPreviewAndRestoreInternal("transport");
                ClearFaultForUserAction("Skip");
                var s = S;
                s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.manualTakeover = true;
                EnsureQueueCurrent();
                AdvanceToNext(userSkip: true);
                Reconcile("skip");
            }
            catch (Exception ex) { LogOnce("skip", "[MUSIC] Skip failed: " + ex.Message, true); }
        }

        /// <summary>Previous transport (wave-2 contract): more than 3s into
        /// the current track restarts it; otherwise steps back one queue
        /// entry (listed order, or the live shuffle cycle — dispersion, or
        /// broadcast album blocks), wrapping at the top.</summary>
        internal static void PlayPrevious()
        {
            if (!_initialized) return;
            try
            {
                if (S.previewTrack.HasValue) StopPreviewAndRestoreInternal("transport");
                ClearFaultForUserAction("PlayPrevious");
                var s = S;
                s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.manualTakeover = true;
                float pos = s.currentStarted ? CurrentMainTimeOr(s.resumePositionSec) : s.resumePositionSec;
                if (s.current.HasValue && pos > 3f)
                {
                    s.resumePositionSec = 0f;
                    s.currentPrematureRetried = false;
                    s.currentEnded = false;   // [N6c] deliberate restart of a finished track
                    bool seeked = false;
                    try
                    {
                        var h = _host;
                        if (h != null && h.Main != null && h.Main.isPlaying) { h.Main.time = 0f; seeked = true; }
                    }
                    catch { }
                    if (!seeked) { s.currentStarted = false; s.mainPausedByUs = false; }
                    Reconcile("previous-restart");
                    return;
                }
                EnsureQueueCurrent();
                AdvanceToPrevious();
                Reconcile("previous");
            }
            catch (Exception ex) { LogOnce("prev", "[MUSIC] PlayPrevious failed: " + ex.Message, true); }
        }

        internal static void PlayTrack(string albumSku, int trackIdx)
        {
            if (!_initialized) return;
            try
            {
                if (S.previewTrack.HasValue) StopPreviewAndRestoreInternal("transport");
                var t = new TrackRef(albumSku, trackIdx);
                if (!IsTrackKnown(t)) { Plugin.Log?.LogInfo($"[MUSIC] PlayTrack: unknown track {t}"); return; }
                if (!IsAlbumPlayable(albumSku)) { Plugin.Log?.LogInfo($"[MUSIC] PlayTrack refused — album not owned: {albumSku}"); return; }
                ClearFaultForUserAction("PlayTrack");
                // An explicit request is also an explicit retry for a clip
                // that previously failed to decode.
                if (!IsVanillaSku(albumSku))
                {
                    string key = t.ToString();
                    if (Clips.TryGetValue(key, out var e) && e.Failed) { DisposeEntry(e); Clips.Remove(key); }
                }
                var s = S;
                s.manualTakeover = true; s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.current = t; s.resumePositionSec = 0f; s.currentStarted = false; s.mainPausedByUs = false;
                s.currentPrematureRetried = false;
                s.currentEnded = false;   // [N6c] explicit selection — this current is a playable again
                s.queueSignature = null;
                Reconcile("play-track");
            }
            catch (Exception ex) { LogOnce("pt", "[MUSIC] PlayTrack failed: " + ex.Message, true); }
        }

        /// <summary>The first-class "Use vanilla music" reset [F14]: clears
        /// manual takeover (and every other intent, fault included) and holds
        /// the engine at Vanilla until the next explicit engine action
        /// (Play/Skip/PlayTrack).</summary>
        internal static void UseVanilla()
        {
            if (!_initialized) return;
            try
            {
                if (S.previewTrack.HasValue) StopPreviewAndRestoreInternal("transport");
                ClearFaultForUserAction("UseVanilla");
                var s = S;
                s.vanillaPreferred = true;
                s.manualTakeover = false; s.stopIntent = false; s.paused = false;
                Reconcile("use-vanilla");
            }
            catch (Exception ex) { LogOnce("uv", "[MUSIC] UseVanilla failed: " + ex.Message, true); }
        }

        internal static bool LoopEnabled
        {
            get { try { return Plugin.MusicLoop == null || Plugin.MusicLoop.Value; } catch { return true; } }
            set
            {
                try { if (Plugin.MusicLoop != null) Plugin.MusicLoop.Value = value; } catch { }
                Reconcile("loop-toggle");
            }
        }

        internal static bool ShuffleEnabled
        {
            get { try { return Plugin.MusicShuffle != null && Plugin.MusicShuffle.Value; } catch { return false; } }
            set
            {
                try { if (Plugin.MusicShuffle != null) Plugin.MusicShuffle.Value = value; } catch { }
                S.queueSignature = null;
                Reconcile("shuffle-toggle");
            }
        }

        // ── volume ───────────────────────────────────────────────────────

        /// <summary>Engine-local multiplier percent, 0..100 — any value is
        /// valid (the slider is continuous; VolumeUp/Down step ±10 from
        /// wherever the config sits, without snapping to a grid [I17]). A
        /// multiplier above 100 has no physical channel (AudioSource.volume
        /// clamps at 1 and the vanilla mixer already applies its own gain), so
        /// 100 is the vanilla-equivalent loudness ceiling.</summary>
        internal static int VolumeStepPercent
        {
            get { try { return Mathf.Clamp(Plugin.MusicVolume != null ? Plugin.MusicVolume.Value : 100, 0, 100); } catch { return 100; } }
        }

        internal static void VolumeUp() { SetVolume(VolumeStepPercent + 10); }
        internal static void VolumeDown() { SetVolume(VolumeStepPercent - 10); }

        /// <summary>Slider write (wave-2 contract): 0..100 clamped, persisted
        /// to Plugin.MusicVolume; the per-frame volume pass applies it live to
        /// both sources through the perceptual curve.</summary>
        internal static void SetVolumePercent(int p) { SetVolume(p); }

        private static void SetVolume(int pct)
        {
            // [I17] clamp WITHOUT flooring to the 10-grid: an off-grid config
            // value (e.g. 55) must step to 65/45, not 60/40.
            try { if (Plugin.MusicVolume != null) Plugin.MusicVolume.Value = Mathf.Clamp(pct, 0, 100); } catch { }
            // Applied by the per-frame volume pass; no Reconcile needed.
        }

        // ── now playing / position (wave-2 transport contract) ───────────

        /// <summary>True while audio is audibly sounding from the engine (a
        /// Custom track, or a preview snippet) — drives the play/pause icon.</summary>
        internal static bool IsPlayingNow
        {
            get
            {
                try
                {
                    var s = S;
                    var h = _host;
                    if (h == null) return false;
                    if (s.mode == MusicMode.Preview)
                        return s.previewStarted && h.Preview != null && h.Preview.isPlaying;
                    return s.mode == MusicMode.Custom && !s.paused
                        && h.Main != null && h.Main.isPlaying;
                }
                catch { return false; }
            }
        }

        /// <summary>Elapsed/duration of the current custom track for the seek
        /// line. TRUE only while the track is audibly playing or deliberately
        /// paused-with-current (PlayPause) — a STOPPED engine (MutedByChoice /
        /// Vanilla / Fault, all failing the mode gate) and a silently-dead
        /// source (the [J1] premature-stop window) return false even though
        /// resumePositionSec is retained for the resume, so the seek row
        /// blanks whenever "Nothing playing" would show [Batch-2 item 4].</summary>
        internal static bool TryGetPosition(out float elapsedSec, out float durationSec)
        {
            elapsedSec = 0f; durationSec = 0f;
            try
            {
                var s = S;
                var h = _host;
                if (h == null || h.Main == null) return false;
                if (s.mode != MusicMode.Custom || !s.current.HasValue || !s.currentStarted) return false;
                var m = h.Main;
                var clip = m.clip;
                if (clip == null || clip.length <= 0f) return false;
                // [Batch-2 item 4] the audibility gate: not sounding and not
                // deliberately paused = no position (a paused source keeps a
                // valid AudioSource.time, so the paused row still ticks).
                if (!m.isPlaying && !s.paused) return false;
                durationSec = clip.length;
                elapsedSec = Mathf.Clamp(m.time, 0f, durationSec);
                return true;
            }
            catch { elapsedSec = 0f; durationSec = 0f; return false; }
        }

        /// <summary>Seek the current track to fraction f (0..1) of its length.
        /// No-op when nothing is playing (contract). Buffered clips make the
        /// AudioSource.time write exact; works while paused too (the position
        /// is kept for the resume).</summary>
        internal static void SeekToFraction(float f01)
        {
            if (!_initialized) return;
            try
            {
                var s = S;
                var h = _host;
                if (h == null || h.Main == null) return;
                if (s.mode != MusicMode.Custom || !s.current.HasValue || !s.currentStarted) return;
                var m = h.Main;
                var clip = m.clip;
                if (clip == null || clip.length <= 0f) return;
                // Stay a hair short of the very end so a full-right drag reads
                // as a natural completion, never a premature stop [I1].
                float target = Mathf.Min(Mathf.Clamp01(f01) * clip.length, Mathf.Max(0f, clip.length - 0.05f));
                try { m.time = target; } catch { }
                s.resumePositionSec = target;
                s.currentEnded = false;   // [N6c] a seek onto a finished track is a deliberate replay-from-position
            }
            catch (Exception ex) { LogOnce("seek", "[MUSIC] SeekToFraction failed: " + ex.Message, true); }
        }

        /// <summary>"" contract [Batch-2 item 4]: empty EXACTLY when the seek
        /// row is hidden too (TryGetPosition false) so the UI can never render
        /// "Nothing playing" beside a live position — paused-with-current
        /// therefore names its track ("Paused: ..."). Preview stays the
        /// deliberate exception the other way (named, no seek row).</summary>
        internal static string NowPlayingLine()
        {
            try
            {
                if (TryGetNowPlaying(out var track, out var artist, out _))
                    return I18n.TrF("Now Playing: {0} - {1}", track, artist);
                var s = S;
                if (s.mode == MusicMode.Custom && s.paused && s.current.HasValue && s.currentStarted
                    && TryDescribeTrack(s.current.Value, out var ptrack, out var partist, out _))
                    return I18n.TrF("Paused: {0} - {1}", ptrack, partist);
                return "";
            }
            catch { return ""; }
        }

        /// <summary>True while a track is actually sounding (Custom playing, or
        /// a preview snippet). Silent modes — paused included — report false;
        /// NowPlayingLine layers the paused-with-current naming on top.</summary>
        internal static bool TryGetNowPlaying(out string track, out string artist, out string album)
        {
            track = ""; artist = ""; album = "";
            try
            {
                var s = S;
                TrackRef? audible = null;
                if (s.mode == MusicMode.Preview && s.previewTrack.HasValue && s.previewStarted) audible = s.previewTrack;
                else if (s.mode == MusicMode.Custom && !s.paused && s.current.HasValue && s.currentStarted) audible = s.current;
                if (!audible.HasValue) return false;
                return TryDescribeTrack(audible.Value, out track, out artist, out album);
            }
            catch { return false; }
        }

        /// <summary>Name resolution for one track ref (vanilla or catalog) —
        /// shared by the audible and paused-with-current display paths.</summary>
        private static bool TryDescribeTrack(TrackRef t, out string track, out string artist, out string album)
        {
            track = ""; artist = ""; album = "";
            if (IsVanillaSku(t.Sku))
            {
                var s = S;
                if (t.Idx < 0 || t.Idx >= s.vanillaTracks.Count) return false;
                track = s.vanillaTracks[t.Idx].Title; artist = VANILLA_ARTIST; album = VANILLA_ALBUM;
                return true;
            }
            var a = MusicCatalog.Get(t.Sku);
            if (a == null || a.Tracks == null || t.Idx < 0 || t.Idx >= a.Tracks.Length) return false;
            track = a.Tracks[t.Idx].Title; artist = a.ArtistName; album = a.AlbumName;
            return true;
        }

        // ── vanilla album introspection (UI) ─────────────────────────────

        internal static int VanillaTrackCount
        {
            get { try { return S.vanillaTracks.Count; } catch { return 0; } }
        }

        internal static string VanillaTrackTitle(int i)
        {
            try { return (i >= 0 && i < S.vanillaTracks.Count) ? S.vanillaTracks[i].Title : ""; }
            catch { return ""; }
        }

        internal static float VanillaTrackLength(int i)
        {
            try
            {
                if (i < 0 || i >= S.vanillaTracks.Count) return 0f;
                var c = S.vanillaTracks[i].Clip;
                return c != null ? c.length : 0f;
            }
            catch { return 0f; }
        }

        /// <summary>Menu theme accessor for the tab's menu-only row [G14]
        /// (enumerated separately from the combat album, never selectable).
        /// Contract addition — the row cannot render without it.</summary>
        // Name is agent D's reflection probe target in NativeUI (menu-theme row) — keep in lockstep.
        internal static bool TryGetVanillaMenuTheme(out string title, out float lengthSeconds)
        {
            title = ""; lengthSeconds = 0f;
            try
            {
                var s = S;
                if (s.menuThemeClip == null) return false;
                title = s.menuThemeTitle; lengthSeconds = s.menuThemeClip.length;
                return true;
            }
            catch { return false; }
        }

        // ── preview [F13][G10] ───────────────────────────────────────────

        internal static void TogglePreview(string albumSku, int trackIdx)
        {
            if (!_initialized || _patchDead) return;
            try
            {
                var s = S;
                var t = new TrackRef(albumSku, trackIdx);
                if (s.previewTrack.HasValue && s.previewTrack.Value.Equals(t)) { StopPreviewAndRestoreInternal("toggle"); return; }
                var album = MusicCatalog.Get(albumSku);
                if (album == null || IsVanillaSku(albumSku) || album.Tracks == null || trackIdx < 0 || trackIdx >= album.Tracks.Length)
                {
                    Plugin.Log?.LogInfo($"[MUSIC] TogglePreview: no preview for {albumSku}/{trackIdx}");
                    return;
                }
                s.previewGen++;
                if (!s.previewTrack.HasValue)
                {
                    // Entering Preview from a real owner: snapshot the INTENT,
                    // not the mode — restoration resubmits it through Reconcile
                    // which re-validates entitlement/readiness [G10].
                    s.previewSnapshot = new PreviewSnapshot
                    {
                        StopIntent = s.stopIntent,
                        Paused = s.paused,
                        VanillaPreferred = s.vanillaPreferred,
                        ManualTakeover = s.manualTakeover,
                        Current = s.current,
                        ResumePositionSec = s.currentStarted ? CurrentMainTimeOr(s.resumePositionSec) : s.resumePositionSec,
                    };
                }
                s.previewTrack = t;
                s.previewStarted = false;
                s.previewStartedRt = Time.realtimeSinceStartup;   // arm stamp: bounds the not-yet-started wait too
                StopPreviewSourceNoThrow();
                // Previews tier trigger (idempotent) + start the snippet load.
                string path = null;
                try { path = MusicAssets.PathFor(album.Tracks[trackIdx].PreviewFile); } catch { }
                if (path == null) { try { MusicAssets.EnsureTier(MusicTier.Previews, "preview"); } catch { } }
                else EnsureClipLoading("p:" + t, path);
                Reconcile("preview-start");
            }
            catch (Exception ex) { LogOnce("tp", "[MUSIC] TogglePreview failed: " + ex.Message, true); }
        }

        internal static bool IsPreviewing(string albumSku, int trackIdx)
        {
            try
            {
                var s = S;
                return s.mode == MusicMode.Preview && s.previewTrack.HasValue
                    && s.previewTrack.Value.Equals(new TrackRef(albumSku, trackIdx));
            }
            catch { return false; }
        }

        /// <summary>Generation-fenced, safe always (registered in the central
        /// persistent-surface teardown + tab switch). A call with no live
        /// preview only advances the generation, which is exactly the fence a
        /// stale async completion needs.</summary>
        internal static void StopPreviewAndRestore()
        {
            try { StopPreviewAndRestoreInternal("external"); }
            catch (Exception ex) { LogOnce("spr", "[MUSIC] StopPreviewAndRestore failed: " + ex.Message, true); }
        }

        private static void StopPreviewAndRestoreInternal(string why)
        {
            var s = S;
            s.previewGen++;                      // invalidates every in-flight completion
            StopPreviewSourceNoThrow();
            if (!s.previewTrack.HasValue) return;
            s.previewTrack = null;
            s.previewStarted = false;
            var snap = s.previewSnapshot;
            s.previewSnapshot = null;
            if (snap != null)
            {
                // Submit the saved INTENT through Reconcile — never reinstall
                // the saved mode [G10]. Reconcile re-validates entitlement and
                // readiness before acting on it.
                s.stopIntent = snap.StopIntent;
                s.paused = snap.Paused;
                s.vanillaPreferred = snap.VanillaPreferred;
                s.manualTakeover = snap.ManualTakeover;
                s.current = snap.Current;
                s.resumePositionSec = snap.ResumePositionSec;
                s.currentStarted = false; s.mainPausedByUs = false;
                s.currentPrematureRetried = false;
                // [N6c] currentEnded is deliberately PRESERVED across the
                // preview: a snapshot whose current had already finished must
                // ADVANCE on restore, never replay the finished clip.
            }
            Reconcile("preview-restore:" + why);
        }

        // ── Reconcile: the single transition owner ───────────────────────

        internal static void Reconcile(string reason)
        {
            if (!_initialized) return;
            if (_inReconcile)
            {
                // A nested call (e.g. a preview restore fired from inside a
                // transition) is deferred to the tick — one owner at a time.
                _reconcileQueued = true; _reconcileQueuedReason = reason;
                return;
            }
            _inReconcile = true;
            try { ReconcileCore(reason); }
            catch (Exception ex)
            {
                // A throwing reconcile must fail TOWARD vanilla, through the
                // single durable-fault funnel [I1].
                try { Plugin.Log?.LogError($"[MUSIC] Reconcile({reason}) threw: {ex}"); } catch { }
                EnterDurableFaultNoThrow("reconcile: " + ex.Message);
            }
            finally { _inReconcile = false; }
        }

        private static void ReconcileCore(string reason)
        {
            var s = S;
            // [I7] Consume a prefix-latched fault FIRST — faultDurable is
            // published BEFORE pending clears, so no callback-ordered path
            // (settings/tier/entitlement/selection/identity) can re-enter
            // Custom between the latch and the next tick.
            if (s.faultPending)
            {
                bool wasDurable = s.faultDurable;
                s.faultDurable = true;
                s.faultPending = false;
                if (!wasDurable)
                    Plugin.Log?.LogError($"[MUSIC] entering durable Fault ({s.faultReason}) — vanilla music active until an explicit retry");
            }
            TickBroadcastEdges();
            RefreshDerivedState();

            MusicMode desired = ComputeDesiredMode();

            // Menu rule, 3-state [Batch-2 item 1]: MenuMusicMode "custom"
            // covers the menu with the playlist (MenuCovered — the legacy
            // MenuMusicEnabled=true behavior); "vanilla" PARKS engine-owned
            // playback — vanilla menu music plays and the engine resumes at
            // the next in-game context; "silent" is a menu-scoped
            // MutedByChoice — the engine OWNS the menu with NOTHING playing
            // (the setting IS the deliberate intent, so the owned-silence
            // invariant holds), and leaving the menu re-derives the real mode,
            // releasing per [G5] when that mode is non-owned. The broadcast
            // predicate still covers the menu outright; Preview is exempt
            // (shop previews happen at the menu by design) and Fault/patch-
            // dead always fail open to audible vanilla, "silent" included.
            s.menuParked = false;
            s.menuParkedMode = MusicMode.Vanilla;
            s.menuSilenced = false;
            if (s.ctx == Ctx.Menu && !MenuCovered())
            {
                if (!_patchDead && MenuSilent()
                    && (desired == MusicMode.Custom || desired == MusicMode.MutedByChoice
                        || desired == MusicMode.Loading || desired == MusicMode.Vanilla))
                {
                    s.menuSilenced = true;
                    desired = MusicMode.MutedByChoice;
                }
                else if (desired == MusicMode.Custom || desired == MusicMode.MutedByChoice)
                {
                    s.menuParked = true;
                    s.menuParkedMode = desired;   // [I18] retain the parked ownership class for the prefix fast path
                    desired = MusicMode.Vanilla;
                }
            }

            if (desired != s.mode) TransitionTo(desired, reason);
            else EnforceModeInvariants();

            _lastMenuCovered = MenuCovered();
            _lastMenuModeSetting = MenuModeSetting();
        }

        private static MusicMode ComputeDesiredMode()
        {
            var s = S;
            if (_patchDead) return MusicMode.Vanilla;
            if (s.faultPending || s.faultDurable) return MusicMode.Fault;   // [I7] pending counts — never re-enter Custom under a latched fault
            if (s.previewTrack.HasValue) return MusicMode.Preview;

            if (BroadcastPredicate())
            {
                // Broadcast override: all custom tracks, ownership bypassed;
                // vanilla keeps playing until ≥1 custom track is validated AND
                // loaded [F17]. Stop stays honored as the operator's silencer.
                if (s.stopIntent) return MusicMode.MutedByChoice;
                return s.hasReadyTrack ? MusicMode.Custom : MusicMode.Loading;
            }

            if (s.stopIntent) return MusicMode.MutedByChoice;
            if (s.vanillaPreferred) return MusicMode.Vanilla;
            if (s.manualTakeover) return s.hasReadyTrack ? MusicMode.Custom : MusicMode.Loading;
            if (SelectionUniverseEmpty()) return MusicMode.Vanilla;          // nothing to manage — fail open
            if (!s.selectionNonEmpty) return MusicMode.MutedByChoice;        // user deselected everything: deliberate silence
            if (SelectionIsPureFullVanilla()) return MusicMode.Vanilla;      // engine output would be byte-identical vanilla
            return s.hasReadyTrack ? MusicMode.Custom : MusicMode.Loading;
        }

        private static bool IsEngineOwned(MusicMode m)
            => m == MusicMode.Custom || m == MusicMode.MutedByChoice || m == MusicMode.Preview;

        private static void TransitionTo(MusicMode desired, string reason)
        {
            var s = S;
            var prev = s.mode;
            bool fromOwned = IsEngineOwned(prev);
            bool toOwned = IsEngineOwned(desired);
            s.mode = desired;

            if (toOwned && !fromOwned)
            {
                // Suppression prefixes alone don't stop an already-playing
                // Sonigon event [F11] — kill the live voices first. Ambience
                // survives (it is keyed to the manager transform, not the
                // music transform) and our prefixes keep mirroring it.
                try { SoundMusicManager.Instance?.StopAllMusic(); }
                catch (Exception ex)
                {
                    // [I1] a failed acquisition must not proceed — both owners
                    // would play. Durable fault; vanilla keeps the room.
                    EnterDurableFaultNoThrow("acquire-stop: " + ex.Message);
                    return;
                }
                s.suppress = true;
                s.vanillaReentryPending = false;   // ownership acquired — a stale retry must never replay vanilla over us
                ApplyOwnedPlayback();
            }
            else if (fromOwned && !toOwned)
            {
                // [G5] ownership-release invariant: stop plugin sources,
                // release suppression, re-enter vanilla for the CURRENT
                // context. Loading is vanilla-audible ALWAYS, including when
                // reached from Custom on playable-set loss.
                // [I1-residual] cleanup success is load-bearing: a source
                // whose Stop threw is hard-silenced but no longer
                // trustworthy — durable Fault owns that terminal (it
                // releases suppression and arms the retried re-entry).
                if (!StopSources())
                {
                    s.mainPausedByUs = false; s.currentStarted = false;
                    EnterDurableFaultNoThrow("release-stop failed");
                    return;
                }
                s.mainPausedByUs = false; s.currentStarted = false;
                s.suppress = false;
                // Re-entry may fail RIGHT NOW (scene-load window) — arm the
                // tick retry instead of claiming it happened [I1-residual].
                s.vanillaReentryPending = !ReenterVanillaForContext();
            }
            else if (toOwned)
            {
                s.suppress = true;
                ApplyOwnedPlayback();
            }
            else
            {
                s.suppress = false;         // non-owned → non-owned: vanilla already audible
            }

            Plugin.Log?.LogInfo($"[MUSIC] mode {prev} -> {desired} ({reason}, ctx={s.ctx}{(s.menuParked ? ", parked" : s.menuSilenced ? ", menu-silent" : "")})");
        }

        /// <summary>Same-mode Reconcile: heal any suppress/ownership drift
        /// (e.g. a prefix fault released suppression and the fault was then
        /// user-cleared before the tick consumed it) and keep Custom fed.
        /// While a fault is PENDING or DURABLE this defers ENTIRELY [I7] —
        /// consumption at ReconcileCore/Tick entry owns that path, so
        /// enforcement can never restart custom audio over a vanilla call
        /// that escaped through a faulted prefix.</summary>
        private static void EnforceModeInvariants()
        {
            var s = S;
            if (s.faultPending || s.faultDurable) return;
            bool owned = IsEngineOwned(s.mode);
            if (owned && !s.suppress)
            {
                try { SoundMusicManager.Instance?.StopAllMusic(); }
                catch (Exception ex) { EnterDurableFaultNoThrow("reacquire-stop: " + ex.Message); return; }
                s.suppress = true;
            }
            if (!owned && s.suppress) s.suppress = false;
            if (s.mode == MusicMode.Custom) ApplyOwnedPlayback();
        }

        private static void ApplyOwnedPlayback()
        {
            var s = S;
            if (s.faultPending || s.faultDurable) return;   // [I7] never (re)start owned audio under a latched fault
            // [I1-residual] every cleanup below reports success; a failure
            // means the source is hard-silenced but its state is no longer
            // trustworthy — durable Fault owns the terminal.
            switch (s.mode)
            {
                case MusicMode.Custom:
                    StopPreviewSourceNoThrow();
                    if (s.paused) { if (!PauseMain()) EnterDurableFaultNoThrow("pause failed"); }
                    else EnsureMainPlaying();
                    break;
                case MusicMode.MutedByChoice:
                    if (!StopSources()) { EnterDurableFaultNoThrow("mute-stop failed"); return; }
                    s.mainPausedByUs = false; s.currentStarted = false;
                    break;
                case MusicMode.Preview:
                    // keep position; preview machinery drives the preview source
                    if (!PauseMain()) EnterDurableFaultNoThrow("preview-pause failed");
                    break;
            }
        }

        /// <summary>[F11] Immediately restore vanilla music for the context the
        /// prefixes last observed — vanilla's own replay guards make this
        /// idempotent, and our prefixes pass it through because suppression is
        /// already released when this is called. [I1-residual] SUCCESS IS
        /// RETURNED, never assumed: false (manager missing, or the Play* call
        /// threw) means vanilla was NOT restored — the caller arms
        /// vanillaReentryPending and the tick retries until a call lands.</summary>
        private static bool ReenterVanillaForContext()
        {
            try
            {
                var mgr = SoundMusicManager.Instance;
                if (mgr == null) return false;
                switch (S.ctx)
                {
                    case Ctx.Menu: mgr.PlayMainMenu(); break;
                    case Ctx.Round: mgr.PlayIngame(false); break;
                    case Ctx.Pick: mgr.PlayIngame(true); break;
                }
                return true;
            }
            catch (Exception ex)
            {
                LogOnce("reenter", "[MUSIC] vanilla re-entry failed: " + ex.Message + " — will retry from the tick", true);
                return false;
            }
        }

        // ── suppression prefix support (called by MusicSuppressionPatch) ──

        /// <summary>SIDE-EFFECT-FREE decision [F20]: pure reads of cached
        /// state. Returns true when a confident decision was made; any throw
        /// escapes to the prefix's catch, which latches FaultPending.</summary>
        internal static bool TryShouldSuppress(bool menuCall, out bool suppress)
        {
            suppress = false;
            var s = S;
            if (!_initialized || _patchDead) return true;
            if (s.faultPending || s.faultDurable) return true;   // fault = vanilla runs
            if (IsEngineOwned(s.mode))
            {
                // Park pass-through: vanilla menu plays — unless the menu mode
                // is "silent", which keeps suppression through menu calls (the
                // engine owns the menu with nothing playing) [Batch-2 item 1].
                if (menuCall && s.mode != MusicMode.Preview && !MenuCovered() && !MenuSilent()) return true;
                suppress = s.suppress;   // normally true; a mid-fault window reads false and lets vanilla through
                return true;
            }
            // [Batch-2 item 1] "silent" pre-ownership fast path: a menu call
            // can arrive before the tick's Reconcile has formalized the
            // menu-scoped MutedByChoice (startup, or a context change into the
            // menu while non-owned) — suppress it HERE so vanilla menu music
            // never blips in. Fault and patch-dead returned above, so a
            // suppressed call is always followed by the owning Reconcile
            // (NotePrefixContext just marked ctxDirty for the tick).
            if (menuCall && !MenuCovered() && MenuSilent()) { suppress = true; return true; }
            // Parked-at-menu fast path: the first in-game call after a menu
            // park is suppressed HERE so vanilla in-game music never blips in
            // the frame before the tick's Reconcile re-takes ownership. [I18]
            // the parked OWNERSHIP CLASS decides: parked MutedByChoice always
            // suppresses (silence is the point — stopIntent and empty
            // selection alike); parked Custom suppresses only while a track
            // is still ready, so a readiness loss cannot swallow the only
            // vanilla call of a Loading round.
            if (!menuCall && s.menuParked)
            {
                suppress = s.menuParkedMode == MusicMode.MutedByChoice
                        || (s.menuParkedMode == MusicMode.Custom && s.hasReadyTrack);
                return true;
            }
            return true;
        }

        /// <summary>Prefix bookkeeping (trivial field writes, no-throw by
        /// construction): context recording + the isCard duck edge —
        /// isCard:true arrives EVERY FRAME during a pick, so both are
        /// change-deduped.</summary>
        internal static void NotePrefixContext(bool menuCall, bool isCard)
        {
            var s = S;
            var c = menuCall ? Ctx.Menu : (isCard ? Ctx.Pick : Ctx.Round);
            if (s.ctx != c) { s.ctx = c; s.ctxDirty = true; }
            // [I14] menu entry clears any stale pick-phase duck — a disconnect
            // can jump Pick→Menu without ever seeing an isCard:false edge.
            if (menuCall) { if (s.duckWanted) s.duckWanted = false; }
            else if (s.duckWanted != isCard) s.duckWanted = isCard;
        }

        /// <summary>Menu call passed through while we were audible (menu not
        /// covered): pause our main source in the SAME call so no frame has
        /// both owners playing; the tick's Reconcile then parks properly.
        /// [I1-residual] a FAILED pause here is the both-owners hazard — the
        /// vanilla call we are inside resumes this same frame. PauseMain
        /// already hard-silenced (mute + volume 0 + Stop retry); latch the
        /// fault so the next tick publishes durable Fault. The latch (not
        /// EnterDurableFaultNoThrow) is deliberate: vanilla is taking the
        /// room through THIS very call, so no re-entry is needed — and
        /// issuing one from inside PlayMainMenu's own prefix would recurse.</summary>
        internal static void NoteVanillaMenuHandoffNoThrow()
        {
            try
            {
                var s = S;
                if (s.mode == MusicMode.Custom && !s.paused && !PauseMain())
                {
                    s.faultReason = "menu-handoff-pause failed";
                    s.suppress = false;
                    s.faultPending = true;
                    if (OnceKeys.Add("handoff-fault"))
                        Plugin.Log?.LogError("[MUSIC] menu-handoff pause failed — source hard-silenced, engine faulting");
                }
            }
            catch { }
        }

        /// <summary>[G13] The prefix exception path: latch FaultPending
        /// (durable static — survives host respawns; consumed at
        /// ReconcileCore/Tick entry, where faultDurable is published BEFORE
        /// pending clears [I7]), release suppression, stop BOTH plugin
        /// sources via no-throw paths (a throwing Stop is hard-silenced in
        /// place: mute + volume 0 + Stop retry [I1-residual]), and let the
        /// caller return true so vanilla runs. Owned-playback enforcement
        /// defers while a fault is pending, so the escaped vanilla call
        /// cannot be overplayed by a custom restart.</summary>
        internal static void LatchFaultFromPrefix(string site, Exception ex)
        {
            try
            {
                var s = S;
                s.faultReason = site + ": " + (ex != null ? ex.Message : "unknown");
                s.suppress = false;
                StopSourcesNoThrow();
                s.faultPending = true;
                if (OnceKeys.Add("prefix-fault"))
                    Plugin.Log?.LogError($"[MUSIC] suppression prefix threw at {site} — vanilla restored, engine faulting: {ex}");
            }
            catch { }
        }

        /// <summary>[I1] The single durable-fault funnel for every owned
        /// playback, transition, or host failure — no-throw by construction.
        /// Publishes durable Fault (BEFORE clearing pending [I7]), silences
        /// both plugin sources (a throwing Stop is hard-silenced: mute +
        /// volume 0 + Stop retry), releases suppression, and REQUESTS
        /// context-correct vanilla re-entry — a failed request arms
        /// vanillaReentryPending and the tick retries it until a call lands
        /// [I1-residual]; the fault never claims vanilla was restored once.
        /// Recovery is ONLY the explicit user retry (ClearFaultForUserAction)
        /// — no automatic reacquisition.</summary>
        private static void EnterDurableFaultNoThrow(string reason)
        {
            try
            {
                var s = S;
                s.faultDurable = true;
                s.faultPending = false;
                s.faultReason = reason;
                StopSourcesNoThrow();
                s.suppress = false;
                s.mode = MusicMode.Fault;
                s.mainPausedByUs = false; s.currentStarted = false;
                s.vanillaReentryPending = !ReenterVanillaForContext();
                Plugin.Log?.LogError($"[MUSIC] durable Fault ({reason}) — vanilla re-entry {(s.vanillaReentryPending ? "pending (tick retries)" : "issued")}; custom music waits for an explicit retry");
            }
            catch { }
        }

        // ── engine tick (host Update — BepInEx never calls Plugin.Update) ─

        internal static void Tick()
        {
            if (!_initialized) return;
            try
            {
                var s = S;
                float rt = Time.realtimeSinceStartup;

                // FaultPending consumption [G13][I7]: ReconcileCore's first
                // act publishes durable Fault (BEFORE clearing pending) —
                // this call just routes there at tick entry.
                if (s.faultPending) Reconcile("fault-latched");

                if (_reconcileQueued) { _reconcileQueued = false; Reconcile(_reconcileQueuedReason ?? "queued"); }

                // [I1-residual] vanilla re-entry RETRY: a release/fault whose
                // context call failed (manager mid-scene-load, throwing Play*)
                // is re-issued here until it lands — durable Fault included.
                // Gated on the non-owned class with suppression released so a
                // stale pending can never replay vanilla over custom audio;
                // vanilla's replay guards make a redundant call a no-op.
                if (s.vanillaReentryPending && !IsEngineOwned(s.mode) && !s.suppress
                    && rt - _reenterRetryRt > 0.5f)
                {
                    _reenterRetryRt = rt;
                    if (ReenterVanillaForContext()) s.vanillaReentryPending = false;
                }

                // Manager identity poll: SoundMusicManager is scene-local.
                if (rt - _managerPollRt > 0.5f)
                {
                    _managerPollRt = rt;
                    PollManagerIdentity();
                    // Menu-cover inputs can change outside Reconcile (config
                    // edit / cfg-lever reload); re-evaluate on the edge. The
                    // 3-state menu mode gets its OWN edge — a vanilla→silent
                    // flip at a parked menu changes neither MenuCovered nor
                    // any other reconcile input [Batch-2 item 1].
                    if (MenuCovered() != _lastMenuCovered) Reconcile("menu-cover-change");
                    else if (!string.Equals(MenuModeSetting(), _lastMenuModeSetting, StringComparison.Ordinal))
                        Reconcile("menu-mode-change");
                }

                if (TickBroadcastEdges()) Reconcile("broadcast-edge");

                if (s.ctxDirty) { s.ctxDirty = false; Reconcile("context-change"); }

                // Loading is edge-poor: a tier that finishes installing fires
                // no event, so the load kicks are re-polled until readiness
                // flips (which IS an edge and reconciles below).
                if (s.mode == MusicMode.Loading && rt - _loadingKickRt > 1f)
                {
                    _loadingKickRt = rt;
                    EnsureQueueCurrent();
                    KickLoadsForQueueHead();
                }

                PumpClipLoads();

                // Readiness-only changes still reconcile [G5].
                bool ready = ScanHasReadyTrack();
                if (ready != s.hasReadyTrack) { s.hasReadyTrack = ready; Reconcile("readiness-change"); }

                TickPlayback(rt);
                TickDuckAndVolume(rt);
            }
            catch (Exception ex)
            {
                // [I1] an exception escaping the tick while the engine owns
                // playback (or still holds suppression) must not leave owned
                // silence over a suppressed vanilla — durable fault.
                if (IsEngineOwned(S.mode) || S.suppress) EnterDurableFaultNoThrow("tick: " + ex.Message);
                else LogOnce("tick", "[MUSIC] tick failed: " + ex.Message, true);
            }
        }

        private static void TickPlayback(float rt)
        {
            var s = S;
            var h = _host;
            if (h == null) return;

            // [R1/R2] The silence bound is armed ONLY while Custom actually
            // holds suppression. Clearing it on every other mode (and while
            // paused) means a stale stamp from an earlier Custom stretch can
            // never fire the moment Custom is re-entered.
            if (s.mode != MusicMode.Custom || s.paused || s.mainPausedByUs)
                s.customSilentSinceRt = -1f;

            if (s.mode == MusicMode.Custom && !s.paused && !s.mainPausedByUs)
            {
                var m = h.Main;
                // [J1] A STARTED-but-silent source is judged HERE and nowhere
                // else, and the branch comes FIRST: falling through to
                // EnsureMainPlaying would blind-replay and re-stamp
                // currentStartedRt, renewing the 0.5s grace forever (silent
                // Custom under held suppression, unbounded — never Fault).
                if (m != null && s.current.HasValue && s.currentStarted && !m.isPlaying)
                {
                    // Grace interval: an AudioSource can report !isPlaying for
                    // a few frames right after Play(). WAIT — no replay, no
                    // timestamp reset — so repeated early stops still expire.
                    if (rt - s.currentStartedRt <= 0.5f) return;
                    // [I1][J1] grace expired — classify by the last position
                    // observed while playing: well short of the clip's end
                    // means the source died mid-track (device fault / external
                    // teardown) — exactly ONE counted resume attempt
                    // (currentPrematureRetried); any further started-but-
                    // silent expiry is durable Fault. At/near the end →
                    // normal advance.
                    var clip = m.clip;
                    if (clip != null && s.resumePositionSec < clip.length - 2f)
                    {
                        if (!s.currentPrematureRetried)
                        {
                            s.currentPrematureRetried = true;
                            s.currentStarted = false;   // EnsureMainPlaying resumes from resumePositionSec
                            Plugin.Log?.LogWarning($"[MUSIC] main source stopped prematurely at {s.resumePositionSec:F1}s of {clip.length:F1}s — attempting one resume");
                            EnsureMainPlaying();
                        }
                        else EnterDurableFaultNoThrow("premature-stop at " + s.resumePositionSec.ToString("F1") + "s");
                    }
                    // Natural track end → advance (shuffle-cycle aware).
                    // [N6c] Mark the end BEFORE the advance: when nothing is
                    // ready yet, the finished clip must read as a cursor, not
                    // a "ready" track — counting it kept desired-mode at
                    // Custom with nothing playing (suppressed silence = dead
                    // air on the broadcast stream) until another load landed.
                    // A successful advance clears the flag in AdoptCurrent.
                    else
                    {
                        s.currentEnded = true;
                        if (AdvanceToNext(userSkip: false)) { s.currentStarted = false; EnsureMainPlaying(); }
                        else Reconcile(s.stopIntent ? "playlist-end" : "no-ready-track");
                    }
                }
                else
                {
                    EnsureMainPlaying();
                    if (m != null && m.isPlaying)
                    {
                        s.resumePositionSec = m.time;
                        s.customSilentSinceRt = -1f;
                    }
                    else
                    {
                        // [R1/R2] BOUNDED SILENT OWNERSHIP — the guarantee this
                        // subsystem was missing. Custom mode SUPPRESSES vanilla,
                        // so "Custom, unpaused, nothing audible" is the forbidden
                        // state the design names outright; the preview path
                        // already bounds its own version of it (12s
                        // preview-load-timeout above) and this path did not.
                        //
                        // Normally this window is sub-frame: Custom is only
                        // entered when a ready track exists, and EnsureMainPlaying
                        // starts it inside the very call above. It persists only
                        // when the current entry can NEVER resolve — a terminally
                        // failed current that traversal will not move off (r4 R1),
                        // or an exhaustion that published stopIntent without a
                        // mode recompute (r4 R2) — and in both the readiness scan
                        // stays true, so no edge ever fires again and the silence
                        // is unbounded on an unattended broadcast seat.
                        //
                        // Four review rounds each found a NEW route into this one
                        // state, so this bounds the STATE instead of enumerating
                        // routes (#389): mark the stuck entry ended so traversal
                        // must move off it, then force a mode recompute. Worst
                        // case it costs one track; it cannot hold silence.
                        if (s.customSilentSinceRt < 0f) s.customSilentSinceRt = rt;
                        else if (rt - s.customSilentSinceRt > CUSTOM_SILENCE_BOUND_SEC)
                        {
                            s.customSilentSinceRt = -1f;
                            Plugin.Log?.LogWarning(
                                $"[MUSIC] Custom held with no audio for {CUSTOM_SILENCE_BOUND_SEC:F0}s — dislodging"
                                + $" (current={(s.current.HasValue ? s.current.Value.ToString() : "none")}, stopIntent={s.stopIntent})");
                            if (s.current.HasValue) s.currentEnded = true;
                            if (AdvanceToNext(userSkip: false)) { s.currentStarted = false; EnsureMainPlaying(); }
                            else Reconcile(s.stopIntent ? "playlist-end" : "custom-silence-bound");
                        }
                    }
                }
            }
            else if (s.mode == MusicMode.Preview && s.previewTrack.HasValue)
            {
                var p = h.Preview;
                int gen = s.previewGen;
                if (!s.previewStarted)
                {
                    // A preview that cannot start (previews tier missing /
                    // download stalled) must not hold silent ownership
                    // unbounded — the menu music it displaced comes back.
                    if (rt - s.previewStartedRt > 12f) { StopPreviewAndRestoreInternal("preview-load-timeout"); return; }
                    var key = "p:" + s.previewTrack.Value;
                    if (Clips.TryGetValue(key, out var e))
                    {
                        if (e.Failed) { StopPreviewAndRestoreInternal("preview-load-failed"); return; }
                        if (e.Clip != null && p != null && gen == s.previewGen)
                        {
                            p.clip = e.Clip;
                            try { p.mute = false; } catch { }   // undo any hard-silence fallback
                            try { p.time = 0f; } catch { }
                            p.Play();
                            s.previewStarted = true;
                            s.previewStartedRt = rt;
                        }
                    }
                    else
                    {
                        // Path became available after EnsureTier finished.
                        var album = MusicCatalog.Get(s.previewTrack.Value.Sku);
                        if (album != null && album.Tracks != null && s.previewTrack.Value.Idx < album.Tracks.Length)
                        {
                            string path = null;
                            try { path = MusicAssets.PathFor(album.Tracks[s.previewTrack.Value.Idx].PreviewFile); } catch { }
                            if (path != null) EnsureClipLoading(key, path);
                        }
                    }
                }
                else if ((p != null && !p.isPlaying && rt - s.previewStartedRt > 0.5f)
                         || rt - s.previewStartedRt > PREVIEW_MAX_SECONDS)
                {
                    StopPreviewAndRestoreInternal("preview-end");
                }
            }
        }

        private static void TickDuckAndVolume(float rt)
        {
            var s = S;
            var h = _host;
            if (h == null) return;

            // Card-phase duck: LPF + volume dip, realtime-smoothed (#332 —
            // never TimeHandler.deltaTime; the spectator seat's clock crawls).
            float target = (s.duckWanted && s.mode == MusicMode.Custom && !s.paused) ? 1f : 0f;
            float dt = Time.unscaledDeltaTime;
            if (dt > 0f)
            {
                float k = 1f - Mathf.Exp(-dt / DUCK_SMOOTH_TAU);
                s.duckLevel = Mathf.Lerp(s.duckLevel, target, k);
            }
            if (Mathf.Abs(s.duckLevel - target) < 0.01f) s.duckLevel = target;

            // Volume-curve fallback refresh (mixer group unavailable): the
            // player can move the vanilla sliders at any time.
            if (!s.mixerRouted && rt - s.fallbackRefreshRt > 1f)
            {
                s.fallbackRefreshRt = rt;
                s.fallbackGain = ComputeFallbackGain();
            }

            // Perceptual volume: gain = (percent/100)² approximates
            // equal-loudness steps, so mid-slider is audibly mid-volume
            // instead of near-full — composes with the duck below.
            float pctFrac = VolumeStepPercent / 100f;
            float mult = pctFrac * pctFrac;
            float baseGain = s.mixerRouted ? 1f : s.fallbackGain;
            var m = h.Main;
            if (m != null) m.volume = mult * baseGain * Mathf.Lerp(1f, DUCK_VOLUME, s.duckLevel);
            var p = h.Preview;
            if (p != null) p.volume = mult * baseGain;
            var lpf = h.Lpf;
            if (lpf != null)
            {
                bool wantFilter = s.duckLevel > 0.02f;
                if (lpf.enabled != wantFilter) lpf.enabled = wantFilter;
                if (wantFilter) lpf.cutoffFrequency = Mathf.Lerp(OPEN_LPF_HZ, DUCK_LPF_HZ, s.duckLevel);
            }
        }

        // ── broadcast [§7] ───────────────────────────────────────────────

        private static bool BroadcastPredicate()
        {
            try { return BroadcastMode.IsBroadcastIdentity && Plugin.BroadcastCustomMusic != null && Plugin.BroadcastCustomMusic.Value; }
            catch { return false; }
        }

        /// <summary>Returns true on a predicate EDGE (the tick then reconciles;
        /// a call from inside Reconcile is already reconciling).</summary>
        private static bool TickBroadcastEdges()
        {
            bool now = BroadcastPredicate();
            if (now == _lastBroadcastPredicate)
            {
                if (now && !S.broadcastHeld) { try { S.broadcastHeld = RunInBackgroundLease.Acquire("broadcast-music"); } catch { } }
                // [I2-residual] the falling-edge Release can fail too — this
                // steady-state branch is what actually retries it: every tick
                // while the predicate stays false and the flag is still held.
                else if (!now && S.broadcastHeld) { try { if (RunInBackgroundLease.Release("broadcast-music")) S.broadcastHeld = false; } catch { } }
                return false;
            }
            _lastBroadcastPredicate = now;
            S.queueSignature = null;    // selection override flips with the predicate
            if (now)
            {
                // Identity resolution: full-tier bootstrap + the background
                // lease so menu/idle playback ticks while unfocused [F18].
                try { if (!MusicAssets.TierReady(MusicTier.Full)) MusicAssets.EnsureTier(MusicTier.Full, "broadcast-identity"); } catch { }
                try { S.broadcastHeld = RunInBackgroundLease.Acquire("broadcast-music"); } catch { }
                Plugin.Log?.LogInfo("[MUSIC] broadcast custom-music predicate ON");
            }
            else if (S.broadcastHeld)
            {
                // [I2] clear held ONLY on a successful restore — a failed
                // release keeps the flag, and the STEADY-STATE (no-edge)
                // branch above retries the Release on every subsequent tick
                // until it lands (this edge branch runs only once per flip).
                try { if (RunInBackgroundLease.Release("broadcast-music")) S.broadcastHeld = false; } catch { }
                Plugin.Log?.LogInfo("[MUSIC] broadcast custom-music predicate OFF");
            }
            RepairAfterBroadcastEdge(now);
            return true;
        }

        /// <summary>[I8] Centralized predicate-edge repair, run on BOTH edges.
        /// A rising edge ends any preview (broadcast bootstrap must win
        /// desired-mode priority; the generation fence kills in-flight
        /// completions). Then the current track is kept on exactly ONE test:
        /// STRICT membership in the NEW effective queue. Manual takeover may
        /// keep a current across SELECTION changes, never across a predicate
        /// edge — Skip always sets takeover, so honoring it here would let an
        /// owned-but-deselected broadcast pick keep playing (and keep
        /// claiming broadcast credit) after the lease fell. A non-member is
        /// stopped and cleared so it can neither keep playing nor count as
        /// ready.</summary>
        private static void RepairAfterBroadcastEdge(bool rising)
        {
            var s = S;
            // [K3] BOTH edges end any live preview before the strict repair:
            // the preview snapshot carries a saved current that its completion
            // would otherwise restore AFTER this one-shot repair has passed —
            // e.g. a broadcast-only track surviving into the post-broadcast
            // queue. Restoration submits intent through Reconcile, which
            // re-validates against the post-edge universe, so ending the
            // preview here is sufficient to fence the snapshot.
            if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal(rising ? "broadcast-rising" : "broadcast-falling");
            else s.previewGen++;
            EnsureQueueCurrent();
            if (!s.current.HasValue) return;
            // [I8-residual] EnsureQueueCurrent just rebuilt against the new
            // effective universe (the edge nulled queueSignature); a located
            // index IS the strict-membership verdict — no takeover carve-out.
            if (s.queueIndex >= 0) return;
            StopMainNoThrow();
            s.current = null; s.resumePositionSec = 0f; s.currentStarted = false;
            s.mainPausedByUs = false; s.currentPrematureRetried = false;
            s.currentEnded = false;
            s.queueIndex = -1;
        }

        // ── selection / queue ────────────────────────────────────────────

        private static bool IsVanillaSku(string sku)
            => string.Equals(sku, MusicCatalog.VANILLA_SKU, StringComparison.Ordinal);

        private static bool IsAlbumPlayable(string sku)
        {
            if (IsVanillaSku(sku)) return S.vanillaTracks.Count > 0;
            if (BroadcastPredicate()) return MusicCatalog.Get(sku) != null;   // ownership bypass [F17]
            try { return MusicEntitlements.Owns(sku); } catch { return false; }
        }

        private static bool IsTrackKnown(TrackRef t)
        {
            if (IsVanillaSku(t.Sku)) return t.Idx >= 0 && t.Idx < S.vanillaTracks.Count;
            var a = MusicCatalog.Get(t.Sku);
            return a != null && a.Tracks != null && t.Idx >= 0 && t.Idx < a.Tracks.Length;
        }

        private static bool SelectionUniverseEmpty()
        {
            if (S.vanillaTracks.Count > 0) return false;
            var albums = MusicCatalog.Albums;
            if (albums != null)
                for (int i = 0; i < albums.Length; i++)
                    if (albums[i] != null && IsAlbumPlayable(albums[i].Sku)) return false;
            return true;
        }

        private static bool SelectionIsPureFullVanilla()
        {
            var s = S;
            if (s.vanillaTracks.Count == 0) return false;
            RefreshDeselectedCache();
            for (int i = 0; i < s.vanillaTracks.Count; i++)
                if (s.deselected.Contains(MusicCatalog.VANILLA_SKU + "/" + i)) return false;
            var albums = MusicCatalog.Albums;
            if (albums != null)
            {
                for (int i = 0; i < albums.Length; i++)
                {
                    var a = albums[i];
                    if (a == null || a.Tracks == null || !IsAlbumPlayable(a.Sku)) continue;
                    for (int j = 0; j < a.Tracks.Length; j++)
                        if (!s.deselected.Contains(a.Sku + "/" + j)) return false;   // a custom track is selected
                }
            }
            return true;
        }

        private static List<TrackRef> BuildEffectiveSelection()
        {
            var list = new List<TrackRef>();
            var s = S;
            if (BroadcastPredicate())
            {
                // Override: ALL custom album tracks, never vanilla, deselected
                // set ignored [F17]. Holds across predicate EDGES too —
                // RepairAfterBroadcastEdge stops/clears any stale current [I8].
                var albums = MusicCatalog.Albums;
                if (albums != null)
                    for (int i = 0; i < albums.Length; i++)
                    {
                        var a = albums[i];
                        if (a == null || a.Tracks == null) continue;
                        for (int j = 0; j < a.Tracks.Length; j++) list.Add(new TrackRef(a.Sku, j));
                    }
                return list;
            }
            RefreshDeselectedCache();
            for (int i = 0; i < s.vanillaTracks.Count; i++)
                if (!s.deselected.Contains(MusicCatalog.VANILLA_SKU + "/" + i))
                    list.Add(new TrackRef(MusicCatalog.VANILLA_SKU, i));
            var albums2 = MusicCatalog.Albums;
            if (albums2 != null)
                for (int i = 0; i < albums2.Length; i++)
                {
                    var a = albums2[i];
                    if (a == null || a.Tracks == null || !IsAlbumPlayable(a.Sku)) continue;
                    for (int j = 0; j < a.Tracks.Length; j++)
                        if (!s.deselected.Contains(a.Sku + "/" + j))
                            list.Add(new TrackRef(a.Sku, j));
                }
            return list;
        }

        // Broadcast forces the SELECTION override only [F17] — shuffle and
        // loop follow the persisted user settings on every seat (owner
        // ruling: the forced broadcast shuffle made Skip appear to shuffle
        // with shuffle off).
        private static bool ShuffleEffective() => ShuffleEnabled;
        private static bool LoopEffective() => LoopEnabled;

        private static void RefreshDerivedState()
        {
            var s = S;
            EnsureQueueCurrent();
            s.selectionNonEmpty = s.queue.Count > 0;
            s.hasReadyTrack = ScanHasReadyTrack();
            // Tier triggers for a selection that wants files we don't hold.
            if (s.selectionNonEmpty && !s.hasReadyTrack) KickLoadsForQueueHead();
        }

        private static void EnsureQueueCurrent()
        {
            var s = S;
            string sig = ComputeQueueSignature();
            if (s.queueSignature == sig) return;
            s.queueSignature = sig;
            var sel = BuildEffectiveSelection();
            s.queue = BuildQueueOrder(sel, s.current);
            s.queueIndex = s.current.HasValue ? s.queue.FindIndex(t => t.Equals(s.current.Value)) : -1;
        }

        private static string ComputeQueueSignature()
        {
            var s = S;
            RefreshDeselectedCache();
            var sb = new StringBuilder();
            sb.Append(BroadcastPredicate() ? "B|" : "n|").Append(ShuffleEffective() ? "S|" : "l|");
            sb.Append(s.vanillaTracks.Count).Append('|').Append(s.deselectedRaw ?? "");
            var albums = MusicCatalog.Albums;
            if (albums != null)
                for (int i = 0; i < albums.Length; i++)
                    if (albums[i] != null && IsAlbumPlayable(albums[i].Sku)) sb.Append('|').Append(albums[i].Sku);
            return sb.ToString();
        }

        /// <summary>Queue order for one cycle from the effective selection.
        /// Shuffle off = the selection's own order (album-major, catalog
        /// album order — BuildEffectiveSelection iterates albums then track
        /// indices). Shuffle on: the BROADCAST queue plays ALBUM-MAJOR BLOCKS
        /// (owner: albums have different vibes — never intermingle them), so
        /// only the block ORDER shuffles; every other seat keeps the
        /// per-track dispersion cycle [Batch-2 item 3]. Skip/Previous walk
        /// whatever order this built; loop wraps it.</summary>
        private static List<TrackRef> BuildQueueOrder(List<TrackRef> sel, TrackRef? avoid)
        {
            if (!ShuffleEffective()) return sel;
            return BroadcastPredicate() ? BuildAlbumBlockCycle(sel, avoid) : BuildDispersionCycle(sel, avoid);
        }

        /// <summary>[Batch-2 item 3] Album-major block cycle for the broadcast
        /// queue: tracks keep their in-album order (grouping preserves the
        /// selection's relative order, which IS the album order); the block
        /// order is Fisher-Yates-shuffled per cycle, and a fresh cycle never
        /// opens with the album that just finished (when more than one album
        /// is in play — mirrors the dispersion cycle's avoidFirst rule).</summary>
        private static List<TrackRef> BuildAlbumBlockCycle(List<TrackRef> sel, TrackRef? avoidFirstAlbum)
        {
            var result = new List<TrackRef>(sel.Count);
            if (sel.Count == 0) return result;
            var groups = new Dictionary<string, List<TrackRef>>(StringComparer.Ordinal);
            var order = new List<string>();
            foreach (var t in sel)
            {
                if (!groups.TryGetValue(t.Sku, out var g)) { g = new List<TrackRef>(); groups[t.Sku] = g; order.Add(t.Sku); }
                g.Add(t);
            }
            for (int i = order.Count - 1; i > 0; i--)       // Fisher-Yates over the BLOCKS
            {
                int j = Rng.Next(i + 1);
                var tmp = order[i]; order[i] = order[j]; order[j] = tmp;
            }
            if (order.Count > 1 && avoidFirstAlbum.HasValue
                && string.Equals(order[0], avoidFirstAlbum.Value.Sku, StringComparison.Ordinal))
            {
                int mid = order.Count / 2;
                var tmp = order[0]; order[0] = order[mid]; order[mid] = tmp;
            }
            foreach (var sku in order) result.AddRange(groups[sku]);
            return result;
        }

        /// <summary>Spotify-style dispersion shuffle: per cycle, each album's
        /// tracks are spread near slot i*n/k with jitter; no repeat within a
        /// cycle (each track appears once by construction); the first track of
        /// a new cycle is never the last of the previous one.</summary>
        private static List<TrackRef> BuildDispersionCycle(List<TrackRef> sel, TrackRef? avoidFirst)
        {
            int n = sel.Count;
            if (n <= 1) return new List<TrackRef>(sel);
            var groups = new Dictionary<string, List<TrackRef>>(StringComparer.Ordinal);
            var order = new List<string>();
            foreach (var t in sel)
            {
                if (!groups.TryGetValue(t.Sku, out var g)) { g = new List<TrackRef>(); groups[t.Sku] = g; order.Add(t.Sku); }
                g.Add(t);
            }
            var scored = new List<KeyValuePair<float, TrackRef>>(n);
            foreach (var sku in order)
            {
                var g = groups[sku];
                for (int i = g.Count - 1; i > 0; i--)       // Fisher-Yates within the album
                {
                    int j = Rng.Next(i + 1);
                    var tmp = g[i]; g[i] = g[j]; g[j] = tmp;
                }
                int k = g.Count;
                for (int i = 0; i < k; i++)
                {
                    float pos = (i + 0.15f + (float)Rng.NextDouble() * 0.7f) * n / k;
                    scored.Add(new KeyValuePair<float, TrackRef>(pos, g[i]));
                }
            }
            scored.Sort((a, b) => a.Key.CompareTo(b.Key));
            var result = new List<TrackRef>(n);
            foreach (var kv in scored) result.Add(kv.Value);
            if (avoidFirst.HasValue && result.Count > 1 && result[0].Equals(avoidFirst.Value))
            {
                int mid = result.Count / 2;
                var tmp = result[0]; result[0] = result[mid]; result[mid] = tmp;
            }
            return result;
        }

        /// <summary>Advance to the next READY track. At a TRUE cycle boundary:
        /// loop off → run-out (deliberate MutedByChoice via stopIntent); loop
        /// on + shuffle → a fresh cycle (dispersion, or broadcast album
        /// blocks) that never opens with what just played. [N6a] A boundary
        /// reached only because later entries are still LOADING is NOT a
        /// cycle boundary: the walk HOLDS the current cycle — no rebuild, no
        /// wrap, no run-out — and reports nothing-ready, so Reconcile parks
        /// at Loading (vanilla audible) and the readiness flip resumes THIS
        /// cycle at the same position once a load lands. The old
        /// rebuild-on-any-boundary destroyed the broadcast album-block order
        /// on every cold start (and could false-end a loop-off playlist whose
        /// tail merely wasn't decoded yet).</summary>
        private static bool AdvanceToNext(bool userSkip)
        {
            var s = S;
            EnsureQueueCurrent();
            int n = s.queue.Count;
            if (n == 0) { s.current = null; s.currentEnded = false; return false; }
            // [P5 REVERTED — do not re-add strict ordering here without
            // redesigning the traversal contract first.] Wave 4 made broadcast
            // traversal order-faithful by parking AT the first pending entry
            // instead of skipping it. Review r3 confirmed that mechanism
            // produces INDEFINITE DEAD AIR on the live stream by three routes
            // (Q1/Q2/Q3): a terminally-failed current is not an ENDED current,
            // so parking leaves it current-and-unplayable while the scan sees a
            // later ready entry, acquires Custom, holds suppression, and
            // EnsureMainPlaying's `clip == null` early-return spins forever;
            // the loop-off pending-behind hold reacquires Custom before
            // stopIntent is published; and a Skip blocked by a pending
            // successor is silently discarded. What it BOUGHT was cosmetic —
            // a cold-start album block can interleave once, or a track appears
            // a cycle late (never lost: this seat runs MusicLoop = true).
            // Dead air is strictly worse than an ordering blemish (#280), and
            // patching a mechanism whose fix produced two HIGHs is the pattern
            // #310 exists to stop. The real fix is ONE authoritative traversal
            // returning ready-target / pending / exhausted, consumed BEFORE
            // Custom ownership is acquired — a redesign, not a condition.
            // Pass 1: the REMAINDER of the current cycle (queueIndex -1 → all).
            bool pendingSkipped = false;
            for (int i = s.queueIndex + 1; i < n; i++)
            {
                var t = s.queue[i];
                if (IsTrackReady(t)) { AdoptCurrent(i, t); return true; }
                KickLoad(t);
                if (IsTrackLoadPending(t)) pendingSkipped = true;
            }
            // [N6a] unplayed entries of THIS cycle are inbound — hold it.
            if (pendingSkipped) return false;
            // Run-out needs a LOCATED cursor: with queueIndex -1 nothing ever
            // played, so an all-unready queue parks at Loading (the old walk
            // could not reach its boundary from -1 either — same semantics).
            if (!LoopEffective() && !userSkip && s.queueIndex >= 0)
            {
                s.stopIntent = true;
                Plugin.Log?.LogInfo("[MUSIC] playlist ended (loop off)");
                return false;
            }
            if (ShuffleEffective())
            {
                // Fresh cycle: broadcast reshuffles the ALBUM BLOCK order,
                // every other seat re-disperses per track [Batch-2 item 3] —
                // BuildQueueOrder picks the builder. [N6d] rebind queueIndex
                // to the NEW order immediately: a no-ready fall-through must
                // never leave an index addressed against the old list.
                s.queue = BuildQueueOrder(BuildEffectiveSelection(), s.current);
                n = s.queue.Count;
                if (n == 0) { s.current = null; s.currentEnded = false; return false; }
                s.queueIndex = s.current.HasValue ? s.queue.FindIndex(x => x.Equals(s.current.Value)) : -1;
            }
            // Pass 2: the fresh cycle (or the listed-order wrap) from the top.
            for (int i = 0; i < n; i++)
            {
                var t = s.queue[i];
                if (IsTrackReady(t)) { AdoptCurrent(i, t); return true; }
                KickLoad(t);
            }
            return false;   // nothing ready — Reconcile parks at Loading (vanilla audible)
        }

        /// <summary>Mirror of AdvanceToNext for the Previous transport: walk
        /// BACKWARD through the queue (wrapping) to the nearest ready track.
        /// Backward never rebuilds, so it needs no held-cycle logic — the
        /// wrap stays inside the live cycle order.</summary>
        private static bool AdvanceToPrevious()
        {
            var s = S;
            EnsureQueueCurrent();
            int n = s.queue.Count;
            if (n == 0) return false;
            int start = s.queueIndex < 0 ? 0 : s.queueIndex;
            for (int step = 1; step <= n; step++)
            {
                int i = ((start - step) % n + n) % n;
                var t = s.queue[i];
                if (IsTrackReady(t)) { AdoptCurrent(i, t); return true; }
                KickLoad(t);
            }
            return false;
        }

        /// <summary>Adopt queue[i] as the current track (shared by both
        /// transports). Clears the ended cursor [N6c] and prefetches the
        /// remainder of the entered album block [N6b].</summary>
        private static void AdoptCurrent(int i, TrackRef t)
        {
            var s = S;
            s.queueIndex = i;
            s.current = t;
            s.currentEnded = false;
            s.resumePositionSec = 0f;
            s.currentStarted = false;
            s.mainPausedByUs = false;
            s.currentPrematureRetried = false;
            PrefetchCurrentAlbumBlock();
        }

        /// <summary>[N6a] An unready CUSTOM entry that can still become ready:
        /// load in flight, or not yet kicked / awaiting the tier install. A
        /// FAILED decode is terminal — never pending — so an all-failed cycle
        /// still reaches the boundary rules instead of deadlocking the walk
        /// (and the readiness scan) forever.</summary>
        private static bool IsTrackLoadPending(TrackRef t)
        {
            if (IsVanillaSku(t.Sku) || !IsTrackKnown(t)) return false;
            if (!Clips.TryGetValue(t.ToString(), out var e)) return true;
            return e.Clip == null && !e.Failed;
        }

        /// <summary>[N6b] Prefetch the REMAINDER of the current album block —
        /// every consecutive same-album entry ahead of the queue cursor —
        /// plus the NEXT block's opening entry. Cold broadcast playback
        /// previously kept only ~2 loads in flight, so a block's later tracks
        /// were still undecoded when their turn came and the walk abandoned
        /// the block; the extra head keeps a cold block TRANSITION from
        /// detouring through Loading (a vanilla blip on the stream). Called
        /// on the adoption/start edges only — a no-op walk of dictionary
        /// lookups when the block is already resident.</summary>
        private static void PrefetchCurrentAlbumBlock()
        {
            var s = S;
            if (s.queueIndex < 0 || s.queueIndex >= s.queue.Count) return;
            string sku = s.queue[s.queueIndex].Sku;
            int i = s.queueIndex + 1;
            for (; i < s.queue.Count; i++)
            {
                if (!string.Equals(s.queue[i].Sku, sku, StringComparison.Ordinal)) break;
                KickLoad(s.queue[i]);
            }
            if (i < s.queue.Count) KickLoad(s.queue[i]);   // next block's head
        }

        // ── clip loading (UnityWebRequest, buffered OGG) ─────────────────

        private static bool IsTrackReady(TrackRef t)
        {
            if (IsVanillaSku(t.Sku)) return t.Idx >= 0 && t.Idx < S.vanillaTracks.Count && S.vanillaTracks[t.Idx].Clip != null;
            return Clips.TryGetValue(t.ToString(), out var e) && e.Clip != null;
        }

        private static bool ScanHasReadyTrack()
        {
            var s = S;
            // [I8] under broadcast the effective universe is custom-only — a
            // stale vanilla current must never count as ready. [N6c] an ENDED
            // current is a cursor, not a playable: counting it held
            // desired-mode at Custom with nothing to play — owned SILENCE
            // under suppression, dead air on the broadcast stream.
            if (s.current.HasValue && !s.currentEnded && IsTrackReady(s.current.Value)
                && !(BroadcastPredicate() && IsVanillaSku(s.current.Value.Sku))) return true;
            var q = s.queue;
            // [N6a-coherence] readiness must mirror what AdvanceToNext can
            // actually REACH. While unplayed entries of the current cycle are
            // still loading, the walk HOLDS the cycle (no wrap, no rebuild),
            // so already-played entries BEHIND the cursor are unreachable and
            // must not count — a cached earlier track would otherwise pin
            // desired-mode at Custom with nothing playable ahead (the same
            // dead-air state through a second door). With nothing pending
            // ahead the boundary IS reachable (wrap or rebuild preserves
            // membership), so any ready entry counts.
            // (The wave-4 per-branch strict-order mirror was reverted with the
            // walk's strict ordering — see the [P5 REVERTED] note there.)
            bool pendingAhead = false;
            for (int i = s.queueIndex < 0 ? 0 : s.queueIndex + 1; i < q.Count; i++)
            {
                if (IsTrackReady(q[i])) return true;
                if (IsTrackLoadPending(q[i])) pendingAhead = true;
            }
            if (pendingAhead) return false;
            for (int i = 0; i < q.Count && i <= s.queueIndex; i++)
                if (IsTrackReady(q[i])) return true;
            return false;
        }

        private static AudioClip ResolveReadyClip(TrackRef t)
        {
            if (IsVanillaSku(t.Sku))
                return (t.Idx >= 0 && t.Idx < S.vanillaTracks.Count) ? S.vanillaTracks[t.Idx].Clip : null;
            return Clips.TryGetValue(t.ToString(), out var e) ? e.Clip : null;
        }

        private static void KickLoadsForQueueHead()
        {
            var s = S;
            int kicked = 0;
            if (s.current.HasValue && KickLoad(s.current.Value)) kicked++;
            for (int i = 0; i < s.queue.Count && kicked < 2; i++)
                if (KickLoad(s.queue[i])) kicked++;
        }

        /// <summary>Start (or re-check) a custom track's clip load. Returns
        /// true when a load is now in flight. Validation authority is the
        /// compiled manifest via MusicAssets.PathFor — a null path means the
        /// tier is not installed/validated, so the tier trigger fires instead
        /// [F12][F22].</summary>
        private static bool KickLoad(TrackRef t)
        {
            if (IsVanillaSku(t.Sku)) return false;
            string key = t.ToString();
            if (Clips.TryGetValue(key, out var e)) return e.Clip == null && !e.Failed;
            var a = MusicCatalog.Get(t.Sku);
            if (a == null || a.Tracks == null || t.Idx >= a.Tracks.Length) return false;
            string path = null;
            try { path = MusicAssets.PathFor(a.Tracks[t.Idx].OggFile); } catch { }
            if (path == null)
            {
                try { if (!MusicAssets.TierReady(MusicTier.Full)) MusicAssets.EnsureTier(MusicTier.Full, "selection"); } catch { }
                return false;
            }
            EnsureClipLoading(key, path);
            return true;
        }

        private static void EnsureClipLoading(string key, string path)
        {
            if (Clips.ContainsKey(key)) return;
            try
            {
                string url;
                try { url = new Uri(path).AbsoluteUri; }
                catch { url = "file:///" + path.Replace('\\', '/'); }
                var req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
                var dh = req.downloadHandler as DownloadHandlerAudioClip;
                // Fully buffered, NOT streamed: disk-IO underruns on streamed
                // playback were the reported light audio skipping, and only a
                // buffered clip gives exact AudioSource.time seeks. The whole
                // pack is ~26MB of compressed audio — trivially resident.
                if (dh != null) dh.streamAudio = false;
                req.SendWebRequest();
                Clips[key] = new ClipEntry { Key = key, Req = req };
            }
            catch (Exception ex)
            {
                Clips[key] = new ClipEntry { Key = key, Failed = true };
                LogOnce("load:" + key, $"[MUSIC] clip load start failed for {key}: {ex.Message}", true);
            }
        }

        /// <summary>Polls in-flight requests (no coroutines: a host respawn
        /// would kill them; the request objects are static and survive).</summary>
        private static void PumpClipLoads()
        {
            List<string> failedNow = null;
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Req == null || !e.Req.isDone || e.Clip != null || e.Failed) continue;
                if (e.Req.result == UnityWebRequest.Result.Success)
                {
                    AudioClip clip = null;
                    try { clip = DownloadHandlerAudioClip.GetContent(e.Req); } catch { }
                    if (clip != null && clip.length > 0.1f)
                    {
                        e.Clip = clip;   // static ref held: scene-transition asset unloads can't collect it
                        continue;
                    }
                }
                e.Failed = true;
                (failedNow ?? (failedNow = new List<string>())).Add(e.Key);
                LogOnce("clipfail:" + e.Key, $"[MUSIC] clip decode failed for {e.Key}: {(e.Req.result != UnityWebRequest.Result.Success ? e.Req.error : "empty clip")}", true);
                try { e.Req.Dispose(); } catch { }
                e.Req = null;
            }
            if (failedNow != null && S.current.HasValue && failedNow.Contains(S.current.Value.ToString()))
            {
                // Current track died: try the next; Reconcile parks at Loading
                // if the playable set is gone [F12].
                if (AdvanceToNext(userSkip: false)) EnsureMainPlaying();
                else Reconcile("current-clip-failed");
            }
        }

        private static void DisposeEntry(ClipEntry e)
        {
            try { e.Req?.Dispose(); } catch { }
            e.Req = null; e.Clip = null;
        }

        private static void EvictUnplayableClips()
        {
            List<string> drop = null;
            foreach (var kv in Clips)
            {
                string sku = kv.Key.StartsWith("p:", StringComparison.Ordinal) ? kv.Key.Substring(2) : kv.Key;
                int slash = sku.LastIndexOf('/');
                if (slash > 0) sku = sku.Substring(0, slash);
                if (IsVanillaSku(sku) || IsAlbumPlayable(sku)) continue;
                (drop ?? (drop = new List<string>())).Add(kv.Key);
            }
            if (drop == null) return;
            foreach (var k in drop) { DisposeEntry(Clips[k]); Clips.Remove(k); }
        }

        // ── playback primitives ──────────────────────────────────────────

        private static void EnsureMainPlaying()
        {
            var s = S;
            var h = _host;
            if (h == null || h.Main == null) return;
            if (s.mode != MusicMode.Custom || s.paused) return;
            if (s.faultPending || s.faultDurable) return;   // [I7]
            if (!s.current.HasValue && !AdvanceToNext(userSkip: false)) return;
            if (!s.current.HasValue) return;
            // [N6c] an ENDED current is a queue cursor, not a playable —
            // advance off it, never (re)start it: after a Loading detour the
            // release cleared currentStarted, so the start branch below would
            // otherwise replay the finished clip from zero when readiness
            // returns. AdvanceToNext clears the flag when it adopts.
            if (s.currentEnded && !AdvanceToNext(userSkip: false)) return;
            var clip = ResolveReadyClip(s.current.Value);
            if (clip == null) { KickLoad(s.current.Value); return; }
            var m = h.Main;
            if (m.clip != clip) { m.clip = clip; s.currentStarted = false; s.mainPausedByUs = false; s.currentPrematureRetried = false; }
            if (m.isPlaying && s.currentStarted)
            {
                // [K2] steady state — but the source may still carry the
                // hard-silence mute from a failed Stop (fault retry path):
                // recover it here or a "recovered" engine stays inaudible.
                try { if (m.mute) m.mute = false; }
                catch (Exception ex) { EnterDurableFaultNoThrow("main-unmute: " + ex.Message); }
                return;
            }
            if (m.isPlaying)
            {
                // [K2] playing WITHOUT started-state = a deliberate restart
                // intent (PlayTrack/Skip/Previous landed on the entry already
                // audible and reset currentStarted). The old early-return here
                // orphaned the state: Now Playing/seek blank, natural end
                // restarted instead of advancing. Stop and fall through to the
                // explicit (re)start below.
                try { m.Stop(); }
                catch (Exception ex) { EnterDurableFaultNoThrow("main-restart-stop: " + ex.Message); return; }
            }
            // [J1] a STARTED source that is silent without being paused-by-us
            // belongs to TickPlayback's premature-stop classifier — never
            // blind-replay it here: Play() would re-stamp currentStartedRt
            // and renew the classifier's grace window forever.
            if (s.currentStarted && !s.mainPausedByUs) return;
            // [I1] every play/unpause failure funnels to durable Fault —
            // owned silence with suppression held is the forbidden state.
            if (s.mainPausedByUs && s.currentStarted)
            {
                // [K2 condition] the unmute is REQUIRED, not best-effort: a
                // swallowed throw here would publish Custom ownership with a
                // hard-silenced source — the forbidden muted-owned state.
                try { m.mute = false; }
                catch (Exception ex) { EnterDurableFaultNoThrow("main-resume-unmute: " + ex.Message); return; }
                try { m.UnPause(); }
                catch (Exception ex) { EnterDurableFaultNoThrow("main-unpause: " + ex.Message); return; }
                s.mainPausedByUs = false;
                // [K9] fresh grace window: Unity can report isPlaying=false for a
                // beat after UnPause; without a re-stamp the premature classifier
                // would spend its one counted retry (or Fault) on that beat.
                // Deliberately does NOT reset currentPrematureRetried.
                s.currentStartedRt = Time.realtimeSinceStartup;
                return;
            }
            // [K2 condition] required unmute, same rule as the resume branch:
            // fault and return rather than start a source that may be muted.
            try { m.mute = false; }
            catch (Exception ex) { EnterDurableFaultNoThrow("main-start-unmute: " + ex.Message); return; }
            try
            {
                float pos = s.resumePositionSec;
                try { m.time = (pos > 0.5f && pos < clip.length - 1f) ? pos : 0f; } catch { }
                m.Play();
            }
            catch (Exception ex) { EnterDurableFaultNoThrow("main-play: " + ex.Message); return; }
            s.currentStarted = true;
            s.currentStartedRt = Time.realtimeSinceStartup;
            // [N6b] block prefetch rides the start edge too — covers the
            // PlayTrack direct-assignment path, which never runs AdoptCurrent.
            PrefetchCurrentAlbumBlock();
        }

        private static float CurrentMainTimeOr(float fallback)
        {
            try
            {
                var h = _host;
                if (h != null && h.Main != null && h.Main.clip != null) return h.Main.time;
            }
            catch { }
            return fallback;
        }

        /// <summary>[I1-residual] Pause the main source, preserving the resume
        /// position. NO-THROW, but cleanup success is REPORTED, not assumed:
        /// returns false when the pause threw — the source is then
        /// hard-silenced (mute + volume 0 + Stop retry) so it cannot stay
        /// audible beside vanilla, and the CALLER must treat the state as
        /// untrustworthy (durable Fault, or the prefix fault latch on the
        /// menu-handoff path).</summary>
        private static bool PauseMain()
        {
            var h = _host;
            if (h == null || h.Main == null) return true;   // nothing to silence
            try
            {
                if (h.Main.isPlaying)
                {
                    S.resumePositionSec = h.Main.time;
                    h.Main.Pause();
                    S.mainPausedByUs = true;
                }
                return true;
            }
            catch (Exception ex)
            {
                HardSilenceMainNoThrow();
                LogOnce("pausefail", "[MUSIC] main pause failed (" + ex.Message + ") — source hard-silenced", true);
                return false;
            }
        }

        /// <summary>[I1-residual] Last-resort silencer for a source whose
        /// Pause/Stop threw: mute, zero volume, and a Stop retry — each
        /// individually guarded. mute is the DURABLE half (nothing else
        /// writes it; the per-tick volume pass rewrites volume), and the
        /// EnsureMainPlaying play/unpause paths un-mute before restarting so
        /// a fault retry can never resume into a muted source.</summary>
        private static void HardSilenceMainNoThrow()
        {
            var h = _host;
            if (h == null) return;
            try { var m = h.Main; if (m != null) m.mute = true; } catch { }
            try { var m = h.Main; if (m != null) m.volume = 0f; } catch { }
            try { var m = h.Main; if (m != null) m.Stop(); } catch { }
        }

        private static void HardSilencePreviewNoThrow()
        {
            var h = _host;
            if (h == null) return;
            try { var p = h.Preview; if (p != null) p.mute = true; } catch { }
            try { var p = h.Preview; if (p != null) p.volume = 0f; } catch { }
            try { var p = h.Preview; if (p != null) p.Stop(); } catch { }
        }

        /// <summary>Stops BOTH sources; every statement individually guarded so
        /// this is safe from the prefix exception path (must-verify item). A
        /// throwing Stop is hard-silenced in place (mute + volume 0 + Stop
        /// retry), so even the failure path leaves nothing audible — callers
        /// that must GUARANTEE cleanup consume StopSources()'s bool instead
        /// [I1-residual].</summary>
        internal static void StopSourcesNoThrow()
        {
            StopSources();
        }

        /// <summary>[I1-residual] Returning form of the both-sources stop:
        /// false means a Stop threw. The source is hard-silenced either way;
        /// the caller owns the terminal (durable Fault) because the engine
        /// can no longer trust that source's state.</summary>
        private static bool StopSources()
        {
            var h = _host;
            if (h == null) return true;
            bool ok = true;
            try { var m = h.Main; if (m != null) m.Stop(); }
            catch { HardSilenceMainNoThrow(); ok = false; }
            try { var p = h.Preview; if (p != null) p.Stop(); }
            catch { HardSilencePreviewNoThrow(); ok = false; }
            return ok;
        }

        private static void StopPreviewSourceNoThrow()
        {
            try { var h = _host; if (h != null && h.Preview != null) h.Preview.Stop(); }
            catch { HardSilencePreviewNoThrow(); }
        }

        private static void StopMainNoThrow()
        {
            try { var h = _host; if (h != null && h.Main != null) h.Main.Stop(); }
            catch { HardSilenceMainNoThrow(); }
        }

        // ── vanilla catalog + mixer acquisition ──────────────────────────

        private static void PollManagerIdentity()
        {
            var s = S;
            SoundMusicManager mgr = null;
            try { mgr = SoundMusicManager.Instance; } catch { }
            int id = mgr != null ? mgr.GetInstanceID() : 0;
            if (id == s.managerInstanceId) return;
            s.managerInstanceId = id;
            if (mgr == null) return;
            // Scene reload: new manager instance. A scene change ends any
            // preview [F13]; then reacquire mixer + vanilla catalog + rerun
            // Reconcile [F19].
            if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal("scene-change");
            s.duckWanted = false;   // [I14] a pick-phase duck cannot outlive the scene that picked
            AcquireRouting(mgr);
            AcquireVanillaCatalog(mgr);
            RouteSources();
            Reconcile("manager-identity");
        }

        /// <summary>Route both sources into the vanilla music AudioMixerGroup:
        /// musicIngame (SoundEvent) → variables → audioMixerGroup, walked via
        /// AccessTools — the Sonigon assembly is deliberately NOT referenced
        /// (#322). Fallback: replicate the SoundVolumeManager dB curve from
        /// the PlayerPrefs sliders.</summary>
        private static void AcquireRouting(SoundMusicManager mgr)
        {
            var s = S;
            s.musicGroup = null;
            s.mixerRouted = false;
            try
            {
                object ev = AccessTools.Field(typeof(SoundMusicManager), "musicIngame")?.GetValue(mgr);
                object vars = ev == null ? null : AccessTools.Field(ev.GetType(), "variables")?.GetValue(ev);
                object grp = vars == null ? null : AccessTools.Field(vars.GetType(), "audioMixerGroup")?.GetValue(vars);
                s.musicGroup = grp as AudioMixerGroup;
            }
            catch (Exception ex) { LogOnce("mixwalk", "[MUSIC] mixer group walk threw: " + ex.Message, true); }
            if (s.musicGroup != null)
            {
                s.mixerRouted = true;
                LogOnce("mixer-path", $"[MUSIC] routed to vanilla music mixer group '{s.musicGroup.name}' — game volume sliders apply natively", false);
            }
            else
            {
                s.fallbackGain = ComputeFallbackGain();
                s.fallbackRefreshRt = Time.realtimeSinceStartup;
                LogOnce("mixer-path", "[MUSIC] mixer group walk found nothing — PlayerPrefs volume-curve fallback engaged", true);
            }
        }

        /// <summary>Replicates SoundVolumeManager.NormalizeVolume's shape from
        /// the persisted sliders, normalized so full sliders = gain 1 (the
        /// mixer's +dB offsets cancel against the full-slider reference; an
        /// AudioSource cannot express gain > 1 anyway).</summary>
        private static float ComputeFallbackGain()
        {
            try
            {
                float master = PlayerPrefs.GetFloat("OPTION_VOLUME_MASTER", 1f);
                float music = PlayerPrefs.GetFloat("OPTION_VOLUME_MUSIC", 1f);
                float dbM = Mathf.Log10(Mathf.Max(master, 0.0001f)) * 20f;
                float dbU = Mathf.Log10(Mathf.Max(music, 0.0001f)) * 20f;
                if (dbM <= -60f || dbU <= -60f) return 0f;   // vanilla's -80 dB floor
                return Mathf.Clamp01(Mathf.Pow(10f, (dbM + dbU) / 20f));
            }
            catch { return 1f; }
        }

        private static void RouteSources()
        {
            var s = S;
            var h = _host;
            if (h == null) return;
            try
            {
                if (h.Main != null) h.Main.outputAudioMixerGroup = s.mixerRouted ? s.musicGroup : null;
                if (h.Preview != null) h.Preview.outputAudioMixerGroup = s.mixerRouted ? s.musicGroup : null;
            }
            catch (Exception ex) { LogOnce("route", "[MUSIC] source routing failed: " + ex.Message, true); }
        }

        /// <summary>[F21] Runtime enumeration of the vanilla combat album:
        /// musicIngame → soundContainerArray → audioClip[], filtered to the
        /// _Game suffix, deduped by clip instance, sorted by name, logged once.
        /// [G14] musicMainMenu enumerated SEPARATELY — the menu theme is
        /// menu-only and never enters the combat playlist. Zero clips =
        /// vanilla album absent + loud log; everything fails open.</summary>
        private static void AcquireVanillaCatalog(SoundMusicManager mgr)
        {
            var s = S;
            var found = new List<VanillaTrack>();
            AudioClip menuClip = null;
            try
            {
                foreach (var clip in EnumerateEventClips(mgr, "musicIngame"))
                {
                    string nm = clip.name ?? "";
                    if (!nm.EndsWith("_Game", StringComparison.Ordinal)) continue;
                    bool dup = false;
                    for (int i = 0; i < found.Count; i++)
                        if (ReferenceEquals(found[i].Clip, clip)) { dup = true; break; }
                    if (!dup) found.Add(new VanillaTrack { RawName = nm, Title = PrettifyVanillaName(nm), Clip = clip });
                }
                found.Sort((a, b) => string.CompareOrdinal(a.RawName, b.RawName));
                foreach (var clip in EnumerateEventClips(mgr, "musicMainMenu"))
                {
                    menuClip = clip;
                    break;
                }

                // Fallback route: at the MAIN MENU the manager's event assets
                // carry EMPTY soundContainerArray (live-probed 2026-09-02:
                // containers=0 on both events, while the clips themselves ARE
                // resident — Sonigon wires containers later). Enumerate the
                // loaded AudioClips directly by the MUS_ naming convention
                // (the scout-verified alternative); the event walk stays
                // preferred because it is name-convention-free.
                if (found.Count == 0 || menuClip == null)
                {
                    bool needCombat = found.Count == 0;   // latch BEFORE the loop — the first add must not stop the rest
                    var all = Resources.FindObjectsOfTypeAll<AudioClip>();
                    for (int i = 0; i < all.Length; i++)
                    {
                        var clip = all[i];
                        if (clip == null) continue;
                        string nm = clip.name ?? "";
                        if (needCombat && nm.StartsWith("MUS_Level_", StringComparison.Ordinal) &&
                            nm.EndsWith("_Game", StringComparison.Ordinal))
                        {
                            bool dup = false;
                            for (int j = 0; j < found.Count; j++)
                                if (ReferenceEquals(found[j].Clip, clip)) { dup = true; break; }
                            if (!dup) found.Add(new VanillaTrack { RawName = nm, Title = PrettifyVanillaName(nm), Clip = clip });
                        }
                        if (menuClip == null && nm.StartsWith("MUS_Main_Menu", StringComparison.Ordinal))
                            menuClip = clip;
                    }
                    found.Sort((a, b) => string.CompareOrdinal(a.RawName, b.RawName));
                    if (found.Count > 0)
                        LogOnce("vanilla-enum-fb", $"[MUSIC] vanilla catalog via Resources fallback: {found.Count} combat clips (event walk saw empty containers)", false);
                }
            }
            catch (Exception ex)
            {
                LogOnce("vanilla-enum", "[MUSIC] vanilla catalog enumeration threw: " + ex.Message + " — vanilla album absent (fail open)", true);
            }
            s.vanillaTracks = found;
            s.menuThemeClip = menuClip;
            s.menuThemeTitle = menuClip != null ? PrettifyVanillaName(menuClip.name ?? "Main Menu Theme") : "";
            s.queueSignature = null;   // catalog membership feeds the queue

            var sig = new StringBuilder();
            foreach (var t in found) sig.Append(t.RawName).Append(';');
            sig.Append(menuClip != null ? menuClip.name : "<no-menu-theme>");
            string signature = sig.ToString();
            if (signature != s.vanillaLogSignature)
            {
                s.vanillaLogSignature = signature;
                if (found.Count == 0)
                {
                    Plugin.Log?.LogError("[MUSIC] vanilla album enumeration yielded ZERO _Game clips — vanilla OST album absent; engine fails open to vanilla behavior");
                    // Diagnostic (#117 discipline): say what the walk actually saw,
                    // one shot per signature, so a miss is debuggable from one log.
                    try
                    {
                        object ev = AccessTools.Field(typeof(SoundMusicManager), "musicIngame")?.GetValue(mgr);
                        if (ev == null) Plugin.Log?.LogError("[MUSIC-DIAG] musicIngame field is NULL on this manager instance");
                        else
                        {
                            object arr = AccessTools.Field(ev.GetType(), "soundContainerArray")?.GetValue(ev);
                            var en = arr as System.Collections.IEnumerable;
                            if (arr == null) Plugin.Log?.LogError($"[MUSIC-DIAG] event type {ev.GetType().FullName} has no/null soundContainerArray");
                            else
                            {
                                int nCont = 0; var names = new StringBuilder();
                                foreach (var sc in en)
                                {
                                    nCont++;
                                    if (sc == null) { names.Append("<null-sc>;"); continue; }
                                    object clips = AccessTools.Field(sc.GetType(), "audioClip")?.GetValue(sc);
                                    var ce = clips as System.Collections.IEnumerable;
                                    if (ce == null) { names.Append(((UnityEngine.Object)sc).name).Append(":<no-audioClip-field>;"); continue; }
                                    int nc = 0;
                                    foreach (var c in ce) { nc++; var cl = c as AudioClip; if (cl != null && names.Length < 900) names.Append(cl.name).Append(';'); }
                                    if (nc == 0 && names.Length < 900) names.Append(((UnityEngine.Object)sc).name).Append(":<0 clips>;");
                                }
                                Plugin.Log?.LogError($"[MUSIC-DIAG] containers={nCont} clipsSeen=[{names}]");
                            }
                        }
                    }
                    catch (Exception dx) { Plugin.Log?.LogError("[MUSIC-DIAG] walk diag threw: " + dx.Message); }
                }
                else
                    Plugin.Log?.LogInfo($"[MUSIC] vanilla album observed: {found.Count} combat clips [{signature}]");
                if (menuClip == null)
                    Plugin.Log?.LogWarning("[MUSIC] menu theme enumeration found no clip — menu-only row omitted");
            }
        }

        private static IEnumerable<AudioClip> EnumerateEventClips(SoundMusicManager mgr, string fieldName)
        {
            object ev = AccessTools.Field(typeof(SoundMusicManager), fieldName)?.GetValue(mgr);
            if (ev == null) yield break;
            object arr = AccessTools.Field(ev.GetType(), "soundContainerArray")?.GetValue(ev);
            var containers = arr as System.Collections.IEnumerable;
            if (containers == null) yield break;
            foreach (var sc in containers)
            {
                if (sc == null) continue;
                object clips = AccessTools.Field(sc.GetType(), "audioClip")?.GetValue(sc);
                var clipArr = clips as System.Collections.IEnumerable;
                if (clipArr == null) continue;
                foreach (var c in clipArr)
                {
                    var clip = c as AudioClip;
                    if (clip != null) yield return clip;
                }
            }
        }

        private static string PrettifyVanillaName(string raw)
        {
            string s = raw ?? "";
            if (s.StartsWith("MUS_Level_", StringComparison.Ordinal)) s = s.Substring(10);
            else if (s.StartsWith("MUS_", StringComparison.Ordinal)) s = s.Substring(4);
            if (s.EndsWith("_Game", StringComparison.Ordinal)) s = s.Substring(0, s.Length - 5);
            return s.Replace('_', ' ');
        }

        // ── entitlements [F15][F16][G11] ─────────────────────────────────

        private static void OnEntitlementsChanged()
        {
            try
            {
                var s = S;
                bool hadSelection = s.selectionNonEmpty;   // pre-change derived state [I9]
                // [G10] entitlement mutations invalidate the preview
                // generation and terminate the preview FIRST; restoration
                // resubmits intent through Reconcile, which re-validates.
                s.previewGen++;
                if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal("entitlements-changed");
                // Full-tier trigger on ownership (design §3).
                bool ownsAny = false;
                var albums = MusicCatalog.Albums;
                if (albums != null)
                    for (int i = 0; i < albums.Length; i++)
                        if (albums[i] != null && IsAlbumPlayable(albums[i].Sku) && !IsVanillaSku(albums[i].Sku)) { ownsAny = true; break; }
                if (ownsAny)
                {
                    try { if (!MusicAssets.TierReady(MusicTier.Full)) MusicAssets.EnsureTier(MusicTier.Full, "entitlement"); } catch { }
                }
                // Ownership LOSS is deterministic and immediate [F15]: stop a
                // now-unplayable current track, drop its cached clips.
                if (s.current.HasValue && !IsVanillaSku(s.current.Value.Sku) && !IsAlbumPlayable(s.current.Value.Sku))
                {
                    StopMainNoThrow();
                    s.current = null; s.resumePositionSec = 0f; s.currentStarted = false; s.mainPausedByUs = false;
                    s.currentEnded = false;
                }
                EvictUnplayableClips();
                s.queueSignature = null;
                // [I9] Ownership loss must never resolve to owned silence:
                // when the revoke just EMPTIED the effective selection while
                // the universe stays non-empty, release takeover to vanilla
                // explicitly — MutedByChoice stays reserved for the user's
                // own deselect-everything choice, and the consent-revoke
                // promise is "vanilla music comes back".
                if (hadSelection && !s.stopIntent)
                {
                    EnsureQueueCurrent();
                    if (s.queue.Count == 0 && !SelectionUniverseEmpty())
                    {
                        s.manualTakeover = false;
                        s.vanillaPreferred = true;
                        Plugin.Log?.LogInfo("[MUSIC] entitlement loss emptied the effective selection — releasing to vanilla");
                    }
                }
                Reconcile("entitlements-changed");
            }
            catch (Exception ex) { LogOnce("entchg", "[MUSIC] entitlements-changed handler failed: " + ex.Message, true); }
        }

        // ── fault retry ──────────────────────────────────────────────────

        /// <summary>The "explicit Retry" that makes Custom eligible again after
        /// a durable Fault: any deliberate transport action — preview-ending
        /// ones included; they clear BEFORE returning [I7]. There is no
        /// automatic health probe — if the cause persists, the next failure
        /// re-latches within a frame.</summary>
        private static void ClearFaultForUserAction(string action)
        {
            var s = S;
            if (!s.faultPending && !s.faultDurable) return;
            s.faultPending = false;
            s.faultDurable = false;
            s.faultReason = "";
            Plugin.Log?.LogInfo($"[MUSIC] fault cleared by user transport ({action}) — retrying");
        }

        // ── deselected-set persistence ───────────────────────────────────

        private static void RefreshDeselectedCache()
        {
            var s = S;
            string raw = null;
            try { raw = Plugin.MusicDeselected != null ? Plugin.MusicDeselected.Value : null; } catch { }
            raw = raw ?? "";
            if (string.Equals(raw, s.deselectedRaw, StringComparison.Ordinal)) return;
            s.deselectedRaw = raw;
            s.deselected.Clear();
            foreach (var part in raw.Split(','))
            {
                var p = part.Trim();
                if (p.Length > 0 && p.IndexOf('/') > 0) s.deselected.Add(p);
            }
            s.queueSignature = null;
        }

        private static void PersistDeselected()
        {
            var s = S;
            var sb = new StringBuilder();
            foreach (var k in s.deselected)
            {
                if (sb.Length > 0) sb.Append(',');
                sb.Append(k);
            }
            s.deselectedRaw = sb.ToString();
            try { if (Plugin.MusicDeselected != null) Plugin.MusicDeselected.Value = s.deselectedRaw; } catch { }
        }

        // ── menu-music rule (3-state, Batch-2 item 1) ────────────────────

        private const string MENU_MODE_VANILLA = "vanilla";
        private const string MENU_MODE_CUSTOM = "custom";
        private const string MENU_MODE_SILENT = "silent";

        /// <summary>Resolved MenuMusicMode: "vanilla" | "custom" | "silent".
        /// The legacy MenuMusicEnabled bool is read (null-guarded) ONLY while
        /// MenuMusicMode is null/unbound — an old cfg mid-migration (#190,
        /// the bind + one-shot migration are Plugin.cs's). An unknown
        /// spelling fails open to "vanilla" (the bind default's behavior).</summary>
        private static string MenuModeSetting()
        {
            // [P9] The legacy MenuMusicEnabled bool is consulted ONLY when the
            // MenuMusicMode entry is genuinely UNBOUND (mid-migration, #190).
            // A BOUND entry hand-edited to blank/whitespace/unknown resolves
            // as vanilla — exactly NativeUI.NormalizeMenuMusicMode's rule —
            // where the old IsNullOrWhiteSpace fall-through made Settings
            // paint Default while the engine played the legacy bool's custom.
            try
            {
                var e = Plugin.MenuMusicMode;
                if (e != null)
                {
                    string v = (e.Value ?? "").Trim();
                    if (string.Equals(v, MENU_MODE_CUSTOM, StringComparison.OrdinalIgnoreCase)) return MENU_MODE_CUSTOM;
                    if (string.Equals(v, MENU_MODE_SILENT, StringComparison.OrdinalIgnoreCase)) return MENU_MODE_SILENT;
                    return MENU_MODE_VANILLA;
                }
            }
            catch { }
            try { return (Plugin.MenuMusicEnabled != null && Plugin.MenuMusicEnabled.Value) ? MENU_MODE_CUSTOM : MENU_MODE_VANILLA; }
            catch { return MENU_MODE_VANILLA; }
        }

        /// <summary>Side-effect-free (prefix-safe): pure config read.</summary>
        private static bool MenuSilent()
            => string.Equals(MenuModeSetting(), MENU_MODE_SILENT, StringComparison.Ordinal);

        private static bool MenuCovered()
        {
            if (BroadcastPredicate()) return true;
            try { return string.Equals(MenuModeSetting(), MENU_MODE_CUSTOM, StringComparison.Ordinal) && S.selectionNonEmpty; }
            catch { return false; }
        }

        // ── host lifecycle (#16: HideAndDontSave + OnDestroy respawn) ────

        private static void SpawnHost()
        {
            try
            {
                var go = new GameObject("CR_MusicEngine");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                go.AddComponent<MusicEngineHost>();
            }
            catch (Exception ex) { Plugin.Log?.LogError($"[MUSIC] host spawn failed: {ex.Message}"); }
        }

        internal static void OnHostAwake(MusicEngineHost host)
        {
            _host = host;
            var s = S;
            RouteSources();
            if (!s.everHosted) { s.everHosted = true; return; }
            // Rehydration [F19]: the durable state object is authoritative; a
            // fresh host just re-derives its component state from it.
            try
            {
                Plugin.Log?.LogInfo($"[MUSIC] host respawned — rehydrating (mode={s.mode})");
                if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal("host-respawn");
                s.currentStarted = false;
                s.mainPausedByUs = false;
                s.duckWanted = false;   // [I14] rehydration re-derives the duck from the next prefix edge
                if (s.broadcastHeld) { try { s.broadcastHeld = RunInBackgroundLease.Acquire("broadcast-music"); } catch { } }
                Reconcile("host-respawn");
            }
            catch (Exception ex)
            {
                // [I1] a failed rehydration is a host failure — durable fault
                // (vanilla restored) instead of a half-rehydrated owner.
                EnterDurableFaultNoThrow("host-rehydrate: " + ex.Message);
            }
        }

        internal static void OnHostDestroyed(MusicEngineHost dying)
        {
            if (!ReferenceEquals(_host, dying)) return;
            _host = null;
            if (_quitting) return;
            SpawnHost();
            // [I1] failed respawn: nothing ticks again, so a held suppression
            // would silence vanilla forever — durable fault releases it all.
            if (_host == null) EnterDurableFaultNoThrow("host-respawn-failed");
        }

        // ── misc ─────────────────────────────────────────────────────────

        private static void LogOnce(string key, string msg, bool warn)
        {
            if (!OnceKeys.Add(key)) return;
            try
            {
                if (warn) Plugin.Log?.LogWarning(msg);
                else Plugin.Log?.LogInfo(msg);
            }
            catch { }
        }
    }

    /// <summary>Playback host: two AudioSources (main + preview) + the duck
    /// LPF on one HideAndDontSave GO. Deliberately stateless — every piece of
    /// session state lives in MusicEngine's durable static object, so a
    /// destroy/respawn cycle loses nothing but the Unity components.</summary>
    internal sealed class MusicEngineHost : MonoBehaviour
    {
        internal AudioSource Main;
        internal AudioSource Preview;
        internal AudioLowPassFilter Lpf;

        private void Awake()
        {
            hideFlags = HideFlags.HideAndDontSave;
            gameObject.hideFlags = HideFlags.HideAndDontSave;
            DontDestroyOnLoad(gameObject);
            Main = gameObject.AddComponent<AudioSource>();
            Preview = gameObject.AddComponent<AudioSource>();
            foreach (var src in new[] { Main, Preview })
            {
                src.playOnAwake = false;
                src.loop = false;            // queue advance is engine-driven
                src.spatialBlend = 0f;       // 2D — music, not positional
                src.priority = 64;
            }
            Lpf = gameObject.AddComponent<AudioLowPassFilter>();
            Lpf.cutoffFrequency = 22000f;
            Lpf.enabled = false;
            MusicEngine.OnHostAwake(this);
        }

        private void Update()
        {
            MusicEngine.Tick();
        }

        private void OnDestroy()
        {
            MusicEngine.OnHostDestroyed(this);
        }
    }

    /// <summary>
    /// Vanilla music suppression [F20][G13]. Prefixes on the two funnels that
    /// carry ALL of vanilla's music intent: SoundMusicManager.PlayIngame(bool)
    /// (called from MapTransition.Enter once per map and CardChoice every
    /// frame during a pick) and PlayMainMenu() (called from the manager's own
    /// Start() on every scene load). A standing prefix is mandatory — a
    /// one-shot StopAllMusic() would be re-armed by the very next call
    /// (musicIngamePlaying resets), see the scout's re-arm hazard.
    ///
    /// Shape per the design: side-effect-free TryShouldSuppress FIRST; only a
    /// confident suppress decision performs effects (ambience mirroring —
    /// PlayAmbience() is vanilla PlayIngame's first statement and
    /// StopAmbience() is PlayMainMenu's, both publicized; plus the deduped
    /// isCard duck edge). ANY exception latches FaultPending, releases
    /// suppression, stops both plugin sources no-throw, and returns true so
    /// vanilla runs — no frame ends with both owners playing.
    ///
    /// NOT gated on IsCompetitiveRoom (#286) — music is seat-local. Attachment
    /// is verified by MusicEngine.Initialize via SuppressionPatchLive (#83).
    /// </summary>
    [HarmonyPatch]
    internal static class MusicSuppressionPatch
    {
        [HarmonyPrefix]
        [HarmonyPatch(typeof(SoundMusicManager), nameof(SoundMusicManager.PlayIngame))]
        private static bool PlayIngamePrefix(SoundMusicManager __instance, bool isCard)
        {
            try
            {
                MusicEngine.NotePrefixContext(menuCall: false, isCard: isCard);
                if (!MusicEngine.TryShouldSuppress(menuCall: false, out bool suppress) || !suppress)
                    return true;
                __instance.PlayAmbience();   // mirror vanilla's first statement — ambience must survive suppression
                return false;
            }
            catch (Exception ex)
            {
                MusicEngine.LatchFaultFromPrefix("PlayIngame", ex);
                return true;
            }
        }

        [HarmonyPrefix]
        [HarmonyPatch(typeof(SoundMusicManager), nameof(SoundMusicManager.PlayMainMenu))]
        private static bool PlayMainMenuPrefix(SoundMusicManager __instance)
        {
            try
            {
                MusicEngine.NotePrefixContext(menuCall: true, isCard: false);
                if (!MusicEngine.TryShouldSuppress(menuCall: true, out bool suppress) || !suppress)
                {
                    // Uncovered menu while we were audible: hand off in the
                    // SAME call (pause our source) so vanilla menu music never
                    // overlaps our track for even a frame.
                    MusicEngine.NoteVanillaMenuHandoffNoThrow();
                    return true;
                }
                __instance.StopAmbience();   // mirror vanilla's first statement
                return false;
            }
            catch (Exception ex)
            {
                MusicEngine.LatchFaultFromPrefix("PlayMainMenu", ex);
                return true;
            }
        }

        /// <summary>PoisonSync pattern: runs after the class's patching pass;
        /// the final invocation (original == null) with no exception means
        /// every prefix attached.</summary>
        [HarmonyCleanup]
        private static Exception Cleanup(System.Reflection.MethodBase original, Exception exception)
        {
            if (original != null) return exception;
            if (exception == null) MusicEngine.SuppressionPatchLive = true;
            return exception;
        }
    }
}
