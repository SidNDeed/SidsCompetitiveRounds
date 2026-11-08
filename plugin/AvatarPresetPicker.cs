using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>Ask 5 (2026-11-08, design ai-collab/seat-b/ASK5-DESIGN.md): the
    /// "AVATAR PRESETS" row on the game's main menu and the picker it opens.
    /// The picker shows the eight character-creator face slots labelled 1-8,
    /// each face composed from the game's own CharacterItem sprites the way
    /// vanilla's portrait draws it, and lets the player nominate item 19's two
    /// defaults (AvatarDefaults.SetModded / SetVanilla) and its auto-switch
    /// (SetAuto). It nominates only: it never selects the worn face, writes no
    /// PlayerPrefs and calls neither SelectFace nor ClickButton.
    ///
    /// The row is cloned the way MainMenuInjector clones the mod's own row: the
    /// template is the button carrying the QuitButton component (fallback: the
    /// TMP text "QUIT" read through reflection), the clone is placed with
    /// SetSiblingIndex only, its QuitButton and GoBack components are destroyed,
    /// its click runs through ClickGuard. Every UI object is built through
    /// UIFactory by reflection; no UnityEngine.UI or TMPro reference. The picker
    /// lives on its own overlay canvas (sortingOrder 30000, a background panel
    /// that swallows clicks), never touches mainMenuGroup, the menu's raycaster
    /// or the EventSystem. The face composition runs once per open and once per
    /// write, never per frame; no reflection lookup sits in a per-frame path.</summary>
    internal static class AvatarPresetPicker
    {
        // ---- D1: the page and the anchor ----------------------------------------
        /// <summary>The anchor is the mod's own main-menu row (its clone name,
        /// set by MainMenuInjector); the new row sits right after it. Sid's
        /// ONLINE-page alternative is this constant and FindAnchorRow().</summary>
        internal const string AnchorRowName = "CompetitiveRoundsButton";
        internal const string RowName = "AvatarPresetsButton";

        private static bool rowAdded;
        private static GameObject addedRow;
        private static float checkTimer;
        private static int retryCount;
        private const int MaxRetries = 30;
        private static bool wasInRoom;
        private static bool loggedExhausted;
        private static bool loggedFirst;

        private static Type tmpTextType;
        private static PropertyInfo tmpTextProp;
        private static PropertyInfo imgRaycastProp;

        internal static Type TmpTextType { get { return EnsureTmpText() ? tmpTextType : null; } }
        internal static PropertyInfo TmpTextProp { get { return EnsureTmpText() ? tmpTextProp : null; } }

        /// <summary>Called beside MainMenuInjector.Reset() when the persistent
        /// object respawns, so the row is placed again on the new scene.</summary>
        internal static void Reset()
        {
            rowAdded = false;
            addedRow = null;
            retryCount = 0;
        }

        /// <summary>Once a second from the plugin's Update, beside
        /// MainMenuInjector.TryInject(). The precondition (the anchor row exists)
        /// is checked BEFORE a retry is spent (lore #98: a budget must not tick
        /// while its precondition is unmet); a room closes the picker and costs
        /// nothing; leaving a room refreshes the budget; past the budget the
        /// cadence drops to one try in ten, never to none.</summary>
        internal static void TryPlaceRow()
        {
            checkTimer += Time.deltaTime;
            if (checkTimer < 1f) return;
            checkTimer = 0f;

            bool inRoom = false;
            try { inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { }
            if (inRoom)
            {
                wasInRoom = true;
                if (IsOpen) Close();
                return;
            }
            if (wasInRoom)
            {
                wasInRoom = false;
                retryCount = 0;
                loggedExhausted = false;
            }

            if (rowAdded && addedRow != null) return;
            if (rowAdded && addedRow == null)
            {
                rowAdded = false;          // the scene rebuilt the menu
                retryCount = 0;
            }

            // Codex r1 M1: the row's Button is rewired through UIFactory's cached
            // Button type, and the menu can be up before InitTypes runs (~3 s
            // after start); until the types resolve the row is not placed. A
            // precondition like the anchor's: no retry spent.
            if (UIFactory.tButton == null && !UIFactory.InitTypes()) return;

            ListMenuButton anchor = FindAnchorRow();
            if (anchor == null) return;    // the precondition: no retry spent

            if (retryCount >= MaxRetries)
            {
                if (!loggedExhausted)
                {
                    loggedExhausted = true;
                    Plugin.Log.LogWarning("[AVATARPICK] row placement still failing after " + MaxRetries + " attempts - slow retry (10s)");
                }
                if (retryCount % 10 != 0) { retryCount++; return; }
            }
            retryCount++;
            try { PlaceRow(anchor); }
            catch (Exception ex) { Plugin.Log.LogWarning("[AVATARPICK] row placement failed: " + ex.Message); }
        }

        /// <summary>The mod's own main-menu row, by the clone name
        /// MainMenuInjector gives it (locale-independent).</summary>
        private static ListMenuButton FindAnchorRow()
        {
            try
            {
                var all = UnityEngine.Object.FindObjectsOfType<ListMenuButton>();
                if (all == null) return null;
                foreach (var b in all)
                {
                    if (b != null && b.gameObject != null && b.gameObject.name == AnchorRowName) return b;
                }
            }
            catch { }
            return null;
        }

        /// <summary>The template beside the anchor: the button carrying the
        /// QuitButton component (ROUNDS localises the label, the component does
        /// not move), with the literal "QUIT" read through reflection as the
        /// fallback MainMenuInjector keeps.</summary>
        private static ListMenuButton FindTemplate(ListMenuButton anchor)
        {
            var all = UnityEngine.Object.FindObjectsOfType<ListMenuButton>();
            if (all == null) return null;
            foreach (var b in all)
            {
                try
                {
                    if (b != null && b.transform.parent == anchor.transform.parent && b.GetComponent<QuitButton>() != null) return b;
                }
                catch { }
            }
            if (!EnsureTmpText()) return null;
            foreach (var b in all)
            {
                try
                {
                    if (b == null || b.transform.parent != anchor.transform.parent) continue;
                    var tmp = b.GetComponentInChildren(tmpTextType, true);
                    if (tmp == null) continue;
                    string text = (tmpTextProp.GetValue(tmp) as string ?? "").Trim().ToUpperInvariant();
                    if (text == "QUIT") return b;
                }
                catch { }
            }
            return null;
        }

        private static void PlaceRow(ListMenuButton anchor)
        {
            if (!EnsureTmpText()) return;
            var template = FindTemplate(anchor);
            if (template == null)
            {
                if (!loggedFirst) Plugin.Log.LogWarning("[AVATARPICK] no QUIT template beside the anchor row");
                return;
            }
            var container = template.transform.parent;
            var clone = UnityEngine.Object.Instantiate(template.gameObject, container);
            clone.name = RowName;
            // Sibling index is for positioning only: directly under the anchor row.
            clone.transform.SetSiblingIndex(anchor.transform.GetSiblingIndex() + 1);
            try
            {
                var quit = clone.GetComponent<QuitButton>();
                if (quit != null) UnityEngine.Object.Destroy(quit);
            }
            catch { }
            try
            {
                var back = clone.GetComponent<GoBack>();
                if (back != null) UnityEngine.Object.Destroy(back);
            }
            catch { }
            try
            {
                var tmp = clone.GetComponentInChildren(tmpTextType);
                if (tmp != null) tmpTextProp.SetValue(tmp, I18n.Tr("AVATAR PRESETS"));
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[AVATARPICK] row text failed: " + ex.Message); }
            clone.AddComponent<AvatarPresetsMenuButton>();
            addedRow = clone;
            rowAdded = true;
            if (!loggedFirst)
            {
                loggedFirst = true;
                Plugin.Log.LogInfo("[AVATARPICK] row placed under " + anchor.gameObject.name);
            }
        }

        private static bool EnsureTmpText()
        {
            if (tmpTextType != null && tmpTextProp != null) return true;
            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    tmpTextType = asm.GetType("TMPro.TMP_Text");
                    if (tmpTextType != null) break;
                }
                if (tmpTextType == null) return false;
                tmpTextProp = tmpTextType.GetProperty("text", BindingFlags.Public | BindingFlags.Instance);
                return tmpTextProp != null;
            }
            catch { return false; }
        }

        // ---- the picker --------------------------------------------------------
        private static GameObject canvasGO;
        private static GameObject rootPanel;
        private static readonly List<GameObject> content = new List<GameObject>();

        private const float TileFace = 180f;
        private static readonly Color PanelColor = new Color(0.07f, 0.07f, 0.09f, 0.98f);
        private static readonly Color FaceColor = new Color(0.12f, 0.12f, 0.15f, 1f);
        private static readonly Color ButtonColor = new Color(0.18f, 0.20f, 0.26f, 1f);
        private static readonly Color DeadColor = new Color(0.11f, 0.11f, 0.13f, 1f);
        private static readonly Color DeadText = new Color(0.45f, 0.45f, 0.48f, 1f);
        private static readonly Color Gold = new Color(1f, 0.851f, 0.302f, 1f);    // #FFD94D, item 19's gold ring
        private static readonly Color Blue = new Color(0.498f, 0.831f, 1f, 1f);    // #7FD4FF, its blue ring
        private static readonly Color Red = new Color(1f, 0.42f, 0.42f, 1f);       // #FF6B6B, its red ring

        private static int openGeneration;   // the catalogue generation the open picker's text was built from (L1)

        internal static bool IsOpen { get { return canvasGO != null && canvasGO.activeSelf; } }

        internal static void Toggle()
        {
            if (IsOpen) Close(); else Open();
        }

        internal static void Open()
        {
            try
            {
                if (CompetitiveUI.InputOwnedBesidesAvatarPicker) return;   // Codex r1/r2 H2: the menu or any other input owner has the screen; the surfaces never overlap
                EnsureCanvas();
                if (canvasGO == null) return;
                canvasGO.SetActive(true);
                Rebuild();
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[AVATARPICK] open failed: " + ex.Message); }
        }

        /// <summary>L1 (Codex r2 H3): the open picker's text follows the catalogue by
        /// CLOSING. A Rebuild from the per-frame tick would put the preview composition
        /// and its lookups on that path, so a catalogue change closes the picker and the
        /// next Open composes from the new catalogue. One int compare per frame.</summary>
        internal static void CloseIfStale()
        {
            if (!IsOpen) return;
            if (I18n.CatalogueGeneration == openGeneration) return;
            Close();
        }

        internal static void Close()
        {
            try
            {
                if (canvasGO == null) return;
                ClearContent();
                canvasGO.SetActive(false);
            }
            catch { }
        }

        /// <summary>The overlay canvas, the pattern of NativeUI.EnsureOverlayCanvas:
        /// its own Canvas at sortingOrder 30000, a 1920x1080 scaler, its own
        /// GraphicRaycaster, and a background panel whose Image is a raycast
        /// target so clicks meant for the menu behind end here.</summary>
        private static void EnsureCanvas()
        {
            if (canvasGO != null) return;
            if (!UIFactory.InitTypes()) return;
            var bf = BindingFlags.Public | BindingFlags.Instance;
            canvasGO = new GameObject("CR_AvatarPickerCanvas");
            canvasGO.hideFlags = HideFlags.HideAndDontSave;
            UnityEngine.Object.DontDestroyOnLoad(canvasGO);
            if (UIFactory.tCanvas != null)
            {
                var cv = canvasGO.AddComponent(UIFactory.tCanvas);
                var rm = UIFactory.tCanvas.GetProperty("renderMode", bf);
                if (rm != null) rm.SetValue(cv, Enum.ToObject(rm.PropertyType, 0));
                var so = UIFactory.tCanvas.GetProperty("sortingOrder", bf);
                if (so != null) so.SetValue(cv, 30000);
            }
            if (UIFactory.tCanvasScaler != null)
            {
                var sc = canvasGO.AddComponent(UIFactory.tCanvasScaler);
                var smp = UIFactory.tCanvasScaler.GetProperty("uiScaleMode", bf);
                if (smp != null) smp.SetValue(sc, Enum.ToObject(smp.PropertyType, 1));
                var rr = UIFactory.tCanvasScaler.GetProperty("referenceResolution", bf);
                if (rr != null) rr.SetValue(sc, new Vector2(1920, 1080));
                // Match the screen HEIGHT: the picker is 1000 reference px tall, so an
                // ultrawide screen (1080 reference px high this way) shows all of it;
                // a 4:3 screen trims the 1600-px root's sides a little instead.
                var mw = UIFactory.tCanvasScaler.GetProperty("matchWidthOrHeight", bf);
                if (mw != null) mw.SetValue(sc, 1f);
            }
            if (UIFactory.tGR != null) canvasGO.AddComponent(UIFactory.tGR);
            canvasGO.AddComponent<AvatarPickerEscape>();
            if (UIFactory.tImage != null && imgRaycastProp == null)
                imgRaycastProp = UIFactory.tImage.GetProperty("raycastTarget", bf);

            // The background: CreatePanel gives its Image raycastTarget = true.
            UIFactory.CreatePanel("BG", canvasGO.transform, new Color(0f, 0f, 0f, 0.86f));

            rootPanel = UIFactory.CreatePanel("Root", canvasGO.transform, PanelColor, new Vector2(1600f, 1000f));
            var rrt = rootPanel.GetComponent<RectTransform>();
            rrt.anchorMin = rrt.anchorMax = new Vector2(0.5f, 0.5f);
            rrt.pivot = new Vector2(0.5f, 0.5f);
            rrt.sizeDelta = new Vector2(1600f, 1000f);
            rrt.anchoredPosition = Vector2.zero;
            UIFactory.AddVLG(rootPanel, spacing: 10, padL: 32, padR: 32, padT: 18, padB: 18, forceExpandW: true, forceExpandH: false);
        }

        private static void ClearContent()
        {
            foreach (var go in content)
            {
                try { if (go != null) UnityEngine.Object.Destroy(go); } catch { }
            }
            content.Clear();
        }

        /// <summary>Everything the picker shows, built from the game's current
        /// state: once per open and once per write. Never from an Update.</summary>
        private static void Rebuild()
        {
            openGeneration = I18n.CatalogueGeneration;
            if (rootPanel == null) return;
            ClearContent();
            var setting = AvatarDefaults.ReadSetting();
            var cch = CharacterCreatorHandler.instance;
            var faces = cch != null ? cch.playerFaces : null;
            float k = CalibrateK(TileFace);

            // Header row 1: title, the auto-switch, a spacer, Back at the right edge.
            var header = Panel("Header", rootPanel.transform, new Color(0f, 0f, 0f, 0f), 0f, 48f);
            UIFactory.AddHLG(header, spacing: 18, forceExpandW: false, forceExpandH: true);
            UIFactory.CreateText("Title", header.transform, "Avatar presets", 34f, Color.white, UIFactory.AlignMidLeft, new Vector2(420f, 48f));
            bool auto = setting.Auto;
            UIFactory.CreateButton("AutoToggle", header.transform,
                auto ? "Avatar auto-switch: <color=#88CCFF>ON</color>" : "Avatar auto-switch: <color=#88CCFF>OFF</color>",
                20f, Color.white, ButtonColor, () => ToggleAuto(), new Vector2(360f, 44f));
            var spacer = UIFactory.CreatePanel("Spacer", header.transform, new Color(0f, 0f, 0f, 0f));
            UIFactory.AddLE(spacer, flexW: 1f);
            UIFactory.CreateButton("Back", header.transform, "Back", 22f, Color.white, ButtonColor, () => Close(), new Vector2(140f, 44f));

            // Header row 2: the two choices with their Clear buttons.
            var choices = Panel("Choices", rootPanel.transform, new Color(0f, 0f, 0f, 0f), 0f, 44f);
            UIFactory.AddHLG(choices, spacing: 18, forceExpandW: false, forceExpandH: true);
            var modded = UIFactory.CreateText("ModdedReadout", choices.transform, "", 20f, Color.white, UIFactory.AlignMidLeft, new Vector2(340f, 44f));
            UIFactory.SetTextRaw(modded, "<b>" + I18n.TrF("Modded avatar: <color=#88CCFF>{0}</color>", AvatarDefaults.PresetLabel(setting.Modded)) + "</b>");
            UIFactory.CreateButton("ClearModded", choices.transform, "Clear", 18f, Color.white,
                setting.Modded >= 0 ? ButtonColor : DeadColor,
                setting.Modded >= 0 ? new UnityEngine.Events.UnityAction(() => Apply(PickerAction.ClearModded, -1)) : null, new Vector2(96f, 40f));
            var vanilla = UIFactory.CreateText("VanillaReadout", choices.transform, "", 20f, Color.white, UIFactory.AlignMidLeft, new Vector2(340f, 44f));
            UIFactory.SetTextRaw(vanilla, "<b>" + I18n.TrF("Vanilla avatar: <color=#88CCFF>{0}</color>", AvatarDefaults.PresetLabel(setting.Vanilla)) + "</b>");
            UIFactory.CreateButton("ClearVanilla", choices.transform, "Clear", 18f, Color.white,
                setting.Vanilla >= 0 ? ButtonColor : DeadColor,
                setting.Vanilla >= 0 ? new UnityEngine.Events.UnityAction(() => Apply(PickerAction.ClearVanilla, -1)) : null, new Vector2(96f, 40f));

            // The legend: item 19's own ring words, in its colours.
            var legend = UIFactory.CreateText("Legend", rootPanel.transform, "", 17f, new Color(0.85f, 0.85f, 0.88f, 1f), UIFactory.AlignTopLeft, new Vector2(1536f, 76f));
            UIFactory.SetTextRaw(legend,
                "<b><color=#FFD94D>" + I18n.Tr("Gold ring: your modded default") + "</color>   "
                + "<color=#7FD4FF>" + I18n.Tr("Blue ring: your vanilla default") + "</color>   "
                + I18n.Tr("Both rings: this preset is both of your defaults") + "\n"
                + "<color=#FF6B6B>" + I18n.Tr("Red ring: this preset has items an unmodded player cannot see, so it cannot be your vanilla default") + "</color></b>");
            var legendGO = legend as Component;
            if (legendGO != null) content.Add(legendGO.gameObject);

            // The grid: two rows of four tiles, slot order.
            GameObject[] rows = new GameObject[AvatarPickerRules.Tiles / AvatarPickerRules.Columns];
            for (int rI = 0; rI < rows.Length; rI++)
            {
                rows[rI] = Panel("Row" + rI, rootPanel.transform, new Color(0f, 0f, 0f, 0f), 0f, 372f);
                UIFactory.AddHLG(rows[rI], spacing: 16, forceExpandW: true, forceExpandH: true);
            }
            for (int s = 0; s < AvatarPickerRules.Tiles; s++)
            {
                PlayerFace face = faces != null && s < faces.Length ? faces[s] : null;
                bool present = face != null;
                bool authored = present && !(face.eyeID == 0 && face.mouthID == 0 && face.detailID == 0 && face.detail2ID == 0);
                bool clean = authored && AvatarDefaults.VanillaUsable(s);
                var tile = AvatarPickerRules.Tile(s, present, authored, clean, setting.Modded, setting.Vanilla);
                BuildTile(rows[AvatarPickerRules.Row(s)].transform, tile, face, k);
            }
        }

        private static GameObject Panel(string name, Transform parent, Color color, float w, float h)
        {
            var go = UIFactory.CreatePanel(name, parent, color);
            UIFactory.AddLE(go, minH: h, prefH: h, prefW: w > 0f ? w : -1f, flexW: w > 0f ? -1f : 1f);
            content.Add(go);
            return go;
        }

        private static void BuildTile(Transform row, PickerTile tile, PlayerFace face, float k)
        {
            var cell = UIFactory.CreatePanel("Tile" + tile.Label, row, new Color(0f, 0f, 0f, 0f));
            UIFactory.AddLE(cell, minH: 372f, prefH: 372f, flexW: 1f);
            UIFactory.AddVLG(cell, spacing: 6, forceExpandW: false, forceExpandH: false);
            AlignChildrenCenter(cell);

            // The ring(s) and the face area, centred boxes inside a fixed holder.
            var holder = UIFactory.CreatePanel("Holder", cell.transform, new Color(0f, 0f, 0f, 0f), new Vector2(TileFace + 24f, TileFace + 24f));
            UIFactory.AddLE(holder, minW: TileFace + 24f, minH: TileFace + 24f, prefW: TileFace + 24f, prefH: TileFace + 24f);
            Transform faceParent = holder.transform;
            if (tile.Ring == PickerRing.Both)
            {
                faceParent = Box("RingOuter", faceParent, Gold, TileFace + 20f).transform;
                faceParent = Box("RingInner", faceParent, Blue, TileFace + 10f).transform;
            }
            else if (tile.Ring != PickerRing.None)
            {
                var c = tile.Ring == PickerRing.Gold ? Gold : tile.Ring == PickerRing.Blue ? Blue : Red;
                faceParent = Box("Ring", faceParent, c, TileFace + 12f).transform;
            }
            var area = Box("Face", faceParent, FaceColor, TileFace);
            if (UIFactory.tRectMask2D != null) { try { area.AddComponent(UIFactory.tRectMask2D); } catch { } }
            if (!tile.Empty) Compose(area, face, k);

            // The digit is an identity string: set raw, never a translation key.
            var label = UIFactory.CreateText("Label", cell.transform, "", 28f, Color.white, UIFactory.AlignMidCenter, new Vector2(TileFace, 34f));
            UIFactory.SetTextRaw(label, "<b>" + tile.Label + "</b>");
            var hint = UIFactory.CreateText("Hint", cell.transform, "", 15f,
                tile.Dirty ? Red : DeadText, UIFactory.AlignMidCenter, new Vector2(TileFace + 100f, 22f));
            if (tile.Empty) UIFactory.SetText(hint, "Empty");
            else if (tile.Dirty) UIFactory.SetText(hint, "Has modded items");

            var buttons = UIFactory.CreatePanel("Buttons", cell.transform, new Color(0f, 0f, 0f, 0f), new Vector2(TileFace + 100f, 44f));
            UIFactory.AddLE(buttons, minW: TileFace + 100f, minH: 44f, prefW: TileFace + 100f, prefH: 44f);
            UIFactory.AddHLG(buttons, spacing: 10, forceExpandW: false, forceExpandH: true);
            var t = tile;
            UIFactory.CreateButton("Modded", buttons.transform, "Modded", 18f,
                t.ModdedEnabled ? Color.white : DeadText,
                t.ModdedEnabled ? (t.IsModded ? Gold * 0.6f : ButtonColor) : DeadColor,
                t.ModdedEnabled ? new UnityEngine.Events.UnityAction(() => Apply(AvatarPickerRules.ModdedClick(t), t.Slot)) : null, new Vector2(132f, 40f));
            UIFactory.CreateButton("Vanilla", buttons.transform, "Vanilla", 18f,
                t.VanillaEnabled ? Color.white : DeadText,
                t.VanillaEnabled ? (t.IsVanilla ? Blue * 0.6f : ButtonColor) : DeadColor,
                t.VanillaEnabled ? new UnityEngine.Events.UnityAction(() => Apply(AvatarPickerRules.VanillaClick(t), t.Slot)) : null, new Vector2(132f, 40f));
        }

        private static void AlignChildrenCenter(GameObject vlgOwner)
        {
            // The VLG's childAlignment = MiddleCenter (TextAnchor 4), by reflection once per tile build.
            try
            {
                var t = vlgOwner.GetComponent("VerticalLayoutGroup");
                if (t == null) return;
                var p = t.GetType().GetProperty("childAlignment", BindingFlags.Public | BindingFlags.Instance);
                if (p != null) p.SetValue(t, Enum.ToObject(p.PropertyType, 4));
            }
            catch { }
        }

        /// <summary>A fixed square box centred in its parent.</summary>
        private static GameObject Box(string name, Transform parent, Color color, float size)
        {
            var go = UIFactory.CreatePanel(name, parent, color, new Vector2(size, size));
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = rt.pivot = new Vector2(0.5f, 0.5f);
            rt.sizeDelta = new Vector2(size, size);
            rt.anchoredPosition = Vector2.zero;
            SetRaycast(go, false);
            return go;
        }

        /// <summary>The writes: item 19's three setters and nothing else, then a
        /// rebuild so the rings, readouts and buttons follow the new state.</summary>
        /// <summary>Codex r1 H1: the live gate before every write. Item 19's
        /// setters each evaluate E8, and E8 applies a face in an online room or
        /// while the player's own face is held in Home for a restoration; the
        /// picker writes only when neither holds, read HERE at the click (the
        /// one-second poll is stale for a join that landed after it). A refusal
        /// closes the picker: it never changes the worn face (D5).</summary>
        private static bool WriteGateOpen(string what)
        {
            bool inRoom = false, unreadable = false;
            // Codex r2 H1: GameStateWatcher.IsInOnlineRoom is a flag its 0.1 s poll writes, so it
            // can say "menu" for a join that landed since the last poll; E8 reads Photon itself
            // (AvatarDefaults.cs), so the gate reads the same two live flags, failing closed on a throw.
            try { inRoom = Photon.Pun.PhotonNetwork.InRoom && !Photon.Pun.PhotonNetwork.OfflineMode; } catch { unreadable = true; }
            int heldHome = -1;
            try { if (Plugin.AvatarHomeSlot != null) heldHome = Plugin.AvatarHomeSlot.Value; } catch { unreadable = true; }
            if (AvatarPickerRules.WriteAllowed(inRoom, unreadable, heldHome)) return true;
            Plugin.Log.LogInfo("[AVATARPICK] " + what + " refused: " + (inRoom ? "in a room" : unreadable ? "room state unreadable" : "a restoration of the home face is owed") + "; the picker closes");
            return false;
        }

        private static void ToggleAuto()
        {
            if (!WriteGateOpen("auto toggle")) { Close(); return; }
            AvatarDefaults.SetAuto(!AvatarDefaults.ReadSetting().Auto);
            Rebuild();
        }

        private static void Apply(PickerAction action, int slot)
        {
            if (!WriteGateOpen("nomination")) { Close(); return; }
            switch (action)
            {
                case PickerAction.SetModded: AvatarDefaults.SetModded(slot); break;
                case PickerAction.ClearModded: AvatarDefaults.SetModded(-1); break;
                case PickerAction.SetVanilla: AvatarDefaults.SetVanilla(slot); break;
                case PickerAction.ClearVanilla: AvatarDefaults.SetVanilla(-1); break;
                default: return;
            }
            Rebuild();
        }

        // ---- the face, composed from the game's own sprites -----------------------
        private struct Part
        {
            internal Sprite Sprite;
            internal Color Color;
            internal int Order;
            internal float Scale;
            internal Vector2 Offset, FaceOffset, Size, PivotFrac;
        }

        /// <summary>Vanilla's CharacterCreatorItemEquipper.EquipFace, in UI: the
        /// four parts through the one funnel CharacterCreatorItemLoader.GetItem
        /// (the mod's ids >= 1000 resolve in its prefix), each an Image with the
        /// prefab's sprite and colour, placed by AvatarPickerRules.PartRect and
        /// ordered by the prefab's sorting order.</summary>
        private static void Compose(GameObject area, PlayerFace face, float k)
        {
            var loader = CharacterCreatorItemLoader.instance;
            if (loader == null || face == null) return;
            var parts = new List<Part>(4);
            AddPart(parts, loader, face.eyeID, CharacterItemType.Eyes, face.eyeOffset);
            AddPart(parts, loader, face.mouthID, CharacterItemType.Mouth, face.mouthOffset);
            AddPart(parts, loader, face.detailID, CharacterItemType.Detail, face.detailOffset);
            AddPart(parts, loader, face.detail2ID, CharacterItemType.Detail, face.detail2Offset);
            parts.Sort((p, q) => p.Order.CompareTo(q.Order));
            int n = 0;
            foreach (var p in parts)
            {
                float w, h, x, y;
                AvatarPickerRules.PartRect(p.Size.x, p.Size.y, p.PivotFrac.x, p.PivotFrac.y, p.Scale,
                                           p.Offset.x, p.Offset.y, p.FaceOffset.x, p.FaceOffset.y, k,
                                           out w, out h, out x, out y);
                var go = UIFactory.CreatePanel("Part" + n++, area.transform, p.Color);
                UIFactory.SetImageSprite(go, p.Sprite);
                SetRaycast(go, false);
                var rt = go.GetComponent<RectTransform>();
                rt.anchorMin = rt.anchorMax = rt.pivot = new Vector2(0.5f, 0.5f);
                rt.sizeDelta = new Vector2(w, h);
                rt.anchoredPosition = new Vector2(x, y);
            }
        }

        private static void AddPart(List<Part> parts, CharacterCreatorItemLoader loader, int id, CharacterItemType type, Vector2 faceOffset)
        {
            CharacterItem item = null;
            try { item = loader.GetItem(id, type); } catch { }
            if (item == null) return;
            SpriteRenderer sr = null;
            try { sr = item.GetComponent<SpriteRenderer>(); } catch { }
            var sprite = item.sprite != null ? item.sprite : (sr != null ? sr.sprite : null);
            if (sprite == null) return;
            var rect = sprite.rect;
            var pivot = rect.width > 0f && rect.height > 0f ? new Vector2(sprite.pivot.x / rect.width, sprite.pivot.y / rect.height) : new Vector2(0.5f, 0.5f);
            parts.Add(new Part
            {
                Sprite = sprite,
                Color = sr != null ? sr.color : Color.white,
                Order = sr != null ? sr.sortingOrder : 0,
                Scale = item.scale,
                Offset = item.offset,
                FaceOffset = faceOffset,
                Size = sprite.bounds.size,
                PivotFrac = pivot,
            });
        }

        /// <summary>Tile pixels per world unit from a live main-menu portrait
        /// (its equipper's scaleM and its BG width), else the fallback.</summary>
        private static float CalibrateK(float tile)
        {
            float fallback = AvatarPickerRules.FallbackK(tile);
            try
            {
                var portraits = AvatarDefaults.MenuPortraits();
                foreach (var p in portraits)
                {
                    if (p == null) continue;
                    var eq = p.GetComponentInChildren<CharacterCreatorItemEquipper>(true);
                    var bg = p.transform.Find("BG");
                    var bgRt = bg != null ? bg.GetComponent<RectTransform>() : null;
                    float bgW = bgRt != null ? bgRt.rect.width : 0f;
                    if (eq != null && bgW > 0f) return AvatarPickerRules.Calibration(eq.scaleM, bgW, tile, fallback);
                }
            }
            catch { }
            return fallback;
        }

        private static void SetRaycast(GameObject go, bool on)
        {
            try
            {
                if (go == null || UIFactory.tImage == null || imgRaycastProp == null) return;
                var img = go.GetComponent(UIFactory.tImage);
                if (img != null) imgRaycastProp.SetValue(img, on);
            }
            catch { }
        }
    }

    /// <summary>The row's click: the Button's onClick cleared and re-wired by
    /// reflection once in Start (as CompetitiveMenuButton does), the click
    /// through ClickGuard (0.2 s per control), and the label re-asserted five
    /// times a second from cached handles (ROUNDS' ListMenuButton resets the
    /// text after submenu navigation); no lookup runs per frame.</summary>
    internal sealed class AvatarPresetsMenuButton : MonoBehaviour
    {
        private object tmp;
        private PropertyInfo textProp;
        private string label;
        private float enforceTimer;
        private int labelGeneration;

        private void Start()
        {
            try
            {
                var t = AvatarPresetPicker.TmpTextType;
                if (t != null)
                {
                    tmp = GetComponentInChildren(t);
                    textProp = AvatarPresetPicker.TmpTextProp;
                }
            }
            catch { }
            labelGeneration = I18n.CatalogueGeneration;
            label = RowLabel();
            // Codex r1 M1: a row whose Button could not be rewired is not a row; it
            // goes away and TryPlaceRow places it again on its next tick (bounded
            // by its retry budget), with no lookup in any per-frame path.
            if (!TryWire())
            {
                Plugin.Log.LogWarning("[AVATARPICK] row wiring incomplete; the row is removed and placed again");
                UnityEngine.Object.Destroy(gameObject);
            }
        }

        private static string RowLabel()
        {
            return I18n.Tr("AVATAR PRESETS");
        }

        /// <summary>The clone's Button.onClick loses the template's listener and
        /// gains OnClick, through UIFactory's cached Button type. False when
        /// anything along that path is missing.</summary>
        private bool TryWire()
        {
            try
            {
                var bt = UIFactory.tButton;
                if (bt == null) return false;
                var btn = GetComponent(bt);
                if (btn == null) return false;
                var onClickProp = bt.GetProperty("onClick", BindingFlags.Public | BindingFlags.Instance);
                var onClick = onClickProp != null ? onClickProp.GetValue(btn) : null;
                if (onClick == null) return false;
                var removeAll = onClick.GetType().GetMethod("RemoveAllListeners");
                if (removeAll != null) removeAll.Invoke(onClick, null);
                var add = onClick.GetType().GetMethod("AddListener");
                if (add == null) return false;
                UnityEngine.Events.UnityAction action = OnClick;
                add.Invoke(onClick, new object[] { action });
                return true;
            }
            catch (Exception ex) { Plugin.Log.LogWarning("[AVATARPICK] row wiring failed: " + ex.Message); return false; }
        }

        private void LateUpdate()
        {
            if (tmp == null || textProp == null) return;
            enforceTimer += Time.unscaledDeltaTime;
            if (enforceTimer < 0.2f) return;
            enforceTimer = 0f;
            try
            {
                int gen = I18n.CatalogueGeneration;
                if (gen != labelGeneration) { labelGeneration = gen; label = RowLabel(); }   // L1: a language change re-translates the label
                if ((textProp.GetValue(tmp) as string) != label) textProp.SetValue(tmp, label);
            }
            catch { }
        }

        private void OnClick()
        {
            if (!ClickGuard.Claim(this)) return;
            AvatarPresetPicker.Toggle();
        }
    }

    /// <summary>The open picker's per-frame tick: Escape closes it; the F5 menu or
    /// any other input owner appearing closes it too (Codex r1/r2 H2: the surfaces
    /// never overlap); a catalogue change closes it (L1, Codex r2 H3: no rebuild on
    /// this path). Three reads per frame, no lookup, no composition.</summary>
    internal sealed class AvatarPickerEscape : MonoBehaviour
    {
        private void Update()
        {
            if (CompetitiveUI.InputOwnedBesidesAvatarPicker) { AvatarPresetPicker.Close(); return; }
            if (Input.GetKeyDown(KeyCode.Escape)) { AvatarPresetPicker.Close(); return; }
            AvatarPresetPicker.CloseIfStale();
        }
    }
}
