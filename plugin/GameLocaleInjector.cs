using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.Localization;
using UnityEngine.Localization.Metadata;
using UnityEngine.Localization.Pseudo;
using UnityEngine.Localization.Settings;
using UnityEngine.Localization.Tables;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.ResourceManagement.ResourceLocations;

namespace CompetitiveRounds
{
    /// <summary>
    /// Base-game locale injector for languages ROUNDS does not ship (uk/sv) —
    /// localization-design §6.3 v2, hardened per the round-2 and round-3
    /// reviews.
    ///
    /// The whole design hangs on two invariants:
    ///
    ///   1. PRIVATE LOCALE — our Locale objects are NEVER added to
    ///      AvailableLocales (round-1 blocker 1: vanilla persists
    ///      OPTION_LANGUAGE as an INDEX into that list and indexes it
    ///      unguarded at options init, so a member locale would brick an
    ///      uninstalled mod's launch). SetSelectedLocale has no membership
    ///      check; table lookup, formatting and fallback all use the object +
    ///      identifier directly (verified in the decompile).
    ///
    ///   2. TABLE DELIVERY VIA ITableProvider — consulted on every NAMED
    ///      table load BEFORE addressables and immune to ReleaseAllTables, so
    ///      there is no registration to wipe and no subscriber ordering to
    ///      win (round-1 blocker 2). Installed on the STRING database only;
    ///      font/asset tables ride FallbackLocale metadata (uk->ru) instead.
    ///
    /// ACTIVATION is a lifecycle-durable static state machine (r2 find 8):
    /// requested -> waiting-init -> loading-en -> building -> committed /
    /// failed. All progress lives in static fields and is stepped from the
    /// persistent behaviour's Update tick — a destroyed-and-respawned
    /// behaviour resumes stepping wherever activation was, unlike the
    /// coroutine the first design draft parked on Plugin.Instance. Nothing
    /// globally observable (provider, UseFallback, locale exposure) happens
    /// before the single commit step; every earlier failure releases the
    /// acquired handles, destroys the built tables, restores any mutated
    /// global, logs ONE line and parks in Failed (no retry storm — only a
    /// mod-language change re-requests).
    ///
    /// GENERATIONS (r3 find 2). A mod-language switch between two injected
    /// codes (uk -> sv) used to tear the committed machinery down BEFORE the
    /// replacement existed: a failed sv build then left the engine selected on
    /// a retired private uk locale that nothing served, so every game string
    /// fell through to uk's ru fallback — Russian text — and a switch back
    /// built a SECOND object also named "uk", which SetSelectedLocale's
    /// name+code early return refuses to select, wedging the readback check
    /// into a permanent conflict. Each attempt is now its own Generation with
    /// a generation-unique Unity object name; the committed one keeps serving
    /// until a replacement has passed every check, at which point the swap is
    /// a single field assignment. A build that fails leaves the committed
    /// generation untouched, and a swap whose re-assert is refused rolls back
    /// to it rather than stranding the engine on an unserved locale.
    ///
    /// COMPAT GATE (r3 find 4). Awake requests activation, but Step() is inert
    /// until Plugin's other-mod compatibility check clears ~3s in: modDisabled
    /// returns from Update ABOVE the Step() call, so anything acquired or
    /// committed before that verdict could never be stepped, released or
    /// re-asserted again. Shutdown() is the idempotent counterpart the disable
    /// branch calls.
    ///
    /// ZERO FOOTPRINT when ModLanguage is not uk/sv: nothing is created,
    /// installed or subscribed; Step() is three bool/enum compares; the
    /// OptionsData patch pair maintains static bools and early-returns
    /// (including the one read of SelectedLocale, which is skipped entirely
    /// while we hold no subscriber). en/es/ru sessions behave byte-identically.
    /// </summary>
    internal static class GameLocaleInjector
    {
        private const string TableDefault = "StringTableDefault";
        private const string TableCards = "StringTableCards";

        /// <summary>The activation ladder (r2 find 8). Requested/WaitingInit/
        /// LoadingEn/Building are the in-flight states Step() advances for the
        /// PENDING generation; Committed means a generation is serving and
        /// nothing is in flight; Failed parks a build that could not complete
        /// (until a mod-language change re-requests).</summary>
        private enum InjState { Idle, Requested, WaitingInit, LoadingEn, Building, Committed, Failed }

        /// <summary>One activation attempt and everything it owns (r3 find 2).
        /// Holding these per attempt — instead of in one set of statics — is
        /// what lets a committed generation keep serving while its replacement
        /// is built, and what keeps the replaced generation's en references
        /// separately releasable at retirement.</summary>
        private sealed class Generation
        {
            internal readonly int Id;
            internal readonly string Code;          // "uk" / "sv"
            internal Locale Locale;                 // PRIVATE locale; never in AvailableLocales
            internal StringTable Default;
            internal StringTable Cards;
            // English source tables. We Acquire exactly ONE independent
            // reference per handle (r2 find 8: balanced ownership) so the
            // SharedData our runtime tables borrow outlives ReleaseAllTables
            // for as long as this generation exists.
            internal AsyncOperationHandle<StringTable> EnDefault;
            internal AsyncOperationHandle<StringTable> EnCards;
            internal bool EnDefaultAcquired;
            internal bool EnCardsAcquired;

            internal Generation(int id, string code) { Id = id; Code = code; }
        }

        private static InjState _state = InjState.Idle;
        private static int _genCounter;
        private static Generation _active;      // committed and serving; null until the first commit
        private static Generation _pending;     // in flight; null when nothing is being built
        private static string _enCode;          // the vanilla en locale's real code ("en-US")

        // en-locale string-table collection enumeration (r2 find 9). We own
        // this handle outright (we created it) — released as soon as parsed.
        private static AsyncOperationHandle<IList<IResourceLocation>> _locationsHandle;
        private static bool _locationsPending;

        private static ScrTableProvider _provider;   // created once, installed only at commit
        private static bool _providerInstalled;      // WE installed it (never uninstall a foreign one)
        private static bool _subscribed;             // SelectedLocaleChanged handler live

        // UseFallback mutations, recorded at the FIRST commit that had to flip
        // them so a later generation's commit cannot overwrite the real prior
        // value. Restored only by Shutdown — a running session that committed
        // once needs them on for every generation.
        private static bool _ufStringMutated, _ufAssetMutated;
        private static bool _ufStringPrior, _ufAssetPrior;

        // r2 find 6 fail-closed flag: SetSelectedLocale readback did not
        // return OUR object once — another locale owner is fighting us. Log
        // once, then never retry for the session (a retry loop against
        // another mod's re-assert would ping-pong the whole locale system).
        private static bool _conflicted;

