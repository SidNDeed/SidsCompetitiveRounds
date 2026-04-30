using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Loads card art (jpg) shipped alongside the DLL in the
    /// `cards/` subfolder of BepInEx/plugins/CompetitiveRounds/.
    /// Keyed by canonical lowercase no-space card name. Sprites are
    /// created lazily on first request and cached for the session.
    /// </summary>
    public static class CardImageLoader
    {
        // Canonical key (lowercase, no spaces) → on-disk file path.
        // Built once at initialize from the cards/ directory listing.
        private static Dictionary<string, string> _filesByKey;
        // Canonical key → cached Sprite. Loaded on demand.
        private static readonly Dictionary<string, Sprite> _spriteCache =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        private static bool _scanAttempted;
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
        /// Scans the cards/ folder for jpg/png files and indexes
        /// them by canonical name (lowercase, no spaces). Safe to
        /// call repeatedly — only the first call does work.
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
                if (!Directory.Exists(_cardsDir))
                {
                    Plugin.Log?.LogWarning($"[CARD-ART] cards/ folder not found at {_cardsDir} — image popups disabled.");
                    _filesByKey = new Dictionary<string, string>();
                    return;
                }
                _filesByKey = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                foreach (var ext in new[] { "*.jpg", "*.jpeg", "*.png" })
                {
                    foreach (var file in Directory.GetFiles(_cardsDir, ext))
                    {
                        string stem = Path.GetFileNameWithoutExtension(file);
                        string key = NormalizeKey(stem);
                        if (!_filesByKey.ContainsKey(key))
                            _filesByKey[key] = file;
                    }
                }
                Plugin.Log?.LogInfo($"[CARD-ART] indexed {_filesByKey.Count} card images from {_cardsDir}");
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[CARD-ART] init failed: {ex.Message}");
                _filesByKey = _filesByKey ?? new Dictionary<string, string>();
            }
        }

        /// <summary>
        /// Returns the cached Sprite for cardName, or loads it from
        /// disk on first request. Returns null if the card has no
        /// art file in the cards/ folder.
        /// </summary>
        public static Sprite GetSprite(string cardName)
        {
            if (string.IsNullOrEmpty(cardName)) return null;
            if (!_scanAttempted) Initialize();
            if (_filesByKey == null) return null;

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
            if (_filesByKey.TryGetValue(keyA, out path)) keyUsed = keyA;
            else if (_filesByKey.TryGetValue(keyB, out path)) keyUsed = keyB;
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
        /// our filename convention "abyssal countdown.jpg" → "abyssalcountdown".</summary>
        private static string NormalizeKey(string s)
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
