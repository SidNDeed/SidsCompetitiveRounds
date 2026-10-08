using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using Photon.Pun;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Item 19 (v1.41.0): two saved default avatars, a modded one and
    /// a vanilla one, chosen by the kind of room. The Unity half: it reads the
    /// game into plain values, asks AvatarRules (AvatarDefaultRules.cs) what to
    /// do, and applies the answer through vanilla's own selection API.
    ///
    /// Design: ai-collab/v1410/ITEM19-DUAL-AVATAR-DESIGN.md revision 3,
    /// "derive, do not latch". The only persisted state is the config int
    /// UI/AvatarHomeSlot (the pre-switch own selection). The only fields here
    /// are the four cached ring sprites and their ensure-once flag.
    ///
    /// Edges that call <see cref="Evaluate"/>: E1 the LoadFaces postfix, E2-E4,
    /// E6, E7, E11, E12 the Photon callbacks in Plugin.cs, E5 the CreatePlayer
    /// prefix, E8 the three settings rows, E9 the SelectFace postfix. E10 (the
    /// swap key) is item 17's Keybinds registry, absent on this lane, so there
    /// is no swap reader and no fallback binding (design 2.5, sentence 3).</summary>
    internal static class AvatarDefaults
    {
        // The four ring sprites and their ensure-once flag (design 2.6) - the
        // only statics this feature adds.
        private static Sprite ringGold, ringBlue, ringBoth, ringRed;
        private static bool ringsBuilt;

        private const string RingName = "CR_AvatarRing";
        private const string LegendName = "CR_AvatarLegend";

        // ---------------------------------------------------------------
        // Reading the game
        // ---------------------------------------------------------------

        private static AvatarLivenessIn ReadLiveness()
        {
            var l = new AvatarLivenessIn();
            try
            {
                var gm = GameManager.instance;
                l.ManagerExists = gm != null;
                if (gm != null) { l.IsPlaying = gm.isPlaying; l.BattleOngoing = gm.battleOngoing; }
                else l.LocalBodyExists = LocalBody() != null;
            }
            catch { l.Unreadable = true; }
            return l;
        }

        /// <summary>The room term. InRoom and OfflineMode are read FIRST and on
        /// their own (fix pass 1, BR-M4): when that read throws, InRoom stays
        /// false and Unreadable is set, so the census cannot answer Vanilla
        /// for a room that was never established (and does not treat the
        /// failure as a confirmed exit either). Only a failure after a real
        /// online room is known reads as an unreadable room.</summary>
        private static AvatarFacingIn ReadFacing()
        {
            var f = new AvatarFacingIn { FaceKey = FacePublisher.PROP_FACE };
            try
            {
                bool inRoom = PhotonNetwork.InRoom;
                bool offline = PhotonNetwork.OfflineMode;
                f.InRoom = inRoom;
                f.OfflineMode = offline;
            }
            catch { f.InRoom = false; f.OfflineMode = false; f.Unreadable = true; return f; }
            if (!f.InRoom || f.OfflineMode) return f;
            try
            {
                f.LocalIsSpectator = RoomActors.LocalIsSpectator;
                var room = PhotonNetwork.CurrentRoom;
                f.RoomExists = room != null;
                if (room == null) return f;
                f.ModIssuedRoom = CompetitiveRoomDetect.IsModIssuedRoom(room.Name, room.CustomProperties);
                var others = new List<IList<string>>();
                foreach (var p in RoomActors.ActiveFighters())
                {
                    if (p == null || p.IsLocal) continue;
                    var props = p.CustomProperties;
                    if (props == null) { others.Add(null); continue; }
                    var keys = new List<string>();
                    foreach (var k in props.Keys) keys.Add(k as string);
                    others.Add(keys);
                }
                f.OtherFighterKeys = others;
            }
            catch { f.Unreadable = true; }
            return f;
        }

        private static AvatarFaceIds[] ReadFaces(CharacterCreatorHandler cch)
        {
            var src = cch?.playerFaces;
            if (src == null) return null;
            var a = new AvatarFaceIds[src.Length];
            for (int i = 0; i < src.Length; i++)
            {
                var fc = src[i];
                if (fc != null) a[i] = AvatarFaceIds.Of(fc.eyeID, fc.mouthID, fc.detailID, fc.detail2ID);
            }
            return a;
        }

        private static bool[] NonNull(CharacterItem[] arr)
        {
            if (arr == null) return null;
            var b = new bool[arr.Length];
            for (int i = 0; i < arr.Length; i++) b[i] = arr[i] != null;
            return b;
        }

        /// <summary>The BASE loader's arrays. The mod never replaces them (its
        /// ids >= 1000 resolve in a GetItem prefix), so these are exactly what a
        /// seat without the mod holds.</summary>
        private static AvatarLoaderView ReadLoader()
        {
            try
            {
                var L = CharacterCreatorItemLoader.instance;
                if (L == null) return null;
                return new AvatarLoaderView { Eyes = NonNull(L.eyes), Mouths = NonNull(L.mouths), Accessories = NonNull(L.accessories) };
            }
            catch { return null; }
        }

        internal static AvatarSetting ReadSetting()
        {
            return new AvatarSetting
            {
                Auto = Plugin.AvatarAutoSwitch != null && Plugin.AvatarAutoSwitch.Value,
                Modded = Plugin.AvatarModdedPreset != null ? Plugin.AvatarModdedPreset.Value : -1,
                Vanilla = Plugin.AvatarVanillaPreset != null ? Plugin.AvatarVanillaPreset.Value : -1,
            };
        }

        private static int ReadHome() => Plugin.AvatarHomeSlot != null ? Plugin.AvatarHomeSlot.Value : -1;

        /// <summary>This seat's own spawned body, by IsMine view - the same
        /// resolution FaceResync.TrySendLocalFace uses.</summary>
        private static global::Player LocalBody()
        {
            var players = PlayerManager.instance?.players;
            if (players == null) return null;
            foreach (var pl in players)
                if (pl != null && pl.gameObject != null && pl.data != null && pl.data.view != null && pl.data.view.IsMine)
                    return pl;
            return null;
        }

        private static int OtherFighterCount(AvatarFacingIn f) => f.OtherFighterKeys != null ? f.OtherFighterKeys.Count : 0;

        // ---------------------------------------------------------------
        // The evaluator
        // ---------------------------------------------------------------

        /// <summary>Recompute f from its three inputs and apply the answer.
        /// Main thread only (every caller is a Unity or Photon callback). The
        /// gate is read FIRST: during a live game nothing is read, written,
        /// published or announced, and Home is left exactly as it is.</summary>
        internal static void Evaluate(string tag)
        {
            try
            {
                var rules = new AvatarRules();
                var l = ReadLiveness();
                var f = ReadFacing();
                if (rules.Gate(rules.Census(l, f))) return;              // THE GATE (DEVIATION 3)

                var cch = CharacterCreatorHandler.instance;
                if (cch == null || cch.selectedFaceID == null || cch.selectedFaceID.Length == 0 || cch.playerFaces == null) return;

                var x = new AvatarEvalIn
                {
                    Liveness = l, Facing = f, Setting = ReadSetting(),
                    Faces = ReadFaces(cch), Loader = ReadLoader(),
                    Live = cch.selectedFaceID[0], Home = ReadHome(),
                };
                var d = rules.Evaluate(x);
                if (d.Gated || d.NothingToRead) return;

                if (d.Unusable != AvatarUnusable.None) Announce(UnusableMessage(d.Unusable));

                // Home is written BEFORE the apply: the apply re-enters this
                // method through the SelectFace postfix (E9), and the re-entrant
                // evaluation must see the remembered value already in place so
                // it finds want == live and returns.
                if (d.HomeChanged && Plugin.AvatarHomeSlot != null) Plugin.AvatarHomeSlot.Value = d.NewHome;
                if (d.Apply >= 0) Apply(d.Apply, tag);

                // The durable capture (S22, fix pass 1 M8): every applied change,
                // and every classification on a room edge even when nothing moves,
                // logs one line naming the facing, the nominee and the other-
                // fighter count.
                if (d.Apply >= 0 || rules.LogsClassification(tag))
                    Plugin.Log.LogInfo(rules.ClassificationLine(tag, d, OtherFighterCount(f), f.ModIssuedRoom, x.Live, x.Home));
                if (d.Apply < 0) return;
                if (d.Switched != AvatarSwitched.None) Announce(SwitchedMessage(d.Switched));
            }
            catch (Exception ex) { Warn("[AVATAR] " + tag + " evaluation failed: " + ex.Message); }
        }

        /// <summary>A warning that cannot itself throw out of a Harmony body or
        /// the evaluator's catch (fix pass 1, BR-M1).</summary>
        internal static void Warn(string msg)
        {
            try { Plugin.Log?.LogWarning(msg); } catch { }
        }

        private static string SwitchedMessage(AvatarSwitched s)
        {
            return s == AvatarSwitched.ToVanilla
                ? I18n.Tr("Switched to your vanilla avatar for this room.")
                : I18n.Tr("Switched back to your modded avatar.");
        }

        private static string UnusableMessage(AvatarUnusable u)
        {
            string first = u == AvatarUnusable.NotClean
                ? I18n.Tr("Your vanilla avatar preset has items an unmodded player cannot see, so your avatar was not switched.")
                : I18n.Tr("That preset has never been customised, so your avatar was not switched.");
            return first + "\n" + RecoveryInstruction();
        }

        internal static string RecoveryInstruction()
        {
            return I18n.Tr("To make a preset an unmodded opponent can see: open the character menu, choose an empty preset, and build the face from base-game eyes, mouths and details only.");
        }

        /// <summary>The one announcer: raises a toast unless the surface is
        /// already showing exactly this text. Remembers nothing.</summary>
        private static void Announce(string msg)
        {
            bool showing = CompetitiveUI.IsShowing(msg);
            if (!new AvatarRules().ShouldRaise(msg, showing ? msg : "", showing ? 1f : 0f)) return;
            CompetitiveUI.ShowNotification(msg, new Color(0.5f, 0.83f, 1f), 5f);
        }

        // ---------------------------------------------------------------
        // The apply
        // ---------------------------------------------------------------

        /// <summary>The menu's own portrait grid: scene objects, playerId == -1
        /// (the main-menu grid; the local-multiplayer grids carry 0..3 and
        /// ClickButton passes that id to SelectFace), bucketed by parent, the
        /// biggest bucket. The apply and the ring painter both use it.</summary>
        internal static List<CharacterCreatorPortrait> MenuPortraits()
        {
            var empty = new List<CharacterCreatorPortrait>();
            try
            {
                var all = Resources.FindObjectsOfTypeAll<CharacterCreatorPortrait>();
                if (all == null || all.Length == 0) return empty;
                var best = all
                    .Where(x => x != null && x.gameObject != null && x.gameObject.scene.IsValid() && x.transform.parent != null)
                    .Where(x => x.playerId == -1)
                    .GroupBy(x => x.transform.parent)
                    .OrderByDescending(g => g.Count())
                    .FirstOrDefault();
                return best != null ? best.ToList() : empty;
            }
            catch { return empty; }
        }

        /// <summary>Select slot through vanilla's own API. Through the live
        /// menu portrait when exactly one carries the slot (so vanilla's Frame
        /// marker moves with it), else SelectFace(0, ...) directly, whose player
        /// index is a literal. Then publish the face carrier, and equip this
        /// seat's own body and re-send the face to the others when a body
        /// exists.</summary>
        private static void Apply(int slot, string tag)
        {
            var cch = CharacterCreatorHandler.instance;
            var face = cch.playerFaces[slot];
            CharacterCreatorPortrait hit = null;
            int hits = 0;
            foreach (var p in MenuPortraits())
                if (p.transform.GetSiblingIndex() == slot) { hit = p; hits++; }
            if (hits == 1 && hit.myFace != null) hit.ClickButton();
            else cch.SelectFace(0, face, slot);
            FacePublisher.PublishLocal();                                  // the one carrier (cr_face)

            var lp = LocalBody();
            if (lp == null) return;
            FaceResync.TrySendLocalFace("AVATAR");                       // the others (RpcTarget.Others)
            var eq = lp.GetComponentInChildren<CharacterCreatorItemEquipper>();
            if (eq != null) eq.EquipFace(face);                           // this seat's own body
        }

        // ---------------------------------------------------------------
        // Player Cards: the one Follow helper
        // ---------------------------------------------------------------

        /// <summary>The face a Player Card in Follow mode shows: the face this
        /// room displaced (Home) while a forced switch is in effect, else the
        /// live selection. Joining a room never changes the card picture.</summary>
        internal static PlayerFace FaceForFollow()
        {
            var cch = CharacterCreatorHandler.instance;
            if (cch == null || cch.playerFaces == null || cch.selectedPlayerFaces == null || cch.selectedPlayerFaces.Length == 0) return null;
            int home = ReadHome();
            if (home >= 0 && home < cch.playerFaces.Length) return cch.playerFaces[home];
            return cch.selectedPlayerFaces[0];
        }

        // ---------------------------------------------------------------
        // Settings support
        // ---------------------------------------------------------------

        /// <summary>A slot index as the dropdowns show it: -1 is "Not set",
        /// players count presets from one.</summary>
        internal static string PresetLabel(int v)
        {
            return v < 0 ? I18n.Tr("Not set") : I18n.TrF("Preset {0}", v + 1);
        }

        /// <summary>Is this slot usable as the vanilla default right now (the
        /// same derivation f uses).</summary>
        internal static bool VanillaUsable(int slot)
        {
            var cch = CharacterCreatorHandler.instance;
            if (cch == null) return false;
            return new AvatarRules().Usable(slot, AvatarFacing.Vanilla, ReadFaces(cch), ReadLoader());
        }

        internal static string[] ModdedOptionIds()
        {
            int slots = PortraitRender.PresetSlotCount();
            var ids = new string[slots + 1];
            for (int i = -1; i < slots; i++) ids[i + 1] = i.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return ids;
        }

        internal static string[] ModdedOptionNames()
        {
            var ids = ModdedOptionIds();
            var n = new string[ids.Length];
            for (int i = 0; i < ids.Length; i++) n[i] = PresetLabel(ParseSlot(ids[i]));
            return n;
        }

        /// <summary>Vanilla options: Not set, every slot (a slot that is not
        /// vanilla-clean is listed with the reason and refused on pick), or the
        /// empty-state line when no slot is clean yet.</summary>
        internal static string[] VanillaOptionIds()
        {
            int slots = PortraitRender.PresetSlotCount();
            var ids = new List<string> { "-1" };
            bool any = false;
            for (int i = 0; i < slots; i++)
            {
                ids.Add(i.ToString(System.Globalization.CultureInfo.InvariantCulture));
                if (VanillaUsable(i)) any = true;
            }
            if (!any) ids.Add("none");
            return ids.ToArray();
        }

        internal static string[] VanillaOptionNames()
        {
            var ids = VanillaOptionIds();
            var n = new string[ids.Length];
            for (int i = 0; i < ids.Length; i++)
            {
                if (ids[i] == "none") { n[i] = I18n.Tr("No preset is free of modded items yet."); continue; }
                int v = ParseSlot(ids[i]);
                n[i] = (v < 0 || VanillaUsable(v)) ? PresetLabel(v)
                     : I18n.TrF("Preset {0} — has items an unmodded player cannot see", v + 1);
            }
            return n;
        }

        internal static int ParseSlot(string id)
        {
            int v;
            return int.TryParse(id, System.Globalization.NumberStyles.Integer, System.Globalization.CultureInfo.InvariantCulture, out v) ? v : -1;
        }

        /// <summary>The three rows' writers. Each one is edge E8: it evaluates
        /// f at the instant the setting changes.</summary>
        internal static void SetAuto(bool on)
        {
            if (Plugin.AvatarAutoSwitch == null) return;
            Plugin.AvatarAutoSwitch.Value = on;
            Evaluate("E8-auto");
        }

        internal static void SetModded(int slot)
        {
            if (Plugin.AvatarModdedPreset == null) return;
            Plugin.AvatarModdedPreset.Value = slot < 0 ? -1 : slot;
            Evaluate("E8-modded");
        }

        internal static void SetVanilla(int slot)
        {
            if (Plugin.AvatarVanillaPreset == null) return;
            if (slot >= 0 && !VanillaUsable(slot)) return;                // a slot that is not clean is refused
            Plugin.AvatarVanillaPreset.Value = slot < 0 ? -1 : slot;
            Evaluate("E8-vanilla");
        }

        // ---------------------------------------------------------------
        // The rings and the legend (design 2.6)
        // ---------------------------------------------------------------

        /// <summary>The per-frame tick, from CompetitiveRoundsBehaviour.Update
        /// (which runs with the mod's overlay closed). Self-throttled by frame
        /// count, so it keeps no timer.</summary>
        internal static void Tick()
        {
            if (Time.frameCount % 15 != 0) return;
            try { PaintRings(); } catch { }
        }

        private static void PaintRings()
        {
            var grid = MenuPortraits();
            if (grid.Count == 0 || !grid[0].gameObject.activeInHierarchy) return;
            EnsureRings();
            var s = ReadSetting();
            var cch = CharacterCreatorHandler.instance;
            var faces = ReadFaces(cch);
            var loader = ReadLoader();
            var rules = new AvatarRules();
            foreach (var p in grid)
            {
                int slot = p.transform.GetSiblingIndex();
                bool isM = slot == s.Modded, isV = slot == s.Vanilla;
                bool red = isV && !rules.Usable(slot, AvatarFacing.Vanilla, faces, loader);
                Sprite spr = red ? ringRed : (isM && isV) ? ringBoth : isM ? ringGold : isV ? ringBlue : null;
                var t = p.transform.Find(RingName);
                if (spr == null) { if (t != null) t.gameObject.SetActive(false); continue; }
                GameObject ring;
                if (t == null)
                {
                    ring = UIFactory.CreatePanel(RingName, p.transform, Color.white);
                    var img = ring.GetComponent(UIFactory.tImage);
                    if (img != null)
                        UIFactory.tImage.GetProperty("raycastTarget", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)?.SetValue(img, false);
                    var rt = ring.GetComponent<RectTransform>();
                    rt.offsetMin = new Vector2(-4, -4);
                    rt.offsetMax = new Vector2(4, 4);
                }
                else ring = t.gameObject;
                ring.SetActive(true);
                ring.transform.SetAsLastSibling();
                UIFactory.SetImageSprite(ring, spr);
            }
            PaintLegend(grid[0].transform.parent);
        }

        /// <summary>One text block beneath the grid. It lives on the grid's
        /// PARENT, never among the portraits: ShownFace walks the grid's
        /// children and reads each one's Frame.</summary>
        private static void PaintLegend(Transform gridParent)
        {
            var host = gridParent != null ? gridParent.parent : null;
            if (host == null) return;
            var t = host.Find(LegendName);
            object txt;
            if (t == null)
            {
                txt = UIFactory.CreateText(LegendName, host, "", 14f, Color.white, UIFactory.AlignTopCenter,
                    sizeDelta: new Vector2(620, 110));
                var go = ((Component)txt).gameObject;
                try
                {
                    var le = go.AddComponent(UIFactory.tLE);
                    UIFactory.tLE.GetProperty("ignoreLayout", System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance)?.SetValue(le, true);
                }
                catch { }
            }
            else
            {
                txt = null;
                foreach (var co in t.GetComponents<Component>())
                    if (co != null && co.GetType().Name == "TextMeshProUGUI") { txt = co; break; }
            }
            if (txt == null) return;
            var lrt = ((Component)txt).GetComponent<RectTransform>();
            var grt = gridParent as RectTransform;
            if (lrt != null && grt != null)
            {
                lrt.pivot = new Vector2(0.5f, 1f);
                var r = grt.rect;
                lrt.position = grt.TransformPoint(new Vector3(r.center.x, r.yMin - 6f, 0f));
            }
            UIFactory.SetTextRaw(txt, I18n.Tr("Avatar defaults") + "\n"
                + "<color=#FFD94D>" + I18n.Tr("Gold ring: your modded default") + "</color>\n"
                + "<color=#7FD4FF>" + I18n.Tr("Blue ring: your vanilla default") + "</color>\n"
                + I18n.Tr("Both rings: this preset is both of your defaults") + "\n"
                + "<color=#FF6B6B>" + I18n.Tr("Red ring: this preset has items an unmodded player cannot see, so it cannot be your vanilla default") + "</color>");
        }

        private static void EnsureRings()
        {
            if (ringsBuilt && ringGold != null && ringBlue != null && ringBoth != null && ringRed != null) return;
            var gold = new Color(1f, 0.851f, 0.302f);       // #FFD94D
            var blue = new Color(0.498f, 0.831f, 1f);       // #7FD4FF
            var red = new Color(1f, 0.42f, 0.42f);          // #FF6B6B
            ringGold = RingSprite("CR_AvRingGold", gold, gold);
            ringBlue = RingSprite("CR_AvRingBlue", blue, blue);
            ringBoth = RingSprite("CR_AvRingBoth", gold, blue);
            ringRed = RingSprite("CR_AvRingRed", red, red);
            ringsBuilt = true;
        }

        /// <summary>A square frame two bands thick: the outer band in one colour,
        /// the inner band in the other (the same colour twice for a single ring).
        /// Built the way NativeUI.CreateFfaDotSprite builds its dot, with a
        /// per-pixel test that writes a band rather than a disc, because the
        /// portrait is a square cell.</summary>
        private static Sprite RingSprite(string name, Color outer, Color inner)
        {
            const int size = 64;
            var tex = new Texture2D(size, size, TextureFormat.ARGB32, false);
            tex.name = name;
            tex.hideFlags = HideFlags.HideAndDontSave;
            tex.filterMode = FilterMode.Bilinear;
            tex.wrapMode = TextureWrapMode.Clamp;
            var px = new Color[size * size];
            var clear = new Color(0f, 0f, 0f, 0f);
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    int edge = Math.Min(Math.Min(x, y), Math.Min(size - 1 - x, size - 1 - y));
                    px[y * size + x] = edge < 3 ? outer : edge < 6 ? inner : clear;
                }
            tex.SetPixels(px);
            tex.Apply(false, true);
            var spr = Sprite.Create(tex, new Rect(0, 0, size, size), new Vector2(0.5f, 0.5f), size, 0,
                SpriteMeshType.FullRect, new Vector4(8, 8, 8, 8));
            spr.name = name;
            spr.hideFlags = HideFlags.HideAndDontSave;
            return spr;
        }
    }

    // -------------------------------------------------------------------
    // The three Harmony edges
    // -------------------------------------------------------------------

    /// <summary>E1, launch: LoadFaces is the only path that fills
    /// selectedFaceID at launch (from PlayerPrefs "SelectedFace0"), so a seat
    /// whose process was killed mid-room restores its own face here. The
    /// positive log line is how a silent non-attach is caught (#83).</summary>
    [HarmonyPatch(typeof(CharacterCreatorHandler), "LoadFaces")]
    internal static class AvatarLoadFacesPatch
    {
        private static void Postfix()
        {
            // The whole body is one exception boundary (fix pass 1, BR-M1):
            // nothing item 19 does may escape into vanilla's LoadFaces.
            try
            {
                Plugin.Log.LogInfo("[AVATAR] LoadFaces postfix attached; launch evaluation (home "
                    + (Plugin.AvatarHomeSlot != null ? Plugin.AvatarHomeSlot.Value : -1) + ")");
                AvatarDefaults.Evaluate("E1-launch");
            }
            catch (Exception ex) { AvatarDefaults.Warn("[AVATAR] E1-launch hook failed: " + ex.Message); }
        }
    }

    /// <summary>E9, an own-selection change. SelectFace is the single writer
    /// of selectedFaceID; only faceID 0 is this seat's own selection (the
    /// local-multiplayer grids pass 1..3).</summary>
    [HarmonyPatch(typeof(CharacterCreatorHandler), "SelectFace")]
    internal static class AvatarSelectFacePatch
    {
        private static void Postfix(int faceID)
        {
            try
            {
                if (faceID != 0) return;
                AvatarDefaults.Evaluate("E9-select");
            }
            catch (Exception ex) { AvatarDefaults.Warn("[AVATAR] E9-select hook failed: " + ex.Message); }
        }
    }

    /// <summary>E5, the pre-spawn deadline: the last instant a write is the
    /// face Player.Start() reads on the frame after the instantiate. Called
    /// per frame under held Space; idempotence (want == live) makes every call
    /// after the first write nothing. No return-false path: a bool prefix
    /// never skips a sibling anyway (#352), and this one decides nothing about
    /// whether the original runs.</summary>
    [HarmonyPatch(typeof(PlayerAssigner), "CreatePlayer")]
    [HarmonyPriority(Priority.VeryHigh)]
    internal static class AvatarCreatePlayerPatch
    {
        private static void Prefix()
        {
            try { AvatarDefaults.Evaluate("E5-spawn"); }
            catch (Exception ex) { AvatarDefaults.Warn("[AVATAR] E5-spawn hook failed: " + ex.Message); }
        }
    }
}
