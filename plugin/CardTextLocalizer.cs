using System;
using System.Collections.Generic;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Resolves card display text through the GAME'S OWN localization
    /// (StringTableCards, in ROUNDS' active locale) — the interim
    /// localization layer for every card-name/description surface
    /// (localization-design §2.1.6 "Interim, free, regardless of the spike").
    ///
    /// Mechanism: CardInfo.CardName / CardDescription are synchronous
    /// PROPERTIES on the publicized assembly; both internally guard IsEmpty
    /// and fall back to the GameObject name, and calling them needs no
    /// Unity.Localization csproj reference (they return string). The frozen
    /// English `cardName` FIELD stays the identity everywhere (matches,
    /// HMAC, achievements — localization-design: "Card names stay English in
    /// every data path, permanently"); this class is DISPLAY ONLY.
    ///
    /// Cache: per session, keyed by the canonical (GameObject) name form via
    /// CardRarityLookup.GetCanonicalName (#19 — log names and display names
    /// both resolve). InvalidateCache() exists for the future mod-language
    /// switch (which also writes ROUNDS' OPTION_LANGUAGE, so one switch).
    /// </summary>
    public static class CardTextLocalizer
    {
        private static readonly Dictionary<string, string> _names =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, string> _descs =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static bool _scanned;

        public static void InvalidateCache()
        {
            _names.Clear(); _descs.Clear(); _scanned = false;
        }

        private static string Key(string anyForm)
        {
            if (string.IsNullOrEmpty(anyForm)) return "";
            string canon = null;
            try { canon = CardRarityLookup.GetCanonicalName(anyForm); } catch { }
            return (canon ?? anyForm).ToLowerInvariant().Replace(" ", "");
        }

        private static void ScanIfNeeded()
        {
            if (_scanned) return;
            _scanned = true;
            try
            {
                // Inactive + unloaded objects included — works at the main
                // menu, same call CardRarityLookup.ScanAll already relies on.
                var all = Resources.FindObjectsOfTypeAll<CardInfo>();
                foreach (var ci in all)
                {
                    if (ci == null) continue;
                    string goName = null;
                    try { goName = ci.gameObject != null ? ci.gameObject.name : null; } catch { }
                    if (string.IsNullOrEmpty(goName)) continue;
                    string k = Key(goName);
                    if (string.IsNullOrEmpty(k) || _names.ContainsKey(k)) continue;
                    string ln = null, ld = null;
                    // Localized resolution can throw if the locale system is
                    // mid-initialization — a per-card failure must not poison
                    // the scan (the entry just stays unlocalized this session).
                    try { ln = ci.CardName; } catch { }
                    try { ld = ci.CardDescription; } catch { }
                    // Both properties return the GameObject name when their
                    // localized reference is EMPTY (vanilla quirk) — that is
                    // "no localized text", not a translation.
                    if (!string.IsNullOrEmpty(ln) && ln != goName) _names[k] = ln;
                    if (!string.IsNullOrEmpty(ld) && ld != goName) _descs[k] = ld;
                }
                Plugin.Log.LogInfo($"[CARD-L10N] scanned {_names.Count} localized names, {_descs.Count} descriptions");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning("[CARD-L10N] scan failed: " + ex.Message);
            }
        }

        /// <summary>Localized display name, or null when the game has none —
        /// callers keep their existing English fallback layers below this.</summary>
        public static string DisplayName(string anyForm)
        {
            if (string.IsNullOrEmpty(anyForm)) return null;
            ScanIfNeeded();
            return _names.TryGetValue(Key(anyForm), out var v) ? v : null;
        }

        /// <summary>Localized description, or null when the game has none.</summary>
        public static string Description(string anyForm)
        {
            if (string.IsNullOrEmpty(anyForm)) return null;
            ScanIfNeeded();
            return _descs.TryGetValue(Key(anyForm), out var v) ? v : null;
        }

        /// <summary>Like DisplayName but NEVER triggers the first scan — for
        /// per-frame in-match paths (the hold-Tab board) where the initial
        /// 67-card localized-table load would be a visible frame hitch.
        /// Returns null until Prime()/any menu-time call has run.</summary>
        public static string DisplayNameIfCached(string anyForm)
        {
            if (!_scanned || string.IsNullOrEmpty(anyForm)) return null;
            return _names.TryGetValue(Key(anyForm), out var v) ? v : null;
        }

        /// <summary>Warm the cache at a frame-cost-tolerant moment (menu).</summary>
        public static void Prime() { ScanIfNeeded(); }
    }
}