        // r2 find 7 session override: the USER picked a vanilla locale on the
        // options row while uk/sv was active OR being activated. Their choice
        // stands until the next mod-language change (ApplyInjected clears it)
        // or relaunch (static). Without this, every Optionshandler re-open
        // re-runs InitializeLocalization on a fresh OptionsData clone and our
        // postfix would stomp the user's pick.
        private static bool _vanillaOverrideLatch;

        private static bool _inReassert;             // our own SetSelectedLocale in flight
        private static bool _compatCleared;          // r3 find 4: Plugin's other-mod check passed
        private static bool _shutdown;               // r3 find 4: terminal, idempotent

        // Every private Locale we ever created, alive or retired. Identity
        // membership is what distinguishes "the engine is on one of OURS"
        // from "the engine is on a vanilla locale" in the restore and latch
        // paths — a name/code test would also match another mod's own uk.
        // Bounded by the number of mod-language switches in a session.
        private static readonly List<Locale> _ourLocales = new List<Locale>();

        /// <summary>Set/cleared by GameLocaleOptionsInitPatch around vanilla's
        /// OptionsData.InitializeLocalization, whose invoke-now callback
        /// selects Locales[savedIndex] SYNCHRONOUSLY — the SelectedLocaleChanged
        /// handler must not read that programmatic selection as a user action.
        /// The window fences a SYNCHRONOUS delivery only; see _awaitedInitLocale
        /// for the deferred one.</summary>
        internal static bool InOptionsInit;

        // r3 find 1. LocalizationSettings.SendLocaleChangedEvents releases and
        // RE-CREATES the initialization operation, then dispatches the
        // SelectedLocaleChanged callbacks only if that fresh operation is
        // already Succeeded — otherwise it hands them to
        // InitializeAndCallSelectedLocaleChangedCoroutine, i.e. a LATER frame.
        // The shipped settings asset has InitializeSynchronously = 0 and the
        // fresh operation preloads the newly selected locale's tables, so the
        // deferred path is the normal one. The SELECTION itself is still
        // synchronous, so the patch bracket can snapshot what vanilla's init
        // left selected and consume that one late callback here instead of
        // mis-reading it as a user action (which would latch the override and
        // permanently refuse re-assertion).
        private static bool _initCallbackExpected;   // armed by the prefix, cleared by a synchronous delivery
        private static Locale _awaitedInitLocale;    // the one late callback we owe, or null
        private static bool _optionsInitLeaveDone;   // postfix ran; keeps the finalizer from re-arming

        // Once-per-(locale,state) "not ready yet" log — mirrors I18n's
        // LogGameLocaleMissOnce style so a pending activation can't spam.
        private static readonly HashSet<string> _pendingLogged =
            new HashSet<string>(StringComparer.Ordinal);
        private static bool _waitingInitLogged;

        internal static bool IsInjectedCode(string code) => code == "uk" || code == "sv";

        /// <summary>The code activation is currently working toward: the
        /// in-flight generation's if one exists, otherwise the committed
        /// one's. I18n.SetLocale assigns its own _locale BEFORE driving the
        /// vanilla switch, so this comparison reads a mod-initiated move away
        /// from uk/sv as "not wanted" at every decision site.</summary>
        private static string TargetCode =>
            _pending != null ? _pending.Code : (_active != null ? _active.Code : null);

        private static bool ModWantsTarget()
        {
            string c = TargetCode;
            return c != null && string.Equals(I18n.Locale, c, StringComparison.Ordinal);
        }

        /// <summary>Generation-unique Unity object name (r3 find 2).
        /// SetSelectedLocale early-returns on name+code equality even for
        /// DIFFERENT objects, so a second "uk" generation built after the
        /// first was retired could never be selected — the readback check
        /// would see the retired object and declare a permanent conflict. The
        /// "(SCR#n)" suffix also keeps another mod's own "uk" locale (usually
        /// named by CultureInfo.EnglishName) from making our selection a
        /// silent no-op.</summary>
        private static string LocaleObjectName(string code, int gen) => code + " (SCR#" + gen + ")";

        private static bool IsOurLocale(Locale l)
        {
            if (l == null) return false;
            for (int i = 0; i < _ourLocales.Count; i++)
                if (ReferenceEquals(_ourLocales[i], l)) return true;
            return false;
        }

        private static Locale ReadSelectedLocale()
        {
            try { return LocalizationSettings.SelectedLocale; } catch { return null; }
        }

        // ── I18n entry points ────────────────────────────────────────────

        /// <summary>I18n.TryApplyRoundsLocale's delegate for uk/sv: request
        /// activation and, when already committed, re-assert immediately.
        /// Returns true when ROUNDS is verifiably rendering our locale after
        /// the call (the caller only uses this for its log suffix; card-cache
        /// invalidation is unconditional at the call site and force-handled
        /// inside the central re-assert).</summary>
        internal static bool ApplyInjected(string code)
        {
            if (!IsInjectedCode(code)) return false;
            // A mod-language change clears the session override (r2 find 7):
            // explicitly choosing uk/sv in the mod picker outranks a vanilla
            // options-row pick made earlier in the session.
            _vanillaOverrideLatch = false;
            RequestActivation(code);
            if (_pending == null && _active != null
                && string.Equals(_active.Code, code, StringComparison.Ordinal))
                return CentralReassert("apply");
            string k = code + "|" + _state;
            if (_pendingLogged.Add(k))
                Plugin.Log.LogInfo($"[GAMELOC] ROUNDS' own locale left unchanged for '{code}': "
                                   + $"injector state {_state} — mod UI still switches; game text "
                                   + "follows when activation commits");
            return false;
        }

        /// <summary>Called by I18n.TryApplyRoundsLocale when a VANILLA locale
        /// is being applied — i.e. the mod is switching away from uk/sv (or
        /// never used one). Only the session override latch is cleared; the
        /// committed machinery (provider, pinned en handles) stays installed
        /// and dormant — the provider answers only for OUR locale object, so
        /// a vanilla session leaves it untouched, and a switch back to the
        /// same injected code is then a pure re-assert.</summary>
        internal static void OnVanillaLocaleRequested()
        {
            _vanillaOverrideLatch = false;
        }

