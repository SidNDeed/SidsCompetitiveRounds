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
            public readonly string Sku;
            public readonly int Idx;
            public readonly string Key;   // r3 LOW 16: "sku/idx" built ONCE — ToString allocates nothing on the Waiting hot path
            public TrackRef(string sku, int idx) { Sku = sku; Idx = idx; Key = sku + "/" + idx; }
            public bool Equals(TrackRef o) => Idx == o.Idx && string.Equals(Sku, o.Sku, StringComparison.Ordinal);
            public override string ToString() => Key;
            /// <summary>Inverse of ToString for the residency key set ("sku/idx").</summary>
            public static bool TryParse(string key, out TrackRef t)
            {
                t = default;
                if (string.IsNullOrEmpty(key)) return false;
                int slash = key.LastIndexOf('/');
                if (slash <= 0 || slash >= key.Length - 1) return false;
                if (!int.TryParse(key.Substring(slash + 1), System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out int idx)) return false;
                t = new TrackRef(key.Substring(0, slash), idx);
                return true;
            }
        }

        private sealed class VanillaTrack
        {
            public string RawName;
            public string Title;
            public AudioClip Clip;
        }

        /// <summary>One loading or open disk clip. Lifecycle (design v2 §2.3,
        /// bug 346): request (a file:// read of the compressed OGG) →
        /// Downloaded (completed, not yet opened) → open (OpenStreamedClip:
        /// GetContent on a streamAudio=true handler hands back a clip whose
        /// samples FMOD decodes from the handler's buffer on its own stream
        /// thread — a 2-5 ms handle, no main-thread decode). The request is
        /// therefore RETAINED as ReqKeep for as long as the clip exists, and
        /// the two leave together as one PendingRelease pair when the key
        /// leaves the residency window (§7 2-4). Static (survives host
        /// respawn) per the hazards list.</summary>
        private sealed class ClipEntry
        {
            public string Key;
            public UnityWebRequest Req;       // in flight, or completed and awaiting its open
            public UnityWebRequest ReqKeep;   // the open clip's backing request — never disposed before the clip
            public AudioClip Clip;
            public bool Failed;
            public bool Downloaded;           // request completed; the open runs on a following tick (one per frame)
            public int RequestedFrame;
        }

        /// <summary>§7 2-4 as rebuilt by impl2 r2 (DETACH-OR-RETIRE): an
        /// evicted entry travels as one pair. Step 1 — the clip may be
        /// Destroyed only when EVERY listed host (rule a) is either observed
        /// destroyed or has both sources cleanly detached from the clip
        /// (rule b: Stop returned, `clip = null` returned, a same-frame
        /// read-back of null). A source that fails that in ANY way — an
        /// exception anywhere, a read-back still bound — is never retried: its
        /// whole host is retired (Destroy of the GameObject, so the
        /// AudioSources and their native voices die with it at end of frame,
        /// #278) and the pair waits for that host to be observed destroyed on
        /// a later frame (rule c). Step 1 is re-evaluated by every sweep —
        /// that is an observation of the host list, not a retry of a detach.
        /// Step 2, in the sweep on a later frame than the Destroy: Dispose the
        /// request. A pair still at step 1 RELEASE_DETACH_WINDOW_SEC after
        /// eviction, or whose clip Destroy threw, is HELD for the session:
        /// never destroyed, never disposed, one `[MUSIC-RELEASE] held:` line,
        /// still counted by the ledger (rule d — a retained buffer is the safe
        /// failure direction, a buffer freed under a live voice is not, #276).
        /// A step 2 that throws retries at most twice a second and is never
        /// held: its clip is already gone, so nothing reads the buffer.</summary>
        private struct PendingReleaseEntry
        {
            public string Key;
            public AudioClip Clip;            // null for an entry that never opened (request only)
            public UnityWebRequest Req;
            public bool Destroyed;            // step 1 done (vacuous when Clip is null)
            public int DestroyedFrame;        // frame of the Destroy call; step 2 waits past it
            public int DisposeAttempts;
            public float QueuedRt;            // realtimeSinceStartup at eviction: the detach window and the self-test's pair age count from here
            public bool Held;                 // step 1 never completed inside the window, or the clip Destroy threw: retained for the session, still counted by the ledger
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
            public string takeoverKey;                  // r3 MEDIUM 3: the ONE explicitly PlayTrack'd key that may play while deselected (null = none)
            public string takeoverSelectionSig;         // the queue signature that PlayTrack was made against — a later selection mutation supersedes it

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

            // ── lag-332 design v6 (W6-A) ──────────────────────────────────
            // WaitingForNext [v4 §2.3, CONFIRMED d4/d5]: the current track
            // loops on itself because its successor is not resident; every
            // exit clears Main.loop (ExitWaiting is the ONLY writer of
            // waiting=false — StopSources and host respawn call it too).
            public bool waiting;
            // Fade-in envelope [v4 §2.5]: progress-based, advances only while
            // Main is audibly playing; armed right after a successful Play().
            public bool fadeActive;
            public float fadeProgress = 1f;
            public int fadeArmFrame = -1;
            // previewSlot Pending bookkeeping (r1 MEDIUM 9): a pending preview
            // that never becomes resident is dropped after this many seconds.
            public float previewPendingRt = -1f;
            // Persisted next shuffle cycle [v6 §2.2]: built ONCE at the tail
            // of a shuffled cycle so residency (the successor key) and
            // traversal (the wrap) consume the same order. Bound to the queue
            // signature it was built under.
            public List<TrackRef> nextCycle;
            public string nextCycleSignature;
            // previewSlot [v6 §2.2]: Pending (clicked, not yet resident),
            // Active (= previewTrack), Retained (last finished preview stays
            // resident and playable anywhere until replaced).
            public TrackRef? previewPending;
            public TrackRef? previewRetained;
            // Vanilla re-entry verification attempts [v4 §2.5 oracle].
            public int reentryAttempts;
        }

        private static readonly EngineState S = new EngineState();
        private static readonly Dictionary<string, ClipEntry> Clips = new Dictionary<string, ClipEntry>(StringComparer.Ordinal);
        // §7 2-4: evicted {clip, request} pairs awaiting their two-step release.
        private static readonly List<PendingReleaseEntry> PendingRelease = new List<PendingReleaseEntry>();
        /// <summary>r5 LOW 9: bumped on every request/clip state transition so
        /// the Music tab's 2 s repaint signature sees Downloaded/Failed/open
        /// changes (the status line repaints without a click).</summary>
        internal static int ClipStateGeneration;
        /// <summary>The residency window: at most this many ENTRIES (current,
        /// successor, preview) may hold a request or a clip at once. Request
        /// admission counts entries (§7 2-3); the object ledger
        /// (LiveObjectCount) is diagnostic only and never an admission input.</summary>
        private const int RESIDENT_KEY_CAP = 3;
        private static readonly HashSet<string> OnceKeys = new HashSet<string>(StringComparer.Ordinal);
        private static readonly System.Random Rng = new System.Random();

        private static MusicEngineHost _host;
        /// <summary>impl2 r2 rule (a): every host this engine ever created,
        /// listed until its GameObject is OBSERVED destroyed (Unity's
        /// overloaded null) on a later frame — PruneObservedNullHosts is the
        /// ONLY remover. Not the component's OnDestroy (after a
        /// component-only Destroy the GameObject and its two AudioSources
        /// outlive it), not a failed silence, not a respawn. The release
        /// pair's step 1 walks this list (rule c) and RetireOtherHosts retires
        /// every entry still listed at a new host's adoption (rule f).</summary>
        private sealed class HostEntry
        {
            public MusicEngineHost Host;      // the component; its Main/Preview fields stay readable after Unity destroys it
            public GameObject Go;             // the object whose observed destruction removes the entry
            public bool Retired;              // Destroy(Go) was issued (or threw): issued once, logged once (rules b/f)
            public int RetiredFrame;
            public string RetiredWhy;
        }
        private static readonly List<HostEntry> Hosts = new List<HostEntry>();
        /// <summary>Rule (e): set by RetireHost when the retired entry was the
        /// adopted host; drained by TickPlayback on a LATER frame, after that
        /// host's OnDestroy has (or has not) respawned a fresh one.</summary>
        private static string _hostRetiredPending;
        private static int _hostRetiredFrame;
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

        /// <summary>[MUSIC-OPEN] measurement: key of the clip opened on the
        /// previous tick, so the following frame's dt (which carries the open)
        /// can be logged too — the §7 2-9 open_block bar.</summary>
        private static string _openLogNextFrame;

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
        // Design v2 §2.3.6 / §7 2-7: a streamed source reports AudioSource.time
        // in packet-coarse steps near EOF, so the near-end arm and the natural
        // classification use a 4 s window (was 2 s for buffered clips).
        private const float EOF_WINDOW_SEC = 4f;

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
                    // Pause/resume continues the SAME intent on the SAME track — an
                    // explicit PlayTrack takeover survives it (impl note 19 as amended
                    // after r4 LOW 8); Skip/Previous/adoption/Use vanilla/a selection
                    // change end it.
                    s.paused = !s.paused;
                    if (s.paused) { if (!PauseMain()) EnterDurableFaultNoThrow("pause failed"); }   // [I1-residual]
                    else Reconcile("play-pause");
                    return;
                }
                s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                s.manualTakeover = true;
                s.takeoverKey = null;   // r3 MEDIUM 3: an ordinary transport ends an explicit takeover
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
                s.takeoverKey = null;   // r3 MEDIUM 3
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
                s.takeoverKey = null;   // r3 MEDIUM 3
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
                int r = TryPrevious(out int predIndex, out var pred);
                if (r == 0)
                {
                    // v6 §2.2: an unresident predecessor. At the admissible menu
                    // it becomes the explicit desired target (parks at Loading
                    // per [S1]; the engine's tick opens it once its file is
                    // read). In a room the current track keeps playing
                    // and the UI says so — never a silent forward wrap.
                    if (MusicAdmission.AtAdmissibleMenu)
                    {
                        ExitWaiting("previous-target");
                        s.queueIndex = predIndex;
                        s.current = pred;
                        s.resumePositionSec = 0f; s.currentStarted = false; s.mainPausedByUs = false;
                        s.currentPrematureRetried = false; s.currentEnded = false;
                        ReconcileResidency();
                    }
                    else
                    {
                        try { CompetitiveUI.ShowNotification(I18n.Tr("Previous track is not loaded yet — use Previous at the main menu"), new Color(1f, 0.85f, 0.4f), 4f); } catch { }
                        return;
                    }
                }
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
                // that previously failed to open.
                if (!IsVanillaSku(albumSku)) ClearTombstone(t.ToString());   // r3 MEDIUM 2: explicit retry of THIS key
                var s = S;
                ExitWaiting("play-track");   // v6 §2.3
                s.manualTakeover = true; s.stopIntent = false; s.vanillaPreferred = false; s.paused = false;
                // r3 MEDIUM 3: the takeover binds to THIS key and to the selection
                // it was made against (see EnsureQueueCurrent).
                s.takeoverKey = IsVanillaSku(albumSku) ? null : t.ToString();
                s.current = t; s.resumePositionSec = 0f; s.currentStarted = false; s.mainPausedByUs = false;
                s.currentPrematureRetried = false;
                s.currentEnded = false;   // [N6c] explicit selection — this current is a playable again
                s.queueSignature = null;
                s.takeoverSelectionSig = ComputeQueueSignature();
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
                s.takeoverKey = null;
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
                // impl-review r1 MEDIUM 10: Waiting exists only under loop-on; turning
                // loop off must release the looped current immediately.
                if (!value) ExitWaiting("loop-off");
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
                // lag-332 v6 §2.2/§2.4 previewSlot: ownership changes ONLY once
                // the preview clip is RESIDENT. An uncached preview becomes the
                // Pending slot: its request starts now and PollClipLoads opens
                // it first once the read completes (§7 2-5), which starts the
                // ownership through StartPendingPreviewOwnership;
                // outside the admissible menu it is refused outright (v3 §2.4).
                string pkey = "p:" + t;
                bool resident = Clips.TryGetValue(pkey, out var pe) && pe.Clip != null;
                if (!resident)
                {
                    if (!MusicAdmission.AtAdmissibleMenu)
                    {
                        try { CompetitiveUI.ShowNotification(I18n.Tr("Previews load at the main menu"), new Color(1f, 0.85f, 0.4f), 3f); } catch { }
                        return;
                    }
                    // r3 MEDIUM 5 / r4 MEDIUM 5: clicking the SAME Pending preview again
                    // is a no-op that keeps its original admission time — rewriting it
                    // reset the 30 s timer to "never started".
                    if (s.previewPending.HasValue && s.previewPending.Value.Equals(t) && !IsFailedKey(pkey))
                    {
                        Plugin.Log?.LogInfo($"[MUSIC] preview {t} still pending (unchanged)");
                        return;
                    }
                    // An explicit Preview click on a tombstoned key is its retry (r3 MEDIUM 2).
                    ClearTombstone(pkey);
                    // r1 MEDIUM 9 / r2 MEDIUM 12 (transactional replacement): an
                    // ACTIVE preview P keeps playing and keeps its slot; Q is
                    // recorded as the Pending intent and P AND Q are BOTH desired
                    // for the duration (the successor yields — DesiredKeys); Q's
                    // request starts now; P is displaced only after Q opened and
                    // took ownership. A Pending Q that fails or times out is
                    // dropped (Tick) and the slot falls back to whatever is retained.
                    s.previewPending = t;
                    s.previewPendingRt = Time.realtimeSinceStartup;   // §7 2-3: the 30 s timeout counts from the click
                    ReconcileResidency();       // the transaction {current, P, Q} requests Q now; the successor yields meanwhile
                    Plugin.Log?.LogInfo($"[MUSIC] preview pending {t} — starts once its file is read");
                    return;
                }
                if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal("preview-replace");   // Q is resident: atomic swap
                StartPreviewOwnership(t);
            }
            catch (Exception ex) { LogOnce("tp", "[MUSIC] TogglePreview failed: " + ex.Message, true); }
        }

        /// <summary>Called by OpenStreamedClip's completion bridge when the
        /// Pending preview's clip just became resident.</summary>
        private static void StartPendingPreviewOwnership()
        {
            var s = S;
            if (!s.previewPending.HasValue) return;
            var t = s.previewPending.Value;
            if (!(Clips.TryGetValue("p:" + t, out var pe) && pe.Clip != null)) return;
            StartPreviewOwnership(t);
        }

        private static void StartPreviewOwnership(TrackRef t)
        {
            try
            {
                var s = S;
                s.previewPending = null;
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
                Reconcile("preview-start");
            }
            catch (Exception ex) { LogOnce("tp", "[MUSIC] preview ownership failed: " + ex.Message, true); }
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
            // r2 MEDIUM 12: tab/overlay teardown clears a Pending intent too, or
            // a Pending Q outlives the surface that asked for it.
            if (s.previewPending.HasValue) { s.previewPending = null; ReconcileResidency(); }
            if (!s.previewTrack.HasValue) return;
            // v6 §2.2 previewSlot: the finished preview is RETAINED (resident,
            // playable anywhere) until another preview replaces it.
            s.previewRetained = s.previewTrack;
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

            // v6 §2.2: every reconcile is a desired-set checkpoint — selection,
            // shuffle/loop, entitlement, broadcast predicate and transport
            // changes all route through here.
            ReconcileResidency();

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
            if (SelectionUniverseEmpty()) return MusicMode.Vanilla;          // nothing to manage — fail open
            // r3 MEDIUM 3: an explicit PlayTrack takeover plays its ONE track
            // regardless of the selection; ordinary transport history never
            // overrides "deselected everything".
            if (s.takeoverKey != null) return s.hasReadyTrack ? MusicMode.Custom : MusicMode.Loading;
            // music v3 §4: every track unchecked = Vanilla, the same value and
            // reason as the empty universe above (nothing to manage). Vanilla
            // is non-owned like Loading, so TransitionTo runs the same [G5]
            // release. Within this method MutedByChoice is returned only for
            // stopIntent (Stop, loop-off run-out); Reconcile's menu branch
            // adds the menu "silent" setting.
            if (!s.selectionNonEmpty) return MusicMode.Vanilla;
            if (s.manualTakeover) return s.hasReadyTrack ? MusicMode.Custom : MusicMode.Loading;
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
                    // v4 §2.5 compensation: the wrapper's play guards may be
                    // left asserting a music that was partly stopped — clear
                    // both so the fail-open re-entry is not a no-op.
                    ClearVanillaGuardsNoThrow();
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
                // v6 §2.3: a parked/released Waiting source restarts at zero
                // when ownership returns (resume position cleared).
                if (s.waiting) { s.resumePositionSec = 0f; ExitWaiting("release"); }
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
                s.reentryAttempts = 0;
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
                    // v6 §2.3: preview OWNERSHIP is a Waiting exit; a parked
                    // Waiting source restarts at zero when Custom resumes.
                    if (s.waiting) { s.resumePositionSec = 0f; ExitWaiting("preview"); }
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
        /// <summary>Re-enter vanilla music for the current context and VERIFY
        /// it (lag-332 v4 §2.5, d4-confirmed oracle): the wrapper's own
        /// guard flags are set BEFORE it calls Sonigon and prove nothing
        /// (SoundMusicManager.cs:33-79), so certification requires Sonigon's
        /// GetSoundEventState(event, musicOwner) == Playing. Delayed = still
        /// pending (retry, guard kept). NotPlaying / a throw / a missing
        /// oracle = the guard this attempt set is CLEARED so the next retry
        /// is not a wrapper no-op; after REENTRY_MAX_ATTEMPTS the engine
        /// fails open and logs UNVERIFIED rather than certifying.</summary>
        private const int REENTRY_MAX_ATTEMPTS = 20;
        private static bool ReenterVanillaForContext()
        {
            var s = S;
            SoundMusicManager mgr;
            try { mgr = SoundMusicManager.Instance; } catch { return false; }
            if (mgr == null) return false;
            bool menu = s.ctx == Ctx.Menu;
            s.reentryAttempts++;
            try
            {
                switch (s.ctx)
                {
                    case Ctx.Menu: mgr.PlayMainMenu(); break;
                    case Ctx.Round: mgr.PlayIngame(false); break;
                    case Ctx.Pick: mgr.PlayIngame(true); break;
                }
            }
            catch (Exception ex)
            {
                // Snapshot BEFORE the clear (dV2 MEDIUM 6): the dump must show
                // the guard as the wrapper left it, or it settles nothing.
                string dumpT = s.reentryAttempts >= REENTRY_MAX_ATTEMPTS ? OracleDump(mgr) : null;
                ClearVanillaGuard(mgr, menu);
                LogOnce("reenter", "[MUSIC] vanilla re-entry threw: " + ex.Message + " — will retry from the tick", true);
                return s.reentryAttempts >= REENTRY_MAX_ATTEMPTS && FailOpenUnverified(mgr, menu, "threw", dumpT);
            }
            var state = VanillaMusicState(mgr, menu);
            // Same rule for the oracle paths: the snapshot precedes every clear.
            string dump = s.reentryAttempts >= REENTRY_MAX_ATTEMPTS ? OracleDump(mgr) : null;
            switch (state)
            {
                case OracleState.Playing:
                    Plugin.Log?.LogInfo($"[MUSIC-WD] vanilla re-entered ctx={s.ctx} (verified Playing, attempt {s.reentryAttempts})");
                    s.reentryAttempts = 0;
                    return true;
                case OracleState.Delayed:
                    return s.reentryAttempts >= REENTRY_MAX_ATTEMPTS && FailOpenUnverified(mgr, menu, "still Delayed", dump);
                case OracleState.NotPlaying:
                    ClearVanillaGuard(mgr, menu);
                    return s.reentryAttempts >= REENTRY_MAX_ATTEMPTS && FailOpenUnverified(mgr, menu, "NotPlaying", dump);
                default:
                    // Oracle unavailable: never certify from the flag — and clear
                    // the guard this attempt set so the next retry is not a
                    // wrapper no-op (r1 MEDIUM 11).
                    ClearVanillaGuard(mgr, menu);
                    return s.reentryAttempts >= REENTRY_MAX_ATTEMPTS && FailOpenUnverified(mgr, menu, "oracle unavailable", dump);
            }
        }

        private static bool FailOpenUnverified(SoundMusicManager mgr, bool menu, string why, string dump)
        {
            // Failing open must not strand a set-but-silent wrapper guard: clear
            // it so vanilla's own next Play* call is a real call (r1 MEDIUM 11).
            // The dump was taken by the caller BEFORE its own clear
            // (music-v7-design.md §2.4): a Sept 3 desktop log carried
            // "UNVERIFIED (NotPlaying)" at the first card pick with nothing to
            // say whether the oracle watched the wrong Sonigon event or the pick
            // music really stayed silent.
            if (dump == null) dump = OracleDump(mgr);
            ClearVanillaGuard(mgr, menu);
            LogOnce("reenter-unverified", $"[MUSIC-WD] vanilla re-entry UNVERIFIED ({why}) after {REENTRY_MAX_ATTEMPTS} attempts — failing open; ctx={S.ctx} {dump}", true);
            return true;
        }

        /// <summary>Diagnostic snapshot for the UNVERIFIED line: the wrapper's
        /// two guard flags and Sonigon's state for BOTH music events (menu and
        /// ingame), whichever the context expects. Best-effort; a missing piece
        /// prints '?' rather than throwing.</summary>
        private static string OracleDump(SoundMusicManager mgr)
        {
            try
            {
                ResolveOracle();
                string gMenu = "?", gIngame = "?", sMenu = "?", sIngame = "?";
                try { if (_wrapperMenuGuard != null && mgr != null) gMenu = (_wrapperMenuGuard.GetValue(mgr) is bool b1 && b1) ? "1" : "0"; } catch { }
                try { if (_wrapperIngameGuard != null && mgr != null) gIngame = (_wrapperIngameGuard.GetValue(mgr) is bool b2 && b2) ? "1" : "0"; } catch { }
                try { sMenu = VanillaMusicState(mgr, true).ToString(); } catch { }
                try { sIngame = VanillaMusicState(mgr, false).ToString(); } catch { }
                return "guard_menu=" + gMenu + " guard_ingame=" + gIngame + " sonigon_menu=" + sMenu + " sonigon_ingame=" + sIngame;
            }
            catch (Exception ex) { return "dump_failed=" + ex.GetType().Name; }
        }

        private enum OracleState { Unavailable, NotPlaying, Delayed, Playing }

        // Sonigon is deliberately unreferenced by the csproj; the oracle is
        // reached by reflection (cached), all failure → Unavailable.
        private static Type _sonigonMgrType;
        private static System.Reflection.PropertyInfo _sonigonInstanceProp;
        private static System.Reflection.MethodInfo _sonigonGetMusicTransform, _sonigonGetState;
        private static System.Reflection.FieldInfo _wrapperMenuEvent, _wrapperIngameEvent, _wrapperMenuGuard, _wrapperIngameGuard;
        private static bool _oracleResolved;

        private static void ResolveOracle()
        {
            if (_oracleResolved) return;
            _oracleResolved = true;
            try
            {
                _sonigonMgrType = AccessTools.TypeByName("Sonigon.SoundManager");
                if (_sonigonMgrType != null)
                {
                    _sonigonInstanceProp = AccessTools.Property(_sonigonMgrType, "Instance");
                    _sonigonGetMusicTransform = AccessTools.Method(_sonigonMgrType, "GetMusicTransform");
                    _sonigonGetState = AccessTools.Method(_sonigonMgrType, "GetSoundEventState");
                }
                _wrapperMenuEvent = AccessTools.Field(typeof(SoundMusicManager), "musicMainMenu");
                _wrapperIngameEvent = AccessTools.Field(typeof(SoundMusicManager), "musicIngame");
                _wrapperMenuGuard = AccessTools.Field(typeof(SoundMusicManager), "musicMainMenuPlaying");
                _wrapperIngameGuard = AccessTools.Field(typeof(SoundMusicManager), "musicIngamePlaying");
            }
            catch (Exception ex) { LogOnce("oracle", "[MUSIC-WD] oracle resolve failed: " + ex.Message, true); }
        }

        private static OracleState VanillaMusicState(SoundMusicManager mgr, bool menu)
        {
            try
            {
                ResolveOracle();
                if (_sonigonInstanceProp == null || _sonigonGetMusicTransform == null || _sonigonGetState == null) return OracleState.Unavailable;
                var evField = menu ? _wrapperMenuEvent : _wrapperIngameEvent;
                if (evField == null) return OracleState.Unavailable;
                object snd = _sonigonInstanceProp.GetValue(null, null);
                if (snd == null) return OracleState.Unavailable;
                object ev = evField.GetValue(mgr);
                if (ev == null) return OracleState.Unavailable;
                object owner = _sonigonGetMusicTransform.Invoke(snd, null);
                object st = _sonigonGetState.Invoke(snd, new object[] { ev, owner });
                int v = Convert.ToInt32(st);
                // Sonigon.SoundEventState: NotPlaying=0, Delayed=1, Playing=2.
                return v == 2 ? OracleState.Playing : v == 1 ? OracleState.Delayed : OracleState.NotPlaying;
            }
            catch { return OracleState.Unavailable; }
        }

        private static void ClearVanillaGuard(SoundMusicManager mgr, bool menu)
        {
            try
            {
                ResolveOracle();
                var f = menu ? _wrapperMenuGuard : _wrapperIngameGuard;
                if (f != null && mgr != null) f.SetValue(mgr, false);
            }
            catch { }
        }

        private static void ClearVanillaGuardsNoThrow()
        {
            try
            {
                var mgr = SoundMusicManager.Instance;
                if (mgr == null) return;
                ClearVanillaGuard(mgr, true);
                ClearVanillaGuard(mgr, false);
            }
            catch { }
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
            // suppresses (silence is the point — ComputeDesiredMode yields
            // MutedByChoice only for stopIntent, Stop or a loop-off run-out,
            // so that is what a parked one is); parked Custom suppresses only
            // while a track is still ready, so a readiness loss cannot
            // swallow the only vanilla call of a Loading round.
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
            if (s.ctx != c)
            {
                bool leavingMenu = s.ctx == Ctx.Menu && c != Ctx.Menu;
                s.ctx = c; s.ctxDirty = true;
                if (leavingMenu)
                {
                    // v6 §2.2: a Pending preview intent does not survive the menu.
                    if (s.previewPending.HasValue) { s.previewPending = null; }
                }
            }
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
                // v6 §2.3: the menu park is a Waiting exit (restart at zero on resume).
                if (s.waiting) { s.resumePositionSec = 0f; ExitWaiting("menu-park"); }
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
                s.reentryAttempts = 0;   // r1 MEDIUM 11: every independent re-entry arc starts its own attempt budget
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

                // r7 MEDIUM 1: a current whose REQUEST START failed inside a
                // residency pass recovers here, first, before any readiness edge
                // below could acquire Custom around the dead current.
                DrainFailedCurrent();

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

                // The admission snapshot is observed every frame: ClickAdmissible
                // still serves EmojiSprites' safe-state gate and AtAdmissibleMenu
                // the cold Previous / uncached-preview branches (§7 keeps both).
                MusicAdmission.Tick();
                SweepPendingRelease();

                // Requests (a file read of the compressed OGG — never a decode)
                // for the desired keys, re-polled because a tier that finishes
                // installing fires no event. Bounded by the residency window.
                if (rt - _loadingKickRt > 1f)
                {
                    _loadingKickRt = rt;
                    EnsureQueueCurrent();
                    KickDesiredLoads();
                }

                if (_openLogNextFrame != null)
                {
                    // Second half of the [MUSIC-OPEN] measurement: the frame AFTER
                    // an open (its unscaledDeltaTime is the open frame's wall length).
                    try { Plugin.Log?.LogInfo($"[MUSIC-OPEN-NEXT] key={_openLogNextFrame} nextFrameDtMs={(Time.unscaledDeltaTime * 1000f).ToString("F0", System.Globalization.CultureInfo.InvariantCulture)}"); } catch { }
                    _openLogNextFrame = null;
                }
                // Completion polling + at most ONE open per frame (a Pending
                // preview's entry first) — OpenStreamedClip runs the readiness
                // bridge itself (design v2 §2.3.1).
                PollClipLoads();

                // §7 2-5: the Pending-preview timeout is judged AFTER the poll,
                // so a read that completed this frame is opened before the 30 s
                // clock can drop it. r1 MEDIUM 9: a Pending preview whose request
                // failed or that never became resident within 30 s returns the
                // slot to Empty (the retained preview, if any, is desired again).
                if (s.previewPending.HasValue)
                {
                    string ppk = "p:" + s.previewPending.Value;
                    bool failed = Clips.TryGetValue(ppk, out var ppe) && ppe.Failed;
                    if (failed || (s.previewPendingRt >= 0f && rt - s.previewPendingRt > 30f))
                    {
                        Plugin.Log?.LogInfo($"[MUSIC] preview pending {s.previewPending.Value} dropped ({(failed ? "request failed" : "timeout")})");
                        s.previewPending = null;
                        if (failed) { Clips.Remove(ppk); DisposeEntry(ppe); }
                        ReconcileResidency();
                    }
                }

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
            // impl2 r2 rule (e): the adopted host was retired on an EARLIER
            // frame (a source of it failed rule b). Its OnDestroy respawned a
            // fresh host at that frame's end, and the rehydration cleared
            // currentStarted, so EnsureMainPlaying below restarts the current
            // from resumePositionSec — charged here as the classifier's ONE
            // counted resume (a stalled death, §7 2-7): a second death of this
            // track is the durable fault it would be anywhere else. No fresh
            // host (the Destroy threw, the respawn failed) is a durable fault
            // outright — nothing can own playback.
            if (_hostRetiredPending != null && Time.frameCount > _hostRetiredFrame)
            {
                string why = _hostRetiredPending;
                _hostRetiredPending = null;
                if ((object)h == null || HostIsRetired(h))
                {
                    if (!s.faultDurable) EnterDurableFaultNoThrow("host-retired without a respawn: " + why);
                    return;
                }
                if (s.mode == MusicMode.Custom && s.current.HasValue)
                {
                    if (!s.currentPrematureRetried)
                    {
                        s.currentPrematureRetried = true;
                        _prematureResumeCount++;
                        Plugin.Log?.LogWarning($"[MUSIC] main source host-retired at {s.resumePositionSec:F1}s ({why}) — attempting one resume on the respawned host");
                    }
                    else
                    {
                        EnterDurableFaultNoThrow("host-retired after the one resume: " + why);
                        return;
                    }
                }
            }
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
                // ── lag-332 v6 §2.3 WaitingForNext ──────────────────────
                // Successor readiness EXITS Waiting immediately: loop clears,
                // the current plays to its natural end, the natural-end branch
                // below then adopts the successor (no truncation).
                if (s.waiting && SuccessorResident()) ExitWaiting("successor-ready");
                // Central enforcement (r1 MEDIUM 10): Waiting cannot outlive loop-on.
                if (s.waiting && (!LoopEffective() || s.stopIntent)) ExitWaiting("loop-off");
                // Arm: inside the last 4 s of a playing current whose successor
                // is not resident, loop it BEFORE it stops so there is no gap.
                // 4 s, not 2 (design v2 §2.3.6): a streamed source reports
                // AudioSource.time in packet-coarse steps near EOF.
                if (!s.waiting && m != null && m.isPlaying && s.currentStarted && s.current.HasValue
                    && LoopEffective() && !s.stopIntent && m.clip != null
                    && (m.clip.length - m.time) < EOF_WINDOW_SEC && !SuccessorResident())
                    EnterWaiting("near-end");
                // A Waiting source that went silent is a device fault, not a
                // natural end: skip the premature-end classifier and let the
                // 8 s silence bound (else-branch below) own it.
                bool waitingSilent = s.waiting && m != null && !m.isPlaying;
                // §7 2-2 / 2-7: the delivery heartbeat is the death gate's SECOND
                // cause. A source that reports isPlaying while no audio reaches
                // the output (no frames delivered for 1 s, or 10 s of digital
                // zeros at a non-zero volume — both on the DSP clock) is judged
                // here exactly like a stopped one, and ALWAYS as premature.
                bool stalled = !waitingSilent && m != null && s.current.HasValue && s.currentStarted && DeliveryStalled(m, s);
                // [J1] A STARTED-but-silent source is judged HERE and nowhere
                // else, and the branch comes FIRST: falling through to
                // EnsureMainPlaying would blind-replay and re-stamp
                // currentStartedRt, renewing the 0.5s grace forever (silent
                // Custom under held suppression, unbounded — never Fault).
                if (!waitingSilent && m != null && s.current.HasValue && s.currentStarted && (!m.isPlaying || stalled))
                {
                    // Grace interval: an AudioSource can report !isPlaying for
                    // a few frames right after Play(). WAIT — no replay, no
                    // timestamp reset — so repeated early stops still expire.
                    // The same grace covers the heartbeat (its baseline is
                    // re-armed by the Play that stamped currentStartedRt).
                    if (rt - s.currentStartedRt <= 0.5f) return;
                    // [I1][J1] grace expired — classify by CAUSE and by the last
                    // position observed while playing (§7 2-7): a stopped source
                    // inside the last 4 s is a natural end; a stopped source well
                    // short of it, or ANY stall, is premature — exactly ONE
                    // counted resume attempt (currentPrematureRetried), then
                    // durable Fault.
                    var clip = m.clip;
                    bool premature = stalled || (clip != null && s.resumePositionSec < clip.length - EOF_WINDOW_SEC);
                    if (premature)
                    {
                        string cause = stalled ? "delivery-stalled" : "premature-stop";
                        if (!s.currentPrematureRetried)
                        {
                            s.currentPrematureRetried = true;
                            s.currentStarted = false;   // EnsureMainPlaying resumes from resumePositionSec (Stop + Play for a still-"playing" stalled source)
                            _prematureResumeCount++;
                            Plugin.Log?.LogWarning($"[MUSIC] main source {cause} at {s.resumePositionSec:F1}s of {(clip != null ? clip.length : 0f):F1}s{(stalled ? " (" + _lastStallDetail + ")" : "")} — attempting one resume");
                            EnsureMainPlaying();
                        }
                        else
                        {
                            if (stalled) _stallFaultCount++;
                            EnterDurableFaultNoThrow(stalled ? "delivery-stalled" : "premature-stop at " + s.resumePositionSec.ToString("F1") + "s");
                        }
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
                        // v6 §2.3: no resident successor with loop on → Waiting
                        // (restart the finished current at zero and loop it)
                        // instead of a Loading detour into vanilla.
                        else if (LoopEffective() && !s.stopIntent && s.current.HasValue && IsTrackReady(s.current.Value)) EnterWaiting("natural-end");
                        else
                        {
                            if (!s.stopIntent) _noReadyTrackCount++;
                            Reconcile(s.stopIntent ? "playlist-end" : "no-ready-track");
                        }
                    }
                }
                else
                {
                    if (!waitingSilent) EnsureMainPlaying();
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
                            // Design v2 §2.3.4(c): one read position per streamed clip —
                            // Main and Preview never share one (preview keys are their
                            // own "p:" files; this refuses a future caller that breaks it).
                            if (h.Main != null && h.Main.clip == e.Clip)
                            {
                                _previewShareRefusals++;
                                Plugin.Log?.LogWarning($"[MUSIC] preview {key} refused: its clip is bound to Main");
                                StopPreviewAndRestoreInternal("preview-clip-shared");
                                return;
                            }
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
            // v4 §2.5 fade-in: progress-based (0.6 s), advancing ONLY while
            // Main is audibly playing (never while paused / paused-by-us). A
            // RESUME re-arms it (impl note 45, r9 LOW 2 — accepted): the track
            // comes back with a fresh 0.6 s fade-in rather than at its frozen
            // gain; a short fade, never a gap or a pop.
            float fade = 1f;
            if (s.fadeActive)
            {
                bool audible = m != null && m.isPlaying && !s.mainPausedByUs && !s.paused;
                // Skip the arming frame AND the one after it: frame N+1's
                // unscaledDeltaTime is frame N's wall time, which carried the
                // open that preceded Play() (r1 LOW 20 / r2 LOW 18 — a 2-5 ms
                // handle under streaming, so the skip is now merely conservative).
                if (audible && dt > 0f && Time.frameCount > s.fadeArmFrame + 1) s.fadeProgress += Mathf.Min(dt, 0.1f) / 0.6f;
                if (s.fadeProgress >= 1f) { s.fadeProgress = 1f; s.fadeActive = false; }
                fade = Mathf.Clamp01(s.fadeProgress);
            }
            if (m != null) m.volume = mult * baseGain * Mathf.Lerp(1f, DUCK_VOLUME, s.duckLevel) * fade;
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
            // Tier triggers + residency-window requests for a selection that
            // wants files we don't hold (requests only — never a decode).
            if (s.selectionNonEmpty && !s.hasReadyTrack) KickDesiredLoads();
        }

        private static void EnsureQueueCurrent()
        {
            var s = S;
            // r3 LOW 16: the no-change path allocates NOTHING — the signature
            // string is rebuilt only when one of its inputs actually moved
            // (Waiting calls this every gameplay frame through SuccessorRef).
            RefreshDeselectedCache();
            if (s.queueSignature != null && QueueInputsUnchanged()) return;
            string sig = ComputeQueueSignature();
            if (s.queueSignature == sig) return;
            // r3 MEDIUM 3: a selection mutation AFTER an explicit PlayTrack
            // supersedes that takeover — it was bound to the selection it was
            // made against, not to transport history.
            if (s.takeoverKey != null && s.takeoverSelectionSig != null && !string.Equals(sig, s.takeoverSelectionSig, StringComparison.Ordinal))
            {
                Plugin.Log?.LogInfo($"[MUSIC] takeover of {s.takeoverKey} released (selection changed)");
                s.takeoverKey = null;
            }
            s.queueSignature = sig;
            var sel = BuildEffectiveSelection();
            s.queue = BuildQueueOrder(sel, s.current);
            s.queueIndex = s.current.HasValue ? s.queue.FindIndex(t => t.Equals(s.current.Value)) : -1;
            // r2 MEDIUM 15: a current that the selection no longer contains must
            // not keep playing (or Waiting-looping) — it becomes an ended cursor
            // so readiness stops counting it and playback advances off it. An
            // explicit PlayTrack takeover of a deselected track stays allowed.
            bool takeover = s.takeoverKey != null && s.current.HasValue
                && string.Equals(s.takeoverKey, s.current.Value.ToString(), StringComparison.Ordinal);
            if (s.current.HasValue && s.queueIndex < 0 && !takeover)
            {
                ExitWaiting("deselected");
                s.currentEnded = true;
                s.hasReadyTrack = false;   // readiness is re-derived by the caller's reconcile
            }
        }

        private static string ComputeQueueSignature()
        {
            var s = S;
            RefreshDeselectedCache();
            bool broadcast = BroadcastPredicate(), shuffle = ShuffleEffective();
            int mask = PlayableAlbumMask();
            var sb = new StringBuilder();
            sb.Append(broadcast ? "B|" : "n|").Append(shuffle ? "S|" : "l|");
            sb.Append(s.vanillaTracks.Count).Append('|').Append(s.deselectedRaw ?? "");
            var albums = MusicCatalog.Albums;
            if (albums != null)
                for (int i = 0; i < albums.Length; i++)
                    if (albums[i] != null && IsAlbumPlayable(albums[i].Sku)) sb.Append('|').Append(albums[i].Sku);
            // Input cache for the allocation-free unchanged test (r3 LOW 16).
            _sigBroadcast = broadcast; _sigShuffle = shuffle; _sigVanilla = s.vanillaTracks.Count;
            _sigAlbumMask = mask; _sigDeselected = s.deselectedRaw;
            return sb.ToString();
        }

        // r3 LOW 16: the signature's inputs, cached at the last rebuild so the
        // per-frame check compares scalars and one string REFERENCE
        // (RefreshDeselectedCache replaces deselectedRaw only when it changed).
        private static bool _sigBroadcast, _sigShuffle;
        private static int _sigVanilla, _sigAlbumMask;
        private static string _sigDeselected;
        private static bool QueueInputsUnchanged()
        {
            var s = S;
            if (!ReferenceEquals(_sigDeselected, s.deselectedRaw)) return false;
            if (_sigBroadcast != BroadcastPredicate() || _sigShuffle != ShuffleEffective()) return false;
            if (_sigVanilla != s.vanillaTracks.Count) return false;
            return _sigAlbumMask == PlayableAlbumMask();
        }
        private static int PlayableAlbumMask()
        {
            int mask = 0;
            var albums = MusicCatalog.Albums;
            if (albums == null) return 0;
            for (int i = 0; i < albums.Length && i < 31; i++)
                if (albums[i] != null && IsAlbumPlayable(albums[i].Sku)) mask |= 1 << i;
            return mask;
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
        /// tail merely wasn't open yet).</summary>
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
            // v6 §2.2: the scans INSPECT readiness only — requests exist for
            // the residency window alone (KickDesiredLoads).
            bool pendingSkipped = false;
            for (int i = s.queueIndex + 1; i < n; i++)
            {
                var t = s.queue[i];
                if (IsTrackReady(t)) { AdoptCurrent(i, t); return true; }
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
                // v6 §2.2: promote the PERSISTED next cycle (the one the
                // residency successor was drawn from) so traversal and
                // residency agree; build fresh only when none is bound.
                var next = EnsureNextCycle();
                s.queue = next ?? BuildQueueOrder(BuildEffectiveSelection(), s.current);
                s.nextCycle = null; s.nextCycleSignature = null;
                n = s.queue.Count;
                if (n == 0) { s.current = null; s.currentEnded = false; return false; }
                s.queueIndex = s.current.HasValue ? s.queue.FindIndex(x => x.Equals(s.current.Value)) : -1;
            }
            // Pass 2: the fresh cycle (or the listed-order wrap) from the top.
            for (int i = 0; i < n; i++)
            {
                var t = s.queue[i];
                if (IsTrackReady(t)) { AdoptCurrent(i, t); return true; }
            }
            return false;   // nothing ready — caller decides: Waiting (loop on) or Loading
        }

        /// <summary>Mirror of AdvanceToNext for the Previous transport: walk
        /// BACKWARD through the queue (wrapping) to the nearest ready track.
        /// Backward never rebuilds, so it needs no held-cycle logic — the
        /// wrap stays inside the live cycle order.</summary>
        /// <summary>v6 §2.2 (d5 #4): Previous addresses ONLY the logical
        /// immediate predecessor — it must never wrap forward to the resident
        /// successor ("Previous acting as Next"). Returns: 1 = adopted a
        /// resident predecessor; 0 = predecessor exists but is not resident
        /// (index in predIndex); -1 = no predecessor (loop off at the top).</summary>
        private static int TryPrevious(out int predIndex, out TrackRef pred)
        {
            var s = S;
            predIndex = -1; pred = default;
            EnsureQueueCurrent();
            int n = s.queue.Count;
            if (n == 0) return -1;
            int cur = s.queueIndex < 0 ? 0 : s.queueIndex;
            int i;
            if (cur > 0) i = cur - 1;
            else if (LoopEffective()) i = n - 1;
            else return -1;
            if (i == cur) return -1;
            predIndex = i; pred = s.queue[i];
            if (IsTrackReady(pred)) { AdoptCurrent(i, pred); return 1; }
            return 0;
        }

        /// <summary>Adopt queue[i] as the current track (shared by both
        /// transports). Clears the ended cursor [N6c] and prefetches the
        /// remainder of the entered album block [N6b].</summary>
        private static void AdoptCurrent(int i, TrackRef t)
        {
            var s = S;
            ExitWaiting("adopt");   // v6 §2.3: successor adoption is a Waiting exit
            s.queueIndex = i;
            s.current = t;
            s.takeoverKey = null;   // r3 MEDIUM 3: adoption ends an explicit takeover
            s.currentEnded = false;
            s.resumePositionSec = 0f;
            s.currentStarted = false;
            s.mainPausedByUs = false;
            s.currentPrematureRetried = false;
            Plugin.Log?.LogInfo($"[MUSIC] adopt {t} (queue {i + 1}/{s.queue.Count})");
            // v6 §2.2 / §7 2-3, 2-4: the desired set moved (new current/
            // successor) — swap residency synchronously. The displaced entry
            // leaves as a release pair (clip Destroyed in this call once its
            // detach is confirmed, request disposed by a later sweep) and the
            // successor's request starts in the same call: the pair may still
            // be queued while the request runs — the release queue never
            // blocks a request.
            ReconcileResidency();
        }

        /// <summary>[N6a] An unready CUSTOM entry that can still become ready:
        /// load in flight, or not yet kicked / awaiting the tier install. A
        /// FAILED open is terminal — never pending — so an all-failed cycle
        /// still reaches the boundary rules instead of deadlocking the walk
        /// (and the readiness scan) forever.</summary>
        private static bool IsTrackLoadPending(TrackRef t)
        {
            if (IsVanillaSku(t.Sku) || !IsTrackKnown(t)) return false;
            if (!Clips.TryGetValue(t.ToString(), out var e)) return true;
            return e.Clip == null && !e.Failed;
        }

        // [N6b] PrefetchCurrentAlbumBlock was REMOVED by lag-332 design v6
        // §2.2: residency is exactly {current, successor, preview}; a block
        // prefetch is a fourth-key request by construction. An unopened
        // successor at a track end means WaitingForNext (loop the current),
        // never a Loading detour — see TickPlayback.

        // ── lag-332 v6 §2.3: WaitingForNext ──────────────────────────────

        /// <summary>The ONLY entry into Waiting: loop the current track on
        /// itself because its successor is not resident. An already-stopped
        /// source restarts at zero with fresh classifier stamps and WITHOUT
        /// consuming currentPrematureRetried.</summary>
        private static void EnterWaiting(string why)
        {
            var s = S;
            var h = _host;
            if (h == null || h.Main == null || !s.current.HasValue) return;
            var m = h.Main;
            try
            {
                m.loop = true;
                if (!m.isPlaying)
                {
                    try { m.time = 0f; } catch { }
                    try { m.volume = 0f; } catch { }   // r1 LOW 20: silent before EVERY Play
                    m.Play();
                    s.currentStarted = true;
                    s.currentStartedRt = Time.realtimeSinceStartup;
                    s.resumePositionSec = 0f;
                    ArmFade();
                    ArmDeliveryTap();
                }
                s.currentEnded = false;
                if (!s.waiting)
                {
                    s.waiting = true;
                    Plugin.Log?.LogInfo($"[MUSIC] waiting for next ({why}) — looping {s.current.Value}");
                }
            }
            catch (Exception ex) { EnterDurableFaultNoThrow("enter-waiting: " + ex.Message); }
        }

        /// <summary>The ONLY exit from Waiting (the only writer of
        /// waiting=false): clears Main.loop. Called from successor
        /// readiness/adoption, Stop/UseVanilla/PlayTrack (all via
        /// TransitionTo's release + AdoptCurrent), park, preview ownership,
        /// fault, StopSources, host replacement and shutdown.</summary>
        private static void ExitWaiting(string why)
        {
            var s = S;
            try { var h = _host; if (h != null && h.Main != null) h.Main.loop = false; } catch { }
            if (!s.waiting) return;
            s.waiting = false;
            Plugin.Log?.LogInfo($"[MUSIC] waiting ended ({why})");
        }

        private static bool SuccessorResident()
        {
            var succ = SuccessorRef();
            return succ.HasValue && IsTrackReady(succ.Value);
        }

        // ── lag-332 v4 §2.5: fade-in envelope ────────────────────────────

        private static void ArmFade()
        {
            var s = S;
            s.fadeActive = true;
            s.fadeProgress = 0f;
            // r1 LOW 20: the frame that called Play() may have carried the
            // open (2-5 ms streamed); its delta is not counted as audible time.
            s.fadeArmFrame = Time.frameCount;
        }

        // ── clip loading (UnityWebRequest, streamed OGG — design v2 §2.3) ─────────────────

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
            // [S1] An EXPLICITLY chosen current that is still LOADING outranks
            // global readiness: report NOT ready so the engine parks at Loading
            // with vanilla audible, and let the target's own open produce the
            // readiness edge that starts it. Without this, a ready entry
            // ELSEWHERE in the queue authorized Custom while the requested
            // track was legitimately mid-download — suppression on, nothing
            // playable — and the silence bound below then "recovered" by
            // killing the healthy request (at the queue tail with loop off
            // that lands in sticky stopIntent, i.e. permanent silence: the
            // bound defeating its own purpose).
            // Deliberately scoped to manualTakeover: every non-manual current
            // is adopted through AdoptCurrent, which only ever adopts a READY
            // track, so this is the one way a pending entry becomes current.
            // A terminally FAILED entry is NOT pending (IsTrackLoadPending is
            // false for it), so the bound still recovers the failed-current
            // route it was built for.
            if (s.manualTakeover && s.current.HasValue && !s.currentEnded
                && IsTrackLoadPending(s.current.Value)) return false;
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

        // ── lag-332 v6 §2.2: residency window ────────────────────────────

        /// <summary>The ONLY keys that may hold a request or a clip: the
        /// current track, its immediate successor, and the preview slot.
        /// Vanilla entries are never keys (their clips are the game's).
        /// Recomputed synchronously wherever the desired set can change
        /// (ReconcileResidency is called from ReconcileCore, AdoptCurrent and
        /// the transports) — never cached across a mutation.</summary>
        private static int DesiredKeys(string[] into)
        {
            var s = S;
            int n = 0;
            // r2 MEDIUM 12 — the preview TRANSACTION: while a replacement Q is
            // Pending, the slot holds BOTH the fallback P (active or retained)
            // and Q, and the SUCCESSOR yields for the duration so the physical
            // bound still holds; P is displaced only once Q has opened and
            // taken ownership (previewPending cleared by StartPreviewOwnership).
            bool transaction = s.previewPending.HasValue;
            TrackRef? fallback = s.previewTrack ?? s.previewRetained;
            // r5 MEDIUM 4: an ENDED current is a traversal cursor, not a playable.
            // It stays desired only while it is already resident (a Previous
            // restart may still need its clip); an ended current that never
            // opened is dropped from the window so no request is spent on it.
            bool currentDesired = s.current.HasValue && !IsVanillaSku(s.current.Value.Sku)
                && (!s.currentEnded || IsTrackReady(s.current.Value));
            if (currentDesired) into[n++] = s.current.Value.ToString();
            else if (!s.current.HasValue && s.queue.Count > 0 && !IsVanillaSku(s.queue[0].Sku))
            {
                // No current yet (Loading before the first adoption): the head of
                // the queue IS the track that will become current, so the window
                // is {queue[0], queue[1]} — "0 of 2 ready", not a one-key window
                // that grows to two after the first open (seen in the Sept 2
                // verification screenshot).
                into[n++] = s.queue[0].ToString();
                if (!transaction && s.queue.Count > 1 && !IsVanillaSku(s.queue[1].Sku)) into[n++] = s.queue[1].ToString();
                if (transaction)
                {
                    if (fallback.HasValue) into[n++] = "p:" + fallback.Value;
                    into[n++] = "p:" + s.previewPending.Value;
                }
                else if (fallback.HasValue) into[n++] = "p:" + fallback.Value;
                return n;
            }
            if (!transaction)
            {
                var succ = SuccessorRef();
                if (succ.HasValue && !IsVanillaSku(succ.Value.Sku))
                {
                    string k = succ.Value.ToString();
                    bool dup = false;
                    for (int i = 0; i < n; i++) if (into[i] == k) { dup = true; break; }
                    if (!dup) into[n++] = k;
                }
                if (fallback.HasValue) into[n++] = "p:" + fallback.Value;
            }
            else
            {
                if (fallback.HasValue) into[n++] = "p:" + fallback.Value;
                into[n++] = "p:" + s.previewPending.Value;
            }
            return n;
        }

        private static bool IsDesiredKey(string key)
        {
            var keys = _desiredScratch;
            int n = DesiredKeys(keys);
            for (int i = 0; i < n; i++) if (keys[i] == key) return true;
            return false;
        }
        private static readonly string[] _desiredScratch = new string[6];

        /// <summary>r3 MEDIUM 2: LOGICAL failure state lives HERE, separate from
        /// physical residency — reconciliation may release a failed entry's
        /// native resources, but that never clears the tombstone; only an
        /// explicit retry does (a PlayTrack of that key, a Preview click of
        /// that key).</summary>
        private static readonly HashSet<string> Tombstones = new HashSet<string>(StringComparer.Ordinal);

        private static bool IsFailedKey(string key)
        {
            if (key == null) return false;
            return Tombstones.Contains(key) || (Clips.TryGetValue(key, out var e) && e.Failed);
        }

        /// <summary>r7 MEDIUM 1: EVERY failure of the CURRENT key — request start,
        /// download, open — recovers through THIS path and nowhere else: an
        /// optional advance to a ready successor, then a mandatory Reconcile (a
        /// readiness edge may already have been consumed, and EnsureMainPlaying
        /// returns while the mode is Loading). Sites that fail INSIDE a residency
        /// pass (request start) must not reconcile re-entrantly: they park the
        /// key in _failedCurrentPending and Tick drains it FIRST, before any
        /// readiness transition can acquire Custom around a dead current.</summary>
        private static void RecoverFailedCurrent(string key, string why)
        {
            var s = S;
            if (!s.current.HasValue || !string.Equals(s.current.Value.ToString(), key, StringComparison.Ordinal)) return;
            if (!AdvanceToNext(userSkip: false))
            {
                // r8 MEDIUM 2: nothing is ready NOW. The failed current must not
                // stay a live cursor: a LATER readiness mutation (a track becomes
                // resident, the vanilla OST is re-enabled) would otherwise acquire
                // Custom around a dead current and EnsureMainPlaying would address
                // it and return — owned silence until the watchdog. As an ENDED
                // cursor [N6c] it is excluded from readiness and EnsureMainPlaying
                // advances off it the moment anything becomes playable.
                s.currentEnded = true;
                s.hasReadyTrack = false;
                Plugin.Log?.LogInfo($"[MUSIC] failed current {key} parked as an ended cursor ({why}) — no successor is ready yet");
            }
            Reconcile("current-failed:" + why);
        }
        private static string _failedCurrentPending, _failedCurrentPendingWhy;
        private static void NoteKeyFailedDeferred(ClipEntry e, string why)
        {
            MarkFailed(e);
            var s = S;
            if (s.current.HasValue && string.Equals(s.current.Value.ToString(), e.Key, StringComparison.Ordinal))
            { _failedCurrentPending = e.Key; _failedCurrentPendingWhy = why; }
        }
        private static void DrainFailedCurrent()
        {
            if (_failedCurrentPending == null) return;
            string k = _failedCurrentPending, why = _failedCurrentPendingWhy;
            _failedCurrentPending = null; _failedCurrentPendingWhy = null;
            RecoverFailedCurrent(k, why);
        }

        private static void MarkFailed(ClipEntry e)
        {
            e.Failed = true;
            ClipStateGeneration++;
            if (e.Key != null && Tombstones.Add(e.Key)) Plugin.Log?.LogInfo($"[MUSIC] tombstone {e.Key} (failed — retry only by an explicit click)");
        }

        private static void ClearTombstone(string key)
        {
            if (key == null) return;
            if (Tombstones.Remove(key)) Plugin.Log?.LogInfo($"[MUSIC] retry {key} (tombstone cleared by an explicit click)");
            if (Clips.TryGetValue(key, out var e) && e.Failed) { Clips.Remove(key); DisposeEntry(e); }
        }

        /// <summary>The logical immediate successor of the current track
        /// under the live loop/shuffle policy — the ONLY forward entry that
        /// may be resident. At a shuffled tail the next cycle is generated
        /// once (EnsureNextCycle) so traversal wraps into the same order.</summary>
        private static TrackRef? SuccessorRef()
        {
            var s = S;
            EnsureQueueCurrent();
            int n = s.queue.Count;
            if (n == 0) return null;
            // r2 MEDIUM 13: a FAILED entry is not a viable successor — skip past
            // it to the next candidate (that track's own Play retries a failed
            // key — ClearTombstone), so Waiting never pins on a dead key.
            int start = s.queueIndex < 0 ? 0 : s.queueIndex + 1;
            for (int i = start; i < n; i++)
            {
                if (IsVanillaSku(s.queue[i].Sku) || !IsFailedKey(s.queue[i].ToString())) return s.queue[i];
            }
            if (!LoopEffective()) return null;
            List<TrackRef> wrap = ShuffleEffective() ? EnsureNextCycle() : s.queue;
            if (wrap == null) return null;
            for (int i = 0; i < wrap.Count; i++)
            {
                if (s.current.HasValue && wrap[i].Equals(s.current.Value) && wrap.Count > 1) continue;
                if (IsVanillaSku(wrap[i].Sku) || !IsFailedKey(wrap[i].ToString())) return wrap[i];
            }
            return null;
        }

        private static List<TrackRef> EnsureNextCycle()
        {
            var s = S;
            string sig = s.queueSignature;
            if (s.nextCycle != null && string.Equals(s.nextCycleSignature, sig, StringComparison.Ordinal)) return s.nextCycle;
            s.nextCycle = BuildQueueOrder(BuildEffectiveSelection(), s.current);
            s.nextCycleSignature = sig;
            return s.nextCycle;
        }

        /// <summary>§7 2-3: the OBJECT ledger — diagnostic only, never an
        /// admission input. Each request (Req or ReqKeep) and each clip counts
        /// once: an open entry is 2; a queued pair is 2 until its Destroy
        /// landed and 1 from then until its request is disposed.</summary>
        private static int LiveObjectCount()
        {
            int c = 0;
            for (int i = 0; i < PendingRelease.Count; i++)
            {
                var p = PendingRelease[i];
                c += (p.Clip != null && !p.Destroyed) ? 2 : 1;
            }
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Clip != null) c++;
                if (e.Req != null || e.ReqKeep != null) c++;
            }
            return c;
        }

        /// <summary>impl2 r2 rule (d): pairs held for the session — a retired
        /// host not observed destroyed inside the detach window, or a clip
        /// Destroy that threw — still counted by LiveObjectCount, shown on
        /// every [MUSIC-RESIDENCY] line.</summary>
        private static int HeldPairCount()
        {
            int c = 0;
            for (int i = 0; i < PendingRelease.Count; i++) if (PendingRelease[i].Held) c++;
            return c;
        }

        /// <summary>Age in seconds of the oldest queued pair (0 when the queue
        /// is empty): the self-test's S4 measure of "pairs drain within 1.0 s"
        /// (§7 2-8), taken per pair rather than per non-empty stretch of the
        /// queue.</summary>
        private static float MaxPendingPairAgeSec(float now)
        {
            float a = 0f;
            for (int i = 0; i < PendingRelease.Count; i++) { float age = now - PendingRelease[i].QueuedRt; if (age > a) a = age; }
            return a;
        }

        /// <summary>Entries holding a request or a clip — what request
        /// admission counts against RESIDENT_KEY_CAP (§7 2-3). A Failed entry
        /// holds neither.</summary>
        private static int EntryCount()
        {
            int c = 0;
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Clip != null || e.Req != null || e.ReqKeep != null) c++;
            }
            return c;
        }

        private static float _ledgerOverBoundLogRt = -999f;
        private static int _ledgerOverBoundCount;   // ticks spent over the bound (the self-test reads the delta)
        /// <summary>§7 2-3: the stated bound is live <= 2 x RESIDENT_KEY_CAP +
        /// 2 x queued pairs. A breach is logged at most once a minute and
        /// changes nothing — the ledger never refuses anything.</summary>
        private static void AuditLedger()
        {
            int live = LiveObjectCount();
            int bound = 2 * RESIDENT_KEY_CAP + 2 * PendingRelease.Count;
            if (live <= bound) return;
            _ledgerOverBoundCount++;
            float rt = Time.realtimeSinceStartup;
            if (rt - _ledgerOverBoundLogRt < 60f) return;
            _ledgerOverBoundLogRt = rt;
            Plugin.Log?.LogWarning($"[MUSIC-RESIDENCY] live={live} over-bound (bound={bound}, entries={EntryCount()}, pendingRelease={PendingRelease.Count}, held={HeldPairCount()})");
        }

        /// <summary>Reconcile the resident set against DesiredKeys: displaced
        /// keys leave as PendingRelease pairs (clip destroyed now, request
        /// disposed on a later frame — §7 2-4); missing desired keys get a
        /// REQUEST while the entry window has room (§7 2-3).</summary>
        private static void ReconcileResidency()
        {
            try
            {
                var keys = _desiredScratch;
                int n = DesiredKeys(keys);
                List<string> drop = null;
                foreach (var kv in Clips)
                {
                    bool keep = false;
                    for (int i = 0; i < n; i++) if (keys[i] == kv.Key) { keep = true; break; }
                    if (!keep) (drop ?? (drop = new List<string>())).Add(kv.Key);
                }
                if (drop != null)
                {
                    foreach (var k in drop) { var e = Clips[k]; Clips.Remove(k); DisposeEntry(e); }
                    ClipStateGeneration++;
                    // Audit line for the physical bound (design v6 §2.2 gate 7):
                    // what was displaced and what is resident right after.
                    Plugin.Log?.LogInfo($"[MUSIC-RESIDENCY] displaced={string.Join(",", drop)} desired={string.Join(",", keys, 0, n)} live={LiveObjectCount()} pendingRelease={PendingRelease.Count} held={HeldPairCount()}");
                }
                KickDesiredLoads();
            }
            catch (Exception ex) { LogOnce("resid", "[MUSIC] residency reconcile failed: " + ex.Message, true); }
        }

        /// <summary>Request (never decode) each desired key that holds no
        /// entry, within the entry window (§7 2-3: the release queue never
        /// blocks a request).</summary>
        private static void KickDesiredLoads()
        {
            var keys = _desiredScratch;
            int n = DesiredKeys(keys);
            for (int i = 0; i < n; i++)
            {
                string key = keys[i];
                if (Clips.ContainsKey(key)) continue;
                if (Tombstones.Contains(key)) continue;               // r3 MEDIUM 2: a failed key is never auto-requested
                if (EntryCount() >= RESIDENT_KEY_CAP) return;         // §7 2-3: entries — never objects, never the release queue
                if (key.StartsWith("p:", StringComparison.Ordinal)) KickPreviewLoad(key.Substring(2));
                else if (TrackRef.TryParse(key, out var t)) KickLoad(t);
            }
        }

        private static void KickPreviewLoad(string trackKey)
        {
            if (!TrackRef.TryParse(trackKey, out var t)) return;
            var album = MusicCatalog.Get(t.Sku);
            if (album == null || album.Tracks == null || t.Idx < 0 || t.Idx >= album.Tracks.Length) return;
            string path = null;
            try { path = MusicAssets.PathFor(album.Tracks[t.Idx].PreviewFile); } catch { }
            if (path == null) { try { MusicAssets.EnsureTier(MusicTier.Previews, "preview"); } catch { } return; }
            EnsureClipLoading("p:" + t, path);
        }

        /// <summary>§7 2-4, the sweep half of the paired release, rebuilt for
        /// impl2 r2 (DETACH-OR-RETIRE). Every sweep first observes the host
        /// list (rule a), then re-evaluates step 1 of every pair still at it —
        /// an observation of retired hosts, not a retry of a detach — and
        /// holds a pair whose window expired (rule d). Step 2 (the request
        /// Dispose) never runs in the frame that issued the Destroy: Unity's
        /// end-of-frame destroy of the clip precedes the release of the
        /// handler buffer it streamed from. The NOMINAL path is two frames:
        /// Destroy in the evicting frame and the pair's FIRST step-2 attempt
        /// on the next sweep, unthrottled (§7 2-8: S4's 1.0 s bound); only a
        /// step 2 that threw retries, at most twice a second — a persistently
        /// faulting object must not cost every frame (the r7 LOW 13 rule).</summary>
        private const float RELEASE_DETACH_WINDOW_SEC = 5f;
        private static float _releaseRetryRt = -1f;
        private static void SweepPendingRelease()
        {
            AuditLedger();
            PruneObservedNullHosts();
            if (PendingRelease.Count == 0) return;
            float now = Time.realtimeSinceStartup;
            bool retry = now - _releaseRetryRt >= 0.5f;
            if (retry) _releaseRetryRt = now;
            int f = Time.frameCount;
            for (int i = PendingRelease.Count - 1; i >= 0; i--)
            {
                var p = PendingRelease[i];
                if (p.Held) continue;
                if (!p.Destroyed)
                {
                    if (!TryReleaseStep1(ref p) && !p.Held && now - p.QueuedRt > RELEASE_DETACH_WINDOW_SEC)
                        HoldPair(ref p, "a retired host was not observed destroyed within " + RELEASE_DETACH_WINDOW_SEC.ToString("F0", System.Globalization.CultureInfo.InvariantCulture) + " s (" + RetiredHostsSummary() + ")");
                    PendingRelease[i] = p;
                    continue;   // step 2 waits for a later frame than the Destroy
                }
                if (f <= p.DestroyedFrame) continue;
                if (p.Req != null)
                {
                    if (p.DisposeAttempts > 0 && !retry) continue;
                    p.DisposeAttempts++;
                    try { p.Req.Dispose(); p.Req = null; }
                    catch (Exception ex)
                    {
                        PendingRelease[i] = p;
                        LogOnce("reqdispose:" + p.Key, $"[MUSIC] request dispose failed for {p.Key} (pair kept, retried at <= 2 Hz): {ex.Message}", true);
                        continue;
                    }
                }
                PendingRelease.RemoveAt(i);
                ClipStateGeneration++;   // the ledger moved (Music tab repaint signature)
            }
        }

        /// <summary>Music-tab status line (design v2 §2.3.2 — replaces the
        /// Prepare affordance): what the residency window is doing for the
        /// desired custom keys. null = nothing to say (every desired key is
        /// open). Not a control: a failed key is retried by that track's own
        /// Play (ClearTombstone), the tier install by the Shop.</summary>
        internal static string MusicStatusLine()
        {
            try
            {
                var keys = _desiredScratch;
                int n = DesiredKeys(keys);
                int total = 0, ready = 0, loading = 0;
                float progress = 0f;
                for (int i = 0; i < n; i++)
                {
                    if (keys[i].StartsWith("p:", StringComparison.Ordinal)) continue;
                    total++;
                    if (!Clips.TryGetValue(keys[i], out var e)) continue;
                    if (e.Clip != null) { ready++; continue; }
                    if (e.Failed || e.Req == null) continue;
                    loading++;
                    float p = 1f;
                    if (!e.Downloaded) { try { p = e.Req.downloadProgress; } catch { p = 0f; } }
                    progress += Mathf.Clamp01(p);
                }
                // r3 MEDIUM 2 / r5 MEDIUM 6: EVERY failed non-preview key counts
                // exactly once — tombstoned or holding a Failed entry.
                var failedKeys = new HashSet<string>(StringComparer.Ordinal);
                foreach (var tk in Tombstones) if (!tk.StartsWith("p:", StringComparison.Ordinal)) failedKeys.Add(tk);
                foreach (var kv in Clips) if (kv.Value.Failed && !kv.Key.StartsWith("p:", StringComparison.Ordinal)) failedKeys.Add(kv.Key);
                if (failedKeys.Count > 0) return I18n.TrF("Music failed to load ({0}) — play the track to retry", failedKeys.Count);
                if (total == 0 || ready == total) return null;
                if (loading > 0)
                {
                    int pct = Mathf.Clamp(Mathf.RoundToInt(progress / loading * 100f), 0, 99);
                    return I18n.TrF("Loading music ({0}%)", pct);
                }
                // Nothing requested for an unresolved key: the full tier is not
                // on disk. MusicAssets.TierStatusLine speaks while a download or
                // a failure is in progress; this line covers the quiet case.
                bool tierReady = false;
                try { tierReady = MusicAssets.TierReady(MusicTier.Full); } catch { }
                if (!tierReady)
                {
                    string tier = null;
                    try { tier = MusicAssets.TierStatusLine(); } catch { }
                    return string.IsNullOrEmpty(tier) ? I18n.Tr("Music files not installed") : null;
                }
                return I18n.TrF("Loading music ({0} of {1} ready)", ready, total);
            }
            catch { return null; }
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
            // lag-332 v6 §2.2: a request may only exist for a desired key.
            if (!IsDesiredKey(key)) return;
            // §7 2-3: admission counts ENTRIES against the residency window;
            // the object ledger and the release queue are never admission
            // inputs (a release that keeps failing cannot wedge loads).
            if (EntryCount() >= RESIDENT_KEY_CAP) return;
            // r1 MEDIUM 12: ownership is established in the counted set BEFORE
            // any throwing operation, so a request that throws mid-construction
            // can never exist uncounted; the local handle is released in the
            // failure path.
            var entry = new ClipEntry { Key = key, RequestedFrame = Time.frameCount };
            Clips[key] = entry;
            UnityWebRequest req = null;
            try
            {
                string url;
                try { url = new Uri(path).AbsoluteUri; }
                catch { url = "file:///" + path.Replace('\\', '/'); }
                req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
                entry.Req = req;
                ClipStateGeneration++;
                var dh = req.downloadHandler as DownloadHandlerAudioClip;
                // STREAMED (design v2 §2.2, bug 346): the clip reads the handler's
                // compressed buffer and FMOD decodes on its own stream thread —
                // no main-thread decode exists. Measured on both seats (v2 §2.4):
                // GetContent 1.7-3.4 ms, +3.5 MB native per open, 0 stalls. The
                // request therefore outlives the clip (ClipEntry.ReqKeep, §7 2-4).
                if (dh != null) dh.streamAudio = true;
                req.SendWebRequest();
                Plugin.Log?.LogInfo($"[MUSIC-RESIDENCY] request {key} entries={EntryCount()} live={LiveObjectCount()} pendingRelease={PendingRelease.Count} held={HeldPairCount()}");
            }
            catch (Exception ex)
            {
                // r3 MEDIUM 4 / r4 MEDIUM 4: every request release goes through the
                // pair queue — the reference is never dropped first.
                if (ReferenceEquals(entry.Req, req)) entry.Req = null;
                QueueRelease(key, null, req);
                NoteKeyFailedDeferred(entry, "request-start");   // r7 MEDIUM 1: the current recovers at the next Tick entry
                LogOnce("load:" + key, $"[MUSIC] clip load start failed for {key}: {ex.Message}", true);
            }
        }

        /// <summary>Polls in-flight requests (no coroutines: a host respawn
        /// would kill them; the request objects are static and survive). A
        /// completed read is marked Downloaded; then AT MOST ONE downloaded
        /// entry per frame is opened by OpenStreamedClip, a Pending preview's
        /// entry first (§7 2-5) — the open runs OUTSIDE the enumeration
        /// because its bridge reconciles residency.</summary>
        private static void PollClipLoads()
        {
            ClipEntry candidate = null;
            bool candidateIsPendingPreview = false;
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Req == null || e.Clip != null || e.Failed) continue;
                if (!e.Downloaded)
                {
                    if (!e.Req.isDone) continue;
                    if (e.Req.result != UnityWebRequest.Result.Success)
                    {
                        LogOnce("clipfail:" + e.Key, $"[MUSIC] clip read failed for {e.Key}: {e.Req.error}", true);
                        ReleaseRequest(e);   // r3 MEDIUM 4 / r4 MEDIUM 4: released through the pair queue
                        NoteKeyFailedDeferred(e, "download");   // r3 MEDIUM 2 tombstone + r7 MEDIUM 1 recovery (drained below, outside the enumeration)
                        continue;
                    }
                    e.Downloaded = true;
                    ClipStateGeneration++;
                }
                bool pp = s_previewPendingIs(e.Key);
                if (candidate == null || (pp && !candidateIsPendingPreview)) { candidate = e; candidateIsPendingPreview = pp; }
            }
            // Current track died: the ONE recovery path (r7 MEDIUM 1) — optional
            // advance, mandatory Reconcile; parks at Loading if the playable set
            // is gone [F12].
            DrainFailedCurrent();
            if (candidate != null) OpenStreamedClip(candidate);
        }

        private static int _lastOpenFrame = -1;

        /// <summary>The open (design v2 §2.3.1): GetContent on a streamAudio
        /// handler returns a clip that streams from the handler's buffer — a
        /// handle, not a decode (1.7-3.4 ms measured, §2.4). Validation and the
        /// failure tail are the former decode's, unchanged (§7 2-1); on success
        /// the request is retained beside the clip (ReqKeep) and the readiness
        /// bridge runs here. §7 2-6: two hosts ticking in one frame produce one
        /// open (the frame guard).</summary>
        private static void OpenStreamedClip(ClipEntry e)
        {
            if (_lastOpenFrame == Time.frameCount) return;
            _lastOpenFrame = Time.frameCount;
            AudioClip clip = null;
            long t0 = System.Diagnostics.Stopwatch.GetTimestamp();
            try { clip = DownloadHandlerAudioClip.GetContent(e.Req); } catch { }
            try
            {
                double openMs = (System.Diagnostics.Stopwatch.GetTimestamp() - t0) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
                try { NetworkSeatTelemetry.NoteMusicOpenMs(openMs); } catch { }   // frame-component ledger (bundle-only): its own cause slot — no decode happens here (impl2 r1 L2)
                Plugin.Log?.LogInfo($"[MUSIC-OPEN] key={e.Key} getContentMs={openMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} lengthS={(clip != null ? clip.length : 0f).ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} ch={(clip != null ? clip.channels : 0)} hz={(clip != null ? clip.frequency : 0)} entries={EntryCount()} live={LiveObjectCount() + (clip != null ? 1 : 0)}");
                _openLogNextFrame = e.Key;
                OpenCounts[e.Key] = (OpenCounts.TryGetValue(e.Key, out var oc) ? oc : 0) + 1;
            }
            catch { }
            if (clip != null && clip.length > 0.1f)
            {
                e.Clip = clip;
                e.ReqKeep = e.Req;   // §7 2-4: the streamed clip reads this request's buffer — it leaves with the clip
                e.Req = null;
                e.Downloaded = false;
                ClipStateGeneration++;
                // Completion bridge (moved verbatim from the click path, §2.3.1):
                // a Pending preview takes ownership now; readiness re-derives;
                // one reconcile publishes the edge.
                if (s_previewPendingIs(e.Key)) StartPendingPreviewOwnership();
                bool ready = ScanHasReadyTrack();
                if (ready != S.hasReadyTrack) S.hasReadyTrack = ready;
                Reconcile("load-complete");
                return;
            }
            MarkFailed(e);   // r3 MEDIUM 2: logical tombstone
            LogOnce("clipfail:" + e.Key, $"[MUSIC] clip open failed for {e.Key}: {(clip == null ? "null clip" : "empty clip")}", true);
            e.Downloaded = false;
            // r2 MEDIUM 14: a rejected NON-null clip is a native object — it
            // leaves with its request as one pair.
            var req = e.Req;
            e.Req = null;
            QueueRelease(e.Key, clip, req);
            // §7 2-1: the failure tail, verbatim — a failed CURRENT advances to a
            // ready successor or parks at Loading; anything else reconciles.
            bool readyAfterFail = ScanHasReadyTrack();
            if (readyAfterFail != S.hasReadyTrack) S.hasReadyTrack = readyAfterFail;
            if (S.current.HasValue && string.Equals(S.current.Value.ToString(), e.Key, StringComparison.Ordinal))
                RecoverFailedCurrent(e.Key, "open");
            else
                Reconcile("open-failed");
        }

        private static bool s_previewPendingIs(string key)
        {
            var p = S.previewPending;
            return p.HasValue && key == "p:" + p.Value;
        }

        /// <summary>§7 2-4 step 1 under impl2 r2 rules (b)/(c): Destroy(clip)
        /// only when every listed host is observed destroyed or cleanly
        /// detached from the clip on both sources. A host already retired
        /// counts only once observed destroyed, on a later frame — until then
        /// the pair waits. A source that fails the clean detach retires its
        /// host right here (never retried). Returns true when the Destroy
        /// call returned (the object dies at end of frame). A pair with no
        /// clip (an entry that never opened) passes vacuously; a Destroy that
        /// throws holds the pair (rule d).</summary>
        private static bool TryReleaseStep1(ref PendingReleaseEntry p)
        {
            if (p.Clip == null) { p.Destroyed = true; p.DestroyedFrame = Time.frameCount; return true; }
            PruneObservedNullHosts();
            bool clear = true;
            for (int i = 0; i < Hosts.Count; i++)
            {
                var e = Hosts[i];
                if (e.Retired) { clear = false; continue; }
                string why = null;
                AudioSource main = null, preview = null;
                bool readOk = true;
                // Reference check, not Unity's overload: after a component-only
                // Destroy the component reads as null while its fields still
                // name two live AudioSources — exactly the sources rule (c)
                // must account for.
                try { var h = e.Host; if ((object)h != null) { main = h.Main; preview = h.Preview; } }
                catch (Exception ex) { why = "host read threw: " + ex.Message; readOk = false; }
                if (!readOk || !DetachSourceClean(main, p.Clip, "Main", ref why) || !DetachSourceClean(preview, p.Clip, "Preview", ref why))
                {
                    RetireHost(e, why);
                    clear = false;
                }
            }
            if (!clear) return false;
            try
            {
                UnityEngine.Object.Destroy(p.Clip);
                p.Destroyed = true;
                p.DestroyedFrame = Time.frameCount;
                return true;
            }
            catch (Exception ex)
            {
                HoldPair(ref p, "clip destroy threw: " + ex.Message);
                return false;
            }
        }

        /// <summary>Rule (b), one source. True when the source is not bound
        /// to the clip (a source Unity reports destroyed holds no voice), or
        /// when Stop() returned, `clip = null` returned and the same-frame
        /// read-back is null. Anything else — an exception anywhere, a
        /// read-back still bound — is false and the caller retires the host;
        /// nothing here is retried.</summary>
        private static bool DetachSourceClean(AudioSource src, AudioClip clip, string name, ref string why)
        {
            try
            {
                if (src == null) return true;
                if (src.clip != clip) return true;
                src.Stop();
                src.clip = null;
                if (src.clip == null) return true;
                why = name + " still bound after clip = null";
                return false;
            }
            catch (Exception ex)
            {
                why = name + " threw during detach: " + ex.Message;
                return false;
            }
        }

        /// <summary>Rule (d): the pair is retained for the session — never
        /// destroyed, never disposed, still counted by LiveObjectCount and
        /// HeldPairCount — and logged exactly once, here.</summary>
        private static void HoldPair(ref PendingReleaseEntry p, string why)
        {
            p.Held = true;
            Plugin.Log?.LogWarning($"[MUSIC-RELEASE] held: key={p.Key} {why} — {Time.realtimeSinceStartup - p.QueuedRt:F1}s after eviction; clip and request retained for the session (live={LiveObjectCount()} held={HeldPairCount() + 1})");
        }

        private static string RetiredHostsSummary()
        {
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < Hosts.Count; i++)
            {
                var e = Hosts[i];
                if (!e.Retired) continue;
                if (sb.Length > 0) sb.Append("; ");
                sb.Append("host#").Append(i).Append(" retired at frame ").Append(e.RetiredFrame).Append(": ").Append(e.RetiredWhy ?? "?");
            }
            return sb.Length == 0 ? "no retired host listed" : sb.ToString();
        }

        /// <summary>The ONLY release primitive: every clip and every request
        /// leaves through a PendingRelease pair (a request-only entry is a pair
        /// with a null clip). Step 1 is attempted now; step 2 is the sweep's,
        /// on a later frame. No other collection ever references the request.</summary>
        private static void QueueRelease(string key, AudioClip clip, UnityWebRequest req)
        {
            if (clip == null && req == null) return;
            var p = new PendingReleaseEntry { Key = key, Clip = clip, Req = req, QueuedRt = Time.realtimeSinceStartup };
            TryReleaseStep1(ref p);
            PendingRelease.Add(p);
            ClipStateGeneration++;
        }

        /// <summary>Release an entry's request(s) without a clip (a read that
        /// failed, a request that never opened).</summary>
        private static void ReleaseRequest(ClipEntry e)
        {
            var a = e.Req; var b = e.ReqKeep;
            e.Req = null; e.ReqKeep = null;
            if (a != null) QueueRelease(e.Key, null, a);
            if (b != null && !ReferenceEquals(a, b)) QueueRelease(e.Key, null, b);
        }

        /// <summary>Evict an entry: its clip and its backing request leave
        /// together as one pair (§7 2-4). A clip still bound to a source is
        /// detached by step 1.</summary>
        private static void DisposeEntry(ClipEntry e)
        {
            var clip = e.Clip;
            var keep = e.ReqKeep;
            var req = e.Req;
            e.Clip = null; e.ReqKeep = null; e.Req = null; e.Downloaded = false;
            QueueRelease(e.Key, clip, keep ?? req);
            if (keep != null && req != null && !ReferenceEquals(keep, req)) QueueRelease(e.Key, null, req);
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
            if (clip == null) { KickDesiredLoads(); return; }
            var m = h.Main;
            if (m.clip != clip) { m.clip = clip; s.currentStarted = false; s.mainPausedByUs = false; s.currentPrematureRetried = false; ArmDeliveryTap(); }
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
                // v4 §2.5 fade: zero gain BEFORE the source becomes audible,
                // envelope armed right after the successful call.
                try { m.volume = 0f; } catch { }
                try { m.UnPause(); }
                catch (Exception ex) { EnterDurableFaultNoThrow("main-unpause: " + ex.Message); return; }
                s.mainPausedByUs = false;
                ArmFade();
                ArmDeliveryTap();   // §7 2-2: the heartbeat baseline restarts with every UnPause
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
                // v4 §2.5 fade: volume 0 and the current duck/LPF state are
                // applied BEFORE Play (TickDuckAndVolume keeps the LPF in
                // step every frame); the envelope baseline is stamped after.
                try { m.volume = 0f; } catch { }
                m.Play();
            }
            catch (Exception ex) { EnterDurableFaultNoThrow("main-play: " + ex.Message); return; }
            s.currentStarted = true;
            s.currentStartedRt = Time.realtimeSinceStartup;
            ArmFade();
            ArmDeliveryTap();   // §7 2-2: the heartbeat baseline restarts with every Play
            // v6 §2.2: the start edge covers the PlayTrack direct-assignment
            // path, which never runs AdoptCurrent — request the successor now.
            KickDesiredLoads();
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
            // v6 §2.3 backstop: no stopped source may keep a Waiting loop.
            try { var m = h.Main; if (m != null) m.loop = false; } catch { }
            ExitWaiting("stop-sources");   // r6 LOW 9: the one writer of waiting=false
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
                // explicitly — the consent-revoke promise is "vanilla music
                // comes back". (ComputeDesiredMode now maps an empty
                // selection to Vanilla as well; the explicit latch here is
                // unchanged.) MutedByChoice stays reserved for stopIntent and
                // the menu "silent" setting.
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
            // impl2 r2 rules (a)/(f): the new host is listed and adopted
            // FIRST, then every other listed entry is retired — the host whose
            // OnDestroy raised this respawn (its GameObject may be dying, or
            // may have survived a component-only Destroy with both
            // AudioSources alive), a clone, a second AddComponent — by rule
            // (b)'s Destroy of the whole GameObject, whether or not a source
            // on it can be seen. Adopting first means _host never names a
            // retired entry past this method; an entry leaves the list only
            // when observed destroyed (PruneObservedNullHosts).
            var entry = new HostEntry { Host = host };
            try { entry.Go = host.gameObject; } catch { }
            Hosts.Add(entry);
            _host = host;
            RetireOtherHosts(host);
            var s = S;
            RouteSources();
            if (!s.everHosted) { s.everHosted = true; return; }
            // Rehydration [F19]: the durable state object is authoritative; a
            // fresh host just re-derives its component state from it.
            try
            {
                Plugin.Log?.LogInfo($"[MUSIC] host respawned — rehydrating (mode={s.mode})");
                if (s.previewTrack.HasValue) StopPreviewAndRestoreInternal("host-respawn");
                ExitWaiting("host-respawn");   // v6 §2.3: the new Main starts loop-off; Waiting re-arms from TickPlayback if still needed
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
            // impl2 r2 rule (f): this is the COMPONENT's OnDestroy. The dying
            // host is silenced if it can be — after a component-only Destroy
            // its GameObject and both AudioSources outlive this callback, and
            // during a GameObject destroy they may still be alive while it
            // runs — and its list entry is left UNTOUCHED (rule a): it leaves
            // only once the GameObject is observed destroyed, and until then
            // the respawned host's Awake retires it (rule b's Destroy of the
            // GameObject) whether or not the silence here succeeded. That is
            // what closes the surviving-source hole (impl2 r2 H2): a failed
            // silence no longer drops the entry the retire needs.
            string why = SilenceSources(dying);
            if (why != null && !_quitting) Plugin.Log?.LogWarning($"[MUSIC] dying host: {why} (entry stays listed until observed destroyed; the respawned host retires it)");
            if (!ReferenceEquals(_host, dying)) return;   // a retired duplicate: no respawn
            _host = null;
            if (_quitting) return;
            _dyingHost = dying;   // RetireOtherHosts tells this routine retire from an unexpected one
            try { SpawnHost(); }
            finally { _dyingHost = null; }
            // [I1] failed respawn: nothing ticks again, so a held suppression
            // would silence vanilla forever — durable fault releases it all.
            if (_host == null) EnterDurableFaultNoThrow("host-respawn-failed");
        }
        private static MusicEngineHost _dyingHost;

        /// <summary>Rule (a): the ONLY remover of a host entry. An entry
        /// leaves when its captured GameObject reads as Unity-null — for a
        /// retired entry only on a frame after its Destroy was issued (Destroy
        /// is deferred to end of frame, #278, so the observation is
        /// necessarily later; the guard makes the rule literal). A GameObject
        /// that was never captured cannot be observed destroyed, so its entry
        /// stays.</summary>
        private static void PruneObservedNullHosts()
        {
            int f = Time.frameCount;
            for (int i = Hosts.Count - 1; i >= 0; i--)
            {
                var e = Hosts[i];
                if ((object)e.Go == null || e.Go != null) continue;
                if (e.Retired && f <= e.RetiredFrame) continue;
                Hosts.RemoveAt(i);
            }
        }

        /// <summary>Rule (f): at a new host's adoption, every listed entry
        /// other than the adopted host and not yet observed destroyed is
        /// retired — live GameObject or not, and without needing to see a
        /// surviving source. The host whose OnDestroy raised this respawn is
        /// the routine case (its GameObject is usually dying with it, and the
        /// second Destroy is a no-op; after a component-only Destroy it is
        /// the Destroy that matters); any other entry is a defect signal. An
        /// entry already retired (a host this engine retired itself, now
        /// dying) is skipped: its Destroy was issued once and logged once.</summary>
        private static void RetireOtherHosts(MusicEngineHost keep)
        {
            PruneObservedNullHosts();
            for (int i = Hosts.Count - 1; i >= 0; i--)
            {
                var e = Hosts[i];
                if (ReferenceEquals(e.Host, keep) || e.Retired) continue;
                RetireHost(e, ReferenceEquals(e.Host, _dyingHost)
                    ? "the host whose OnDestroy raised this respawn (its GameObject is destroyed in case it outlived the component)"
                    : "listed host not observed destroyed at a new host's adoption");
            }
        }

        /// <summary>Rule (b)'s retire: the whole GameObject is Destroyed, so
        /// its AudioSources and their native voices go with it at end of
        /// frame (#278) — the one action that needs nothing from a source
        /// that just threw. Issued once per entry and logged once (rule f); a
        /// best-effort silence first, so a voice stops now rather than at end
        /// of frame. A Destroy that throws leaves the entry retired and never
        /// observed destroyed — every pair waiting on it holds at the window
        /// (rule d). Retiring the adopted host is noted for TickPlayback
        /// (rule e): its OnDestroy respawns as it always did.</summary>
        private static void RetireHost(HostEntry e, string why)
        {
            if (e.Retired) return;
            e.Retired = true;
            e.RetiredFrame = Time.frameCount;
            e.RetiredWhy = why;
            string silence = SilenceSources(e.Host);
            bool adopted = ReferenceEquals(e.Host, _host);
            bool routine = ReferenceEquals(e.Host, _dyingHost) && silence == null;
            try { UnityEngine.Object.Destroy(e.Go); }
            catch (Exception ex) { e.RetiredWhy = why = why + "; host destroy threw: " + ex.Message; routine = false; }
            string line = $"[MUSIC] host retired ({why}){(silence != null ? "; silence: " + silence : "")} — adopted={adopted}, listed={Hosts.Count}; the GameObject dies at end of frame and its entry leaves once observed destroyed";
            if (routine) Plugin.Log?.LogInfo(line); else Plugin.Log?.LogWarning(line);
            if (adopted) { _hostRetiredPending = why; _hostRetiredFrame = Time.frameCount; }
        }

        private static bool HostIsRetired(MusicEngineHost h)
        {
            for (int i = 0; i < Hosts.Count; i++) if (ReferenceEquals(Hosts[i].Host, h)) return Hosts[i].Retired;
            return false;
        }

        /// <summary>Best-effort Stop + unbind of both sources of a host;
        /// never throws, never retried. The return is a reason for the log
        /// (null when everything returned) — the guarantee is the
        /// GameObject's Destroy in RetireHost, not this.</summary>
        private static string SilenceSources(MusicEngineHost h)
        {
            string why = null;
            AudioSource m = null, p = null;
            try { if ((object)h != null) { m = h.Main; p = h.Preview; } }
            catch (Exception ex) { return "source read threw: " + ex.Message; }
            SilenceSource(m, "Main", ref why);
            SilenceSource(p, "Preview", ref why);
            return why;
        }

        private static void SilenceSource(AudioSource src, string name, ref string why)
        {
            try
            {
                if (src == null) return;
                src.Stop();
                src.clip = null;
            }
            catch (Exception ex) { why = (why == null ? "" : why + "; ") + name + " threw during silence: " + ex.Message; }
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

        // ── delivery heartbeat (design v2 §2.3.5; §7 2-2 / 2-7) ──────────

        private const long STALL_CALLBACK_US = 1000000L;   // no output frames delivered for 1 s of DSP time
        private const long STALL_SILENCE_SEC = 10L;        // 10 s of consecutive all-zero output at a non-zero volume
        private static long _hbFramesSeen = -1L;
        private static long _hbLastAdvanceUs;
        private static string _lastStallDetail = "";
        // Self-test counters (TickTestScript reads the deltas; diagnostic only).
        private static int _prematureResumeCount, _stallFaultCount, _noReadyTrackCount, _previewShareRefusals;
        private static readonly Dictionary<string, int> OpenCounts = new Dictionary<string, int>(StringComparer.Ordinal);

        private static long DspNowUs()
        {
            try { return (long)(AudioSettings.dspTime * 1000000.0); } catch { return 0L; }
        }

        /// <summary>Re-arm at every Main clip assignment / Play / UnPause: the
        /// delivered-frame baseline restarts from now on the DSP clock, so "no
        /// output since Play" trips after STALL_CALLBACK_US, and the silence
        /// run restarts too.</summary>
        private static void ArmDeliveryTap()
        {
            try
            {
                _hbLastAdvanceUs = DspNowUs();
                var h = _host;
                var tap = h != null ? h.Tap : null;
                if (tap == null) { _hbFramesSeen = -1L; return; }
                tap.Arm();
                _hbFramesSeen = tap.FramesDelivered;
            }
            catch { }
        }

        /// <summary>§7 2-2, evaluated on the main thread once per Custom tick.
        /// Both clocks belong to the audio system — AudioSettings.dspTime here,
        /// and frame counters that advance only when the tap's callback runs —
        /// never wall time; design v2 §2.3.5's premise is that the two stop
        /// together when the mixer pauses (focus loss, AudioListener.pause),
        /// so no gap grows there. Excluded states, where no output is owed:
        /// not playing, paused by the engine, muted, volume 0 (the fade-in's
        /// first frame; no 0.05 threshold, §7 2-2). A tap that never armed, or
        /// whose audio-thread callback ever threw, never trips: the heartbeat
        /// then does nothing rather than faulting healthy playback, and says
        /// so once.</summary>
        private static bool DeliveryStalled(AudioSource m, EngineState s)
        {
            var h = _host;
            var tap = h != null ? h.Tap : null;
            if (tap == null || m == null) return false;
            if (tap.Faults > 0) { LogOnce("tap-fault", "[MUSIC] delivery tap: the audio-thread callback threw — heartbeat inactive for this session", true); return false; }
            if (!m.isPlaying || s.mainPausedByUs || m.mute || m.volume <= 0f) return false;
            if (_hbFramesSeen < 0L) return false;
            long now = DspNowUs();
            long frames = tap.FramesDelivered;
            if (frames != _hbFramesSeen) { _hbFramesSeen = frames; _hbLastAdvanceUs = now; }
            else if (now - _hbLastAdvanceUs > STALL_CALLBACK_US)
            {
                _lastStallDetail = "no output for " + ((now - _hbLastAdvanceUs) / 1000L) + " ms";
                return true;
            }
            int hz = 0;
            try { hz = AudioSettings.outputSampleRate; } catch { }
            long silent = tap.SilentFrames;
            if (hz > 0 && silent > STALL_SILENCE_SEC * hz)
            {
                _lastStallDetail = "all-zero output for " + (silent / hz) + " s at volume " + m.volume.ToString("F2", System.Globalization.CultureInfo.InvariantCulture);
                return true;
            }
            return false;
        }

        // ── [Music] TestScript — engine exercise (design v2 §2.5; oracles §7 2-8) ──
        // Broadcast identity only (TestOpenTab's gate; that tick re-reads the cfg
        // file every 2 s). One script runs per DISTINCT cfg value; the value
        // present at launch runs too (a value written before launch runs at
        // startup). Steps run one at a time; a step ends when its
        // oracle is decided and logs `[MUSIC-SELFTEST] step=<n> <name> pass|fail <detail>`.
        // Named steps: s1 successor handoff, s2 tombstoned successor (loop off),
        // s3 preview over Main, s4 eviction, s5 suppression (Sandbox + broadcast
        // music; its release half waits for the Sandbox to end), s6 stall
        // injection, s6neg its negative control. Verbs: album:<sku>,
        // play:<sku>/<idx>, preview:<sku>/<idx>, fail:<sku>/<idx>, seek:len-<n>,
        // loop:on|off, shuffle:on|off, select:<sku>:<i,j,..>|all, stall, unstall,
        // stop, play-pause, skip, prev, use-vanilla, stop-preview, wait:<sec>, reset.

        private static string _tsLast;
        private static readonly List<string> _tsSteps = new List<string>();
        private static int _tsIdx = -1, _tsNo, _tsPass, _tsFail, _tsPhase;
        private static float _tsT0, _tsT1, _tsT2, _tsF0, _tsF1, _tsPendingSince = -1f;
        private static int _tsI0, _tsI1, _tsI2;
        private static long _tsL0;
        private static string _tsAlbum, _tsName, _tsArg;
        // impl2 r1 L1: the operator's configuration at script start — the exact
        // deselected set plus loop/shuffle — restored exactly at the end.
        private static HashSet<string> _tsSnapDeselected;
        private static bool _tsSnapLoop, _tsSnapShuffle;
        // impl2 r1 M2 / M1: bounds on the two waits the oracles used to skip.
        private const float TS_VANILLA_AUDIBLE_SEC = 5f;   // S2: vanilla Playing after the Loading edge
        private const float TS_LEDGER_SETTLE_SEC = 2f;     // S3: 3 entries / 6 objects / 0 pairs after the preview start

        internal static void TickTestScript()
        {
            if (!_initialized || _host == null) return;
            if (!BroadcastMode.IsBroadcastIdentity) return;
            var cfg = Plugin.MusicTestScript;
            if (cfg == null) return;
            string raw;
            try { raw = (cfg.Value ?? "").Trim(); } catch { return; }
            if (_tsIdx < 0)
            {
                if (raw.Length == 0 || raw == _tsLast) return;
                if (Time.realtimeSinceStartup < 6f) return;   // let the menu settle (TestOpenTab's rule)
                _tsLast = raw;
                _tsSteps.Clear();
                foreach (var part in raw.Split(';')) { var p = part.Trim(); if (p.Length > 0) _tsSteps.Add(p); }
                if (_tsSteps.Count == 0) return;
                _tsIdx = 0; _tsNo = 0; _tsPass = 0; _tsFail = 0; _tsAlbum = null;
                TsSnapshot();
                Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] start steps={_tsSteps.Count} script='{raw}' snapshot: deselected={(_tsSnapDeselected != null ? _tsSnapDeselected.Count : -1)} loop={_tsSnapLoop} shuffle={_tsSnapShuffle}");
                TsBegin();
                return;
            }
            try { TsRun(); }
            catch (Exception ex) { TsEnd(false, "exception: " + ex.Message); }
        }

        private static float TsRt => Time.realtimeSinceStartup;
        private static string TsCurrentKey() => S.current.HasValue ? S.current.Value.ToString() : "none";
        private static bool TsMainPlaying() { var h = _host; return h != null && h.Main != null && h.Main.isPlaying; }
        private static float TsMainTime() { try { var h = _host; return h != null && h.Main != null ? h.Main.time : -1f; } catch { return -1f; } }
        private static bool TsStartedOn(string key) => S.mode == MusicMode.Custom && S.currentStarted && TsCurrentKey() == key && TsMainPlaying();
        private static MusicDeliveryTap TsTap() { var h = _host; return h != null ? h.Tap : null; }
        private static int TsOpens(string key) => OpenCounts.TryGetValue(key, out var n) ? n : 0;
        private static string TsKey(int idx) => _tsAlbum + "/" + idx;
        private static bool TsSandboxLive() { try { var gt = GM_Test.instance; return gt != null && gt.isActiveAndEnabled; } catch { return false; } }
        private static string TsVanilla(bool menu)
        {
            try { var mgr = SoundMusicManager.Instance; return mgr == null ? "no-manager" : VanillaMusicState(mgr, menu).ToString(); }
            catch { return "?"; }
        }
        private static string TsState()
        {
            var tap = TsTap();
            return $"mode={S.mode} current={TsCurrentKey()} started={S.currentStarted} playing={TsMainPlaying()} t={TsMainTime():F1} suppress={S.suppress} waiting={S.waiting} stopIntent={S.stopIntent} fault={(S.faultDurable ? S.faultReason : "none")} entries={EntryCount()} live={LiveObjectCount()} pendingRelease={PendingRelease.Count} held={HeldPairCount()} hosts={Hosts.Count} tapCallbacks={(tap != null ? tap.Callbacks : -1)} admissible={MusicAdmission.AtAdmissibleMenu}";
        }

        private static void TsLog(bool pass, string name, string detail)
        {
            if (pass) _tsPass++; else _tsFail++;
            Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] step={_tsNo} {name} {(pass ? "pass" : "fail")} {detail}");
        }

        private static void TsEnd(bool pass, string detail)
        {
            TsLog(pass, _tsName, detail);
            TsAdvance();
        }

        private static void TsAdvance()
        {
            _tsIdx++;
            if (_tsIdx >= _tsSteps.Count)
            {
                TsRestore();
                Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] end pass={_tsPass} fail={_tsFail}");
                _tsIdx = -1;
                return;
            }
            TsBegin();
        }

        private static void TsSnapshot()
        {
            try
            {
                RefreshDeselectedCache();
                _tsSnapDeselected = new HashSet<string>(S.deselected, StringComparer.Ordinal);
                _tsSnapLoop = LoopEnabled;
                _tsSnapShuffle = ShuffleEnabled;
            }
            catch (Exception ex) { _tsSnapDeselected = null; Plugin.Log?.LogWarning("[MUSIC-SELFTEST] snapshot failed: " + ex.Message); }
        }

        /// <summary>impl2 r1 L1: restore EXACTLY the snapshot — the deselected
        /// set as it was (a track deselected before the script stays
        /// deselected, one selected before it is selected again), then loop and
        /// shuffle. One persistence write and one Reconcile for the set; the
        /// setters' own Reconcile for the two flags. A preview a failed step
        /// left running is stopped first.</summary>
        private static void TsRestore()
        {
            try
            {
                var tap = TsTap(); if (tap != null) tap.Frozen = false;
                if (S.previewTrack.HasValue || S.previewPending.HasValue) StopPreviewAndRestoreInternal("self-test-end");
                var snap = _tsSnapDeselected;
                if (snap == null) Plugin.Log?.LogWarning("[MUSIC-SELFTEST] no snapshot — selection left as the script set it");
                else
                {
                    RefreshDeselectedCache();
                    if (!S.deselected.SetEquals(snap))
                    {
                        S.deselected.Clear();
                        S.deselected.UnionWith(snap);
                        PersistDeselected();
                        S.queueSignature = null;
                        Reconcile("self-test-restore");
                    }
                }
                if (LoopEnabled != _tsSnapLoop) LoopEnabled = _tsSnapLoop;
                if (ShuffleEnabled != _tsSnapShuffle) ShuffleEnabled = _tsSnapShuffle;
                Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] restored: deselected={S.deselected.Count} loop={LoopEnabled} shuffle={ShuffleEnabled}");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[MUSIC-SELFTEST] restore failed: " + ex.Message); }
        }

        private static MusicAlbumDef TsAlbumDef()
        {
            if (_tsAlbum != null) return MusicCatalog.Get(_tsAlbum);
            MusicAlbumDef best = null;
            foreach (var a in MusicCatalog.Albums)
            {
                if (a == null || a.Tracks == null || a.Tracks.Length < 2 || IsVanillaSku(a.Sku) || !IsAlbumPlayable(a.Sku)) continue;
                if (best == null || (best.Tracks.Length < 4 && a.Tracks.Length >= 4)) best = a;
            }
            if (best != null) _tsAlbum = best.Sku;
            return best;
        }

        /// <summary>Common precondition of every named step: tap unfrozen, no
        /// preview, loop and shuffle off, this album's tombstones and every
        /// Failed entry cleared, the selection reduced to the given track
        /// indices (null = all). Returns a failure detail, or null.</summary>
        private static string TsSetup(int[] tracks, int minTracks)
        {
            var a = TsAlbumDef();
            if (a == null) return "no playable custom album (set album:<sku>, or this seat owns none)";
            if (a.Tracks.Length < minTracks) return $"album {_tsAlbum} has {a.Tracks.Length} tracks; the step needs {minTracks}";
            var tap = TsTap(); if (tap != null) tap.Frozen = false;
            if (S.previewTrack.HasValue || S.previewPending.HasValue) StopPreviewAndRestoreInternal("self-test");
            LoopEnabled = false; ShuffleEnabled = false;
            var drop = new List<string>();
            foreach (var k in Tombstones) if (k.StartsWith(_tsAlbum + "/", StringComparison.Ordinal) || k.StartsWith("p:" + _tsAlbum + "/", StringComparison.Ordinal)) drop.Add(k);
            foreach (var k in drop) Tombstones.Remove(k);
            drop.Clear();
            foreach (var kv in Clips) if (kv.Value.Failed) drop.Add(kv.Key);
            foreach (var k in drop) { var e = Clips[k]; Clips.Remove(k); DisposeEntry(e); }
            for (int i = 0; i < a.Tracks.Length; i++) SetSelected(_tsAlbum, i, tracks == null || Array.IndexOf(tracks, i) >= 0);
            return null;
        }

        private static bool TsParseTrack(string arg, out string sku, out int idx)
        {
            sku = null; idx = -1;
            if (string.IsNullOrEmpty(arg)) return false;
            int slash = arg.LastIndexOf('/');
            if (slash <= 0) return false;
            sku = arg.Substring(0, slash);
            return int.TryParse(arg.Substring(slash + 1), out idx) && MusicCatalog.Get(sku) != null;
        }

        /// <summary>Test verb `fail:<key>`: tombstone the key (and release its
        /// entry) the way a failed open does.</summary>
        private static void TsFailKey(string key)
        {
            if (Clips.TryGetValue(key, out var e)) { Clips.Remove(key); DisposeEntry(e); }
            if (Tombstones.Add(key)) Plugin.Log?.LogInfo($"[MUSIC] tombstone {key} (self-test fail verb)");
            ClipStateGeneration++;
            if (TsCurrentKey() == key) RecoverFailedCurrent(key, "self-test"); else Reconcile("self-test-fail");
        }

        private static bool TsSeekLenMinus(float n)
        {
            var h = _host;
            if (h == null || h.Main == null || h.Main.clip == null) return false;
            if (S.mode != MusicMode.Custom || !S.currentStarted) return false;
            float len = h.Main.clip.length;
            if (len <= 0f) return false;
            SeekToFraction(Mathf.Clamp01((len - n) / len));
            return true;
        }

        private static void TsBegin()
        {
            string step = _tsSteps[_tsIdx];
            int colon = step.IndexOf(':');
            _tsName = (colon < 0 ? step : step.Substring(0, colon)).Trim().ToLowerInvariant();
            _tsArg = colon < 0 ? "" : step.Substring(colon + 1).Trim();
            _tsNo++; _tsPhase = 0; _tsT0 = TsRt; _tsPendingSince = -1f;
            string sku; int idx;
            switch (_tsName)
            {
                case "album":
                    if (MusicCatalog.Get(_tsArg) == null) { TsEnd(false, "unknown album " + _tsArg); return; }
                    _tsAlbum = _tsArg; TsEnd(true, _tsArg); return;
                case "play":
                    if (!TsParseTrack(_tsArg, out sku, out idx)) { TsEnd(false, "bad track " + _tsArg); return; }
                    PlayTrack(sku, idx); TsEnd(true, TsState()); return;
                case "preview":
                    if (!TsParseTrack(_tsArg, out sku, out idx)) { TsEnd(false, "bad track " + _tsArg); return; }
                    TogglePreview(sku, idx); TsEnd(true, TsState()); return;
                case "fail":
                    if (!TsParseTrack(_tsArg, out sku, out idx)) { TsEnd(false, "bad track " + _tsArg); return; }
                    TsFailKey(sku + "/" + idx); TsEnd(true, TsState()); return;
                case "seek":
                    {
                        float n;
                        if (!_tsArg.StartsWith("len-", StringComparison.Ordinal) || !float.TryParse(_tsArg.Substring(4), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out n)) { TsEnd(false, "want seek:len-<n>"); return; }
                        TsEnd(TsSeekLenMinus(n), TsState()); return;
                    }
                case "loop": LoopEnabled = _tsArg == "on"; TsEnd(true, "loop=" + LoopEnabled); return;
                case "shuffle": ShuffleEnabled = _tsArg == "on"; TsEnd(true, "shuffle=" + ShuffleEnabled); return;
                case "select":
                    {
                        int c = _tsArg.IndexOf(':');
                        string s2 = c < 0 ? _tsArg : _tsArg.Substring(0, c);
                        var a = MusicCatalog.Get(s2);
                        if (a == null || a.Tracks == null) { TsEnd(false, "unknown album " + s2); return; }
                        string list = c < 0 ? "all" : _tsArg.Substring(c + 1);
                        var on = new HashSet<int>();
                        if (list != "all") foreach (var t in list.Split(',')) { if (int.TryParse(t.Trim(), out var ti)) on.Add(ti); }
                        for (int i = 0; i < a.Tracks.Length; i++) SetSelected(s2, i, list == "all" || on.Contains(i));
                        TsEnd(true, "selected " + list); return;
                    }
                case "stall": { var tap = TsTap(); if (tap == null) { TsEnd(false, "no tap"); return; } tap.Frozen = true; TsEnd(true, "tap frozen"); return; }
                case "unstall": { var tap = TsTap(); if (tap != null) tap.Frozen = false; TsEnd(true, "tap live"); return; }
                case "stop": Stop(); TsEnd(true, TsState()); return;
                case "play-pause": PlayPause(); TsEnd(true, TsState()); return;
                case "skip": Skip(); TsEnd(true, TsState()); return;
                case "prev": PlayPrevious(); TsEnd(true, TsState()); return;
                case "use-vanilla": UseVanilla(); TsEnd(true, TsState()); return;
                case "stop-preview": StopPreviewAndRestore(); TsEnd(true, TsState()); return;
                case "reset": { string err = TsSetup(null, 2); TsEnd(err == null, err ?? TsState()); return; }
                case "wait":
                    if (!float.TryParse(_tsArg, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out _tsF0)) _tsF0 = 1f;
                    return;   // TsRun ends it
                case "s1": case "s2": case "s3": case "s4": case "s5": case "s6": case "s6neg":
                    return;   // multi-tick: TsRun drives the phases from phase 0
                default:
                    TsEnd(false, "unknown step"); return;
            }
        }

        private static void TsRun()
        {
            float rt = TsRt;
            switch (_tsName)
            {
                case "wait":
                    if (rt - _tsT0 >= _tsF0) TsEnd(true, $"{_tsF0:F1}s " + TsState());
                    return;
                case "s1": TsRunS1(rt); return;
                case "s2": TsRunS2(rt); return;
                case "s3": TsRunS3(rt); return;
                case "s4": TsRunS4(rt); return;
                case "s5": case "s5-release": TsRunS5(rt); return;
                case "s6": TsRunS6(rt, true); return;
                case "s6neg": TsRunS6(rt, false); return;
                default: TsEnd(false, "no runner"); return;
            }
        }

        // S1 (§2.5): play track 0, loop off, seek to len-10 -> track 1 is current
        // within 4 s of the expected end, no "no-ready-track" reconcile.
        private static void TsRunS1(float rt)
        {
            string k0 = TsKey(0), k1 = TsKey(1);
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1, 2, 3 }, 2);
                        if (err != null) { TsEnd(false, err); return; }
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (TsStartedOn(k0))
                    {
                        if (!TsSeekLenMinus(10f)) { TsEnd(false, "seek refused: " + TsState()); return; }
                        _tsI0 = _noReadyTrackCount; _tsT1 = rt; _tsPhase = 2; return;
                    }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not start within 20 s: " + TsState());
                    return;
                case 2:
                    if (S.faultDurable) { TsEnd(false, "durable fault: " + TsState()); return; }
                    if (_noReadyTrackCount != _tsI0) { TsEnd(false, "no-ready-track fired before the handoff: " + TsState()); return; }
                    if (TsStartedOn(k1)) { TsEnd(true, $"handoff to {k1} {rt - _tsT1:F1}s after the seek to len-10 (bound 14), opens[{k1}]={TsOpens(k1)}, {TsState()}"); return; }
                    if (rt - _tsT1 > 14f) TsEnd(false, "no handoff within 14 s of the seek: " + TsState());
                    return;
            }
        }

        // S2 (§7 2-8): selection {0,1}, loop OFF, track 1 tombstoned -> Loading
        // within 1 s of the end (no Waiting), vanilla AUDIBLE (the oracle reads
        // Playing) within TS_VANILLA_AUDIBLE_SEC of that edge and still at 60 s,
        // and the tombstoned key is never re-opened for 60 s (impl2 r1 M2:
        // "Loading + suppress=false" alone is also what a failing re-entry shows).
        private static void TsRunS2(float rt)
        {
            string k0 = TsKey(0), k1 = TsKey(1);
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1 }, 2);
                        if (err != null) { TsEnd(false, err); return; }
                        TsFailKey(k1);
                        _tsI1 = TsOpens(k1);
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (TsStartedOn(k0))
                    {
                        if (!TsSeekLenMinus(10f)) { TsEnd(false, "seek refused: " + TsState()); return; }
                        _tsT1 = rt; _tsF0 = -1f; _tsPhase = 2; return;
                    }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not start within 20 s: " + TsState());
                    return;
                case 2:
                    if (_tsF0 < 0f && (!TsMainPlaying() || S.mode != MusicMode.Custom)) _tsF0 = rt;   // the end
                    if (_tsF0 >= 0f)
                    {
                        if (S.mode == MusicMode.Loading)
                        {
                            if (S.suppress || S.waiting) { TsEnd(false, "Loading but suppress/waiting held: " + TsState()); return; }
                            _tsT2 = rt; _tsF1 = -1f; _tsPhase = 3; return;
                        }
                        if (rt - _tsF0 > 1f) TsEnd(false, "not Loading within 1 s of the end: " + TsState());
                        return;
                    }
                    if (rt - _tsT1 > 14f) TsEnd(false, "track 0 did not end within 14 s of the seek to len-10: " + TsState());
                    return;
                case 3:
                    {
                        if (TsOpens(k1) != _tsI1) { TsEnd(false, $"tombstoned {k1} was re-opened: " + TsState()); return; }
                        if (IsEngineOwned(S.mode) || S.suppress) { TsEnd(false, "engine re-owned or re-suppressed after the tombstoned end: " + TsState()); return; }
                        string van = TsVanilla(true);
                        bool audible = van == "Playing";
                        if (audible && _tsF1 < 0f)
                        {
                            if (S.mode != MusicMode.Loading) { TsEnd(false, $"vanilla audible but mode={S.mode} (want Loading): " + TsState()); return; }
                            _tsF1 = rt - _tsT2;   // first audible, seconds after the Loading edge
                        }
                        if (_tsF1 < 0f && rt - _tsT2 > TS_VANILLA_AUDIBLE_SEC) { TsEnd(false, $"vanilla not audible within {TS_VANILLA_AUDIBLE_SEC:F0} s of the Loading edge (oracle={van}, want Playing): " + TsState()); return; }
                        if (rt - _tsT2 >= 60f)
                            TsEnd(audible, $"Loading {(_tsT2 - _tsF0):F2}s after the end with loop off (no Waiting), unsuppressed; vanilla audible {_tsF1:F2}s after the edge (bound {TS_VANILLA_AUDIBLE_SEC:F0}) and at 60 s oracle={van} (want Playing) mode={S.mode}; opens[{k1}] delta 0 for 60 s; {TsState()}");
                        return;
                    }
            }
        }

        // S3 (§7 2-8): Main + resident successor + preview = 3 entries = 6 objects;
        // preview ownership starts and stops; Main resumes at its position.
        // impl2 r1 M1: production evicts the successor at preview admission (it
        // yields for the transaction — DesiredKeys) and re-requests it once the
        // preview has opened, so the six-object state arrives one request
        // (~0.1 s) after the preview starts: the count is awaited, bounded by
        // TS_LEDGER_SETTLE_SEC, and asserted then.
        private static void TsRunS3(float rt)
        {
            string k0 = TsKey(0), k1 = TsKey(1);
            var h = _host;
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1, 2 }, 3);
                        if (err != null) { TsEnd(false, err); return; }
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (TsStartedOn(k0)) { _tsT1 = rt; _tsPhase = 2; return; }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not start within 20 s: " + TsState());
                    return;
                case 2:
                    if (Clips.TryGetValue(k1, out var succ) && succ.Clip != null)
                    {
                        _tsF0 = TsMainTime(); _tsI0 = _previewShareRefusals;
                        TogglePreview(_tsAlbum, 2);
                        _tsT1 = rt; _tsPhase = 3; return;
                    }
                    if (rt - _tsT1 > 15f) TsEnd(false, "successor not resident within 15 s: " + TsState());
                    return;
                case 3:
                    if (S.mode == MusicMode.Preview && S.previewStarted && h != null && h.Preview != null && h.Preview.isPlaying)
                    {
                        bool distinct = h.Preview.clip != null && h.Preview.clip != h.Main.clip;
                        if (!distinct || _previewShareRefusals != _tsI0)
                        {
                            TsEnd(false, $"preview playing but distinct={distinct} shareRefusals delta={_previewShareRefusals - _tsI0}: " + TsState());
                            StopPreviewAndRestore();
                            return;
                        }
                        _tsT2 = rt; _tsPhase = 4; return;
                    }
                    if (rt - _tsT1 > 20f) TsEnd(false, "preview did not start within 20 s (needs the admissible main menu): " + TsState());
                    return;
                case 4:
                    {
                        int entries = EntryCount(), live = LiveObjectCount(), pairs = PendingRelease.Count;
                        if (entries == 3 && live == 6 && pairs == 0) { _tsF1 = rt - _tsT2; _tsT1 = rt; _tsPhase = 5; return; }
                        if (rt - _tsT2 > TS_LEDGER_SETTLE_SEC)
                        {
                            TsEnd(false, $"ledger did not reach 3 entries / 6 objects / 0 pairs within {TS_LEDGER_SETTLE_SEC:F0} s of the preview start: entries={entries} live={live} pairs={pairs}: " + TsState());
                            StopPreviewAndRestore();
                        }
                        return;
                    }
                case 5:
                    if (rt - _tsT1 >= 2f) { StopPreviewAndRestore(); _tsT1 = rt; _tsPhase = 6; }
                    return;
                case 6:
                    if (TsStartedOn(k0))
                    {
                        float t = TsMainTime();
                        bool posOk = t >= 0f && Mathf.Abs(t - _tsF0) <= 2f;
                        TsEnd(posOk, $"preview owned Main+successor+preview = 3 entries / 6 objects {_tsF1:F2}s after the preview start (bound {TS_LEDGER_SETTLE_SEC:F0}); Main resumed at {t:F1}s (paused near {_tsF0:F1}s, want within 2 s); shareRefusals delta {_previewShareRefusals - _tsI0}; {TsState()}");
                        return;
                    }
                    if (rt - _tsT1 > 10f) TsEnd(false, "Main did not resume within 10 s of the preview stop: " + TsState());
                    return;
            }
        }

        // S4 (§7 2-8): four tracks in sequence; the oldest key is dropped at each
        // handoff, the ledger never exceeds 2 x cap + 2 x pairs, and no release
        // pair stays queued longer than 1.0 s (impl2 r1 M3: per PAIR, from its
        // own QueuedRt, and strict — the nominal path is Destroy in the evicting
        // frame + Dispose on the next sweep; a failed step's 2 Hz retry is what
        // this bound reports).
        private static void TsRunS4(float rt)
        {
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(null, 4);
                        if (err != null) { TsEnd(false, err); return; }
                        _tsI0 = _ledgerOverBoundCount; _tsF0 = 0f; _tsF1 = 0f; _tsI1 = 0; _tsI2 = 0; _tsPendingSince = -1f;
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    {
                        int pr = PendingRelease.Count;
                        if (pr > 0)
                        {
                            if (_tsPendingSince < 0f) { _tsPendingSince = rt; _tsI2++; }
                            float age = MaxPendingPairAgeSec(rt);
                            if (age > _tsF0) _tsF0 = age;
                        }
                        else _tsPendingSince = -1f;
                        int live = LiveObjectCount();
                        if (live > _tsF1) _tsF1 = live;
                        if (_ledgerOverBoundCount != _tsI0) { TsEnd(false, $"ledger over bound (live={live}): " + TsState()); return; }
                        if (_tsF0 > 1.0f) { TsEnd(false, $"a release pair stayed queued {_tsF0:F2}s (bound 1.0 strict): " + TsState()); return; }
                        if (TsStartedOn(TsKey(_tsI1)))
                        {
                            if (_tsI1 >= 2 && Clips.ContainsKey(TsKey(_tsI1 - 2))) { TsEnd(false, $"oldest key {TsKey(_tsI1 - 2)} still resident after {TsKey(_tsI1)} started: " + TsState()); return; }
                            if (_tsI1 < 3) { _tsI1++; PlayTrack(_tsAlbum, _tsI1); _tsT1 = rt; return; }
                            _tsT1 = rt; _tsPhase = 2; return;
                        }
                        if (rt - _tsT1 > 20f) TsEnd(false, $"track {_tsI1} did not start within 20 s: " + TsState());
                        return;
                    }
                case 2:
                    {
                        float age = MaxPendingPairAgeSec(rt);
                        if (age > _tsF0) _tsF0 = age;
                        if (PendingRelease.Count == 0) { TsEnd(true, $"4 tracks in sequence: queueStretches={_tsI2} peakLive={_tsF1:F0} (bound {2 * RESIDENT_KEY_CAP} + 2 x pairs) maxPairAge={_tsF0:F2}s (bound 1.0 strict) overBound delta 0; {TsState()}"); return; }
                        if (_tsF0 > 1.0f) TsEnd(false, $"the last release pair stayed queued {_tsF0:F2}s (bound 1.0 strict): " + TsState());
                        return;
                    }
            }
        }

        // S5 (§2.5): inside the Sandbox with BroadcastCustomMusic on — engine-owned
        // playback, vanilla in-game music not playing, tap delivering; then the
        // release edge once the Sandbox ends (the operator/runner leaves it).
        private static void TsRunS5(float rt)
        {
            var tap = TsTap();
            switch (_tsPhase)
            {
                case 0:
                    if (!BroadcastPredicate()) { TsEnd(false, "BroadcastCustomMusic is off on this seat (BroadcastPredicate false)"); return; }
                    if (!TsSandboxLive()) { TsEnd(false, "not inside the Sandbox (GM_Test not live)"); return; }
                    if (tap == null) { TsEnd(false, "no delivery tap on the host"); return; }
                    _tsL0 = tap.FramesDelivered; _tsT1 = rt; _tsPhase = 1; return;
                case 1:
                    if (S.mode == MusicMode.Custom && S.suppress && BroadcastMusicLive && tap != null && tap.Callbacks > 0 && tap.FramesDelivered > _tsL0 && rt - _tsT1 >= 2f)
                    {
                        string van = TsVanilla(false);
                        bool vanillaSilent = van == "NotPlaying";
                        TsLog(vanillaSilent, "s5", $"engine-owned playback in the Sandbox: vanilla-ingame={van} (want NotPlaying) tapCallbacks={tap.Callbacks} frames={tap.FramesDelivered - _tsL0}; {TsState()}");
                        if (!vanillaSilent) { TsAdvance(); return; }
                        _tsName = "s5-release"; _tsNo++; _tsT2 = rt; _tsPhase = 2; return;
                    }
                    if (rt - _tsT1 > 30f) TsEnd(false, "no engine-owned playback within 30 s: " + TsState());
                    return;
                case 2:
                    if (!TsSandboxLive()) { _tsT1 = rt; _tsPhase = 3; return; }
                    if (rt - _tsT2 > 90f) TsEnd(false, "Sandbox exit not observed within 90 s — the release edge was not exercised (leave the Sandbox while this step waits)");
                    return;
                case 3:
                    if (!IsEngineOwned(S.mode) && !S.suppress) { TsEnd(true, $"released {rt - _tsT1:F1}s after the Sandbox ended: vanilla-menu={TsVanilla(true)}; {TsState()}"); return; }
                    if (rt - _tsT1 > 3f) TsEnd(false, "still owned 3 s after the Sandbox ended: " + TsState());
                    return;
            }
        }

        // S6 (§7 2-8): freeze the tap's production counters while audio keeps
        // flowing -> one resume, then durable fault "delivery-stalled" within
        // 3 s, suppression released. s6neg: the same run without the freeze
        // shows no fault and no resume in 60 s (#391 negative control).
        private static void TsRunS6(float rt, bool inject)
        {
            string k0 = TsKey(0);
            var tap = TsTap();
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1, 2 }, 2);
                        if (err != null) { TsEnd(false, err); return; }
                        if (tap == null) { TsEnd(false, "no delivery tap on the host"); return; }
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (TsStartedOn(k0)) { _tsT1 = rt; _tsL0 = tap.FramesDelivered; _tsPhase = 2; return; }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not start within 20 s: " + TsState());
                    return;
                case 2:
                    if (rt - _tsT1 < 1f) return;
                    if (tap.FramesDelivered <= _tsL0) { TsEnd(false, "no delivery observed in 1 s of playback (tap frames not advancing): " + TsState()); return; }
                    _tsI0 = _prematureResumeCount; _tsI1 = _stallFaultCount; _tsL0 = tap.FramesDelivered;
                    if (inject) tap.Frozen = true;
                    _tsT1 = rt; _tsPhase = 3; return;
                case 3:
                    if (inject)
                    {
                        if (S.faultDurable)
                        {
                            tap.Frozen = false;
                            float el = rt - _tsT1;
                            bool ok = S.faultReason == "delivery-stalled" && _prematureResumeCount - _tsI0 == 1 && _stallFaultCount - _tsI1 == 1 && !S.suppress && el <= 3f;
                            TsEnd(ok, $"durable fault '{S.faultReason}' {el:F2}s after the stall (want delivery-stalled within 3 s), resumes={_prematureResumeCount - _tsI0} (want 1), stallFaults={_stallFaultCount - _tsI1} (want 1), suppress={S.suppress} (want False); {TsState()}");
                            return;
                        }
                        if (rt - _tsT1 > 6f) { tap.Frozen = false; TsEnd(false, $"no durable fault within 6 s of the stall: resumes={_prematureResumeCount - _tsI0}; " + TsState()); }
                        return;
                    }
                    if (S.faultDurable) { TsEnd(false, "durable fault without a stall: " + TsState()); return; }
                    if (_prematureResumeCount != _tsI0) { TsEnd(false, "a resume fired without a stall: " + TsState()); return; }
                    if (rt - _tsT1 >= 60f) TsEnd(true, $"60 s without a fault or a resume (negative control): frames delivered {tap.FramesDelivered - _tsL0}; {TsState()}");
                    return;
            }
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
        internal MusicDeliveryTap Tap;   // §7 2-2: the delivery heartbeat's audio-thread half

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
            Tap = gameObject.AddComponent<MusicDeliveryTap>();
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

    /// <summary>§7 2-2: the delivery heartbeat's audio-thread half. Sits on
    /// the host GameObject beside Main, Preview and the duck LPF, so
    /// OnAudioFilterRead receives output from the sources on this object;
    /// MusicEngine evaluates the predicate only while it owns Custom playback,
    /// where the mode edge that entered Custom stopped Preview. Audio-thread
    /// work: two Interlocked adds and one zero scan — no allocation, no
    /// logging, no Unity API call (AudioSettings.dspTime is read on the main
    /// thread only). Longs are read with Interlocked.Read (a long cannot be
    /// volatile). Design v2 §2.3.5 prescribed DSP-microsecond stamps written
    /// on the audio thread; the frame counters carry the same two predicates
    /// (no delivery for 1 s of DSP time, 10 s of zeros) without calling into
    /// Unity from the audio thread.</summary>
    internal sealed class MusicDeliveryTap : MonoBehaviour
    {
        private long _framesDelivered;    // monotonic: audio frames handed to the output
        private long _silentFrames;       // consecutive all-zero frames, reset by the first non-zero sample
        /// <summary>Test lever (self-test S6): the production counters freeze while audio keeps flowing.</summary>
        internal volatile bool Frozen;
        /// <summary>Diagnostic: callbacks since Arm (self-test S5). Single writer; read racy on purpose.</summary>
        internal volatile int Callbacks;
        /// <summary>Non-zero once the callback body threw; the engine treats a faulted tap as absent.</summary>
        internal volatile int Faults;

        internal long FramesDelivered => System.Threading.Interlocked.Read(ref _framesDelivered);
        internal long SilentFrames => System.Threading.Interlocked.Read(ref _silentFrames);

        internal void Arm()
        {
            System.Threading.Interlocked.Exchange(ref _silentFrames, 0L);
            Callbacks = 0;
        }

        private void OnAudioFilterRead(float[] data, int channels)
        {
            try
            {
                Callbacks++;
                if (Frozen) return;
                int frames = channels > 0 ? data.Length / channels : data.Length;
                System.Threading.Interlocked.Add(ref _framesDelivered, frames);
                bool silent = true;
                for (int i = 0; i < data.Length; i++) { if (data[i] != 0f) { silent = false; break; } }
                if (silent) System.Threading.Interlocked.Add(ref _silentFrames, frames);
                else System.Threading.Interlocked.Exchange(ref _silentFrames, 0L);
            }
            catch { Faults++; }
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
