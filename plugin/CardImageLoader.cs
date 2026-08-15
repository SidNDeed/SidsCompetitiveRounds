using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Card art resolver. The PRIMARY source is the native snapshot
    /// pipeline (CardSnapshot — locale-aware, game-authentic renders;
    /// learning #299). A cards/ folder of jpg/png files beside the DLL
    /// is read as a SILENT legacy fallback for old installs that still
    /// carry one — new installs ship no card art and never download any.
    ///
    /// History, so the old design is not reintroduced: this class used
    /// to self-bootstrap the cards/ folder by downloading cards.zip from
    /// an old GitHub release. That asset was retired (every launch 404'd
    /// against it) and the native renderer supersedes the PNG pack, so
    /// the downloader, the expected-count machinery and every folder-scan
    /// warning were removed outright (Aug 2026, learnings #133/#299).
    /// With no folder present, GetSprite goes straight to native-or-null;
    /// every consumer (Card Stats popup, hold-Tab board, tier-list
    /// export) carries its own text/placeholder fallback for null.
    /// </summary>
    public static class CardImageLoader
    {
        // Canonical key (lowercase, no spaces) → on-disk file path.
        // Written once by Initialize(); volatile retained from the era
        // when a background thread swapped it (harmless, and keeps any
        // future async writer honest about publication).
        private static volatile Dictionary<string, string> _filesByKey;
        // Canonical key → cached Sprite. Loaded on demand.
        private static readonly Dictionary<string, Sprite> _spriteCache =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        private static bool _scanAttempted;
        // One-shot log guard for the native-snapshot seam (per-frame path).
        private static bool _snapSeamLogged;
        private static string _cardsDir;

        /// <summary>
        /// One-time scan of the legacy cards/ folder beside the DLL.
        /// SILENT when the folder is absent or empty — that is the normal
        /// state for every new install, not an error, so there is nothing
        /// to warn about and nothing to fetch. Safe to call repeatedly —
        /// only the first call scans.
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
                // Info-only, and only when legacy art is actually present —
                // tells a log reader which fallback tier this rig has.
                // Never a prompt to install anything.
                if (_filesByKey.Count > 0)
                    Plugin.Log?.LogInfo($"[CARD-ART] legacy PNG fallback available: indexed {_filesByKey.Count} card images from {_cardsDir}");
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

        /// <summary>
        /// Returns the best available Sprite for cardName: native
        /// snapshot first, then any legacy on-disk PNG, else null
        /// (consumers render their text/placeholder fallback).
        /// </summary>
        public static Sprite GetSprite(string cardName, bool prioritize = false,
            bool allowPngWhilePending = false)
        {
            if (string.IsNullOrEmpty(cardName)) return null;

            // NATIVE CARD RENDERING seam — the ONE seam every image
            // consumer (Card Stats popup, hold-Tab board, tier-list export)
            // goes through, so all three upgrade at once. Snapshot first;
            // on a miss, kick the async capture. Sits BEFORE the PNG map
            // null-check so native art serves even though new installs
            // have no cards/ folder at all.
            //
            // Aug 6 item 3 ("turn the card images off"): while the pipeline
            // is HEALTHY, a pending capture returns NULL instead of the PNG
            // — consumers show their text/placeholder fallback and upgrade
            // when the native render lands (no more PNG-first flash). The
            // legacy PNG folder — where one still exists on disk — serves
            // only the rigs where native capture is broken
            // (SnapshotsHealthy=false after 3 straight failures) or a
            // per-card dead end below; installs without the folder fall
            // back to text in those cases, which is the accepted trade for
            // not shipping/downloading ~15 MB of art (see class header).
            // `prioritize` puts the card the player is looking at RIGHT NOW
            // at the front of the capture queue; `allowPngWhilePending`
            // keeps the old PNG-while-capturing behavior for bulk surfaces
            // (tier-list export) where a null cell reads worse than old art.
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
                    CardSnapshot.RequestSnapshot(cardName, prioritize);
                    // Codex round 1 (MEDIUM): the null-instead-of-PNG rule is
                    // for a capture that is still COMING. A card that has
                    // exhausted its retries and landed in the failed set has
                    // no capture coming EVER, and RequestSnapshot no-ops for
                    // it — so returning null here rendered that one card as
                    // permanently blank while global SnapshotsHealthy stayed
                    // true (the health kill-switch only trips after 3
                    // CONSECUTIVE failures, which interleaved successes reset).
                    // A per-card dead end must fall through to the PNG (when
                    // a legacy folder has one; text otherwise).
                    // Only withhold the PNG when a capture is genuinely
                    // COMING. Round 2 (finding 10) added RequestsBlocked: the
                    // request can be declined outright (30s env cooldown, or
                    // the cache cap) in which case nothing is coming and a
                    // null renders as a blank card forever.
                    if (CardSnapshot.SnapshotsHealthy && !allowPngWhilePending
                        && !CardSnapshot.IsFailed(cardName)
                        && !CardSnapshot.RequestsBlocked)
                        return null;
                }
                catch (Exception ex)
                {
                    if (!_snapSeamLogged)
                    {
                        _snapSeamLogged = true;
                        Plugin.Log?.LogWarning($"[CARD-ART] native snapshot seam failed ({ex.Message}) — serving legacy PNGs where present");
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