        /// <summary>Arm (or re-arm) activation for an injected code. Safe to
        /// call repeatedly — in-flight/committed activation for the same code
        /// is idempotent. The only caller is the SetLocale path, so a Failed
        /// re-request is user-action-bounded, never a tick-driven retry storm.
        /// A switch to a DIFFERENT injected code starts a fresh generation and
        /// deliberately leaves the committed one serving (r3 find 2).</summary>
        internal static void RequestActivation(string code)
        {
            if (!IsInjectedCode(code) || _shutdown) return;
            if (_pending != null && string.Equals(_pending.Code, code, StringComparison.Ordinal))
                return; // already building this code
            if (_pending != null)
                AbandonPending($"superseded by '{code}'"); // the committed generation is untouched
            if (_active != null && string.Equals(_active.Code, code, StringComparison.Ordinal))
            {
                // Already committed and serving this code — nothing to build;
                // the caller's re-assert is the whole operation.
                _state = InjState.Committed;
                return;
            }
            _conflicted = false;
            _waitingInitLogged = false;
            _pending = new Generation(++_genCounter, code);
            _state = InjState.Requested;
            Plugin.Log.LogInfo($"[GAMELOC] activation requested for '{code}' (generation {_pending.Id})");
        }

        /// <summary>r3 find 4: Plugin's other-mod compatibility check passed,
        /// so activation may start doing globally observable work. Everything
        /// before this point is bookkeeping in our own statics.</summary>
        internal static void OnCompatCleared()
        {
            if (_shutdown || _compatCleared) return;
            _compatCleared = true;
            if (_state == InjState.Requested)
                Plugin.Log.LogInfo("[GAMELOC] compatibility check cleared — resuming activation");
        }

        /// <summary>r3 find 4: terminal, idempotent teardown, called when the
        /// mod disables itself. Order is load-bearing — the vanilla locale is
        /// restored FIRST, while the provider is still installed, so there is
        /// never a frame where one of our private locales is selected with
        /// nothing able to serve its tables (the ru-fallback / Russian-text
        /// failure mode). Only then do the provider, the subscription, the
        /// UseFallback mutations and the retained en references go.</summary>
        internal static void Shutdown(string reason)
        {
            if (_shutdown) return;
            _shutdown = true;
            try { RestoreVanillaSelection("shutdown"); } catch { }
            if (_subscribed)
            {
                try { LocalizationSettings.SelectedLocaleChanged -= OnSelectedLocaleChanged; } catch { }
                _subscribed = false;
            }
            if (_providerInstalled)
            {
                try
                {
                    var sdb = LocalizationSettings.StringDatabase;
                    if (sdb != null && ReferenceEquals(sdb.TableProvider, _provider))
                        sdb.TableProvider = null;
                }
                catch { }
                _providerInstalled = false;
            }
            try
            {
                var sdb = LocalizationSettings.StringDatabase;
                if (_ufStringMutated && sdb != null) sdb.UseFallback = _ufStringPrior;
                var adb = LocalizationSettings.AssetDatabase;
                if (_ufAssetMutated && adb != null) adb.UseFallback = _ufAssetPrior;
            }
            catch { }
            _ufStringMutated = false;
            _ufAssetMutated = false;
            ReleaseEnHandles(_active);
            ReleaseEnHandles(_pending);
            ReleaseLocations();
            _active = null;
            _pending = null;
            _state = InjState.Idle;
            _awaitedInitLocale = null;
            Plugin.Log.LogInfo($"[GAMELOC] shut down: {reason}");
        }

        // ── State machine (stepped from CompetitiveRoundsBehaviour.Update) ──

        /// <summary>One bounded step per frame. All state is static (r2 find
        /// 8): the persistent behaviour can be destroyed and respawned at any
        /// scene transition and the next instance resumes here unchanged.</summary>
        internal static void Step()
        {
            if (_shutdown) return;
            // r3 find 4: inert until the other-mod check clears. A Requested
            // generation simply waits here — no handle acquired, nothing
            // installed, nothing to unwind if the check disables the mod.
            if (!_compatCleared) return;
            if (_state == InjState.Idle || _state == InjState.Committed || _state == InjState.Failed)
                return; // the zero-footprint fast path
            try
            {
                switch (_state)
                {
                    case InjState.Requested: StepRequested(); break;
                    case InjState.WaitingInit: StepWaitingInit(); break;
                    case InjState.LoadingEn: StepLoadingEn(); break;
                    case InjState.Building: BuildAndCommit(); break;
                }
            }
            catch (Exception ex)
            {
                Abort("unexpected: " + ex.Message);
            }
        }

        private static void StepRequested()
        {
            // HasSettings (not Instance): Instance CREATES a default settings
            // asset when none is loaded yet, which would wedge the real one.
            if (!LocalizationSettings.HasSettings) return;
            // r3 find 3: subscribe HERE, not at commit. A user who changes the
            // vanilla language row while the en tables are still loading made
            // a deliberate choice; with the subscriber installed only at
            // commit there was nothing to latch it and the commit re-assert
            // silently overwrote them. Programmatic init changes stay fenced —
            // synchronously by InOptionsInit, and for the deferred dispatch by
            // the _awaitedInitLocale marker the patch pair arms.
            Subscribe();
            _state = InjState.WaitingInit;
            if (!_waitingInitLogged)
            {
                _waitingInitLogged = true;
                Plugin.Log.LogInfo("[GAMELOC] waiting for LocalizationSettings initialization");
            }
        }

        private static void StepWaitingInit()
        {
            var init = LocalizationSettings.InitializationOperation;
            if (!init.IsDone) return;
            // Status == Succeeded, never merely IsDone (r2 find 8): a Failed
            // init is Done too, and building tables against a half-initialized
            // database would commit garbage.
            if (init.Status != AsyncOperationStatus.Succeeded)
            {
                Abort($"LocalizationSettings initialization ended {init.Status}");
                return;
            }
            BeginLoadEn();
        }

