using System;
using System.Collections.Generic;
using HarmonyLib;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Custom character cosmetics (face items) — shop-purchasable eyes / mouths /
    /// details that appear in ROUNDS' own character-editing menu next to the
    /// vanilla items and render everywhere a face renders (in-match body,
    /// card-pick visualizer, menu portraits).
    ///
    /// ── How vanilla works (decompile: CharacterCreator*, PlayerFace, Player) ──
    /// A face is 4 slots (eyes / mouth / detail / detail2), each an integer ID +
    /// drag offset, persisted in PlayerPrefs and synced in-match via
    /// Player.RPCA_SetFace / CardChoiceVisuals.Show (plus our own cr_face props).
    /// EVERY consumer resolves IDs through exactly two methods on
    /// CharacterCreatorItemLoader: GetItem(id, type) and GetItemID(item, type).
    /// GetItem try/catches out-of-range → null, and Equip(null) early-returns.
    ///
    /// ── Our design ──
    /// Custom items live at IDs >= CUSTOM_ID_BASE (1000), resolved by TWO Harmony
    /// prefixes on those methods — the vanilla arrays are never touched, so:
    ///   * vanilla items keep their vanilla IDs (saved faces stay stable),
    ///   * other array-appending mods can't shift our IDs,
    ///   * a client WITHOUT the item (vanilla opponent, older mod) resolves the
    ///     ID to null and simply renders that slot empty — no crash, no desync,
    ///   * ownership can gate the character-editor UI without hiding the item
    ///     from the RESOLVER (opponents' owned cosmetics render for everyone).
    /// The character editor lists owned items via a Postfix on
    /// CharacterCreatorButtonSpawner.OpenMenu that clones vanilla's own button
    /// flow, so click/equip/drag/save all run 100% vanilla code paths.
    ///
    /// Sprites are runtime-loaded PNGs (Texture2D.LoadImage + Sprite.Create) from
    /// plugins/CompetitiveRounds/cosmetics/ — the same pipeline as card art.
    /// AssetBundles are a dead end here: ROUNDS' Unity build hash is no longer
    /// downloadable, so no bundle we produce is binary-compatible (see the
    /// custom-nametag-typeface post-mortem in TODO.md). Rendering constants
    /// (layer "Player", sorting layer "MostFront", order eyes=3 / mouth=4 /
    /// detail=5, 512px ≈ scale 1) match Pykess's PlayerCustomizationUtilities,
    /// the 463k-download reference implementation for ROUNDS cosmetics.
    ///
    /// The CATALOG is append-only and ships with the mod — every client knows
    /// every item so remote faces render; the SHOP (kind='face') only gates
    /// which items the local player may equip. Equipping itself is vanilla
    /// (PlayerPrefs + face RPC) — the server stores no equip state.
    /// </summary>
    internal static class CustomCosmetics
    {
        public const int CUSTOM_ID_BASE = 1000;
        private const string TEMPLATE_PREFIX = "CRCOS_";

        internal class CosmeticDef
        {
            public string Sku;           // shop_items.sku (kind='face')
            public string DisplayName;
            public CharacterItemType Slot;
            public string PngFile;       // file under plugins/CompetitiveRounds/cosmetics/
            public float Scale = 1f;     // 512px PNG @ PPU100 ≈ scale 1 (FacesPlus spec)
            public Vector2 Offset = Vector2.zero; // default position; player can drag
            public float Fps = 10f;      // animation rate when extra frames exist
            public int Id;               // CUSTOM_ID_BASE + catalog index (assigned at init)
            public CharacterItem Template; // hidden template GO (built at init)
        }

        /// <summary>Animated cosmetics (July 12 round 2, item 7). Drop numbered
        /// frames beside any catalog PNG — `eyes_star.png` + `eyes_star__f2.png` +
        /// `eyes_star__f3.png` ... — and the item animates at CosmeticDef.Fps
        /// (default 10). No catalog/ID change: the base file stays frame 1, so a
        /// client WITHOUT the extra frames just renders the static art.
        ///
        /// The cycler lives on the hidden TEMPLATE; vanilla's SpawnItem does
        /// Object.Instantiate(template.gameObject) for every equip (body, pick
        /// visualizer, menu portrait — verified in the decompile), and Unity
        /// clones serialized component fields, so every rendered instance carries
        /// its own cycler with the shared Sprite[] — zero per-consumer patches.
        /// Unscaled time keeps all instances in frame-sync and immune to pause.</summary>
        internal class CosmeticFrameCycler : MonoBehaviour
        {
            public Sprite[] frames;
            public float fps = 10f;
            private SpriteRenderer sr;
            private int lastFrame = -1;
            private void Awake() { sr = GetComponent<SpriteRenderer>(); }
            private void Update()
            {
                if (frames == null || frames.Length < 2 || sr == null || fps <= 0f) return;
                // v1.32 item 8: static-cosmetics mode pins every animated face item to
                // frame 1. One check covers all clones (in-match body, pick visualizer,
                // menu portraits) because vanilla clones this component onto each.
                if (Plugin.AnimatedCosmetics != null && !Plugin.AnimatedCosmetics.Value)
                {
                    if (lastFrame != 0 || sr.sprite != frames[0])
                    {
                        sr.sprite = frames[0];
                        lastFrame = 0;
                    }
                    return;
                }
                int frame = (int)(Time.unscaledTime * fps) % frames.Length;
                if (frame == lastFrame && sr.sprite == frames[frame]) return;
                sr.sprite = frames[frame];
                lastFrame = frame;
            }
        }

        // ── Catalog — APPEND ONLY. Index order defines the network ID, so items
        // must never be removed or reordered; retire an item by pointing its
        // sku at a hidden shop row instead. Every client ships the full catalog.
        private static readonly CosmeticDef[] Catalog = new[]
        {
            new CosmeticDef { Sku = "face_eyes_star",    DisplayName = "Star Eyes",      Slot = CharacterItemType.Eyes,   PngFile = "eyes_star.png",    Scale = 1.0f, Offset = new Vector2(0f, 0.10f) },
            new CosmeticDef { Sku = "face_eyes_hearts",  DisplayName = "Heart Eyes",     Slot = CharacterItemType.Eyes,   PngFile = "eyes_hearts.png",  Scale = 1.0f, Offset = new Vector2(0f, 0.10f) },
            new CosmeticDef { Sku = "face_mouth_stache", DisplayName = "Moustache",      Slot = CharacterItemType.Mouth,  PngFile = "mouth_stache.png", Scale = 0.9f, Offset = new Vector2(0f, -0.15f) },
            new CosmeticDef { Sku = "face_mouth_stitch", DisplayName = "Stitched Grin",  Slot = CharacterItemType.Mouth,  PngFile = "mouth_stitch.png", Scale = 0.8f, Offset = new Vector2(0f, -0.15f) },
            new CosmeticDef { Sku = "face_detail_crown", DisplayName = "Crown",          Slot = CharacterItemType.Detail, PngFile = "detail_crown.png", Scale = 1.6f, Offset = new Vector2(-0.028f, 4.499f) },
            new CosmeticDef { Sku = "face_detail_halo",  DisplayName = "Halo",           Slot = CharacterItemType.Detail, PngFile = "detail_halo.png",  Scale = 1.1f, Offset = new Vector2(0f, 0.75f) },
            // July 12 round 3: first community-artist cosmetics (lopidav / Nix).
            new CosmeticDef { Sku = "face_detail_sprout",   DisplayName = "Sprout",        Slot = CharacterItemType.Detail, PngFile = "detail_sprout.png",   Scale = 1.1f, Offset = new Vector2(0f, 0.55f) },
            new CosmeticDef { Sku = "face_detail_earmuffs", DisplayName = "Star Earmuffs", Slot = CharacterItemType.Detail, PngFile = "detail_earmuffs.png", Scale = 1.1f, Offset = new Vector2(0f, 0.20f) },
            // July 13 batch: house cosmetics round 2 (procedural art), including the
            // first two ANIMATED items (storm halo / flame crest — 4 frames @ 8fps,
            // exercising the __fN frame pipeline end to end).
            new CosmeticDef { Sku = "face_eyes_crazed",          DisplayName = "Crazed Eyes",    Slot = CharacterItemType.Eyes,   PngFile = "eyes_crazed.png",           Scale = 1.35f, Offset = new Vector2(0f, 0.10f) },
            new CosmeticDef { Sku = "face_eyes_yinyang",         DisplayName = "Yin & Yang",     Slot = CharacterItemType.Eyes,   PngFile = "eyes_yinyang.png",          Scale = 1.35f, Offset = new Vector2(0f, 0.10f) },
            new CosmeticDef { Sku = "face_detail_devil_horns",   DisplayName = "Devil Horns",    Slot = CharacterItemType.Detail, PngFile = "detail_devil_horns.png",    Scale = 1.1f, Offset = new Vector2(0f, 0.45f) },
            new CosmeticDef { Sku = "face_detail_alien_antennae",DisplayName = "Alien Antennae", Slot = CharacterItemType.Detail, PngFile = "detail_alien_antennae.png", Scale = 1.1f, Offset = new Vector2(0f, 0.55f) },
            new CosmeticDef { Sku = "face_detail_storm_halo",    DisplayName = "Storm Halo",     Slot = CharacterItemType.Detail, PngFile = "detail_storm_halo.png",     Scale = 1.2f, Offset = new Vector2(0f, 0.80f), Fps = 8f },
            new CosmeticDef { Sku = "face_detail_flame_crest",   DisplayName = "Flame Crest",    Slot = CharacterItemType.Detail, PngFile = "detail_flame_crest.png",    Scale = 1.1f, Offset = new Vector2(0f, 0.60f), Fps = 8f },
            // July 13 round 2: source art preprocessed for the pipeline (painted
            // checkerboard backdrop keyed out + enclosed holes punched); the
            // wings wrap the body, hence the oversized scale.
            new CosmeticDef { Sku = "face_detail_demon_wings",   DisplayName = "Demon Wings",    Slot = CharacterItemType.Detail, PngFile = "detail_demon_wings.png",    Scale = 2.1f, Offset = new Vector2(0f, 0.05f) },
            // July 13 round 2 (cont.): 7-item house batch, two more animated
            // (dark aura / energy orbs, 4 frames @ 7fps).
            new CosmeticDef { Sku = "face_detail_thorn_crown",   DisplayName = "Thorn Crown",      Slot = CharacterItemType.Detail, PngFile = "detail_thorn_crown.png",   Scale = 1.0f, Offset = new Vector2(0f, 0.00f) },
            new CosmeticDef { Sku = "face_detail_sun_halo",      DisplayName = "Sunburst Halo",    Slot = CharacterItemType.Detail, PngFile = "detail_sun_halo.png",      Scale = 1.1f, Offset = new Vector2(0f, 0.10f) },
            new CosmeticDef { Sku = "face_detail_knight_helm",   DisplayName = "Knight Great-Helm",Slot = CharacterItemType.Detail, PngFile = "detail_knight_helm.png",   Scale = 1.55f, Offset = new Vector2(0f, 0.05f) },
            new CosmeticDef { Sku = "face_detail_mini_flags",    DisplayName = "Rally Flags",      Slot = CharacterItemType.Detail, PngFile = "detail_mini_flags.png",    Scale = 1.0f, Offset = new Vector2(0f, 0.15f) },
            new CosmeticDef { Sku = "face_detail_dark_aura",     DisplayName = "Dark Aura",        Slot = CharacterItemType.Detail, PngFile = "detail_dark_aura.png",     Scale = 2.25f, Offset = new Vector2(0.032f, 1.17f), Fps = 7f },
            new CosmeticDef { Sku = "face_detail_energy_orbs",   DisplayName = "Energy Orbs",      Slot = CharacterItemType.Detail, PngFile = "detail_energy_orbs.png",   Scale = 1.0f, Offset = new Vector2(0f, 0.05f), Fps = 7f },
            // v1.35.3: placement revision 2 (artist-proposed, admin-approved) —
            // scale 1.70 -> 2.15, offset unchanged. Art is byte-identical
            // (md5 254dc7de...), so this is a pure placement republish; values
            // copied verbatim from approved_render_* (#165 — never the mutable
            // proposal columns), and migration 172 stamps published revision 2.
            new CosmeticDef { Sku = "face_detail_tattered_cape", DisplayName = "Tattered Cape",    Slot = CharacterItemType.Detail, PngFile = "detail_tattered_cape.png", Scale = 2.15f, Offset = new Vector2(0f, -0.10f) },
            // July 15: Nix's animated crown — 13 frames @ 3.6fps (twinkling lights +
            // pulsing star; ~3.6s loop — slowed from 9fps per Sid, a calmer flash).
            // Widest animated set so far; exercises the __fN loader past 4 frames.
            // Wide arch, so it sits high like the other crowns.
            new CosmeticDef { Sku = "face_detail_party_crown",   DisplayName = "Party Crown",      Slot = CharacterItemType.Detail, PngFile = "detail_party_crown.png",   Scale = 1.2f, Offset = new Vector2(0f, 0.55f), Fps = 3.6f },
            // July 17: Galaxyice's first two (new community artist). Both are
            // the artist's own 512px spec exports used VERBATIM — the canvas
            // composition IS the placement (cat drawn in the top half so it
            // rides above the head; the star's canvas position per frame is
            // the orbit animation, 6fps ~= 1s per lap) — so scale 1, no
            // offset. Players can still drag-adjust like any face item.
            new CosmeticDef { Sku = "face_detail_rounds_cat",    DisplayName = "Rounds Cat",       Slot = CharacterItemType.Detail, PngFile = "detail_rounds_cat.png",    Scale = 1.7f, Offset = Vector2.zero },  // placement revision 2 (v1.36.0): artist rescaled 1.0 -> 1.7; art unchanged
            new CosmeticDef { Sku = "face_detail_star_spin",     DisplayName = "Star Spin",        Slot = CharacterItemType.Detail, PngFile = "detail_star_spin.png",     Scale = 1.0f, Offset = Vector2.zero, Fps = 6f },
            // v1.34.3 — first community submission shipped through the artist
            // upload + admin placement review workflow. Scale/Offset are the
            // ADMIN-APPROVED values (approved_placement_revision 1), copied
            // verbatim from cosmetic_submissions so the render matches exactly
            // what was reviewed in-game (learning #164/#165).
            new CosmeticDef { Sku = "face_detail_spooky_head_bouncers", DisplayName = "Spooky Head-Bouncers", Slot = CharacterItemType.Detail, PngFile = "detail_spooky_head_bouncers.png", Scale = 1.3f, Offset = new Vector2(0.113f, 3.665f) },
            // v1.34.5 — two community submissions, same workflow. Scale/Offset
            // are the ADMIN-APPROVED values (approved_placement_revision 1),
            // copied verbatim from cosmetic_submissions.approved_render_* and
            // guarded by migration 153, which refuses to publish if the
            // artist revised the placement after this bundle was cut.
            // PNGs were pulled from png_data with md5 verification.
            new CosmeticDef { Sku = "face_detail_ballooniphones", DisplayName = "Ballooniphones", Slot = CharacterItemType.Detail, PngFile = "Ballooniphones.png", Scale = 1.7f, Offset = new Vector2(-0.192f, 2.112f) },
            new CosmeticDef { Sku = "face_detail_soda_helm",      DisplayName = "Soda Helm",      Slot = CharacterItemType.Detail, PngFile = "SodaHelm.png",      Scale = 1.3f, Offset = new Vector2(-0.096f, 2.4f) },
            // v1.35.5 batch. Scale/Offset copied verbatim from the APPROVED
            // snapshot columns (approved_render_*), never the artist's mutable
            // proposal — migration 175 aborts if the artist has revised the
            // placement since this bundle was cut. PNGs pulled from png_data
            // with md5 verified against the row before writing.
            new CosmeticDef { Sku = "face_detail_brain_cane",        DisplayName = "Brain Cane",        Slot = CharacterItemType.Detail, PngFile = "detail_brain_cane.png",        Scale = 1.3f, Offset = Vector2.zero },
            new CosmeticDef { Sku = "face_mouth_casi_s_mouth",       DisplayName = "Casi's mouth",      Slot = CharacterItemType.Mouth,  PngFile = "mouth_casi_s_mouth.png",       Scale = 1.3f, Offset = Vector2.zero },
            new CosmeticDef { Sku = "face_eyes_casicorn_s_eyes",     DisplayName = "Casicorn's Eyes",   Slot = CharacterItemType.Eyes,   PngFile = "eyes_casicorn_s_eyes.png",     Scale = 1.3f, Offset = Vector2.zero },
            new CosmeticDef { Sku = "face_detail_little_pink_buddy", DisplayName = "Little Pink Buddy", Slot = CharacterItemType.Detail, PngFile = "detail_little_pink_buddy.png", Scale = 1.3f, Offset = Vector2.zero },
            new CosmeticDef { Sku = "face_detail_sniper_medal",      DisplayName = "Sniper Medal",      Slot = CharacterItemType.Detail, PngFile = "detail_sniper_medal.png",      Scale = 1.3f, Offset = Vector2.zero },
            // v1.36.0 - approved placement revision 1, values copied verbatim
            // from cosmetic_submissions.approved_* so the render matches what
            // was reviewed in-game (learning #164/#165). 512x512, md5 verified
            // against the DB before writing the PNG.
            new CosmeticDef { Sku = "face_detail_spilled_icecream", DisplayName = "Spilled Icecream", Slot = CharacterItemType.Detail, PngFile = "detail_spilled_icecream.png", Scale = 1.3f, Offset = Vector2.zero },

            // Magical Hat (Nix) — approved placement revision 1, Scale/Offset
            // copied verbatim from cosmetic_submissions.approved_* (#164/#165).
            // ANIMATED: 10 frames, detail_magical_hat.png + __f2..__f10.
            //
            // Fps = 2.5 is not a taste choice, it is the SOURCE RATE. The
            // supplied GIF is 10 frames at 400 ms each = a 4.000 s loop, and the
            // request was for it to play "about the gif's speed". At the 7 fps
            // the extraction script suggests by default, those 10 frames finish
            // in 1.43 s — 2.8x too fast, which is the flashing that prompted
            // this. 10 frames / 2.5 fps = 4.000 s reproduces the source exactly.
            //
            // The frames were extracted with --no-trim on purpose. Measured
            // first: the approved static PNG fills 97.5% of its canvas centred
            // at (0.501, 0.469) and the GIF frames fill 97.1% centred at
            // (0.499, 0.470) — already the same framing, so the script's default
            // trim-and-repad would have RE-FRAMED the art and silently made the
            // approved scale of 1.3 render the wrong size. Verified after
            // extraction: every frame's alpha bbox equals its source frame's and
            // the alpha mismatch is 0 px on all ten.
            new CosmeticDef { Sku = "face_detail_magical_hat",      DisplayName = "Magical Hat",      Slot = CharacterItemType.Detail, PngFile = "detail_magical_hat.png",      Scale = 1.3f, Offset = Vector2.zero, Fps = 2.5f },
        };

        private static readonly Dictionary<int, CosmeticDef> byId = new Dictionary<int, CosmeticDef>();
        private static readonly Dictionary<string, CosmeticDef> byTemplateName = new Dictionary<string, CosmeticDef>();
        // Shop preview art (item 1): the runtime-loaded sprite per sku, so shop
        // rows can render the actual cosmetic instead of a text description.
        private static readonly Dictionary<string, Sprite> _spriteBySku =
            new Dictionary<string, Sprite>(StringComparer.OrdinalIgnoreCase);
        public static Sprite GetShopSprite(string sku)
        {
            if (string.IsNullOrEmpty(sku)) return null;
            Sprite s;
            return _spriteBySku.TryGetValue(sku, out s) ? s : null;
        }

        /// <summary>
        /// Returns the exact base PNG and published placement compiled into this
        /// client. Legacy artist-owned cosmetics predate cosmetic_submissions, so
        /// the Artist tab uses this as the source for their first placement
        /// revision. The server still verifies ownership and the PNG container;
        /// an admin must approve the proposed values before a later client ships
        /// them.
        /// </summary>
        public static bool TryGetPublishedPlacement(
            string sku, out string slot, out float scale, out Vector2 offset,
            out byte[] pngBytes)
        {
            slot = "";
            scale = 1f;
            offset = Vector2.zero;
            pngBytes = null;
            if (string.IsNullOrEmpty(sku)) return false;

            CosmeticDef match = null;
            for (int i = 0; i < Catalog.Length; i++)
            {
                if (string.Equals(Catalog[i].Sku, sku, StringComparison.OrdinalIgnoreCase))
                {
                    match = Catalog[i];
                    break;
                }
            }
            if (match == null) return false;

            slot = match.Slot == CharacterItemType.Eyes ? "eyes"
                 : match.Slot == CharacterItemType.Mouth ? "mouth"
                 : "detail";
            scale = match.Scale;
            offset = match.Offset;

            try
            {
                string dir = _cosmeticsDir;
                if (string.IsNullOrEmpty(dir))
                {
                    string dllDir = System.IO.Path.GetDirectoryName(
                        System.Reflection.Assembly.GetExecutingAssembly().Location);
                    dir = System.IO.Path.Combine(dllDir, "cosmetics");
                }
                string path = System.IO.Path.Combine(dir, match.PngFile);
                if (!System.IO.File.Exists(path)) return false;
                pngBytes = System.IO.File.ReadAllBytes(path);
                return pngBytes.Length > 0;
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning(
                    $"[COSMETIC] could not read published art for {sku}: {ex.Message}");
                pngBytes = null;
                return false;
            }
        }

        // Bug #74: animated items were static in the shop thumbnail. Frames +
        // fps per sku so NativeUI can cycle the uGUI Image sprite in its Tick.
        private static readonly Dictionary<string, (Sprite[] frames, float fps)> _shopFramesBySku =
            new Dictionary<string, (Sprite[], float)>(StringComparer.OrdinalIgnoreCase);
        public static Sprite[] GetShopFrames(string sku, out float fps)
        {
            fps = 0f;
            if (string.IsNullOrEmpty(sku)) return null;
            if (_shopFramesBySku.TryGetValue(sku, out var e)) { fps = e.fps; return e.frames; }
            return null;
        }
        private static bool initialized;

        /// <summary>Build sprites + hidden template GameObjects. Called from
        /// Plugin.DoInitialize (file IO off the startup hot path). Missing PNGs
        /// skip their item with a warning — the resolver then returns null for
        /// that ID, which renders as an empty slot (vanilla-identical fallback).</summary>
        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;
            try
            {
                string dllDir = System.IO.Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
                _cosmeticsDir = System.IO.Path.Combine(dllDir, "cosmetics");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[COSMETIC] plugin dir resolve failed: {ex.Message}");
                return;
            }
            int missing = BuildFromDisk();
#if !THUNDERSTORE
            // Bug #71 (lopidav): GitHub-release installs only ever receive the DLL —
            // the auto-updater copies one file — so the cosmetics/ folder never
            // arrives and EVERY item logs "missing art ... disabled this session"
            // (his log: "Initialized 0/8"). Items he BOUGHT could never appear in
            // the character editor. Same self-bootstrap as CardImageLoader: fetch
            // cosmetics.zip from the LATEST release (the zip is re-attached on
            // every /ship, so latest-zip always matches or supersedes the
            // auto-updated DLL's catalog; extra unknown art is harmless — the
            // catalog drives). Download happens on a worker thread; the template
            // REBUILD must run on the main thread (GameObject creation), so a
            // coroutine waits for the worker and re-runs BuildFromDisk.
            if (missing > 0 && Plugin.Instance != null)
            {
                Plugin.Log.LogInfo($"[COSMETIC] {missing} art file(s) missing — fetching cosmetics.zip from the latest release in background.");
                MaybeStartArtDownload();
                Plugin.Instance.StartCoroutine(RebuildAfterDownload());
            }
#else
            if (missing > 0)
                Plugin.Log.LogWarning($"[COSMETIC] {missing} art file(s) missing at {_cosmeticsDir} — reinstall via the mod manager (Thunderstore bundles ship the art).");
#endif
        }

        private static string _cosmeticsDir = "";

        /// <summary>Build sprites + templates for every catalog def whose art is on
        /// disk and which hasn't been built yet. Re-runnable (the #71 bootstrap
        /// calls it again after the art download); already-built defs are skipped,
        /// so IDs and existing template references stay stable. Returns how many
        /// defs are still missing their art.</summary>
        private static int BuildFromDisk()
        {
            int built = 0, missing = 0;
            string dir = _cosmeticsDir;

            for (int i = 0; i < Catalog.Length; i++)
            {
                var def = Catalog[i];
                def.Id = CUSTOM_ID_BASE + i;
                if (def.Template != null) continue;  // built on a previous pass
                try
                {
                    string path = System.IO.Path.Combine(dir, def.PngFile);
                    if (!System.IO.File.Exists(path))
                    {
                        missing++;
                        Plugin.Log.LogWarning($"[COSMETIC] missing art {def.PngFile} — '{def.DisplayName}' disabled this session");
                        continue;
                    }
                    var sprite = LoadCosmeticSprite(path);
                    if (sprite == null)
                    {
                        Plugin.Log.LogWarning($"[COSMETIC] LoadImage failed for {def.PngFile}");
                        continue;
                    }

                    // Animated variant (item 7): collect <base>__f2.png, __f3.png, ...
                    // The base file is frame 1.
                    var frames = new List<Sprite> { sprite };
                    string baseName = System.IO.Path.GetFileNameWithoutExtension(def.PngFile);
                    for (int f = 2; ; f++)
                    {
                        string fp = System.IO.Path.Combine(dir, $"{baseName}__f{f}.png");
                        if (!System.IO.File.Exists(fp)) break;
                        var fs = LoadCosmeticSprite(fp);
                        if (fs == null) break;
                        frames.Add(fs);
                    }

                    var go = new GameObject(TEMPLATE_PREFIX + def.Sku, typeof(SpriteRenderer), typeof(CharacterItem));
                    var sr = go.GetComponent<SpriteRenderer>();
                    sr.sprite = sprite;
                    // Item 1 (July 17 round 2): a runtime SpriteRenderer defaults to
                    // unlit Sprites/Default, but the whole ROUNDS scene — vanilla
                    // face items included — renders through the SFSS-lit shader and
                    // is multiplied DOWN by the scene lightmap (< 1 nearly
                    // everywhere). Unlit, our art rendered at raw PNG brightness
                    // against a darkened scene ("cat too bright, green eyes gone").
                    // Adopt the vanilla item material so we shade with the body.
                    // May still be null this early — EnsureVanillaItemMaterial()
                    // backfills all templates once the loader exists.
                    if (_vanillaItemMat != null) sr.sharedMaterial = _vanillaItemMat;
                    if (frames.Count >= 2)
                    {
                        var cyc = go.AddComponent<CosmeticFrameCycler>();
                        cyc.frames = frames.ToArray();
                        cyc.fps = def.Fps;
                        _shopFramesBySku[def.Sku] = (frames.ToArray(), def.Fps);
                        Plugin.Log.LogInfo($"[COSMETIC] '{def.DisplayName}' animated: {frames.Count} frames @ {def.Fps:F0}fps");
                    }
                    // Rendering constants per the reference implementation: the player
                    // rig draws on layer "Player"; face items sort on "MostFront" with
                    // eyes=3, mouth=4, detail=5 so details overlay mouths overlay eyes.
                    go.layer = LayerMask.NameToLayer("Player");
                    sr.sortingLayerID = SortingLayer.NameToID("MostFront");
                    sr.sortingOrder = def.Slot == CharacterItemType.Eyes ? 3
                                    : def.Slot == CharacterItemType.Mouth ? 4 : 5;
                    var item = go.GetComponent<CharacterItem>();
                    item.sprite = sprite;
                    item.itemType = def.Slot;
                    item.scale = def.Scale;
                    item.offset = def.Offset;
                    // Hide the template without SetActive(false): every consumer
                    // (button spawner, equipper SpawnItem) explicitly re-sets
                    // localPosition and localScale on clones, so parking the
                    // original far away at scale 0 is invisible AND clone-safe.
                    // HideAndDontSave (not DontDestroyOnLoad!) — ROUNDS destroys
                    // unknown DDOL objects on scene transitions (learning #16);
                    // HideAndDontSave objects live outside scene management
                    // entirely, the same pattern as the mod's persistent watcher.
                    // Instantiate() resets hideFlags on clones, so spawned copies
                    // behave as normal scene objects.
                    go.hideFlags = HideFlags.HideAndDontSave;
                    go.transform.position = new Vector3(0f, 100000f, 0f);
                    go.transform.localScale = Vector3.zero;

                    def.Template = item;
                    byId[def.Id] = def;
                    byTemplateName[go.name] = def;
                    _spriteBySku[def.Sku] = sprite;
                    built++;
                }
                catch (Exception ex)
                {
                    Plugin.Log.LogWarning($"[COSMETIC] build failed for {def.Sku}: {ex.Message}");
                }
            }
            Plugin.Log.LogInfo($"[COSMETIC] Initialized {built}/{Catalog.Length} custom cosmetics this pass (id base {CUSTOM_ID_BASE}, {missing} missing art)");
            return missing;
        }

