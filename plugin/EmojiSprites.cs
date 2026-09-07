using System;
using System.Collections;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using BepInEx.Configuration;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Bug 333 step 2: colour emoji on the mod's OWN TextMeshPro labels.
    ///
    /// Step 1 moved the minimised chat to TMP, so emoji render through the OS
    /// fallback chain (#110) in monochrome. TMP's SDF atlas cannot carry CBDT
    /// colour glyphs; colour needs a sprite asset. The mechanism here is the one
    /// the design review settled on (group4-design-v2 E-1..E-5):
    ///
    ///  * No global default. Each mod-owned label is <see cref="Attach"/>ed
    ///    (its own <c>spriteAsset</c> slot, previous value remembered) and its
    ///    text goes through <see cref="Substitute"/> before <c>.text</c> is set:
    ///    a longest-match replacement of every supported emoji SEQUENCE with
    ///    <c>&lt;sprite name="e_1F468-200D-1F469-200D-1F467"&gt;</c>. Vanilla
    ///    text, other mods and <c>TMP_Settings</c> are never touched.
    ///  * The atlas (tools/emoji_atlas.py; Noto Color Emoji, OFL 1.1, licence
    ///    text shipped beside it) is 2048x2048 RGBA32 sheets of 48 px cells, one
    ///    sheet for the default list; the index names hyphenated hex code-point
    ///    sequences and the runtime matcher is a trie over them (E-2).
    ///  * Delivery is the music pack's shape (#458/#474): a dedicated immutable
    ///    GitHub release, the DLL pins the bytes (<see cref="INDEX_SHA256"/> is
    ///    the sha256 of emoji-index.json; every sheet is checked against the
    ///    sha256 the index carries), downloaded on a worker thread from the first
    ///    safe menu state, staged and published atomically. Until it is present,
    ///    emoji stay monochrome - no wait, no toast.
    ///  * E-5 budget: decode + upload run only from a safe menu state (admissible
    ///    menu AND no match tracking), the wall time is measured, and colour
    ///    emoji is disabled for the session with ONE log line when it exceeds
    ///    <see cref="BUDGET_MS"/> or the seat reports low memory.
    ///  * E-3/E-4: the TMP_SpriteAsset is built by reflection (every member
    ///    guarded - a missing one names itself once and disables the feature),
    ///    every runtime object is HideAndDontSave (#16), each label's previous
    ///    spriteAsset is restored on Detach/teardown, sheets are destroyed at
    ///    Application.quitting.
    ///
    /// Line metrics: the sprite asset's faceInfo is left at its default
    /// (pointSize 0), which is the TMP path that scales a sprite to the FONT's
    /// ascent and keeps the font's own ascent/descent for the line - a line with
    /// emoji is exactly as tall as one without (#292's class stays closed).
    /// Sprites are not tinted: TMP takes the label's alpha for an untinted sprite
    /// (fades work) and tinting would multiply the emoji by the text colour.</summary>
    internal static class EmojiSprites
    {
        internal const string ATLAS_VERSION = "emoji-atlas-v1";
        internal const string ATLAS_REVISION = MusicAssets.EMOJI_ATLAS_REVISION;
        /// <summary>SHA-256 (lower-case hex) of emoji-index.json exactly as
        /// tools/emoji_atlas.py wrote it (the tool prints this line). "" = no
        /// atlas is pinned for this build: the feature stays off with one log
        /// line and nothing is downloaded. Changing the atlas bytes means a new
        /// pin AND a new release revision - published releases are never edited.</summary>
        internal const string INDEX_SHA256 = "";
        /// <summary>Byte-scannable probe (#306): referenced from the init log line
        /// so it lands in the DLL's UTF-16 string heap; pack/release tooling can
        /// read the pin out of a DLL and compare it with the zip's index.</summary>
        internal const string BUILD_MARKER = "SCR_EMOJI_ATLAS_PIN=" + INDEX_SHA256;
        internal const string SPRITE_NAME_PREFIX = "e_";

        private const string INDEX_FILE = "emoji-index.json";
        private const string LICENCE_FILE = "LICENSE-NotoColorEmoji.txt";
        private const string SHEET_PREFIX = "emoji-sheet-";
        private const string ZIP_FILE = ATLAS_VERSION + ".zip";
        private const int MAX_SHEETS = 2;                 // tools/emoji_atlas.py MAX_RUNTIME_SHEETS
        private const long MAX_ZIP_BYTES = 12L << 20;     // streaming cap; integrity is the pin, not this
        private const long MAX_INDEX_BYTES = 2L << 20;
        private const long MAX_SHEET_BYTES = 8L << 20;
        private const long MAX_LICENCE_BYTES = 64L << 10;
        private const int DOWNLOAD_ATTEMPTS = 4;
        private const int MAX_RETRY_AFTER_MS = 60000;
        private const long BUDGET_MS = 150;
        /// <summary>ROUNDS' minimum spec is 4 GB; a seat reporting under 3 GB
        /// (systemMemorySize is MB, and 4 GB machines report ~3.9 GB) is below
        /// spec and does not get a 16 MiB texture plus transient decode copies.</summary>
        private const int MIN_SYSTEM_MB = 3072;
        /// <summary>Below this the renderer is software / shared-memory only.</summary>
        private const int MIN_GRAPHICS_MB = 128;
        private const float TICK_SECONDS = 1f;
        /// <summary>The unicode TMP treats as "no character": keeps our sprites out
        /// of the unicode lookup, so nothing is ever substituted by code point.</summary>
        private const uint SPRITE_UNICODE = 0xFFFE;

        private enum State { Off, NeedDownload, Downloading, OnDisk, Active, Disabled }

        private sealed class Attachment { public object Component; public object Previous; }

        private static bool _initialized;
        private static State _state = State.Off;
        private static string _root;   // <dllDir>/emoji
        private static string _dir;    // <root>/<revision>
        private static float _lastTick = -100f;
        private static int _generation;
        private static EmojiMatcher _matcher;
        private static object _asset0;
        private static readonly List<Attachment> _attached = new List<Attachment>();
        private static readonly List<UnityEngine.Object> _runtimeObjects = new List<UnityEngine.Object>();
        private static readonly HashSet<string> _loggedOnce = new HashSet<string>();
        private static ConfigEntry<bool> _enabledCfg;
        private static ConfigEntry<bool> _selfTestCfg;
#if !THUNDERSTORE
        private static WorkerBox _box;
#endif

        // ── Public surface ──

        /// <summary>Bumps when colour emoji becomes active (a label that caches
        /// substituted/measured text keys its cache on this).</summary>
        internal static int Generation => _generation;

        internal static bool Active => _state == State.Active;

        /// <summary>Replace every supported emoji sequence in <paramref name="text"/>
        /// with its sprite tag. Identity until the atlas is active; never touches
        /// text inside an existing rich-text tag; unknown code points pass through.</summary>
        internal static string Substitute(string text)
        {
            if (_state != State.Active || _matcher == null || string.IsNullOrEmpty(text)) return text;
            try { return _matcher.Substitute(text, false); }
            catch (Exception ex) { LogOnce("subst", "[EMOJI] substitute failed: " + ex.Message + " (text left as-is)"); return text; }
        }

        /// <summary>Give this TMP_Text (any subclass; passed as object because the
        /// mod reaches TMP by reflection) the mod's sprite asset. Remembered so a
        /// label attached BEFORE the atlas is active receives it when it is, and so
        /// the previous value is restored on Detach or teardown.</summary>
        internal static void Attach(object tmp)
        {
            if (tmp == null || _state == State.Disabled) return;
            try
            {
                if (!Tmp.Resolve(out string missing)) { Disable("TMP member missing: " + missing); return; }
                if (!Tmp.TmpTextType.IsInstanceOfType(tmp)) return;
                Prune();
                for (int i = 0; i < _attached.Count; i++)
                    if (ReferenceEquals(_attached[i].Component, tmp)) return;
                var a = new Attachment { Component = tmp, Previous = Tmp.SpriteAssetProp.GetValue(tmp, null) };
                _attached.Add(a);
                if (_state == State.Active && _asset0 != null) Tmp.SpriteAssetProp.SetValue(tmp, _asset0, null);
            }
            catch (Exception ex) { LogOnce("attach", "[EMOJI] attach failed: " + ex.Message); }
        }

        /// <summary>Restore the label's previous spriteAsset and forget it.</summary>
        internal static void Detach(object tmp)
        {
            if (tmp == null) return;
            try
            {
                for (int i = _attached.Count - 1; i >= 0; i--)
                {
                    if (!ReferenceEquals(_attached[i].Component, tmp)) continue;
                    Restore(_attached[i]);
                    _attached.RemoveAt(i);
                }
            }
            catch (Exception ex) { LogOnce("detach", "[EMOJI] detach failed: " + ex.Message); }
        }

        // ── Lifecycle ──

        /// <summary>From Plugin.DoInitialize, after MusicAssets/MusicEngine. Binds
        /// the levers, hooks teardown, resolves the cache dir, sweeps crashed
        /// downloads, and decides the starting state. No decode, no download here.</summary>
        internal static void Initialize()
        {
            if (_initialized) return;
            _initialized = true;
            try
            {
                ConfigFile cf = Plugin.ConfigFileForLevers;
                if (cf != null)
                {
                    _enabledCfg = cf.Bind("Chat", "ColourEmoji", true,
                        "Render emoji in the mod's chat labels (minimised chat, F5 chat pane) in colour from the downloaded emoji atlas. Off = monochrome OS glyphs, nothing downloaded.");
                    _selfTestCfg = cf.Bind("Chat", "EmojiSpritesSelfTest", false,
                        "Development only: once at startup, run the emoji sequence matcher over its shared vectors and log one [EMOJI] selftest line per case plus a summary line. Nothing is shown, sent or persisted.");
                }
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[EMOJI] lever bind failed: " + ex.Message); }
            bool selfTest = false;
            try { selfTest = _selfTestCfg != null && _selfTestCfg.Value; } catch { }
            if (selfTest) EmojiMatcher.RunSelfTest(s => Plugin.Log?.LogInfo(s), s => Plugin.Log?.LogWarning(s));
            bool enabled = true;
            try { enabled = _enabledCfg == null || _enabledCfg.Value; } catch { }
            if (!enabled)
            {
                Plugin.Log?.LogInfo("[EMOJI] colour emoji off by config ([Chat] ColourEmoji = false)");
                return;
            }
            try { Application.quitting += Teardown; } catch { }
            try
            {
                string dllDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
                _root = Path.Combine(dllDir, "emoji");
                _dir = Path.Combine(_root, ATLAS_REVISION);
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning("[EMOJI] plugin dir resolve failed: " + ex.Message + " - colour emoji off this session");
                _state = State.Disabled;
                return;
            }
            // BUILD_MARKER reference is load-bearing (#306): an unreferenced const
            // is folded away and never reaches the string heap.
            if (INDEX_SHA256.Length == 0)
            {
                Plugin.Log?.LogInfo("[EMOJI] init " + BUILD_MARKER + ": no atlas pinned in this build - colour emoji off");
                return;
            }
            Sweep();
            string reason = null;
            if (AtlasOnDisk(_dir, out reason))
            {
                _state = State.OnDisk;
                Plugin.Log?.LogInfo("[EMOJI] init " + BUILD_MARKER + ": atlas on disk - builds at the first safe menu state");
                return;
            }
#if THUNDERSTORE
            // Never touch the network: the pack zip bundles the atlas; a missing or
            // invalid one is surfaced once and left alone (the music pack's [G4]).
            _state = State.Disabled;
            Plugin.Log?.LogWarning("[EMOJI] init " + BUILD_MARKER + ": bundled atlas missing/invalid (" + reason + ") - colour emoji off (reinstall via the mod manager)");
#else
            _state = State.NeedDownload;
            Plugin.Log?.LogInfo("[EMOJI] init " + BUILD_MARKER + ": atlas absent (" + reason + ") - downloads at the first safe menu state");
#endif
        }

        /// <summary>Per-frame from the persistent host's Update; self-throttled to
        /// one evaluation per second and a single flag read once Active/Disabled.
        /// Download starts, and decode + upload runs, ONLY from a safe menu state.</summary>
        internal static void Tick()
        {
            if (_state == State.Off || _state == State.Active || _state == State.Disabled) return;
            float now = Time.realtimeSinceStartup;
            if (now - _lastTick < TICK_SECONDS) return;
            _lastTick = now;
            switch (_state)
            {
                case State.NeedDownload:
#if !THUNDERSTORE
                    if (SafeState()) StartDownload();
#endif
                    break;
                case State.Downloading:
#if !THUNDERSTORE
                    if (_box != null && _box.Done)
                    {
                        var box = _box;
                        _box = null;
                        string reason = null;
                        if (box.Ok && AtlasOnDisk(_dir, out reason))
                        {
                            _state = State.OnDisk;
                            Plugin.Log?.LogInfo("[EMOJI] atlas downloaded and verified - builds at the next safe menu state");
                        }
                        else Disable(box.Ok ? "downloaded atlas failed validation (" + reason + ")" : (box.Why ?? "download failed"));
                    }
#endif
                    break;
                case State.OnDisk:
                    if (SafeState()) Build();
                    break;
            }
        }

        private static bool SafeState()
        {
            try { return MusicAdmission.AtAdmissibleMenu && !GameStateWatcher.IsTracking; }
            catch { return false; }
        }

        private static void Teardown()
        {
            try
            {
                for (int i = 0; i < _attached.Count; i++) Restore(_attached[i]);
                _attached.Clear();
            }
            catch { }
            DestroyRuntimeObjects();
            _matcher = null;
            _asset0 = null;
            if (_state == State.Active) _state = State.Off;
        }

        private static void Disable(string reason)
        {
            _state = State.Disabled;
            try
            {
                for (int i = 0; i < _attached.Count; i++) Restore(_attached[i]);
            }
            catch { }
            DestroyRuntimeObjects();
            _matcher = null;
            _asset0 = null;
            Plugin.Log?.LogWarning("[EMOJI] colour emoji off this session: " + reason);
        }

        private static void Restore(Attachment a)
        {
            try
            {
                var uo = a.Component as UnityEngine.Object;
                if (uo == null) return;                         // destroyed (Unity's overloaded ==)
                if (Tmp.SpriteAssetProp == null) return;
                object cur = Tmp.SpriteAssetProp.GetValue(a.Component, null);
                if (_asset0 != null && !ReferenceEquals(cur, _asset0)) return;   // someone else set it since
                Tmp.SpriteAssetProp.SetValue(a.Component, a.Previous, null);
            }
            catch { }
        }

        private static void Prune()
        {
            for (int i = _attached.Count - 1; i >= 0; i--)
            {
                var uo = _attached[i].Component as UnityEngine.Object;
                if (uo == null) _attached.RemoveAt(i);
            }
        }

        private static void DestroyRuntimeObjects()
        {
            for (int i = 0; i < _runtimeObjects.Count; i++)
            {
                try { if (_runtimeObjects[i] != null) UnityEngine.Object.Destroy(_runtimeObjects[i]); } catch { }
            }
            _runtimeObjects.Clear();
        }

        private static void LogOnce(string key, string line)
        {
            if (!_loggedOnce.Add(key)) return;
            Plugin.Log?.LogWarning(line);
        }

        // ── Build (main thread, safe menu state only) ──

        private static void Build()
        {
            var total = Stopwatch.StartNew();
            var textures = new List<Texture2D>();
            try
            {
                string missing;
                if (!Tmp.Resolve(out missing)) { Disable("TMP member missing: " + missing); return; }
                int sysMb = 0, gfxMb = 0;
                try { sysMb = SystemInfo.systemMemorySize; gfxMb = SystemInfo.graphicsMemorySize; } catch { }
                if (sysMb > 0 && sysMb < MIN_SYSTEM_MB) { Disable("system memory " + sysMb + " MB is below the " + MIN_SYSTEM_MB + " MB floor"); return; }
                if (gfxMb > 0 && gfxMb < MIN_GRAPHICS_MB) { Disable("graphics memory " + gfxMb + " MB is below the " + MIN_GRAPHICS_MB + " MB floor"); return; }

                byte[] indexBytes = File.ReadAllBytes(Path.Combine(_dir, INDEX_FILE));
                if (!string.Equals(Sha256Hex(indexBytes), INDEX_SHA256, StringComparison.OrdinalIgnoreCase)) { Disable("index hash mismatch at build"); return; }
                AtlasIndex index; string err;
                if (!AtlasIndex.TryParse(Encoding.UTF8.GetString(indexBytes), out index, out err)) { Disable("index invalid: " + err); return; }

                long decodeMs = 0;
                for (int i = 0; i < index.Sheets.Count; i++)
                {
                    var s = index.Sheets[i];
                    byte[] png = File.ReadAllBytes(Path.Combine(_dir, s.File));
                    if (png.LongLength != s.Bytes || !string.Equals(Sha256Hex(png), s.Sha256, StringComparison.OrdinalIgnoreCase))
                    { Disable(s.File + " does not match the index (size/sha256)"); return; }
                    var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                    tex.name = "CR_EmojiSheet" + i;
                    tex.hideFlags = HideFlags.HideAndDontSave;
                    tex.wrapMode = TextureWrapMode.Clamp;
                    tex.filterMode = FilterMode.Bilinear;
                    _runtimeObjects.Add(tex);
                    textures.Add(tex);
                    var sw = Stopwatch.StartNew();
                    bool ok = ImageConversion.LoadImage(tex, png, false);
                    if (ok) tex.Apply(false, true);          // upload; CPU copy released (makeNoLongerReadable)
                    sw.Stop();
                    decodeMs += sw.ElapsedMilliseconds;
                    if (!ok) { Disable(s.File + " did not decode"); return; }
                    if (tex.width != index.Sheet || tex.height != index.Sheet)
                    { Disable(s.File + " is " + tex.width + "x" + tex.height + ", index says " + index.Sheet); return; }
                }
                if (decodeMs > BUDGET_MS)
                {
                    Disable("decode+upload took " + decodeMs + " ms, over the " + BUDGET_MS + " ms budget for this seat");
                    return;
                }

                Shader shader = FindSpriteShader();
                if (shader == null) { Disable("shader TextMeshPro/Sprite not found in this build"); return; }

                var assets = new List<object>(textures.Count);
                for (int i = 0; i < textures.Count; i++)
                {
                    object asset = CreateSpriteAsset(textures[i], i, index, shader, out missing);
                    if (asset == null) { Disable("sprite asset build failed: " + missing); return; }
                    assets.Add(asset);
                }
                if (assets.Count > 1)
                {
                    var list = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(Tmp.SpriteAssetType));
                    for (int i = 1; i < assets.Count; i++) list.Add(assets[i]);
                    Tmp.FallbackField.SetValue(assets[0], list);
                }
                var keys = new List<string>(index.Sequences.Count);
                for (int i = 0; i < index.Sequences.Count; i++) keys.Add(index.Sequences[i].Key);
                _matcher = new EmojiMatcher(keys);
                _asset0 = assets[0];
                _state = State.Active;
                _generation++;
                Prune();
                for (int i = 0; i < _attached.Count; i++)
                {
                    try { Tmp.SpriteAssetProp.SetValue(_attached[i].Component, _asset0, null); } catch { }
                }
                try { NativeUI.MarkDirty(); } catch { }
                total.Stop();
                long mib = (long)index.Sheet * index.Sheet * 4L * index.Sheets.Count / (1024L * 1024L);
                Plugin.Log?.LogInfo("[EMOJI] colour emoji active: " + index.Sheets.Count + " sheet(s) " + index.Sheet + "px, "
                    + index.Sequences.Count + " sequences, cell " + index.Cell + "px ascent " + index.Ascent
                    + "px, decode+upload " + decodeMs + " ms (budget " + BUDGET_MS + "), build " + total.ElapsedMilliseconds
                    + " ms, " + mib + " MiB texture memory, " + _attached.Count + " label(s) attached");
            }
            catch (Exception ex)
            {
                Disable("build threw " + ex.GetType().Name + ": " + ex.Message);
            }
        }

        private static Shader FindSpriteShader()
        {
            Shader s = null;
            try { s = Shader.Find("TextMeshPro/Sprite"); } catch { }
            if (s != null) return s;
            try
            {
                foreach (var sh in Resources.FindObjectsOfTypeAll<Shader>())
                    if (sh != null && sh.name == "TextMeshPro/Sprite") return sh;
            }
            catch { }
            return null;
        }

        /// <summary>E-3: one TMP_SpriteAsset per sheet. Every glyph: rect (PNG
        /// top-left flipped to Unity's bottom-left origin), metrics width/height =
        /// cell, bearing (0, cell ascent), advance = cell, scale 1; then
        /// UpdateLookupTables(). m_Version is set BEFORE the material: TMP 3.x
        /// treats a versionless asset that owns a material as a legacy one and
        /// would run UpgradeSpriteAsset over a null spriteInfoList.</summary>
        private static object CreateSpriteAsset(Texture2D tex, int sheetIndex, AtlasIndex index, Shader shader, out string missing)
        {
            missing = null;
            object asset = ScriptableObject.CreateInstance(Tmp.SpriteAssetType);
            if (asset == null) { missing = "ScriptableObject.CreateInstance(TMP_SpriteAsset) returned null"; return null; }
            var so = (ScriptableObject)asset;
            _runtimeObjects.Add(so);
            so.name = "CR_EmojiAtlas_" + sheetIndex;
            so.hideFlags = HideFlags.HideAndDontSave;
            Tmp.VersionField.SetValue(asset, "1.1.0");
            Tmp.SpriteSheetField.SetValue(asset, tex);
            var mat = new Material(shader);
            mat.name = "CR_EmojiSprite_" + sheetIndex;
            mat.hideFlags = HideFlags.HideAndDontSave;
            mat.mainTexture = tex;
            _runtimeObjects.Add(mat);
            Tmp.MaterialField.SetValue(asset, mat);
            Tmp.HashCodeField.SetValue(asset, EmojiMatcher.SimpleHash(so.name));
            var glyphs = Tmp.GlyphTableProp.GetValue(asset, null) as IList;
            var chars = Tmp.CharTableProp.GetValue(asset, null) as IList;
            if (glyphs == null || chars == null) { missing = "TMP_SpriteAsset tables are not lists"; return null; }
            uint gi = 0;
            int cell = index.Cell;
            for (int i = 0; i < index.Sequences.Count; i++)
            {
                var e = index.Sequences[i];
                if (e.SheetIndex != sheetIndex) continue;
                object rect = Tmp.GlyphRectCtor.Invoke(new object[] { e.X, index.Sheet - e.Y - cell, cell, cell });
                object metrics = Tmp.GlyphMetricsCtor.Invoke(new object[] { (float)cell, (float)cell, 0f, (float)index.Ascent, (float)cell });
                object glyph = Tmp.SpriteGlyphCtor.Invoke(new object[] { gi, metrics, rect, 1f, 0 });
                object ch = Tmp.SpriteCharCtor.Invoke(new object[] { SPRITE_UNICODE, glyph });
                Tmp.NameProp.SetValue(ch, SPRITE_NAME_PREFIX + e.Key, null);
                glyphs.Add(glyph);
                chars.Add(ch);
                gi++;
            }
            Tmp.UpdateLookupTables.Invoke(asset, null);
            return asset;
        }

        // ── On-disk atlas ──

        /// <summary>Main thread: the final tree validates when the index is present,
        /// hashes to the pin, parses, and every sheet it names is present with the
        /// declared size (each sheet's sha256 is checked again when its bytes are
        /// read for decoding). Never fetches, never deletes.</summary>
        private static bool AtlasOnDisk(string dir, out string reason)
        {
            reason = null;
            try
            {
                if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) { reason = "no atlas dir"; return false; }
                string ip = Path.Combine(dir, INDEX_FILE);
                var fi = new FileInfo(ip);
                if (!fi.Exists) { reason = "index missing"; return false; }
                if (fi.Length > MAX_INDEX_BYTES) { reason = "index too large"; return false; }
                byte[] bytes = File.ReadAllBytes(ip);
                if (!string.Equals(Sha256Hex(bytes), INDEX_SHA256, StringComparison.OrdinalIgnoreCase)) { reason = "index does not match the pinned hash"; return false; }
                AtlasIndex index; string err;
                if (!AtlasIndex.TryParse(Encoding.UTF8.GetString(bytes), out index, out err)) { reason = "index invalid: " + err; return false; }
                for (int i = 0; i < index.Sheets.Count; i++)
                {
                    var sf = new FileInfo(Path.Combine(dir, index.Sheets[i].File));
                    if (!sf.Exists || sf.Length != index.Sheets[i].Bytes) { reason = index.Sheets[i].File + " missing or wrong size"; return false; }
                }
                if (!File.Exists(Path.Combine(dir, LICENCE_FILE))) { reason = "licence text missing"; return false; }
                return true;
            }
            catch (Exception ex) { reason = ex.GetType().Name + ": " + ex.Message; return false; }
        }

        /// <summary>Init-time sweep of crashed downloads (staging dirs, *.tmp) and
        /// of revision dirs other than the current one.</summary>
        private static void Sweep()
        {
            try
            {
                if (_root == null || !Directory.Exists(_root)) return;
                int swept = 0;
                foreach (var d in Directory.GetDirectories(_root))
                {
                    string leaf = Path.GetFileName(d);
                    if (string.Equals(leaf, ATLAS_REVISION, StringComparison.Ordinal)) continue;
                    TryDeleteDir(d);
                    swept++;
                }
                foreach (var f in Directory.GetFiles(_root, "*.tmp")) { TryDeleteFile(f); swept++; }
                if (swept > 0) Plugin.Log?.LogInfo("[EMOJI] swept " + swept + " stale entr(ies) from the emoji cache");
            }
            catch (Exception ex) { Plugin.Log?.LogWarning("[EMOJI] cache sweep failed: " + ex.Message); }
        }

