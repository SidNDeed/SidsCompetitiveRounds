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
            private void Awake() { sr = GetComponent<SpriteRenderer>(); }
            private void Update()
            {
                if (frames == null || frames.Length < 2 || sr == null || fps <= 0f) return;
                sr.sprite = frames[(int)(Time.unscaledTime * fps) % frames.Length];
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
            new CosmeticDef { Sku = "face_detail_crown", DisplayName = "Crown",          Slot = CharacterItemType.Detail, PngFile = "detail_crown.png", Scale = 1.1f, Offset = new Vector2(0f, 0.55f) },
            new CosmeticDef { Sku = "face_detail_halo",  DisplayName = "Halo",           Slot = CharacterItemType.Detail, PngFile = "detail_halo.png",  Scale = 1.1f, Offset = new Vector2(0f, 0.75f) },
            // July 12 round 3: first community-artist cosmetics (lopidav / Nix).
            new CosmeticDef { Sku = "face_detail_sprout",   DisplayName = "Sprout",        Slot = CharacterItemType.Detail, PngFile = "detail_sprout.png",   Scale = 1.1f, Offset = new Vector2(0f, 0.55f) },
            new CosmeticDef { Sku = "face_detail_earmuffs", DisplayName = "Star Earmuffs", Slot = CharacterItemType.Detail, PngFile = "detail_earmuffs.png", Scale = 1.1f, Offset = new Vector2(0f, 0.20f) },
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
        private static bool initialized;

        /// <summary>Build sprites + hidden template GameObjects. Called from
        /// Plugin.DoInitialize (file IO off the startup hot path). Missing PNGs
        /// skip their item with a warning — the resolver then returns null for
        /// that ID, which renders as an empty slot (vanilla-identical fallback).</summary>
        public static void Initialize()
        {
            if (initialized) return;
            initialized = true;
            int built = 0;
            string dir = "";
            try
            {
                string dllDir = System.IO.Path.GetDirectoryName(System.Reflection.Assembly.GetExecutingAssembly().Location);
                dir = System.IO.Path.Combine(dllDir, "cosmetics");
            }
            catch (Exception ex)
            {
                Plugin.Log.LogWarning($"[COSMETIC] plugin dir resolve failed: {ex.Message}");
                return;
            }

            for (int i = 0; i < Catalog.Length; i++)
            {
                var def = Catalog[i];
                def.Id = CUSTOM_ID_BASE + i;
                try
                {
                    string path = System.IO.Path.Combine(dir, def.PngFile);
                    if (!System.IO.File.Exists(path))
                    {
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
                    if (frames.Count >= 2)
                    {
                        var cyc = go.AddComponent<CosmeticFrameCycler>();
                        cyc.frames = frames.ToArray();
                        cyc.fps = def.Fps;
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
            Plugin.Log.LogInfo($"[COSMETIC] Initialized {built}/{Catalog.Length} custom cosmetics (id base {CUSTOM_ID_BASE})");
        }

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

        /// <summary>Resolver for custom IDs. Null for unknown IDs — same contract
        /// as vanilla's out-of-range fallback (slot renders empty).</summary>
        public static CharacterItem GetItem(int itemID, CharacterItemType itemType)
        {
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