#if !THUNDERSTORE
        // ── Bug #71: cosmetics art self-bootstrap (mirrors CardImageLoader) ──
        private const string COSMETICS_ZIP_URL =
            "https://github.com/SidNDeed/SidsCompetitiveRounds/releases/latest/download/cosmetics.zip";
        private static int _artDownloadStarted;   // 0 = not started; 1 = in flight/done
        private static volatile bool _artDownloadDone;
        private static volatile bool _artDownloadOk;

        private static void MaybeStartArtDownload()
        {
            if (System.Threading.Interlocked.Exchange(ref _artDownloadStarted, 1) != 0) return;
            var t = new System.Threading.Thread(ArtDownloadWorker) { IsBackground = true, Name = "CR_CosmeticArtDownload" };
            t.Start();
        }

        private static void ArtDownloadWorker()
        {
            string tmpZip = null;
            try
            {
                System.IO.Directory.CreateDirectory(_cosmeticsDir);
                tmpZip = System.IO.Path.Combine(System.IO.Path.GetDirectoryName(_cosmeticsDir), "cosmetics-download.zip");
                Plugin.Log?.LogInfo($"[COSMETIC] downloading {COSMETICS_ZIP_URL} → {tmpZip}");
                try { System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12; } catch { }
                using (var wc = new System.Net.WebClient())
                {
                    wc.Headers.Add("User-Agent", "CompetitiveRounds-Mod/" + Plugin.ModVersion);
                    wc.DownloadFile(COSMETICS_ZIP_URL, tmpZip);
                }
                int extracted = 0;
                using (var fs = System.IO.File.OpenRead(tmpZip))
                using (var zip = new System.IO.Compression.ZipArchive(fs, System.IO.Compression.ZipArchiveMode.Read))
                {
                    foreach (var entry in zip.Entries)
                    {
                        if (string.IsNullOrEmpty(entry.Name)) continue;
                        if (!entry.Name.ToLowerInvariant().EndsWith(".png")) continue;
                        string outPath = System.IO.Path.Combine(_cosmeticsDir, entry.Name);
                        try
                        {
                            using (var es = entry.Open())
                            using (var os = System.IO.File.Create(outPath))
                                es.CopyTo(os);
                            extracted++;
                        }
                        catch (Exception exEntry)
                        {
                            Plugin.Log?.LogWarning($"[COSMETIC] extract failed for {entry.Name}: {exEntry.Message}");
                        }
                    }
                }
                Plugin.Log?.LogInfo($"[COSMETIC] art bootstrap extracted {extracted} file(s)");
                _artDownloadOk = extracted > 0;
            }
            catch (Exception ex)
            {
                Plugin.Log?.LogWarning($"[COSMETIC] art bootstrap failed: {ex.Message} — items without art stay disabled this session");
            }
            finally
            {
                try { if (tmpZip != null && System.IO.File.Exists(tmpZip)) System.IO.File.Delete(tmpZip); } catch { }
                _artDownloadDone = true;
            }
        }

        private static System.Collections.IEnumerator RebuildAfterDownload()
        {
            while (!_artDownloadDone) yield return new WaitForSeconds(1f);
            if (!_artDownloadOk) yield break;
            int stillMissing = BuildFromDisk();   // main thread — safe to create templates
            Plugin.Log.LogInfo($"[COSMETIC] post-bootstrap rebuild complete ({stillMissing} still missing)");
            try { NativeUI.MarkDirty(); } catch { }
        }
