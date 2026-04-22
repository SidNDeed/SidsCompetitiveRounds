# Shelved: custom nametag typefaces + glow effects

Both features ran into Unity / TMP engine limits that couldn't be worked around with the tools available. Feature code stays in-repo as infrastructure for a future attempt. This doc captures what we tried, why each path failed, and what to revisit.

## Custom typefaces

**Goal:** Let players buy visually distinct fonts for their in-game nametag (gothic, cursive, pixel, horror, etc.) — local-only rendering so non-modded players see the plain name with no artifacts.

### What we picked (22 OFL-licensed fonts across 11 styles)

| Rarity | Price | Fonts |
|---|---|---|
| Common | 100g | Caveat, Permanent Marker, Courier Prime |
| Uncommon | 150g | Pacifico, Playfair Display, Special Elite, VT323, MedievalSharp, Smokum, Rye, Orbitron |
| Rare | 250g | Great Vibes, Cinzel Decorative, Press Start 2P, Audiowide, Monoton, Bungee Shade, Metal Mania |
| Legendary | 500g | UnifrakturMaguntia, Creepster, Rubik Puddles, Rubik Marker Hatch |

TTF sources: Google Fonts GitHub repo (`ofl/` and `apache/` subdirs), all under OFL 1.1 or Apache 2.0 — legal to redistribute.

### What we built

- `unity-font-bundler/` — a Unity 2022.3.34f1 project with:
  - `Assets/FontSources/` — 22 TTF files
  - `Assets/Editor/FontBundler.cs` — menu item `Competitive Rounds ▸ Build Font Bundle` that bakes each TTF into a `TMP_FontAsset` and writes a `comp-rounds-fonts` AssetBundle to `plugin/bin/Release/netstandard2.1/`
- `plugin/NametagFontRenderer.cs` — runtime loader that reads the bundle at plugin startup (`AssetBundle.LoadFromFile` next to the DLL), looks up `TMP_FontAsset` by name, and swaps `TMP_Text.font` on matching player nametag labels
- MSBuild target in `plugin/CompetitiveRounds.csproj` that copies the bundle next to the DLL in BepInEx on every build
- SQL migration 041 inserted the 22 SKUs; migration 042 deleted them + refunded

### Why each attempt failed

1. **First try — `Font.CreateDynamicFontFromOSFont` + TMP's `CreateFontAsset` at runtime.** Unity explicitly documents OS fonts as incompatible with TMP's SDF pipeline. Log showed `Unable to load font face for [Papyrus]. Make sure "Include Font Data" is enabled in the Font Import Settings.` `CreateDynamicFontFromOSFont` returns a `Font` without raw face data; TMP needs face data to rasterize glyphs into its SDF atlas. Dead end.
2. **Second try — pre-baked `TMP_FontAssets` shipped via AssetBundle, Editor-built.** Bundle builds fine, but `AssetBundle.LoadFromFile` returns null at ROUNDS runtime with `could not be loaded because it is not compatible with this newer version of the Unity runtime`. The Unity build hash our Editor produces (`4886f5360533`, the only one Unity's archive currently serves for `2022.3.34f1`) differs from the Unity build ROUNDS was compiled against. Bundle serialization format is version-sensitive.
3. **Tried `BuildAssetBundleOptions.UncompressedAssetBundle | DisableWriteTypeTree` for forward-compat.** Same error. The incompatibility is in the bundle header, not the asset contents.
4. **Tried direct-URL install of specific Unity build hashes.** Unity Hub delivered the current archive build (`4886f5360533`) regardless of the hash in the URL.

### What to try if picking this up again

- **Internet Archive / Wayback Machine** for a cached older Unity 2022.3.34f1 installer (the hash ROUNDS was actually built with — we don't know what that hash is; the `1613658dd9ba` we found in `globalgamemanagers` turned out to be an asset GUID, not the Unity build hash).
- **Contact Landfall or Unity support** — they can sometimes provide specific historical builds for source-compatibility reasons.
- **Reflection-based TMP font asset creation** — bypass AssetBundle entirely. Call TMP's internal font asset builder (the same one the Editor uses) at runtime with TTF bytes embedded in the mod DLL. Experimental but avoids the Unity-version trap.
- **Ship a custom TMP shader** alongside the fonts (addresses the glow problem too — see below). Same AssetBundle pipeline; same version-compat risk.

## Glow effects

**Goal:** 4 glow SKUs (red/blue/gold/pink) applied locally by `NametagGlowRenderer.cs` — clones the TMP material, enables `GLOW_ON`/`UNDERLAY_ON` shader keywords, paints a colored halo around the nametag letters.

### Why it failed

ROUNDS' TMP shader variants were compiled with the glow and underlay samplers stripped out at build time (probably for performance). Setting `GLOW_ON` / `UNDERLAY_ON` keywords at runtime has no rendering effect because the shader doesn't contain code to read those keywords. Confirmed across multiple sessions:

- Log showed material clone succeeds, keywords enabled, properties set correctly
- `[GLOW] post-set props: outlineWidth=... faceColor=... outlineColor=...` confirmed property values land
- Only outline renders visually; glow and underlay are silent no-ops

Falling back to outline alone gave "inconsistent highlighter" appearance rather than a glow.

### What to try if picking this up again

- **Dual-label halo** — instead of relying on shader keywords, spawn a second `TMP_Text` GameObject as a child of each player nametag, scale 1.15x, tint the glow color, set render order behind the main label. Produces an actual visible halo without shader support. ~1-2 hours of work; likely the right call.
- **Ship a custom TMP shader** with the glow sampler compiled in, loaded via AssetBundle (same pipeline as typefaces). Most "correct" but hits the Unity-version wall.

## Files involved (leave in-repo)

- `unity-font-bundler/` — Unity Editor project with the bundler
- `plugin/NametagFontRenderer.cs` — bundle loader + font swap logic
- `plugin/NametagGlowRenderer.cs` — glow material clone + outline application
- `plugin/NametagStyler.cs` — subgroup recognition for typeface SKUs (still handles `color/size/font` subgroups for the non-shelved styles)

The runtime code is dormant without matching shop SKUs — `GetOrBuildFontAsset` immediately returns null when given an unknown sku, and `ApplyGlowToLabel` short-circuits when the Photon `cr_nametag_glow` prop isn't set. Safe to leave loaded.
