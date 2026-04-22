#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.IO;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.TextCore.LowLevel;  // GlyphRenderMode

namespace CompetitiveRounds.FontBundler
{
    /// <summary>
    /// One-button pipeline that turns raw .ttf files in Assets/FontSources/ into TMP_FontAssets
    /// and packs them into an AssetBundle the BepInEx mod can load at runtime.
    ///
    /// Usage:
    ///   1. Drop .ttf files into Assets/FontSources/. Name them <fontkey>.ttf (lowercase,
    ///      no spaces). The fontkey becomes the sku suffix — e.g. pacifico.ttf → the mod
    ///      looks up "pacifico" → nametag_typeface_pacifico.
    ///   2. Top menu → Competitive Rounds → Build Font Bundle.
    ///   3. The script imports each TTF as a Font asset, bakes a TMP_FontAsset from it
    ///      (Dynamic atlas with a reasonable default sampling size), assigns an AssetBundle
    ///      label to each, and builds a StandaloneWindows AssetBundle named
    ///      "comp-rounds-fonts" at ../plugin/bin/Release/netstandard2.1/ so the next mod
    ///      build picks it up next to the DLL.
    ///
    /// Incremental-safe: re-running skips TTFs whose TMP_FontAsset already exists. Delete
    /// the generated .asset in Assets/TMPFonts/ to force a rebake.
    /// </summary>
    public static class FontBundler
    {
        private const string BUNDLE_NAME = "comp-rounds-fonts";
        private const string FONT_SOURCES_DIR = "Assets/FontSources";
        private const string TMP_FONTS_DIR = "Assets/TMPFonts";
        // Atlas knobs. 512x512 is enough for ASCII + Latin-1 supplement; TMP grows the atlas
        // on demand for dynamic fonts, so this is just a starting hint. Sampling point size
        // 64 is a good balance of SDF sharpness vs atlas memory for nametag-sized rendering.
        private const int ATLAS_WIDTH = 512;
        private const int ATLAS_HEIGHT = 512;
        private const int SAMPLING_POINT_SIZE = 64;
        private const int ATLAS_PADDING = 6;