        private static void BeginLoadEn()
        {
            var gen = _pending;
            if (gen == null) { ParkNoPending(); return; }
            var sdb = LocalizationSettings.StringDatabase;
            if (sdb == null) { Abort("StringDatabase unavailable"); return; }
            var en = ResolveVanillaLocale("en");
            if (en == null) { Abort("no vanilla 'en' locale in AvailableLocales"); return; }
            _enCode = en.Identifier.Code; // "en-US" on the shipped build

            // Load the en tables through the database's own named path (the
            // r2 "unnecessary complexity" note prefers this over hard-coded
            // Addressables addresses), then Acquire ONE independent reference
            // per handle so the SharedData our runtime tables borrow can
            // never be unloaded under them by ReleaseAllTables (r2 find 8 —
            // confirmed: ReleaseAllTables does not invalidate an
            // independently retained handle). Acquire exactly once per
            // generation; released exactly once when that generation aborts,
            // is abandoned, is retired after a swap, or at shutdown.
            gen.EnDefault = sdb.GetTableAsync(TableDefault, en);
            Addressables.ResourceManager.Acquire(gen.EnDefault);
            gen.EnDefaultAcquired = true;
            gen.EnCards = sdb.GetTableAsync(TableCards, en);
            Addressables.ResourceManager.Acquire(gen.EnCards);
            gen.EnCardsAcquired = true;

            // r2 find 9 fail-closed probe: enumerate the en locale's STRING
            // table collections by the same label+type query the game's own
            // LoadAllTablesOperation uses (label "Locale-<code>", filtered to
            // StringTable — every vanilla named load depends on exactly this
            // label/type indexing, verified in AddressablesInterface). If a
            // game update ever ships a third string collection, the catalogue
            // has no coverage for it and uk's ru fallback would serve RUSSIAN
            // for its keys — so the whole activation must abort (game stays
            // English) rather than leak.
            _locationsHandle = Addressables.LoadResourceLocationsAsync(
                (object)("Locale-" + _enCode), typeof(StringTable));
            _locationsPending = true;

            _state = InjState.LoadingEn;
        }

        private static void StepLoadingEn()
        {
            var gen = _pending;
            if (gen == null) { ParkNoPending(); return; }
            if (!gen.EnDefault.IsDone || !gen.EnCards.IsDone) return;
            if (_locationsPending && !_locationsHandle.IsDone) return;

            // Unknown-collection gate first (r2 find 9): the set must be
            // EXACTLY {StringTableDefault, StringTableCards}.
            if (_locationsHandle.Status != AsyncOperationStatus.Succeeded
                || _locationsHandle.Result == null)
            {
                Abort("en collection enumeration failed: " + _locationsHandle.Status);
                return;
            }
            var found = new HashSet<string>(StringComparer.Ordinal);
            string suffix = "_" + _enCode;
            foreach (var loc in _locationsHandle.Result)
            {
                if (loc == null) continue;
                string key = loc.PrimaryKey ?? "";
                // Table addresses are "<Collection>_<code>" (AddressHelper).
                // Anything not matching that shape stays as-is and fails the
                // exact-set compare below — the fail-closed direction.
                found.Add(key.EndsWith(suffix, StringComparison.Ordinal)
                    ? key.Substring(0, key.Length - suffix.Length)
                    : key);
            }
            ReleaseLocations();
            if (!(found.Count == 2 && found.Contains(TableDefault) && found.Contains(TableCards)))
            {
                Abort("en string-table collections {" + string.Join(", ", found)
                      + "} != {" + TableDefault + ", " + TableCards + "} — a new/renamed "
                      + "collection has no catalogue coverage; failing closed");
                return;
            }

            if (gen.EnDefault.Status != AsyncOperationStatus.Succeeded || gen.EnDefault.Result == null)
            { Abort("en " + TableDefault + " load: " + gen.EnDefault.Status); return; }
            if (gen.EnCards.Status != AsyncOperationStatus.Succeeded || gen.EnCards.Result == null)
            { Abort("en " + TableCards + " load: " + gen.EnCards.Status); return; }

            _state = InjState.Building;
        }