#if !THUNDERSTORE
        // ── Download (standalone builds only; worker thread, main-thread poll) ──

        private sealed class WorkerBox
        {
            public volatile bool Done;
            public volatile bool Ok;
            public volatile string Why;
        }

        private static void StartDownload()
        {
            var box = new WorkerBox();
            _box = box;
            _state = State.Downloading;
            string url = MusicAssets.EMOJI_RELEASE_BASE + ZIP_FILE;
            Plugin.Log?.LogInfo("[EMOJI] downloading " + url);
            try
            {
                var th = new Thread(() => InstallWorker(url, box)) { IsBackground = true, Name = "CR_EmojiAtlasDownload" };
                th.Start();
            }
            catch (Exception ex) { box.Why = "worker start failed: " + ex.Message; box.Done = true; }
        }

        /// <summary>Download to a temp file (streaming size cap), verify + extract
        /// into a staging dir, publish with one rename. Writes only into its own
        /// box; the main thread validates the published tree itself.</summary>
        private static void InstallWorker(string url, WorkerBox box)
        {
            string tmpZip = null, staging = null;
            try
            {
                Directory.CreateDirectory(_root);
                string tag = Guid.NewGuid().ToString("N");
                tmpZip = Path.Combine(_root, "download-" + tag + ".zip.tmp");
                staging = Path.Combine(_root, "staging-" + tag);
                string why;
                if (!Download(url, tmpZip, out why)) { box.Why = why; return; }
                if (!ExtractAndVerify(tmpZip, staging, out why)) { box.Why = why; return; }
                if (Directory.Exists(_dir)) Directory.Delete(_dir, true);   // only reached when the final tree failed validation
                Directory.Move(staging, _dir);
                staging = null;
                box.Ok = true;
            }
            catch (Exception ex) { box.Why = ex.GetType().Name + ": " + ex.Message; }
            finally
            {
                TryDeleteFile(tmpZip);
                TryDeleteDir(staging);
                box.Done = true;
            }
        }

        private static bool Download(string url, string path, out string why)
        {
            var rng = new System.Random();
            for (int attempt = 1; ; attempt++)
            {
                int status, retryAfterMs; string err; bool capHit;
                if (DownloadOnce(url, path, out status, out retryAfterMs, out capHit, out err)) { why = null; return true; }
                TryDeleteFile(path);
                if (status == 404 || status == 410) { why = "HTTP " + status + " for the atlas release - failing closed (asset release missing?)"; return false; }
                if (capHit) { why = "download exceeded the " + (MAX_ZIP_BYTES >> 20) + " MiB cap - aborted"; return false; }
                if (attempt >= DOWNLOAD_ATTEMPTS) { why = "download failed after " + attempt + " attempts: " + err; return false; }
                int waitMs = retryAfterMs >= 0
                    ? Math.Min(retryAfterMs, MAX_RETRY_AFTER_MS)
                    : Math.Min(30000, (1000 << attempt) + rng.Next(0, 1000));
                Thread.Sleep(waitMs);
            }
        }

        private static bool DownloadOnce(string url, string path, out int status, out int retryAfterMs, out bool capHit, out string err)
        {
            status = 0; retryAfterMs = -1; capHit = false; err = null;
            try
            {
                // #194: ServicePointManager governs HttpWebRequest - same TLS 1.2 opt-in as the other bootstraps.
                try { System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12; } catch { }
                var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);
                req.UserAgent = "CompetitiveRounds-Mod/" + Plugin.ModVersion;
                using (var resp = (System.Net.HttpWebResponse)req.GetResponse())
                using (var rs = resp.GetResponseStream())
                using (var os = File.Create(path))
                {
                    var buf = new byte[81920];
                    long total = 0;
                    int r;
                    while ((r = rs.Read(buf, 0, buf.Length)) > 0)
                    {
                        total += r;
                        if (total > MAX_ZIP_BYTES) { capHit = true; return false; }   // Content-Length is never consulted
                        os.Write(buf, 0, r);
                    }
                }
                return true;
            }
            catch (System.Net.WebException wex)
            {
                var resp = wex.Response as System.Net.HttpWebResponse;
                if (resp != null)
                {
                    status = (int)resp.StatusCode;
                    retryAfterMs = ParseRetryAfterMs(resp);
                    try { resp.Close(); } catch { }
                }
                err = wex.Message;
                return false;
            }
            catch (Exception ex) { err = ex.Message; return false; }
        }

        private static int ParseRetryAfterMs(System.Net.HttpWebResponse resp)
        {
            try
            {
                string h = resp.Headers?["Retry-After"];
                if (string.IsNullOrEmpty(h)) return -1;
                h = h.Trim();
                int sec;
                if (int.TryParse(h, NumberStyles.None, CultureInfo.InvariantCulture, out sec))
                    return sec > int.MaxValue / 1000 ? int.MaxValue : sec * 1000;
                DateTimeOffset when;
                if (DateTimeOffset.TryParse(h, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out when))
                {
                    double ms = (when - DateTimeOffset.UtcNow).TotalMilliseconds;
                    if (ms <= 0) return 0;
                    return ms >= int.MaxValue ? int.MaxValue : (int)ms;
                }
            }
            catch { }
            return -1;
        }

        /// <summary>The zip is FLAT and its entry set is exactly: the index (hashes
        /// to the pin), the sheets the index names (declared and actual size,
        /// sha256), the licence text. Anything else - a directory entry, a
        /// duplicate, an unknown name, an oversize entry - rejects the whole zip.</summary>
        private static bool ExtractAndVerify(string tmpZip, string staging, out string why)
        {
            var files = new Dictionary<string, byte[]>(StringComparer.Ordinal);
            using (var fs = File.OpenRead(tmpZip))
            using (var zip = new ZipArchive(fs, ZipArchiveMode.Read))
            {
                foreach (var entry in zip.Entries)
                {
                    string n = entry.FullName;
                    if (string.IsNullOrEmpty(n) || n.EndsWith("/", StringComparison.Ordinal)) { why = "reject zip: directory entry"; return false; }
                    long cap;
                    if (!AllowedEntry(n, out cap)) { why = "reject zip: unknown entry '" + n + "'"; return false; }
                    if (files.ContainsKey(n)) { why = "reject zip: duplicate entry '" + n + "'"; return false; }
                    if (entry.Length > cap) { why = "reject zip: '" + n + "' declares " + entry.Length + " bytes (cap " + cap + ")"; return false; }
                    using (var es = entry.Open())
                    using (var ms = new MemoryStream())
                    {
                        var buf = new byte[81920];
                        long written = 0;
                        int r;
                        while ((r = es.Read(buf, 0, buf.Length)) > 0)
                        {
                            written += r;
                            if (written > cap) { why = "reject zip: '" + n + "' overflows its cap"; return false; }
                            ms.Write(buf, 0, r);
                        }
                        files[n] = ms.ToArray();
                    }
                }
            }
            byte[] idx;
            if (!files.TryGetValue(INDEX_FILE, out idx)) { why = "reject zip: index missing"; return false; }
            if (!string.Equals(Sha256Hex(idx), INDEX_SHA256, StringComparison.OrdinalIgnoreCase)) { why = "reject zip: index does not match the pinned hash"; return false; }
            AtlasIndex index; string err;
            if (!AtlasIndex.TryParse(Encoding.UTF8.GetString(idx), out index, out err)) { why = "reject zip: index invalid: " + err; return false; }
            for (int i = 0; i < index.Sheets.Count; i++)
            {
                var s = index.Sheets[i];
                byte[] png;
                if (!files.TryGetValue(s.File, out png)) { why = "reject zip: " + s.File + " missing"; return false; }
                if (png.LongLength != s.Bytes) { why = "reject zip: " + s.File + " is " + png.LongLength + " bytes, index says " + s.Bytes; return false; }
                if (!string.Equals(Sha256Hex(png), s.Sha256, StringComparison.OrdinalIgnoreCase)) { why = "reject zip: " + s.File + " sha256 mismatch"; return false; }
            }
            if (!files.ContainsKey(LICENCE_FILE)) { why = "reject zip: licence text missing"; return false; }
            if (files.Count != index.Sheets.Count + 2) { why = "reject zip: " + files.Count + " entries for " + index.Sheets.Count + " sheet(s)"; return false; }
            Directory.CreateDirectory(staging);
            foreach (var kv in files) File.WriteAllBytes(Path.Combine(staging, kv.Key), kv.Value);
            why = null;
            return true;
        }

        private static bool AllowedEntry(string name, out long cap)
        {
            cap = 0;
            if (name == INDEX_FILE) { cap = MAX_INDEX_BYTES; return true; }
            if (name == LICENCE_FILE) { cap = MAX_LICENCE_BYTES; return true; }
            if (name.StartsWith(SHEET_PREFIX, StringComparison.Ordinal) && name.EndsWith(".png", StringComparison.Ordinal))
            {
                string num = name.Substring(SHEET_PREFIX.Length, name.Length - SHEET_PREFIX.Length - 4);
                int n;
                if (num.Length >= 1 && num.Length <= 2 && int.TryParse(num, NumberStyles.None, CultureInfo.InvariantCulture, out n) && n < MAX_SHEETS)
                { cap = MAX_SHEET_BYTES; return true; }
            }
            return false;
        }
