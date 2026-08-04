using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEngine;
#if !THUNDERSTORE
using System.IO.Compression;
using System.Net;
using System.Threading;
#endif

namespace CompetitiveRounds
{
    /// <summary>
    /// Loads card art shipped alongside the DLL in the
    /// `cards/` subfolder of BepInEx/plugins/CompetitiveRounds/.
    /// Keyed by canonical lowercase no-space card name. Sprites are
    /// created lazily on first request and cached for the session.
    ///
    /// Self-bootstrapping: if the cards/ folder is missing or sparse on
    /// first launch (e.g. mod was installed via Discord installer or a
    /// manual DLL drop without the asset zip), this loader downloads
    /// cards.zip from the v1.26.0 GitHub release on a background
    /// thread, extracts it, and rescans. No user action needed.
    /// </summary>
    public static class CardImageLoader
    {
        // Bumped whenever Landfall ships a new card. The auto-bootstrap
        // (non-Thunderstore builds only) also re-fires if the on-disk
        // count is lower than this.
        private const int EXPECTED_CARD_COUNT = 67;

#if !THUNDERSTORE
        // Stable URL — cards.zip is attached to the v1.26.0 release and
        // never moves. Future patch releases reuse the same asset since
        // the cards themselves don't change with our code patches.
        // Thunderstore builds NEVER reference this URL — Thunderstore
        // packages must be self-contained, so the bundle ships the
        // cards directly under plugins/cards/ and the download path is
        // compiled out entirely.
        private const string CARDS_ZIP_URL =
            "https://github.com/SidNDeed/SidsCompetitiveRounds/releases/download/v1.26.0/cards.zip";
#endif

        // Canonical key (lowercase, no spaces) → on-disk file path.
        // Replaced atomically by the rescan after auto-download so
        // concurrent reads always see a consistent dictionary.
        private static volatile Dictionary<string, string> _filesByKey;
        // Canonical key → cached Sprite. Loaded on demand.
        private static readonly Dictionary<string, Sprite> _spriteCache =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        private static bool _scanAttempted;
        // One-shot log guard for the native-snapshot seam (per-frame path).
        private static bool _snapSeamLogged;
#if !THUNDERSTORE
        private static int _downloadStarted; // 0 = not started, 1 = in flight or done
#endif
        private static string _cardsDir;

        /// <summary>
        /// True once the cards/ folder has been scanned and at least
        /// one image is available. Callers that branch on
        /// "image present" should check this before calling GetSprite.
        /// </summary>
        public static bool IsAvailable =>
            _filesByKey != null && _filesByKey.Count > 0;

        public static int Count => _filesByKey?.Count ?? 0;

        /// <summary>
        /// Scans the cards/ folder for jpg/png files and indexes them
        /// by canonical name. If the folder is missing or has fewer
        /// than EXPECTED_CARD_COUNT images, kicks off a background
        /// download of cards.zip from the GitHub release. Safe to
        /// call repeatedly — only the first call does the sync scan.
        /// </summary>
        public static void Initialize()
        {
            if (_scanAttempted) return;
            _scanAttempted = true;
            try
            {
                string dllPath = Assembly.GetExecutingAssembly().Location;
                string dllDir = Path.GetDirectoryName(dllPath);
                _cardsDir = Path.Combine(dllDir, "cards");
                _filesByKey = ScanCardsDir();
                int found = _filesByKey.Count;
                if (found >= EXPECTED_CARD_COUNT)
                {
                    Plugin.Log?.LogInfo($"[CARD-ART] indexed {found} card images from {_cardsDir}");
                    return;
                }
#if THUNDERSTORE
                // Thunderstore packages ship the cards directly in the
                // bundle. If the count is below expected here, the user
                // either has a corrupt install or extracted the bundle
                // wrong — re-install via the mod manager.
                Plugin.Log?.LogWarning($"[CARD-ART] only {found}/{EXPECTED_CARD_COUNT} card images present at {_cardsDir}. Reinstall via the mod manager if popups / tier list export look broken.");
#else
                Plugin.Log?.LogInfo($"[CARD-ART] {found}/{EXPECTED_CARD_COUNT} card images present at {_cardsDir} — fetching the rest from GitHub release in background.");
                MaybeStartAutoDownload();
#endif
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[CARD-ART] init failed: {ex.Message}");
                _filesByKey = _filesByKey ?? new Dictionary<string, string>();
            }
        }