        /// <summary>Build both runtime tables, verify everything, then run
        /// the single COMMIT step. Ordering is load-bearing: the provider
        /// install, the UseFallback writes and the generation swap happen ONLY
        /// after every verification passed; any failure before that
        /// releases/destroys/restores, leaves the previously committed
        /// generation exactly as it was, and parks in Failed.</summary>
        private static void BuildAndCommit()
        {
            var gen = _pending;
            if (gen == null) { ParkNoPending(); return; }
            var sdb = LocalizationSettings.StringDatabase;
            var adb = LocalizationSettings.AssetDatabase;
            if (sdb == null || adb == null) { Abort("databases unavailable at build"); return; }

            // r2 find 5: one replace-only provider slot per database. If
            // another mod owns it, overwriting would break that mod (and our
            // own later disable would break us both) — ABORT, never replace.
            var existingProvider = sdb.TableProvider;
            if (existingProvider != null && !ReferenceEquals(existingProvider, _provider))
            {
                Abort("a foreign ITableProvider is installed ("
                      + existingProvider.GetType().FullName + ") — refusing to overwrite it");
                return;
            }

            // FallbackLocale target: uk -> vanilla ru (Gravity has no
            // Ukrainian glyphs; the ru locale's Roboto SDF set has all 8 —
            // fonts ride ru's ASSET tables via per-entry fallback); sv ->
            // vanilla en (Gravity covers Swedish natively; the metadata only
            // exists so future asset lookups resolve deterministically).
            // String-side fallback can never fire for either: the tables
            // below carry an explicit entry for EVERY en key.
            var fb = ResolveVanillaLocale(gen.Code == "uk" ? "ru" : "en");
            if (fb == null) { Abort("no vanilla fallback locale for '" + gen.Code + "'"); return; }

            var cat = GameLocaleCatalogues.ForLocale(gen.Code);
            if (cat == null) { Abort("no embedded catalogue for '" + gen.Code + "'"); return; }

            // PRIVATE locale with a generation-unique Unity object name — see
            // LocaleObjectName (r2 find 6 / r3 find 2). CreateLocale names it
            // "Ukrainian"/"Swedish"; override before anything can observe it.
            var locale = Locale.CreateLocale(gen.Code);
            locale.name = LocaleObjectName(gen.Code, gen.Id);
            locale.hideFlags = HideFlags.HideAndDontSave;
            locale.Metadata.AddMetadata(new FallbackLocale(fb));

            StringTable builtDefault = null, builtCards = null;
            try
            {
                builtDefault = BuildTable(gen.EnDefault.Result, locale, cat, gen);
                builtCards = BuildTable(gen.EnCards.Result, locale, cat, gen);
            }
            catch (Exception ex)
            {
                DestroyPreCommit(locale, builtDefault, builtCards);
                Abort("table build threw: " + ex.Message);
                return;
            }
            // Verified build: entry count == en entry count (every key gets
            // an entry — target or explicit current-English self-heal — so
            // STRING fallback never fires; r2 find 5).
            if (builtDefault == null || builtCards == null
                || builtDefault.Count != gen.EnDefault.Result.Count
                || builtCards.Count != gen.EnCards.Result.Count)
            {
                DestroyPreCommit(locale, builtDefault, builtCards);
                Abort("built entry counts "
                      + (builtDefault == null ? "null" : builtDefault.Count.ToString()) + "/"
                      + (builtCards == null ? "null" : builtCards.Count.ToString())
                      + " != en " + gen.EnDefault.Result.Count + "/" + gen.EnCards.Result.Count);
                return;
            }

            // ── COMMIT ──  (everything above verified; from here the steps
            // are globally observable and must each roll back on failure)

            // UseFallback precondition (r2 find 5): with AssetDatabase
            // .UseFallback false, the uk font ASSET lookup resolves to a
            // SUCCESSFUL NULL — invisible text, no error. Set if settable,
            // READ BACK, abort if either still reads false.
            bool priorStringUf = sdb.UseFallback;
            bool priorAssetUf = adb.UseFallback;
            bool mutStringUf = false, mutAssetUf = false;
            if (!sdb.UseFallback) { sdb.UseFallback = true; mutStringUf = true; }
            if (!adb.UseFallback) { adb.UseFallback = true; mutAssetUf = true; }
            if (!sdb.UseFallback || !adb.UseFallback)
            {
                if (mutStringUf) sdb.UseFallback = priorStringUf;
                if (mutAssetUf) adb.UseFallback = priorAssetUf;
                DestroyPreCommit(locale, builtDefault, builtCards);
                Abort($"UseFallback readback false (string={sdb.UseFallback}, asset={adb.UseFallback})");
                return;
            }

            // Provider install — STRING database only, and verified back by
            // reference (r2 find 5). The asset database never gets one.
            if (_provider == null) _provider = new ScrTableProvider();
            if (sdb.TableProvider == null)
            {
                sdb.TableProvider = _provider;
                _providerInstalled = true;
            }
            if (!ReferenceEquals(sdb.TableProvider, _provider))
            {
                if (_providerInstalled) { sdb.TableProvider = null; _providerInstalled = false; }
                if (mutStringUf) sdb.UseFallback = priorStringUf;
                if (mutAssetUf) adb.UseFallback = priorAssetUf;
                DestroyPreCommit(locale, builtDefault, builtCards);
                Abort("provider readback is not ours after install");
                return;
            }
            // Record the mutation ONCE (the first commit that had to flip it
            // holds the real prior value; a later generation's commit sees
            // them already true and must not overwrite the record).
            if (mutStringUf && !_ufStringMutated) { _ufStringMutated = true; _ufStringPrior = priorStringUf; }
            if (mutAssetUf && !_ufAssetMutated) { _ufAssetMutated = true; _ufAssetPrior = priorAssetUf; }

            // ── ATOMIC SWAP (r3 find 2) ──  A single assignment moves the
            // provider's answer, the re-assert target and I18n's exposure from
            // the previous generation to this one. Until this line the previous
            // generation was still serving — a build that failed anywhere above
            // returned through Abort and left it exactly as it was, which is
            // the whole point: a failed replacement must never cost the player
            // the language they already had.
            gen.Locale = locale;
            gen.Default = builtDefault;
            gen.Cards = builtCards;
            _ourLocales.Add(locale);
            var previous = _active;
            _active = gen;
            _pending = null;
            _state = InjState.Committed;
            Subscribe(); // normally already live from StepRequested
            Plugin.Log.LogInfo($"[GAMELOC] '{gen.Code}' committed (generation {gen.Id}): "
                               + $"{builtDefault.Count}+{builtCards.Count} entries, fallback -> "
                               + $"{fb.Identifier.Code}, provider installed"
                               + (mutStringUf || mutAssetUf ? " (UseFallback was flipped on)" : ""));

            // Activation commit is a central-re-assert site. Honor the
            // session override (the user may have picked a vanilla locale
            // while we were building — r3 find 3 makes that observable now)
            // and the current mod language (the player may have switched to
            // es mid-activation — the committed machinery then just sits
            // dormant).
            if (!_vanillaOverrideLatch && ModWantsTarget()) CentralReassert("commit");

            // Retiring the replaced generation is where "atomically swap OR
            // restore a verified vanilla locale" lands: RetireGeneration first
            // checks whether the engine is somehow STILL selected on it and,
            // if so, moves to vanilla English before the provider stops
            // answering for it. Rolling the swap back instead was considered
            // and is unreachable-or-wrong: the two ways CentralReassert can
            // refuse are (a) the provider slot is no longer ours, which leaves
            // the previous generation just as unservable as this one, and
            // (b) another owner won the selection, which leaves the engine on
            // THEIR locale, not on the previous one.
            if (previous != null) RetireGeneration(previous, "replaced by generation " + gen.Id);
        }

        /// <summary>One runtime StringTable for one collection. SharedData is
        /// BORROWED from the en table and never mutated: entries are added by
        /// KEY ID (the AddEntry(long,..) overload never touches SharedData;
        /// the string overload's FindKeyId(addKey:true) path is exactly what
        /// this must never call), and only for ids that already exist in the
        /// en table. Per-key identity + explicit English self-heal (r2 find
        /// 5): the catalogue target applies only while the live en text still
        /// equals the catalogue's expected_en; a reworded entry renders the
        /// CURRENT English instead of a stale translation, and every key gets
        /// SOME entry so locale fallback (uk->ru) can never serve a string.</summary>
        private static StringTable BuildTable(StringTable en, Locale locale,
                                              Dictionary<string, string[]> cat, Generation gen)
        {
            string collection = en.TableCollectionName;
            var t = ScriptableObject.CreateInstance<StringTable>();
            t.name = collection + "_" + gen.Code + " (SCR#" + gen.Id + ")";
            t.hideFlags = HideFlags.HideAndDontSave;
            t.SharedData = en.SharedData;
            t.LocaleIdentifier = locale.Identifier;
            foreach (var enEntry in en.Values)
            {
                if (enEntry == null) continue;
                string keyName = null;
                try { keyName = enEntry.Key; } catch { }
                string enText = enEntry.LocalizedValue;
                string target = enText; // explicit self-heal default
                string[] pair;
                if (keyName != null
                    && cat.TryGetValue(collection + "/" + keyName, out pair)
                    && pair != null && pair.Length >= 2
                    && string.Equals(pair[0], enText, StringComparison.Ordinal))
                {
                    target = pair[1];
                }
                var mine = t.AddEntry(enEntry.KeyId, target);
                // Mirror IsSmart (PROMPT_ROOMCODE today): the setter creates
                // the SmartFormatTag on OUR table's metadata, not SharedData.
                if (enEntry.IsSmart) mine.IsSmart = true;
            }
            return t;
        }

        // ── Central re-assert (r2 find 7) ────────────────────────────────

