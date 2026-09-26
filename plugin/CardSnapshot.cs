using System;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// NATIVE CARD RENDERING — live-rendered snapshots of the game's real
    /// card objects, replacing the bundled PNG pack as the primary art
    /// source (PNGs remain the fallback this release; CardImageLoader is
    /// untouched below the seam).
    ///
    /// Pipeline (per card, one in flight at a time, coroutine hosted on
    /// Plugin.Instance — the FfaMode/ExportTierList pattern):
    ///   1. Resolve the CardInfo prefab by canonical name from
    ///      CardChoice.instance.cards (Resources fallback for unregistered
    ///      cards, mirroring NativeUI.ShowCardPreview's two-path resolve).
    ///   2. Clone via CardChoice.AddCardVisual (plain Object.Instantiate,
    ///      NO Photon registration — the production-proven FfaMode recipe,
    ///      FfaMode.cs ~1880), parked FAR from every camera frustum.
    ///      NEVER parented under any shared canvas root — the documented
    ///      v1.25.24 failure (CHANGELOG 1.25.24: overlay-canvas parenting =
    ///      grey flash) was the parenting + same-frame capture, not the
    ///      concept. We also never call CardVisuals.Leave()/Pick() on the
    ///      clone: both Destroy(transform.root) (Pick via PhotonNetwork).
    ///   3. Wait ~0.9s realtime for visual settlement — the card body is
    ///      particle-built (GeneralParticleSystem spawns uGUI Image
    ///      particles over frames, initSpawn=100; CurveAnimation PlayIn is
    ///      ~0.35s). Same-frame capture is exactly the v1.25.24 empty-card
    ///      failure (learning #96 class).
    ///   4. Re-apply the isolation layer AFTER settlement: ObjectPool
    ///      instantiates its pooled particle GameObjects lazily on first
    ///      Play(), so children born during the settle window keep the
    ///      PREFAB's layer unless re-stamped.
    ///   5. Temp orthographic camera (tier-export harness values: near 0.1,
    ///      SolidColor clear — but TRANSPARENT and cullingMask = only our
    ///      layer, where the tier cam used opaque + ~0), 380x600
    ///      RenderTexture (PNG display aspect), ReadPixels → Texture2D.
    ///   6. Learning #139 lit-pixel probe: if the capture is effectively
    ///      empty (the SFSS-lit-material risk — a lit material renders
    ///      NOTHING on an isolated RT camera), the card is marked failed
    ///      and NOT cached, so the PNG fallback serves. The card's uGUI
    ///      images/TMP are unlit (tier export proves they render on this
    ///      pipeline); the one unverified renderer is the REAL
    ///      ParticleSystem on cardBase (cardColor glow) — if only that one
    ///      is dark the probe still passes on the uGUI pixels and we ship
    ///      without the glow (accepted; shader name is logged for diag).
    ///   7. Teardown clone/camera/RT in finally — guaranteed even when the
    ///      pump catches a mid-capture exception (iterator finally runs
    ///      during unwind).
    ///
    /// Localization synergy: CardInfoDisplayer.DrawCard renders name,
    /// description and stat lines through the game's own Unity Localization
    /// (UILocalizedString), so a snapshot is automatically in the active
    /// locale. CardTextLocalizer.InvalidateCache (mod-language switch)
    /// calls InvalidateAll() so the next request re-renders localized.
    ///
    /// Failure policy (learning #66: every early-return logs its reason):
    /// any failure degrades to exact current behavior — the seam in
    /// CardImageLoader.GetSprite returns the PNG as today. Three failure
    /// classes:
    ///   - soft (environment not ready: no CardChoice.instance /
    ///     Optionshandler.instance / Plugin.Instance, clone destroyed by a
    ///     scene change mid-settle): retried up to 3x with a 5s backoff,
    ///     never counted against pipeline health;
    ///   - per-card (no matching CardInfo, degenerate bounds): card marked
    ///     failed for the session, health untouched;
    ///   - capture (exception, #139 probe): card marked failed AND counted;
    ///     3 consecutive => SnapshotsHealthy=false, pipeline off for the
    ///     session (PNGs serve everything).
    /// </summary>
    public static class CardSnapshot
    {
        // ── Master switch ──
        // ONE flag reverts the whole feature to pure-PNG behavior: the
        // CardImageLoader.GetSprite seam checks it before touching any
        // snapshot state. Default ON.
        public static bool UseNativeSnapshots = true;

        /// <summary>False after 3 consecutive capture failures — the
        /// pipeline stops attempting for the session and every surface
        /// serves the PNG fallback. Reset by InvalidateAll (bounded
        /// re-probe on locale switch).</summary>
        public static bool SnapshotsHealthy { get; private set; } = true;

        /// <summary>Bumped by InvalidateAll (locale switch), which DESTROYS
        /// every cached sprite/texture. Consumers that cache raw Texture2D
        /// references taken from snapshot sprites (TabStatsOverlay's hover
        /// cache) compare this and drop their entries when it changes, so
        /// they never paint a destroyed texture.</summary>
        public static int Generation => _generation;

        // Output size — matches the 380x600 PNG display slot in
        // NativeUI.ShowCardPreview (native PNG art is ~2:3; consumers all
        // draw with preserveAspect, so exact aspect is non-critical).
        private const int RT_W = 380;
        private const int RT_H = 600;

        // Opaque backing composited under every capture AFTER the #139 probe
        // (CompositeOntoOpaqueBacking). Deliberately the same colour as
        // NativeUI's card-preview panel so the popup shows no seam around the
        // image, and it reads as a dark plate at the IMGUI draw sites.
        private static readonly Color BACKING_COLOR = new Color(0.10f, 0.12f, 0.16f, 1f);

        // Park position for the clone + camera. DELIBERATELY distinct from
        // the tier export's (50000,50000): the tier camera renders with
        // cullingMask ~0, so a concurrent snapshot clone at the same spot
        // would photobomb a tier-list export. 2345 units of X clearance is
        // outside the tier canvas' widest half-extent (1500).
        private static readonly Vector3 ParkPos = new Vector3(52345f, 50000f, 0f);

        // #139 probe: fraction of sampled pixels that must be composited-
        // VISIBLE — alpha AND at least one color channel above the floor.
        // (The old alpha-OR-color test passed fully-transparent colored
        // pixels and opaque BLACK renders — an invisible/black capture is
        // exactly the #139 failure this probe exists to reject.) 8%, not
        // 2%: a real card body fills most of the 380x600 frame (measured
        // real captures land far above 30% lit), while title/description
        // TEXT ALONE measures ~2% — so a 2% floor accepted text-only
        // renders where the particle-built card body never drew. 8%
        // cleanly separates the two populations.
        private const float PROBE_MIN_LIT_FRACTION = 0.08f;
        private const byte PROBE_CHANNEL_FLOOR = 12; // of 255

        private const int MAX_CACHED = 96;          // 67 vanilla cards + alias-key slack
        private const int MAX_SOFT_RETRIES = 3;
        private const float SOFT_RETRY_BACKOFF_S = 5f;
        private const int MAX_CONSECUTIVE_FAILURES = 3;
        // Aug 6 item 3: 0.9s -> 0.55s so the native render shows up faster.
        // 0.55 still clears PlayIn (0.35s) + a few particle-build frames; the
        // #139 probe stays the correctness gate. If the FAST settle probes
        // blank (slow rig, heavy scene), the item soft-retries ONCE with
        // SETTLE_RETRY_BONUS_S added (1.2s total — above the old 0.9) before
        // a probe failure is allowed to count toward SnapshotsHealthy, so
        // the speedup can never cascade into disabling the pipeline.
        private const float SETTLE_SECONDS = 0.55f; // > PlayIn 0.35s
        private const float SETTLE_RETRY_BONUS_S = 0.65f;
        private const int SETTLE_MIN_FRAMES = 10;
        private const float TEXT_WAIT_EXTRA_S = 1.0f; // localized-string resolution slack
        private const float PUMP_STALE_SECONDS = 10f; // no pump tick this long = dead host (F4)

        private sealed class PendingItem
        {
            public string key;
            public string name;
            public int softRetries;
            // Extra settle time granted after a fast-settle probe failure
            // (see SETTLE_SECONDS comment). 0 = first, fast attempt.
            public float settleBonus;
        }

        // FailedCapture: CaptureOne already logged the specific reason —
        // the pump only records (fail set + health counter, no second log).
        // FailedHandled: the pump's exception catch already did BOTH.
        private enum Outcome { None, Success, SoftRetry, FailedCard, FailedCapture, FailedHandled }

        private static readonly Dictionary<string, Sprite> _cache =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        // The Top Card THUMBNAIL for the same key: a second Sprite over the
        // SAME Texture2D, cropped to the card's corner band. Written only
        // beside _cache[key] in CaptureOne and removed only by EvictKey, so
        // the two maps hold the same keys. Never handed to the full-size
        // consumers (CardImageLoader.GetSprite, TabStatsOverlay) — they read
        // _cache through TryGetSprite and are unaffected by the crop.
        private static readonly Dictionary<string, Sprite> _thumbs =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        // Insertion order of _cache keys — the F1 insert-time cap evicts
        // (and DESTROYS) the oldest entry first. Kept in lockstep with
        // _cache at every add/remove site.
        private static readonly List<string> _cacheOrder = new List<string>();
        private static readonly HashSet<string> _failed =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        // List, not Queue: Aug 6 item 3 added front-of-line priority for the
        // card the player is LOOKING AT (Card Stats popup / Tab hover) so it
        // never waits behind a long prewarm backlog. Small (<= MAX_CACHED),
        // so RemoveAt(0)/Insert(0) costs nothing.
        private static readonly List<PendingItem> _queue = new List<PendingItem>();
        private static readonly HashSet<string> _queuedKeys =
            new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        private static bool _pumpRunning;
        // F4 dead-pump detection: the host the pump was started on (Unity
        // fake-null once destroyed — the persistent-GO respawn kills the
        // coroutine WITHOUT running its finally), a liveness stamp the pump
        // refreshes at its yield sites, and a monotonically increasing pump
        // id so a stale iterator's late finally can never clear the CURRENT
        // pump's flag.
        private static UnityEngine.Object _pumpHost;
        private static float _pumpLastTick;
        private static int _pumpId;
        private static int _consecutiveFailures;
        // After a request exhausts its soft retries (environment not ready),
        // silently refuse NEW enqueues for a while — without this a per-frame
        // hover path (Tab board) would cycle enqueue -> 3 retries -> drop ->
        // re-enqueue forever, spamming the log.
        private static float _softBlockUntil;
        /// <summary>True while new capture requests are being refused (the
        /// env-not-ready cooldown, or the cache cap). Codex round 2 (finding
        /// 10): the seam treats "healthy + not failed + cache miss" as "a
        /// capture is coming", but RequestSnapshot can DECLINE without
        /// queuing anything — during the 30s soft block, or once the cache cap
        /// is reached — and then nothing is coming, so returning null renders
        /// a blank card while a perfectly good PNG sits on disk.</summary>
        internal static bool RequestsBlocked
        {
            get
            {
                try
                {
                    return Time.realtimeSinceStartup < _softBlockUntil
                           || _cache.Count >= MAX_CACHED;
                }
                catch { return false; }
            }
        }
        private static Outcome _lastOutcome = Outcome.None;
        private static string _lastSoftReason;
        // Generation guard: a locale switch (InvalidateAll) mid-capture must
        // not let the in-flight capture — rendered with the OLD locale's
        // text — land in the fresh cache.
        private static int _generation;

        // One-shot log guards (RequestSnapshot/TryGetSprite sit on per-frame
        // paths — TabStatsOverlay hover — so state-transition logging only).
        private static bool _loggedNoHost;
        private static bool _loggedCapReached;
        private static bool _loggedSeamError;
        private static int _chosenLayer = -1;

        // TMP reflection (read-only text probe; no TMPro csproj reference —
        // same find-by-name idiom as NativeUI's description scan).
        private static Type _tmpType;
        private static PropertyInfo _tmpTextProp;
        private static bool _tmpProbed;

        // ── Public API ──

        /// <summary>Cache hit only — never starts work. Key derivation is
        /// identical to CardImageLoader.GetSprite's canonical key so every
        /// name form (GameObject name, display name, canonical) collapses
        /// to the same entry.</summary>
        public static bool TryGetSprite(string cardName, out Sprite sprite)
        {
            sprite = null;
            if (!UseNativeSnapshots || string.IsNullOrEmpty(cardName)) return false;
            try
            {
                string key = KeyFor(cardName);
                if (string.IsNullOrEmpty(key)) return false;
                if (_cache.TryGetValue(key, out var s))
                {
                    if (s != null) { sprite = s; return true; }
                    // Sprite destroyed underneath us (should not happen —
                    // HideAndDontSave — but a fake-null cached entry must
                    // read as a miss, not serve a dead sprite). The
                    // thumbnail over the same texture goes with it.
                    EvictKey(key);
                }
            }
            catch { /* miss — PNG fallback serves */ }
            return false;
        }

        /// <summary>Cache hit only, like TryGetSprite, but returns the Top
        /// Card THUMBNAIL: the same capture cropped to the card's corner
        /// band, so the vanilla name plate above that band is not in the
        /// picture and the card's own corners reach the edges of whatever
        /// box the caller draws it in. Every key in _cache has an entry
        /// here (CaptureOne writes both, EvictKey removes both), and when
        /// the crop could not be built that entry IS the full sprite — so a
        /// caller always gets a picture, and the degraded case is a logged
        /// warning rather than an empty slot.</summary>
        public static bool TryGetThumbSprite(string cardName, out Sprite sprite)
        {
            sprite = null;
            if (!UseNativeSnapshots || string.IsNullOrEmpty(cardName)) return false;
            try
            {
                string key = KeyFor(cardName);
                if (string.IsNullOrEmpty(key)) return false;
                if (_thumbs.TryGetValue(key, out var s))
                {
                    if (s != null) { sprite = s; return true; }
                    EvictKey(key);
                }
            }
            catch { /* miss — the caller re-requests, PNG fallback serves */ }
            return false;
        }

        /// <summary>True when the card is marked failed for the session —
        /// lets per-frame consumers (TabStatsOverlay's cached-PNG path)
        /// skip re-requesting a card that can never succeed. Same key
        /// derivation as TryGetSprite/RequestSnapshot. O(1), log-silent.</summary>
        public static bool IsFailed(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return false;
            try
            {
                string key = KeyFor(cardName);
                return !string.IsNullOrEmpty(key) && _failed.Contains(key);
            }
            catch { return false; }
        }

        /// <summary>Starts an async capture for the card if it is not
        /// already cached, failed, or queued. O(1) and log-silent on the
        /// common repeat-call path (called every frame from hover paths).</summary>
        public static void RequestSnapshot(string cardName, bool prioritize = false)
        {
            try
            {
                if (!UseNativeSnapshots || !SnapshotsHealthy) return;
                if (string.IsNullOrEmpty(cardName)) return;
                if (Time.realtimeSinceStartup < _softBlockUntil) return; // env-not-ready cooldown (logged at block time)
                string key = KeyFor(cardName);
                if (string.IsNullOrEmpty(key)) return;
                if (_cache.ContainsKey(key) || _failed.Contains(key) || _queuedKeys.Contains(key))
                {
                    // Aug 6 item 3: a prioritized request for an
                    // already-queued key jumps that item to the front —
                    // the player is looking at it right now.
                    if (prioritize && _queuedKeys.Contains(key) && !_cache.ContainsKey(key))
                    {
                        int idx = _queue.FindIndex(p => string.Equals(p.key, key, StringComparison.OrdinalIgnoreCase));
                        if (idx > 0)
                        {
                            var moved = _queue[idx];
                            _queue.RemoveAt(idx);
                            _queue.Insert(0, moved);
                        }
                    }
                    // F4(a): a queued key must STILL kick the pump — the
                    // coroutine host can die (persistent-GO respawn) and
                    // strand the whole queue; without this, the per-key
                    // early-return above made the strand permanent.
                    // EnsurePump is O(1) when the pump is alive.
                    if (_queue.Count > 0) EnsurePump();
                    return;
                }
                if (_cache.Count >= MAX_CACHED)
                {
                    if (!_loggedCapReached)
                    {
                        _loggedCapReached = true;
                        Plugin.Log?.LogWarning($"[CARDSNAP] cache cap {MAX_CACHED} reached — further cards serve PNG fallback this session");
                    }
                    return;
                }
                _queuedKeys.Add(key);
                var pending = new PendingItem { key = key, name = cardName, softRetries = 0 };
                if (prioritize) _queue.Insert(0, pending);
                else _queue.Add(pending);
                EnsurePump();
            }
            catch (Exception ex)
            {
                if (!_loggedSeamError)
                {
                    _loggedSeamError = true;
                    Plugin.Log?.LogWarning("[CARDSNAP] RequestSnapshot failed: " + ex.Message);
                }
            }
        }

        /// <summary>Locale change — drop every snapshot so the next request
        /// re-renders with the game's own localized card text (that is the
        /// point of native rendering). Sprites AND their backing textures
        /// are DESTROYED here (F1 — ~0.9MB/card would otherwise leak on
        /// every locale switch). Load-bearing coupling, do not break it:
        /// the ONLY caller is the mod-language switch
        /// (CardTextLocalizer.InvalidateCache, from I18n.SetLocale), which
        /// immediately rebuilds the whole F5 page — so no live UI keeps
        /// painting a destroyed sprite for more than a frame — and
        /// TabStatsOverlay watches Generation to drop its raw-texture hover
        /// cache the same way. If InvalidateAll ever gains a caller that
        /// does NOT rebuild the F5 page, revisit these destroys.</summary>
        public static void InvalidateAll()
        {
            try
            {
                int n = _cache.Count;
                _generation++;
                // Accepted residual (R2-Low3): a tier-list export coroutine
                // mid-flight across a language switch may render blank cells
                // — the sprites it already grabbed references to are
                // destroyed underneath it here. Cosmetic, self-serve fix
                // (user re-runs the export); no machinery to guard it.
                foreach (var key in new List<string>(_cache.Keys)) EvictKey(key);
                _cache.Clear();
                _thumbs.Clear();
                _cacheOrder.Clear();
                _failed.Clear();
                _queue.Clear();
                _queuedKeys.Clear();
                _consecutiveFailures = 0;
                SnapshotsHealthy = true;
                _loggedCapReached = false;
                Plugin.Log?.LogInfo($"[CARDSNAP] invalidated {n} cached snapshot(s) — next requests re-render in the active locale");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] InvalidateAll failed: " + ex.Message);
            }
        }

        /// <summary>Destroys a cached snapshot sprite AND its backing
        /// Texture2D — Object.Destroy(sprite) alone does NOT free the
        /// texture, which is the F1 leak. Safe on null/fake-null.</summary>
        private static void DestroySprite(Sprite s)
        {
            try
            {
                if (s == null) return; // includes Unity fake-null
                var t = s.texture;
                UnityEngine.Object.Destroy(s);
                if (t != null) UnityEngine.Object.Destroy(t);
            }
            catch { /* teardown must never throw */ }
        }

        /// <summary>Drops one key from BOTH sprite maps and from the eviction
        /// order, destroying what it finds. The full sprite goes through
        /// DestroySprite, which frees the Texture2D; the thumbnail is a
        /// second Sprite over that same texture, so it is destroyed on its
        /// own — freeing the texture twice is what this split avoids. The
        /// thumbnail entry can BE the full sprite (the crop failed at
        /// capture); destroying an already-destroyed Unity object is a
        /// no-op, so that case needs no special handling here.
        ///
        /// Every removal from _cache goes through this method, which is what
        /// keeps the two maps holding the same keys.</summary>
        private static void EvictKey(string key)
        {
            _cache.TryGetValue(key, out var full);
            _thumbs.TryGetValue(key, out var thumb);
            _cache.Remove(key);
            _thumbs.Remove(key);
            _cacheOrder.Remove(key);
            // The full sprite FIRST: it is the one that frees the shared
            // Texture2D. Destroying the thumbnail first would leave the
            // full sprite fake-null when thumb and full are the same object
            // (the failed-crop case), and DestroySprite would then return
            // before freeing the texture.
            DestroySprite(full);
            try { if (thumb != null) UnityEngine.Object.Destroy(thumb); } catch { }
        }

        // ── Internals ──

        /// <summary>Same derivation as CardImageLoader.GetSprite's primary
        /// key: canonical form (CardRarityLookup, #19 — log names and
        /// display names both resolve) then the loader's NormalizeKey.
        /// NOTE: before CardRarityLookup.ScanAll has populated its map an
        /// alias name ("Leach") keys under its raw form; after the scan the
        /// same card keys canonical ("leech"). Worst case that re-captures
        /// an alias card once — bounded, harmless.</summary>
        private static string KeyFor(string cardName)
        {
            string canonical = null;
            try { canonical = CardRarityLookup.GetCanonicalName(cardName); } catch { }
            return CardImageLoader.NormalizeKey(canonical ?? cardName);
        }

        private static void EnsurePump()
        {
            if (_pumpRunning)
            {
                // F4(b): "_pumpRunning" can lie — when the host GameObject
                // dies (persistent-GO respawn, #16) Unity kills the
                // coroutine and the flag may never clear, stranding the
                // queue forever. Host gone or no tick for
                // PUMP_STALE_SECONDS = presumed dead: reset and start a
                // fresh pump on the CURRENT Plugin.Instance (the pump-id
                // guard retires the old iterator if it is somehow alive).
                bool hostGone = _pumpHost == null; // Unity fake-null
                bool stale = Time.realtimeSinceStartup - _pumpLastTick > PUMP_STALE_SECONDS;
                if (!hostGone && !stale) return;
                Plugin.Log?.LogWarning($"[CARDSNAP] pump presumed dead (hostGone={hostGone}, idle {Time.realtimeSinceStartup - _pumpLastTick:F0}s) — restarting on the current host");
                _pumpRunning = false;
            }
            if (Plugin.Instance == null)
            {
                // Coroutine host not up yet (very early startup) — the queue
                // keeps the items; the next RequestSnapshot retries.
                if (!_loggedNoHost)
                {
                    _loggedNoHost = true;
                    Plugin.Log?.LogWarning("[CARDSNAP] Plugin.Instance null — deferring snapshot pump until the persistent host exists");
                }
                return;
            }
            try
            {
                _pumpRunning = true;
                _pumpId++;
                _pumpHost = Plugin.Instance;
                _pumpLastTick = Time.realtimeSinceStartup;
                Plugin.Instance.StartCoroutine(Pump(_pumpId));
            }
            catch (Exception ex)
            {
                _pumpRunning = false;
                Plugin.Log?.LogWarning("[CARDSNAP] pump start failed: " + ex.Message);
            }
        }

        /// <summary>One capture in flight at a time. The inner iterator is
        /// driven manually so an exception thrown between yields is caught
        /// HERE (yield return is illegal inside try/catch) — CaptureOne's
        /// own try/finally still runs its teardown during the unwind.</summary>
        private static IEnumerator Pump(int pumpId)
        {
            try
            {
                while (_queue.Count > 0)
                {
                    if (pumpId != _pumpId)
                    {
                        // A replacement pump was started after this one was
                        // presumed dead — retire quietly; the new pump owns
                        // the queue (finally below is id-guarded too).
                        Plugin.Log?.LogInfo($"[CARDSNAP] stale pump #{pumpId} retiring (current #{_pumpId})");
                        yield break;
                    }
                    _pumpLastTick = Time.realtimeSinceStartup;
                    if (!UseNativeSnapshots || !SnapshotsHealthy)
                    {
                        Plugin.Log?.LogInfo($"[CARDSNAP] pump stopping (enabled={UseNativeSnapshots} healthy={SnapshotsHealthy}) — {_queue.Count} queued request(s) dropped");
                        _queue.Clear();
                        _queuedKeys.Clear();
                        yield break;
                    }
                    var item = _queue[0];
                    _queue.RemoveAt(0);
                    _queuedKeys.Remove(item.key);
                    if (_cache.ContainsKey(item.key) || _failed.Contains(item.key)) continue;

                    _lastOutcome = Outcome.None;
                    _lastSoftReason = null;
                    var inner = CaptureOne(pumpId, item);
                    while (true)
                    {
                        object cur = null;
                        bool moved;
                        try
                        {
                            moved = inner.MoveNext();
                            if (moved) cur = inner.Current;
                        }
                        catch (Exception ex)
                        {
                            OnCaptureFailure(item.key, item.name, "exception: " + ex.Message);
                            _lastOutcome = Outcome.FailedHandled;
                            moved = false;
                        }
                        if (!moved) break;
                        yield return cur;
                        if (pumpId != _pumpId)
                        {
                            // R2-1: _pumpId can only change while this
                            // iterator is SUSPENDED (EnsurePump runs on the
                            // main thread between our yields), so checking at
                            // every resume is complete: a pump presumed dead
                            // during a capture's settle wait can never run
                            // another MoveNext alongside its replacement.
                            // Dispose the inner iterator — CaptureOne's
                            // finally tears down clone/camera/RT during the
                            // Dispose unwind — and retire WITHOUT touching
                            // the queue or _pumpRunning (the new pump owns
                            // both; the finally below is id-guarded too).
                            try { (inner as IDisposable)?.Dispose(); } catch { }
                            Plugin.Log?.LogWarning($"[CARDSNAP] stale pump #{pumpId} aborting capture (current #{_pumpId})");
                            yield break;
                        }
                        _pumpLastTick = Time.realtimeSinceStartup;
                    }

                    switch (_lastOutcome)
                    {
                        case Outcome.Success:
                            _consecutiveFailures = 0;
                            break;
                        case Outcome.FailedCard:
                            // Data problem (unknown card), not a pipeline
                            // problem — permanent for the session, no
                            // health hit. Already logged in CaptureOne.
                            _failed.Add(item.key);
                            break;
                        case Outcome.FailedCapture:
                            // CaptureOne logged its specific reason — record
                            // the failure + health tick without a second log.
                            RecordCaptureFailure(item.key);
                            break;
                        case Outcome.FailedHandled:
                            break; // exception path — fully handled in the catch
                        case Outcome.SoftRetry:
                            if (item.softRetries < MAX_SOFT_RETRIES)
                            {
                                item.softRetries++;
                                _queuedKeys.Add(item.key);
                                _queue.Add(item);
                                Plugin.Log?.LogInfo($"[CARDSNAP] '{item.name}' soft-deferred ({_lastSoftReason}) — retry {item.softRetries}/{MAX_SOFT_RETRIES} in {SOFT_RETRY_BACKOFF_S:F0}s");
                                float until = Time.realtimeSinceStartup + SOFT_RETRY_BACKOFF_S;
                                while (Time.realtimeSinceStartup < until)
                                {
                                    yield return null;
                                    _pumpLastTick = Time.realtimeSinceStartup;
                                }
                            }
                            else
                            {
                                _softBlockUntil = Time.realtimeSinceStartup + 30f;
                                Plugin.Log?.LogInfo($"[CARDSNAP] '{item.name}' dropped after {MAX_SOFT_RETRIES} soft retries ({_lastSoftReason}) — new requests blocked 30s, PNG serves meanwhile");
                            }
                            break;
                        default:
                            // Iterator ended without recording an outcome —
                            // treat as a capture failure so it cannot loop.
                            OnCaptureFailure(item.key, item.name, "capture ended without outcome");
                            break;
                    }

                    yield return null; // breathe a frame between captures
                }
            }
            finally
            {
                // Only the CURRENT pump may clear the flag — a presumed-dead
                // iterator's late finally (Unity Dispose on stop) must not
                // reopen the gate underneath the replacement pump.
                if (pumpId == _pumpId) _pumpRunning = false;
            }
        }

        private static void OnCaptureFailure(string key, string name, string reason)
        {
            Plugin.Log?.LogWarning($"[CARDSNAP] capture failed for '{name}': {reason} — PNG fallback serves");
            RecordCaptureFailure(key);
        }

        /// <summary>Fail-set + health accounting shared by every capture
        /// failure (the specific reason is logged at the failure site).</summary>
        private static void RecordCaptureFailure(string key)
        {
            _failed.Add(key);
            _consecutiveFailures++;
            if (_consecutiveFailures >= MAX_CONSECUTIVE_FAILURES && SnapshotsHealthy)
            {
                SnapshotsHealthy = false;
                Plugin.Log?.LogError($"[CARDSNAP] {MAX_CONSECUTIVE_FAILURES} consecutive capture failures — native rendering disabled for the session, all surfaces serve the PNG pack");
            }
        }

        /// <summary>The capture pipeline for one card. try/finally only (no
        /// catch — yields are legal inside try-with-finally; the pump's
        /// manual MoveNext catches exceptions). Every early return records
        /// _lastOutcome and logs its reason (learning #66). pumpId is the
        /// owning pump's id — the cache insert is guarded on it (R2-1).</summary>
        private static IEnumerator CaptureOne(int pumpId, PendingItem pending)
        {
            string key = pending.key;
            string cardName = pending.name;
            GameObject clone = null;
            GameObject camGO = null;
            RenderTexture rt = null;
            Texture2D tex = null;
            bool keepTex = false;
            int genAtStart = _generation;
            float t0 = Time.realtimeSinceStartup;
            try
            {
                // ── Environment probes (soft failures — retryable) ──
                var choice = CardChoice.instance;
                if (choice == null)
                {
                    // Risk (iii) from the recon: CardInfo.Awake calls
                    // CardChoice.instance.GetSourceCard — instantiating
                    // without the instance would NRE inside Unity's Awake
                    // dispatch (swallowed by Unity, leaving a half-built
                    // card). Probe first, per the recon's requirement.
                    SoftFail("CardChoice.instance is null (scene without the card registry)");
                    yield break;
                }
                if (Optionshandler.instance == null)
                {
                    // CardInfoDisplayer.DrawCard reads
                    // Optionshandler.instance.OptionsData per stat line.
                    SoftFail("Optionshandler.instance is null");
                    yield break;
                }

                var proto = ResolveCard(choice, cardName);
                if (proto == null)
                {
                    _lastOutcome = Outcome.FailedCard;
                    Plugin.Log?.LogWarning($"[CARDSNAP] no CardInfo prefab matches '{cardName}' — card marked failed for the session (PNG serves)");
                    yield break;
                }

                if (_chosenLayer < 0)
                {
                    _chosenLayer = PickIsolationLayer();
                    Plugin.Log?.LogInfo($"[CARDSNAP] isolation layer {_chosenLayer} ('{LayerMask.LayerToName(_chosenLayer)}')");
                }

                // ── Spawn (FfaMode recipe, FfaMode.cs ~1880) ──
                clone = choice.AddCardVisual(proto, ParkPos);
                if (clone == null)
                {
                    _lastOutcome = Outcome.FailedCapture;
                    Plugin.Log?.LogWarning($"[CARDSNAP] AddCardVisual returned null for '{cardName}'");
                    yield break;
                }
                // No HideFlags on the clone: if this coroutine somehow never
                // reaches teardown, ROUNDS' scene transition destroys unknown
                // objects (#16) — a free leak backstop. HideFlags go on OUR
                // camera only.

                // Strip the card prefab's PhotonView (plain Instantiate means
                // viewID 0 / unregistered, production-proven in FFA, but the
                // recon calls for stripping on the out-of-room path).
                try
                {
                    var views = clone.GetComponentsInChildren<PhotonView>(true);
                    for (int i = 0; i < views.Length; i++)
                        if (views[i] != null) UnityEngine.Object.Destroy(views[i]);
                }
                catch (Exception pvEx)
                {
                    Plugin.Log?.LogWarning($"[CARDSNAP] PhotonView strip failed for '{cardName}': {pvEx.Message} (continuing — FFA runs with the view in place)");
                }

                // Vanilla disables the card's DamagableEvent Collider2D so
                // bullets can't "shoot-to-pick" it. String-typed GetComponent
                // — the FfaMode idiom (Collider2D derives from Behaviour, so
                // .enabled is reachable through that cast without touching
                // the csproj).
                try
                {
                    var dmg = clone.GetComponentInChildren<DamagableEvent>();
                    var col = dmg != null ? dmg.GetComponent("Collider2D") as Behaviour : null;
                    if (col != null) col.enabled = false;
                }
                catch (Exception colEx)
                {
                    Plugin.Log?.LogWarning($"[CARDSNAP] collider disable failed for '{cardName}': {colEx.Message}");
                }

                // Mute the clone: CurveAnimation.DoAnimation plays the
                // card-appear sound (SoundManager.Instance.Play) when its
                // PlayIn runs — for the snapshot clone that would be an
                // audible whoosh from an invisible offscreen card. The
                // PlayIn that matters fires from CardVisuals.Start NEXT
                // frame (ChangeSelected(true)), so nulling the soundPlay
                // entries in the same frame as the Instantiate silences it.
                // (A playOnAwake animation could still emit one sound during
                // Instantiate itself — accepted residual, identical to what
                // FFA's production pick phase already does.)
                try
                {
                    var anims = clone.GetComponentsInChildren<CurveAnimation>(true);
                    for (int i = 0; i < anims.Length; i++)
                    {
                        var sp = anims[i] != null ? anims[i].soundPlay : null;
                        if (sp == null) continue;
                        for (int j = 0; j < sp.Length; j++) sp[j] = null;
                    }
                }
                catch (Exception sndEx)
                {
                    Plugin.Log?.LogWarning($"[CARDSNAP] sound mute failed for '{cardName}': {sndEx.Message} (capture continues — cosmetic only)");
                }

                SetLayerRecursive(clone, _chosenLayer);

                // ── Settle: the card is particle-built over frames ──
                // settleBonus is 0 on the fast first attempt; a probe-failed
                // retry re-runs with the bonus so slow rigs still capture.
                float settleTarget = SETTLE_SECONDS + pending.settleBonus;
                float settleStart = Time.realtimeSinceStartup;
                int frames = 0;
                while (Time.realtimeSinceStartup - settleStart < settleTarget || frames < SETTLE_MIN_FRAMES)
                {
                    yield return null;
                    frames++;
                    if (clone == null)
                    {
                        // Scene transition destroyed it mid-settle.
                        SoftFail("clone destroyed mid-settle (scene change)");
                        yield break;
                    }
                }

                // Extra grace for the game's async localized-string
                // resolution: wait until at least one TMP text under the
                // clone is non-empty (name text always resolves eventually —
                // CardInfo.CardName falls back to the GameObject name).
                float textStart = Time.realtimeSinceStartup;
                bool haveText = AnyVisibleTmpText(clone);
                while (!haveText && Time.realtimeSinceStartup - textStart < TEXT_WAIT_EXTRA_S)
                {
                    yield return null;
                    if (clone == null)
                    {
                        SoftFail("clone destroyed during text wait (scene change)");
                        yield break;
                    }
                    haveText = AnyVisibleTmpText(clone);
                }
                if (!haveText)
                    Plugin.Log?.LogWarning($"[CARDSNAP] '{cardName}': no TMP text visible after {TEXT_WAIT_EXTRA_S:F0}s extra wait — capturing anyway (probe decides)");

                // Re-stamp the layer: GeneralParticleSystem's ObjectPool
                // instantiated its pooled particle GameObjects DURING the
                // settle window (new children keep the prefab's layer, not
                // the parent's) — without this pass the particle-built card
                // body is invisible to the isolated camera.
                SetLayerRecursive(clone, _chosenLayer);

                // Same pre-capture layout flush as the tier-export harness.
                ForceUpdateCanvases();

                // ── Frame the card ──
                if (!TryComputeBounds(clone, out var bMin, out var bMax))
                {
                    _lastOutcome = Outcome.FailedCard;
                    Plugin.Log?.LogWarning($"[CARDSNAP] degenerate bounds for '{cardName}' — card marked failed for the session");
                    yield break;
                }
                var center = (bMin + bMax) * 0.5f;
                float halfW = (bMax.x - bMin.x) * 0.5f;
                float halfH = (bMax.y - bMin.y) * 0.5f;
                float depth = Mathf.Max(1f, bMax.z - bMin.z);

                // ── Render (tier-export harness camera, isolated) ──
                camGO = new GameObject("CR_CardSnapCam");
                camGO.hideFlags = HideFlags.HideAndDontSave;
                camGO.transform.position = new Vector3(center.x, center.y, bMin.z - 10f);
                var cam = camGO.AddComponent<Camera>();
                cam.enabled = false; // manual Render() only — never a live scene camera
                cam.orthographic = true;
                cam.aspect = (float)RT_W / RT_H;
                // Fit both extents inside the fixed RT aspect; 8% padding so
                // the idle CardAnimation wobble doesn't clip edges.
                cam.orthographicSize = Mathf.Max(halfH, halfW / cam.aspect) * 1.08f;
                cam.clearFlags = CameraClearFlags.SolidColor;
                cam.backgroundColor = new Color(0f, 0f, 0f, 0f); // transparent — card floats over any panel
                cam.cullingMask = 1 << _chosenLayer;             // our layer ONLY
                cam.nearClipPlane = 0.1f;
                cam.farClipPlane = 20f + depth + 10f;

                // ── Top Card thumbnail rect (item 9a, reopened 2026-09-21) ──
                // Texels, computed from the SAME framing the camera just got,
                // so nothing here scans pixels. The camera is orthographic
                // and its aspect is the RT's, so one scale serves both axes:
                // orthographicSize is the visible world half-HEIGHT, and
                // RT_H / (2 * that) is texels per world unit. Texel origin is
                // bottom-left, matching ReadPixels and Sprite.Create.
                //
                // The ink rect is the framed FACE bounds projected back
                // through that scale. On the prefab this was measured against
                // that one step drops all three unwanted things: the 1.08
                // wobble pad, the letterbox the fixed RT aspect adds, and the
                // vanilla name plate — the last because Text_Name sits ABOVE
                // the "Canvas" child TryComputeBounds framed on. The band
                // keying below is a hedge for a prefab where the body is a
                // SMALLER rect than the framed face; on this one the two
                // rects agree and it changes nothing. See BAND_HOLDER_PATHS.
                float pxPerWorld = RT_H / (2f * cam.orthographicSize);
                Rect inkRect = WorldRectToTexels(center, bMin, bMax, pxPerWorld);
                Rect thumbRect = inkRect;
                string thumbFrom = "ink:" + _faceBoundsSource;
                if (TryComputeBandBounds(clone, out var cMin, out var cMax))
                {
                    thumbRect = WorldRectToTexels(center, cMin, cMax, pxPerWorld);
                    thumbFrom = _bandHolderName;
                }
                else
                {
                    // Harmless by itself WHEN the face was found by name — the
                    // framed face rect is a crop, and on the measured prefab
                    // it is the same rect the band would have given. When it
                    // was not, the next check is what says so. Either way a
                    // prefab child this code names by string has gone, and the
                    // only other trace would be one field of one Info line.
                    // Say it at WARNING so a rename is visible in a log that
                    // is read by grepping for warnings.
                    Plugin.Log?.LogWarning($"[CARDSNAP] Top Card thumbnail for '{cardName}': no corner-band holder under the clone (looked for Front/Background) — using the framed face bounds instead; a prefab rename is the usual reason");
                }
                // The failure that takes the Top Card away again:
                // TryComputeBounds found no child named "Canvas" and
                // encapsulated EVERY RectTransform instead, which includes
                // Particles — larger than the card — so the framing, the ink
                // rect and therefore the thumbnail are all wider than the card
                // face. HOW that then shows was MEASURED, not assumed
                // (mutation M7, 2026-09-21): the card ends up small enough in
                // frame that the #139 lit probe reads 0.2% and soft-defers
                // every capture, so nothing is cached and the Top Card row
                // hides itself — no picture rather than a wrong one. This line
                // therefore claims only the part that held, that the thumbnail
                // is not a crop of the card. Before it existed, nothing above
                // Info said any of it.
                if (_faceBoundsSource != FACE_SOURCE_NAMED)
                    Plugin.Log?.LogWarning($"[CARDSNAP] Top Card thumbnail for '{cardName}': the card face was framed by encapsulating every RectTransform, not by the '{FACE_SOURCE_NAMED}' child — the framing is wider than the card, so this thumbnail is not a crop of it");
                DumpCardHierarchyOnce(clone, cardName, center, pxPerWorld);

                rt = new RenderTexture(RT_W, RT_H, 24);
                cam.targetTexture = rt;
                cam.Render();

                var prevActive = RenderTexture.active;
                try
                {
                    RenderTexture.active = rt;
                    tex = new Texture2D(RT_W, RT_H, TextureFormat.RGBA32, false);
                    tex.ReadPixels(new Rect(0, 0, RT_W, RT_H), 0, 0);
                    tex.Apply();
                }
                finally
                {
                    RenderTexture.active = prevActive;
                }

                // ── #139 lit-pixel probe ──
                float litFraction = ProbeLitFraction(tex);
                if (litFraction < PROBE_MIN_LIT_FRACTION)
                {
                    if (pending.settleBonus <= 0f)
                    {
                        // Fast-settle miss (Aug 6 item 3): the 0.55s window
                        // may simply have been too short on this rig. Grant
                        // the retry bonus and soft-retry BEFORE letting a
                        // probe failure count toward SnapshotsHealthy — the
                        // speedup must never disable the pipeline.
                        pending.settleBonus = SETTLE_RETRY_BONUS_S;
                        _lastOutcome = Outcome.SoftRetry;
                        _lastSoftReason = $"probe blank on fast settle (lit {litFraction:P2}) — retrying with +{SETTLE_RETRY_BONUS_S:F2}s settle";
                        yield break;
                    }
                    _lastOutcome = Outcome.FailedCapture;
                    Plugin.Log?.LogWarning($"[CARDSNAP] #139 probe FAILED for '{cardName}' (lit {litFraction:P2} < {PROBE_MIN_LIT_FRACTION:P1}) — blank capture NOT cached, PNG serves. Card PS shader: {DescribeCardParticleShader(clone)}");
                    yield break;
                }

                if (pumpId != _pumpId)
                {
                    // R2-1 second guard: a stale pump's capture must never
                    // insert into the cache the replacement pump owns.
                    // Unreachable in practice — the driver loop aborts a
                    // stale pump at every yield resume, before the MoveNext
                    // that would run this code — so this is pure defense in
                    // depth. Discard without a fail count.
                    _lastOutcome = Outcome.SoftRetry;
                    _lastSoftReason = "pump replaced mid-capture";
                    yield break;
                }

                if (_generation != genAtStart)
                {
                    // Locale switched mid-capture — this snapshot carries
                    // the OLD locale's text. Discard silently-successfully:
                    // no fail count, the fresh request re-renders.
                    _lastOutcome = Outcome.SoftRetry;
                    _lastSoftReason = "locale changed mid-capture";
                    yield break;
                }

                // Self-contained image: re-render the SAME settled clone over
                // an opaque backing and force alpha to 255. Runs AFTER the
                // #139 probe on purpose (see the method comment) and after the
                // discard guards above so a snapshot we are about to throw
                // away never pays for it.
                bool opaque = CompositeOntoOpaqueBacking(cam, rt, tex);

                tex.filterMode = FilterMode.Bilinear;
                tex.hideFlags = HideFlags.HideAndDontSave;
                var sprite = Sprite.Create(tex,
                    new Rect(0, 0, tex.width, tex.height),
                    new Vector2(0.5f, 0.5f), 100f);
                sprite.name = $"CardSnap_{key}";
                sprite.hideFlags = HideFlags.HideAndDontSave;
                // The Top Card thumbnail: a second Sprite over the SAME
                // texture, so the crop costs no extra pixels. If it cannot
                // be built, the full sprite stands in — the Top Card slot
                // then shows the old framing instead of nothing, and the
                // warning below is how that is noticed.
                Sprite thumb = null;
                try
                {
                    thumb = Sprite.Create(tex, thumbRect, new Vector2(0.5f, 0.5f), 100f);
                    thumb.name = $"CardSnapThumb_{key}";
                    thumb.hideFlags = HideFlags.HideAndDontSave;
                }
                catch (Exception ex)
                {
                    Plugin.Log?.LogWarning($"[CARDSNAP] thumbnail crop failed for '{cardName}' ({ex.Message}) — Top Card shows the full card picture");
                    thumb = null;
                }
                // F1(c): a re-capture landing on a live key (alias re-keying
                // after CardRarityLookup.ScanAll populates, generation races)
                // must destroy the sprite/texture it replaces, or it leaks.
                if (_cache.ContainsKey(key)) EvictKey(key);
                // F1(b): hard cap at INSERT time — the enqueue-time check
                // alone can be exceeded by items already sitting in the
                // queue when the cap is crossed. Evict + DESTROY the oldest
                // (insertion order).
                // Accepted residual (R2-Low4): with the vanilla 67-card set
                // the cap (96) never trips. In a hypothetically modded
                // >cap environment, an evicted sprite still bound to a live
                // uGUI Image goes blank until the next hover re-captures.
                while (_cache.Count >= MAX_CACHED && _cacheOrder.Count > 0)
                {
                    string oldest = _cacheOrder[0];
                    bool had = _cache.ContainsKey(oldest);
                    EvictKey(oldest);   // removes it from _cacheOrder too
                    if (had)
                        Plugin.Log?.LogInfo($"[CARDSNAP] cache cap {MAX_CACHED} — evicted oldest '{oldest}' to admit '{key}'");
                }
                _cache[key] = sprite;
                _thumbs[key] = thumb ?? sprite;
                _cacheOrder.Add(key);
                keepTex = true;
                _lastOutcome = Outcome.Success;
                Plugin.Log?.LogInfo($"[CARDSNAP] captured '{cardName}' ({RT_W}x{RT_H}, lit {litFraction:P1}, opaque={opaque}) in {(Time.realtimeSinceStartup - t0) * 1000f:F0}ms — {_cache.Count} cached");
                Plugin.Log?.LogInfo($"[CARDSNAP-THUMB] '{cardName}' rect=({thumbRect.x:F1},{thumbRect.y:F1},{thumbRect.width:F1}x{thumbRect.height:F1}) from={thumbFrom} ink=({inkRect.x:F1},{inkRect.y:F1},{inkRect.width:F1}x{inkRect.height:F1}) rt={RT_W}x{RT_H}");
            }
            finally
            {
                try { if (clone != null) UnityEngine.Object.Destroy(clone); } catch { }
                try
                {
                    if (camGO != null)
                    {
                        var c = camGO.GetComponent<Camera>();
                        if (c != null) c.targetTexture = null;
                        UnityEngine.Object.Destroy(camGO);
                    }
                }
                catch { }
                try { if (rt != null) UnityEngine.Object.Destroy(rt); } catch { }
                try { if (!keepTex && tex != null) UnityEngine.Object.Destroy(tex); } catch { }
            }
        }

        private static void SoftFail(string reason)
        {
            _lastOutcome = Outcome.SoftRetry;
            _lastSoftReason = reason;
        }

        /// <summary>Two-path resolve mirroring NativeUI.ShowCardPreview:
        /// CardChoice.instance.cards first (always-loaded global registry),
        /// then Resources.FindObjectsOfTypeAll for cards not registered
        /// there — asset prefabs only (never a live "(Clone)" mid-pick).
        /// Matches GameObject name and display-name field, both normalized
        /// the same way as the requested + canonical forms (#19: both name
        /// forms must resolve).</summary>
        private static CardInfo ResolveCard(CardChoice choice, string requested)
        {
            string reqKey = CardImageLoader.NormalizeKey(requested);
            string canonKey = KeyFor(requested);
            // Bug #155: the canonical name is DB-facing and CORRECTS ROUNDS'
            // typos, so for Leech/Ricochet/Poison it matches no live prefab at
            // all — those cards logged "no CardInfo prefab matches" on every
            // request and permanently served the PNG. Walk the alias map
            // backwards and accept any raw in-game spelling too.
            var rawKeys = new List<string> { reqKey, canonKey };
            try
            {
                foreach (var raw in CardRarityLookup.RawNamesFor(
                             CardRarityLookup.GetCanonicalName(requested) ?? requested))
                {
                    string k = CardImageLoader.NormalizeKey(raw);
                    if (!string.IsNullOrEmpty(k) && !rawKeys.Contains(k)) rawKeys.Add(k);
                }
            }
            catch { }

            bool Matches(string s)
            {
                if (string.IsNullOrEmpty(s)) return false;
                string k = CardImageLoader.NormalizeKey(s);
                for (int i = 0; i < rawKeys.Count; i++)
                    if (k == rawKeys[i]) return true;
                return false;
            }

            try
            {
                var cards = choice.cards;
                if (cards != null)
                {
                    for (int i = 0; i < cards.Length; i++)
                    {
                        var ci = cards[i];
                        if (ci == null) continue;
                        string goName = ci.gameObject != null ? ci.gameObject.name.Replace("(Clone)", "").Trim() : null;
                        if (Matches(goName) || Matches(ci.cardName)) return ci;
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] registry scan failed: " + ex.Message);
            }

            try
            {
                var all = Resources.FindObjectsOfTypeAll<CardInfo>();
                for (int i = 0; i < all.Length; i++)
                {
                    var ci = all[i];
                    if (ci == null || ci.gameObject == null) continue;
                    string goName = ci.gameObject.name;
                    if (goName.Contains("(Clone)")) continue; // live scene copy — want the asset
                    if (Matches(goName) || Matches(ci.cardName)) return ci;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] Resources fallback scan failed: " + ex.Message);
            }
            return null;
        }

        /// <summary>Highest UNNAMED layer — unnamed means no game code can
        /// reference it via LayerMask.NameToLayer (the game's named layers
        /// are "Default"/"Player"/etc). Even a false positive is benign:
        /// the park position keeps the clone outside every live frustum
        /// (the tier-export harness relies on position isolation alone).</summary>
        internal static int PickIsolationLayer()
        {
            try
            {
                for (int l = 31; l >= 24; l--)
                    if (string.IsNullOrEmpty(LayerMask.LayerToName(l))) return l;
            }
            catch { }
            return 31;
        }

        internal static void SetLayerRecursive(GameObject root, int layer)
        {
            try
            {
                var transforms = root.GetComponentsInChildren<Transform>(true);
                for (int i = 0; i < transforms.Length; i++)
                    if (transforms[i] != null) transforms[i].gameObject.layer = layer;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] layer stamp failed: " + ex.Message);
            }
        }

        /// <summary>The child name that IS the card face. Also the value
        /// _faceBoundsSource carries when that child was the one used, which
        /// is the only case where the framing is the card's own rect.</summary>
        private const string FACE_SOURCE_NAMED = "Canvas";

        /// <summary>Which path TryComputeBounds last took: FACE_SOURCE_NAMED
        /// when it framed on that child, "encapsulated" when it had to union
        /// every RectTransform instead. Read by the capture to decide whether
        /// the thumbnail rect is the card's rect or something larger.
        /// Static, and safe to read that way for one reason only: the capture
        /// coroutine has no yield between the call that writes it and the two
        /// reads of it, so nothing can run in between. Moving either the call
        /// or the reads across a yield breaks that and the value would then
        /// belong to whichever capture wrote it last.</summary>
        private static string _faceBoundsSource = FACE_SOURCE_NAMED;

        /// <summary>World-XY bounds of the card face. Prefers the cardBase's
        /// "Canvas" RectTransform (vanilla structure per CardVisuals.Awake:
        /// "Canvas/Front/Grid") — exactly the card face, right aspect. Falls
        /// back to encapsulating every RectTransform under the clone, which is
        /// a WIDER box than the card (Particles alone overruns it), so the
        /// fallback is recorded rather than taken silently.</summary>
        private static bool TryComputeBounds(GameObject root, out Vector3 min, out Vector3 max)
        {
            min = Vector3.zero;
            max = Vector3.zero;
            _faceBoundsSource = "encapsulated";
            try
            {
                var rts = root.GetComponentsInChildren<RectTransform>(true);
                if (rts == null || rts.Length == 0) return false;
                RectTransform face = null;
                for (int i = 0; i < rts.Length; i++)
                {
                    if (rts[i] != null && rts[i].gameObject.name == FACE_SOURCE_NAMED) { face = rts[i]; break; }
                }
                if (face != null) _faceBoundsSource = FACE_SOURCE_NAMED;
                var corners = new Vector3[4];
                bool got = false;
                Vector3 mn = Vector3.zero, mx = Vector3.zero;
                void Encapsulate(RectTransform r)
                {
                    r.GetWorldCorners(corners);
                    for (int i = 0; i < 4; i++)
                    {
                        if (!got) { mn = mx = corners[i]; got = true; }
                        else { mn = Vector3.Min(mn, corners[i]); mx = Vector3.Max(mx, corners[i]); }
                    }
                }
                if (face != null) Encapsulate(face);
                else
                {
                    for (int i = 0; i < rts.Length; i++)
                        if (rts[i] != null) Encapsulate(rts[i]);
                }
                if (!got) return false;
                min = mn;
                max = mx;
                return (max.x - min.x) > 0.05f && (max.y - min.y) > 0.05f;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] bounds compute failed: " + ex.Message);
                return false;
            }
        }

        // ── Top Card thumbnail: what actually crops it, and what this does ──
        //
        // The thumbnail has to exclude three things: the camera's 1.08 wobble
        // pad, the letterbox the fixed RT aspect adds, and the vanilla name
        // plate (a second copy of the card's name, unreadable at 104 px and
        // crowding the badge's top rail). On the prefab this was measured
        // against, ALL THREE go for ONE reason, and it is not this table.
        //
        // DumpCardHierarchyOnce read 150 RectTransforms off a real clone on
        // this seat (2026-09-21, ai-collab/wavebc-r3-9a-child-dump.log):
        //
        //   00 Canvas                  (14.1, 60.1) 351.9 x 479.9  top = 540.0
        //   02 Canvas/Front/Background (14.1, 60.1) 351.9 x 479.9  <- IDENTICAL
        //   28 Canvas/Front/Text_Name  (37.1,539.4) 305.8 x  60.6  <- ABOVE it
        //   47/57/67/77 Canvas/Front/Edges/EdgePart[0..3] 31.9 x 31.9, at the
        //       four corners of that same rect (x 14.1|334.0, y 60.1|508.0)
        //
        // TryComputeBounds frames on the child named "Canvas", so the ink
        // rect IS entry 00 — and entry 02 is the same rect to a tenth of a
        // texel. So the pad and the letterbox go because the thumbnail is the
        // framed face rect rather than the whole texture, the corner marks
        // land on its edges because they sit on that same rect, and the name
        // plate goes because Text_Name STARTS at y 539.4, above Canvas's top
        // at 540.0 — outside the face, not merely outside the band.
        //
        // On this prefab the table below therefore changes NOTHING: the
        // capture log line says so on its own face, rect == ink. Keeping it
        // is a hedge for a prefab where the two rects differ — a name plate
        // moved inside Canvas, an outer frame added — where Background would
        // still be the body and the face rect would not. It is matched by
        // parent AND child name because "Background" also occurs under
        // Canvas/Back and choosing by traversal order would be luck.
        //
        // Nothing here has been SHOWN to fix anything, and no comment should
        // say it has: a check bound to something that merely correlates with
        // the property stops meaning what its name says while staying green
        // (#732). What the witness demonstrated is the crop; the keying rides
        // along. Both outcomes are logged, and the caller warns when the
        // holder is missing AND when the face bounds came from the
        // encapsulate-everything fallback — that second case is the one that
        // silently restores the reported picture.
        private static readonly string[,] BAND_HOLDER_PATHS = { { "Front", "Background" } };
        private static string _bandHolderName = "(none)";

        /// <summary>Project a world-space XY box onto the render texture, in
        /// texels with a bottom-left origin. The camera is orthographic with
        /// the RT's own aspect, so pxPerWorld is the same on both axes and
        /// the camera's XY position is the texture's centre.</summary>
        private static Rect WorldRectToTexels(Vector3 camCenter, Vector3 wMin, Vector3 wMax, float pxPerWorld)
        {
            float x0 = RT_W * 0.5f + (wMin.x - camCenter.x) * pxPerWorld;
            float x1 = RT_W * 0.5f + (wMax.x - camCenter.x) * pxPerWorld;
            float y0 = RT_H * 0.5f + (wMin.y - camCenter.y) * pxPerWorld;
            float y1 = RT_H * 0.5f + (wMax.y - camCenter.y) * pxPerWorld;
            x0 = Mathf.Clamp(x0, 0f, RT_W); x1 = Mathf.Clamp(x1, 0f, RT_W);
            y0 = Mathf.Clamp(y0, 0f, RT_H); y1 = Mathf.Clamp(y1, 0f, RT_H);
            // Sprite.Create throws on a rect outside the texture or with a
            // non-positive extent; one texel is the smallest thing that is
            // still a picture.
            return new Rect(x0, y0, Mathf.Max(1f, x1 - x0), Mathf.Max(1f, y1 - y0));
        }

        /// <summary>World-XY bounds of the card's corner band — the first
        /// BAND_HOLDER_PATHS parent/child pair present under the clone.
        /// False when none is, which leaves the thumbnail on the framed face
        /// rect and makes the caller warn. Records which pair answered, for
        /// the capture log line.</summary>
        private static bool TryComputeBandBounds(GameObject root, out Vector3 min, out Vector3 max)
        {
            min = Vector3.zero;
            max = Vector3.zero;
            try
            {
                var rts = root.GetComponentsInChildren<RectTransform>(true);
                if (rts == null || rts.Length == 0) return false;
                var corners = new Vector3[4];
                for (int n = 0; n < BAND_HOLDER_PATHS.GetLength(0); n++)
                {
                    string wantParent = BAND_HOLDER_PATHS[n, 0], wantChild = BAND_HOLDER_PATHS[n, 1];
                    for (int i = 0; i < rts.Length; i++)
                    {
                        if (rts[i] == null || rts[i].gameObject.name != wantChild) continue;
                        var parent = rts[i].transform.parent;
                        if (parent == null || parent.gameObject.name != wantParent) continue;
                        rts[i].GetWorldCorners(corners);
                        Vector3 mn = corners[0], mx = corners[0];
                        for (int c = 1; c < 4; c++) { mn = Vector3.Min(mn, corners[c]); mx = Vector3.Max(mx, corners[c]); }
                        if ((mx.x - mn.x) <= 0.05f || (mx.y - mn.y) <= 0.05f) continue;
                        min = mn; max = mx;
                        _bandHolderName = wantParent + "/" + wantChild;
                        return true;
                    }
                }
                _bandHolderName = "(none)";
                return false;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] band bounds compute failed: " + ex.Message);
                _bandHolderName = "(error)";
                return false;
            }
        }

        private static bool _dumpedHierarchy;

        /// <summary>One-shot dump of the cloned card's RectTransform children
        /// — name, path, and the texel box each one would crop to — so the
        /// corner-band holder can be read off a real prefab instead of
        /// guessed. Broadcast seat only, once per session, same gate and
        /// log-prefix idiom as the other [Broadcast] Test* levers.</summary>
        private static void DumpCardHierarchyOnce(GameObject root, string cardName, Vector3 camCenter, float pxPerWorld)
        {
            try
            {
                if (_dumpedHierarchy || root == null) return;
                if (!BroadcastMode.IsBroadcastIdentity) return;
                _dumpedHierarchy = true;
                var rts = root.GetComponentsInChildren<RectTransform>(true);
                if (rts == null) return;
                Plugin.Log?.LogInfo($"[CARDSNAP-DUMP] '{cardName}': {rts.Length} RectTransform(s); rect is texels in a {RT_W}x{RT_H} capture, origin bottom-left");
                var corners = new Vector3[4];
                for (int i = 0; i < rts.Length; i++)
                {
                    if (rts[i] == null) continue;
                    string path = rts[i].gameObject.name;
                    var t = rts[i].transform.parent;
                    while (t != null && t != root.transform) { path = t.gameObject.name + "/" + path; t = t.parent; }
                    rts[i].GetWorldCorners(corners);
                    Vector3 mn = corners[0], mx = corners[0];
                    for (int c = 1; c < 4; c++) { mn = Vector3.Min(mn, corners[c]); mx = Vector3.Max(mx, corners[c]); }
                    Rect r = WorldRectToTexels(camCenter, mn, mx, pxPerWorld);
                    Plugin.Log?.LogInfo($"[CARDSNAP-DUMP]   {i:D2} name='{rts[i].gameObject.name}' active={rts[i].gameObject.activeInHierarchy} path='{path}' rect=({r.x:F1},{r.y:F1},{r.width:F1}x{r.height:F1})");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP-DUMP] failed: " + ex.Message);
            }
        }

        private static void ForceUpdateCanvases()
        {
            try
            {
                Type canvasT = null;
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    canvasT = asm.GetType("UnityEngine.Canvas");
                    if (canvasT != null) break;
                }
                canvasT?.GetMethod("ForceUpdateCanvases", BindingFlags.Public | BindingFlags.Static)?.Invoke(null, null);
            }
            catch { }
        }

        /// <summary>True when at least one ACTIVE TMP text under the clone
        /// has non-empty text (the displayer's name label at minimum —
        /// CardInfo.CardName falls back to the GameObject name so it always
        /// resolves eventually). Reflection-only TMP access.</summary>
        private static bool AnyVisibleTmpText(GameObject root)
        {
            try
            {
                if (!_tmpProbed)
                {
                    _tmpProbed = true;
                    foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                    {
                        _tmpType = asm.GetType("TMPro.TMP_Text") ?? asm.GetType("TMPro.TextMeshProUGUI");
                        if (_tmpType != null) break;
                    }
                    _tmpTextProp = _tmpType?.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                }
                if (_tmpType == null || _tmpTextProp == null) return true; // cannot check — never block on it
                var comps = root.GetComponentsInChildren(_tmpType, false);
                for (int i = 0; i < comps.Length; i++)
                {
                    if (comps[i] == null) continue;
                    var s = _tmpTextProp.GetValue(comps[i]) as string;
                    if (!string.IsNullOrEmpty(s) && s.Trim().Length > 0) return true;
                }
                return false;
            }
            catch
            {
                return true;
            }
        }

        /// <summary>Re-renders the SAME settled clone over an OPAQUE backing
        /// and forces every captured pixel to alpha 255, so the cached texture
        /// is self-contained at EVERY draw site. Returns false (and leaves the
        /// transparent capture in place — exact previous behavior) on any
        /// failure.
        ///
        /// Why: uGUI/TMP render with `Blend SrcAlpha OneMinusSrcAlpha`, and
        /// that blend applies to the ALPHA channel too — over a
        /// transparent-cleared RT a layer of coverage `a` lands as `a*a`, so
        /// every semi-transparent part of the card (the theme-tinted front
        /// Images CardVisuals.ChangeSelected assigns, the soft card art, TMP's
        /// anti-aliased glyph edges) captures at far less coverage than it has
        /// in game. NativeUI's card popup hides that completely — its Image
        /// sits on a 0.97-alpha panel — but the hold-Tab overlay composites
        /// the same texture straight onto the live map, which is the "really
        /// faint and hard to read" report. Clearing to an opaque colour makes
        /// the RGB channel the exact straight-alpha composite (RGB is already
        /// correct premultiplied coverage; only the alpha channel is squared,
        /// hence the forced 255).
        ///
        /// Ordering is load-bearing: this is a SECOND render, run only after
        /// ProbeLitFraction has already judged the transparent-backed capture.
        /// The #139 probe therefore keeps its exact current semantics (a blank
        /// render still reads 0% lit and is rejected) instead of passing
        /// because a fill colour was painted into every pixel.</summary>
        private static bool CompositeOntoOpaqueBacking(Camera cam, RenderTexture rt, Texture2D tex)
        {
            try
            {
                if (cam == null || rt == null || tex == null) return false;
                cam.backgroundColor = BACKING_COLOR;
                cam.Render();
                var prevActive = RenderTexture.active;
                try
                {
                    RenderTexture.active = rt;
                    tex.ReadPixels(new Rect(0, 0, RT_W, RT_H), 0, 0);
                }
                finally
                {
                    RenderTexture.active = prevActive;
                }
                var px = tex.GetPixels32();
                if (px != null && px.Length > 0)
                {
                    for (int i = 0; i < px.Length; i++) px[i].a = 255;
                    tex.SetPixels32(px);
                }
                tex.Apply();
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] opaque composite failed: " + ex.Message + " — caching the transparent capture (previous behavior)");
                return false;
            }
        }

        /// <summary>Fraction of sampled pixels that are composited-visible:
        /// alpha AND max(r,g,b) above the floor (transparent or pure-black
        /// pixels do not count — F5). Stride-4 sampling keeps the one-time
        /// cost small (~57k checks of 228k pixels).</summary>
        private static float ProbeLitFraction(Texture2D tex)
        {
            try
            {
                var px = tex.GetPixels32();
                if (px == null || px.Length == 0) return 0f;
                int lit = 0, sampled = 0;
                for (int i = 0; i < px.Length; i += 4)
                {
                    sampled++;
                    var c = px[i];
                    if (c.a > PROBE_CHANNEL_FLOOR &&
                        (c.r > PROBE_CHANNEL_FLOOR || c.g > PROBE_CHANNEL_FLOOR ||
                         c.b > PROBE_CHANNEL_FLOOR))
                        lit++;
                }
                return sampled > 0 ? (float)lit / sampled : 0f;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[CARDSNAP] probe failed: " + ex.Message);
                return 0f;
            }
        }

        /// <summary>Diagnostic for the #139 report: names the shader on the
        /// cardBase's REAL ParticleSystem renderer — the one card renderer
        /// whose lit/unlit status the recon could not verify statically.</summary>
        private static string DescribeCardParticleShader(GameObject clone)
        {
            try
            {
                if (clone == null) return "clone gone";
                var psr = clone.GetComponentInChildren<ParticleSystemRenderer>(true);
                var mat = psr != null ? psr.sharedMaterial : null;
                var sh = mat != null ? mat.shader : null;
                return sh != null ? sh.name : "none found";
            }
            catch { return "probe error"; }
        }
    }
}
