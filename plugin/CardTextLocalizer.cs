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
    /// both resolve). InvalidateCache() is called by the mod-language switch,
    /// which drives ROUNDS' OWN locale live (I18n.TryApplyRoundsLocale) — one
    /// switch. It no-ops when that game locale did NOT actually move, because
    /// these strings come from the game, not from the mod catalogue.
    /// </summary>
    public static class CardTextLocalizer
    {
        private static readonly Dictionary<string, string> _names =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static readonly Dictionary<string, string> _descs =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private static bool _scanned;

        // The GAME's locale code these caches were populated under, and
        // whether we have ever observed one. Both caches (and the baked card
        // SNAPSHOTS behind them) mirror ROUNDS' locale — NOT the mod's — so
        // this is the only thing that can make them stale.
        private static string _syncedGameLocale;
        private static bool _haveSyncedGameLocale;

        /// <summary>Drop the localized card-text caches (and the baked card
        /// snapshots) because ROUNDS' own locale moved.
        ///
        /// SELF-GUARDED, deliberately: a mod-language switch does not always
        /// move the GAME's locale (the game may not ship that language, or the
        /// live LocalizationSettings assignment may fail), and before Aug-3
        /// this ran unconditionally on every switch — re-scanning 67 CardInfos
        /// into byte-identical strings and DESTROYING + re-rendering every
        /// cached card snapshot for nothing. The guard lives here rather than
        /// only at the caller so no future call site can reintroduce that.
        ///
        /// Residual: the very first call of a session invalidates even when
        /// nothing changed (we have no recorded locale to compare against yet)
        /// unless Prime()/any lookup ran first — Plugin does Prime() at the
        /// menu, so the normal path is already primed. `force` bypasses the
        /// guard for a caller that knows the game text changed some other way.
        /// Skipping also skips CardSnapshot's bounded health re-probe, which
        /// is exactly right when nothing was re-rendered.</summary>
        public static void InvalidateCache(bool force = false)
        {
            string now = null;
            try { now = I18n.GetRoundsLocaleCode(); } catch { }
            if (!force && _haveSyncedGameLocale
                && string.Equals(_syncedGameLocale, now, StringComparison.OrdinalIgnoreCase))
            {
                Plugin.Log.LogInfo($"[CARD-L10N] cache kept — ROUNDS locale unchanged ('{now ?? "?"}')");
                return;
            }
            _syncedGameLocale = now;
            _haveSyncedGameLocale = true;
            _names.Clear(); _descs.Clear(); _scanned = false;
            // NATIVE CARD RENDERING: snapshots bake the game's localized
            // card text into pixels, so a language switch must re-render
            // them too. This is the one locale-change funnel the mod
            // already has — call through so the two card-text caches can
            // never disagree on locale.
            try { CardSnapshot.InvalidateAll(); } catch { }
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
            // Record the locale we are about to read the card text IN, so the
            // next InvalidateCache can tell a real locale move from a
            // mod-only language switch.
            try { _syncedGameLocale = I18n.GetRoundsLocaleCode(); _haveSyncedGameLocale = true; } catch { }
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

        /// <summary>Drop the cache if ROUNDS' OWN locale has moved since the
        /// scan, whoever moved it.
        ///
        /// Codex Aug-4 r2 find 9: every invalidation hook hangs off
        /// I18n.SetLocale, i.e. off the MOD's language picker. A player who
        /// changes language through the base game's Options screen instead
        /// never calls it, so the cached English card names and the baked card
        /// snapshots kept serving until the next mod-side switch or a relaunch.
        ///
        /// Checked here rather than per-frame: this is the funnel every card
        /// name and description already passes through, and the check is one
        /// reflected property read against a memoized string — the actual
        /// rescan only happens when the code genuinely differs.</summary>
        private static void SyncToGameLocale()
        {
            if (!_haveSyncedGameLocale) return;      // nothing scanned yet
            string now = null;
            try { now = I18n.GetRoundsLocaleCode(); } catch { return; }
            if (string.Equals(_syncedGameLocale, now, StringComparison.OrdinalIgnoreCase)) return;
            Plugin.Log.LogInfo($"[CARD-L10N] ROUNDS locale changed outside the mod "
                               + $"('{_syncedGameLocale ?? "?"}' -> '{now ?? "?"}') — dropping card caches");
            InvalidateCache();
        }

        /// <summary>Localized display name, or null when the game has none —
        /// callers keep their existing English fallback layers below this.</summary>
        public static string DisplayName(string anyForm)
        {
            if (string.IsNullOrEmpty(anyForm)) return null;
            SyncToGameLocale();
            ScanIfNeeded();
            return _names.TryGetValue(Key(anyForm), out var v) ? v : null;
        }

        /// <summary>Localized description, or null when the game has none.</summary>
        public static string Description(string anyForm)
        {
            if (string.IsNullOrEmpty(anyForm)) return null;
            SyncToGameLocale();
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

        /// <summary>The name to SHOW for a card, with casing normalized
        /// (bug #157, Sid: "card names throughout the SCR menu are inconsistent
        /// casing — they look best with first capital letter and lower rest").
        ///
        /// The inconsistency is upstream and unfixable at the source: ROUNDS'
        /// own localization table shouts some names ("CAREFUL PLANNING",
        /// "SPRAY") and title-cases others ("Fast Forward", "Emp", "Huge"), and
        /// our stored DB names inherit whichever form the capture path saw
        /// (learning #19's two forms). So normalize at DISPLAY time only —
        /// nothing here touches a stored name, a canonical key, or a lookup.
        ///
        /// Normalization is UNCONDITIONAL, not "only if it shouts": the table
        /// also contains half-shouted names ("Target BOUNCE"), which an
        /// any-lowercase-means-intentional rule would leave exactly as broken
        /// as the all-caps ones. English gets word-by-word capitals to match
        /// the forms already in the table ("Fast Forward"); other locales get
        /// sentence case, because Spanish and Russian do not capitalize every
        /// word of a title.</summary>
        public static string PrettyName(string anyForm, string fallback = null)
        {
            string s = DisplayName(anyForm) ?? fallback ?? anyForm;
            return PrettyCase(s);
        }

        /// <summary>PrettyName without the first-scan cost — for per-frame
        /// in-match paths (mirrors DisplayNameIfCached).</summary>
        public static string PrettyNameIfCached(string anyForm, string fallback = null)
        {
            string s = DisplayNameIfCached(anyForm) ?? fallback ?? anyForm;
            return PrettyCase(s);
        }

        /// <summary>Casing normalizer — see PrettyName. Safe on null/empty and
        /// on strings with no cased characters at all.</summary>
        public static string PrettyCase(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            bool hasLetter = false;
            for (int i = 0; i < s.Length; i++)
                if (char.IsLetter(s[i])) { hasLetter = true; break; }
            if (!hasLetter) return s;               // digits/symbols only
            bool perWord = false;
            try { perWord = I18n.IsEnglish; } catch { perWord = true; }
            var sb = new System.Text.StringBuilder(s.Length);
            bool atStart = true;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                bool isLetter = char.IsLetter(c);
                if (!isLetter)
                {
                    sb.Append(c);
                    // Whitespace and dashes start a new word. Apostrophes do
                    // NOT, so "DEMON'S PACT" becomes "Demon's Pact" rather than
                    // "Demon'S Pact".
                    if (perWord && (char.IsWhiteSpace(c) || c == '-')) atStart = true;
                    continue;
                }
                sb.Append(atStart ? char.ToUpperInvariant(c) : char.ToLowerInvariant(c));
                atStart = false;
            }
            return sb.ToString();
        }
    }
}