        /// <summary>THE one method that makes ROUNDS render our locale:
        /// selects BY REFERENCE, asserts the readback (r2 find 6),
        /// force-invalidates the card-text caches when the selected OBJECT
        /// actually moved, and requests the NativeUI repaint. Used by the
        /// activation commit, the OptionsData postfix and I18n's apply path —
        /// no other site may call SetSelectedLocale with our locale.</summary>
        internal static bool CentralReassert(string source)
        {
            if (_shutdown) return false;
            var gen = _active;
            if (gen == null || gen.Locale == null) return false;
            if (_conflicted) return false; // fail closed — no retry loop (r2 find 6)

            // r2 find 5: verify the installed provider BY REFERENCE before
            // every selection, not just at commit. The slot is replace-only;
            // if another mod overwrote it after our commit, our tables can
            // no longer be served and selecting uk would hand its keys to
            // the ru locale fallback — Russian text, silently. Same
            // fail-closed posture as the selection-readback conflict.
            try
            {
                var sdb = LocalizationSettings.StringDatabase;
                if (sdb == null || !ReferenceEquals(sdb.TableProvider, _provider))
                {
                    _conflicted = true;
                    Plugin.Log.LogWarning($"[GAMELOC] TableProvider is no longer ours at re-assert "
                                          + $"({source}) — another mod replaced it; giving up for the session");
                    return false;
                }
            }
            catch { return false; }

            Locale before = ReadSelectedLocale();
            bool moved = !ReferenceEquals(before, gen.Locale);

            _inReassert = true;
            try { LocalizationSettings.SelectedLocale = gen.Locale; }
            finally { _inReassert = false; }

            Locale after = ReadSelectedLocale();
            if (!ReferenceEquals(after, gen.Locale))
            {
                // Another locale owner won a name+code-equal race or is
                // re-asserting against us. Retrying would ping-pong the
                // engine's locale every frame both mods touch it — log ONCE
                // and give up for the session (fail closed).
                _conflicted = true;
                Plugin.Log.LogWarning($"[GAMELOC] SetSelectedLocale readback is not our '{gen.Code}' "
                                      + $"object (got '{(after == null ? "null" : after.name)}', {source}) "
                                      + "— conflicting locale owner; giving up for the session");
                return false;
            }

            // FORCE the card-cache drop when the selected OBJECT moved (r2
            // find 7): the CODE can be unchanged across an object swap
            // (another mod's own 'uk' locale, or our own next generation of
            // the same code), which the cache's own code-compare guard would
            // wrongly keep. When the object did NOT move, nothing the caches
            // read has changed — force:false lets the existing guard keep
            // them (this is what makes the postfix path cheap on every
            // options-screen open).
            try { CardTextLocalizer.InvalidateCache(force: moved); } catch { }
            try { NativeUI.MarkDirty(); } catch { }
            if (moved)
            {
                try { NativeUI.RequestCatalogueRebuild(); } catch { }
                Plugin.Log.LogInfo($"[GAMELOC] re-asserted '{gen.Code}' ({source})");
            }
            return true;
        }

        /// <summary>Move the engine off one of OUR private locales onto a
        /// verified vanilla one (r3 find 2 / find 4). Never touches a
        /// selection that is already vanilla — a user's own pick must stand.
        /// Called before retiring a generation that is still rendering and
        /// as the first step of Shutdown, both times while the provider is
        /// still installed so the switch cannot pass through an unserved
        /// state.</summary>
        private static void RestoreVanillaSelection(string reason)
        {
            Locale cur = ReadSelectedLocale();
            if (!IsOurLocale(cur)) return;
            Locale target = ResolveVanillaLocale("en");
            if (target == null) target = ResolveVanillaLocale("ru");
            if (target == null) target = FirstVanillaLocale();
            if (target == null)
            {
                Plugin.Log.LogWarning($"[GAMELOC] cannot restore a vanilla locale ({reason}): "
                                      + "AvailableLocales has none");
                return;
            }
            _inReassert = true;
            try { LocalizationSettings.SelectedLocale = target; }
            catch (Exception ex) { Plugin.Log.LogWarning("[GAMELOC] vanilla restore: " + ex.Message); }
            finally { _inReassert = false; }
            try { CardTextLocalizer.InvalidateCache(force: true); } catch { }
            try { NativeUI.MarkDirty(); } catch { }
            try { NativeUI.RequestCatalogueRebuild(); } catch { }
            Plugin.Log.LogInfo($"[GAMELOC] restored vanilla locale '{target.Identifier.Code}' ({reason})");
        }

        /// <summary>OptionsData.InitializeLocalization prefix body: open the
        /// programmatic-selection window and arm the deferred-callback fence
        /// (r3 find 1 — the dispatch of the selection made inside this window
        /// usually lands a frame or more later).</summary>
        internal static void OnOptionsInitEntering()
        {
            InOptionsInit = true;
            _initCallbackExpected = true;
            _awaitedInitLocale = null;
            _optionsInitLeaveDone = false;
        }

        /// <summary>Close the window. If the callback for vanilla's selection
        /// has NOT already been delivered synchronously, snapshot the locale
        /// it left selected — the one late callback carrying that object is
        /// consumed by OnSelectedLocaleChanged instead of being latched as a
        /// user action (r3 find 1). Runs before the postfix's re-assert, which
        /// is what moves the selection away again. Idempotent: the finalizer
        /// calls it too, and must not re-arm off the post-re-assert state.</summary>
        internal static void OnOptionsInitLeaving()
        {
            InOptionsInit = false;
            if (_optionsInitLeaveDone) return;
            _optionsInitLeaveDone = true;
            bool expected = _initCallbackExpected;
            _initCallbackExpected = false;
            _awaitedInitLocale = null;
            // Skipping the SelectedLocale read while we hold no subscriber is
            // what keeps en/es/ru sessions free of any side effect here.
            if (!expected || !_subscribed) return;
            Locale sel = ReadSelectedLocale();
            if (sel != null && !IsOurLocale(sel)) _awaitedInitLocale = sel;
        }

        /// <summary>OptionsData.InitializeLocalization postfix body — called
        /// IMMEDIATELY, same frame (r2 find 7: the invoke-now callback inside
        /// it selects Locales[savedIndex] synchronously, so a synchronous
        /// postfix re-assert wins deterministically; the one-frame delay of
        /// the first draft let English prime every card cache first).</summary>
        internal static void OnOptionsInitCompleted()
        {
            if (_shutdown) return;
            if (_active == null) return;
            if (_vanillaOverrideLatch) return; // the user's vanilla-row pick stands
            if (!ModWantsTarget()) return;
            CentralReassert("options-init");
        }

