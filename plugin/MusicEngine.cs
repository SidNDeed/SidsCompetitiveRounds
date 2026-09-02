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
    /// engine-owned class stops the plugin sources, releases the vanilla
    /// suppression prefixes, and RE-ENTERS vanilla music for the CURRENT
    /// context (menu → PlayMainMenu, round → PlayIngame(false), pick →
    /// PlayIngame(true)) — never waiting for vanilla's next natural call,
    /// because in the menu there may be none [F11]. Loading is vanilla-audible
    /// ALWAYS, including when reached from Custom on playable-set loss.
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
        /// HELD for the life of the entry — DownloadHandlerAudioClip owns a
        /// streamed clip's buffers, so disposing the request would kill a clip
        /// mid-play. Static (survives host respawn) per the hazards list.</summary>
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
            // DURABLE by construction (a plain static field consumed only by
            // the engine tick, never cleared by respawns or scene loads);
            // consuming it enters faultDurable, which pins the desired mode at
            // Fault until an explicit user transport action retries.
            public volatile bool faultPending;
            public bool faultDurable;
            public string faultReason = "";

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
            public bool mainPausedByUs;                 // Pause()d (menu park / preview / PlayPause) — NOT ended
            public string queueSignature;               // selection+shuffle+broadcast fingerprint; null forces rebuild

            // Derived, refreshed by Reconcile (read by the side-effect-free
            // suppression decision, so they must stay plain cached bools).
            public bool selectionNonEmpty;
            public bool hasReadyTrack;
            public bool menuParked;                     // non-owned ONLY because the menu is uncovered; round entry resumes

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
        private static bool _lastMenuCovered;
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

        // ── transport ────────────────────────────────────────────────────

        internal static void PlayPause()
        {
            if (!_initialized) return;
            try
            {
                if (S.previewTrack.HasValue) { StopPreviewAndRestoreInternal("transport"); return; }
                ClearFaultForUserAction("PlayPause");
                var s = S;
                if (s.mode == MusicMode.Custom)
                {
                    s.paused = !s.paused;
                    if (s.paused) PauseMainNoThrow();
                    else Reconcile("play-pause");
                    return;
                }
                s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.manualTakeover = true;
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
                if (S.previewTrack.HasValue) { StopPreviewAndRestoreInternal("stop"); return; }
                ClearFaultForUserAction("Stop");
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

        /// <summary>Engine-local multiplier percent, 0..100 in 10% steps. A
        /// multiplier above 100 has no physical channel (AudioSource.volume
        /// clamps at 1 and the vanilla mixer already applies its own gain), so
        /// the stepper tops out at the vanilla-equivalent loudness.</summary>
        internal static int VolumeStepPercent
        {
            get { try { return Mathf.Clamp(Plugin.MusicVolume != null ? Plugin.MusicVolume.Value : 100, 0, 100); } catch { return 100; } }
        }

        internal static void VolumeUp() { SetVolume(VolumeStepPercent + 10); }
        internal static void VolumeDown() { SetVolume(VolumeStepPercent - 10); }

        private static void SetVolume(int pct)
        {
            try { if (Plugin.MusicVolume != null) Plugin.MusicVolume.Value = Mathf.Clamp((pct / 10) * 10, 0, 100); } catch { }
            // Applied by the per-frame volume pass; no Reconcile needed.
        }

        // ── now playing ──────────────────────────────────────────────────

        internal static string NowPlayingLine()
        {
            try
            {
                if (!TryGetNowPlaying(out var track, out var artist, out _)) return "";
                return I18n.TrF("Now Playing: {0} - {1}", track, artist);
            }
            catch { return ""; }
        }

        /// <summary>True while a track is actually sounding (Custom playing, or
        /// a preview snippet). Silent modes report false.</summary>
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
                var t = audible.Value;
                if (IsVanillaSku(t.Sku))
                {
                    if (t.Idx < 0 || t.Idx >= s.vanillaTracks.Count) return false;
                    track = s.vanillaTracks[t.Idx].Title; artist = VANILLA_ARTIST; album = VANILLA_ALBUM;
                    return true;
                }
                var a = MusicCatalog.Get(t.Sku);
                if (a == null || a.Tracks == null || t.Idx < 0 || t.Idx >= a.Tracks.Length) return false;
                track = a.Tracks[t.Idx].Title; artist = a.ArtistName; album = a.AlbumName;
                return true;
            }
            catch { return false; }
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
                // A throwing reconcile must fail TOWARD vanilla: silence our
                // sources, release suppression, restore vanilla, latch Fault.
                try
                {
                    S.faultDurable = true;
                    S.faultReason = "reconcile: " + ex.Message;
                    StopSourcesNoThrow();
                    S.suppress = false;
                    S.mode = MusicMode.Fault;
                    ReenterVanillaForContext();
                    Plugin.Log?.LogError($"[MUSIC] Reconcile({reason}) threw — durable Fault, vanilla restored: {ex}");
                }
                catch { }
            }
            finally { _inReconcile = false; }
        }

        private static void ReconcileCore(string reason)
        {
            var s = S;
            TickBroadcastEdges();
            RefreshDerivedState();

            MusicMode desired = ComputeDesiredMode();

            // Menu-cover rule: engine-owned playback covers the menu only when
            // (MenuMusicEnabled && selection non-empty) or the broadcast
            // predicate holds; otherwise PARK — vanilla menu music plays and
            // the engine resumes at the next in-game context. Preview is
            // exempt (shop previews happen at the menu by design).
            s.menuParked = false;
            if ((desired == MusicMode.Custom || desired == MusicMode.MutedByChoice)
                && s.ctx == Ctx.Menu && !MenuCovered())
            {
                s.menuParked = true;
                desired = MusicMode.Vanilla;
            }

            if (desired != s.mode) TransitionTo(desired, reason);
            else EnforceModeInvariants();

            _lastMenuCovered = MenuCovered();
        }

        private static MusicMode ComputeDesiredMode()
        {
            var s = S;
            if (_patchDead) return MusicMode.Vanilla;
            if (s.faultDurable) return MusicMode.Fault;
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
                catch (Exception ex) { LogOnce("sam", "[MUSIC] StopAllMusic failed: " + ex.Message, true); }
                s.suppress = true;
                ApplyOwnedPlayback();
            }
            else if (fromOwned && !toOwned)
            {
                // [G5] ownership-release invariant: stop plugin sources,
                // release suppression, re-enter vanilla for the CURRENT
                // context. Loading is vanilla-audible ALWAYS, including when
                // reached from Custom on playable-set loss.
                StopSourcesNoThrow();
                s.mainPausedByUs = false; s.currentStarted = false;
                s.suppress = false;
                ReenterVanillaForContext();
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

            Plugin.Log?.LogInfo($"[MUSIC] mode {prev} -> {desired} ({reason}, ctx={s.ctx}{(s.menuParked ? ", parked" : "")})");
        }

        /// <summary>Same-mode Reconcile: heal any suppress/ownership drift
        /// (e.g. a prefix fault released suppression and the fault was then
        /// user-cleared before the tick consumed it) and keep Custom fed.</summary>
        private static void EnforceModeInvariants()
        {
            var s = S;
            bool owned = IsEngineOwned(s.mode);
            if (owned && !s.suppress && !s.faultPending && !s.faultDurable)
            {
                try { SoundMusicManager.Instance?.StopAllMusic(); } catch { }
                s.suppress = true;
            }
            if (!owned && s.suppress) s.suppress = false;
            if (s.mode == MusicMode.Custom) ApplyOwnedPlayback();
        }

        private static void ApplyOwnedPlayback()
        {
            var s = S;
            switch (s.mode)
            {
                case MusicMode.Custom:
                    StopPreviewSourceNoThrow();
                    if (s.paused) PauseMainNoThrow();
                    else EnsureMainPlaying();
                    break;
                case MusicMode.MutedByChoice:
                    StopSourcesNoThrow();
                    s.mainPausedByUs = false; s.currentStarted = false;
                    break;
                case MusicMode.Preview:
                    PauseMainNoThrow();     // keep position; preview machinery drives the preview source
                    break;
            }
        }

        /// <summary>[F11] Immediately restore vanilla music for the context the
        /// prefixes last observed — vanilla's own replay guards make this
        /// idempotent, and our prefixes pass it through because suppression is
        /// already released when this is called.</summary>
        private static void ReenterVanillaForContext()
        {
            try
            {
                var mgr = SoundMusicManager.Instance;
                if (mgr == null) return;
                switch (S.ctx)
                {
                    case Ctx.Menu: mgr.PlayMainMenu(); break;
                    case Ctx.Round: mgr.PlayIngame(false); break;
                    case Ctx.Pick: mgr.PlayIngame(true); break;
                }
            }
            catch (Exception ex) { LogOnce("reenter", "[MUSIC] vanilla re-entry failed: " + ex.Message, true); }
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
                if (menuCall && s.mode != MusicMode.Preview && !MenuCovered()) return true; // park: vanilla menu plays
                suppress = s.suppress;   // normally true; a mid-fault window reads false and lets vanilla through
                return true;
            }
            // Parked-at-menu fast path: the first in-game call after a menu
            // park is suppressed HERE so vanilla in-game music never blips in
            // the frame before the tick's Reconcile re-enters Custom.
            if (!menuCall && s.menuParked && (s.stopIntent || s.hasReadyTrack)) { suppress = true; return true; }
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
            if (!menuCall && s.duckWanted != isCard) s.duckWanted = isCard;
        }

        /// <summary>Menu call passed through while we were audible (menu not
        /// covered): pause our main source in the SAME call so no frame has
        /// both owners playing; the tick's Reconcile then parks properly.</summary>
        internal static void NoteVanillaMenuHandoffNoThrow()
        {
            try
            {
                var s = S;
                if (s.mode == MusicMode.Custom && !s.paused) PauseMainNoThrow();
            }
            catch { }
        }

        /// <summary>[G13] The prefix exception path: latch FaultPending
        /// (durable static — survives host respawns; consumed only by the
        /// engine tick), release suppression, stop BOTH plugin sources via
        /// no-throw paths, and let the caller return true so vanilla runs.
        /// No frame can end with both owners playing.</summary>
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

        // ── engine tick (host Update — BepInEx never calls Plugin.Update) ─

        internal static void Tick()
        {
            if (!_initialized) return;
            try
            {
                var s = S;
                float rt = Time.realtimeSinceStartup;

                // FaultPending consumption → durable Fault [G13]. Custom stays
                // ineligible until an explicit user transport action retries.
                if (s.faultPending)
                {
                    s.faultPending = false;
                    s.faultDurable = true;
                    Plugin.Log?.LogError($"[MUSIC] entering durable Fault ({s.faultReason}) — vanilla music active until an explicit retry");
                    Reconcile("fault-latched");
                }

                if (_reconcileQueued) { _reconcileQueued = false; Reconcile(_reconcileQueuedReason ?? "queued"); }

                // Manager identity poll: SoundMusicManager is scene-local.
                if (rt - _managerPollRt > 0.5f)
                {
                    _managerPollRt = rt;
                    PollManagerIdentity();
                    // Menu-cover inputs can change outside Reconcile (config
                    // edit / cfg-lever reload); re-evaluate on the edge.
                    if (MenuCovered() != _lastMenuCovered) Reconcile("menu-cover-change");
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
                LogOnce("tick", "[MUSIC] tick failed: " + ex.Message, true);
            }
        }

        private static void TickPlayback(float rt)
        {
            var s = S;
            var h = _host;
            if (h == null) return;

            if (s.mode == MusicMode.Custom && !s.paused && !s.mainPausedByUs)
            {
                var m = h.Main;
                if (m != null && s.current.HasValue && s.currentStarted && !m.isPlaying
                    && rt - s.currentStartedRt > 0.5f)
                {
                    // Natural track end → advance (shuffle-cycle aware).
                    if (AdvanceToNext(userSkip: false)) { s.currentStarted = false; EnsureMainPlaying(); }
                    else Reconcile(s.stopIntent ? "playlist-end" : "no-ready-track");
                }
                else
                {
                    EnsureMainPlaying();
                    if (m != null && m.isPlaying) s.resumePositionSec = m.time;
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

            float mult = VolumeStepPercent / 100f;
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
                if (now && !S.broadcastHeld) { try { RunInBackgroundLease.Acquire("broadcast-music"); S.broadcastHeld = true; } catch { } }
                return false;
            }
            _lastBroadcastPredicate = now;
            S.queueSignature = null;    // selection override flips with the predicate
            if (now)
            {
                // Identity resolution: full-tier bootstrap + the background
                // lease so menu/idle playback ticks while unfocused [F18].
                try { if (!MusicAssets.TierReady(MusicTier.Full)) MusicAssets.EnsureTier(MusicTier.Full, "broadcast-identity"); } catch { }
                try { RunInBackgroundLease.Acquire("broadcast-music"); S.broadcastHeld = true; } catch { }
                Plugin.Log?.LogInfo("[MUSIC] broadcast custom-music predicate ON");
            }
            else if (S.broadcastHeld)
            {
                try { RunInBackgroundLease.Release("broadcast-music"); } catch { }
                S.broadcastHeld = false;
                Plugin.Log?.LogInfo("[MUSIC] broadcast custom-music predicate OFF");
            }
            return true;
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
                // set ignored [F17].
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

        private static bool ShuffleEffective() => ShuffleEnabled || BroadcastPredicate();
        private static bool LoopEffective() => LoopEnabled || BroadcastPredicate();

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
            s.queue = ShuffleEffective() ? BuildDispersionCycle(sel, s.current) : sel;
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

        /// <summary>Advance to the next READY track. At the cycle boundary:
        /// loop off → run-out (deliberate MutedByChoice via stopIntent); loop
        /// on + shuffle → a fresh dispersion cycle whose first track differs
        /// from the one just played.</summary>
        private static bool AdvanceToNext(bool userSkip)
        {
            var s = S;
            EnsureQueueCurrent();
            int n = s.queue.Count;
            if (n == 0) { s.current = null; return false; }
            int start = s.queueIndex;
            for (int step = 1; step <= n; step++)
            {
                int i = start + step;
                if (i >= n)
                {
                    if (!LoopEffective() && !userSkip)
                    {
                        s.stopIntent = true;
                        Plugin.Log?.LogInfo("[MUSIC] playlist ended (loop off)");
                        return false;
                    }
                    if (i == n && ShuffleEffective())
                    {
                        s.queue = BuildDispersionCycle(BuildEffectiveSelection(), s.current);
                        n = s.queue.Count;
                        if (n == 0) { s.current = null; return false; }
                    }
                    i %= n;
                }
                var t = s.queue[i];
                if (IsTrackReady(t))
                {
                    s.queueIndex = i;
                    s.current = t;
                    s.resumePositionSec = 0f;
                    s.currentStarted = false;
                    s.mainPausedByUs = false;
                    return true;
                }
                KickLoad(t);
            }
            return false;   // nothing ready — Reconcile parks at Loading (vanilla audible)
        }

        // ── clip loading (UnityWebRequest, streamed OGG) ─────────────────

        private static bool IsTrackReady(TrackRef t)
        {
            if (IsVanillaSku(t.Sku)) return t.Idx >= 0 && t.Idx < S.vanillaTracks.Count && S.vanillaTracks[t.Idx].Clip != null;
            return Clips.TryGetValue(t.ToString(), out var e) && e.Clip != null;
        }

        private static bool ScanHasReadyTrack()
        {
            var s = S;
            if (s.current.HasValue && IsTrackReady(s.current.Value)) return true;
            var q = s.queue;
            for (int i = 0; i < q.Count; i++) if (IsTrackReady(q[i])) return true;
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
                if (dh != null) dh.streamAudio = true;   // FMOD streams from disk: sub-MB resident per active stream
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
            if (!s.current.HasValue && !AdvanceToNext(userSkip: false)) return;
            if (!s.current.HasValue) return;
            var clip = ResolveReadyClip(s.current.Value);
            if (clip == null) { KickLoad(s.current.Value); return; }
            var m = h.Main;
            if (m.clip != clip) { m.clip = clip; s.currentStarted = false; s.mainPausedByUs = false; }
            if (m.isPlaying) return;
            if (s.mainPausedByUs && s.currentStarted)
            {
                try { m.UnPause(); } catch { }
                s.mainPausedByUs = false;
                return;
            }
            try
            {
                float pos = s.resumePositionSec;
                m.time = (pos > 0.5f && pos < clip.length - 1f) ? pos : 0f;
            }
            catch { }
            m.Play();
            s.currentStarted = true;
            s.currentStartedRt = Time.realtimeSinceStartup;
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

        private static void PauseMainNoThrow()
        {
            try
            {
                var h = _host;
                if (h == null || h.Main == null) return;
                if (h.Main.isPlaying)
                {
                    S.resumePositionSec = h.Main.time;
                    h.Main.Pause();
                    S.mainPausedByUs = true;
                }
            }
            catch { }
        }

        /// <summary>Stops BOTH sources; every statement individually guarded so
        /// this is safe from the prefix exception path (must-verify item).</summary>
        internal static void StopSourcesNoThrow()
        {
            var h = _host;
            if (h == null) return;
            try { var m = h.Main; if (m != null) m.Stop(); } catch { }
            try { var p = h.Preview; if (p != null) p.Stop(); } catch { }
        }

        private static void StopPreviewSourceNoThrow()
        {
            try { var h = _host; if (h != null && h.Preview != null) h.Preview.Stop(); } catch { }
        }

        private static void StopMainNoThrow()
        {
            try { var h = _host; if (h != null && h.Main != null) h.Main.Stop(); } catch { }
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
                    Plugin.Log?.LogError("[MUSIC] vanilla album enumeration yielded ZERO _Game clips — vanilla OST album absent; engine fails open to vanilla behavior");
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
                }
                EvictUnplayableClips();
                s.queueSignature = null;
                Reconcile("entitlements-changed");
            }
            catch (Exception ex) { LogOnce("entchg", "[MUSIC] entitlements-changed handler failed: " + ex.Message, true); }
        }

        // ── fault retry ──────────────────────────────────────────────────

        /// <summary>The "explicit Retry" that makes Custom eligible again after
        /// a durable Fault: any deliberate transport action. There is no
        /// automatic health probe — if the cause persists, the next prefix
        /// throw re-latches within a frame.</summary>
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

        // ── menu-cover rule ──────────────────────────────────────────────

        private static bool MenuCovered()
        {
            if (BroadcastPredicate()) return true;
            try { return Plugin.MenuMusicEnabled != null && Plugin.MenuMusicEnabled.Value && S.selectionNonEmpty; }
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
                if (s.broadcastHeld) { try { RunInBackgroundLease.Acquire("broadcast-music"); } catch { } }
                Reconcile("host-respawn");
            }
            catch (Exception ex) { LogOnce("rehydrate", "[MUSIC] rehydrate failed: " + ex.Message, true); }
        }

        internal static void OnHostDestroyed(MusicEngineHost dying)
        {
            if (!ReferenceEquals(_host, dying)) return;
            _host = null;
            if (_quitting) return;
            SpawnHost();
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