#endif

        // ── Small helpers ──

        private static string Sha256Hex(byte[] bytes)
        {
            using (var sha = SHA256.Create())
            {
                byte[] h = sha.ComputeHash(bytes);
                var sb = new StringBuilder(h.Length * 2);
                for (int i = 0; i < h.Length; i++) sb.Append(h[i].ToString("x2"));
                return sb.ToString();
            }
        }

        private static void TryDeleteFile(string p)
        {
            try { if (!string.IsNullOrEmpty(p) && File.Exists(p)) File.Delete(p); } catch { }
        }

        private static void TryDeleteDir(string p)
        {
            try { if (!string.IsNullOrEmpty(p) && Directory.Exists(p)) Directory.Delete(p, true); } catch { }
        }

        // ── Reflection targets (TMP 3.x as shipped with ROUNDS' Unity 2022.3) ──

        private static class Tmp
        {
            public static Type SpriteAssetType, SpriteGlyphType, SpriteCharType, TmpTextType, GlyphRectType, GlyphMetricsType;
            public static ConstructorInfo GlyphRectCtor, GlyphMetricsCtor, SpriteGlyphCtor, SpriteCharCtor;
            public static FieldInfo SpriteSheetField, MaterialField, HashCodeField, VersionField, FallbackField;
            public static PropertyInfo GlyphTableProp, CharTableProp, NameProp, SpriteAssetProp;
            public static MethodInfo UpdateLookupTables;
            private static bool _done, _ok;
            private static string _missing;

            /// <summary>Every step guarded (#110's fallback discipline): the first
            /// missing member is named and the whole feature stays off.</summary>
            public static bool Resolve(out string missing)
            {
                if (_done) { missing = _missing; return _ok; }
                _done = true;
                _ok = false;
                try
                {
                    const string tmpAsm = ", Unity.TextMeshPro";
                    const string coreAsm = ", UnityEngine.TextCoreFontEngineModule";
                    const BindingFlags pub = BindingFlags.Public | BindingFlags.Instance;
                    const BindingFlags priv = BindingFlags.NonPublic | BindingFlags.Instance;
                    if ((SpriteAssetType = Type.GetType("TMPro.TMP_SpriteAsset" + tmpAsm)) == null) return Miss("TMPro.TMP_SpriteAsset", out missing);
                    if ((SpriteGlyphType = Type.GetType("TMPro.TMP_SpriteGlyph" + tmpAsm)) == null) return Miss("TMPro.TMP_SpriteGlyph", out missing);
                    if ((SpriteCharType = Type.GetType("TMPro.TMP_SpriteCharacter" + tmpAsm)) == null) return Miss("TMPro.TMP_SpriteCharacter", out missing);
                    if ((TmpTextType = Type.GetType("TMPro.TMP_Text" + tmpAsm)) == null) return Miss("TMPro.TMP_Text", out missing);
                    if ((GlyphRectType = Type.GetType("UnityEngine.TextCore.GlyphRect" + coreAsm)) == null) return Miss("UnityEngine.TextCore.GlyphRect", out missing);
                    if ((GlyphMetricsType = Type.GetType("UnityEngine.TextCore.GlyphMetrics" + coreAsm)) == null) return Miss("UnityEngine.TextCore.GlyphMetrics", out missing);
                    if ((GlyphRectCtor = GlyphRectType.GetConstructor(new[] { typeof(int), typeof(int), typeof(int), typeof(int) })) == null) return Miss("GlyphRect(int,int,int,int)", out missing);
                    if ((GlyphMetricsCtor = GlyphMetricsType.GetConstructor(new[] { typeof(float), typeof(float), typeof(float), typeof(float), typeof(float) })) == null) return Miss("GlyphMetrics(float x5)", out missing);
                    if ((SpriteGlyphCtor = SpriteGlyphType.GetConstructor(new[] { typeof(uint), GlyphMetricsType, GlyphRectType, typeof(float), typeof(int) })) == null) return Miss("TMP_SpriteGlyph(uint,GlyphMetrics,GlyphRect,float,int)", out missing);
                    if ((SpriteCharCtor = SpriteCharType.GetConstructor(new[] { typeof(uint), SpriteGlyphType })) == null) return Miss("TMP_SpriteCharacter(uint,TMP_SpriteGlyph)", out missing);
                    if ((SpriteSheetField = SpriteAssetType.GetField("spriteSheet", pub)) == null) return Miss("TMP_SpriteAsset.spriteSheet", out missing);
                    if ((MaterialField = SpriteAssetType.GetField("material", pub)) == null) return Miss("TMP_Asset.material", out missing);
                    if ((HashCodeField = SpriteAssetType.GetField("hashCode", pub)) == null) return Miss("TMP_Asset.hashCode", out missing);
                    if ((VersionField = SpriteAssetType.GetField("m_Version", priv)) == null) return Miss("TMP_SpriteAsset.m_Version", out missing);
                    if ((FallbackField = SpriteAssetType.GetField("fallbackSpriteAssets", pub)) == null) return Miss("TMP_SpriteAsset.fallbackSpriteAssets", out missing);
                    if ((GlyphTableProp = SpriteAssetType.GetProperty("spriteGlyphTable", pub)) == null) return Miss("TMP_SpriteAsset.spriteGlyphTable", out missing);
                    if ((CharTableProp = SpriteAssetType.GetProperty("spriteCharacterTable", pub)) == null) return Miss("TMP_SpriteAsset.spriteCharacterTable", out missing);
                    if ((NameProp = SpriteCharType.GetProperty("name", pub)) == null || !NameProp.CanWrite) return Miss("TMP_SpriteCharacter.name", out missing);
                    if ((SpriteAssetProp = TmpTextType.GetProperty("spriteAsset", pub)) == null || !SpriteAssetProp.CanWrite) return Miss("TMP_Text.spriteAsset", out missing);
                    if ((UpdateLookupTables = SpriteAssetType.GetMethod("UpdateLookupTables", pub, null, Type.EmptyTypes, null)) == null) return Miss("TMP_SpriteAsset.UpdateLookupTables()", out missing);
                    _ok = true;
                    missing = null;
                    return true;
                }
                catch (Exception ex)
                {
                    return Miss("reflection threw " + ex.GetType().Name + ": " + ex.Message, out missing);
                }
            }

            private static bool Miss(string what, out string missing)
            {
                _missing = missing = what;
                _ok = false;
                return false;
            }
        }

        // ── emoji-index.json (manual parsing: JsonUtility cannot read nested arrays) ──

        internal sealed class AtlasIndex
        {
            internal sealed class SheetInfo { public string File; public string Sha256; public long Bytes; }
            internal struct Seq { public string Key; public int SheetIndex, X, Y; }

            public string Version;
            public int Cell, Sheet, Ascent;
            public readonly List<SheetInfo> Sheets = new List<SheetInfo>();
            public readonly List<Seq> Sequences = new List<Seq>();

            /// <summary>Strict: version, geometry, 1..MAX_SHEETS sheets named
            /// emoji-sheet-N.png in order with 64-hex sha256 and a positive size,
            /// at least one sequence, every placement inside its sheet.</summary>
            public static bool TryParse(string json, out AtlasIndex index, out string err)
            {
                index = null; err = null;
                try
                {
                    var ix = new AtlasIndex();
                    if (!ReadString(json, "version", out ix.Version)) { err = "version missing"; return false; }
                    if (ix.Version != ATLAS_VERSION) { err = "version '" + ix.Version + "' is not " + ATLAS_VERSION; return false; }
                    long v;
                    if (!ReadLong(json, "cell", out v) || v < 8 || v > 512) { err = "cell missing/out of range"; return false; }
                    ix.Cell = (int)v;
                    if (!ReadLong(json, "sheet", out v) || v < ix.Cell || v > 4096) { err = "sheet missing/out of range"; return false; }
                    ix.Sheet = (int)v;
                    if (!ReadLong(json, "ascent", out v) || v < 0 || v > ix.Cell) { err = "ascent missing/out of range"; return false; }
                    ix.Ascent = (int)v;
                    if (!ParseSheets(json, ix, out err)) return false;
                    if (!ParseSequences(json, ix, out err)) return false;
                    index = ix;
                    return true;
                }
                catch (Exception ex) { err = ex.GetType().Name + ": " + ex.Message; return false; }
            }

            private static bool ParseSheets(string json, AtlasIndex ix, out string err)
            {
                err = null;
                int p = FindKey(json, "sheets", 0);
                if (p < 0) { err = "sheets missing"; return false; }
                p = SkipWs(json, p);
                if (p >= json.Length || json[p] != '[') { err = "sheets is not an array"; return false; }
                p++;
                for (; ; )
                {
                    p = SkipWs(json, p);
                    if (p >= json.Length) { err = "sheets unterminated"; return false; }
                    if (json[p] == ']') break;
                    if (json[p] != '{') { err = "sheet entry is not an object"; return false; }
                    int close = json.IndexOf('}', p);
                    if (close < 0) { err = "sheet object unterminated"; return false; }
                    string obj = json.Substring(p, close - p + 1);
                    var s = new SheetInfo();
                    if (!ReadString(obj, "file", out s.File) || !ReadString(obj, "sha256", out s.Sha256) || !ReadLong(obj, "bytes", out s.Bytes))
                    { err = "sheet entry incomplete"; return false; }
                    if (s.File != SHEET_PREFIX + ix.Sheets.Count.ToString(CultureInfo.InvariantCulture) + ".png") { err = "sheet file name/order '" + s.File + "'"; return false; }
                    if (s.Sha256.Length != 64 || !IsHex(s.Sha256)) { err = "sheet sha256 malformed"; return false; }
                    if (s.Bytes <= 0 || s.Bytes > MAX_SHEET_BYTES) { err = "sheet size out of range"; return false; }
                    ix.Sheets.Add(s);
                    if (ix.Sheets.Count > MAX_SHEETS) { err = "more than " + MAX_SHEETS + " sheets"; return false; }
                    p = SkipWs(json, close + 1);
                    if (p < json.Length && json[p] == ',') p++;
                }
                if (ix.Sheets.Count == 0) { err = "no sheets"; return false; }
                return true;
            }

            private static bool ParseSequences(string json, AtlasIndex ix, out string err)
            {
                err = null;
                int p = FindKey(json, "sequences", 0);
                if (p < 0) { err = "sequences missing"; return false; }
                p = SkipWs(json, p);
                if (p >= json.Length || json[p] != '{') { err = "sequences is not an object"; return false; }
                p++;
                var seen = new HashSet<string>(StringComparer.Ordinal);
                for (; ; )
                {
                    p = SkipWs(json, p);
                    if (p >= json.Length) { err = "sequences unterminated"; return false; }
                    if (json[p] == '}') break;
                    if (json[p] != '"') { err = "sequence key expected"; return false; }
                    int q = json.IndexOf('"', p + 1);
                    if (q < 0) { err = "sequence key unterminated"; return false; }
                    string key = json.Substring(p + 1, q - p - 1);
                    if (!IsSeqKey(key)) { err = "sequence key malformed '" + key + "'"; return false; }
                    if (!seen.Add(key)) { err = "duplicate sequence key " + key; return false; }
                    p = SkipWs(json, q + 1);
                    if (p >= json.Length || json[p] != ':') { err = "colon expected after " + key; return false; }
                    p = SkipWs(json, p + 1);
                    if (p >= json.Length || json[p] != '[') { err = "placement array expected for " + key; return false; }
                    int close = json.IndexOf(']', p);
                    if (close < 0) { err = "placement unterminated"; return false; }
                    string[] parts = json.Substring(p + 1, close - p - 1).Split(',');
                    int si, x, y;
                    if (parts.Length != 3
                        || !int.TryParse(parts[0].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out si)
                        || !int.TryParse(parts[1].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out x)
                        || !int.TryParse(parts[2].Trim(), NumberStyles.None, CultureInfo.InvariantCulture, out y))
                    { err = "placement malformed for " + key; return false; }
                    if (si < 0 || si >= ix.Sheets.Count || x < 0 || y < 0 || x + ix.Cell > ix.Sheet || y + ix.Cell > ix.Sheet)
                    { err = "placement out of range for " + key; return false; }
                    ix.Sequences.Add(new Seq { Key = key, SheetIndex = si, X = x, Y = y });
                    p = SkipWs(json, close + 1);
                    if (p < json.Length && json[p] == ',') p++;
                }
                if (ix.Sequences.Count == 0) { err = "no sequences"; return false; }
                return true;
            }

            /// <summary>Position just after the colon following "name" (the key
            /// with its quotes, so "sheet" never matches "sheets"), or -1.</summary>
            private static int FindKey(string json, string name, int from)
            {
                string needle = "\"" + name + "\"";
                int p = from;
                for (; ; )
                {
                    p = json.IndexOf(needle, p, StringComparison.Ordinal);
                    if (p < 0) return -1;
                    int q = SkipWs(json, p + needle.Length);
                    if (q < json.Length && json[q] == ':') return q + 1;
                    p += needle.Length;
                }
            }

            private static bool ReadString(string json, string name, out string value)
            {
                value = null;
                int p = FindKey(json, name, 0);
                if (p < 0) return false;
                p = SkipWs(json, p);
                if (p >= json.Length || json[p] != '"') return false;
                int q = json.IndexOf('"', p + 1);
                if (q < 0) return false;
                value = json.Substring(p + 1, q - p - 1);
                return value.IndexOf('\\') < 0;   // the tool never escapes; a backslash here is not our file
            }

            private static bool ReadLong(string json, string name, out long value)
            {
                value = 0;
                int p = FindKey(json, name, 0);
                if (p < 0) return false;
                p = SkipWs(json, p);
                int q = p;
                while (q < json.Length && json[q] >= '0' && json[q] <= '9') q++;
                if (q == p) return false;
                return long.TryParse(json.Substring(p, q - p), NumberStyles.None, CultureInfo.InvariantCulture, out value);
            }

            private static int SkipWs(string s, int p)
            {
                while (p < s.Length && (s[p] == ' ' || s[p] == '\n' || s[p] == '\r' || s[p] == '\t')) p++;
                return p;
            }

            private static bool IsHex(string s)
            {
                for (int i = 0; i < s.Length; i++)
                {
                    char c = s[i];
                    if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return false;
                }
                return true;
            }

            private static bool IsSeqKey(string k)
            {
                if (k.Length == 0 || k.Length > 80 || k[0] == '-' || k[k.Length - 1] == '-') return false;
                for (int i = 0; i < k.Length; i++)
                {
                    char c = k[i];
                    if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || c == '-')) return false;
                    if (c == '-' && k[i - 1] == '-') return false;
                }
                return true;
            }
        }
    }

    /// <summary>The runtime half of tools/emoji_atlas.py's Matcher - the SAME
    /// algorithm, the SAME self-check vectors (the pytest reads them out of this
    /// file). Pure: no Unity, no reflection; usable from any thread.
    ///
    /// Rules: text without a char >= U+00A9 is returned as-is; a rich-text tag
    /// (letter, '/' or '#' after '&lt;', a '&gt;' within 128 chars, no newline or
    /// second '&lt;' inside) is copied verbatim; elsewhere the trie is walked over
    /// code points and the LONGEST terminal wins; a skin-tone modifier or VS16
    /// the trie does not spell at the current node is skipped during the walk and
    /// consumed after a match (a toned form the atlas lacks shows its neutral
    /// sprite, never a stray swatch); everything else passes through unchanged.</summary>
    internal sealed class EmojiMatcher
    {
        private const int VS16 = 0xFE0F;

        private sealed class Node
        {
            public Dictionary<int, Node> Kids;
            public string Key;
        }

        private readonly Node _root = new Node();
        public int Count { get; private set; }

        public EmojiMatcher(IEnumerable<string> keys)
        {
            foreach (var k in keys)
            {
                if (string.IsNullOrEmpty(k)) continue;
                var node = _root;
                bool any = false;
                foreach (var part in k.Split('-'))
                {
                    if (part.Length == 0) continue;
                    int cp;
                    if (!int.TryParse(part, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out cp)) { node = null; break; }
                    if (node.Kids == null) node.Kids = new Dictionary<int, Node>();
                    Node next;
                    if (!node.Kids.TryGetValue(cp, out next)) { next = new Node(); node.Kids[cp] = next; }
                    node = next;
                    any = true;
                }
                if (node == null || !any) continue;
                if (node.Key == null) Count++;
                node.Key = k.ToUpperInvariant();
            }
        }

        public static string Tag(string key, bool tint)
        {
            return "<sprite name=\"" + EmojiSprites.SPRITE_NAME_PREFIX + key + "\"" + (tint ? " tint=1" : "") + ">";
        }

        private static bool IsModifier(int cp) { return cp == VS16 || (cp >= 0x1F3FB && cp <= 0x1F3FF); }

        public string Substitute(string text, bool tint)
        {
            if (string.IsNullOrEmpty(text)) return text;
            bool any = false;
            for (int i = 0; i < text.Length; i++) if (text[i] >= '\u00A9') { any = true; break; }
            if (!any) return text;
            var sb = new StringBuilder(text.Length + 32);
            int n = text.Length, p = 0;
            while (p < n)
            {
                char c = text[p];
                if (c == '<')
                {
                    int end = TagEnd(text, p);
                    if (end > 0) { sb.Append(text, p, end - p); p = end; continue; }
                }
                string key;
                int matchEnd = Match(text, p, out key);
                if (key != null)
                {
                    sb.Append(Tag(key, tint));
                    p = matchEnd;
                    while (p < n)
                    {
                        int len;
                        int cp = Cp(text, p, out len);
                        if (IsModifier(cp)) p += len; else break;
                    }
                    continue;
                }
                int l;
                Cp(text, p, out l);
                sb.Append(text, p, l);
                p += l;
            }
            return sb.ToString();
        }

        private static int TagEnd(string s, int i)
        {
            int n = s.Length;
            if (i + 1 >= n) return -1;
            char c1 = s[i + 1];
            if (!(c1 < 128 && (char.IsLetter(c1) || c1 == '/' || c1 == '#'))) return -1;
            int limit = Math.Min(n, i + 129);
            for (int j = i + 1; j < limit; j++)
            {
                char ch = s[j];
                if (ch == '>') return j + 1;
                if (ch == '<' || ch == '\n') return -1;
            }
            return -1;
        }

        private static int Cp(string s, int i, out int len)
        {
            char c = s[i];
            if (char.IsHighSurrogate(c) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]))
            {
                len = 2;
                return char.ConvertToUtf32(c, s[i + 1]);
            }
            len = 1;
            return c;
        }

        private int Match(string s, int i, out string key)
        {
            var node = _root;
            int j = i, bestEnd = -1, n = s.Length;
            key = null;
            while (j < n)
            {
                int len;
                int cp = Cp(s, j, out len);
                Node next = null;
                if (node.Kids == null || !node.Kids.TryGetValue(cp, out next))
                {
                    if (j > i && IsModifier(cp)) { j += len; continue; }   // transparent: the walk continues past it
                    break;
                }
                node = next;
                j += len;
                if (node.Key != null) { bestEnd = j; key = node.Key; }
            }
            return bestEnd;
        }

        /// <summary>TMP_TextUtilities.GetSimpleHashCode - used only to give the
        /// runtime asset a plausible hashCode; sprite NAME lookups hash inside TMP.</summary>
        public static int SimpleHash(string s)
        {
            int h = 0;
            for (int i = 0; i < s.Length; i++) h = ((h << 5) + h) ^ s[i];
            return h;
        }

        // Shared self-check vectors - mirrors tools/emoji_atlas.py SELF_CHECK_*.
        // backend/tests/test_emoji_atlas.py decodes the literals between these
        // markers and fails when the two lists drift. Escapes only: a literal
        // ZWJ or VS16 in source is invisible. No quotes in comments inside the
        // marker blocks (the test collects every string literal in them).
        // EMOJI-SELFCHECK-KEYS-BEGIN
        internal static readonly string[] SelfCheckKeys =
        {
            "1F600", "1F468-200D-1F469-200D-1F467", "1F468", "1F469", "1F467",
            "2764-FE0F", "0023-FE0F-20E3", "1F44D", "1F1FA-1F1F8", "1F469-200D-1F680",
            "1F634",
        };
        // EMOJI-SELFCHECK-KEYS-END
        // EMOJI-SELFCHECK-VECTORS-BEGIN
        internal static readonly string[][] SelfCheckVectors =
        {
            new[] { "hi \U0001F600", "hi <sprite name=\"e_1F600\">" },
            new[] { "\U0001F468\u200D\U0001F469\u200D\U0001F467", "<sprite name=\"e_1F468-200D-1F469-200D-1F467\">" },
            new[] { "\U0001F468\u200D\U0001F469\u200D\U0001F466", "<sprite name=\"e_1F468\">\u200D<sprite name=\"e_1F469\">\u200D\U0001F466" },
            new[] { "\u2764", "\u2764" },
            new[] { "\u2764\uFE0F", "<sprite name=\"e_2764-FE0F\">" },
            new[] { "#\uFE0F\u20E3", "<sprite name=\"e_0023-FE0F-20E3\">" },
            new[] { "#\u20E3", "#\u20E3" },
            new[] { "# 1", "# 1" },
            new[] { "\U0001F44D\U0001F3FD!", "<sprite name=\"e_1F44D\">!" },
            new[] { "\U0001F469\U0001F3FD\u200D\U0001F680", "<sprite name=\"e_1F469-200D-1F680\">" },
            new[] { "\U0001F600\uFE0F", "<sprite name=\"e_1F600\">" },
            new[] { "<sprite name=\"e_1F600\"> \U0001F600", "<sprite name=\"e_1F600\"> <sprite name=\"e_1F600\">" },
            new[] { "<color=#FF0000>\U0001F600</color>", "<color=#FF0000><sprite name=\"e_1F600\"></color>" },
            new[] { "a < b \U0001F600", "a < b <sprite name=\"e_1F600\">" },
            new[] { "\U0001F1FA\U0001F1F8", "<sprite name=\"e_1F1FA-1F1F8\">" },
            new[] { "\U0001F1FA", "\U0001F1FA" },
            new[] { "hello", "hello" },
            new[] { "", "" },
            new[] { "\U0001F600\U0001F600", "<sprite name=\"e_1F600\"><sprite name=\"e_1F600\">" },
            new[] { "caf\u00E9 \u2603", "caf\u00E9 \u2603" },
            new[] { "(\U0001F634)", "(<sprite name=\"e_1F634\">)" },
        };
        // EMOJI-SELFCHECK-VECTORS-END
        // EMOJI-SELFCHECK-TINT-BEGIN
        internal static readonly string[] SelfCheckTint = { "\U0001F600", "<sprite name=\"e_1F600\" tint=1>" };
        // EMOJI-SELFCHECK-TINT-END

        /// <summary>[Chat] EmojiSpritesSelfTest: one line per vector, one summary
        /// (the LagNotices/H2HRules shape). Nothing shown, sent or persisted.</summary>
        internal static void RunSelfTest(Action<string> info, Action<string> warn)
        {
            int run = 0, pass = 0, fail = 0;
            int expected = SelfCheckVectors.Length + 1;
            try
            {
                var m = new EmojiMatcher(SelfCheckKeys);
                for (int i = 0; i < SelfCheckVectors.Length; i++)
                {
                    run++;
                    string got;
                    try { got = m.Substitute(SelfCheckVectors[i][0], false); }
                    catch (Exception ex) { got = "EXCEPTION:" + ex.GetType().Name; }
                    bool ok = got == SelfCheckVectors[i][1];
                    if (ok) pass++; else fail++;
                    info("[EMOJI] selftest case=" + i + " expected=" + Escape(SelfCheckVectors[i][1]) + " got=" + Escape(got) + (ok ? " PASS" : " FAIL"));
                }
                run++;
                string tinted = m.Substitute(SelfCheckTint[0], true);
                bool tok = tinted == SelfCheckTint[1];
                if (tok) pass++; else fail++;
                info("[EMOJI] selftest case=tint expected=" + Escape(SelfCheckTint[1]) + " got=" + Escape(tinted) + (tok ? " PASS" : " FAIL"));
            }
            catch (Exception ex)
            {
                fail++;
                warn("[EMOJI] selftest harness failed: " + ex.Message);
            }
            bool all = run == expected && fail == 0;
            string summary = "[EMOJI] selftest summary run=" + run + " expected=" + expected + " pass=" + pass + " fail=" + fail + (all ? " PASS" : " FAIL");
            if (all) info(summary); else warn(summary);
        }

        private static string Escape(string s)
        {
            if (s == null) return "null";
            var sb = new StringBuilder(s.Length + 8);
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c < 0x20 || c > 0x7E) sb.Append("\\u").Append(((int)c).ToString("X4"));
                else sb.Append(c);
            }
            return sb.ToString();
        }
    }
}
