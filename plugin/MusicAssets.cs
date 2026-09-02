using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Which asset tier a music file belongs to. Independent trees:
    /// music/&lt;revision&gt;/previews/ and music/&lt;revision&gt;/full/, each with its own
    /// installed.json ready marker (design v3 §3 [G2]).</summary>
    internal enum MusicTier { Previews, Full }

    /// <summary>One row of the compiled install manifest — the validity
    /// authority for downloaded/bundled music files [F22]/[G8].</summary>
    internal sealed class MusicManifestEntry
    {
        public string Name;
        public MusicTier Tier;
        public long Size;
        public string Sha256;
    }

    /// <summary>
    /// Music asset delivery — the v3-FINAL immutable-asset-revision protocol
    /// (design v3 §3 + [H1]/[H2]).
    ///
    /// ── Model ──
    /// Assets live on a DEDICATED immutable GitHub release, tag
    /// "music-{ASSET_REVISION}", holding exactly music-previews.zip + music.zip.
    /// ASSET_REVISION is bumped ONLY when music bytes change; an ordinary mod
    /// release never attaches or re-attaches music, so "a release forgot the
    /// music" cannot exist as a failure mode [G3]. Disk layout under the DLL dir
    /// (standalone BepInEx and Thunderstore profiles place the plugin dir
    /// differently — never a hardcoded game path):
    ///   music/ar1/previews/  + installed.json   (7 snippets + cover PNG)
    ///   music/ar1/full/      + installed.json   (7 full OGGs)
    ///
    /// ── Install protocol [H1] ──
    /// download to temp (streaming compressed-byte cap from COMPILED sizes,
    /// never Content-Length) → per-entry verify against the compiled manifest
    /// (exact name set, size, SHA-256, total ceiling) while extracting into a
    /// unique same-volume staging dir → write installed.json LAST inside
    /// staging → ONE atomic Directory.Move publishes the complete tier. An
    /// invalid pre-existing final tree is renamed to a quarantine path before
    /// publication and the quarantine deleted only after the new tree
    /// revalidates. Cleanup is per-TIER and keep-until-replaced; Initialize
    /// RESOLVES each tier's orphan staging/quarantine trees (publish a valid
    /// copy when the final is absent/invalid, retain quarantine until the
    /// same-tier final validates) and deletes only what that decision makes
    /// redundant — all before the engine opens any clip [I12].
    ///
    /// ── Crash-convergence walk (design R3 implement-must-verify) ──
    /// crash mid-download → *.tmp swept at init, cache untouched;
    /// crash mid-extract/verify → markerless staging (incomplete by protocol)
    ///   swept, cache untouched;
    /// crash after marker write, before rename → the completed staging tree
    ///   validates at init and is PUBLISHED when the final is absent/invalid
    ///   (redundant when a final already validates) — no re-download;
    /// crash after quarantine rename, before publication → final absent: the
    ///   completed staging tree is published, then the quarantine (now
    ///   replaced) is deleted; if no orphan copy validates, the quarantine is
    ///   RETAINED and EnsureTier reinstalls;
    /// crash between publication and quarantine delete → final valid,
    ///   quarantine now redundant and swept;
    /// crash mid stale-revision delete → partial stale tree re-deleted next
    ///   init (current tier still validates).
    /// Every path converges to a valid current tier or a clean re-download with
    /// no manual deletion; a stale revision's tier is never deleted without a
    /// validated current replacement, and no orphan copy is deleted while it is
    /// the only tree of its tier that validates.
    ///
    /// ── HTTP policy [H2] ──
    /// 403/429/5xx/timeouts are TRANSIENT: honor Retry-After in BOTH RFC 7231
    /// forms (delta-seconds and HTTP-date) — a delay within the worker's sleep
    /// budget is waited exactly (no jitter); a longer one is honored on the
    /// main thread WITHOUT consuming in-worker attempts or the session
    /// auto-retry (bounded honored waits, then the normal ladder). The
    /// deferred wait does NOT outlive its coroutine host [J5]: a destroyed
    /// host kills the flight mid-wait with no finally, and recovery is the
    /// stale-heartbeat reap — the next EnsureTier / TierStatusLine /
    /// RetryAvailable query at least FLIGHT_HEARTBEAT_STALE_SECONDS after the
    /// flight's last tick clears it, and the relaunched flight honors the
    /// REMAINDER of the stored absolute Retry-After deadline (never restarts
    /// the throttle from zero). Capped jittered backoff only when no valid
    /// header (bounded in-worker attempts, then one automatic session retry,
    /// then the manual Retry control), validated caches preserved.
    /// 404/410 and integrity failures FAIL CLOSED: status line + Retry control,
    /// cache untouched, never recreate or overwrite a revision in response.
    ///
    /// THUNDERSTORE builds bundle both trees in the pack zip and never touch
    /// the network; the bundled trees validate through this same manifest
    /// reader [G4].
    ///
    /// Threading: EnsureTier/TierReady/PathFor/Initialize are MAIN-THREAD only
    /// (TierReady reads Time.realtimeSinceStartup). The download worker is a
    /// background thread touching only IO + volatile handoff fields; completion
    /// is a polled main-thread coroutine (the CustomCosmetics
    /// RebuildAfterDownload pattern).
    /// </summary>
    internal static class MusicAssets
    {
        /// <summary>Content revision — bumped ONLY when music bytes change.
        /// SHIP COUPLING: the immutable GitHub release "music-{ASSET_REVISION}"
        /// must exist and verify (scripts/verify_music_release.py) BEFORE any
        /// DLL referencing this constant ships [G3]/[H2].</summary>
        internal const string ASSET_REVISION = "ar1";

        /// <summary>Byte-scannable build probe (impl-r3 K4, the #306 pattern:
        /// a probe must exist for no other purpose). Referenced from the init
        /// log line below so the literal lands in the DLL's UTF-16 #US heap;
        /// pack/release tooling scans the PACKAGED DLL for
        /// "SCR_MUSIC_REVISION=&lt;rev&gt;" to prove the DLL and the bundled/
        /// released payload agree on the revision. Never reuse this string
        /// for anything user-visible.</summary>
        internal const string BUILD_REVISION_MARKER = "SCR_MUSIC_REVISION=" + ASSET_REVISION;

        private const string MARKER_FILE = "installed.json";
        private const string PREVIEWS_ZIP = "music-previews.zip";
        private const string FULL_ZIP = "music.zip";
        // Dedicated immutable release — never /latest/ [F22][G3].
        private const string RELEASE_BASE =
            "https://github.com/SidNDeed/SidsCompetitiveRounds/releases/download/music-" + ASSET_REVISION + "/";

        private const int DOWNLOAD_ATTEMPTS = 4;       // in-worker transient attempts
        private const float READY_TTL_SECONDS = 5f;    // TierReady revalidation throttle
        private const int SAFE_WORKER_WAIT_MS = 60000; // [H2] worker Thread.Sleep ceiling
        private const int MAX_DEFERRED_WAIT_MS = 900000; // 15 min cap on one honored long Retry-After
        private const int MAX_DEFERRED_WAITS = 3;      // honored long waits per tier per session
        // [J5] A live install coroutine stamps its heartbeat every ~1s tick;
        // anything older than this while InFlight means the coroutine host
        // died (or the game was suspended — the generation fence covers the
        // suspended-not-dead case, #367) and the flight is reapable.
        private const float FLIGHT_HEARTBEAT_STALE_SECONDS = 120f;

        // ── Compiled manifest — all 15 files (7 full, 7 previews, cover) [G8] ──

        internal static readonly MusicManifestEntry[] Manifest = BuildManifest();

        private static MusicManifestEntry[] BuildManifest()
        {
            // Track rows derive from MusicCatalog so the two compiled tables can
            // never drift; a future album appended to the catalog joins the
            // manifest (and therefore the NEXT asset revision's zips) for free.
            var list = new List<MusicManifestEntry>();
            foreach (var album in MusicCatalog.Albums)
            {
                foreach (var tr in album.Tracks)
                {
                    list.Add(new MusicManifestEntry { Name = tr.OggFile, Tier = MusicTier.Full, Size = tr.OggSize, Sha256 = tr.OggSha256 });
                    list.Add(new MusicManifestEntry { Name = tr.PreviewFile, Tier = MusicTier.Previews, Size = tr.PreviewSize, Sha256 = tr.PreviewSha256 });
                }
            }
            // Cover art is per-album but MusicAlbumDef (the contract shape)
            // carries no size/hash for it — append the matching cover row here
            // when appending an album. Same provenance as every other value:
            // plugin/music/manifest.json.
            list.Add(new MusicManifestEntry
            {
                Name = "music_album_another_round.png",
                Tier = MusicTier.Previews,
                Size = 132956L,
                Sha256 = "6a6813b96a5fadf60621f912724f53a7fa68fe70c62e33c40cb23f94fda17a9b",
            });
            return list.ToArray();
        }

        // ── Per-tier runtime state ──

        private sealed class TierRuntime
        {
            public MusicTier Tier;
            public bool InFlight;          // main-thread coalescing flag [G2]
            public bool AutoRetryUsed;     // one automatic retry per tier per session
            public bool GaveUp;            // terminal until RetryFailedTier()
            public bool FailedIntegrity;   // flavor for the status line
            public bool MissingWarned;     // THUNDERSTORE: warn once per tier
            public bool DeferredWaiting;   // main thread: honoring a long Retry-After between worker runs
            public int DeferredWaitsUsed;  // bounded honored long waits per session [I13]
            // [J5] Flight liveness + ownership (#367's latch/token pair). The
            // install coroutine stamps the heartbeat on EVERY tick — worker
            // polls, auto-retry waits, and deferred Retry-After waits alike —
            // and every consumer of flight state reaps a stale one via
            // ReapDeadFlight. FlightGen bumps at every launch AND every reap:
            // a coroutine resuming to a bumped gen is superseded and exits
            // without touching the successor's state.
            public volatile float FlightHeartbeatRt;
            public int FlightGen;
            // [J5]/[I13] ABSOLUTE realtime deadline of the last granted long
            // Retry-After. Deliberately survives flight death and reaping so
            // a rehydrated relaunch honors the REMAINDER of the server's
            // window instead of restarting the throttle from zero (or firing
            // a request inside it).
            public float DeferredUntilRt;
            public bool ReadyCache;
            public bool ReadyCacheValid;
            public float ReadyCheckedAt;
        }

        private enum ResultKind { Ok = 0, Transient = 1, FailClosedHttp = 2, FailClosedIntegrity = 3, TransientDeferred = 4 }
        private enum DlOutcome { Ok, Transient, FailClosedHttp, CapExceeded }

        private static readonly TierRuntime _previews = new TierRuntime { Tier = MusicTier.Previews };
        private static readonly TierRuntime _full = new TierRuntime { Tier = MusicTier.Full };
        private static TierRuntime St(MusicTier t) => t == MusicTier.Previews ? _previews : _full;

        private static bool _initialized;
        private static bool _notReadyWarned;
        private static string _musicRoot;   // <dllDir>/music; null = unavailable this session

        private static string TierDirName(MusicTier t) => t == MusicTier.Previews ? "previews" : "full";
        private static string TierDir(MusicTier t) => Path.Combine(_musicRoot, ASSET_REVISION, TierDirName(t));
        private static string TierUrl(MusicTier t) => RELEASE_BASE + (t == MusicTier.Previews ? PREVIEWS_ZIP : FULL_ZIP);

        private static long ExpectedTierBytes(MusicTier t)
        {
            long sum = 0;
            for (int i = 0; i < Manifest.Length; i++)
                if (Manifest[i].Tier == t) sum += Manifest[i].Size;
            return sum;
        }

        // ── Startup ──

        /// <summary>Called from Plugin.DoInitialize AFTER CustomCosmetics and
        /// BEFORE the engine creates any AudioSource — cleanup must never run
        /// while a clip handle is open [H1]. No downloads start here; tiers are
        /// fetched lazily by their triggers (previews: music UI; full:
        /// entitlement / broadcast).</summary>
        internal static void Initialize()
        {
            if (_initialized) return;
            _initialized = true;
            try
            {
                string dllDir = Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
                _musicRoot = Path.Combine(dllDir, "music");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[MUSIC] plugin dir resolve failed: {ex.Message} - music assets unavailable this session");
                _musicRoot = null;
                return;
            }
            try
            {
                if (Directory.Exists(_musicRoot))
                {
                    // 0. Dev-loop repair: CopyToPlugins plants hash-valid trees
                    //    with no marker — attest them before resolution so the
                    //    seat never re-downloads (or quarantines) its own files.
                    TryRepairUnmarkedTier(MusicTier.Previews);
                    TryRepairUnmarkedTier(MusicTier.Full);

                    // 1. Per-tier orphan RESOLUTION [I12]: decide which valid
                    //    copy of each tier survives BEFORE deleting anything. A
                    //    crash between quarantine rename and publication leaves
                    //    the final absent beside a marker-complete staging tree
                    //    — that tree is published here instead of re-downloaded,
                    //    and a quarantine tree is retained until the same-tier
                    //    final validates.
                    int swept = ResolveTierOrphans(MusicTier.Previews)
                              + ResolveTierOrphans(MusicTier.Full);

                    // 2. Residual sweep: orphan dirs matching NEITHER tier name
                    //    carry nothing resolvable; leftover *.tmp files are
                    //    crashed downloads.
                    foreach (var d in Directory.GetDirectories(_musicRoot))
                    {
                        string leaf = Path.GetFileName(d);
                        if (!leaf.StartsWith("staging-", StringComparison.Ordinal) &&
                            !leaf.StartsWith("quarantine-", StringComparison.Ordinal)) continue;
                        if (IsTierOrphanName(leaf)) continue;   // resolved above; survivors are deliberate
                        TryDeleteDir(d);
                        swept++;
                    }
                    foreach (var f in Directory.GetFiles(_musicRoot, "*.tmp"))
                    {
                        TryDeleteFile(f);
                        swept++;
                    }

                    // 3. Final readiness AFTER resolution — publication above can
                    //    have restored a tier the pre-resolution state lacked.
                    bool prevOk = TierReady(MusicTier.Previews);
                    bool fullOk = TierReady(MusicTier.Full);

                    // 4. Stale revision cleanup, per-TIER, keep-until-replaced: a
                    //    stale revision's tier is deleted ONLY after the current
                    //    revision's SAME tier validates; the parent dir goes only
                    //    when empty [H1][G3].
                    int stale = 0;
                    foreach (var d in Directory.GetDirectories(_musicRoot))
                    {
                        string leaf = Path.GetFileName(d);
                        if (string.Equals(leaf, ASSET_REVISION, StringComparison.Ordinal)) continue;
                        if (leaf.StartsWith("staging-", StringComparison.Ordinal) ||
                            leaf.StartsWith("quarantine-", StringComparison.Ordinal)) continue;
                        if (prevOk) TryDeleteDir(Path.Combine(d, TierDirName(MusicTier.Previews)));
                        if (fullOk) TryDeleteDir(Path.Combine(d, TierDirName(MusicTier.Full)));
                        try
                        {
                            if (Directory.Exists(d) && Directory.GetFileSystemEntries(d).Length == 0)
                            {
                                Directory.Delete(d);
                                stale++;
                            }
                        }
                        catch { }
                    }
                    // BUILD_REVISION_MARKER reference is load-bearing: an unreferenced
                    // const is folded away and never reaches the string heap (#306).
                    Plugin.Log?.LogInfo($"[MUSIC] init {BUILD_REVISION_MARKER}: previews={(prevOk ? "ready" : "absent")} full={(fullOk ? "ready" : "absent")} (swept {swept} orphan(s), removed {stale} stale revision dir(s))");
                }
                else
                {
                    Plugin.Log?.LogInfo("[MUSIC] no music dir yet - tiers download on first use");
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[MUSIC] init cleanup failed: {ex.Message}");
            }
#if THUNDERSTORE
            // Bundled installs always carry both trees; absence means a broken
            // install that can never self-heal over the network [G4].
            if (_musicRoot != null && (!TierReady(MusicTier.Previews) || !TierReady(MusicTier.Full)))
                Plugin.Log?.LogWarning("[MUSIC] bundled music trees missing/invalid - reinstall via the mod manager (Thunderstore bundles ship the music)");
#endif
        }

        private static bool IsTierOrphanName(string leaf)
        {
            foreach (var t in new[] { MusicTier.Previews, MusicTier.Full })
            {
                string td = TierDirName(t);
                if (leaf.StartsWith("staging-" + td + "-", StringComparison.Ordinal) ||
                    leaf.StartsWith("quarantine-" + td + "-", StringComparison.Ordinal)) return true;
            }
            return false;
        }

        /// <summary>[I12] Init-time orphan resolution for one tier: decide which
        /// valid copy survives FIRST, delete only what that decision makes
        /// redundant. When the final tree does not validate, a validated orphan
        /// copy (completed staging first — newest bytes by protocol — then a
        /// quarantine that still validates) is PUBLISHED in its place, so a
        /// crash between quarantine rename and publication never costs a
        /// re-download. Quarantine trees are retained until the same-tier final
        /// validates; a staging tree survives only while it is the sole valid
        /// copy. Main thread (TierReady), runs in BOTH build variants — local
        /// recovery needs no network. Returns orphan dirs deleted.</summary>
        private static int ResolveTierOrphans(MusicTier t)
        {
            int removed = 0;
            try
            {
                string stagingPrefix = "staging-" + TierDirName(t) + "-";
                string quarantinePrefix = "quarantine-" + TierDirName(t) + "-";
                var stagingDirs = new List<string>();
                var quarantineDirs = new List<string>();
                foreach (var d in Directory.GetDirectories(_musicRoot))
                {
                    string leaf = Path.GetFileName(d);
                    if (leaf.StartsWith(stagingPrefix, StringComparison.Ordinal)) stagingDirs.Add(d);
                    else if (leaf.StartsWith(quarantinePrefix, StringComparison.Ordinal)) quarantineDirs.Add(d);
                }
                var s = St(t);
                s.ReadyCacheValid = false;
                bool finalOk = TierReady(t);
                if (!finalOk && (stagingDirs.Count > 0 || quarantineDirs.Count > 0))
                {
                    var candidates = new List<string>(stagingDirs.Count + quarantineDirs.Count);
                    candidates.AddRange(stagingDirs);
                    candidates.AddRange(quarantineDirs);
                    foreach (var cand in candidates)
                    {
                        if (!Directory.Exists(cand) || !ValidateTierTree(cand, t)) continue;
                        if (PublishOrphan(cand, t, quarantineDirs)) { finalOk = true; break; }
                    }
                }
                foreach (var d in stagingDirs)
                {
                    if (!Directory.Exists(d)) continue;               // consumed by publication
                    if (!finalOk && ValidateTierTree(d, t)) continue; // sole valid copy — keep
                    TryDeleteDir(d);
                    removed++;
                }
                foreach (var d in quarantineDirs)
                {
                    if (!finalOk) break;                              // retained until the final validates
                    if (!Directory.Exists(d)) continue;
                    TryDeleteDir(d);
                    removed++;
                }
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[MUSIC] orphan resolution failed for {TierDirName(t)}: {ex.Message}");
            }
            return removed;
        }

        /// <summary>Move a validated orphan tree into the final tier position,
        /// quarantining a present-but-invalid final first (the new quarantine
        /// joins this pass's retention/deletion decision via the list). True
        /// only when the published tree revalidates in place.</summary>
        private static bool PublishOrphan(string cand, MusicTier t, List<string> quarantineDirs)
        {
            try
            {
                string final = TierDir(t);
                Directory.CreateDirectory(Path.Combine(_musicRoot, ASSET_REVISION));
                if (Directory.Exists(final))
                {
                    string q = Path.Combine(_musicRoot, "quarantine-" + TierDirName(t) + "-" + Guid.NewGuid().ToString("N"));
                    Directory.Move(final, q);
                    quarantineDirs.Add(q);
                }
                Directory.Move(cand, final);
                var s = St(t);
                s.ReadyCacheValid = false;
                bool ok = TierReady(t);
                Plugin.Log?.LogInfo(ok
                    ? $"[MUSIC] published recovered {TierDirName(t)} tree from '{Path.GetFileName(cand)}' - no re-download needed"
                    : $"[MUSIC] recovered {TierDirName(t)} tree from '{Path.GetFileName(cand)}' failed revalidation after publish");
                return ok;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[MUSIC] publish of recovered {TierDirName(t)} tree failed: {ex.Message}");
                return false;
            }
        }

        // ── Readiness / lookup ──

        /// <summary>Cheap readiness check (marker content + per-file sizes; the
        /// full hash check ran at install/pack time). Result cached for
        /// READY_TTL_SECONDS so per-frame UI queries stay off the disk.
        /// Main-thread only.</summary>
        internal static bool TierReady(MusicTier t)
        {
            if (_musicRoot == null) return false;
            var s = St(t);
            float now = Time.realtimeSinceStartup;
            if (s.ReadyCacheValid && now - s.ReadyCheckedAt < READY_TTL_SECONDS) return s.ReadyCache;
            bool ok = ValidateTierTree(TierDir(t), t);
            s.ReadyCache = ok;
            s.ReadyCheckedAt = now;
            s.ReadyCacheValid = true;
            if (ok)
            {
                // A tree that validates clears any failure latch — covers a dev
                // hand-copy landing mid-session after a failed download.
                s.GaveUp = false;
                s.FailedIntegrity = false;
            }
            return ok;
        }

        /// <summary>Absolute path of a manifest file inside its tier tree, or
        /// null when the name is unknown or its tier is not installed.</summary>
        internal static string PathFor(string fileName)
        {
            if (string.IsNullOrEmpty(fileName) || _musicRoot == null) return null;
            for (int i = 0; i < Manifest.Length; i++)
            {
                var e = Manifest[i];
                if (!string.Equals(e.Name, fileName, StringComparison.Ordinal)) continue;
                if (!TierReady(e.Tier)) return null;
                return Path.Combine(TierDir(e.Tier), fileName);
            }
            return null;
        }

        // ── Ensure / retry ──

        /// <summary>[J5] Flight liveness reap. A destroyed coroutine host
        /// kills the install coroutine with NO finally, which used to strand
        /// InFlight as a permanent coalescer (EnsureTier no-oped forever,
        /// GaveUp never set, Retry never shown). Instead every consumer of
        /// flight state — EnsureTier's coalesce check, TierStatusLine, and
        /// RetryAvailable — calls this first: a heartbeat older than
        /// FLIGHT_HEARTBEAT_STALE_SECONDS while InFlight means the flight is
        /// dead; clear the flight flags, bump the generation (a merely
        /// SUSPENDED coroutine — backgrounded game, realtime kept advancing —
        /// resumes to the bumped gen and exits silently instead of racing its
        /// successor, #367), and let the normal trigger/Retry path relaunch.
        /// DeferredUntilRt deliberately survives the reap so the relaunch
        /// honors the remaining Retry-After window. Recovery is QUERY-driven,
        /// not timer-driven: it happens at the next call into one of those
        /// surfaces after the staleness bound, not the instant the host dies.
        /// Logs once per death (clearing InFlight makes the condition
        /// unrepeatable for that flight). Main-thread only (realtime read);
        /// a no-op in THUNDERSTORE builds, where InFlight is never set.</summary>
        private static void ReapDeadFlight(TierRuntime s, string where)
        {
            if (!s.InFlight) return;
            if (Time.realtimeSinceStartup - s.FlightHeartbeatRt <= FLIGHT_HEARTBEAT_STALE_SECONDS) return;
            s.FlightGen++;          // supersede a suspended-not-dead coroutine (#367)
            s.InFlight = false;
            s.DeferredWaiting = false;
            Plugin.Log?.LogWarning($"[MUSIC] {TierDirName(s.Tier)} install flight heartbeat stale (>{(int)FLIGHT_HEARTBEAT_STALE_SECONDS}s - coroutine host destroyed?) - cleared via {where}; normal trigger/Retry relaunches (Retry-After deadline preserved)");
        }

        /// <summary>Idempotent tier bootstrap — no-op when ready, in a LIVE
        /// flight (a flight whose heartbeat went stale is reaped first, [J5]),
        /// or gave up (manual Retry owns that state). Main-thread only; the
        /// InFlight flag is the per-tier coalescer [G2]. Triggers (design §3):
        /// previews on first music UI render, full on entitlement/broadcast.</summary>
        internal static void EnsureTier(MusicTier t, string reason)
        {
            var s = St(t);
            if (_musicRoot == null)
            {
                if (!_notReadyWarned)
                {
                    _notReadyWarned = true;
                    Plugin.Log?.LogWarning($"[MUSIC] EnsureTier({TierDirName(t)}) before init / after failed init (reason {reason}) - ignored");
                }
                return;
            }
            if (TierReady(t)) return;
#if THUNDERSTORE
            // Never touch the network: the pack zip bundles both trees; a
            // missing/invalid one is surfaced once and left alone [G4].
            if (!s.MissingWarned)
            {
                s.MissingWarned = true;
                Plugin.Log?.LogWarning($"[MUSIC] {TierDirName(t)} assets missing/invalid (reason {reason}) - reinstall via the mod manager (Thunderstore bundles ship the music)");
            }
#else
            ReapDeadFlight(s, "EnsureTier");   // [J5] a dead flight must not coalesce forever
            if (s.InFlight || s.GaveUp) return;
            if (Plugin.Instance == null)
            {
                Plugin.Log?.LogWarning($"[MUSIC] EnsureTier({TierDirName(t)}) has no coroutine host yet (reason {reason}) - ignored");
                return;
            }
            s.InFlight = true;
            // [J5] Stamp before launch so the pre-first-tick window can never
            // read as stale; the gen is this flight's ownership token (#367).
            s.FlightHeartbeatRt = Time.realtimeSinceStartup;
            int gen = ++s.FlightGen;
            Plugin.Log?.LogInfo($"[MUSIC] ensure {TierDirName(t)} (reason {reason}) - downloading {TierUrl(t)}");
            // A throw here must not strand the coalescing latch (#367): no
            // coroutine means nothing would ever clear InFlight.
            try { Plugin.Instance.StartCoroutine(RunTierInstall(s, gen)); }
            catch (Exception ex)
            {
                s.InFlight = false;
                Plugin.Log?.LogWarning($"[MUSIC] EnsureTier({TierDirName(t)}) coroutine start failed: {ex.Message}");
            }
#endif
        }

        /// <summary>True when a tier exhausted its automatic attempts and waits
        /// on the Music tab's manual Retry control. Always false in
        /// THUNDERSTORE builds (GaveUp is never set there). Reaps dead
        /// flights first [J5] — a stranded InFlight would otherwise pin this
        /// false (and the status line on "Downloading...") forever.</summary>
        internal static bool RetryAvailable
        {
            get
            {
                ReapDeadFlight(_previews, "RetryAvailable");
                ReapDeadFlight(_full, "RetryAvailable");
                return (_previews.GaveUp && !_previews.InFlight) || (_full.GaveUp && !_full.InFlight);
            }
        }

        /// <summary>Manual retry for every gave-up tier — one fresh attempt per
        /// press (the session's automatic retry stays consumed).</summary>
        internal static void RetryFailedTier()
        {
            RetryOne(_previews);
            RetryOne(_full);
        }

        private static void RetryOne(TierRuntime s)
        {
            if (!s.GaveUp || s.InFlight) return;
            s.GaveUp = false;
            s.FailedIntegrity = false;
            s.ReadyCacheValid = false;
            EnsureTier(s.Tier, "manual-retry");
        }

        /// <summary>One localized line for the Music tab; "" when nothing needs
        /// saying (ready, or simply not yet triggered).</summary>
        internal static string TierStatusLine()
        {
#if THUNDERSTORE
            if (_musicRoot != null && (!TierReady(MusicTier.Previews) || !TierReady(MusicTier.Full)))
                return I18n.Tr("Music files are missing - reinstall the mod through your mod manager");
            return "";
#else
            var p = _previews;
            var f = _full;
            ReapDeadFlight(p, "TierStatusLine");   // [J5] never render a dead
            ReapDeadFlight(f, "TierStatusLine");   // flight as "Downloading..."
            if (p.DeferredWaiting || f.DeferredWaiting)
                return I18n.Tr("Music download is rate-limited - waiting to retry");
            if (p.InFlight && f.InFlight) return I18n.Tr("Downloading music...");
            if (p.InFlight) return I18n.Tr("Downloading music previews...");
            if (f.InFlight) return I18n.Tr("Downloading full album...");
            if (p.GaveUp || f.GaveUp)
                return (p.FailedIntegrity || f.FailedIntegrity)
                    ? I18n.Tr("Music files failed verification - press Retry")
                    : I18n.Tr("Music download failed - press Retry");
            return "";
#endif
        }

#if !THUNDERSTORE
        // ── Install pipeline (standalone builds only) ──

        /// <summary>Per-worker-run handoff (worker thread → polling coroutine).
        /// A fresh box per run — never fields shared on TierRuntime — so a
        /// worker thread orphaned by host destruction writes only into its own
        /// box: it can neither satisfy nor clobber a rehydrated successor
        /// flight's completion ([J5], #367's capture-handles-as-locals half).</summary>
        private sealed class WorkerBox
        {
            public volatile bool Done;
            public volatile int Result;        // (int)ResultKind
            public volatile int RetryAfterMs;  // server delay past the sleep budget
        }

        /// <summary>[J5] Flight lifetime, stated honestly: this coroutine dies
        /// with its host and runs NO finally when it does — every wait below
        /// (worker poll, deferred Retry-After, auto-retry) therefore ticks at
        /// ~1s, stamping the heartbeat and checking the ownership gen. Death
        /// recovery is the consumers' stale-heartbeat reap (ReapDeadFlight),
        /// bounded at FLIGHT_HEARTBEAT_STALE_SECONDS past the last tick plus
        /// however long until the next EnsureTier/TierStatusLine/RetryAvailable
        /// query; the relaunch then resumes any outstanding Retry-After window
        /// from its ABSOLUTE deadline rather than from zero.</summary>
        private static IEnumerator RunTierInstall(TierRuntime s, int myGen)
        {
            for (; ; )
            {
                // [J5]/[I13] Honor any outstanding absolute Retry-After
                // deadline BEFORE contacting the server. DeferredUntilRt is
                // set by this flight's own deferral grant below OR by a
                // predecessor flight whose host died mid-wait — a rehydrated
                // relaunch waits out the REMAINDER of the server's window
                // (never restarts the throttle from zero, never fires a
                // request inside it).
                if (Time.realtimeSinceStartup < s.DeferredUntilRt)
                {
                    s.DeferredWaiting = true;
                    while (Time.realtimeSinceStartup < s.DeferredUntilRt)
                    {
                        s.FlightHeartbeatRt = Time.realtimeSinceStartup;
                        yield return new WaitForSecondsRealtime(1f);
                        if (s.FlightGen != myGen) yield break;   // superseded — successor owns all flight state (#367)
                    }
                    s.DeferredWaiting = false;
                }
                var box = new WorkerBox();
                var th = new Thread(() => InstallWorker(s.Tier, box))
                {
                    IsBackground = true,
                    Name = "CR_MusicDownload_" + TierDirName(s.Tier),
                };
                th.Start();
                while (!box.Done)
                {
                    s.FlightHeartbeatRt = Time.realtimeSinceStartup;
                    yield return new WaitForSecondsRealtime(1f);
                    if (s.FlightGen != myGen) yield break;
                }
                s.ReadyCacheValid = false;
                if (TierReady(s.Tier))
                {
                    // Post-publication validation is the authority, not the
                    // worker's own result code.
                    s.InFlight = false;
                    s.FailedIntegrity = false;
                    Plugin.Log?.LogInfo($"[MUSIC] {TierDirName(s.Tier)} tier installed and validated");
                    try { NativeUI.MarkDirty(); } catch { }
                    try { MusicEngine.Reconcile("music-tier-ready"); }
                    catch (Exception ex) { Plugin.Log?.LogWarning($"[MUSIC] post-install reconcile failed: {ex.Message}"); }
                    yield break;
                }
                var kind = (ResultKind)box.Result;
                if (kind == ResultKind.TransientDeferred && s.DeferredWaitsUsed < MAX_DEFERRED_WAITS)
                {
                    // [I13] The server named a wait past the worker's sleep
                    // budget. Honored at the loop top WITHOUT consuming the
                    // in-worker attempt budget or the session auto-retry; the
                    // cycle cap keeps a perpetually throttling server from
                    // parking the tier in-flight forever — it degrades to the
                    // normal transient ladder (auto-retry, then manual Retry).
                    // Stored as an ABSOLUTE realtime deadline so the wait
                    // outlives this coroutine [J5]: if the host dies mid-wait
                    // the stale-heartbeat reap frees the flight and the
                    // relaunch resumes this same window at the loop top.
                    s.DeferredWaitsUsed++;
                    int deferMs = Math.Min(box.RetryAfterMs, MAX_DEFERRED_WAIT_MS);
                    s.DeferredUntilRt = Time.realtimeSinceStartup + deferMs / 1000f;
                    Plugin.Log?.LogInfo($"[MUSIC] {TierDirName(s.Tier)} download throttled (Retry-After {box.RetryAfterMs / 1000}s) - honoring {deferMs / 1000}s before the next attempt (attempts preserved)");
                    try { NativeUI.MarkDirty(); } catch { }
                    continue;   // loop top marks DeferredWaiting and waits it out (same frame — continue does not yield)
                }
                if ((kind == ResultKind.Transient || kind == ResultKind.TransientDeferred) && !s.AutoRetryUsed)
                {
                    s.AutoRetryUsed = true;
                    Plugin.Log?.LogInfo($"[MUSIC] {TierDirName(s.Tier)} download failed (transient) - one automatic retry in 5s");
                    float retryAt = Time.realtimeSinceStartup + 5f;
                    while (Time.realtimeSinceStartup < retryAt)
                    {
                        s.FlightHeartbeatRt = Time.realtimeSinceStartup;
                        yield return new WaitForSecondsRealtime(1f);
                        if (s.FlightGen != myGen) yield break;
                    }
                    continue;
                }
                s.InFlight = false;
                s.GaveUp = true;
                s.FailedIntegrity = kind == ResultKind.FailClosedIntegrity;
                Plugin.Log?.LogWarning($"[MUSIC] {TierDirName(s.Tier)} tier install failed ({kind}) - manual Retry available in the Music tab");
                try { NativeUI.MarkDirty(); } catch { }
                try { MusicEngine.Reconcile("music-tier-failed"); } catch { }
                yield break;
            }
        }

        private static void InstallWorker(MusicTier t, WorkerBox box)
        {
            int result = (int)ResultKind.Transient;
            string tmpZip = null;
            try
            {
                Directory.CreateDirectory(_musicRoot);
                tmpZip = Path.Combine(_musicRoot, "download-" + TierDirName(t) + "-" + Guid.NewGuid().ToString("N") + ".zip.tmp");
                result = (int)InstallWorkerCore(t, box, tmpZip);
            }
            catch (Exception ex)
            {
                // Includes ZipArchive throws on a corrupt/truncated download —
                // deliberately TRANSIENT, not fail-closed: a truncated transfer
                // and a corrupt source are indistinguishable here, retries are
                // bounded either way, and the cache is untouched either way.
                Plugin.Log?.LogWarning($"[MUSIC] {TierDirName(t)} install worker failed: {ex.Message}");
            }
            finally
            {
                TryDeleteFile(tmpZip);
                box.Result = result;
                box.Done = true;
            }
        }

        private static ResultKind InstallWorkerCore(MusicTier t, WorkerBox box, string tmpZip)
        {
            // ── download, with the [H2] transient policy in-worker ──
            var rng = new System.Random();
            for (int attempt = 1; ; attempt++)
            {
                var oc = DownloadWithCap(TierUrl(t), tmpZip, 2L * ExpectedTierBytes(t), out int retryAfterMs);
                if (oc == DlOutcome.Ok) break;
                if (oc == DlOutcome.FailClosedHttp) return ResultKind.FailClosedHttp;
                if (oc == DlOutcome.CapExceeded) return ResultKind.FailClosedIntegrity;
                if (retryAfterMs > SAFE_WORKER_WAIT_MS)
                {
                    // [I13] Longer than this thread may sleep — hand the delay
                    // to the coroutine so it is honored without burning the
                    // remaining attempts inside a throttle window they cannot
                    // outlast.
                    box.RetryAfterMs = retryAfterMs;
                    return ResultKind.TransientDeferred;
                }
                if (attempt >= DOWNLOAD_ATTEMPTS) return ResultKind.Transient;
                // [I13] A valid Retry-After (either RFC 7231 form) is waited
                // exactly; capped jitter only when no valid header (-1).
                int waitMs = retryAfterMs >= 0
                    ? retryAfterMs
                    : Math.Min(30000, (1000 << attempt) + rng.Next(0, 1000));
                Plugin.Log?.LogInfo($"[MUSIC] {TierDirName(t)} download attempt {attempt} failed (transient) - retrying in {waitMs}ms");
                Thread.Sleep(waitMs);
            }

            // ── verify+extract into staging; marker LAST; one atomic rename [H1] ──
            string staging = Path.Combine(_musicRoot, "staging-" + TierDirName(t) + "-" + Guid.NewGuid().ToString("N"));
            try
            {
                if (!ExtractAndVerify(tmpZip, t, staging)) return ResultKind.FailClosedIntegrity;
                WriteMarker(staging, t);
                return PublishStaging(ref staging, t) ? ResultKind.Ok : ResultKind.FailClosedIntegrity;
            }
            finally
            {
                if (staging != null) TryDeleteDir(staging);  // no-op when consumed by the rename
            }
        }

        private static DlOutcome DownloadWithCap(string url, string tmpPath, long capBytes, out int retryAfterMs)
        {
            retryAfterMs = -1;   // -1 = no valid Retry-After; >= 0 = the server's delay
            bool capHit = false;
            try
            {
                // #194: ServicePointManager governs HttpWebRequest/WebClient (and
                // nothing else) — same TLS1.2 opt-in as the cosmetics bootstrap.
                try { System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12; } catch { }
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);
                req.UserAgent = "CompetitiveRounds-Mod/" + Plugin.ModVersion;
                using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
                using (var rs = resp.GetResponseStream())
                using (var os = File.Create(tmpPath))
                {
                    var buf = new byte[81920];
                    long total = 0;
                    int r;
                    while ((r = rs.Read(buf, 0, buf.Length)) > 0)
                    {
                        total += r;
                        // Streaming cap from COMPILED sizes — Content-Length is
                        // attacker/CDN-controlled and never consulted [G9].
                        if (total > capBytes) { capHit = true; break; }
                        os.Write(buf, 0, r);
                    }
                }
                if (capHit)
                {
                    TryDeleteFile(tmpPath);
                    Plugin.Log?.LogWarning($"[MUSIC] download exceeded the compiled size cap ({capBytes} bytes) - aborted");
                    return DlOutcome.CapExceeded;
                }
                return DlOutcome.Ok;
            }
            catch (System.Net.WebException wex)
            {
                TryDeleteFile(tmpPath);
                var resp = wex.Response as System.Net.HttpWebResponse;
                if (resp != null)
                {
                    int code = (int)resp.StatusCode;
                    retryAfterMs = ParseRetryAfterMs(resp);
                    try { resp.Close(); } catch { }
                    if (code == 404 || code == 410)
                    {
                        // [H2] The immutable release is absent — fail closed,
                        // never hammer, never touch the cache.
                        Plugin.Log?.LogWarning($"[MUSIC] HTTP {code} for {url} - failing closed (asset release missing?)");
                        return DlOutcome.FailClosedHttp;
                    }
                    Plugin.Log?.LogWarning($"[MUSIC] HTTP {code} for {url} - transient");
                    return DlOutcome.Transient;
                }
                Plugin.Log?.LogWarning($"[MUSIC] download failed ({wex.Status}) - transient");
                return DlOutcome.Transient;
            }
            catch (Exception ex)
            {
                TryDeleteFile(tmpPath);
                Plugin.Log?.LogWarning($"[MUSIC] download failed: {ex.Message} - transient");
                return DlOutcome.Transient;
            }
        }

        /// <summary>[I13] Both RFC 7231 Retry-After forms. -1 = absent/invalid
        /// (caller may jitter); >= 0 = the server's requested delay in ms
        /// (0 = retry immediately). Delta-seconds are unsigned digits only;
        /// an HTTP-date in the past means no further delay.</summary>
        private static int ParseRetryAfterMs(System.Net.HttpWebResponse resp)
        {
            try
            {
                string h = resp.Headers?["Retry-After"];
                if (string.IsNullOrEmpty(h)) return -1;
                h = h.Trim();
                if (int.TryParse(h, System.Globalization.NumberStyles.None,
                        System.Globalization.CultureInfo.InvariantCulture, out int sec))
                    return sec > int.MaxValue / 1000 ? int.MaxValue : sec * 1000;
                if (DateTimeOffset.TryParse(h, System.Globalization.CultureInfo.InvariantCulture,
                        System.Globalization.DateTimeStyles.AssumeUniversal, out var when))
                {
                    double ms = (when - DateTimeOffset.UtcNow).TotalMilliseconds;
                    if (ms <= 0) return 0;
                    return ms >= int.MaxValue ? int.MaxValue : (int)ms;
                }
            }
            catch { }
            return -1;
        }

        /// <summary>Verify every zip entry against the compiled manifest for the
        /// tier while extracting into the staging dir: exact expected-name set
        /// (unknown/duplicate reject), declared AND actual per-entry size,
        /// SHA-256, total uncompressed ceiling [G8][G9].</summary>
        private static bool ExtractAndVerify(string tmpZip, MusicTier t, string staging)
        {
            var expected = new Dictionary<string, MusicManifestEntry>(StringComparer.Ordinal);
            long ceiling = 0;
            for (int i = 0; i < Manifest.Length; i++)
            {
                var e = Manifest[i];
                if (e.Tier != t) continue;
                expected[e.Name] = e;
                ceiling += e.Size;
            }
            Directory.CreateDirectory(staging);
            var seen = new HashSet<string>(StringComparer.Ordinal);
            long total = 0;
            using (var fs = File.OpenRead(tmpZip))
            using (var zip = new ZipArchive(fs, ZipArchiveMode.Read))
            {
                foreach (var entry in zip.Entries)
                {
                    // FullName, deliberately: the release zips are FLAT, so any
                    // directory prefix (or directory entry) is an unknown name.
                    string n = entry.FullName;
                    if (!expected.TryGetValue(n, out var man))
                    {
                        Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: unknown entry '{n}'");
                        return false;
                    }
                    if (!seen.Add(n))
                    {
                        Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: duplicate entry '{n}'");
                        return false;
                    }
                    if (entry.Length != man.Size)
                    {
                        Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: '{n}' declares {entry.Length} bytes, manifest says {man.Size}");
                        return false;
                    }
                    long written = 0;
                    using (var es = entry.Open())
                    using (var sha = SHA256.Create())
                    using (var os = File.Create(Path.Combine(staging, n)))
                    {
                        var buf = new byte[81920];
                        int r;
                        while ((r = es.Read(buf, 0, buf.Length)) > 0)
                        {
                            written += r;
                            if (written > man.Size)
                            {
                                Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: '{n}' overflows its declared size");
                                return false;
                            }
                            os.Write(buf, 0, r);
                            sha.TransformBlock(buf, 0, r, null, 0);
                        }
                        sha.TransformFinalBlock(buf, 0, 0);
                        if (written != man.Size)
                        {
                            Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: '{n}' short ({written}/{man.Size} bytes)");
                            return false;
                        }
                        string hex = ToHex(sha.Hash);
                        if (!string.Equals(hex, man.Sha256, StringComparison.OrdinalIgnoreCase))
                        {
                            Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: '{n}' SHA-256 mismatch");
                            return false;
                        }
                    }
                    total += written;
                    if (total > ceiling)
                    {
                        Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: total bytes exceed the manifest ceiling");
                        return false;
                    }
                }
            }
            if (seen.Count != expected.Count)
            {
                Plugin.Log?.LogWarning($"[MUSIC] reject {TierDirName(t)} zip: {expected.Count - seen.Count} expected entr(ies) missing");
                return false;
            }
            return true;
        }

        /// <summary>[H1] Publication: quarantine an invalid pre-existing final
        /// tree, then ONE atomic same-volume rename; the quarantine is deleted
        /// only after the new final tree revalidates. Sets staging to null when
        /// the rename consumed it. Worker thread (pure IO).</summary>
        private static bool PublishStaging(ref string staging, MusicTier t)
        {
            string final = TierDir(t);
            Directory.CreateDirectory(Path.Combine(_musicRoot, ASSET_REVISION));
            string quarantine = null;
            if (Directory.Exists(final))
            {
                if (ValidateTierTree(final, t))
                {
                    // A valid tree appeared while we were downloading (dev copy,
                    // another process) — keep it, discard the redundant staging.
                    return true;
                }
                quarantine = Path.Combine(_musicRoot, "quarantine-" + TierDirName(t) + "-" + Guid.NewGuid().ToString("N"));
                Directory.Move(final, quarantine);
            }
            Directory.Move(staging, final);   // THE publication
            staging = null;
            bool ok = ValidateTierTree(final, t);
            if (ok && quarantine != null) TryDeleteDir(quarantine);
            return ok;
        }

#endif

        /// <summary>Ready marker, written LAST inside the staging dir (download
        /// path) or in place by the unmarked-tree repair below. Format (the
        /// Thunderstore pack tooling must emit the same fields; whitespace
        /// and file order are free — the reader parses, it does not byte-compare):
        /// {"revision":"ar1","tier":"previews","files":[{"name":"...","size":N,"sha256":"..."}]}</summary>
        private static void WriteMarker(string dir, MusicTier t)
        {
            var sb = new StringBuilder();
            sb.Append("{\"revision\":\"").Append(ASSET_REVISION)
              .Append("\",\"tier\":\"").Append(TierDirName(t))
              .Append("\",\"files\":[");
            bool first = true;
            for (int i = 0; i < Manifest.Length; i++)
            {
                var e = Manifest[i];
                if (e.Tier != t) continue;
                if (!first) sb.Append(',');
                first = false;
                sb.Append("{\"name\":\"").Append(e.Name)
                  .Append("\",\"size\":").Append(e.Size)
                  .Append(",\"sha256\":\"").Append(e.Sha256).Append("\"}");
            }
            sb.Append("]}");
            File.WriteAllText(Path.Combine(dir, MARKER_FILE), sb.ToString());
        }

        /// <summary>Dev-loop / pack-source repair: a final tier tree whose
        /// ACTUAL contents are exactly the expected tier files (no extras,
        /// subdirectories, or reparse points) and whose files all match the
        /// compiled manifest (size + full SHA-256) but which carries no ready
        /// marker gets the marker written in place. This is how CopyToPlugins
        /// dev trees become valid — the csproj deliberately emits no marker
        /// because the format is owned HERE, and a hand-rolled MSBuild marker
        /// that drifted would read as an invalid tree (quarantine risk).
        /// Verifying first preserves the marker's integrity guarantee: we only
        /// ever attest a tree we verified COMPLETELY [I15].</summary>
        private static void TryRepairUnmarkedTier(MusicTier t)
        {
            try
            {
                string dir = TierDir(t);
                if (!Directory.Exists(dir)) return;
                if (File.Exists(Path.Combine(dir, MARKER_FILE))) return;
                if (!TreeEntriesExact(dir, t, expectMarker: false)) return;
                using (var sha = System.Security.Cryptography.SHA256.Create())
                {
                    for (int i = 0; i < Manifest.Length; i++)
                    {
                        var e = Manifest[i];
                        if (e.Tier != t) continue;
                        var fi = new FileInfo(Path.Combine(dir, e.Name));
                        if (!fi.Exists || fi.Length != e.Size) return;
                        byte[] h;
                        using (var fs = File.OpenRead(fi.FullName)) h = sha.ComputeHash(fs);
                        if (!string.Equals(ToHex(h), e.Sha256, StringComparison.OrdinalIgnoreCase)) return;
                    }
                }
                WriteMarker(dir, t);
                Plugin.Log?.LogInfo($"[MUSIC] wrote missing ready marker for hash-valid {TierDirName(t)} tree (dev/pack source)");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[MUSIC] unmarked-tier repair failed for {TierDirName(t)}: {ex.Message}");
            }
        }

        // ── Manifest reader (shared by standalone installs and Thunderstore
        //    bundles — the SAME validation path for both [G4]) ──

        /// <summary>Marker CONTENT validation, not just presence: revision +
        /// tier + the exact per-file name/size/sha set must equal the COMPILED
        /// manifest, every file must exist with the exact byte length, and the
        /// directory's ACTUAL entries must be exactly those files + the marker
        /// (extras, subdirectories, and reparse points reject) [I15]. A marker
        /// from a different manifest generation therefore never validates. No
        /// hashing here (contract: full hashes at install/pack time only).
        /// Safe from any thread — pure IO.</summary>
        private static bool ValidateTierTree(string dir, MusicTier t)
        {
            try
            {
                if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
                string markerPath = Path.Combine(dir, MARKER_FILE);
                if (!File.Exists(markerPath)) return false;
                if (!TreeEntriesExact(dir, t, expectMarker: true)) return false;
                string json;
                try { json = File.ReadAllText(markerPath); }
                catch { return false; }
                if (!TryParseMarker(json, out string rev, out string tier, out var files)) return false;
                if (!string.Equals(rev, ASSET_REVISION, StringComparison.Ordinal)) return false;
                if (!string.Equals(tier, TierDirName(t), StringComparison.Ordinal)) return false;
                int expectedCount = 0;
                for (int i = 0; i < Manifest.Length; i++)
                {
                    var e = Manifest[i];
                    if (e.Tier != t) continue;
                    expectedCount++;
                    if (!files.TryGetValue(e.Name, out var m)) return false;
                    if (m.size != e.Size) return false;
                    if (!string.Equals(m.sha, e.Sha256, StringComparison.OrdinalIgnoreCase)) return false;
                    var fi = new FileInfo(Path.Combine(dir, e.Name));
                    if (!fi.Exists || fi.Length != e.Size) return false;
                }
                if (files.Count != expectedCount) return false;   // no extras
                return true;
            }
            catch { return false; }
        }

        /// <summary>[I15] The exact-tree gate shared by marker repair and marker
        /// validation: the directory's ACTUAL entries must be exactly the
        /// tier's expected regular files (plus installed.json when
        /// expectMarker) — any subdirectory, reparse point (symlink/junction),
        /// or extra file rejects, so a marker never attests a tree it does not
        /// fully describe. Throws propagate to the callers' catch-alls
        /// (both fail closed).</summary>
        private static bool TreeEntriesExact(string dir, MusicTier t, bool expectMarker)
        {
            var allowed = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < Manifest.Length; i++)
                if (Manifest[i].Tier == t) allowed.Add(Manifest[i].Name);
            if (expectMarker) allowed.Add(MARKER_FILE);
            int seen = 0;
            foreach (var path in Directory.GetFileSystemEntries(dir))
            {
                var attrs = File.GetAttributes(path);
                if ((attrs & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0) return false;
                if (!allowed.Contains(Path.GetFileName(path))) return false;
                seen++;
            }
            // Names within one directory are unique and each counted entry is a
            // distinct allowed regular file, so count equality = set equality.
            return seen == allowed.Count;
        }

        private static bool TryParseMarker(string json, out string revision, out string tier,
            out Dictionary<string, (long size, string sha)> files)
        {
            revision = null;
            tier = null;
            files = null;
            if (string.IsNullOrEmpty(json)) return false;
            revision = ExtractJsonString(json, "revision");
            tier = ExtractJsonString(json, "tier");
            if (revision == null || tier == null) return false;
            int fi = json.IndexOf("\"files\"", StringComparison.Ordinal);
            if (fi < 0) return false;
            int lb = json.IndexOf('[', fi);
            if (lb < 0) return false;
            // Plain depth counting is safe HERE and only here: every string value
            // is a compiled filename or hex digest — no braces/brackets can occur
            // inside them (#156's carve-out for non-user-authored content). A
            // corrupted marker that confuses the scan just fails validation,
            // which is the correct outcome.
            var dict = new Dictionary<string, (long, string)>(StringComparer.Ordinal);
            int depth = 0, objStart = -1;
            for (int i = lb + 1; i < json.Length; i++)
            {
                char c = json[i];
                if (c == '{')
                {
                    if (depth == 0) objStart = i;
                    depth++;
                }
                else if (c == '}')
                {
                    depth--;
                    if (depth == 0 && objStart >= 0)
                    {
                        string obj = json.Substring(objStart, i - objStart + 1);
                        string name = ExtractJsonString(obj, "name");
                        string sha = ExtractJsonString(obj, "sha256");
                        long size = ExtractJsonLong(obj, "size");
                        if (name == null || sha == null || size < 0) return false;
                        if (dict.ContainsKey(name)) return false;   // duplicate row
                        dict[name] = (size, sha);
                        objStart = -1;
                    }
                }
                else if (c == ']' && depth == 0)
                {
                    break;
                }
            }
            files = dict;
            return true;
        }

        private static string ExtractJsonString(string src, string key)
        {
            int k = src.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
            if (k < 0) return null;
            int colon = src.IndexOf(':', k + key.Length + 2);
            if (colon < 0) return null;
            int q1 = src.IndexOf('"', colon + 1);
            if (q1 < 0) return null;
            int q2 = src.IndexOf('"', q1 + 1);
            if (q2 < 0) return null;
            return src.Substring(q1 + 1, q2 - q1 - 1);
        }

        private static long ExtractJsonLong(string src, string key)
        {
            int k = src.IndexOf("\"" + key + "\"", StringComparison.Ordinal);
            if (k < 0) return -1;
            int colon = src.IndexOf(':', k + key.Length + 2);
            if (colon < 0) return -1;
            int i = colon + 1;
            while (i < src.Length && (src[i] == ' ' || src[i] == '\t')) i++;
            long v = 0;
            bool any = false;
            while (i < src.Length && src[i] >= '0' && src[i] <= '9')
            {
                v = v * 10 + (src[i] - '0');
                any = true;
                i++;
            }
            return any ? v : -1;
        }

        private static string ToHex(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            for (int i = 0; i < bytes.Length; i++) sb.Append(bytes[i].ToString("x2"));
            return sb.ToString();
        }

        private static void TryDeleteFile(string p)
        {
            try { if (!string.IsNullOrEmpty(p) && File.Exists(p)) File.Delete(p); } catch { }
        }

        private static void TryDeleteDir(string p)
        {
            try { if (!string.IsNullOrEmpty(p) && Directory.Exists(p)) Directory.Delete(p, true); } catch { }
        }
    }
}
