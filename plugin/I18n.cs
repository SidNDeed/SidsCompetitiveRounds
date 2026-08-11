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

        /// <summary>Monotonic "the translation data behind Tr() changed"
        /// counter. Bumped by SetLocale, RegisterCatalogue, LoadCachedPack and
        /// a successfully installed ApplyPack — i.e. every write to the
        /// catalogue floor, to the server overlay, or to the current locale.
        ///
        /// ANY cache whose entries hold a TRANSLATED string must include this
        /// value in its key. The locale alone is NOT enough: an approved
        /// correction can be installed at any moment — the launch fetch, the
        /// offline cache, or (because SetLocale loads the cached pack for the
        /// new locale itself) from INSIDE a locale switch — so two strings
        /// cached under the same locale can legitimately differ. A cache that
        /// keys on locale only pins the old wording for the rest of the
        /// session, which is precisely what the live-correction pipeline
        /// exists to prevent.
        ///
        /// Deliberately biased toward OVER-bumping: a spurious bump costs one
        /// cache rebuild, a missed one is stale text with no recovery short of
        /// a relaunch. Plain static int behind a getter — read it as often as
        /// you like, on the main thread like everything else here.</summary>
        public static int CatalogueGeneration => _catalogueGeneration;
        private static int _catalogueGeneration;

        public static event Action LocaleChanged;

        /// <summary>Fired when the TRANSLATION DATA behind the current locale
        /// changed without the locale itself changing — i.e. a server pack (or
        /// its cached copy) was installed as the overlay. Subscribers must do
        /// nothing but request a repaint/rebuild (NativeUI.MarkDirty): a pack
        /// can land at any time, including from inside SetLocale, so a
        /// synchronous rebuild here would reenter the UI mid-switch.
        ///
        /// Separate from LocaleChanged ON PURPOSE: ApiClient.FetchI18nPack is
        /// a LocaleChanged subscriber, so firing that event from ApplyPack
        /// would recurse (fetch -> apply -> event -> fetch). Safe with zero
        /// subscribers (null-conditional, and every invoke is guarded).</summary>
        public static event Action CatalogueUpdated;

        public static void SetLocale(string locale)
        {
            locale = string.IsNullOrEmpty(locale) ? LOCALE_EN : locale.Trim().ToLowerInvariant();
            _pseudo = locale == LOCALE_PSEUDO;
            _locale = _pseudo ? LOCALE_EN : locale;
            // Bump BEFORE the staged switch below: anything that reads a
            // translated string while the switch runs (a coroutine resuming
            // between steps, a subscriber called from step 5) must already see
            // the new generation, or it caches the OLD wording under the NEW
            // key. LoadCachedPack/ApplyPack below bump again — monotonic, and
            // over-bumping is the safe direction (see CatalogueGeneration).
            _catalogueGeneration++;

            // STAGED SWITCH (Aug-3 live-switch recon). Order is load-bearing:
            // every consumer of LocaleChanged rebuilds UI, so all data layers
            // must already be correct for the NEW locale before it fires.
            //
            //   1. overlay swap + cached pack for the new locale
            //   2. re-arm the font fallback (new script range)
            //   3. apply the GAME's own locale (live, not just the pref)
            //   4. invalidate card caches (self-guarded on the GAME's locale)
            //   5. fire LocaleChanged (page rebuild)

            // (1) The overlay is per-locale; Tr already ignores one whose
            // locale doesn't match, but dropping it here means an A->B->A
            // round trip can never resurrect a stale generation, and the
            // cached pack for B loads NOW instead of at the next launch
            // (previously LoadCachedPack had exactly one caller, Plugin.Awake,
            // so a live switch rendered pack-only strings in English until a
            // fetch landed — one of the "three languages at once" layers).
            _serverOverlay = null;
            _serverOverlayLocale = null;
            try { LoadCachedPack(); } catch { }

            // (2) Install() is one-shot behind _installed and its only other
            // caller (UIFactory.InitFont) sets fontReady=true BEFORE calling
            // it, so a failed install is never retried for the session and
            // every non-ASCII glyph renders as nothing until a relaunch. A
            // locale switch is the one moment we know new scripts are needed.
            try { UnicodeFallback.OnLocaleChanged(_locale); } catch { }

            // (3) ONE SWITCH (localization-design §2.1.4 / Codex client find
            // 8): the mod's language also drives ROUNDS' own locale so native
            // card faces agree with the mod chrome. The old implementation
            // wrote ONLY the OPTION_LANGUAGE PlayerPref, which vanilla applies
            // at LAUNCH ONLY (OptionsData.InitializeLocalization, reached via
            // RegisterCallbackOptions(invokeNow:true)) — so mid-session the
            // options row repainted to the new language while the engine, and
            // every card name, stayed on the launch locale. We now assign
            // LocalizationSettings.SelectedLocale live as well. The old
            // comment's fear (its OnLocaleChanged calls ReleaseAllTables) is
            // real but harmless: ReleaseAllTables drops addressable handles
            // and the tables reload on next access, and CardInfo.CardName
            // resolves synchronously (WaitForCompletion) — a one-time hitch,
            // not breakage.
            bool gameLocaleChanged = false;
            if (!_pseudo)
                try { gameLocaleChanged = TryApplyRoundsLocale(_locale); } catch { }

            // (4) UNCONDITIONAL, deliberately. The card caches (and the baked
            // card SNAPSHOTS behind them) mirror the GAME's locale, not ours,
            // so the question that decides staleness is "has the game's locale
            // moved since we last SCANNED it" — which gameLocaleChanged cannot
            // answer: it only reports whether THIS call moved it. Gating on it
            // missed the case where the player had already switched ROUNDS'
            // own language in vanilla Options: the engine was already Spanish,
            // step (3) is a legitimate no-op, and the caches happily kept
            // serving the English text they were primed with.
            //
            // InvalidateCache asks the right question itself — its recorded
            // _syncedGameLocale against the live GetRoundsLocaleCode() — and
            // early-returns when they agree, so the "don't re-render every
            // snapshot for nothing" saving still happens. It costs one
            // reflection read, never a re-scan. The guard lives THERE rather
            // than here on purpose, so no call site can reintroduce this.
            try { CardTextLocalizer.InvalidateCache(); } catch { }

            // (5)
            try { LocaleChanged?.Invoke(); } catch { }
            Plugin.Log.LogInfo($"[I18N] locale set: {locale}"
                               + (gameLocaleChanged ? " (game locale followed)" : ""));
        }

        // Everything below is reflection-only. The csproj DOES reference
        // Unity.Localization now (GameLocaleInjector needs typed access —
        // ITableProvider's generic method cannot be implemented via
        // reflection), but these pre-existing reflection paths deliberately
        // stay as they are (§6.3 build-config note: touching them is out of
        // scope). Every lookup is null-guarded and logged; any failure
        // leaves ROUNDS' locale alone and the mod UI still switches.
        private const System.Reflection.BindingFlags PubStatic =
            System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static;

        private static Type FindLocalizationSettingsType()
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type t = null;
                try { t = asm.GetType("UnityEngine.Localization.Settings.LocalizationSettings"); }
                catch { }
                if (t != null) return t;
            }
            return null;
        }

        private static string LocaleCodeOf(object locale)
        {
            if (locale == null) return null;
            try
            {
                var ident = locale.GetType().GetProperty("Identifier")?.GetValue(locale);
                return ident?.GetType().GetProperty("Code")?.GetValue(ident) as string;
            }
            catch { return null; }
        }

        /// <summary>The locale code ROUNDS is CURRENTLY rendering in
        /// (LocalizationSettings.SelectedLocale), or null when the locale
        /// system is unavailable. Used by CardTextLocalizer to decide whether
        /// a mod-language switch actually invalidated its cache.</summary>
        internal static string GetRoundsLocaleCode()
        {
            try
            {
                Type ls = FindLocalizationSettingsType();
                if (ls == null) return null;
                var sel = ls.GetProperty("SelectedLocale", PubStatic)?.GetValue(null);
                return LocaleCodeOf(sel);
            }
            catch { return null; }
        }

        // Log-once-per-locale so a game that doesn't ship the language (uk/sv
        // have no vanilla locale at all) can't spam the log on every switch.
        private static readonly HashSet<string> _gameLocaleMissLogged =
            new HashSet<string>(StringComparer.Ordinal);

        /// <summary>Applies our locale to ROUNDS itself: resolves the matching
        /// Locale by CODE, assigns LocalizationSettings.SelectedLocale (LIVE —
        /// the pref alone is applied at launch only), and writes the
        /// OPTION_LANGUAGE PlayerPref as that locale's index IN THE SAME LIST
        /// vanilla indexes at startup (OptionsData.InitializeLocalization does
        /// `SelectedLocale = AvailableLocales.Locales[value]`), so the applied
        /// locale and the persisted one can never disagree. Finally it pushes
        /// the same index into vanilla's LIVE options state
        /// (SyncVanillaLanguageRow) — the pref is only re-read by vanilla at
        /// launch and on a panel enable, so an Options screen that is already
        /// open would otherwise keep stepping from its stale value.
        ///
        /// Resolution is BY CODE, never by list order: Locales is filled in
        /// addressables load-completion order (LocalesProvider.AddLocale) and
        /// may contain PseudoLocale entries, so a hardcoded/remembered index
        /// can name one language in the options row and select another in the
        /// engine. PseudoLocale rows are skipped for the same reason.
        ///
        /// Returns true ONLY when the engine's locale actually moved (verified
        /// by reading SelectedLocale back) — the caller uses that to decide
        /// whether the card-text caches are stale.</summary>
        private static bool TryApplyRoundsLocale(string twoLetter)
        {
            // INJECTED BASE-GAME LOCALES (uk/sv — localization-design §6.3
            // v2): the game ships no such Locale, and one must NEVER be
            // resolved from (or added to) AvailableLocales — vanilla persists
            // OPTION_LANGUAGE as an INDEX into that list and indexes it
            // unguarded at options init, so an out-of-range persisted index
            // throws every launch on an uninstalled mod (round-1 blocker 1).
            // Delegate to the injector: it selects its PRIVATE locale object
            // by reference once activation commits (miss-style log until
            // then). OPTION_LANGUAGE is never written and the vanilla options
            // row is never synced for these codes — the mod's own ModLanguage
            // config is the persistence, re-asserted each launch.
            if (GameLocaleInjector.IsInjectedCode(twoLetter))
                return GameLocaleInjector.ApplyInjected(twoLetter);

            // A vanilla-locale request means the player is switching AWAY
            // from an injected locale (or never used one): clear the
            // injector's session override latch (r2 find 7) so a later
            // switch back to uk/sv re-asserts. No-op when never active.
            GameLocaleInjector.OnVanillaLocaleRequested();

            Type ls = FindLocalizationSettingsType();
            if (ls == null)
            {
                LogGameLocaleMissOnce(twoLetter, "LocalizationSettings type not found");
                return false;
            }
            var avail = ls.GetProperty("AvailableLocales", PubStatic)?.GetValue(null);
            var locales = avail?.GetType().GetProperty("Locales")?.GetValue(avail)
                as System.Collections.IList;
            if (locales == null)
            {
                LogGameLocaleMissOnce(twoLetter, "AvailableLocales.Locales unavailable");
                return false;
            }

            // Exact code first ("es"), then a region variant ("es-ES") — a
            // bare StartsWith would also accept an unrelated longer code.
            int idx = -1; object target = null; string targetCode = null;
            for (int pass = 0; pass < 2 && idx < 0; pass++)
            {
                for (int i = 0; i < locales.Count; i++)
                {
                    var loc = locales[i];
                    if (loc == null) continue;
                    string tn = null;
                    try { tn = loc.GetType().Name; } catch { }
                    if (tn != null && tn.IndexOf("Pseudo", StringComparison.OrdinalIgnoreCase) >= 0)
                        continue;
                    string code = LocaleCodeOf(loc);
                    if (string.IsNullOrEmpty(code)) continue;
                    string lower = code.ToLowerInvariant();
                    bool hit = pass == 0
                        ? lower == twoLetter
                        : lower.StartsWith(twoLetter + "-", StringComparison.Ordinal);
                    if (!hit) continue;
                    idx = i; target = loc; targetCode = code;
                    break;
                }
            }
            if (idx < 0)
            {
                LogGameLocaleMissOnce(twoLetter, $"no Locale with code '{twoLetter}' among {locales.Count} available");
                return false;
            }

            string before = GetRoundsLocaleCode();

            // Persist FIRST so a throw inside the live assignment still leaves
            // the next launch correct (the pre-fix behaviour, never worse).
            try
            {
                UnityEngine.PlayerPrefs.SetInt("OPTION_LANGUAGE", idx);
                UnityEngine.PlayerPrefs.Save();
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] OPTION_LANGUAGE write failed: {ex.Message}"); }

            var selProp = ls.GetProperty("SelectedLocale", PubStatic);
            if (selProp == null || !selProp.CanWrite)
            {
                Plugin.Log.LogWarning($"[I18N] SelectedLocale not settable — ROUNDS stays on '{before}' until restart (pref={idx}/{targetCode})");
                return false;
            }
            try { selProp.SetValue(null, target); }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[I18N] SelectedLocale assign failed: {ex.Message} — ROUNDS follows at next launch (pref={idx}/{targetCode})");
                return false;
            }

            // The engine now renders the new language, and the pref carries it
            // to the next launch — but vanilla's options row holds its own
            // in-memory copy of that index and only reloads it from the pref on
            // a panel enable, so an ALREADY-OPEN Options screen still shows the
            // old language and its next arrow press steps from the stale value.
            // Push the index into vanilla's live settings object as well.
            //
            // Deliberately NOT reached by the two early returns above: in those
            // worlds nothing was applied live at all (no LocalizationSettings,
            // no settable property), the pref alone is the carrier, and driving
            // the engine through vanilla's options callback instead would be a
            // recovery path for a branch we have never seen taken.
            bool rowSynced = false;
            try { rowSynced = SyncVanillaLanguageRow(idx); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] options-row sync failed: {ex.Message}"); }

            string after = GetRoundsLocaleCode();
            // Bias toward "changed" when the read-back is UNKNOWN: a false
            // positive costs one wasted re-scan (and CardTextLocalizer's own
            // guard catches it anyway), while a false negative leaves every
            // card name in the previous language until restart — the exact bug
            // this is fixing. Residual, accepted: if the getter is broken while
            // the setter works, both reads are null and neither layer can tell.
            bool changed = after == null
                || !string.Equals(before, after, StringComparison.OrdinalIgnoreCase);
            Plugin.Log.LogInfo($"[I18N] ROUNDS locale: '{before ?? "?"}' -> '{after ?? "?"}' "
                               + $"(resolved '{twoLetter}' -> {targetCode} at index {idx}; OPTION_LANGUAGE={idx};"
                               + $" options row {(rowSynced ? "synced" : "not synced")})"
                               + (changed ? "" : " — already applied, no card re-render needed"));
            return changed;
        }

        /// <summary>Applies `idx` to ROUNDS' own OPTION_LANGUAGE setting — the
        /// IN-MEMORY value the vanilla options row displays, steps from with
        /// its arrows, and hands to the MultiOptions dropdown. Returns true
        /// when vanilla's live state now carries our index.
        ///
        /// Not a reflection poke: Assembly-CSharp is referenced and publicized,
        /// so this is vanilla's OWN mutation path — `SettingsData
        /// .CurrentValueOptions`, the exact property UISettingsValueOptions'
        /// arrows and MultiOptions.ClickRessButton assign. Setting it fires
        /// OnValueChangedOptions, whose subscribers are (1) the callback
        /// OptionsData.InitializeLocalization registered — `SelectedLocale =
        /// AvailableLocales.Locales[value]`, an idempotent no-op here because
        /// LocalizationSettings.SetSelectedLocale returns early when the
        /// requested locale is already selected (verified in the decompile;
        /// the caller has just assigned the same Locale) — and (2) the open
        /// row's UpdateValue, which is the repaint we are after. The setter
        /// then persists through SaveSettings.
        ///
        /// Reached via Optionshandler.instance.OptionsData, which is the
        /// per-handler CLONE (`Awake: Instantiate(m_optionsData)`) that owns
        /// the registered callback and the rows' subscriptions — the
        /// serialized asset is NOT the live object. `instance` is never
        /// cleared in OnDestroy, so the Unity fake-null compare below is load
        /// bearing: a destroyed handler means the rows are gone too and the
        /// next handler's InitOptions LoadSettings-es our pref anyway.
        ///
        /// Silent no-op when the options UI has not run Initialize() yet
        /// (m_settingsDictionary empty). GetSettingsData is avoided on purpose
        /// — it Debug.LogErrors on a miss, and "not initialized yet" is a
        /// normal state, not an error.
        ///
        /// WHAT STILL FIXES ITSELF WITHOUT THIS: the row is built from the pref
        /// at launch (Optionshandler.InitOptions -> OptionsData.Initialize ->
        /// SettingsData.LoadSettings), and vanilla ships a re-read on panel
        /// enable (UIUpdateOptionValuesOnEnable -> Optionshandler.UpdateValues
        /// -> LoadSettings) — that component's wiring is a scene detail we
        /// cannot verify from the assembly, so treat it as a likely second
        /// path, not a guarantee. The gap this method closes either way is
        /// "the panel is open across the switch".
        ///
        /// KNOWN GAP, pre-existing and NOT introduced here: the row's LABEL
        /// comes from vanilla's parallel `m_valueOptions` array indexed by the
        /// same integer vanilla indexes AvailableLocales.Locales with. If those
        /// two lists ever disagree in ORDER the label names one language while
        /// the engine renders another — which is equally true of the pref alone
        /// at launch (see this method's caller on resolving BY CODE). An
        /// out-of-RANGE index is skipped outright rather than left to throw
        /// inside vanilla's event invocation.</summary>
        private static bool SyncVanillaLanguageRow(int idx)
        {
            var handler = Optionshandler.instance;
            if (handler == null) return false;              // no options UI alive (or destroyed)
            var data = handler.OptionsData;
            if (data == null || data.m_settingsDictionary == null) return false;
            OptionsData.SettingsData sd;
            if (!data.m_settingsDictionary.TryGetValue("OPTION_LANGUAGE", out sd) || sd == null)
                return false;                               // Initialize() has not run yet

            var labels = sd.m_options.m_valueOptions;
            if (labels == null || idx < 0 || idx >= labels.Length)
            {
                Plugin.Log.LogInfo($"[I18N] options row left alone: index {idx} is outside vanilla's "
                                   + $"{(labels == null ? 0 : labels.Length)} language labels — its "
                                   + "CurrentStringValueOptions would throw. The pref is written, so "
                                   + "the row picks the index up the next time it loads settings.");
                return false;
            }

            // Compare the FIELD, not CurrentValueOptions: that getter returns 0
            // on a platform where the setting is not valid, which would read as
            // "already correct" for idx 0 on every call. Skipping a no-change
            // write also skips a pointless event fire and PlayerPrefs.Save (a
            // disk flush) on every locale set.
            if (sd.m_currentValueOptions == idx) return true;
            sd.CurrentValueOptions = idx;
            return true;
        }

        private static void LogGameLocaleMissOnce(string twoLetter, string why)
        {
            string k = (twoLetter ?? "?") + "|" + why;
            if (!_gameLocaleMissLogged.Add(k)) return;
            Plugin.Log.LogInfo($"[I18N] ROUNDS' own locale left unchanged for '{twoLetter}': {why}"
                               + " — mod UI still switches; card text stays in the game's language");
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
        // (wave-2 find 18). PackMaxStringLen must exceed the LONGEST source
        // key — the FFA How-It-Works doc is ~4.3k chars and its RU
        // translation runs longer, so 4000 made that key permanently
        // undeliverable via pack (Codex Aug-3 find 6). The proposal endpoint
        // (main.py i18n_propose) carries the matching 8000 cap.
        private const int PackMaxBytes = 2 * 1024 * 1024;
        private const int PackMaxEntries = 5000;
        private const int PackMaxStringLen = 8000;

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
            // Bumped on EVERY path we actually got this far on, not just a
            // successful ApplyPack: a caller may have dropped the previous
            // overlay before calling (SetLocale does exactly that), so "no
            // cache file" still means the effective translation data moved.
            // Keeping the bump here rather than only at that caller makes this
            // public entry point self-contained.
            _catalogueGeneration++;
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
                            // LF-canonical on install (line-ending invariant
                            // above): the server's copy of a source string can
                            // have travelled through a CRLF checkout, and Tr
                            // looks this layer up with an LF key.
                            s = NormalizeLf(s);
                            t = NormalizeLf(t);
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
                // The overlay IS the data Tr reads first — every cache holding
                // a translated string is now stale. Bump before the repaint
                // request below, so a subscriber that rebuilds synchronously
                // already keys on the new generation.
                _catalogueGeneration++;
                Plugin.Log.LogInfo($"[I18N] pack overlay installed: {overlay.Count} entries"
                                   + (dropped > 0 ? $" ({dropped} dropped: unknown key / tag mismatch)" : "")
                                   + $" [{(fromCache ? "cache" : "server")}]");
                // A pack that lands AFTER the page was built used to stay
                // invisible until the next rebuild (recon item d, layer 3):
                // installing the overlay changed no UI state, so those strings
                // rendered English for the rest of the session unless the user
                // happened to navigate away and back. Ask for a repaint.
                RequestUiRepaint();
                return true;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[I18N] pack rejected: {ex.Message}");
                return false;
            }
        }

        /// <summary>"The visible text may have changed — repaint." Fires
        /// CatalogueUpdated for anyone who wants it AND, as the built-in
        /// default, flips NativeUI's dirty flag itself, so the refresh works
        /// with zero subscribers wired (the event exists for surfaces that
        /// need more than a repaint). NOT LocaleChanged — that would recurse
        /// through ApiClient.FetchI18nPack (fetch -> apply -> event -> fetch).
        ///
        /// MarkDirty() is idempotent (`dirty = true`), so a subscriber that
        /// also calls it costs nothing. Each half is guarded separately: a
        /// throwing subscriber must not cost the repaint, and vice versa.</summary>
        private static void RequestUiRepaint()
        {
            try { CatalogueUpdated?.Invoke(); }
            catch (Exception hx) { Plugin.Log.LogWarning($"[I18N] CatalogueUpdated handler threw: {hx.Message}"); }
            try { NativeUI.MarkDirty(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] repaint request failed: {ex.Message}"); }
            // MarkDirty only re-runs the per-tab DATA refresh; every static
            // label built once in BuildPage would keep its old wording. Ask for
            // a full rebuild too — NativeUI defers it to a safe frame (r2 find 8).
            try { NativeUI.RequestCatalogueRebuild(); }
            catch (Exception ex) { Plugin.Log.LogWarning($"[I18N] rebuild request failed: {ex.Message}"); }
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
                // LF-canonical membership set — mirrors Tr's lookup key so a
                // multi-line source can be reached by a server correction.
                var set = new HashSet<string>(StringComparer.Ordinal);
                try { foreach (var k in I18nSourceKeys.Keys) set.Add(NormalizeLf(k)); } catch { }
                foreach (var kv in _catalogues)
                    foreach (var k in kv.Value.Keys) set.Add(NormalizeLf(k));
                _sourceKeySet = set;
            }
            return _sourceKeySet.Contains(NormalizeLf(s));
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
                if (two == "es" || two == "ru" || two == "uk" || two == "sv") return two;
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
                // LF-canonical on INSTALL as well as on lookup: the generated
                // catalogue is already LF (Python writes it), but a hand-added
                // entry in a CRLF-checked-out file would otherwise install a
                // key no normalized lookup can ever reach. Values normalize
                // too so a translated body can't carry stray CRs into TMP.
                cat[NormalizeLf(kv.Key)] = NormalizeLf(kv.Value);
                accepted++;
            }
            // The embedded floor moved. In practice this only runs at Install()
            // before any UI exists, but it is a PUBLIC entry point, so treat a
            // late registration as a real data change: bump the generation so
            // consumers' translated-string caches rebuild, and drop the
            // memoized source-key allowlist (IsEmbeddedKey, above) which is
            // built from _catalogues and would otherwise keep rejecting server
            // corrections for the keys just registered.
            _catalogueGeneration++;
            _sourceKeySet = null;
            Plugin.Log.LogInfo($"[I18N] catalogue '{locale}': +{accepted} entries" +
                               (rejected > 0 ? $" ({rejected} REJECTED on tag mismatch)" : ""));
        }

        // ── LINE-ENDING INVARIANT (Aug-3 recon item f) ──
        // CATALOGUE KEYS ARE LF. Any '\r' in a runtime string is an artifact
        // of the SOURCE FILE's line endings, never semantic.
        //
        // Why this exists: a C# verbatim literal (@"...") embeds the .cs
        // file's ACTUAL line endings, and the hand-written plugin sources are
        // checked out CRLF (no .gitattributes, core.autocrlf=true) — so
        // ModeInfoText's mode docs and NativeUI's tournament instruction
        // blocks produce "\r\n" at runtime. The extractor reads those same
        // files in Python and emits "\n" keys, and Tr is an ORDINAL dictionary
        // lookup, so every multi-line verbatim string was a GUARANTEED miss on
        // every machine, restart-invariant: the popup titles (single-line)
        // translated while their bodies stayed English. Normalizing at the
        // lookup — not rewriting the literals — keeps the English source
        // byte-identical, so no existing translation is re-keyed (#289).
        //
        // Hot path: an IndexOf('\r') scan, never an unconditional Replace.
        // Pure-ASCII single-line strings (virtually every UI label) pay one
        // vectorized scan and allocate nothing.
        private static string NormalizeLf(string s)
        {
            if (s == null || s.IndexOf('\r') < 0) return s;
            return s.Replace("\r\n", "\n").Replace('\r', '\n');
        }

        /// <summary>The chokepoint. English in, display-locale out; unknown
        /// strings pass through untouched (raw keys are never shown because
        /// the key IS the English source). TrF inherits the line-ending
        /// normalization below because it Tr's its TEMPLATE through here.</summary>
        public static string Tr(string english)
        {
            if (string.IsNullOrEmpty(english)) return english;
            if (_pseudo) return Pseudo(english);
            if (_locale == LOCALE_EN) return english;
            // LF-canonical lookup key; `english` itself is returned unchanged
            // on a miss so a CRLF source string keeps its own line endings.
            string key = NormalizeLf(english);
            // Server overlay first (approved corrections, live without a
            // release), then the embedded catalogue floor.
            var ov = _serverOverlay;
            if (ov != null && _serverOverlayLocale == _locale)
            {
                string o;
                if (ov.TryGetValue(key, out o) && !string.IsNullOrEmpty(o)) return o;
            }
            Dictionary<string, string> cat;
            if (_catalogues.TryGetValue(_locale, out cat))
            {
                string t;
                if (cat.TryGetValue(key, out t) && !string.IsNullOrEmpty(t)) return t;
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
            // NAMED smart-format holes ({ROOMCODE}) — combined brace grammar
            // mirroring the server's _i18n_validate (Aug 11, localization-
            // design §6.3): when the SOURCE carries named tokens the target
            // must carry the identical multiset, and the verified tokens are
            // stripped from BOTH sides before the numeric {N} validation runs
            // on the remainder. No client-namespace source carries one, so
            // mod-catalogue behavior is unchanged; the rule exists for the
            // base-game 'game' namespace (PROMPT_ROOMCODE).
            string holeSrc = source, holeTgt = target;
            var sNamed = ExtractNamedHoles(source);
            if (sNamed.Count > 0)
            {
                var tNamed = ExtractNamedHoles(target);
                if (sNamed.Count != tNamed.Count) return false;
                sNamed.Sort(StringComparer.Ordinal);
                tNamed.Sort(StringComparer.Ordinal);
                for (int i = 0; i < sNamed.Count; i++)
                    if (!string.Equals(sNamed[i], tNamed[i], StringComparison.Ordinal)) return false;
                holeSrc = StripNamedHoles(source);
                holeTgt = StripNamedHoles(target);
            }
            // Placeholder IDENTITY (Codex Aug-3 r2 find 4 + r3 find 2,
            // mirrors the server's _i18n_validate rule exactly): the target's
            // hole TOKENS must equal the source's as a multiset. This rejects
            // dropped holes, "{{1:F0}}" (renders literally via .NET brace
            // escaping), stray/truncated braces, "{10}" (throws at format
            // time), AND spec rewrites like "{1:F0}"->"{1:Q}" or "{1}" — a
            // typed spec against the real argument throws, so TrF would show
            // raw English with visible holes.
            bool tgtOk;
            var sh = ExtractHoleTokens(holeSrc, out _);
            var th = ExtractHoleTokens(holeTgt, out tgtOk);
            if (!tgtOk || sh.Count != th.Count) return false;
            sh.Sort(StringComparer.Ordinal);
            th.Sort(StringComparer.Ordinal);
            for (int i = 0; i < sh.Count; i++)
                if (!string.Equals(sh[i], th[i], StringComparison.Ordinal)) return false;
            return true;
        }

        /// <summary>Named-hole tokens: "{" + [A-Z] + [A-Z_]* + "}", exactly
        /// the server's _I18N_NAMED_HOLE regex, hand-scanned (this file uses
        /// no Regex). Returns them in order of appearance.</summary>
        private static List<string> ExtractNamedHoles(string s)
        {
            var toks = new List<string>();
            for (int i = 0; i < s.Length; i++)
            {
                if (s[i] != '{') continue;
                int j = i + 1;
                if (j >= s.Length || s[j] < 'A' || s[j] > 'Z') continue;
                j++;
                while (j < s.Length && ((s[j] >= 'A' && s[j] <= 'Z') || s[j] == '_')) j++;
                if (j < s.Length && s[j] == '}')
                {
                    toks.Add(s.Substring(i, j - i + 1));
                    i = j;
                }
            }
            return toks;
        }

        private static string StripNamedHoles(string s)
        {
            var toks = ExtractNamedHoles(s);
            if (toks.Count == 0) return s;
            string outp = s;
            foreach (var t in toks)
            {
                int at = outp.IndexOf(t, StringComparison.Ordinal);
                if (at >= 0) outp = outp.Remove(at, t.Length);
            }
            return outp;
        }

        /// <summary>Exact hole tokens ("{0}", "{1:F0}") in order; wellFormed
        /// goes false on any brace that does not form a {N}/{N:spec} hole
        /// (spec brace-free). Sources never carry literal braces, so a
        /// conforming target can never make string.Format throw or
        /// brace-escape.</summary>
        private static List<string> ExtractHoleTokens(string s, out bool wellFormed)
        {
            var toks = new List<string>();
            wellFormed = true;
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '}') { wellFormed = false; break; }
                if (c != '{') continue;
                if (i + 2 >= s.Length) { wellFormed = false; break; }
                char d = s[i + 1];
                if (d < '0' || d > '9') { wellFormed = false; break; }
                int j = i + 2;
                if (s[j] == ':')
                {
                    j++;
                    while (j < s.Length && s[j] != '}' && s[j] != '{') j++;
                    if (j >= s.Length || s[j] != '}') { wellFormed = false; break; }
                }
                else if (s[j] != '}') { wellFormed = false; break; }
                toks.Add(s.Substring(i, j - i + 1));
                i = j;
            }
            return toks;
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

        // KNOWN QUIRK (dev-only, accepted — Codex Aug-3 find 9): sites that
        // Tr/TrF explicitly and then pass the result through a chokepoint
        // (CreateText/SetText/ShowNotification) double-apply the PSEUDO
        // transform under the qps locale — nested brackets + doubled padding.
        // Real locales are unaffected: a translated string simply misses the
        // catalogue on the second lookup and passes through unchanged.
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