        /// <summary>Reads the cards directory once and returns a fresh
        /// canonical-name → path map. Returns an empty map if the
        /// directory is missing.</summary>
        private static Dictionary<string, string> ScanCardsDir()
        {
            var map = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            if (string.IsNullOrEmpty(_cardsDir) || !Directory.Exists(_cardsDir)) return map;
            foreach (var ext in new[] { "*.jpg", "*.jpeg", "*.png" })
            {
                foreach (var file in Directory.GetFiles(_cardsDir, ext))
                {
                    string stem = Path.GetFileNameWithoutExtension(file);
                    string key = NormalizeKey(stem);
                    if (!map.ContainsKey(key)) map[key] = file;
                }
            }
            return map;
        }

#if !THUNDERSTORE
        /// <summary>One-shot guarded auto-download. Spawns a background
        /// thread that fetches cards.zip from the GitHub release,
        /// extracts the PNGs into _cardsDir, and rescans. Subsequent
        /// calls are no-ops thanks to the Interlocked compare-exchange.
        /// Compiled out of Thunderstore builds — those bundles ship the
        /// cards directly so runtime download is unnecessary AND would
        /// violate Thunderstore's "no runtime asset fetching" policy.</summary>
        private static void MaybeStartAutoDownload()
        {
            if (Interlocked.Exchange(ref _downloadStarted, 1) != 0) return;
            var t = new Thread(AutoDownloadWorker) { IsBackground = true, Name = "CR_CardArtDownload" };
            t.Start();
        }

        private static void AutoDownloadWorker()
        {
            string tmpZip = null;
            try
            {
                Directory.CreateDirectory(_cardsDir);
                tmpZip = Path.Combine(Path.GetDirectoryName(_cardsDir), "cards-download.zip");
                Plugin.Log?.LogInfo($"[CARD-ART] downloading {CARDS_ZIP_URL} → {tmpZip}");

                // GitHub redirects to S3 / objects.githubusercontent.com.
                // WebClient follows redirects by default. TLS 1.2 needed
                // on older .NET runtimes; force it explicitly.
                try { ServicePointManager.SecurityProtocol |= SecurityProtocolType.Tls12; } catch { }

                using (var wc = new WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRounds-Mod/" + Plugin.ModVersion);
                    wc.DownloadFile(CARDS_ZIP_URL, tmpZip);
                }

                long bytes = new FileInfo(tmpZip).Length;
                Plugin.Log?.LogInfo($"[CARD-ART] downloaded {bytes / 1024} KB, extracting to {_cardsDir}");

                int extracted = 0;
                using (var fs = File.OpenRead(tmpZip))
                using (var zip = new ZipArchive(fs, ZipArchiveMode.Read))
                {
                    foreach (var entry in zip.Entries)
                    {
                        if (string.IsNullOrEmpty(entry.Name)) continue; // directory marker
                        string lower = entry.Name.ToLowerInvariant();
                        if (!lower.EndsWith(".png") && !lower.EndsWith(".jpg") && !lower.EndsWith(".jpeg")) continue;
                        string outPath = Path.Combine(_cardsDir, entry.Name);
                        try
                        {
                            using (var es = entry.Open())
                            using (var os = File.Create(outPath))
                            {
                                es.CopyTo(os);
                            }
                            extracted++;
                        }
                        catch (Exception exEntry)
                        {
                            Plugin.Log?.LogWarning($"[CARD-ART] extract failed for {entry.Name}: {exEntry.Message}");
                        }
                    }
                }

                // Atomic swap — readers either see the old (partial) map
                // or the new (full) one, never an in-progress mutation.
                _filesByKey = ScanCardsDir();
                Plugin.Log?.LogInfo($"[CARD-ART] auto-bootstrap complete: extracted {extracted} files, indexed {_filesByKey.Count}.");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[CARD-ART] auto-download failed: {ex.Message} — image popups will fall back to text until the next launch.");
            }
            finally
            {
                if (tmpZip != null && File.Exists(tmpZip))
                {
                    try { File.Delete(tmpZip); } catch { }
                }
            }
        }
#endif