#endif

        private static Sprite LoadCosmeticSprite(string path)
        {
            try
            {
                var bytes = System.IO.File.ReadAllBytes(path);
                var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
                if (!tex.LoadImage(bytes)) return null;
                tex.hideFlags = HideFlags.HideAndDontSave;
                // PPU 100 (Unity default) — the FacesPlus-proven combo with 512px art.
                var sprite = Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f));
                sprite.hideFlags = HideFlags.HideAndDontSave;
                return sprite;
            }
            catch { return null; }
        }

        // Item 1: the SFSS-lit material borrowed from a vanilla face item, so
        // custom cosmetics get the exact lightmap multiply vanilla items get
        // (SpawnItem clones never copy material, so fixing the template fixes
        // every consumer — in-match body, pick visualizer, menu portraits).
        private static Material _vanillaItemMat;

        internal static void EnsureVanillaItemMaterial()
        {
            if (_vanillaItemMat != null) return;
            try
            {
                var loader = CharacterCreatorItemLoader.instance;
                if (loader == null || loader.eyes == null || loader.eyes.Length == 0) return;
                var vsr = loader.eyes[0].GetComponent<SpriteRenderer>();
                if (vsr == null || vsr.sharedMaterial == null) return;
                _vanillaItemMat = vsr.sharedMaterial;
                // Learning #91 discipline: prove the borrowed asset is what we
                // think — this should log shader=Sprites/SFSoftShadow.
                Plugin.Log.LogInfo($"[COSMETIC] adopting vanilla item material, shader={_vanillaItemMat.shader?.name}");
                foreach (var def in Catalog)
                {
                    var tsr = def.Template != null ? def.Template.GetComponent<SpriteRenderer>() : null;
                    if (tsr != null) tsr.sharedMaterial = _vanillaItemMat;
                }
            }
            catch (Exception ex) { Plugin.Log.LogWarning($"[COSMETIC] material adopt failed: {ex.Message}"); }
        }

        /// <summary>Resolver for custom IDs. Null for unknown IDs — same contract
        /// as vanilla's out-of-range fallback (slot renders empty).</summary>
        public static CharacterItem GetItem(int itemID, CharacterItemType itemType)
        {
            // Loader.instance is guaranteed alive here (we're called from its
            // own GetItem via the Harmony prefix) — safe point to adopt the
            // vanilla material for every template.
            EnsureVanillaItemMaterial();
            if (byId.TryGetValue(itemID, out var def) && def.Slot == itemType && def.Template != null)
                return def.Template;
            return null;
        }

        /// <summary>Reverse lookup by template/clone. Unity clones append
        /// "(Clone)" (possibly repeatedly for clones-of-clones) — strip all.</summary>
        public static bool TryGetId(CharacterItem item, out int id)
        {
            id = -1;
            if (item == null) return false;
            string n = item.gameObject.name;
            if (!n.StartsWith(TEMPLATE_PREFIX, StringComparison.Ordinal)) return false;
            while (n.EndsWith("(Clone)", StringComparison.Ordinal))
                n = n.Substring(0, n.Length - 7).TrimEnd();
            if (byTemplateName.TryGetValue(n, out var def)) { id = def.Id; return true; }
            return false;
        }

        /// <summary>Owned custom items for a slot, from the cached shop payload
        /// (server annotates 'owned'; the mod owner auto-owns everything). Cache
        /// empty → none listed (the resolver still works for remote faces).</summary>
        public static List<CosmeticDef> OwnedItemsFor(CharacterItemType slot)
        {
            var result = new List<CosmeticDef>();
            var shop = ApiClient.CachedShopItems;
            if (shop == null)
            {
                // Warm the cache so the NEXT menu open lists items (creator is
                // reachable without ever opening our F5 page).
                try
                {
                    var sid = MatchTracker.LocalSteamId;
                    if (!string.IsNullOrEmpty(sid) && sid != "unknown") ApiClient.FetchShopItems(sid);
                }
                catch { }
                return result;
            }
            var owned = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var it in shop)
                if (it != null && it.owned && it.kind == "face" && !string.IsNullOrEmpty(it.sku))
                    owned.Add(it.sku);
            foreach (var def in Catalog)
                if (def.Template != null && def.Slot == slot && owned.Contains(def.Sku))
                    result.Add(def);
            return result;
        }

        internal static int CurrentFaceIdFor(CharacterCreator creator, CharacterItemType slot, int slotNr)
        {
            if (creator == null || creator.currentPlayerFace == null) return -1;
            var f = creator.currentPlayerFace;
            if (slot == CharacterItemType.Eyes) return f.eyeID;
            if (slot == CharacterItemType.Mouth) return f.mouthID;
            return slotNr == 0 ? f.detailID : f.detail2ID;
        }
    }

    // ── Resolution patches — the entire network/render integration ────────────

    [HarmonyPatch(typeof(CharacterCreatorItemLoader), "GetItem")]
    internal static class CosmeticGetItemPatch
    {
        static bool Prefix(int itemID, CharacterItemType itemType, ref CharacterItem __result)
        {
            if (itemID < CustomCosmetics.CUSTOM_ID_BASE) return true; // vanilla path
            __result = CustomCosmetics.GetItem(itemID, itemType);
            return false;
        }
    }

    [HarmonyPatch(typeof(CharacterCreatorItemLoader), "GetItemID")]
    internal static class CosmeticGetItemIdPatch
    {
        static bool Prefix(CharacterItem newSprite, ref int __result)
        {
            if (CustomCosmetics.TryGetId(newSprite, out int id))
            {
                __result = id;
                return false;
            }
            return true; // vanilla path (sprite-reference compare)
        }
    }

    // ── Character-editor listing — owned items appear after the vanilla grid ──

    [HarmonyPatch(typeof(CharacterCreatorButtonSpawner), "OpenMenu", typeof(CharacterItemType), typeof(int))]
    internal static class CosmeticButtonSpawnerPatch
    {
        static void Postfix(CharacterCreatorButtonSpawner __instance, CharacterItemType target, int slotNr)
        {
            try
            {
                // Character editor is open -> the item loader exists; adopt the
                // vanilla SFSS-lit material for our templates (item 1).
                CustomCosmetics.EnsureVanillaItemMaterial();
                var owned = CustomCosmetics.OwnedItemsFor(target);
                if (owned.Count == 0) return;
                var creator = __instance.GetComponent<CharacterCreator>();
                var sourceButton = __instance.sourceButton;
                if (sourceButton == null) return;
                int currentId = CustomCosmetics.CurrentFaceIdFor(creator, target, slotNr);

                foreach (var def in owned)
                {
                    // Mirror vanilla's own button flow (decompile: OpenMenu) so
                    // CharacterItemButton.Click → Equip → GetItemID runs unchanged.
                    GameObject btn = UnityEngine.Object.Instantiate(sourceButton, sourceButton.transform.parent);
                    btn.SetActive(true);
                    Transform itemParent = btn.transform.Find("ItemParent");
                    GameObject vis = UnityEngine.Object.Instantiate(def.Template.gameObject, itemParent);
                    btn.GetComponent<CharacterItemButton>().itemType = target;
                    btn.GetComponent<CharacterItemButton>().slotNr = slotNr;
                    var btnItem = btn.GetComponentInChildren<CharacterItem>();
                    if (btnItem != null) btnItem.sprite = def.Template.sprite;
                    var visItem = vis.GetComponentInChildren<CharacterItem>();
                    var visSr = vis.GetComponentInChildren<SpriteRenderer>();
                    if (visItem != null)
                    {
                        visItem.GetComponent<SpriteRenderer>().sortingOrder = def.Template.GetComponent<SpriteRenderer>().sortingOrder;
                        visItem.scale = def.Scale;
                        visItem.itemType = target;
                        visItem.offset = def.Offset;
                        visItem.slotNr = slotNr;
                    }
                    if (visSr != null)
                    {
                        // The hidden template is parked at scale 0 / y=100000 —
                        // restore real transform values on the button thumbnail
                        // (vanilla sets these same two fields for its items).
                        visSr.transform.localPosition = def.Offset;
                        visSr.transform.localScale = def.Scale * Vector2.one;
                    }
                    if (currentId == def.Id)
                    {
                        var dot = btn.transform.Find("SelectedDot");
                        if (dot != null) dot.gameObject.SetActive(true);
                    }
                }
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[COSMETIC] OpenMenu inject failed: {ex.Message}");
            }
        }
    }

    // Vanilla SelectButton (runs on every click) matches selected-dots by
    // child-index == face ID, which can never match our IDs (>=1000) — so it
    // correctly clears every dot but can't set ours. Re-apply it here.
    [HarmonyPatch(typeof(CharacterCreatorButtonSpawner), "SelectButton")]
    internal static class CosmeticSelectButtonPatch
    {
        static void Postfix(CharacterCreatorButtonSpawner __instance, CharacterItemType itemType, int slotNr)
        {
            try
            {
                var creator = __instance.GetComponent<CharacterCreator>();
                int currentId = CustomCosmetics.CurrentFaceIdFor(creator, itemType, slotNr);
                if (currentId < CustomCosmetics.CUSTOM_ID_BASE) return;
                var src = __instance.sourceButton;
                if (src == null) return;
                foreach (Transform child in src.transform.parent)
                {
                    if (!child.gameObject.activeSelf) continue;
                    var item = child.GetComponentInChildren<CharacterItem>();
                    if (item == null) continue;
                    if (CustomCosmetics.TryGetId(item, out int id) && id == currentId)
                    {
                        var dot = child.Find("SelectedDot");
                        if (dot != null) dot.gameObject.SetActive(true);
                    }
                }
            }
            catch { }
        }
    }
}
