// The contract lists `internal enum MusicMode` beside the class and both
// sibling spellings landed in the same wave: CompetitiveUI compares
// MusicEngine.MusicMode.Custom (nested) while NativeUI takes a bare MusicMode
// parameter (top-level). The enum is nested (the canonical home) and this
// global alias makes the bare spelling resolve to the SAME type everywhere.
global using MusicMode = CompetitiveRounds.MusicEngine.MusicMode;

using System;
using System.Collections.Generic;
using System.Text;
using BepInEx.Logging;
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

        /// <summary>One loading or open disk clip. Lifecycle (design v3
        /// branch D, bug 346): request (a file:// read of the compressed OGG)
        /// → Downloaded (completed, not yet opened) → open (OpenStreamedClip:
        /// GetContent on a streamAudio=true handler hands back a clip whose
        /// samples FMOD decodes from the handler's buffer on its own stream
        /// thread — a 2-5 ms handle, no main-thread decode). The clip reads
        /// the request's buffer for as long as it exists, so a request on
        /// which GetContent was ever invoked lives until process exit, clip
        /// or no clip, and so does every clip: nothing releases while the
        /// engine lives, and nothing is disposed at quit (D1/D6). A key is
        /// requested once per process; a later selection reuses its resident
        /// entry (D3); the bound is the catalog (D2). The one dispose left is
        /// a request that failed BEFORE GetContent was invoked (D10: no clip
        /// can depend on it). Static (survives host respawn) per the hazards
        /// list.</summary>
        private sealed class ClipEntry
        {
            public string Key;
            public UnityWebRequest Req;       // in flight, awaiting its open, or the open clip's backing request — never disposed once GetContentInvoked
            public AudioClip Clip;
            public bool Failed;
            public bool Downloaded;           // request completed; the open runs on a following tick (one per frame)
            public bool GetContentInvoked;    // D10: set BEFORE GetContent is called; from then on Req is retained for the process
            public int RequestedFrame;
        }

        /// <summary>D10: a key whose open failed AFTER GetContent was invoked
        /// — it threw, returned null, or returned a clip the playability
        /// check rejects — and every ambiguous case (a DataProcessingError
        /// read, a null download handler, a SendWebRequest that threw after
        /// the request existed, a request dispose that threw). The request
        /// and any returned clip are rooted here for the process: never
        /// played, never bound to a source, never released (retention is the
        /// conservative direction, #276), counted on every [MUSIC-RESIDENCY]
        /// line as rooted_failed=. The key's tombstone is STICKY (never
        /// cleared in this process), so no second request for the key can
        /// ever exist: at most one entry, at most two objects, per key.</summary>
        private sealed class RootedFailedEntry
        {
            public string Key;
            public UnityWebRequest Req;
            public AudioClip Clip;
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
        // D10: post-GetContent failures, rooted for the process (RootedFailedEntry).
        private static readonly List<RootedFailedEntry> RootedFailed = new List<RootedFailedEntry>();
        /// <summary>r5 LOW 9: bumped on every request/clip state transition so
        /// the Music tab's 2 s repaint signature sees Downloaded/Failed/open
        /// changes (the status line repaints without a click).</summary>
        internal static int ClipStateGeneration;
        /// <summary>D2: the bound on resident entries is the CATALOG — every
        /// full track plus every preview (42 at ar3), computed from
        /// MusicCatalog at Initialize. Admission never refuses on a count: a
        /// key is requested once per process and a later selection reuses its
        /// resident entry (D3). AuditLedger compares entries + rooted_failed +
        /// probe_opens against it and logs `over-bound` — log only, never a
        /// refusal (§7 2-3, D14).</summary>
        private static int RESIDENT_ENTRY_BOUND;
        // D11/D12: the residency figures beside the entry counts — opens the
        // stream probe made (its pairs are retained too), the compressed bytes
        // every retained request holds (catalog sizes), and the native
        // allocator counter sampled before the engine's first request, so
        // native_delta_mb is a process figure prod logs carry.
        private static int _probeOpens;
        private static long _compressedBytes;
        private static long _nativeBaseline = -1L;
        private static readonly HashSet<string> OnceKeys = new HashSet<string>(StringComparer.Ordinal);
        private static readonly System.Random Rng = new System.Random();

        private static MusicEngineHost _host;
        /// <summary>D13: the GameObject of the host whose OnDestroy last ran
        /// while it was the adopted host. PollHost respawns once this reads
        /// Unity-null on a LATER frame (Destroy is deferred to end of frame,
        /// #278), so the resident clip is bound on the new host only — one
        /// reader per streamed clip — or, R2, once the wait hits its 15 s
        /// bound (`host-dying-stuck`: the object is abandoned, the respawn
        /// binds nothing and the durable fault releases suppression). One
        /// field; no host list.</summary>
        private static GameObject _dying;
        private static float _dyingSinceRt;
        private static int _dyingRetryStage;              // R2: Destroy re-issued at 5 s (1) and 10 s (2) of the dying wait
        private static bool _spawnWithoutRehydrate;       // R2: the host-dying-stuck respawn adopts without rebinding playback
        private static float _intruderLogRt = -999f;      // R3: duplicate-host line, at most once per 5 s
        private static float _hostLessLogRt = -999f;
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
                RESIDENT_ENTRY_BOUND = CatalogKeyCount();
                SpawnHost();
                // [I1] no host = no tick = no repair loop — never pretend.
                // D13: the fault releases suppression now; PollHost (the
                // plugin's per-frame poll) retries the spawn every frame.
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
                var t = new TrackRef(albumSku, trackIdx);
                // R10: a STICKY key (its open failed at or after GetContent,
                // D10) is refused BEFORE any state change — the current stays,
                // no preview is stopped, no fault is cleared, nothing is
                // opened; one line. The tab shows "Unavailable until the game
                // restarts" for it.
                if (!IsVanillaSku(albumSku) && StickyTombstones.Contains(t.ToString()))
                {
                    SafeLog(LogLevel.Info, $"[MUSIC] PlayTrack refused — {t} failed at its open earlier this session (unavailable until the game restarts)");
                    return;
                }
                if (S.previewTrack.HasValue) StopPreviewAndRestoreInternal("transport");
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
                // R10: a STICKY preview key is refused before any state change
                // (it can never be the playing preview: it never opened).
                if (StickyTombstones.Contains("p:" + t))
                {
                    SafeLog(LogLevel.Info, $"[MUSIC] preview refused — {t} failed at its open earlier this session (unavailable until the game restarts)");
                    return;
                }
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
                AuditLedger();   // D14: the ledger audit, every tick (logged at most once a minute)

                // Requests (a file read of the compressed OGG — never a decode)
                // for the desired keys, re-polled because a tier that finishes
                // installing fires no event. One request per key, ever (D3).
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
                    // D10: a post-open failure's entry has left Clips (rooted,
                    // sticky tombstone); a pre-open failure leaves its marker
                    // entry until an explicit click clears it. Nothing here
                    // disposes anything.
                    bool failed = IsFailedKey(ppk);
                    if (failed || (s.previewPendingRt >= 0f && rt - s.previewPendingRt > 30f))
                    {
                        Plugin.Log?.LogInfo($"[MUSIC] preview pending {s.previewPending.Value} dropped ({(failed ? "request failed" : "timeout")})");
                        s.previewPending = null;
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
            // v6 §2.2: the scans INSPECT readiness only — requests are made for
            // the desired set alone (KickDesiredLoads); what was once requested
            // stays resident (D1).
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
            // v6 §2.2 / D4: the desired set moved (new current/successor) —
            // the successor's request starts synchronously in this call. The
            // entry that left the desired set stays resident (D1: nothing is
            // displaced or released) and is reused if it is selected again.
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
        // §2.2: the DESIRED set is exactly {current, successor, preview}; a
        // block prefetch is a fourth desired key by construction (under D an
        // entry once requested stays resident, but a request is only ever
        // made for a desired key). An unopened successor at a track end means
        // WaitingForNext (loop the current), never a Loading detour — see
        // TickPlayback.

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
            // D: a resident clip stays resident when its key is tombstoned (the
            // self-test's fail verb; nothing releases), so readiness consults
            // the tombstone too — a tombstoned key is never playable.
            string key = t.ToString();
            return Clips.TryGetValue(key, out var e) && e.Clip != null && !e.Failed && !Tombstones.Contains(key) && !StickyTombstones.Contains(key);
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

        // ── lag-332 v6 §2.2: the desired set (what gets requested) ────────

        /// <summary>The ONLY keys a request is ever MADE for: the current
        /// track, its immediate successor, and the preview slot. Vanilla
        /// entries are never keys (their clips are the game's). Under D this
        /// set drives requests only — an entry stays resident after its key
        /// leaves the set (D1) and is reused when it returns (D3). Recomputed
        /// synchronously wherever the desired set can change
        /// (ReconcileResidency is called from ReconcileCore, AdoptCurrent and
        /// the transports) — never cached across a mutation.</summary>
        private static int DesiredKeys(string[] into)
        {
            var s = S;
            int n = 0;
            // r2 MEDIUM 12 — the preview TRANSACTION: while a replacement Q is
            // Pending, the slot holds BOTH the fallback P (active or retained)
            // and Q, and the SUCCESSOR yields for the duration (at most three
            // desired keys, as before); P leaves the slot only once Q has opened
            // and taken ownership (previewPending cleared by StartPreviewOwnership).
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
        /// physical residency. Two classes (D10): a RETRYABLE tombstone (the
        /// request failed before GetContent was invoked; disposed at once) is
        /// cleared by an explicit retry only — a PlayTrack of that key, a
        /// Preview click of that key; a STICKY tombstone (the open failed at
        /// or after GetContent was invoked; request and clip rooted) is never
        /// cleared in this process — an explicit click shows the existing
        /// unavailable state and opens nothing.</summary>
        private static readonly HashSet<string> Tombstones = new HashSet<string>(StringComparer.Ordinal);
        private static readonly HashSet<string> StickyTombstones = new HashSet<string>(StringComparer.Ordinal);

        private static bool IsFailedKey(string key)
        {
            if (key == null) return false;
            return Tombstones.Contains(key) || StickyTombstones.Contains(key) || (Clips.TryGetValue(key, out var e) && e.Failed);
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
                SafeLog(LogLevel.Info, $"[MUSIC] failed current {key} parked as an ended cursor ({why}) — no successor is ready yet");   // R7: after the transitions it describes
            }
            Reconcile("current-failed:" + why);
        }
        private static string _failedCurrentPending, _failedCurrentPendingWhy;
        /// <summary>Records that the CURRENT key failed inside a residency
        /// pass or an enumeration, for DrainFailedCurrent (r7 MEDIUM 1). The
        /// tombstone itself is the caller's: MarkFailed (retryable) or
        /// RootFailed (sticky), D10.</summary>
        private static void NoteKeyFailedDeferred(ClipEntry e, string why)
        {
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

        /// <summary>D10, the PRE-GetContent class: the read finished with a
        /// ConnectionError or ProtocolError result and GetContent was never
        /// invoked, so no clip can depend on the buffer — the request is
        /// disposed at once and the key gets a RETRYABLE tombstone; the
        /// hollow entry stays in Clips as the failed marker until an explicit
        /// click clears it (the status line counts it once). A Dispose that
        /// throws is an ambiguous case: the request is rooted instead.</summary>
        private static void FailBeforeOpen(ClipEntry e)
        {
            var req = e.Req;
            e.Req = null; e.Downloaded = false;
            if (req != null)
            {
                try { req.Dispose(); }
                catch (Exception ex) { RootFailed(e, req, null, "dispose threw: " + ex.Message); return; }
                NoteCompressedBytes(e.Key, -1);
            }
            MarkFailed(e);
        }

        private static void MarkFailed(ClipEntry e)
        {
            e.Failed = true;
            ClipStateGeneration++;
            if (e.Key != null && !StickyTombstones.Contains(e.Key) && Tombstones.Add(e.Key)) SafeLog(LogLevel.Info, $"[MUSIC] tombstone {e.Key} (failed before its open — retry only by an explicit click)");
        }

        /// <summary>D10, the POST-GetContent class (and every ambiguous case):
        /// the entry leaves Clips, its request and any returned clip are
        /// rooted for the process (RootedFailedEntry: never played, never
        /// bound, never released) and the key's tombstone is STICKY. Callers
        /// run the recovery tail themselves (§7 2-1). Never called inside an
        /// enumeration of Clips (it removes from it).</summary>
        private static void RootFailed(ClipEntry e, UnityWebRequest req, AudioClip clip, string why)
        {
            e.Failed = true;
            e.Req = null; e.Clip = null; e.Downloaded = false;
            if (e.Key != null && Clips.TryGetValue(e.Key, out var listed) && ReferenceEquals(listed, e)) Clips.Remove(e.Key);
            if (req != null || clip != null) RootedFailed.Add(new RootedFailedEntry { Key = e.Key, Req = req, Clip = clip });
            ClipStateGeneration++;
            if (e.Key == null) return;
            Tombstones.Remove(e.Key);
            if (StickyTombstones.Add(e.Key)) SafeLog(LogLevel.Info, $"[MUSIC] tombstone {e.Key} (failed at or after its open: {why} — request{(clip != null ? " and clip" : "")} rooted for the session, never retried; rooted_failed={RootedFailed.Count})");
        }

        /// <summary>The explicit-click path (D10): clears a RETRYABLE
        /// tombstone and drops the hollow marker entry a pre-open failure
        /// left, so the key can be requested again. A STICKY key stays
        /// unavailable and nothing is opened — PlayTrack and TogglePreview
        /// refuse it before reaching here (R10); the check below is the
        /// backstop for any other caller. An entry on which GetContent was
        /// invoked is never disposed here or anywhere.</summary>
        private static void ClearTombstone(string key)
        {
            if (key == null) return;
            if (StickyTombstones.Contains(key)) { SafeLog(LogLevel.Info, $"[MUSIC] {key} failed at its open earlier this session — stays unavailable (nothing opened)"); return; }
            if (Tombstones.Remove(key)) SafeLog(LogLevel.Info, $"[MUSIC] retry {key} (tombstone cleared by an explicit click)");
            if (Clips.TryGetValue(key, out var e) && e.Failed)
            {
                if (e.GetContentInvoked || e.Req != null || e.Clip != null) return;   // holds objects: retained for the process (D1)
                Clips.Remove(key);
                ClipStateGeneration++;
            }
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
        /// admission input. Each request and each clip counts once: an open
        /// entry is 2, an entry awaiting its open 1, and every rooted failure
        /// (D10) its request plus its clip.</summary>
        private static int LiveObjectCount()
        {
            int c = 0;
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Clip != null) c++;
                if (e.Req != null) c++;
            }
            for (int i = 0; i < RootedFailed.Count; i++)
            {
                var r = RootedFailed[i];
                if (r.Req != null) c++;
                if (r.Clip != null) c++;
            }
            return c;
        }

        /// <summary>Entries holding a request or a clip. A pre-open failure's
        /// marker entry holds neither; a rooted failure is not an entry.</summary>
        private static int EntryCount()
        {
            int c = 0;
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Clip != null || e.Req != null) c++;
            }
            return c;
        }

        /// <summary>D2: the catalog bound — every full track plus every
        /// preview of every album in MusicCatalog.</summary>
        private static int CatalogKeyCount()
        {
            int n = 0;
            try
            {
                var albums = MusicCatalog.Albums;
                for (int i = 0; i < albums.Length; i++)
                    if (albums[i] != null && albums[i].Tracks != null) n += 2 * albums[i].Tracks.Length;
            }
            catch { }
            return n;
        }

        /// <summary>Compressed size the catalog records for a key's file (the
        /// OGG a request holds in its buffer); 0 for an unknown key.</summary>
        private static long CatalogBytesForKey(string key)
        {
            try
            {
                bool preview = key.StartsWith("p:", StringComparison.Ordinal);
                if (!TrackRef.TryParse(preview ? key.Substring(2) : key, out var t)) return 0L;
                var a = MusicCatalog.Get(t.Sku);
                if (a == null || a.Tracks == null || t.Idx < 0 || t.Idx >= a.Tracks.Length) return 0L;
                return preview ? a.Tracks[t.Idx].PreviewSize : a.Tracks[t.Idx].OggSize;
            }
            catch { return 0L; }
        }

        private static void NoteCompressedBytes(string key, int sign)
        {
            long b = CatalogBytesForKey(key);
            _compressedBytes += sign < 0 ? -b : b;
            if (_compressedBytes < 0L) _compressedBytes = 0L;
        }

        private static long NativeAlloc()
        {
            try { return UnityEngine.Profiling.Profiler.GetTotalAllocatedMemoryLong(); } catch { return -1L; }
        }

        /// <summary>D12/R11: the native allocator counter is sampled once, at
        /// the ENGINE's first request creation (EnsureClipLoading, before it
        /// allocates); every residency line prints the delta since then.
        /// Probe allocations before it are excluded — the probe keeps its own
        /// baseline for its own rows — so `native_delta_mb=?` on a probe line
        /// means the engine has not requested yet.</summary>
        private static void SeedNativeBaseline()
        {
            if (_nativeBaseline < 0L) _nativeBaseline = NativeAlloc();
        }

        private static double NativeDeltaMb()
        {
            if (_nativeBaseline < 0L) return double.NaN;
            long now = NativeAlloc();
            if (now < 0L) return double.NaN;
            return (now - _nativeBaseline) / 1048576.0;
        }

        private static string NativeDeltaMbText()
        {
            double d = NativeDeltaMb();
            return double.IsNaN(d) ? "?" : d.ToString("+0.0;-0.0;0.0", System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>The tail every [MUSIC-RESIDENCY] line carries (D12): the
        /// entry and object counts, the rooted failures, the probe's opens,
        /// the compressed bytes held and the native delta since the first
        /// request.</summary>
        private static string ResidencyFields()
        {
            return $"entries={EntryCount()} live={LiveObjectCount()} rooted_failed={RootedFailed.Count} probe_opens={_probeOpens} compressed_mb={(_compressedBytes / 1048576.0).ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} native_delta_mb={NativeDeltaMbText()}";
        }

        /// <summary>D11/R8: the stream probe reports each open RECORD it
        /// writes (one per key per process, written before it allocates; a
        /// record whose allocation threw is counted too and holds no bytes).
        /// It retains its pair like the engine does. R11: this does NOT seed
        /// the engine's native baseline — that is the engine's first request.</summary>
        internal static void NoteProbeOpen(string probeKey, long compressedBytes)
        {
            try
            {
                _probeOpens++;
                _compressedBytes += Math.Max(0L, compressedBytes);
                SafeLog(LogLevel.Info, $"[MUSIC-RESIDENCY] probe {probeKey} {ResidencyFields()}");
            }
            catch { }
        }

        private static float _ledgerOverBoundLogRt = -999f;
        /// <summary>D14: entries + rooted failures + probe opens against the
        /// catalog bound (D2). A breach is logged at most once a minute and
        /// changes nothing — the ledger never refuses anything (§7 2-3).</summary>
        private static void AuditLedger()
        {
            int count = EntryCount() + RootedFailed.Count + _probeOpens;
            if (count <= RESIDENT_ENTRY_BOUND) return;
            float rt = Time.realtimeSinceStartup;
            if (rt - _ledgerOverBoundLogRt < 60f) return;
            _ledgerOverBoundLogRt = rt;
            SafeLog(LogLevel.Warning, $"[MUSIC-RESIDENCY] over-bound count={count} bound={RESIDENT_ENTRY_BOUND} {ResidencyFields()}");   // R12: `count=` (no pair state exists to be `held`)
        }

        /// <summary>D4: the desired set's OPEN job only — every desired key
        /// that holds no entry gets a request. Nothing is displaced: a key
        /// that leaves the desired set keeps its entry (D1), and a later
        /// selection of it is a reuse (D3).</summary>
        private static void ReconcileResidency()
        {
            try { KickDesiredLoads(); }
            catch (Exception ex) { LogOnce("resid", "[MUSIC] residency reconcile failed: " + ex.Message, true); }
        }

        /// <summary>Request (never decode) each desired key that holds no
        /// entry. No count gates it (D2): a resident key is reused, so at
        /// most one request per key ever exists.</summary>
        private static void KickDesiredLoads()
        {
            var keys = _desiredScratch;
            int n = DesiredKeys(keys);
            for (int i = 0; i < n; i++)
            {
                string key = keys[i];
                if (Clips.ContainsKey(key)) continue;
                if (Tombstones.Contains(key) || StickyTombstones.Contains(key)) continue;   // r3 MEDIUM 2 / D10: a failed key is never auto-requested
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

        /// <summary>Music-tab status line (design v2 §2.3.2 — replaces the
        /// Prepare affordance): what the desired set's requests are doing for the
        /// desired custom keys. null = nothing to say (every desired key is
        /// open). Not a control: a RETRYABLE failed key is retried by that
        /// track's own Play (ClearTombstone), the tier install by the Shop; a
        /// STICKY key (D10) has its own line and nothing retries it (R10).</summary>
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
                // exactly once — a RETRYABLE tombstone or a Failed entry on the
                // retry line; a STICKY tombstone (D10) on its own line (R10:
                // a click retries nothing, so the line promises nothing). The
                // retry line wins while any retryable key exists (it is the
                // actionable one); the sticky line shows once none is left.
                var failedKeys = new HashSet<string>(StringComparer.Ordinal);
                var stickyKeys = new HashSet<string>(StringComparer.Ordinal);
                foreach (var tk in StickyTombstones) if (!tk.StartsWith("p:", StringComparison.Ordinal)) stickyKeys.Add(tk);
                foreach (var tk in Tombstones) if (!tk.StartsWith("p:", StringComparison.Ordinal) && !stickyKeys.Contains(tk)) failedKeys.Add(tk);
                foreach (var kv in Clips) if (kv.Value.Failed && !kv.Key.StartsWith("p:", StringComparison.Ordinal) && !stickyKeys.Contains(kv.Key)) failedKeys.Add(kv.Key);
                if (failedKeys.Count > 0) return I18n.TrF("Music failed to load ({0}) — play the track to retry", failedKeys.Count);
                if (stickyKeys.Count > 0) return I18n.Tr("Unavailable until the game restarts");
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

        /// <summary>D3: one request per key per process — a key that already
        /// holds an entry (registered BEFORE any throwing call) or a rooted
        /// record (D10) returns at once, so a re-selection binds the resident
        /// clip and never requests again. This is THE request-creation site
        /// and the guard lives here (R5): a creation that finds the key
        /// resident counts on DuplicateRequests — the once-only oracle S3/S4
        /// assert reads 0 — and is reachable only through the s4neg hook.
        /// `selfTest` (the openall and s4neg verbs only) skips the desired-key
        /// gate.</summary>
        private static void EnsureClipLoading(string key, string path, bool selfTest = false)
        {
            bool resident = Clips.ContainsKey(key) || HasRootedRecord(key);
            bool forced = _tsForceDuplicateOnce;
            _tsForceDuplicateOnce = false;
            if (resident && !forced) return;
            // lag-332 v6 §2.2: a request may only exist for a desired key.
            if (!selfTest && !IsDesiredKey(key)) return;
            if (resident) DuplicateRequests++;   // R5: a second request for a key that already holds one (the guard above removed, or s4neg)
            // r1 MEDIUM 12: ownership is established in the counted set BEFORE
            // any throwing operation, so a request that throws mid-construction
            // can never exist uncounted; the failure path roots the handle (D10).
            var entry = new ClipEntry { Key = key, RequestedFrame = Time.frameCount };
            Clips[key] = entry;
            UnityWebRequest req = null;
            try
            {
                string url;
                try { url = new Uri(path).AbsoluteUri; }
                catch { url = "file:///" + path.Replace('\\', '/'); }
                SeedNativeBaseline();   // D12: before the first allocation
                req = UnityWebRequestMultimedia.GetAudioClip(url, AudioType.OGGVORBIS);
                entry.Req = req;
                OpenCounts[key] = (OpenCounts.TryGetValue(key, out var oc) ? oc : 0) + 1;   // D15: requests created per key since init (diagnostic)
                NoteCompressedBytes(key, +1);
                ClipStateGeneration++;
                var dh = req.downloadHandler as DownloadHandlerAudioClip;
                // STREAMED (design v2 §2.2, bug 346): the clip reads the handler's
                // compressed buffer and FMOD decodes on its own stream thread —
                // no main-thread decode exists. Measured on both seats (v2 §2.4):
                // GetContent 1.7-3.4 ms, +3.5 MB native per open, 0 stalls. The
                // request therefore lives as long as the clip — for the process
                // (D1). A handler that is not the audio handler cannot be
                // streamed: an ambiguous case, rooted below (D10).
                if (dh == null) throw new InvalidOperationException("no audio download handler on the request");
                dh.streamAudio = true;
                req.SendWebRequest();
                SafeLog(LogLevel.Info, $"[MUSIC-RESIDENCY] request {key} {ResidencyFields()}");   // R7: a throwing logger cannot root a healthy request
            }
            catch (Exception ex)
            {
                // D10: a request that exists but never completed cleanly is an
                // ambiguous case — rooted with a sticky tombstone, never
                // disposed. The current recovers at the next Tick entry (r7
                // MEDIUM 1: this runs inside a residency pass). R7: the
                // disposition first, the line after.
                RootFailed(entry, req, null, "request-start: " + ex.Message);
                NoteKeyFailedDeferred(entry, "request-start");
                LogOnce("load:" + key, $"[MUSIC] clip load start failed for {key}: {ex.Message}", true);
            }
        }

        /// <summary>R5: whether a rooted record (D10) exists for the key — the
        /// second half of the creation-site guard (a sticky key is not in
        /// Clips).</summary>
        private static bool HasRootedRecord(string key)
        {
            for (int i = 0; i < RootedFailed.Count; i++)
                if (string.Equals(RootedFailed[i].Key, key, StringComparison.Ordinal)) return true;
            return false;
        }

        /// <summary>Polls in-flight requests (no coroutines: a host respawn
        /// would kill them; the request objects are static and survive). A
        /// completed read is marked Downloaded; then AT MOST ONE downloaded
        /// entry per frame is opened by OpenStreamedClip, a Pending preview's
        /// entry first (§7 2-5) — the open and every failure disposition run
        /// OUTSIDE the enumeration (the open's bridge reconciles residency; a
        /// rooted failure leaves Clips).</summary>
        private static void PollClipLoads()
        {
            ClipEntry candidate = null;
            bool candidateIsPendingPreview = false;
            List<ClipEntry> failed = null;      // a read that finished without Success, or a request property that threw
            List<ClipEntry> revisited = null;   // R6: GetContentInvoked and not Ready — rooted without a second GetContent
            foreach (var kv in Clips)
            {
                var e = kv.Value;
                if (e.Req == null || e.Clip != null || e.Failed) continue;
                if (e.GetContentInvoked) { (revisited ?? (revisited = new List<ClipEntry>())).Add(e); continue; }
                if (!e.Downloaded)
                {
                    // R6: a request property that throws is an ambiguous case
                    // (D10) — rooted below, outside the enumeration, never
                    // re-read on a later frame.
                    bool done, ok;
                    try { done = e.Req.isDone; ok = done && e.Req.result == UnityWebRequest.Result.Success; }
                    catch { done = true; ok = false; }
                    if (!done) continue;
                    if (!ok)
                    {
                        (failed ?? (failed = new List<ClipEntry>())).Add(e);
                        continue;
                    }
                    e.Downloaded = true;
                    ClipStateGeneration++;
                }
                bool pp = s_previewPendingIs(e.Key);
                if (candidate == null || (pp && !candidateIsPendingPreview)) { candidate = e; candidateIsPendingPreview = pp; }
            }
            if (revisited != null)
            {
                for (int i = 0; i < revisited.Count; i++)
                {
                    var e = revisited[i];
                    RootFailed(e, e.Req, null, "open-revisited: GetContent was invoked and the entry is not Ready");
                    NoteKeyFailedDeferred(e, "open-revisited");
                }
            }
            if (failed != null)
            {
                for (int i = 0; i < failed.Count; i++)
                {
                    var e = failed[i];
                    UnityWebRequest.Result result;
                    string error;
                    try { result = e.Req.result; error = e.Req.error; }
                    catch (Exception ex) { result = UnityWebRequest.Result.DataProcessingError; error = "result read threw: " + ex.Message; }
                    // D10: a transport or HTTP failure with GetContent never
                    // invoked is the PRE class — disposed now, retryable; a
                    // DataProcessingError (or anything else) is ambiguous —
                    // rooted, sticky. R7: the disposition first, the line after.
                    if (!e.GetContentInvoked && (result == UnityWebRequest.Result.ConnectionError || result == UnityWebRequest.Result.ProtocolError)) FailBeforeOpen(e);
                    else RootFailed(e, e.Req, null, "read: " + result);
                    NoteKeyFailedDeferred(e, "download");   // r7 MEDIUM 1 recovery (drained below)
                    LogOnce("clipfail:" + e.Key, $"[MUSIC] clip read failed for {e.Key}: {error} ({result})", true);
                }
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
        /// failure tail are the former decode's (§7 2-1) with D10's
        /// disposition: GetContentInvoked is set BEFORE the call, so the
        /// request is never disposed from here on; on success the clip joins
        /// it in the entry for the process (D1) and the readiness bridge runs
        /// here; a throw, a null or an unplayable clip roots request and clip
        /// (sticky tombstone). R6: ONE try/catch covers everything from
        /// "request exists" to "entry Ready" — the GetContent call, the open
        /// line, the length/channels/frequency reads and the playability
        /// check — so any exception anywhere roots the entry exactly once and
        /// nothing between the request and Ready is retried (PollClipLoads
        /// roots an entry it revisits with GetContentInvoked set). §7 2-6: two
        /// hosts ticking in one frame produce one open (the frame guard).</summary>
        private static void OpenStreamedClip(ClipEntry e)
        {
            if (_lastOpenFrame == Time.frameCount) return;
            _lastOpenFrame = Time.frameCount;
            AudioClip clip = null;
            string what = null;
            e.GetContentInvoked = true;   // D10: BEFORE the call — a throwing GetContent may already have created FMOD state on the buffer
            try
            {
                long t0 = System.Diagnostics.Stopwatch.GetTimestamp();
                try { clip = DownloadHandlerAudioClip.GetContent(e.Req); }
                catch (Exception ex) { what = "GetContent threw: " + ex.Message; }
                double openMs = (System.Diagnostics.Stopwatch.GetTimestamp() - t0) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
                try { NetworkSeatTelemetry.NoteMusicOpenMs(openMs); } catch { }   // frame-component ledger (bundle-only): its own cause slot — no decode happens here (impl2 r1 L2)
                float lengthS = 0f; int ch = 0, hz = 0;
                if (what == null && clip == null) what = "null clip";
                if (clip != null) { lengthS = clip.length; ch = clip.channels; hz = clip.frequency; }   // R6: a throw here is the outer catch's — rooted
                if (what == null && lengthS <= 0.1f) what = "empty clip";
                SafeLog(LogLevel.Info, $"[MUSIC-OPEN] key={e.Key} getContentMs={openMs.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} lengthS={lengthS.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} ch={ch} hz={hz} entries={EntryCount()} live={LiveObjectCount() + (clip != null ? 1 : 0)}");
                _openLogNextFrame = e.Key;
                if (what == null)
                {
                    e.Clip = clip;   // Ready. Req stays: the streamed clip reads its buffer — both live for the process (D1)
                    e.Downloaded = false;
                    ClipStateGeneration++;
                }
            }
            catch (Exception ex) { what = what ?? ("open threw: " + ex.Message); }
            if (what == null)
            {
                // Completion bridge (moved verbatim from the click path, §2.3.1):
                // a Pending preview takes ownership now; readiness re-derives;
                // one reconcile publishes the edge. Past Ready, so outside R6's
                // try: an exception here is the tick's policy, not a root.
                if (s_previewPendingIs(e.Key)) StartPendingPreviewOwnership();
                bool ready = ScanHasReadyTrack();
                if (ready != S.hasReadyTrack) S.hasReadyTrack = ready;
                Reconcile("load-complete");
                return;
            }
            // D10 POST: request and any returned clip rooted, sticky tombstone
            // (a rejected NON-null clip is a native object; it is kept with
            // its request, never destroyed under a possible reader).
            RootFailed(e, e.Req, clip, what);
            // §7 2-1: the failure tail, verbatim — a failed CURRENT advances to a
            // ready successor or parks at Loading; anything else reconciles.
            // R7: the transitions and the recovery call run BEFORE the line
            // that describes them.
            bool readyAfterFail = ScanHasReadyTrack();
            if (readyAfterFail != S.hasReadyTrack) S.hasReadyTrack = readyAfterFail;
            if (S.current.HasValue && string.Equals(S.current.Value.ToString(), e.Key, StringComparison.Ordinal))
                RecoverFailedCurrent(e.Key, "open");
            else
                Reconcile("open-failed");
            LogOnce("clipfail:" + e.Key, $"[MUSIC] clip open failed for {e.Key}: {what}", true);
        }

        private static bool s_previewPendingIs(string key)
        {
            var p = S.previewPending;
            return p.HasValue && key == "p:" + p.Value;
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
            // §7 2-7: the one-resume charge is per TRACK — reset where the
            // current CHANGES (adopt, PlayTrack, Previous, preview restore,
            // current cleared), never here: this assignment is also what
            // rehydration performs on a fresh host, and a reset here would let
            // every host respawn buy the same track a new resume.
            if (m.clip != clip) { m.clip = clip; s.currentStarted = false; s.mainPausedByUs = false; ArmDeliveryTap(); }
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
                // now-unplayable current track. Its clips stay resident (D:
                // nothing releases); selection and PlayTrack refuse the album,
                // so nothing plays them.
                if (s.current.HasValue && !IsVanillaSku(s.current.Value.Sku) && !IsAlbumPlayable(s.current.Value.Sku))
                {
                    StopMainNoThrow();
                    s.current = null; s.resumePositionSec = 0f; s.currentStarted = false; s.mainPausedByUs = false;
                    s.currentEnded = false;
                }
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
            SafeLog(LogLevel.Info, $"[MUSIC] fault cleared by user transport ({action}) — retrying");   // R7 class: the flags above are cleared; a throw here would skip the caller's Reconcile
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

        /// <summary>Never throws: the logger in its catch is itself guarded,
        /// and whether the spawn adopted a host is judged by _host afterwards
        /// — Awake runs inside AddComponent, and an Awake that threw is logged
        /// by Unity, not raised here. Leaving without a host destroys the
        /// object whose Awake did not adopt, so PollHost's per-frame retry
        /// cannot leak one GameObject per attempt. A failure is logged at
        /// most once per 5 s (D13: the poll retries every frame).</summary>
        private static void SpawnHost()
        {
            GameObject go = null;
            try
            {
                go = new GameObject("CR_MusicEngine");
                go.hideFlags = HideFlags.HideAndDontSave;
                UnityEngine.Object.DontDestroyOnLoad(go);
                go.AddComponent<MusicEngineHost>();
            }
            catch (Exception ex)
            {
                try
                {
                    float rt = Time.realtimeSinceStartup;
                    if (rt - _hostLessLogRt >= 5f) { _hostLessLogRt = rt; Plugin.Log?.LogError($"[MUSIC] host spawn failed: {ex.Message} (retried every frame)"); }
                }
                catch { }
            }
            finally
            {
                if (_host == null && go != null) { try { UnityEngine.Object.Destroy(go); } catch { } }
            }
        }

        /// <summary>D13: the host respawn, STATELESS and UNCAPPED, from the
        /// plugin's persistent per-frame poll (Plugin.cs
        /// CompetitiveRoundsBehaviour.Update, beside MusicStreamProbe.Tick) —
        /// the engine's Tick is the host's Update, so nothing inside the
        /// engine can run without one. Spawns whenever no host is adopted and
        /// the last dying host's GameObject reads Unity-null (its Destroy is
        /// end-of-frame, #278, so that is necessarily a later frame — the
        /// observed-null rule with one field instead of a list). R2 bounds
        /// that wait: Destroy is issued again at 5 s and 10 s, and at 15 s the
        /// object is given up on (`host-dying-stuck`) — a host is spawned
        /// WITHOUT rehydrating playback and the durable fault releases
        /// suppression, so owned silence lasts at most 15 s and a streamed
        /// clip the abandoned object may still hold gets no second reader. A
        /// respawn that fails enters the durable fault once (suppression
        /// released: vanilla plays at the game's next own transition, design
        /// v3 §2.8) and is retried every frame; the fault's pending vanilla
        /// re-entry lands once a host ticks again.</summary>
        internal static void PollHost()
        {
            if (!_initialized || _quitting || Plugin.modDisabled) return;
            if (_host != null) return;
            var dying = _dying;
            if ((object)dying != null)
            {
                if (dying != null)
                {
                    // Not yet observed destroyed: routine for exactly one frame
                    // (the end-of-frame Destroy). Longer means that Destroy
                    // never landed — re-issued at 5 s and 10 s (one line each),
                    // given up on at 15 s.
                    float rt = Time.realtimeSinceStartup;
                    float age = rt - _dyingSinceRt;
                    if (age < 15f)
                    {
                        int stage = age >= 10f ? 2 : age >= 5f ? 1 : 0;
                        if (stage > _dyingRetryStage)
                        {
                            _dyingRetryStage = stage;
                            string outcome;
                            try { UnityEngine.Object.Destroy(dying); outcome = "Destroy issued again"; }
                            catch (Exception ex) { outcome = "Destroy threw again: " + ex.Message; }
                            SafeLog(LogLevel.Warning, $"[MUSIC] host-less for {age:F0} s: the dying host's GameObject is still not observed destroyed — {outcome} (given up on at 15 s)");
                        }
                        return;
                    }
                    // R2, the bound: the object is abandoned (its sources were
                    // silenced best-effort in OnHostDestroyed), a host is
                    // spawned WITHOUT rehydrating playback — nothing is bound
                    // on it — and the durable fault releases suppression;
                    // custom music waits for an explicit retry.
                    _dying = null;
                    _dyingRetryStage = 0;
                    SafeLog(LogLevel.Error, $"[MUSIC] host-dying-stuck: the dying host's GameObject was not observed destroyed within {age:F0} s — abandoned; respawning without rehydration, entering the durable fault");
                    _spawnWithoutRehydrate = true;
                    try { SpawnHost(); }
                    finally { _spawnWithoutRehydrate = false; }
                    EnterDurableFaultNoThrow("host-dying-stuck");
                    return;
                }
                _dying = null;
                _dyingRetryStage = 0;
            }
            SpawnHost();
            if (_host == null && !S.faultDurable) EnterDurableFaultNoThrow("host-respawn-failed");
        }

        internal static void OnHostAwake(MusicEngineHost host)
        {
            // R3: ONE adopted host. A component that wakes while a live host is
            // adopted is an intruder (nothing in this engine spawns while _host
            // is set — PollHost and Initialize spawn only when it is null):
            // its GameObject is destroyed at once, nothing is adopted or bound,
            // said so at most once per 5 s. Its OnDestroy hands nothing over
            // (OnHostDestroyed acts only for the adopted host).
            if (_host != null && !ReferenceEquals(_host, host))
            {
                try { UnityEngine.Object.Destroy(host.gameObject); } catch { }
                float rt = 0f;
                try { rt = Time.realtimeSinceStartup; } catch { }
                if (rt - _intruderLogRt >= 5f)
                {
                    _intruderLogRt = rt;
                    SafeLog(LogLevel.Warning, "[MUSIC] duplicate host component woke while a host is adopted — destroyed, not adopted (one host, one reader)");
                }
                return;
            }
            _host = host;
            var s = S;
            RouteSources();
            if (!s.everHosted) { s.everHosted = true; return; }
            if (_spawnWithoutRehydrate)
            {
                // R2: the host-dying-stuck respawn adopts and routes only — no
                // rebind, no Reconcile — so a clip the abandoned object may
                // still hold has no second reader; the durable fault that
                // follows releases suppression, and the explicit retry that
                // clears it re-derives everything on this host.
                SafeLog(LogLevel.Info, $"[MUSIC] host respawned after host-dying-stuck — adopted without rehydration (mode={s.mode})");
                return;
            }
            // Rehydration [F19]: the durable state object is authoritative; a
            // fresh host just re-derives its component state from it — the
            // resident clip is rebound on THIS host only (the dying host was
            // observed destroyed before PollHost spawned this one, D13).
            try
            {
                SafeLog(LogLevel.Info, $"[MUSIC] host respawned — rehydrating (mode={s.mode})");   // R7 class: a throwing logger must not enter the fault below
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

        /// <summary>D13: the COMPONENT's OnDestroy. Best effort first — the
        /// dying host's sources are silenced (a throw is caught and logged
        /// once) — then its whole GameObject is destroyed in its own
        /// try/catch (a component-only Destroy would leave the object and its
        /// AudioSources alive; destroying it kills the sources at end of
        /// frame, #278), and the finally ALWAYS hands the respawn to PollHost:
        /// `_dying = gameObject; _host = null`. Nothing here spawns; the poll
        /// does, once the object reads Unity-null on a later frame — or at
        /// the 15 s bound (R2, host-dying-stuck). Only the adopted host hands
        /// over — a component this engine did not adopt (an object whose
        /// Awake did not adopt, an R3 intruder) is silenced and destroyed but
        /// leaves the adopted host in place.</summary>
        internal static void OnHostDestroyed(MusicEngineHost dying)
        {
            bool adopted = ReferenceEquals(_host, dying);
            GameObject go = null;
            try { go = dying.gameObject; } catch { }
            try
            {
                string why = SilenceSources(dying);
                if (why != null && !_quitting) LogOnce("dying-host-silence", $"[MUSIC] dying host: {why} (its GameObject is destroyed with it)", true);
            }
            catch { }
            try { if ((object)go != null) UnityEngine.Object.Destroy(go); }
            catch (Exception ex) { try { LogOnce("dying-host-destroy", $"[MUSIC] dying host: GameObject destroy threw: {ex.Message}", true); } catch { } }
            finally
            {
                if (adopted)
                {
                    _dying = go;
                    _dyingRetryStage = 0;
                    try { _dyingSinceRt = Time.realtimeSinceStartup; } catch { }
                    _host = null;
                }
            }
        }

        /// <summary>Best-effort Stop + unbind of both sources of a host;
        /// never throws, never retried. The return is a reason for the log
        /// (null when everything returned) — the guarantee is the
        /// GameObject's Destroy in OnHostDestroyed, not this.</summary>
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

        /// <summary>R7: logging never changes media state. Every log call in
        /// the open path, the failure tail, RootFailed, FailBeforeOpen, the
        /// tombstone writers, the residency line and the probe's teardown
        /// goes through here — a logger that throws (a broken sink, a
        /// formatter) is swallowed, so no transition and no recovery call is
        /// skipped by the line that describes it.</summary>
        internal static void SafeLog(LogLevel level, string msg)
        {
            try { Plugin.Log?.Log(level, msg); } catch { }
        }

        private static void LogOnce(string key, string msg, bool warn)
        {
            if (!OnceKeys.Add(key)) return;
            SafeLog(warn ? LogLevel.Warning : LogLevel.Info, msg);
        }

        // ── delivery heartbeat (design v2 §2.3.5; §7 2-2 / 2-7) ──────────

        private const long STALL_CALLBACK_US = 1000000L;   // no output frames delivered for 1 s of DSP time
        private const long STALL_SILENCE_SEC = 10L;        // 10 s of consecutive all-zero output at a non-zero volume
        private static long _hbFramesSeen = -1L;
        private static long _hbLastAdvanceUs;
        private static string _lastStallDetail = "";
        // Self-test counters (TickTestScript reads the deltas; diagnostic only).
        private static int _prematureResumeCount, _stallFaultCount, _noReadyTrackCount, _previewShareRefusals;
        private static readonly Dictionary<string, int> OpenCounts = new Dictionary<string, int>(StringComparer.Ordinal);   // D15: requests created per key since init (EnsureClipLoading)
        /// <summary>R5: requests the creation site made for a key that already
        /// held an entry or a rooted record — reachable only with
        /// EnsureClipLoading's guard removed, or through the s4neg hook. The
        /// once-only oracle (TsOnceOnly) asserts 0 at the end of S3 and S4.</summary>
        private static int DuplicateRequests;
        private static bool _tsForceDuplicateOnce;   // R5 / s4neg: the test-only hook — the next EnsureClipLoading bypasses the guard once
        private static readonly List<ClipEntry> _tsDisplaced = new List<ClipEntry>();   // s4neg: the entry a forced duplicate displaced, rooted so its request (the playing clip's buffer) is never finalized

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
        // file every 2 s) — EXCEPT a script of nothing but `openall`, which runs
        // on any seat (R1: the D12 gate opens requests and clips and plays
        // nothing; the desktop owner-run gate must be reachable). One script
        // runs per DISTINCT cfg value; the value present at launch runs too (a
        // value written before launch runs at startup). Steps run one at a
        // time; a step ends when its oracle is decided and logs
        // `[MUSIC-SELFTEST] step=<n> <name> pass|fail <detail>`; the run ends
        // with `[MUSIC-SELFTEST] end pass=<n> fail=<m> reason=<first failure's
        // reason|none>`.
        // Named steps: s1 successor handoff, s2 tombstoned successor (loop off),
        // s3 preview over Main (per-key reuse, once-only oracle, R5), s4 four
        // keys with no release (same oracle), s4neg the once-only oracle's
        // negative control (forces a duplicate request; must END fail=1
        // reason=duplicate-request), s5 suppression (Sandbox + broadcast music;
        // its release half waits for the Sandbox to end), s6 stall injection,
        // s6neg its negative control, openall every catalog key resident at
        // once (the D12 cumulative gate; run it from a fresh process — R9: a
        // non-fresh run prints bar=fail reason=not-fresh). Verbs: album:<sku>,
        // play:<sku>/<idx>, preview:<sku>/<idx>, fail:<sku>/<idx>, seek:len-<n>,
        // loop:on|off, shuffle:on|off, select:<sku>:<i,j,..>|all, stall, unstall,
        // stop, play-pause, skip, prev, use-vanilla, stop-preview, wait:<sec>, reset.

        private static string _tsLast;
        private static readonly List<string> _tsSteps = new List<string>();
        private static int _tsIdx = -1, _tsNo, _tsPass, _tsFail, _tsPhase;
        private static float _tsT0, _tsT1, _tsT2, _tsF0, _tsF1;
        private static int _tsI0, _tsI1, _tsI2;
        private static long _tsL0;
        private static string _tsAlbum, _tsName, _tsArg;
        // impl2 r1 L1: the operator's configuration at script start — the exact
        // deselected set plus loop/shuffle — restored exactly at the end.
        private static HashSet<string> _tsSnapDeselected;
        private static bool _tsSnapLoop, _tsSnapShuffle;
        // impl2 r1 M2 / M1: bounds on the two waits the oracles used to skip.
        private const float TS_VANILLA_AUDIBLE_SEC = 5f;   // S2: vanilla Playing after the Loading edge
        private const float TS_LEDGER_SETTLE_SEC = 2f;     // S3: the three keys' state after the preview start; S4 after the 4th key; openall before its line

        internal static void TickTestScript()
        {
            if (!_initialized || _host == null) return;
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
                // R1: the broadcast-identity guard applies to every verb EXCEPT
                // openall, judged once here at the script's start (a script is
                // admitted whole; identity is fixed for the process).
                if (!BroadcastMode.IsBroadcastIdentity && !TsOpenAllOnly())
                {
                    LogOnce("ts-seat:" + raw, "[MUSIC-SELFTEST] ignored on this seat: only a script of nothing but `openall` runs outside the broadcast identity", true);
                    _tsSteps.Clear();
                    return;
                }
                _tsIdx = 0; _tsNo = 0; _tsPass = 0; _tsFail = 0; _tsAlbum = null; _tsFirstFailReason = null;
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
        /// <summary>R1: true when every step of the parsed script is the
        /// `openall` verb (no argument) — the one script any seat runs.</summary>
        private static bool TsOpenAllOnly()
        {
            for (int i = 0; i < _tsSteps.Count; i++)
                if (!string.Equals(_tsSteps[i].Trim(), "openall", StringComparison.OrdinalIgnoreCase)) return false;
            return _tsSteps.Count > 0;
        }
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
            return $"mode={S.mode} current={TsCurrentKey()} started={S.currentStarted} playing={TsMainPlaying()} t={TsMainTime():F1} suppress={S.suppress} waiting={S.waiting} stopIntent={S.stopIntent} fault={(S.faultDurable ? S.faultReason : "none")} entries={EntryCount()} live={LiveObjectCount()} rooted={RootedFailed.Count} tapCallbacks={(tap != null ? tap.Callbacks : -1)} admissible={MusicAdmission.AtAdmissibleMenu}";
        }

        private static string _tsFirstFailReason;   // R5/R9: the end line carries the first failure's reason token
        private static void TsLog(bool pass, string name, string detail)
        {
            if (pass) _tsPass++;
            else
            {
                _tsFail++;
                if (_tsFirstFailReason == null)
                {
                    // A detail that starts with `reason=<token>` names its own
                    // reason (the once-only oracle, openall); any other failure
                    // is named by its step.
                    string d = detail ?? "";
                    if (d.StartsWith("reason=", StringComparison.Ordinal))
                    {
                        int sp = d.IndexOf(' ');
                        _tsFirstFailReason = sp < 0 ? d.Substring(7) : d.Substring(7, sp - 7);
                    }
                    else _tsFirstFailReason = name;
                }
            }
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
                Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] end pass={_tsPass} fail={_tsFail} reason={_tsFirstFailReason ?? "none"}");
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
        /// preview, loop and shuffle off, this album's RETRYABLE tombstones
        /// and every hollow Failed entry cleared (a sticky key stays, D10),
        /// the selection reduced to the given track indices (null = all).
        /// Returns a failure detail, or null.</summary>
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
            // D10: a pre-open failure's hollow marker leaves Clips so the key can
            // be requested again; an entry holding objects is never disposed.
            foreach (var kv in Clips) if (kv.Value.Failed && kv.Value.Req == null && kv.Value.Clip == null && !kv.Value.GetContentInvoked) drop.Add(kv.Key);
            foreach (var k in drop) Clips.Remove(k);
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

        /// <summary>Test verb `fail:<key>`: a RETRYABLE tombstone on the key —
        /// its resident entry, if any, stays where it is (D: nothing
        /// releases; IsTrackReady consults the tombstone), so the next step's
        /// TsSetup clears it without a second request.</summary>
        private static void TsFailKey(string key)
        {
            if (Tombstones.Add(key)) SafeLog(LogLevel.Info, $"[MUSIC] tombstone {key} (self-test fail verb)");
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
            _tsNo++; _tsPhase = 0; _tsT0 = TsRt;
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
                case "s1": case "s2": case "s3": case "s4": case "s4neg": case "s5": case "s6": case "s6neg": case "openall":
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
                case "s4neg": TsRunS4Neg(rt); return;
                case "s5": case "s5-release": TsRunS5(rt); return;
                case "s6": TsRunS6(rt, true); return;
                case "s6neg": TsRunS6(rt, false); return;
                case "openall": TsRunOpenAll(rt); return;
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

        // D15 per-run key oracles: what each of a step's keys looked like at the
        // step's start, so a key resident from an earlier step (nothing
        // releases) is judged as a REUSE and never as a global total.
        private static readonly Dictionary<string, ClipEntry> _tsEntryAtStart = new Dictionary<string, ClipEntry>(StringComparer.Ordinal);
        private static readonly Dictionary<string, int> _tsOpensAtStart = new Dictionary<string, int>(StringComparer.Ordinal);
        private static readonly Dictionary<string, AudioClip> _tsClipSeen = new Dictionary<string, AudioClip>(StringComparer.Ordinal);
        private static void TsSnapshotKeys(string[] keys)
        {
            _tsEntryAtStart.Clear(); _tsOpensAtStart.Clear(); _tsClipSeen.Clear();
            foreach (var k in keys)
            {
                _tsOpensAtStart[k] = TsOpens(k);
                if (Clips.TryGetValue(k, out var e) && (e.Clip != null || e.Req != null)) _tsEntryAtStart[k] = e;
            }
        }
        /// <summary>null when every key is Ready, was requested exactly once
        /// in this step if it had no entry at the start and not at all if it
        /// had one (same ClipEntry object), else the first violation. `grew`
        /// = keys that had no entry at the start; `opens` = the counts.</summary>
        private static string TsKeysReused(string[] keys, out int grew, out string opens)
        {
            grew = 0;
            var sb = new StringBuilder("opens=[");
            string why = null;
            foreach (var k in keys)
            {
                int n = TsOpens(k), n0 = _tsOpensAtStart.TryGetValue(k, out var s0) ? s0 : 0;
                bool wasResident = _tsEntryAtStart.TryGetValue(k, out var e0);
                if (!wasResident) grew++;
                if (sb.Length > 7) sb.Append(',');
                sb.Append(k).Append(':').Append(n);
                if (why != null) continue;
                if (!Clips.TryGetValue(k, out var e) || e.Clip == null) { why = k + " not Ready"; continue; }
                if (wasResident && !ReferenceEquals(e, e0)) { why = k + " lost its ClipEntry identity across the re-selection"; continue; }
                if (n != n0 + (wasResident ? 0 : 1)) why = $"{k} requested {n - n0} time(s) this step (want {(wasResident ? 0 : 1)})";
            }
            opens = sb.Append(']').ToString();
            return why;
        }
        /// <summary>S4: every clip saved during the step is still Unity-non-null,
        /// still its entry's clip, and its entry still holds the request.
        /// Returns the first violation, or null.</summary>
        private static string TsClipsRetained()
        {
            foreach (var kv in _tsClipSeen)
            {
                if (kv.Value == null) return kv.Key + " clip is Unity-null (destroyed)";
                if (!Clips.TryGetValue(kv.Key, out var e)) return kv.Key + " entry left Clips";
                if (!ReferenceEquals(e.Clip, kv.Value)) return kv.Key + " entry's clip changed";
                if (e.Req == null) return kv.Key + " request gone";
            }
            return null;
        }
        private static void TsCollectClips(int upToIdx)
        {
            for (int i = 0; i <= upToIdx; i++)
            {
                string k = TsKey(i);
                if (!_tsClipSeen.ContainsKey(k) && Clips.TryGetValue(k, out var e) && e.Clip != null) _tsClipSeen[k] = e.Clip;
            }
        }

        // S3 (D15): Main + successor + preview, judged per run — each of the
        // three keys is Ready and was requested at most once in this step (a
        // key resident at the step's start is REUSED: request count and
        // ClipEntry identity unchanged; a key without an entry gained exactly
        // one request), and Clips grew by exactly the number of keys that had
        // no entry. impl2 r1 M1's settle stays: the successor is re-requested
        // after the preview opens (DesiredKeys), so the state is awaited,
        // bounded by TS_LEDGER_SETTLE_SEC, and asserted then; preview
        // ownership then stops and Main resumes at its position.
        private static void TsRunS3(float rt)
        {
            string k0 = TsKey(0), k1 = TsKey(1), kp = "p:" + TsKey(2);
            var h = _host;
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1, 2 }, 3);
                        if (err != null) { TsEnd(false, err); return; }
                        TsSnapshotKeys(new[] { k0, k1, kp });
                        _tsI2 = Clips.Count;
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
                        string why = TsKeysReused(new[] { k0, k1, kp }, out int grew, out string opens);
                        if (why == null && Clips.Count - _tsI2 != grew) why = $"Clips grew by {Clips.Count - _tsI2}, want {grew} (the keys that had no entry)";
                        if (why == null) { _tsF1 = rt - _tsT2; _tsT1 = rt; _tsPhase = 5; return; }
                        if (rt - _tsT2 > TS_LEDGER_SETTLE_SEC)
                        {
                            TsEnd(false, $"three keys not reused/ready within {TS_LEDGER_SETTLE_SEC:F0} s of the preview start: {why}; {opens}: " + TsState());
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
                        string why = TsKeysReused(new[] { k0, k1, kp }, out int grew, out string opens);
                        string once = TsOnceOnly();   // R5: the absolute once-only invariant, at the step's end
                        TsEnd(posOk && why == null && once == null, (once != null ? once + " " : "") + $"Main+successor+preview reused/ready {_tsF1:F2}s after the preview start (bound {TS_LEDGER_SETTLE_SEC:F0}); {opens}; Clips grew by {Clips.Count - _tsI2} = the {grew} key(s) that had no entry; identity kept{(why != null ? " FAILED: " + why : "")}; once-only {(once == null ? "holds" : "FAILED")} (duplicate_requests={DuplicateRequests}); Main resumed at {t:F1}s (paused near {_tsF0:F1}s, want within 2 s); shareRefusals delta {_previewShareRefusals - _tsI0}; {TsState()}");
                        return;
                    }
                    if (rt - _tsT1 > 10f) TsEnd(false, "Main did not resume within 10 s of the preview stop: " + TsState());
                    return;
            }
        }

        // S4 (D15): four tracks in sequence with NO release — every clip saved
        // as its key became Ready is still Unity-non-null and still its
        // entry's clip after the 4th key started (an eviction that survived
        // Destroys it: the mutation this catches), every entry still holds
        // its request, a re-selection of a resident key (track 0 again)
        // creates no second request, and the once-only oracle holds (R5:
        // every key in Clips has OpenCounts == 1, DuplicateRequests == 0). A
        // re-selection never reaches EnsureClipLoading (KickDesiredLoads skips
        // a resident key), so the guard-removed mutation is exercised by
        // s4neg at runtime, not by this step's re-selection.
        private static void TsRunS4(float rt)
        {
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(null, 4);
                        if (err != null) { TsEnd(false, err); return; }
                        TsSnapshotKeys(new[] { TsKey(0), TsKey(1), TsKey(2), TsKey(3) });
                        _tsI1 = 0; _tsI2 = 0;
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    {
                        TsCollectClips(_tsI1);
                        string lost = TsClipsRetained();
                        if (lost != null) { TsEnd(false, "release seen: " + lost + ": " + TsState()); return; }
                        if (TsStartedOn(TsKey(_tsI1)))
                        {
                            if (_tsI1 < 3) { _tsI1++; PlayTrack(_tsAlbum, _tsI1); _tsT1 = rt; return; }
                            _tsT1 = rt; _tsPhase = 2; return;
                        }
                        if (rt - _tsT1 > 20f) TsEnd(false, $"track {_tsI1} did not start within 20 s: " + TsState());
                        return;
                    }
                case 2:
                    {
                        TsCollectClips(3);
                        string lost = TsClipsRetained();
                        if (lost != null) { TsEnd(false, "release seen after the 4th key: " + lost + ": " + TsState()); return; }
                        if (rt - _tsT1 < TS_LEDGER_SETTLE_SEC) return;
                        _tsI2 = TsOpens(TsKey(0));
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 3; return;
                    }
                case 3:
                    if (TsStartedOn(TsKey(0)))
                    {
                        string lost = TsClipsRetained();
                        int n = TsOpens(TsKey(0));
                        string once = TsOnceOnly();   // R5: absolute — every key in Clips requested exactly once this process, no duplicate at the creation site
                        bool ok = lost == null && n == _tsI2 && once == null;
                        TsEnd(ok, (once != null ? once + " " : "") + $"4 tracks in sequence, no release: {_tsClipSeen.Count} clips saved, all Unity-non-null and retained with their requests{(lost != null ? " FAILED: " + lost : "")}; re-selected {TsKey(0)} opens={n} (was {_tsI2}: reuse, no second request); once-only {(once == null ? "holds" : "FAILED")} (duplicate_requests={DuplicateRequests}); {TsState()}");
                        return;
                    }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not restart within 20 s of its re-selection: " + TsState());
                    return;
            }
        }

        /// <summary>R5: the ABSOLUTE once-only invariant, per process — every
        /// key in Clips was requested exactly once (OpenCounts == 1; a key
        /// resident from an earlier run reads 1 too) and the creation site
        /// never made a request for a key that already held an entry or a
        /// rooted record (DuplicateRequests == 0). null when it holds, else
        /// the violation, `reason=duplicate-request` first so the end line
        /// carries it. Asserted at the end of S3 and S4; s4neg is its
        /// negative control (#391). (A pre-open failure retried by an
        /// explicit click legitimately requests its key again; the named
        /// steps make none.)</summary>
        private static string TsOnceOnly()
        {
            if (DuplicateRequests > 0) return $"reason=duplicate-request duplicate_requests={DuplicateRequests} (want 0)";
            foreach (var kv in Clips)
            {
                int n = TsOpens(kv.Key);
                if (n != 1) return $"reason=duplicate-request {kv.Key} requested {n} time(s) this process (want 1)";
            }
            return null;
        }

        // s4neg (R5, #391): the once-only oracle's negative control. Track 0
        // is played (resident, Ready); then the test-only hook forces a SECOND
        // request for that resident key through the creation site — what
        // removing EnsureClipLoading's guard would do — and the same oracle is
        // asserted at once: the step must FAIL with reason=duplicate-request
        // and the run END `fail=1 reason=duplicate-request`. A step that
        // passes here means the oracle is decoration. The process carries the
        // duplicate afterwards (OpenCounts 2, DuplicateRequests 1, the
        // displaced entry's objects retained off the ledger): run s4neg last,
        // or in its own process.
        private static void TsRunS4Neg(float rt)
        {
            string k0 = TsKey(0);
            switch (_tsPhase)
            {
                case 0:
                    {
                        string err = TsSetup(new[] { 0, 1, 2 }, 2);
                        if (err != null) { TsEnd(false, err); return; }
                        PlayTrack(_tsAlbum, 0); _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (TsStartedOn(k0))
                    {
                        string before = TsOnceOnly();
                        if (before != null) { TsEnd(false, "once-only oracle already violated before the hook (not a control result): " + before + "; " + TsState()); return; }
                        var a = TsAlbumDef();
                        string path = null;
                        try { path = a != null ? MusicAssets.PathFor(a.Tracks[0].OggFile) : null; } catch { }
                        if (path == null) { TsEnd(false, "no file path for track 0"); return; }
                        int opens0 = TsOpens(k0), dup0 = DuplicateRequests;
                        // The duplicate replaces the resident entry in Clips; the
                        // displaced one stays rooted here (its request backs the
                        // clip Main is still playing — an unreferenced request
                        // could be finalized under that reader, D1).
                        if (Clips.TryGetValue(k0, out var displaced)) _tsDisplaced.Add(displaced);
                        _tsForceDuplicateOnce = true;
                        try { EnsureClipLoading(k0, path, selfTest: true); }
                        finally { _tsForceDuplicateOnce = false; }
                        string why = TsOnceOnly();
                        TsEnd(why == null, (why ?? "the once-only oracle still holds after a forced duplicate request — the oracle is NOT load-bearing;") + $" opens[{k0}]={TsOpens(k0)} (was {opens0}) duplicate_requests={DuplicateRequests} (was {dup0}); {TsState()}");
                        return;
                    }
                    if (rt - _tsT1 > 20f) TsEnd(false, "track 0 did not start within 20 s: " + TsState());
                    return;
            }
        }

        // openall (D12): from a fresh process, request every catalog key (full
        // + preview) one per frame — PollClipLoads opens one per frame — wait
        // until each is Ready or failed, settle TS_LEDGER_SETTLE_SEC, print the
        // gate line, which evaluates its own bar (R9): fresh AND entries +
        // rooted_failed == keys AND native_delta_mb <= 120, where fresh = no
        // entry, no rooted record, no probe open (and no engine baseline)
        // existed when the verb began; a non-fresh run prints bar=fail
        // reason=not-fresh. A gate failure on either seat -> B2, never a patch.
        private static List<KeyValuePair<string, string>> _tsOpenAll;   // key, path
        private static bool _tsOpenAllFresh;
        private static void TsRunOpenAll(float rt)
        {
            switch (_tsPhase)
            {
                case 0:
                    {
                        _tsOpenAll = new List<KeyValuePair<string, string>>();
                        long bytes = 0L;
                        var albums = MusicCatalog.Albums;
                        for (int a = 0; a < albums.Length; a++)
                        {
                            var album = albums[a];
                            if (album == null || album.Tracks == null) continue;
                            for (int i = 0; i < album.Tracks.Length; i++)
                            {
                                var t = album.Tracks[i];
                                string key = album.Sku + "/" + i;
                                string full = null, prev = null;
                                try { full = MusicAssets.PathFor(t.OggFile); prev = MusicAssets.PathFor(t.PreviewFile); } catch { }
                                if (full == null || prev == null) { TsEnd(false, $"file not ready for {key} (full={(full != null)} preview={(prev != null)}) — both tiers must be installed"); return; }
                                _tsOpenAll.Add(new KeyValuePair<string, string>(key, full));
                                _tsOpenAll.Add(new KeyValuePair<string, string>("p:" + key, prev));
                                bytes += t.OggSize + t.PreviewSize;
                            }
                        }
                        if (_tsOpenAll.Count == 0) { TsEnd(false, "empty catalog"); return; }
                        _tsL0 = bytes;
                        _tsI0 = 0;
                        int residentAtStart = 0;
                        foreach (var kv in _tsOpenAll) if (Clips.TryGetValue(kv.Key, out var e) && (e.Clip != null || e.Req != null)) residentAtStart++;
                        // R9: judged NOW, before this verb requests anything. The
                        // baseline term catches a hollow marker an explicit click
                        // cleared (Clips empty again, an earlier request made).
                        _tsOpenAllFresh = Clips.Count == 0 && RootedFailed.Count == 0 && _probeOpens == 0 && _nativeBaseline < 0L;
                        Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] openall begin keys={_tsOpenAll.Count} fresh={(_tsOpenAllFresh ? 1 : 0)} resident_at_start={residentAtStart} sticky={StickyTombstones.Count} {ResidencyFields()}");
                        _tsT1 = rt; _tsPhase = 1; return;
                    }
                case 1:
                    if (_tsI0 < _tsOpenAll.Count)
                    {
                        var kv = _tsOpenAll[_tsI0++];
                        if (!StickyTombstones.Contains(kv.Key)) EnsureClipLoading(kv.Key, kv.Value, selfTest: true);
                        return;
                    }
                    _tsPhase = 2; _tsT1 = rt; return;
                case 2:
                    {
                        int ready = 0, failedKeys = 0, pending = 0;
                        foreach (var kv in _tsOpenAll)
                        {
                            if (Clips.TryGetValue(kv.Key, out var e) && e.Clip != null) ready++;
                            else if (IsFailedKey(kv.Key)) failedKeys++;
                            else pending++;
                        }
                        if (pending == 0) { _tsT2 = rt; _tsPhase = 3; return; }
                        if (rt - _tsT1 > 120f) TsEnd(false, $"{pending} of {_tsOpenAll.Count} keys neither Ready nor failed after 120 s (ready={ready} failed={failedKeys}): " + TsState());
                        return;
                    }
                case 3:
                    {
                        if (rt - _tsT2 < TS_LEDGER_SETTLE_SEC) return;
                        int keys = _tsOpenAll.Count, entries = EntryCount(), rooted = RootedFailed.Count;
                        double delta = NativeDeltaMb();
                        string deltaText = NativeDeltaMbText();
                        string compressed = (_tsL0 / 1048576.0).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);
                        bool fresh = _tsOpenAllFresh;
                        bool countOk = entries + rooted == keys;
                        bool memOk = !double.IsNaN(delta) && delta <= 120.0;
                        bool bar = fresh && countOk && memOk;
                        string reason = !fresh ? "not-fresh" : !countOk ? "entries" : double.IsNaN(delta) ? "native-unmeasured" : !memOk ? "native-delta" : "none";
                        // R9: the gate line evaluates its own bar; the runner's
                        // end line carries the same fail count.
                        Plugin.Log?.LogInfo($"[MUSIC-SELFTEST] openall keys={keys} entries={entries} rooted_failed={rooted} compressed_mb={compressed} native_delta_mb={deltaText} fresh={(fresh ? 1 : 0)} bar={(bar ? "pass" : "fail")} fail={(bar ? 0 : 1)} reason={reason}");
                        TsEnd(bar, $"reason={reason} entries + rooted_failed = {entries + rooted} (want {keys}) native_delta_mb={deltaText} (bound 120) fresh={(fresh ? 1 : 0)} probe_opens={_probeOpens}; {TsState()}");
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
            // D13: OnHostDestroyed is non-throwing by construction (its hand-off
            // to PollHost runs in a finally); the guard here is so no future
            // edit to it can let Unity abort this load-bearing hook (#92).
            try { MusicEngine.OnHostDestroyed(this); } catch { }
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