        /// <summary>
        /// Returns the cached Sprite for cardName, or loads it from
        /// disk on first request. Returns null if the card has no
        /// art file in the cards/ folder.
        /// </summary>
        public static Sprite GetSprite(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return null;

            // NATIVE CARD RENDERING seam — the ONE seam every image
            // consumer (Card Stats popup, hold-Tab board, tier-list export)
            // goes through, so all three upgrade at once. Snapshot first;
            // on a miss, kick the async capture and serve the PNG exactly
            // as before (async upgrade — the snapshot lands for the NEXT
            // request). Sits BEFORE the PNG map null-check so native art
            // can serve even when the cards/ folder is missing/corrupt.
            // CardSnapshot.UseNativeSnapshots is the single master switch
            // back to pure-PNG behavior; any exception here falls through
            // to the PNG path (one log, then permanently quiet — this is a
            // per-frame path on the Tab board).
            if (CardSnapshot.UseNativeSnapshots)
            {
                try
                {
                    if (CardSnapshot.TryGetSprite(cardName, out var snap) && snap != null)
                        return snap;
                    CardSnapshot.RequestSnapshot(cardName);
                }
                catch (Exception ex)
                {
                    if (!_snapSeamLogged)
                    {
                        _snapSeamLogged = true;
                        Plugin.Log?.LogWarning($"[CARD-ART] native snapshot seam failed ({ex.Message}) — serving PNGs");
                    }
                }
            }

            if (!_scanAttempted) Initialize();
            var map = _filesByKey;
            if (map == null) return null;

            // Try the canonical (server-normalized) name first, then
            // the raw name. Some callers pass display names (with
            // spaces); others pass canonical (lowercase no space).
            string canonical = null;
            try { canonical = CardRarityLookup.GetCanonicalName(cardName); } catch { }
            string keyA = NormalizeKey(canonical ?? cardName);
            string keyB = NormalizeKey(cardName);

            if (_spriteCache.TryGetValue(keyA, out var sA) && sA != null) return sA;
            if (keyA != keyB && _spriteCache.TryGetValue(keyB, out var sB) && sB != null) return sB;

            string path = null;
            string keyUsed = null;
            if (map.TryGetValue(keyA, out path)) keyUsed = keyA;
            else if (map.TryGetValue(keyB, out path)) keyUsed = keyB;
            if (path == null) return null;

            try
            {
                byte[] bytes = File.ReadAllBytes(path);
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                tex.hideFlags = HideFlags.HideAndDontSave;
                if (!tex.LoadImage(bytes))
                {
                    Plugin.Log?.LogWarning($"[CARD-ART] LoadImage failed for {path}");
                    return null;
                }
                tex.filterMode = FilterMode.Bilinear;
                var sprite = Sprite.Create(tex,
                    new Rect(0, 0, tex.width, tex.height),
                    new Vector2(0.5f, 0.5f), 100f);
                sprite.name = $"CardArt_{keyUsed}";
                sprite.hideFlags = HideFlags.HideAndDontSave;
                _spriteCache[keyUsed] = sprite;
                return sprite;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[CARD-ART] failed to load {path}: {ex.Message}");
                return null;
            }
        }

        /// <summary>Lowercase + strip spaces, hyphens, apostrophes, periods. Matches
        /// our filename convention "abyssal countdown.png" → "abyssalcountdown".
        /// internal: CardSnapshot keys its cache with THIS normalizer so the
        /// native-render cache and the PNG cache collapse name forms
        /// identically (one seam, one key derivation).</summary>
        internal static string NormalizeKey(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new System.Text.StringBuilder(s.Length);
            foreach (char c in s)
            {
                if (c == ' ' || c == '-' || c == '\'' || c == '.' || c == '_') continue;
                sb.Append(char.ToLowerInvariant(c));
            }
            return sb.ToString();
        }
    }
}
