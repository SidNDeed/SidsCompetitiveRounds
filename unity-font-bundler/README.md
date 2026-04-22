# Font Bundler — Unity project for baking TMP_FontAssets

Sister project to the BepInEx mod. Turns raw `.ttf` files into TMP font assets and packs them into an AssetBundle the mod loads at runtime.

## One-time setup

1. Install **Unity Hub** (`unity.com/download` → Unity Hub).
2. Install **Unity Editor 2022.3.34f1** (the exact version ROUNDS is built on; any other version will produce binary-incompatible TMP assets). Via Hub: Installs → Add → find `2022.3.34f1` (may need to click "Archive" if it's not in the default list) → include **Windows Build Support (IL2CPP)**. ~10 GB + 30-60 min.
3. Open this folder (`unity-font-bundler/`) in Unity Hub: Projects → Open → select `unity-font-bundler/`. First open takes 5-10 min to import Assets and compile.

## Building the bundle

Top menu → **Competitive Rounds → Build Font Bundle**.

The script:
1. Walks every `.ttf`/`.otf` in `Assets/FontSources/`.
2. Imports each as a Unity `Font` asset.
3. Bakes a `TMP_FontAsset` with SDF-AA atlas, sampling size 64, 512×512 starting atlas (dynamic — grows on demand).
4. Saves the baked asset to `Assets/TMPFonts/<fontkey>.asset`.
5. Tags all baked assets with the AssetBundle name `comp-rounds-fonts`.
6. Builds a `StandaloneWindows64` AssetBundle and writes it to `../plugin/bin/Release/netstandard2.1/comp-rounds-fonts` (alongside the DLL).

Incremental: re-running the menu item skips fonts whose baked `.asset` already exists. Delete the `.asset` in `Assets/TMPFonts/` to force a rebake.

## Adding a new font

1. Drop `newfont.ttf` into `Assets/FontSources/`.
2. Run `Competitive Rounds → Build Font Bundle`.
3. Back in the main repo: edit `plugin/NametagFontRenderer.cs` `_skuToTmpFontName` to add `{ "nametag_typeface_newfont", "newfont" }`.
4. Add a SQL migration (`backend/sql/0NN_add_newfont.sql`) inserting the new shop item.
5. Rebuild the mod DLL.

## What NOT to do

- Don't rename `Assets/Editor/FontBundler.cs` — the menu path is wired to the namespace.
- Don't commit `Library/`, `Temp/`, `Obj/`, `UserSettings/`, or `*.csproj` — they're all regenerated on project open. The `.gitignore` handles this.
- Don't bake with a different Unity version; the resulting AssetBundle's serialization format won't match ROUNDS at runtime.

## Licensing

Every TTF in `Assets/FontSources/` is under either SIL Open Font License 1.1 or Apache License 2.0 (the two free-to-redistribute licenses Google Fonts uses). Safe to bundle + ship with the mod. Source license files are tracked alongside the fonts when the upstream repo includes them.
