using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Localization runtime (localization-design.md v1).
    ///
    /// v1 scope: WHOLE-STRING lookup at the two uGUI chokepoints
    /// (UIFactory.CreateText / SetText) plus explicit Tr() calls from IMGUI
    /// sites. The catalogue is keyed by the ENGLISH SOURCE STRING itself at
    /// runtime (the sha1 key_id scheme lives in the offline catalogue files;
    /// the DLL embeds a flat source→target table per locale, which is what a
    /// whole-string chokepoint can actually consume).
    ///
    /// Fallback chain per entry: approved → machine draft → English source.
    /// Machine drafts render LIVE (D4 — a language with no moderator is still
    /// usable) and the pack format distinguishes them so the completeness
    /// metric can honestly report "covered but 0% reviewed".
    ///
    /// FROZEN, never translated (localization-design §2.4): status enums the
    /// client compares (`kind`, `status`, lock_reason, ladder, mode), SKUs,
    /// room prefixes, HMAC canonicals, card identity names. The chokepoint
    /// only ever sees composed DISPLAY strings, and the catalogue simply has
    /// no entries for identity strings — but never add one.
    ///
    /// PSEUDO-LOCALE ("qps"): renders every catalogued string bracketed and
    /// widened ([Ļéàdéŕbóàŕd ẋẋẋẋ]) so untranslated/overflowing surfaces are
    /// visible at a glance. Dev tool; reachable from the language picker only
    /// when PseudoLocaleEnabled config is true.
    ///
    /// D2: locale is asked ONCE (config sentinel "unset" → prompt with the
    /// OS-culture suggestion), changeable later in Settings. The switch also
    /// (optionally) writes ROUNDS' own OPTION_LANGUAGE so in-match card faces
    /// agree with the mod (one switch, not two — §2.1.4).
    /// </summary>
    public static class I18n
    {
        public const string LOCALE_UNSET = "unset";
        public const string LOCALE_EN = "en";
        public const string LOCALE_PSEUDO = "qps";

        // locale → (source → target). Loaded from the embedded catalogues at
        // Install(); server-fetched overlay merges on top when it arrives.
        private static readonly Dictionary<string, Dictionary<string, string>> _catalogues =
            new Dictionary<string, Dictionary<string, string>>(StringComparer.Ordinal);
        private static string _locale = LOCALE_EN;
        private static bool _pseudo;

        /// <summary>Current mod display locale ("en" when unset).</summary>
        public static string Locale => _locale;
        public static bool IsEnglish => _locale == LOCALE_EN && !_pseudo;

        public static event Action LocaleChanged;

        public static void SetLocale(string locale)
        {
            locale = string.IsNullOrEmpty(locale) ? LOCALE_EN : locale.Trim().ToLowerInvariant();
            _pseudo = locale == LOCALE_PSEUDO;
            _locale = _pseudo ? LOCALE_EN : locale;
            try { CardTextLocalizer.InvalidateCache(); } catch { }
            // ONE SWITCH (localization-design §2.1.4 / Codex client find 8):
            // the mod's language also writes ROUNDS' own OPTION_LANGUAGE so
            // native card faces agree with the mod chrome. Written as a RAW
            // PlayerPref, applied by vanilla at NEXT LAUNCH — never by
            // flipping LocalizationSettings.SelectedLocale live, whose
            // OnLocaleChanged calls ReleaseAllTables() for ALL locales and
            // drops every loaded string/font table mid-session.
            if (!_pseudo)
                try { TryWriteRoundsLanguagePref(_locale); } catch { }
            try { LocaleChanged?.Invoke(); } catch { }
            Plugin.Log.LogInfo($"[I18N] locale set: {locale}");
        }

        /// <summary>Maps our two-letter locale onto ROUNDS' AvailableLocales
        /// index and writes the OPTION_LANGUAGE PlayerPref (all via
        /// reflection — the csproj deliberately does not reference
        /// Unity.Localization). Returns silently when the locale system or a
        /// matching locale is absent.</summary>
        private static void TryWriteRoundsLanguagePref(string twoLetter)
        {
            Type ls = null;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                ls = asm.GetType("UnityEngine.Localization.Settings.LocalizationSettings");
                if (ls != null) break;
            }
            if (ls == null) return;
            var avail = ls.GetProperty("AvailableLocales",
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static)?.GetValue(null);
            var locales = avail?.GetType().GetProperty("Locales")?.GetValue(avail)
                as System.Collections.IList;
            if (locales == null) return;
            for (int i = 0; i < locales.Count; i++)
            {
                var loc = locales[i];
                if (loc == null) continue;
                var ident = loc.GetType().GetProperty("Identifier")?.GetValue(loc);
                var code = ident?.GetType().GetProperty("Code")?.GetValue(ident) as string;
                if (string.IsNullOrEmpty(code)) continue;
                if (code.ToLowerInvariant().StartsWith(twoLetter))
                {
                    UnityEngine.PlayerPrefs.SetInt("OPTION_LANGUAGE", i);
                    UnityEngine.PlayerPrefs.Save();
                    Plugin.Log.LogInfo($"[I18N] wrote ROUNDS OPTION_LANGUAGE={i} ({code}) — card text follows after restart");
                    return;
                }
            }
        }

        // ── Server pack overlay (localization-design §2.2/§2.3) ──
        // Delivery is dual: the embedded catalogue is the permanent floor;
        // the server pack (fetched at launch, cached to BepInEx/config/)
        // makes an approved correction live without a release. The cache
        // loads BEFORE any network call so offline players keep the last
        // known overlay.

        private static string PackCachePath(string locale) =>
            System.IO.Path.Combine(BepInEx.Paths.ConfigPath,
                $"CompetitiveRounds.i18n.{locale}.json");

        // The server overlay is a SEPARATE, WHOLE-SALE-REPLACEABLE layer
        // (wave-2 find 9): merging server entries into the embedded catalogue
        // meant an admin REVERT (server deletes the entry, next pack omits
        // it) could never remove the stale override from a running client.
        // Tr() checks this layer first; ApplyPack swaps it atomically.
        private static Dictionary<string, string> _serverOverlay;
        private static string _serverOverlayLocale;

        // Hard bounds on anything a (possibly compromised) server hands us
        // (wave-2 find 18).
        private const int PackMaxBytes = 2 * 1024 * 1024;
        private const int PackMaxEntries = 5000;
        private const int PackMaxStringLen = 4000;

        public static void LoadCachedPack()
        {
            if (_locale == LOCALE_EN || _pseudo) return;
            try
            {
                string p = PackCachePath(_locale);
                if (System.IO.File.Exists(p))
                    ApplyPack(System.IO.File.ReadAllText(p), _locale, fromCache: true);
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] cached pack load failed: {ex.Message}"); }
        }

        /// <summary>Parse + install a server pack as the overlay layer for
        /// `expectedLocale`. Wire contract (design Part 4 item 4): the integer
        /// `format` is checked BEFORE the body is parsed, `min_mod_version` is
        /// enforced, and the response's own `locale` field must match the
        /// expected one (wave-2 find 8 — a slow response from a PREVIOUS
        /// locale selection must never install under the current one). Strict
        /// parse (find 18): an unterminated string or unclosed array rejects
        /// the whole pack, and byte/entry/string caps bound a hostile server.
        /// Sources not present in the embedded catalogue are dropped (find
        /// 19): a pack can only re-translate KNOWN UI strings, never poison a
        /// name or status value. Returns true when the pack was installed
        /// (caller may cache the raw response).</summary>
        public static bool ApplyPack(string json, string expectedLocale, bool fromCache = false)
        {
            if (string.IsNullOrEmpty(json) || string.IsNullOrEmpty(expectedLocale)) return false;
            if (json.Length > PackMaxBytes)
            {
                Plugin.Log.LogWarning($"[I18N] pack too large ({json.Length}B) — ignored");
                return false;
            }
            if (_locale != expectedLocale)
            {
                Plugin.Log.LogInfo($"[I18N] pack for '{expectedLocale}' arrived after locale moved to '{_locale}' — ignored");
                return false;
            }
            try
            {
                // Structural pre-pass (round-4 find F3): the old root check
                // was a bare IndexOf('}') that a brace INSIDE a trailing
                // string value satisfied, so a truncated document could be
                // installed and cached. Full string-aware brace/bracket
                // balance is one cheap pass over ≤2MB.
                if (!JsonStructureBalanced(json))
                {
                    Plugin.Log.LogWarning("[I18N] pack rejected: unbalanced JSON structure");
                    return false;
                }
                int fmt = ExtractInt(json, "\"format\":");
                if (fmt != 1)
                {
                    Plugin.Log.LogWarning($"[I18N] pack format {fmt} unsupported — ignored");
                    return false;
                }
                string packLocale = ExtractSimpleString(json, "\"locale\":\"");
                if (!string.Equals(packLocale, expectedLocale, StringComparison.OrdinalIgnoreCase))
                {
                    Plugin.Log.LogWarning($"[I18N] pack locale '{packLocale}' != expected '{expectedLocale}' — ignored");
                    return false;
                }
                string minVer = ExtractSimpleString(json, "\"min_mod_version\":\"");
                if (!string.IsNullOrEmpty(minVer) && VersionLess(Plugin.ModVersion, minVer))
                {
                    Plugin.Log.LogWarning($"[I18N] pack needs mod {minVer} — ignored");
                    return false;
                }
                int arr = json.IndexOf("\"entries\":", StringComparison.Ordinal);
                if (arr < 0) return false;
                arr = json.IndexOf('[', arr);
                if (arr < 0) return false;
                var overlay = new Dictionary<string, string>(StringComparer.Ordinal);
                int dropped = 0, parsedEntries = 0;
                int i = arr + 1;
                bool closed = false;
                while (i < json.Length)
                {
                    if (json[i] == ']') { closed = true; break; }
                    if (json[i] == '{')
                    {
                        // Cap PARSED entry objects (round-3 find N9: the old
                        // cap counted unique ACCEPTED sources, so 6000 copies
                        // of one entry sailed under it).
                        if (++parsedEntries > PackMaxEntries)
                            throw new FormatException("entry cap exceeded");
                        string s = null, t = null;
                        i++;
                        while (i < json.Length && json[i] != '}')
                        {
                            if (json[i] == '"')
                            {
                                bool okStr;
                                string keyName = ReadJsonString(json, ref i, out okStr);
                                if (!okStr) throw new FormatException("unterminated key string");
                                while (i < json.Length && (json[i] == ':' || json[i] == ' ')) i++;
                                if (i < json.Length && json[i] == '"')
                                {
                                    string val = ReadJsonString(json, ref i, out okStr);
                                    if (!okStr) throw new FormatException("unterminated value string");
                                    if (keyName == "s") s = val;
                                    else if (keyName == "t") t = val;
                                }
                                else
                                {
                                    // non-string value (none expected) — skip token
                                    while (i < json.Length && json[i] != ',' && json[i] != '}') i++;
                                }
                            }
                            else i++;
                        }
                        if (i >= json.Length) throw new FormatException("unterminated entry object");
                        if (!string.IsNullOrEmpty(s) && t != null
                            && s.Length <= PackMaxStringLen && t.Length <= PackMaxStringLen)
                        {
                            // Find 19: only re-translate KNOWN embedded keys.
                            if (!IsEmbeddedKey(s)) { dropped++; }
                            else if (!TagsMatch(s, t)) { dropped++; }
                            else overlay[s] = t;
                        }
                    }
                    i++;
                }
                if (!closed) throw new FormatException("unterminated entries array");
                // Root closure is guaranteed by JsonStructureBalanced above
                // (round-4 find F3 retired the naive IndexOf('}') check).
                // Atomic layer swap — an empty pack legitimately clears every
                // server override (that IS the revert path, find 9). NO
                // LocaleChanged fire here: a fetch handler subscribed to that
                // event would recurse (fetch -> apply -> event -> fetch).
                _serverOverlay = overlay;
                _serverOverlayLocale = expectedLocale;
                Plugin.Log.LogInfo($"[I18N] pack overlay installed: {overlay.Count} entries"
                                   + (dropped > 0 ? $" ({dropped} dropped: unknown key / tag mismatch)" : "")
                                   + $" [{(fromCache ? "cache" : "server")}]");
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[I18N] pack rejected: {ex.Message}");
                return false;
            }
        }

        /// <summary>Caches a freshly fetched pack for offline launches. The
        /// caller passes the locale it FETCHED for (find 8): the cache path
        /// must never be derived from the mutable current locale.</summary>
        public static void CachePack(string json, string locale)
        {
            if (string.IsNullOrEmpty(locale) || locale == LOCALE_EN || _pseudo) return;
            try { System.IO.File.WriteAllText(PackCachePath(locale), json); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] pack cache write failed: {ex.Message}"); }
        }

        /// <summary>True when `s` is a known translatable SOURCE. The
        /// allowlist is the EXTRACTED source registry (I18nSourceKeys.g.cs,
        /// round-3 find N5 — the translated dictionaries alone rejected the
        /// 200+ extracted-but-untranslated keys that server corrections
        /// exist to reach) UNION the embedded catalogue keys (hand-added
        /// entries the extractor may not see). A compromised server still
        /// cannot define translations for arbitrary strings.</summary>
        private static HashSet<string> _sourceKeySet;
        private static bool IsEmbeddedKey(string s)
        {
            if (_sourceKeySet == null)
            {
                var set = new HashSet<string>(StringComparer.Ordinal);
                try { foreach (var k in I18nSourceKeys.Keys) set.Add(k); } catch { }
                foreach (var kv in _catalogues)
                    foreach (var k in kv.Value.Keys) set.Add(k);
                _sourceKeySet = set;
            }
            return _sourceKeySet.Contains(s);
        }

        private static int ExtractInt(string json, string marker)
        {
            int p = json.IndexOf(marker, StringComparison.Ordinal);
            if (p < 0) return -1;
            p += marker.Length;
            int end = p;
            while (end < json.Length && (char.IsDigit(json[end]) || json[end] == ' ')) end++;
            int v;
            return int.TryParse(json.Substring(p, end - p).Trim(), out v) ? v : -1;
        }

        // Only safe for values we KNOW are escape-free (version strings).
        private static string ExtractSimpleString(string json, string marker)
        {
            int p = json.IndexOf(marker, StringComparison.Ordinal);
            if (p < 0) return null;
            p += marker.Length;
            int end = json.IndexOf('"', p);
            return end > p ? json.Substring(p, end - p) : null;
        }

        private static bool VersionLess(string a, string b)
        {
            try
            {
                var pa = (a ?? "0").Split('.');
                var pb = (b ?? "0").Split('.');
                for (int i = 0; i < Math.Max(pa.Length, pb.Length); i++)
                {
                    int x = i < pa.Length && int.TryParse(pa[i], out var xv) ? xv : 0;
                    int y = i < pb.Length && int.TryParse(pb[i], out var yv) ? yv : 0;
                    if (x != y) return x < y;
                }
            }
            catch { }
            return false;
        }

        /// <summary>String-aware structural validation (round-4 find F3,
        /// hardened per the round-5 gate): TYPED delimiter stack — a scalar
        /// depth counter let `{...]` cancel out — plus single-`{`-root
        /// enforcement: the first token must open the root object, a closer
        /// must match the stack top, and after the root closes only
        /// whitespace may follow (no second root, no trailing string).</summary>
        private static bool JsonStructureBalanced(string json)
        {
            var stack = new Stack<char>();
            bool rootOpened = false, rootClosed = false;
            int i = 0;
            while (i < json.Length)
            {
                char c = json[i];
                if (char.IsWhiteSpace(c)) { i++; continue; }
                if (rootClosed) return false;      // ANY token after the root
                if (!rootOpened)
                {
                    if (c != '{') return false;    // root must be one object
                    rootOpened = true;
                    stack.Push('{');
                    i++;
                    continue;
                }
                if (c == '"')
                {
                    i++;
                    while (i < json.Length)
                    {
                        if (json[i] == '\\') { i += 2; continue; }
                        if (json[i] == '"') break;
                        i++;
                    }
                    if (i >= json.Length) return false;   // unterminated string
                }
                else if (c == '{' || c == '[')
                {
                    stack.Push(c);
                    if (stack.Count > 64) return false;
                }
                else if (c == '}' || c == ']')
                {
                    if (stack.Count == 0) return false;
                    char open = stack.Pop();
                    if ((c == '}') != (open == '{')) return false;   // mismatched closer
                    if (stack.Count == 0) rootClosed = true;
                }
                i++;
            }
            return rootOpened && rootClosed;
        }

        /// <summary>Reads a JSON string starting at the opening quote
        /// (json[i] == '"'); leaves i just past the closing quote. Handles
        /// the full escape set including \uXXXX. `ok` is false when EOF was
        /// reached before the closing quote (find 18 — a truncated pack must
        /// be REJECTED, not silently installed with a cut-off value).</summary>
        private static string ReadJsonString(string json, ref int i, out bool ok)
        {
            var sb = new StringBuilder();
            ok = false;
            i++;   // opening quote
            while (i < json.Length)
            {
                char c = json[i];
                if (c == '"') { i++; ok = true; break; }
                if (c == '\\' && i + 1 < json.Length)
                {
                    char e = json[i + 1];
                    i += 2;
                    switch (e)
                    {
                        case 'n': sb.Append('\n'); break;
                        case 'r': sb.Append('\r'); break;
                        case 't': sb.Append('\t'); break;
                        case 'u':
                            if (i + 4 <= json.Length
                                && ushort.TryParse(json.Substring(i, 4),
                                    System.Globalization.NumberStyles.HexNumber,
                                    CultureInfo.InvariantCulture, out var u))
                            { sb.Append((char)u); i += 4; }
                            break;
                        default: sb.Append(e); break;   // \" \\ \/ etc.
                    }
                    continue;
                }
                sb.Append(c);
                i++;
            }
            return sb.ToString();
        }

        /// <summary>OS-culture suggestion for the ask-once prompt (D2). Only
        /// locales we actually ship are suggested; everything else → en.</summary>
        public static string SuggestFromOs()
        {
            try
            {
                string two = CultureInfo.CurrentUICulture.TwoLetterISOLanguageName?.ToLowerInvariant();
                if (two == "es" || two == "ru") return two;
            }
            catch { }
            return LOCALE_EN;
        }

        public static void RegisterCatalogue(string locale, Dictionary<string, string> entries)
        {
            if (string.IsNullOrEmpty(locale) || entries == null) return;
            Dictionary<string, string> cat;
            if (!_catalogues.TryGetValue(locale, out cat))
            {
                cat = new Dictionary<string, string>(StringComparer.Ordinal);
                _catalogues[locale] = cat;
            }
            int accepted = 0, rejected = 0;
            foreach (var kv in entries)
            {
                // Client-side re-validation at load (localization-design
                // §2.5 defence-in-depth): a translation whose TMP tag
                // sequence differs from its source silently bleeds
                // formatting across the whole page — drop the single entry,
                // keep English, log once per pack.
                if (!TagsMatch(kv.Key, kv.Value)) { rejected++; continue; }
                cat[kv.Key] = kv.Value;
                accepted++;
            }
            Plugin.Log.LogInfo($"[I18N] catalogue '{locale}': +{accepted} entries" +
                               (rejected > 0 ? $" ({rejected} REJECTED on tag mismatch)" : ""));
        }

        /// <summary>The chokepoint. English in, display-locale out; unknown
        /// strings pass through untouched (raw keys are never shown because
        /// the key IS the English source).</summary>
        public static string Tr(string english)
        {
            if (string.IsNullOrEmpty(english)) return english;
            if (_pseudo) return Pseudo(english);
            if (_locale == LOCALE_EN) return english;
            // Server overlay first (approved corrections, live without a
            // release), then the embedded catalogue floor.
            var ov = _serverOverlay;
            if (ov != null && _serverOverlayLocale == _locale)
            {
                string o;
                if (ov.TryGetValue(english, out o) && !string.IsNullOrEmpty(o)) return o;
            }
            Dictionary<string, string> cat;
            if (_catalogues.TryGetValue(_locale, out cat))
            {
                string t;
                if (cat.TryGetValue(english, out t) && !string.IsNullOrEmpty(t)) return t;
            }
            return english;
        }

        /// <summary>Interpolation-friendly form: Tr the TEMPLATE, then
        /// string.Format — call sites migrate `$"...{x}..."` to
        /// `I18n.TrF("...{0}...", x)` so the translatable unit is stable.</summary>
        public static string TrF(string template, params object[] args)
        {
            try { return string.Format(CultureInfo.InvariantCulture, Tr(template), args); }
            catch { return template; }
        }

        // ── validation ──

        /// <summary>Ordered TMP tag-token comparison (the injection vector —
        /// localization-design §2.5 item 2). Tags must appear in the same
        /// order with identical content; a mismatch rejects the entry.</summary>
        private static bool TagsMatch(string source, string target)
        {
            if (target == null) return false;
            var a = ExtractTags(source);
            var b = ExtractTags(target);
            if (a.Count != b.Count) return false;
            for (int i = 0; i < a.Count; i++)
                if (!string.Equals(a[i], b[i], StringComparison.Ordinal)) return false;
            // Placeholder arity: {0}..{9} must survive verbatim.
            for (int d = 0; d <= 9; d++)
            {
                string ph = "{" + d + "}";
                if (CountOf(source, ph) != CountOf(target, ph)) return false;
            }
            return true;
        }

        private static List<string> ExtractTags(string s)
        {
            var tags = new List<string>();
            if (s == null) return tags;
            int i = 0;
            while (i < s.Length)
            {
                int lt = s.IndexOf('<', i);
                if (lt < 0) break;
                int gt = s.IndexOf('>', lt + 1);
                if (gt < 0) break;
                tags.Add(s.Substring(lt, gt - lt + 1));
                i = gt + 1;
            }
            return tags;
        }

        private static int CountOf(string s, string sub)
        {
            int n = 0, i = 0;
            while ((i = s.IndexOf(sub, i, StringComparison.Ordinal)) >= 0) { n++; i += sub.Length; }
            return n;
        }

        // ── pseudo-locale ──

        private static readonly Dictionary<char, char> _pseudoMap = new Dictionary<char, char>
        {
            ['a'] = 'à', ['e'] = 'é', ['i'] = 'ï', ['o'] = 'ó', ['u'] = 'ü',
            ['A'] = 'À', ['E'] = 'É', ['I'] = 'Ï', ['O'] = 'Ó', ['U'] = 'Ü',
            ['n'] = 'ñ', ['c'] = 'ç', ['y'] = 'ý', ['L'] = 'Ļ', ['r'] = 'ŕ',
        };

        private static string Pseudo(string s)
        {
            var sb = new StringBuilder(s.Length * 2 + 8);
            sb.Append('[');
            bool inTag = false;
            foreach (var ch in s)
            {
                if (ch == '<') inTag = true;
                if (inTag) { sb.Append(ch); if (ch == '>') inTag = false; continue; }
                char m;
                sb.Append(_pseudoMap.TryGetValue(ch, out m) ? m : ch);
            }
            // +40% width padding so every overflow shows at once (§2.8).
            int pad = Math.Max(2, s.Length * 2 / 5);
            sb.Append(' ');
            for (int i = 0; i < pad; i++) sb.Append('ẋ');
            sb.Append(']');
            return sb.ToString();
        }
    }
}