        /// <summary>SelectedLocaleChanged subscriber (installed from the first
        /// activation step onward — r3 find 3). A change to a locale that is
        /// NOT ours, outside our own re-assert and outside vanilla's options
        /// init, is a USER action on the vanilla options row — record the
        /// session override latch and nothing else. NEVER SetSelectedLocale
        /// from inside this event: the settings object is mid-
        /// InvokeSelectedLocaleChanged and a nested selection re-enters the
        /// callback array (the r2-flagged nested-event hazard).</summary>
        private static void OnSelectedLocaleChanged(Locale newLocale)
        {
            try
            {
                if (_shutdown) return;
                if (_inReassert) return;
                if (InOptionsInit)
                {
                    // Delivered synchronously inside vanilla's init window —
                    // nothing is owed to the deferred fence (r3 find 1).
                    _initCallbackExpected = false;
                    return;
                }
                // The one late callback vanilla's init owes us. Consuming it
                // by OBJECT identity means a genuine later user pick of the
                // same locale still latches (a re-pick of the already-selected
                // locale raises no event at all, so there is nothing to
                // shadow).
                if (_awaitedInitLocale != null && ReferenceEquals(newLocale, _awaitedInitLocale))
                {
                    _awaitedInitLocale = null;
                    return;
                }
                // Any other late delivery describes a SUPERSEDED selection —
                // our own re-assert already moved past it — and must not be
                // read as user intent (r3 find 1). The selection itself is
                // always applied synchronously by SetSelectedLocale, so the
                // live value is the authority.
                if (!ReferenceEquals(newLocale, ReadSelectedLocale())) return;

                if (IsOurLocale(newLocale)) return; // ours, current or retired
                if (!ModWantsTarget()) return;
                if (_vanillaOverrideLatch) return;
                _vanillaOverrideLatch = true;
                Plugin.Log.LogInfo("[GAMELOC] user selected a vanilla locale on the options row ("
                                   + (newLocale == null ? "null" : newLocale.Identifier.Code)
                                   + ") — honoring it for the session");
            }
            catch { }
        }

        // ── Teardown ─────────────────────────────────────────────────────

        private static void Subscribe()
        {
            if (_subscribed || _shutdown) return;
            try
            {
                LocalizationSettings.SelectedLocaleChanged += OnSelectedLocaleChanged;
                _subscribed = true;
            }
            catch { }
        }

        /// <summary>Pre-commit failure: drop the in-flight generation, log ONE
        /// line, park in Failed. The committed generation (if any) is
        /// deliberately untouched — it is still selected, still served, and a
        /// failed replacement must not cost the player the language they
        /// already had (r3 find 2). Created-object destruction and
        /// mutated-global restoration happen at the failure sites (they know
        /// what exists); this is the shared tail every abort funnels
        /// through.</summary>
        private static void Abort(string reason)
        {
            string code = _pending != null ? _pending.Code
                        : (_active != null ? _active.Code : "?");
            AbandonPending(null);
            ReleaseLocations();
            _state = InjState.Failed;
            Plugin.Log.LogWarning($"[GAMELOC] activation failed for '{code}': {reason} — "
                                  + (_active != null
                                     ? $"generation {_active.Id} ('{_active.Code}') keeps serving"
                                     : "game text stays English this session (mod UI still localized)"));
        }

        /// <summary>Discard an in-flight generation: balanced handle release,
        /// nothing else. Nothing it owns is globally observable before the
        /// commit step, so there is no provider/subscription/selection to
        /// unwind.</summary>
        private static void AbandonPending(string reason)
        {
            ReleaseLocations();
            var gen = _pending;
            _pending = null;
            if (gen == null) return;
            ReleaseEnHandles(gen);
            if (reason != null)
                Plugin.Log.LogInfo($"[GAMELOC] in-flight activation for '{gen.Code}' "
                                   + $"(generation {gen.Id}) abandoned: {reason}");
            _state = _active != null ? InjState.Committed : InjState.Idle;
        }

        /// <summary>Retire a generation the swap replaced. Its built tables and
        /// locale are RETIRED, not Destroy()ed: post-commit they are
        /// observable — the database's TableOperations cache holds completed
        /// ops on them — so destroying trades a bounded two-object leak for
        /// use-after-destroy in vanilla lookup paths. (Pre-commit failures DO
        /// destroy, via DestroyPreCommit — nothing observed those objects.)
        /// The engine must not still be rendering it: the provider stops
        /// answering for a retired locale, so a lingering selection would fall
        /// through to the ru fallback.</summary>
        private static void RetireGeneration(Generation gen, string reason)
        {
            if (gen == null) return;
            if (IsSelected(gen.Locale)) RestoreVanillaSelection($"retiring generation {gen.Id}");
            ReleaseEnHandles(gen);
            Plugin.Log.LogInfo($"[GAMELOC] generation {gen.Id} ('{gen.Code}') retired: {reason}");
        }

        private static bool IsSelected(Locale l)
        {
            return l != null && ReferenceEquals(ReadSelectedLocale(), l);
        }

        /// <summary>No pending generation but the state machine is in an
        /// in-flight state — only reachable if a request was superseded
        /// between steps. Park where the committed generation says to.</summary>
        private static void ParkNoPending()
        {
            _state = _active != null ? InjState.Committed : InjState.Idle;
        }

        private static void DestroyPreCommit(Locale locale, StringTable a, StringTable b)
        {
            try { if (a != null) UnityEngine.Object.Destroy(a); } catch { }
            try { if (b != null) UnityEngine.Object.Destroy(b); } catch { }
            try { if (locale != null) UnityEngine.Object.Destroy(locale); } catch { }
        }

        private static void ReleaseEnHandles(Generation gen)
        {
            if (gen == null) return;
            if (gen.EnDefaultAcquired)
            {
                try { if (gen.EnDefault.IsValid()) Addressables.Release(gen.EnDefault); } catch { }
                gen.EnDefaultAcquired = false;
            }
            if (gen.EnCardsAcquired)
            {
                try { if (gen.EnCards.IsValid()) Addressables.Release(gen.EnCards); } catch { }
                gen.EnCardsAcquired = false;
            }
            gen.EnDefault = default(AsyncOperationHandle<StringTable>);
            gen.EnCards = default(AsyncOperationHandle<StringTable>);
        }

        private static void ReleaseLocations()
        {
            if (_locationsPending)
            {
                try { if (_locationsHandle.IsValid()) Addressables.Release(_locationsHandle); } catch { }
                _locationsPending = false;
            }
            _locationsHandle = default(AsyncOperationHandle<IList<IResourceLocation>>);
        }