        [MenuItem("Competitive Rounds/Build Font Bundle")]
        public static void BuildBundle()
        {
            if (!Directory.Exists(FONT_SOURCES_DIR))
            {
                EditorUtility.DisplayDialog(
                    "Font Bundler",
                    $"Missing folder: {FONT_SOURCES_DIR}\nPut .ttf / .otf files there and try again.",
                    "OK");
                return;
            }
            if (!Directory.Exists(TMP_FONTS_DIR))
                Directory.CreateDirectory(TMP_FONTS_DIR);

            var ttfPaths = Directory.GetFiles(FONT_SOURCES_DIR, "*.ttf");
            var otfPaths = Directory.GetFiles(FONT_SOURCES_DIR, "*.otf");
            var allFontFiles = new List<string>(ttfPaths);
            allFontFiles.AddRange(otfPaths);
            if (allFontFiles.Count == 0)
            {
                EditorUtility.DisplayDialog(
                    "Font Bundler",
                    $"No .ttf or .otf files in {FONT_SOURCES_DIR}.",
                    "OK");
                return;
            }

            AssetDatabase.Refresh();

            var tmpFontPaths = new List<string>();
            int baked = 0, skipped = 0;
            foreach (var srcPath in allFontFiles)
            {
                string fontKey = Path.GetFileNameWithoutExtension(srcPath).ToLowerInvariant().Replace(" ", "").Replace("-", "");
                string tmpAssetPath = $"{TMP_FONTS_DIR}/{fontKey}.asset";

                if (File.Exists(tmpAssetPath))
                {
                    // Ensure bundle label is set even on existing assets (someone might have
                    // pulled the repo after we renamed the bundle, etc.).
                    SetBundleLabel(tmpAssetPath);
                    tmpFontPaths.Add(tmpAssetPath);
                    skipped++;
                    continue;
                }

                var srcFont = AssetDatabase.LoadAssetAtPath<Font>(srcPath);
                if (srcFont == null)
                {
                    Debug.LogWarning($"[FontBundler] Skipping {srcPath} — Unity couldn't import it as a Font. Re-save the TTF.");
                    continue;
                }

                var tmpAsset = TMP_FontAsset.CreateFontAsset(
                    srcFont,
                    SAMPLING_POINT_SIZE,
                    ATLAS_PADDING,
                    GlyphRenderMode.SDFAA,
                    ATLAS_WIDTH,
                    ATLAS_HEIGHT,
                    AtlasPopulationMode.Dynamic,
                    enableMultiAtlasSupport: true);
                if (tmpAsset == null)
                {
                    Debug.LogWarning($"[FontBundler] TMP_FontAsset.CreateFontAsset returned null for {srcPath}.");
                    continue;
                }
                tmpAsset.name = fontKey;

                AssetDatabase.CreateAsset(tmpAsset, tmpAssetPath);
                SetBundleLabel(tmpAssetPath);
                tmpFontPaths.Add(tmpAssetPath);
                baked++;
                Debug.Log($"[FontBundler] Baked {fontKey} → {tmpAssetPath}");
            }

            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            // AssetBundle output goes directly into the plugin output folder so `dotnet build`
            // picks it up on the next mod build. Path is relative to the project root (the
            // one containing Assets/, Packages/, ProjectSettings/).
            string outDir = Path.GetFullPath(Path.Combine(
                Application.dataPath, "..", "..", "plugin", "bin", "Release", "netstandard2.1"));
            if (!Directory.Exists(outDir))
                Directory.CreateDirectory(outDir);

            var builds = new[]
            {
                new AssetBundleBuild
                {
                    assetBundleName = BUNDLE_NAME,
                    assetNames = tmpFontPaths.ToArray(),
                },
            };

            // Force rebuild so Unity's up-to-date check can't short-circuit us when the
            // Editor version changes but asset hashes haven't. Log the chosen Unity version
            // so we can verify in the Console which install actually produced this bundle —
            // AssetBundle binary format varies across Unity patch revisions.
            Debug.Log($"[FontBundler] Unity {Application.unityVersion} — building {tmpFontPaths.Count} asset(s) into {BUNDLE_NAME}...");

            // Serialization flags. Previous attempts used ChunkBasedCompression and hit
            // "AssetBundle not compatible with this newer version of the Unity runtime"
            // when the Editor-side Unity build differed from ROUNDS' runtime build. The
            // chunked format is serialization-version-sensitive. Uncompressed + stripped
            // type tree ('DisableWriteTypeTree') produces the most forward-/backward-
            // compatible bundle at the cost of bundle size (~2.4MB becomes ~8MB but we
            // don't care — it's shipped once). DisableWriteTypeTree is safe as long as
            // the mod runtime uses the same TMP types as the editor, which it does
            // because both reference com.unity.textmeshpro 3.0.9.
            var manifest = BuildPipeline.BuildAssetBundles(
                outDir,
                builds,
                BuildAssetBundleOptions.UncompressedAssetBundle
                    | BuildAssetBundleOptions.DisableWriteTypeTree
                    | BuildAssetBundleOptions.ForceRebuildAssetBundle,
                BuildTarget.StandaloneWindows64);

            if (manifest == null)
            {
                EditorUtility.DisplayDialog(
                    "Font Bundler",
                    "BuildAssetBundles returned null — check the console for errors.",
                    "OK");
                return;
            }

            string bundlePath = Path.Combine(outDir, BUNDLE_NAME);
            if (!File.Exists(bundlePath))
            {
                Debug.LogError($"[FontBundler] Bundle file missing after build: {bundlePath}");
                EditorUtility.DisplayDialog(
                    "Font Bundler — failed",
                    $"BuildAssetBundles ran but no file appeared at:\n{bundlePath}\n\n" +
                    $"Check the Console for errors (the \"AssetBundle module is disabled\" warning is often the smoking gun — if you see it, the project opened with a Unity install that doesn't include Windows build support).",
                    "OK");
                return;
            }
            long size = new FileInfo(bundlePath).Length;
            Debug.Log($"[FontBundler] Bundle written: {bundlePath} ({size / 1024} KB, {baked} baked / {skipped} reused)");
            EditorUtility.DisplayDialog(
                "Font Bundler — done",
                $"Unity: {Application.unityVersion}\n" +
                $"Baked {baked} new font(s), reused {skipped} existing.\n" +
                $"Bundle: {bundlePath}\n" +
                $"Size: {size / 1024} KB\n\n" +
                $"Next step: rebuild the mod DLL (dotnet build plugin/CompetitiveRounds.csproj -c Release). " +
                $"The MSBuild CopyToPlugins target will pick up both the DLL and this .bundle file.",
                "OK");
        }

        private static void SetBundleLabel(string assetPath)
        {
            var importer = AssetImporter.GetAtPath(assetPath);
            if (importer == null) return;
            if (importer.assetBundleName != BUNDLE_NAME)
            {
                importer.assetBundleName = BUNDLE_NAME;
                importer.SaveAndReimport();
            }
        }
    }
}
#endif
