using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 17 (v1.41.0): the Controls sub-tab - the eighth member of the
    /// settings page's sub-tab bar - and every player-facing string the
    /// keybind system shows: the sixteen row labels and help bodies, the
    /// binding faces (key and mouse names), the refusals, the ready-up
    /// prompts and the round-start toast. Every literal sits inside its own
    /// I18n.Tr / TrF so tools/i18n_extract.py harvests it (this file is on
    /// its explicit list, #464). Keybinds.cs holds no display text.
    /// </summary>
    public static partial class NativeUI
    {
        // ---------------------------------------------------------------
        // Display names (design section 2.9)
        // ---------------------------------------------------------------

        /// <summary>The name of one InControl Key row: the glyph a glyph key
        /// prints (68 keys, never translated), the function key's own id
        /// (15), or one of the 48 named keys through the catalogue.</summary>
        internal static string KeybindKeyName(int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeybindRules.KeyTableLength) return I18n.Tr("Unbound");
            string glyph = KeybindRules.GlyphFor(keyOrdinal);
            if (glyph != null) return glyph;
            if (KeybindRules.FunctionNumber(keyOrdinal) > 0) return KeybindRules.KeyIds[keyOrdinal];
            switch (KeybindRules.KeyIds[keyOrdinal])
            {
                case "Shift": return I18n.Tr("Shift");
                case "Alt": return I18n.Tr("Alt");
                case "Command": return I18n.Tr("Command");
                case "Control": return I18n.Tr("Control");
                case "LeftShift": return I18n.Tr("Left Shift");
                case "LeftAlt": return I18n.Tr("Left Alt");
                case "LeftCommand": return I18n.Tr("Left Command");
                case "LeftControl": return I18n.Tr("Left Control");
                case "RightShift": return I18n.Tr("Right Shift");
                case "RightAlt": return I18n.Tr("Right Alt");
                case "RightCommand": return I18n.Tr("Right Command");
                case "RightControl": return I18n.Tr("Right Control");
                case "Escape": return I18n.Tr("Escape");
                case "Backspace": return I18n.Tr("Backspace");
                case "Tab": return I18n.Tr("Tab");
                case "Return": return I18n.Tr("Return");
                case "Space": return I18n.Tr("Space");
                case "Insert": return I18n.Tr("Insert");
                case "Delete": return I18n.Tr("Delete");
                case "Home": return I18n.Tr("Home");
                case "End": return I18n.Tr("End");
                case "PageUp": return I18n.Tr("PageUp");
                case "PageDown": return I18n.Tr("PageDown");
                case "LeftArrow": return I18n.Tr("Left Arrow");
                case "RightArrow": return I18n.Tr("Right Arrow");
                case "UpArrow": return I18n.Tr("Up Arrow");
                case "DownArrow": return I18n.Tr("Down Arrow");
                case "Pad0": return I18n.Tr("Pad 0");
                case "Pad1": return I18n.Tr("Pad 1");
                case "Pad2": return I18n.Tr("Pad 2");
                case "Pad3": return I18n.Tr("Pad 3");
                case "Pad4": return I18n.Tr("Pad 4");
                case "Pad5": return I18n.Tr("Pad 5");
                case "Pad6": return I18n.Tr("Pad 6");
                case "Pad7": return I18n.Tr("Pad 7");
                case "Pad8": return I18n.Tr("Pad 8");
                case "Pad9": return I18n.Tr("Pad 9");
                case "Numlock": return I18n.Tr("Numlock");
                case "PadDivide": return I18n.Tr("Pad Divide");
                case "PadMultiply": return I18n.Tr("Pad Multiply");
                case "PadMinus": return I18n.Tr("Pad Minus");
                case "PadPlus": return I18n.Tr("Pad Plus");
                case "PadEnter": return I18n.Tr("Pad Enter");
                case "PadPeriod": return I18n.Tr("Pad Period");
                case "Clear": return I18n.Tr("Clear");
                case "PadEquals": return I18n.Tr("Pad Equals");
                case "AltGr": return I18n.Tr("Alt Graphic");
                case "CapsLock": return I18n.Tr("Caps Lock");
                default: return KeybindRules.KeyIds[keyOrdinal];
            }
        }

        /// <summary>A mouse source's name (InControl.Mouse value).</summary>
        internal static string KeybindMouseName(int mouseValue)
        {
            switch (mouseValue)
            {
                case 1: return I18n.Tr("Left Mouse");
                case 2: return I18n.Tr("Right Mouse");
                case 3: return I18n.Tr("Middle Mouse");
                default:
                    int n = mouseValue >= 10 && mouseValue <= 13 ? mouseValue - 6 : mouseValue;
                    return I18n.TrF("Mouse {0}", n.ToString(CultureInfo.InvariantCulture));
            }
        }

        internal static string KeybindFace(BindSource s)
        {
            if (s.Kind == BindKind.Key) return KeybindKeyName(s.Value);
            if (s.Kind == BindKind.Mouse) return KeybindMouseName(s.Value);
            return I18n.Tr("Unbound");
        }

        /// <summary>The face of one row: what the row is bound to now (the
        /// default while the accessor is not validated).</summary>
        internal static string KeybindRowFace(int row)
        {
            return KeybindFace(Keybinds.MappingReady ? Keybinds.Bound(row) : KeybindRules.Default(row));
        }

        internal static string KeybindRowLabel(int row)
        {
            switch (row)
            {
                case KeybindRules.MenuToggle: return I18n.Tr("Menu");
                case KeybindRules.Scoreboard: return I18n.Tr("Scoreboard");
                case KeybindRules.QuickChat: return I18n.Tr("Quick chat");
                case KeybindRules.DanceWheel: return I18n.Tr("Dance wheel");
                case KeybindRules.ChatOpen: return I18n.Tr("Open chat");
                case KeybindRules.ChatChannel: return I18n.Tr("Chat language channel");
                case KeybindRules.ChatOverlayMode: return I18n.Tr("Chat overlay mode");
                case KeybindRules.MapSkinCycle: return I18n.Tr("Map skin cycle");
                case KeybindRules.AvatarSwap: return I18n.Tr("Avatar swap");
                case KeybindRules.MoveUp: return I18n.Tr("Move up");
                case KeybindRules.MoveDown: return I18n.Tr("Move down");
                case KeybindRules.MoveLeft: return I18n.Tr("Move left");
                case KeybindRules.MoveRight: return I18n.Tr("Move right");
                case KeybindRules.Jump: return I18n.Tr("Jump");
                case KeybindRules.Fire: return I18n.Tr("Shoot");
                case KeybindRules.Block: return I18n.Tr("Block");
                default: return "";
            }
        }

        private static string KeybindRowHelp(int row)
        {
            switch (row)
            {
                case KeybindRules.MenuToggle: return I18n.Tr("Opens and closes this menu. F5 always works as well, whatever you set here.");
                case KeybindRules.Scoreboard: return I18n.Tr("Hold in a match for the live scoreboard: score, cards, accuracy and connection.");
                case KeybindRules.QuickChat: return I18n.Tr("Hold to open the quick-chat wheel, point at a phrase and release to send it.");
                case KeybindRules.DanceWheel: return I18n.Tr("Hold to open the dance wheel. Dancing locks your own controls until it ends.");
                case KeybindRules.ChatOpen: return I18n.Tr("Opens the mod's own chat box. The vanilla chat keeps its own key.");
                case KeybindRules.ChatChannel: return I18n.Tr("Tapped while typing, switches which language channel your message goes to. Needs a key that types nothing.");
                case KeybindRules.ChatOverlayMode: return I18n.Tr("Cycles the chat overlay between normal, pinned and muted.");
                case KeybindRules.MapSkinCycle: return I18n.Tr("Cycles your equipped map color skins as a new round paints in.");
                case KeybindRules.AvatarSwap: return I18n.Tr("Swaps your avatar in the seats that show one.");
                case KeybindRules.MoveUp: return I18n.Tr("Moves your character up. This is the game's own control - the mod rewrites the game's binding.");
                case KeybindRules.MoveDown: return I18n.Tr("Moves your character down.");
                case KeybindRules.MoveLeft: return I18n.Tr("Moves your character left.");
                case KeybindRules.MoveRight: return I18n.Tr("Moves your character right.");
                case KeybindRules.Jump: return I18n.Tr("Jumps. In a lobby the same control readies you up and joins.");
                case KeybindRules.Fire: return I18n.Tr("Fires your gun.");
                case KeybindRules.Block: return I18n.Tr("Raises your block.");
                default: return "";
            }
        }

        private static string KeybindRowRecommended(int row)
        {
            switch (row)
            {
                case KeybindRules.MenuToggle: return I18n.Tr("Recommended: the default. F5 always opens this menu, whatever you set here.");
                case KeybindRules.ChatChannel: return I18n.Tr("Recommended: the default. This one is read while you are typing, so it needs a key that types nothing - a modifier, a function key or one of the navigation keys.");
                case KeybindRules.MapSkinCycle: return I18n.Tr("Recommended: the default. Left Shift also cycles the base game's own map art. Both follow this control.");
                case KeybindRules.Jump: return I18n.Tr("Recommended: the default. Space also readies you up in a lobby. Move Jump and the ready-up key moves with it.");
            }
            return KeybindRules.IsGameRow(row)
                ? I18n.Tr("Recommended: the default. All seven game controls can take a mouse button; the mod's own controls cannot.")
                : I18n.Tr("Recommended: the default. Every screenshot and every other player's habit assumes it.");
        }

        private static string KeybindRefusalText(Refusal r)
        {
            switch (r)
            {
                case Refusal.Overlap: return I18n.Tr("That key is already used by another control.");
                case Refusal.TypesText: return I18n.Tr("That key types into the chat box it would switch.");
                case Refusal.Reserved: return I18n.Tr("The game reserves that key.");
                case Refusal.MouseOnModRow: return I18n.Tr("The mod's own controls cannot take a mouse button.");
                case Refusal.RescueKey: return I18n.Tr("F5 stays on the menu control.");
                case Refusal.WheelModifier: return I18n.Tr("The two wheels cannot take a modifier key.");
                case Refusal.ApplyFailed: return KeybindApplyFailedText();
                default: return "";
            }
        }

        /// <summary>Fix pass 1 F6: a valid change whose commit threw; every
        /// control was put back as it was.</summary>
        internal static string KeybindApplyFailedText()
        {
            return I18n.Tr("That change could not be applied, so every control was put back as it was.");
        }

        /// <summary>The vanilla join prompt, naming the bound Jump control.</summary>
        internal static string KeybindJoinPrompt()
        {
            return I18n.TrF("Press\n[{0}]\nto join", KeybindRowFace(KeybindRules.Jump).ToUpperInvariant());
        }

        /// <summary>The vanilla ready prompt, naming the bound Jump control.</summary>
        internal static string KeybindReadyPrompt()
        {
            return I18n.TrF("Press [{0}] when ready", KeybindRowFace(KeybindRules.Jump).ToUpperInvariant());
        }

        /// <summary>Q5: one local toast at the next round start after the
        /// player rebinds, naming every row that changed and its new face.</summary>
        internal static string KeybindChangedToast(List<int> rows)
        {
            if (rows == null || rows.Count == 0) return null;
            var sb = new StringBuilder();
            foreach (int r in rows)
            {
                if (sb.Length > 0) sb.Append(", ");
                sb.Append(KeybindRowLabel(r)).Append(" = ").Append(KeybindRowFace(r));
            }
            return I18n.TrF("Your controls changed: {0}", sb.ToString());
        }

        /// <summary>The input overlay's cap for one row: the local player's
        /// own binding, or the semantic action on a spectating seat, whose
        /// keyboard is not the watched player's (design section 2.7).</summary>
        internal static string KeybindOverlayCap(int row, bool spectator)
        {
            if (spectator)
            {
                switch (row)
                {
                    case KeybindRules.MoveUp: return I18n.Tr("UP");
                    case KeybindRules.MoveDown: return I18n.Tr("DOWN");
                    case KeybindRules.MoveLeft: return I18n.Tr("LEFT");
                    case KeybindRules.MoveRight: return I18n.Tr("RIGHT");
                    case KeybindRules.Jump: return I18n.Tr("JUMP");
                    case KeybindRules.Fire: return I18n.Tr("FIRE");
                    case KeybindRules.Block: return I18n.Tr("BLOCK");
                }
            }
            return KeybindRowFace(row).ToUpperInvariant();
        }

        /// <summary>The semantic caps the broadcast HUD draws over a watched
        /// player's REPLICATED state: that player's binding is unknown here.</summary>
        internal static string KeybindSemanticCap(int row) { return KeybindOverlayCap(row, true); }

        // ---------------------------------------------------------------
        // Bodies elsewhere that name a binding (design section 2.7's
        // inventory): each takes the bound name, never a fixed key.
        // ---------------------------------------------------------------

        /// <summary>The four movement names and the jump name, as the input
        /// overlay's settings row lists them.</summary>
        private static string KbMoveAndJumpFaces()
        {
            return string.Join(", ", new[]
            {
                KeybindRowFace(KeybindRules.MoveUp), KeybindRowFace(KeybindRules.MoveLeft),
                KeybindRowFace(KeybindRules.MoveDown), KeybindRowFace(KeybindRules.MoveRight),
                KeybindRowFace(KeybindRules.Jump),
            });
        }

        private static string KbDescInputOverlay()
        {
            return I18n.TrF("Input overlay (bottom-left): shows {0} and both mouse buttons. Lights up red when pressed. Useful for streams or spotting missed inputs.",
                KbMoveAndJumpFaces());
        }

        private static string KbDescInGameChat()
        {
            return I18n.TrF("Shows community chat in the corner while you play. Press {0} to type a reply, or {1} in game to cycle normal / pinned / muted.",
                KeybindRowFace(KeybindRules.ChatOpen), KeybindRowFace(KeybindRules.ChatOverlayMode));
        }

        private static string KbDescHpPrecision()
        {
            return I18n.TrF("Decimals on the HP readout in the hold-{0} board, the spectator seat and the broadcaster HUD. Both halves of \"current/max\" follow it, so a card that leaves max health on a fraction stops reading as a whole number too. Local display only - nothing stored or sent changes.",
                KeybindRowFace(KeybindRules.Scoreboard));
        }

        /// <summary>A shop category description: the two that name a key
        /// (map colours, dances) take the bound one.</summary>
        private static string KbShopTabDesc(int i)
        {
            string d = SHOP_TAB_DESCS[i];
            if (d.IndexOf("{0}", StringComparison.Ordinal) < 0) return I18n.Tr(d);
            int row = d.StartsWith("Emote", StringComparison.Ordinal) ? KeybindRules.DanceWheel : KeybindRules.MapSkinCycle;
            return I18n.TrF(d, KeybindRowFace(row));
        }

        /// <summary>A shop item's server description. The two dance rows
        /// the server carries end "with the E wheel."; they render through
        /// the catalogue's "{0} wheel." template with the bound key, so the
        /// line is right for a player who moved the wheel and is translated
        /// from the same key (tools/shop_strings.json registers it).</summary>
        private static string KbShopItemDesc(string description)
        {
            string d = description ?? "";
            const string legacy = " with the E wheel.";
            if (d.EndsWith(legacy, StringComparison.Ordinal))
                return I18n.TrF(d.Substring(0, d.Length - legacy.Length) + " with the {0} wheel.", KeybindRowFace(KeybindRules.DanceWheel));
            return I18n.Tr(d);
        }

        /// <summary>The settings rows whose help body names a binding are
        /// built once per page; a rebind refreshes their bodies.</summary>
        private static void KbRefreshNamedDescs()
        {
            SettingsRowRec r;
            if (settingsByKey.TryGetValue("SInpOv", out r)) r.Desc = KbDescInputOverlay();
            if (settingsByKey.TryGetValue("SIgChat", out r)) r.Desc = KbDescInGameChat();
            if (settingsByKey.TryGetValue("SHpPrec", out r)) r.Desc = KbDescHpPrecision();
        }

        // ---------------------------------------------------------------
        // The Controls body (design section 2.5)
        // ---------------------------------------------------------------

        private static int kbPaintedRev = -1, kbPaintedGen = -1, kbPaintedCapture = -2;
        private static bool kbResetArmed;
        private static GameObject kbResetAllBtn, kbResetAllConfirmBtn, kbResetAllCancelBtn;
        private static readonly Dictionary<int, SettingsRowRec> kbRows = new Dictionary<int, SettingsRowRec>();

        private static int KeybindTabIndex { get { return SettingsModel.SubTabIndex("controls"); } }

        /// <summary>The capture's surface: the page is open on the settings
        /// tab with the Controls body showing. FrameTick cancels a capture
        /// the moment this is false.</summary>
        internal static bool KeybindCaptureSurfaceVisible()
        {
            int t = KeybindTabIndex;
            return isOpen && pageBuilt && currentTab == TAB_SETTINGS && settingsSubTab == t
                && t >= 0 && settingsBodies[t] != null && settingsBodies[t].activeInHierarchy;
        }

        /// <summary>From BuildSettingsTab: the two headed sections, sixteen
        /// rows, each emitted by SettingsKeybind.</summary>
        private static void BuildControlsRows(Transform body)
        {
            kbRows.Clear();
            kbPaintedRev = kbPaintedGen = -1;
            kbPaintedCapture = -2;
            KeybindHeading(body, "SKbHeadMod", I18n.Tr("Mod controls"));
            for (int r = 0; r < KeybindRules.FirstGameRow; r++) SettingsKeybind(body, r);
            KeybindHeading(body, "SKbHeadGame", I18n.Tr("Game controls"));
            for (int r = KeybindRules.FirstGameRow; r < KeybindRules.RowCount; r++) SettingsKeybind(body, r);
        }

        private static void KeybindHeading(Transform body, string name, string text)
        {
            var h = UIFactory.CreateText(name, body, text, 15f, C_GOLD, UIFactory.AlignMidLeft, sizeDelta: new Vector2(960, 22));
            UIFactory.FitOneLine(h);
            UIFactory.AddLE(((Component)h).gameObject, minH: 22, prefH: 22, flexH: 0);
        }

        /// <summary>One KEYBIND row: SKb&lt;Id&gt; with _q, _l, _c and in the
        /// cell _b (the 240 px face), _x (unbind) and _r (reset this row).</summary>
        private static GameObject SettingsKeybind(Transform parent, int row)
        {
            string key = "SKb" + KeybindRules.RowIds[row];
            var rec = SettingsNewRow(parent, key, SettingsKind.Keybind, KeybindRowHelp(row));
            rec.KbRow = row;
            var b = UIFactory.CreateButton(key + "_b", rec.Cell.transform, "", 14f, C_WHITE, C_BTN,
                () => { SettingsSelectRec(rec); KeybindArm(rec); }, new Vector2(240, 26));
            UIFactory.SetMinW(b, 240);
            rec.Face = b;
            rec.FaceTxt = UIFactory.GetButtonText(b);
            var x = UIFactory.CreateButton(key + "_x", rec.Cell.transform, "", 14f, C_WHITE, C_BTN,
                () => { SettingsSelectRec(rec); KeybindUnbind(rec); }, new Vector2(26, 26));
            UIFactory.SetMinW(x, 26);
            UIFactory.SetTextNoHook(UIFactory.GetButtonText(x), "×");
            rec.KbUnbind = x;
            var rs = UIFactory.CreateButton(key + "_r", rec.Cell.transform, "", 14f, C_WHITE, C_BTN,
                () => { SettingsSelectRec(rec); KeybindResetRow(rec); }, new Vector2(26, 26));
            UIFactory.SetMinW(rs, 26);
            UIFactory.SetTextNoHook(UIFactory.GetButtonText(rs), "↺");
            rec.KbReset = rs;
            kbRows[row] = rec;
            KeybindPaintRow(rec);
            return rec.Row;
        }

        private static void KeybindArm(SettingsRowRec rec)
        {
            if (rec == null || rec.KbRow < 0) return;
            if (Keybinds.KeybindCaptureActive) return;   // the armed row's own clicks are inert
            if (!Keybinds.ArmCapture(rec.KbRow)) { settingsPaneDirty = true; return; }
            KeybindPaintAll();
            settingsPaneDirty = true;
        }

        private static void KeybindUnbind(SettingsRowRec rec)
        {
            if (rec == null || rec.KbRow < 0 || Keybinds.KeybindCaptureActive || !Keybinds.RowsWritable) return;
            Keybinds.Unbind(rec.KbRow);
            KeybindPaintAll();
            settingsPaneDirty = true;
        }

        private static void KeybindResetRow(SettingsRowRec rec)
        {
            if (rec == null || rec.KbRow < 0 || Keybinds.KeybindCaptureActive || !Keybinds.RowsWritable) return;
            Keybinds.ResetRow(rec.KbRow);
            KeybindPaintAll();
            settingsPaneDirty = true;
        }

        private static void KeybindPaintRow(SettingsRowRec rec)
        {
            if (rec == null || rec.KbRow < 0) return;
            int row = rec.KbRow;
            string label = KeybindRowLabel(row);
            bool capturing = Keybinds.CaptureRow == row;
            string face = capturing ? I18n.Tr("Press a key...") : KeybindRowFace(row);
            rec.LastLabel = label;
            rec.LastValue = face;
            rec.LastPainted = label + ": " + face;
            UIFactory.SetTextNoHook(rec.Label, label);
            UIFactory.SetTextNoHook(rec.FaceTxt, face);
            bool writable = Keybinds.RowsWritable;
            UIFactory.SetImageColor(rec.Face, capturing ? C_TABACT : C_BTN);
            UIFactory.SetColor(rec.FaceTxt, !writable ? C_DIM : Keybinds.BoundSourceUnreadable(row) ? C_RED : C_WHITE);
            bool inert = capturing || !writable;
            if (rec.KbUnbind != null) UIFactory.SetColor(UIFactory.GetButtonText(rec.KbUnbind), inert ? C_DIM : C_WHITE);
            if (rec.KbReset != null) UIFactory.SetColor(UIFactory.GetButtonText(rec.KbReset), inert ? C_DIM : C_WHITE);
        }

        private static void KeybindPaintAll()
        {
            foreach (var kv in kbRows) KeybindPaintRow(kv.Value);
            KbRefreshNamedDescs();
            kbPaintedRev = Keybinds.Revision;
            kbPaintedGen = settingsBuildGen;
            kbPaintedCapture = Keybinds.CaptureRow;
        }

        /// <summary>Per frame from TickSettingsInput, before its gates: a
        /// write, a capture arming, cancelling or expiring repaints the rows
        /// and the pane, whichever path caused it.</summary>
        private static void KeybindPaintTick()
        {
            if (kbRows.Count == 0) return;
            if (kbPaintedRev == Keybinds.Revision && kbPaintedGen == settingsBuildGen && kbPaintedCapture == Keybinds.CaptureRow) return;
            KeybindPaintAll();
            settingsPaneDirty = true;
        }

        /// <summary>The capture poll's place in the settings key ladder,
        /// after the modal, chat and page gates: while it owns input the
        /// page's own key dispatch stands down this frame.</summary>
        private static bool KeybindTakeInput()
        {
            if (!KeybindCaptureSurfaceVisible()) return false;
            if (Keybinds.KeybindCaptureActive) { Keybinds.PollCapture(); KeybindPaintTick(); return true; }
            return Keybinds.CaptureOwnsInput;
        }

        // -- the pane ---------------------------------------------------

        private static bool KeybindRenderPane(SettingsRowRec rec)
        {
            if (rec == null || rec.Kind != SettingsKind.Keybind || rec.KbRow < 0) return false;
            int row = rec.KbRow;
            UIFactory.SetTextNoHook(setDetTitleTxt, KeybindRowLabel(row));
            UIFactory.SetTextNoHook(setDetCurTxt, I18n.TrF("Currently: {0}", KeybindRowFace(row)));
            SettingsSetActive(setDetCurGO, true);
            SettingsSetActive(setDetRecGO, true);
            SettingsSetActive(setDetDetectedGO, false);
            UIFactory.SetTextNoHook(setDetRecTxt, KeybindRowRecommended(row));
            string reason = "";
            if (Keybinds.LastRefusalRow == row && Keybinds.LastRefusal != Refusal.None)
            {
                reason = KeybindRefusalText(Keybinds.LastRefusal);
                if (Keybinds.LastRefusalOther >= 0) reason += " (" + KeybindRowLabel(Keybinds.LastRefusalOther) + ")";
            }
            UIFactory.SetTextNoHook(setDetReasonTxt, reason);
            var sb = new StringBuilder(KeybindRowHelp(row));
            if (row == KeybindRules.QuickChat || row == KeybindRules.DanceWheel)
                sb.Append("\n\n").Append(I18n.Tr("The two wheels cannot take a modifier key."));
            if (Keybinds.CaptureRow == row) sb.Append("\n\n").Append(I18n.Tr("Esc cancels"));
            else if (Keybinds.RowsWritable) sb.Append("\n\n").Append("↺  ").Append(I18n.Tr("Reset this control"));
            if (!Keybinds.RowsWritable)
                sb.Append("\n\n").Append(I18n.Tr("Controls cannot be changed on this game build; every control keeps its default."));
            UIFactory.SetTextNoHook(setDetBodyTxt, sb.ToString());
            SettingsShowExtras(null);
            settingsMoreKey = null;
            SettingsSetActive(setDetMoreBtn, false);
            return true;
        }

        // -- reset all (the footer, design section 2.5) -----------------

        private static void KeybindBuildFooter(Transform foot)
        {
            kbResetArmed = false;
            kbResetAllBtn = UIFactory.CreateButton("SKbResetAll", foot, "Reset all controls", 14f, C_WHITE, C_BTN,
                () => { if (Keybinds.KeybindCaptureActive || !Keybinds.RowsWritable) return; kbResetArmed = true; SettingsRenderPane(); },
                new Vector2(300, 26));
            kbResetAllConfirmBtn = UIFactory.CreateButton("SKbResetAllC", foot, "Confirm", 14f, C_WHITE,
                new Color(0.55f, 0.35f, 0.12f, 0.95f), () =>
                {
                    if (!kbResetArmed) return;
                    kbResetArmed = false;
                    Keybinds.ResetAll();
                    KeybindPaintAll();
                    SettingsRenderPane();
                }, new Vector2(110, 26));
            kbResetAllCancelBtn = UIFactory.CreateButton("SKbResetAllX", foot, "Cancel", 14f, C_LABEL, C_BTN,
                () => { kbResetArmed = false; SettingsRenderPane(); }, new Vector2(100, 26));
            kbResetAllBtn.SetActive(false);
            kbResetAllConfirmBtn.SetActive(false);
            kbResetAllCancelBtn.SetActive(false);
        }

        /// <summary>The footer on the Controls tab: the item-13 per-tab reset
        /// has nothing to write there, so its buttons give way to reset all.
        /// Returns true when the armed prompt owns the pane.</summary>
        private static bool KeybindRenderFooter()
        {
            bool onControls = settingsSubTab == KeybindTabIndex && KeybindTabIndex >= 0;
            if (!onControls) kbResetArmed = false;
            SettingsSetActive(kbResetAllBtn, onControls && !kbResetArmed);
            SettingsSetActive(kbResetAllConfirmBtn, onControls && kbResetArmed);
            SettingsSetActive(kbResetAllCancelBtn, onControls && kbResetArmed);
            if (!onControls) return false;
            SettingsSetActive(setResetBtn, false);
            SettingsSetActive(setResetConfirmBtn, false);
            SettingsSetActive(setResetCancelBtn, false);
            if (!kbResetArmed) return false;
            UIFactory.SetTextNoHook(setDetTitleTxt, I18n.Tr("Controls"));
            SettingsSetActive(setDetCurGO, false);
            SettingsSetActive(setDetRecGO, false);
            SettingsSetActive(setDetDetectedGO, false);
            UIFactory.SetTextNoHook(setDetBodyTxt, I18n.Tr("Reset every control to its default?"));
            SettingsShowExtras(null);
            SettingsSetActive(setDetMoreBtn, false);
            return true;
        }

        // -- the lever (broadcast seat, design T7's driven witness, #420) --

        /// <summary>"5:kb:&lt;verb&gt;[:&lt;arg&gt;][:&lt;nonce&gt;]" through TestOpenTab:
        /// arm:&lt;RowId&gt; arms the row's capture exactly as a click on its
        /// face does; key:&lt;KeyId&gt; and mouse:&lt;n&gt; feed the next capture
        /// poll one press, which then runs the real path (FirstHit,
        /// CaptureGesture, Refuse, Write); reset:&lt;RowId&gt;, resetall,
        /// mutations (the T2 battery) and t3 (the matcher battery).</summary>
        private static bool KeybindDirective(string d)
        {
            if (!d.StartsWith("kb:", StringComparison.OrdinalIgnoreCase)) return false;
            string[] p = d.Substring(3).Split(':');
            string verb = p[0].Trim().ToLowerInvariant();
            string arg = p.Length > 1 ? p[1].Trim() : "";
            int t = KeybindTabIndex;
            if (t >= 0 && settingsSubTab != t) SettingsSwitchSubTab(t);
            int row = Array.FindIndex(KeybindRules.RowIds, id => string.Equals(id, arg, StringComparison.OrdinalIgnoreCase));
            switch (verb)
            {
                case "arm":
                    if (row >= 0 && kbRows.ContainsKey(row)) { SettingsSelectRec(kbRows[row]); KeybindArm(kbRows[row]); }
                    break;
                case "key":
                    Keybinds.DriveKeyRow = KeybindRules.KeyOrdinal(arg);
                    break;
                case "mouse":
                    int n;
                    if (int.TryParse(arg, NumberStyles.Integer, CultureInfo.InvariantCulture, out n) && n >= 0 && n < 7) Keybinds.DriveMouseButton = n;
                    break;
                case "reset":
                    if (row >= 0 && kbRows.ContainsKey(row)) KeybindResetRow(kbRows[row]);
                    break;
                case "resetall":
                    if (Keybinds.RowsWritable && !Keybinds.KeybindCaptureActive) { Keybinds.ResetAll(); KeybindPaintAll(); }
                    break;
                case "mutations":
                    Keybinds.RequestMutationBattery();
                    break;
                case "t3":
                    Keybinds.TranspilerMatcherBattery();
                    break;
                default:
                    Plugin.Log.LogWarning("[KEYBIND] lever: unknown verb '" + verb + "'");
                    return true;
            }
            Plugin.Log.LogInfo("[KEYBIND] lever " + verb + (arg.Length > 0 ? " " + arg : ""));
            settingsPaneDirty = true;
            return true;
        }
    }
}