        /// <summary>Resolve a VANILLA locale from AvailableLocales by
        /// two-letter code — exact first, then a region variant ("en" ->
        /// "en-US") — skipping PseudoLocale rows. Mirrors I18n's
        /// TryApplyRoundsLocale resolution rules, typed.</summary>
        private static Locale ResolveVanillaLocale(string twoLetter)
        {
            var avail = LocalizationSettings.AvailableLocales;
            var locales = avail == null ? null : avail.Locales;
            if (locales == null) return null;
            for (int pass = 0; pass < 2; pass++)
            {
                foreach (var loc in locales)
                {
                    if (loc == null || loc is PseudoLocale) continue;
                    string code = loc.Identifier.Code;
                    if (string.IsNullOrEmpty(code)) continue;
                    string lower = code.ToLowerInvariant();
                    bool hit = pass == 0
                        ? lower == twoLetter
                        : lower.StartsWith(twoLetter + "-", StringComparison.Ordinal);
                    if (hit) return loc;
                }
            }
            return null;
        }

        /// <summary>Last-resort restore target: any non-pseudo member of
        /// AvailableLocales. Only reached when the build ships neither en nor
        /// ru, which no shipped ROUNDS build does — but a restore that cannot
        /// find a target would leave the engine on a private locale, the exact
        /// state RestoreVanillaSelection exists to prevent.</summary>
        private static Locale FirstVanillaLocale()
        {
            var avail = LocalizationSettings.AvailableLocales;
            var locales = avail == null ? null : avail.Locales;
            if (locales == null) return null;
            foreach (var loc in locales)
            {
                if (loc == null || loc is PseudoLocale) continue;
                if (IsOurLocale(loc)) continue; // cannot happen: ours are never members
                return loc;
            }
            return null;
        }

        // ── Provider ─────────────────────────────────────────────────────

        /// <summary>Serves the COMMITTED generation's runtime tables for that
        /// generation's locale and nothing else. Installed on
        /// LocalizedStringDatabase.TableProvider ONLY — never the asset
        /// database (fonts ride FallbackLocale metadata).
        ///
        /// NOTE (r2 find 13): providers are consulted only by NAMED loads
        /// (GetTableAsync -> FindTableByName). Preload discovery and
        /// GetAllTables enumerate addressable LABELS directly, so these
        /// tables are invisible to preload/enumeration. No shipped caller
        /// depends on enumerating them; a future one would see an empty set
        /// for uk/sv, not a crash.</summary>
        private sealed class ScrTableProvider : ITableProvider
        {
            public AsyncOperationHandle<TTable> ProvideTableAsync<TTable>(string tableCollectionName, Locale locale)
                where TTable : LocalizationTable
            {
                // "Not mine" MUST be the INVALID default handle (r2 find 4):
                // LoadTableOperation falls through to addressables only when
                // IsValid() is false. A valid failed/completed-null handle
                // reaches CustomTableLoaded, whose addressables retry then
                // overwrites m_LoadTableOperation while Destroy releases only
                // the replacement — one leaked operation per English reload.
                if (_shutdown) return default(AsyncOperationHandle<TTable>);
                var gen = _active;
                if (gen == null) return default(AsyncOperationHandle<TTable>);
                if (!ReferenceEquals(locale, gen.Locale)) return default(AsyncOperationHandle<TTable>);
                StringTable t = null;
                if (tableCollectionName == TableDefault) t = gen.Default;
                else if (tableCollectionName == TableCards) t = gen.Cards;
                if (t == null) return default(AsyncOperationHandle<TTable>);
                var typed = t as TTable;
                if (typed == null) return default(AsyncOperationHandle<TTable>);
                // FRESH completed operation per call: the database caches and
                // later releases each handle it is given (LoadTableOperation
                // .Destroy releases it after the outer op) — a shared handle
                // would be double-released (r2 confirmed-answers note).
                return Addressables.ResourceManager.CreateCompletedOperation<TTable>(typed, null);
            }
        }
    }

    /// <summary>r2 find 7: OptionsData.InitializeLocalization's invoke-now
    /// OPTION_LANGUAGE callback synchronously selects Locales[savedIndex],
    /// silently flipping the game off an injected locale whenever vanilla
    /// options init runs after our activation — and Optionshandler
    /// re-instantiates its OptionsData clone (rerunning this method) on
    /// every options-screen lifecycle. The prefix/postfix pair brackets the
    /// window so the SelectedLocaleChanged subscriber can tell vanilla's
    /// programmatic selection from a real user arrow press, and the postfix
    /// re-asserts IMMEDIATELY (same frame — see OnOptionsInitCompleted).
    ///
    /// r3 find 1: the bracket alone is NOT sufficient, because the SELECTION
    /// is synchronous while its SelectedLocaleChanged DISPATCH usually is not
    /// (LocalizationSettings.SendLocaleChangedEvents re-creates the
    /// initialization operation and defers the callbacks to a coroutine unless
    /// it is already Succeeded; the shipped asset has InitializeSynchronously
    /// = 0). OnOptionsInitLeaving therefore snapshots what vanilla left
    /// selected so the late callback is consumed rather than mistaken for the
    /// user's own choice. Inert bookkeeping when the injector is not active.
    /// </summary>
    [HarmonyPatch(typeof(OptionsData), "InitializeLocalization")]
    internal static class GameLocaleOptionsInitPatch
    {
        private static void Prefix()
        {
            GameLocaleInjector.OnOptionsInitEntering();
        }

        private static void Postfix()
        {
            // Arm the deferred fence BEFORE the re-assert — the re-assert is
            // what moves the selection off what vanilla just chose.
            GameLocaleInjector.OnOptionsInitLeaving();
            try { GameLocaleInjector.OnOptionsInitCompleted(); }
            catch (Exception ex) { Plugin.Log.LogWarning("[GAMELOC] options-init reassert: " + ex.Message); }
        }

        /// <summary>Postfixes are SKIPPED when the original throws (the
        /// vanilla out-of-range-index hazard, which we never trigger but
        /// another mod could) — without this the window would stick open and
        /// permanently disarm the user-override latch. Runs after Postfix on
        /// the normal path too; OnOptionsInitLeaving is idempotent and will
        /// not re-arm off the post-re-assert selection. The exception is
        /// rethrown untouched — never swallow vanilla's.</summary>
        private static Exception Finalizer(Exception __exception)
        {
            GameLocaleInjector.OnOptionsInitLeaving();
            return __exception;
        }
    }
}
