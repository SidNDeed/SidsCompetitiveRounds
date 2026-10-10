using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>What a binding is: an InControl Key ordinal, an InControl
    /// Mouse value, or nothing (item 17 design section 2.1).</summary>
    internal enum BindKind { None, Key, Mouse }

    internal struct BindSource : IEquatable<BindSource>
    {
        internal readonly BindKind Kind;
        internal readonly int Value;

        internal BindSource(BindKind kind, int value) { Kind = kind; Value = kind == BindKind.None ? 0 : value; }

        internal static readonly BindSource None = new BindSource(BindKind.None, 0);
        internal static BindSource Key(int keyOrdinal) { return new BindSource(BindKind.Key, keyOrdinal); }
        internal static BindSource Mouse(int mouseValue) { return new BindSource(BindKind.Mouse, mouseValue); }

        public bool Equals(BindSource o) { return Kind == o.Kind && Value == o.Value; }
        public override bool Equals(object o) { return o is BindSource && Equals((BindSource)o); }
        public override int GetHashCode() { return ((int)Kind * 397) ^ Value; }
        public override string ToString() { return KeybindRules.FormatToken(this); }
    }

    /// <summary>Why a check refused a binding (design section 2.6).</summary>
    /// ApplyFailed (fix pass 1 F6): the write was valid but committing it
    /// threw, and every prior state was put back.
    internal enum Refusal { None, Overlap, Reserved, RescueKey, MouseOnModRow, NoneAsBind, TypesText, WheelModifier, ApplyFailed }

    /// <summary>Fix pass 1 F6: where an accepted write lands. Keybinds
    /// implements it over the BepInEx entries and the registered action
    /// sets; the harness with a fake that throws on a chosen step.</summary>
    internal interface IBindStore
    {
        /// <summary>The persisted token of a row.</summary>
        string ReadEntry(int row);
        void WriteEntry(int row, string token);
        /// <summary>Apply the whole set to every live action set; throws on
        /// the first set that fails.</summary>
        void ApplyAll(BindSource[] bound);
    }

    /// <summary>What one capture-poll input means (design section 2.5).</summary>
    internal enum Gesture { Ignore, Bind, Cancel }

    /// <summary>The three-valued result of every input read the achievement
    /// path makes (design section 2.7, METHOD CHANGE 1). Two-valued is what
    /// pays: to a bool read "not pressed" and "could not be read" are the
    /// same false, and only one of them means the player did not act.</summary>
    internal enum Read { Down, Up, Unreadable }

    /// <summary>What one frame's input edges were attributed to by the
    /// ChatChannel tap detector (item 17 fix pass 1, F2). Flags: one frame
    /// can carry a key edge AND a mouse edge, and both are recorded. Unknown
    /// is an edge the platform reported that no KeyCode names - it is never
    /// read as the mouse.</summary>
    [Flags]
    internal enum EdgeAttribution { None = 0, Alias = 1, Key = 2, Mouse = 4, Unknown = 8 }

    /// <summary>One frame of physical input, so the tap detector runs on the
    /// real stream in production (Keybinds) and on a scripted one in the
    /// harness and in T2 case j.</summary>
    internal interface IFrameInput
    {
        /// <summary>The KeyCode ordinal went down this frame (Input.GetKeyDown).
        /// Mouse buttons are KeyCode.Mouse0-Mouse6 (323-329).</summary>
        bool KeyDown(int code);
        bool KeyUp(int code);
        /// <summary>Input.anyKeyDown: some key or button went down.</summary>
        bool AnyKeyDown();
        /// <summary>Input.inputString: the text this frame's keys typed. A
        /// second, independent keyboard channel: it carries characters from
        /// keys no KeyCode names.</summary>
        string TypedText();
        /// <summary>Held mouse state; read only by mutation 23 (revision 3's
        /// held-button shape).</summary>
        bool AnyMouseHeld();
        float Now();
        bool Focused();
        /// <summary>Fix pass 2 (M1): how many keyboard keys went down this
        /// frame according to a source that is independent of the KeyCode
        /// table, of the mouse and of the typed text (production: the game
        /// thread's own keyboard state, read once a frame and latched against
        /// the previous frame's read, Keybinds.KeyboardEdgeLatch). Mouse
        /// buttons are never counted. -1 when that source cannot be read.</summary>
        int KeyboardEdges();
    }

    /// <summary>
    /// Item 17 (v1.41.0, the keybind system): every decision the keybind
    /// system makes that needs no Unity, so tools/client-rules-harness can
    /// EXECUTE it (#391). The plugin calls these functions; it keeps no second
    /// copy of any of them (T4's static half). The key table is transcribed
    /// from InControl's UnityKeyboardProvider.KeyMappings literal on the live
    /// install; at run time Keybinds validates the reflected table against
    /// it (design section 2.1a, T2 case i).
    /// </summary>
    internal static class KeybindRules
    {
        // -- the sixteen rows (design section 2.2) -------------------------
        internal const int RowCount = 16;
        internal const int MenuToggle = 0, Scoreboard = 1, QuickChat = 2, DanceWheel = 3, ChatOpen = 4,
                           ChatChannel = 5, ChatOverlayMode = 6, MapSkinCycle = 7, AvatarSwap = 8,
                           MoveUp = 9, MoveDown = 10, MoveLeft = 11, MoveRight = 12, Jump = 13,
                           Fire = 14, Block = 15;
        internal const int FirstGameRow = 9;

        /// <summary>The config key of each row (section "Controls").</summary>
        internal static readonly string[] RowIds =
        {
            "MenuToggle", "Scoreboard", "QuickChat", "DanceWheel", "ChatOpen", "ChatChannel",
            "ChatOverlayMode", "MapSkinCycle", "AvatarSwap", "MoveUp", "MoveDown", "MoveLeft",
            "MoveRight", "Jump", "Fire", "Block",
        };

        /// <summary>The sixteen defaults, today's keys exactly (design
        /// section 2.8). MapSkinCycle narrows to left shift (question 8).</summary>
        private static readonly string[] DefaultTokens =
        {
            "key:F5", "key:Tab", "key:Q", "key:E", "key:T", "key:Alt", "key:M", "key:LeftShift", "none",
            "key:W", "key:S", "key:A", "key:D", "key:Space", "mouse:LeftButton", "mouse:RightButton",
        };

        /// <summary>The same sixteen defaults spelled as KeyCode ordinals, the
        /// fallback every reader resolves to while the mapping accessor is
        /// not validated (design section 2.1a). The two mouse rows need no
        /// table. Case 11 proves these equal the token table's codes.</summary>
        internal static readonly int[][] StaticDefaults =
        {
            new[] { 286 },          // F5
            new[] { 9 },            // Tab
            new[] { 113 },          // Q
            new[] { 101 },          // E
            new[] { 116 },          // T
            new[] { 308, 307 },     // LeftAlt, RightAlt
            new[] { 109 },          // M
            new[] { 304 },          // LeftShift
            new int[0],             // AvatarSwap: unbound
            new[] { 119 },          // W
            new[] { 115 },          // S
            new[] { 97 },           // A
            new[] { 100 },          // D
            new[] { 32 },           // Space
            new int[0],             // Fire: mouse:LeftButton
            new int[0],             // Block: mouse:RightButton
        };

        internal static bool IsGameRow(int row) { return row >= FirstGameRow && row < RowCount; }
        internal static bool IsModRow(int row) { return row >= 0 && row < FirstGameRow; }

        // -- the key table, transcribed from UnityKeyboardProvider.KeyMappings
        // (132 rows, index == InControl.Key ordinal; KeyCode ordinals) -------
        internal const int KeyTableLength = 132;

        internal static readonly string[] KeyIds =
        {
            "None", "Shift", "Alt", "Command", "Control", "LeftShift", "LeftAlt", "LeftCommand",
            "LeftControl", "RightShift", "RightAlt", "RightCommand", "RightControl", "Escape", "F1", "F2",
            "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10",
            "F11", "F12", "Key0", "Key1", "Key2", "Key3", "Key4", "Key5",
            "Key6", "Key7", "Key8", "Key9", "A", "B", "C", "D",
            "E", "F", "G", "H", "I", "J", "K", "L",
            "M", "N", "O", "P", "Q", "R", "S", "T",
            "U", "V", "W", "X", "Y", "Z", "Backquote", "Minus",
            "Equals", "Backspace", "Tab", "LeftBracket", "RightBracket", "Backslash", "Semicolon", "Quote",
            "Return", "Comma", "Period", "Slash", "Space", "Insert", "Delete", "Home",
            "End", "PageUp", "PageDown", "LeftArrow", "RightArrow", "UpArrow", "DownArrow", "Pad0",
            "Pad1", "Pad2", "Pad3", "Pad4", "Pad5", "Pad6", "Pad7", "Pad8",
            "Pad9", "Numlock", "PadDivide", "PadMultiply", "PadMinus", "PadPlus", "PadEnter", "PadPeriod",
            "Clear", "PadEquals", "F13", "F14", "F15", "AltGr", "CapsLock", "ExclamationMark",
            "Tilde", "At", "Hash", "Dollar", "Percent", "Caret", "Ampersand", "Asterisk",
            "LeftParen", "RightParen", "Underscore", "Plus", "LeftBrace", "RightBrace", "Pipe", "Colon",
            "DoubleQuote", "LessThan", "GreaterThan", "QuestionMark",
        };

        internal static readonly int[] KeyCode0 =
        {
            0, 304, 308, 310, 306, 304, 308, 310, 306, 303, 307, 309, 305, 27, 282, 283,
            284, 285, 286, 287, 288, 289, 290, 291, 292, 293, 48, 49, 50, 51, 52, 53,
            54, 55, 56, 57, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108,
            109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 96, 45,
            61, 8, 9, 91, 93, 92, 59, 39, 13, 44, 46, 47, 32, 277, 127, 278,
            279, 280, 281, 276, 275, 273, 274, 256, 257, 258, 259, 260, 261, 262, 263, 264,
            265, 300, 267, 268, 269, 270, 271, 266, 12, 272, 294, 295, 296, 313, 301, 33,
            126, 64, 35, 36, 37, 94, 38, 42, 40, 41, 95, 43, 123, 125, 124, 58,
            34, 60, 62, 63,
        };

        /// <summary>The second target of the four aggregate rows (Shift, Alt,
        /// Command, Control); 0 everywhere else.</summary>
        internal static readonly int[] KeyCode1 = BuildKeyCode1();

        private static int[] BuildKeyCode1()
        {
            var a = new int[KeyTableLength];
            a[1] = 303;   // Shift   -> RightShift
            a[2] = 307;   // Alt     -> RightAlt
            a[3] = 309;   // Command -> RightMeta
            a[4] = 305;   // Control -> RightControl
            return a;
        }

        /// <summary>InControl.Mouse member names, by value (Mouse.cs:5-20).</summary>
        internal static readonly string[] MouseIds =
        {
            "None", "LeftButton", "RightButton", "MiddleButton", "NegativeX", "PositiveX", "NegativeY",
            "PositiveY", "PositiveScrollWheel", "NegativeScrollWheel", "Button4", "Button5", "Button6", "Button7",
        };

        /// <summary>Unity GetMouseButton(n) for n = 0..6 to InControl.Mouse:
        /// the enum is SPARSE (UnityMouseProvider.cs:42-48), so (Mouse)(n + 1)
        /// would bind button 3 to NegativeX (design section 2.5 property 5).</summary>
        private static readonly int[] UnityToMouse = { 1, 2, 3, 10, 11, 12, 13 };

        /// <summary>Mutation selector for the harness and the in-game
        /// self-test. Always 0 outside a self-test run.</summary>
        internal static int Mut;

        private static readonly Dictionary<string, int> keyIndex = BuildKeyIndex();
        private static Dictionary<string, int> BuildKeyIndex()
        {
            var d = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < KeyIds.Length; i++) d[KeyIds[i]] = i;
            return d;
        }

        internal static int KeyOrdinal(string id)
        {
            int i;
            return id != null && keyIndex.TryGetValue(id, out i) ? i : -1;
        }

        internal static readonly int KeyEscape = KeyOrdinal("Escape"), KeyReturn = KeyOrdinal("Return"),
                                     KeyPadEnter = KeyOrdinal("PadEnter"), KeyF5 = KeyOrdinal("F5"),
                                     KeySpace = KeyOrdinal("Space"), KeyBackspace = KeyOrdinal("Backspace"),
                                     KeyDelete = KeyOrdinal("Delete");
        internal const int CodeF5 = 286;

        /// <summary>The KeyCode ordinals one Key row names: 0, 1 or 2 codes.</summary>
        internal static int[] StaticCodesForKey(int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeyTableLength) return new int[0];
            int a = KeyCode0[keyOrdinal], b = KeyCode1[keyOrdinal];
            if (a == 0) return new int[0];
            return b == 0 ? new[] { a } : new[] { a, b };
        }

        /// <summary>Every distinct KeyCode the table names, KeyCode.None
        /// excluded: 127. The four aggregate rows re-name the eight
        /// side-specific codes their own rows already name, so 131 rows give
        /// 127 codes (design section 2.1a, r3 R4).</summary>
        internal static int[] StaticKeyScan { get { return BuildStaticKeyScan(Mut == 108); } }
        private static int[] scanCache;
        private static int[] BuildStaticKeyScan(bool byRow)
        {
            if (!byRow && scanCache != null) return scanCache;
            var seen = new HashSet<int>();
            var list = new List<int>();
            for (int i = 1; i < KeyTableLength; i++)
                foreach (int c in StaticCodesForKey(i))
                    if (byRow || seen.Add(c)) list.Add(c);
            var arr = list.ToArray();
            if (!byRow) scanCache = arr;
            return arr;
        }

        // -- tokens ----------------------------------------------------------

        internal static string FormatToken(BindSource s)
        {
            switch (s.Kind)
            {
                case BindKind.Key:
                    return s.Value > 0 && s.Value < KeyTableLength ? "key:" + KeyIds[s.Value] : "none";
                case BindKind.Mouse:
                    return s.Value > 0 && s.Value < MouseIds.Length ? "mouse:" + MouseIds[s.Value] : "none";
                default:
                    return "none";
            }
        }

        /// <summary>A config string to a source. False for anything that is
        /// not a token this table can name; the loader then keeps the row's
        /// default (a corrupt line never throws and never unbinds).</summary>
        internal static bool ParseToken(string token, out BindSource src)
        {
            src = BindSource.None;
            if (Mut == 5 && token != null && token.StartsWith("bogus", StringComparison.Ordinal))
                throw new FormatException("mutation 5: the parser throws on an unknown token");
            if (token == null) return false;
            string t = token.Trim();
            if (string.Equals(t, "none", StringComparison.OrdinalIgnoreCase)) return true;
            int colon = t.IndexOf(':');
            if (colon <= 0) return false;
            string kind = t.Substring(0, colon).Trim(), name = t.Substring(colon + 1).Trim();
            if (string.Equals(kind, "key", StringComparison.OrdinalIgnoreCase))
            {
                int k = KeyOrdinal(name);
                if (k <= 0) return false;
                src = BindSource.Key(k);
                return true;
            }
            if (string.Equals(kind, "mouse", StringComparison.OrdinalIgnoreCase))
            {
                for (int i = 0; i < UnityToMouse.Length; i++)
                    if (string.Equals(MouseIds[UnityToMouse[i]], name, StringComparison.OrdinalIgnoreCase))
                    {
                        src = BindSource.Mouse(UnityToMouse[i]);
                        return true;
                    }
                return false;
            }
            return false;
        }

        internal static string DefaultToken(int row)
        {
            if (Mut == 11 && row == MapSkinCycle) return "key:Shift";
            return row >= 0 && row < RowCount ? DefaultTokens[row] : "none";
        }

        internal static BindSource Default(int row)
        {
            BindSource s;
            return ParseToken(DefaultToken(row), out s) ? s : BindSource.None;
        }

        /// <summary>The loader's rule: a token that parses is the binding,
        /// anything else falls back to the row's default.</summary>
        internal static BindSource LoadToken(int row, string token)
        {
            BindSource s;
            try { if (ParseToken(token, out s)) return s; }
            catch (Exception) { if (Mut == 5) throw; }
            return Default(row);
        }

        // -- mouse -------------------------------------------------------------

        /// <summary>Unity button n (0..6) to its InControl.Mouse source;
        /// None outside the range.</summary>
        internal static BindSource MouseIndexToSource(int unityIndex)
        {
            if (unityIndex < 0 || unityIndex >= UnityToMouse.Length) return BindSource.None;
            if (Mut == 9) return BindSource.Mouse(unityIndex + 1);
            return BindSource.Mouse(UnityToMouse[unityIndex]);
        }

        /// <summary>The reverse: the Unity button a Mouse value is read
        /// through, or -1.</summary>
        internal static int MouseSourceToUnityIndex(int mouseValue)
        {
            for (int i = 0; i < UnityToMouse.Length; i++) if (UnityToMouse[i] == mouseValue) return i;
            return -1;
        }

        /// <summary>One guarded mouse read in UnityMouseProvider.SafeGetMouseButton's
        /// shape (UnityMouseProvider.cs:60-74): a button at or above the cap
        /// is Unreadable for the rest of the process, and an ArgumentException
        /// from the raw read lowers the cap. Never throws (Mut 13 makes a
        /// capped button read Up instead, the shape case 13 must red on).</summary>
        internal static Read GuardedMouseRead(int button, ref int cap, Func<int, bool> raw, Action<int> onCapped)
        {
            if (button < 0) return Read.Unreadable;
            if (button >= cap) return Mut == 13 ? Read.Up : Read.Unreadable;
            try { return raw(button) ? Read.Down : Read.Up; }
            catch (ArgumentException)
            {
                if (button < cap) { cap = button; if (onCapped != null) { try { onCapped(button); } catch { } } }
                return Mut == 13 ? Read.Up : Read.Unreadable;
            }
            catch (Exception) { return Read.Unreadable; }
        }

        /// <summary>True when the row's bound mouse button sits at or above the cap.</summary>
        internal static bool MouseUnreadable(BindSource s, int cap)
        {
            if (s.Kind != BindKind.Mouse) return false;
            int n = MouseSourceToUnityIndex(s.Value);
            if (Mut == 13) return false;
            return n < 0 || n >= cap;
        }

        // -- overlap and refusal (design section 2.6) ------------------------

        /// <summary>Two sources conflict when their KeyCode sets intersect or
        /// they carry the same mouse value. The KeyCode set, never Key
        /// equality: Shift and LeftShift are two values and one physical key.</summary>
        internal static bool Overlap(BindSource a, BindSource b, Func<int, int[]> codesFor)
        {
            if (a.Kind == BindKind.None || b.Kind == BindKind.None) return false;
            if (a.Kind == BindKind.Mouse && b.Kind == BindKind.Mouse) return Mut != 7 && a.Value == b.Value;
            if (a.Kind != BindKind.Key || b.Kind != BindKind.Key) return false;
            if (Mut == 1) return a.Value == b.Value;
            var ca = (codesFor ?? StaticCodesForKey)(a.Value);
            var cb = (codesFor ?? StaticCodesForKey)(b.Value);
            foreach (int x in ca) foreach (int y in cb) if (x == y && x != 0) return true;
            return false;
        }

        /// <summary>The first OTHER row whose binding conflicts, or -1.</summary>
        internal static int OverlapRow(int row, BindSource src, BindSource[] current, Func<int, int[]> codesFor)
        {
            if (current == null) return -1;
            for (int r = 0; r < current.Length && r < RowCount; r++)
                if (r != row && Overlap(src, current[r], codesFor)) return r;
            return -1;
        }

        private static bool CodesContain(BindSource s, int code, Func<int, int[]> codesFor)
        {
            if (s.Kind != BindKind.Key) return false;
            foreach (int c in (codesFor ?? StaticCodesForKey)(s.Value)) if (c == code) return true;
            return false;
        }

        /// <summary>Rule 6's set: a key that CHANGES THE TEXT in the chat box
        /// - by putting a character in or by taking one out - and is not
        /// consumed by the box first. 68 glyph keys, 16 numpad value keys,
        /// Space, Backspace and Delete: 87.</summary>
        internal static bool IsTextChanging(int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeyTableLength) return false;
            string id = KeyIds[keyOrdinal];
            if (IsGlyphKey(keyOrdinal) || IsNumpadValueKey(id)) return true;
            if (Mut == 14) return false;                                   // revision 2's rendering-arm classifier
            if (keyOrdinal == KeySpace) return true;
            if (keyOrdinal == KeyBackspace) return Mut != 15 && Mut != 17;
            if (keyOrdinal == KeyDelete) return Mut != 17;
            return false;
        }

        private static bool IsNumpadValueKey(string id)
        {
            switch (id)
            {
                case "Pad0": case "Pad1": case "Pad2": case "Pad3": case "Pad4":
                case "Pad5": case "Pad6": case "Pad7": case "Pad8": case "Pad9":
                case "PadDivide": case "PadMultiply": case "PadMinus": case "PadPlus":
                case "PadPeriod": case "PadEquals":
                    return true;
            }
            return false;
        }

        private static readonly HashSet<int> ModifierCodes = new HashSet<int> { 303, 304, 305, 306, 307, 308, 309, 310, 313 };

        /// <summary>A key every code of which is a modifier (either Shift,
        /// Alt, Control, Command or AltGr).</summary>
        internal static bool IsModifierKey(int keyOrdinal, Func<int, int[]> codesFor)
        {
            var codes = (codesFor ?? StaticCodesForKey)(keyOrdinal);
            if (codes.Length == 0) return false;
            foreach (int c in codes) if (!ModifierCodes.Contains(c)) return false;
            return true;
        }

        /// <summary>The whole check, in rule order. <paramref name="other"/>
        /// names the row that already holds the source on an overlap.</summary>
        internal static Refusal Refuse(int row, BindSource src, BindSource[] current, Func<int, int[]> codesFor, out int other)
        {
            other = -1;
            if (src.Kind == BindKind.None) return Refusal.NoneAsBind;                                  // rule 5
            if (src.Kind == BindKind.Mouse)
            {
                if (IsModRow(row) && !(Mut == 6 && row == ChatOpen)) return Refusal.MouseOnModRow;     // rule 4
                if (MouseSourceToUnityIndex(src.Value) < 0) return Refusal.NoneAsBind;
            }
            if (src.Kind == BindKind.Key)
            {
                if (src.Value <= 0 || src.Value >= KeyTableLength) return Refusal.NoneAsBind;
                if ((src.Value == KeyEscape && Mut != 2) || (src.Value == KeyReturn && Mut != 3) || src.Value == KeyPadEnter)
                    return Refusal.Reserved;                                                             // rule 2
                if (row != MenuToggle && CodesContain(src, CodeF5, codesFor) && !(Mut == 4 && row == Scoreboard))
                    return Refusal.RescueKey;                                                            // rule 3
                if (row == ChatChannel && Mut != 8 && IsTextChanging(src.Value)) return Refusal.TypesText;   // rule 6
                if ((row == QuickChat || row == DanceWheel) && IsModifierKey(src.Value, codesFor))
                    return Refusal.WheelModifier;                                                        // question 6
            }
            other = OverlapRow(row, src, current, codesFor);                                             // rule 1
            return other >= 0 ? Refusal.Overlap : Refusal.None;
        }

        /// <summary>Fix pass 1 F5: the loaded config made a conflict-free
        /// effective set. Rows are taken in row order, each checked against
        /// the rows already RETAINED (later rows are not yet in force). A row
        /// the rules refuse falls back to its default, and the default is
        /// checked against the retained rows the same way; a default they
        /// refuse too leaves the row unbound, so one key never drives two
        /// rows. <paramref name="notes"/> receives one line per row changed.</summary>
        internal static BindSource[] ResolveLoaded(BindSource[] parsed, Func<int, int[]> codesFor, List<string> notes)
        {
            var eff = new BindSource[RowCount];
            if (Mut == 20)
            {
                // a22f80ed: every row checked against the whole parsed set, the
                // fallback default written unchecked into the same array.
                for (int i = 0; i < RowCount; i++) eff[i] = parsed != null && i < parsed.Length ? parsed[i] : Default(i);
                for (int i = 0; i < RowCount; i++)
                {
                    if (eff[i].Kind == BindKind.None) continue;
                    int o;
                    if (Refuse(i, eff[i], eff, codesFor, out o) != Refusal.None) eff[i] = Default(i);
                }
                return eff;
            }
            for (int i = 0; i < RowCount; i++)
            {
                var cand = parsed != null && i < parsed.Length ? parsed[i] : Default(i);
                if (cand.Kind == BindKind.None) { eff[i] = cand; continue; }
                int other;
                var r = Refuse(i, cand, eff, codesFor, out other);
                if (r == Refusal.None) { eff[i] = cand; continue; }
                string why = FormatToken(cand) + " refused (" + r + (other >= 0 ? " with " + RowIds[other] : "") + ")";
                var d = Default(i);
                int otherD = -1;
                Refusal rd;
                if (d.Kind == BindKind.None) rd = Refusal.None;
                else if (d.Equals(cand)) { rd = r; otherD = other; }
                else rd = Refuse(i, d, eff, codesFor, out otherD);
                if (rd == Refusal.None)
                {
                    eff[i] = d;
                    if (notes != null) notes.Add(RowIds[i] + ": " + why + "; default " + FormatToken(d) + " kept");
                }
                else
                {
                    eff[i] = BindSource.None;
                    if (notes != null) notes.Add(RowIds[i] + ": " + why + "; default " + FormatToken(d) + " refused too ("
                                                 + rd + (otherD >= 0 ? " with " + RowIds[otherD] : "") + "); unbound");
                }
            }
            return eff;
        }

        /// <summary>Fix pass 1 F6: one accepted write or reset, all or nothing.
        /// The rows are written into <paramref name="bound"/> (the registry),
        /// persisted, then applied to every live set. If any step throws,
        /// every registry row, every persisted entry the commit touched and
        /// every live set are put back as they were and false is returned;
        /// <paramref name="failure"/> names what threw (and a restore step
        /// that threw too).</summary>
        internal static bool Commit(BindSource[] bound, int[] rows, BindSource[] values, IBindStore store, out string failure)
        {
            failure = null;
            var before = (BindSource[])bound.Clone();
            var tokens = new string[rows.Length];
            for (int k = 0; k < rows.Length; k++)
            {
                try { tokens[k] = store.ReadEntry(rows[k]); }
                catch { tokens[k] = FormatToken(before[rows[k]]); }
            }
            try
            {
                for (int k = 0; k < rows.Length; k++) bound[rows[k]] = values[k];
                for (int k = 0; k < rows.Length; k++) store.WriteEntry(rows[k], FormatToken(values[k]));
                store.ApplyAll(bound);
                return true;
            }
            catch (Exception e)
            {
                failure = e.GetType().Name + ": " + e.Message;
                if (Mut == 21) return true;   // a22f80ed: each step's own catch, success reported, nothing put back
                Array.Copy(before, bound, bound.Length);
                for (int k = 0; k < rows.Length; k++)
                {
                    try { store.WriteEntry(rows[k], tokens[k]); }
                    catch (Exception e2) { failure += "; restoring " + RowIds[rows[k]] + ": " + e2.Message; }
                }
                try { store.ApplyAll(bound); }
                catch (Exception e3) { failure += "; restoring the live sets: " + e3.Message; }
                return false;
            }
        }

        /// <summary>True when no two rows of the set conflict and every bound
        /// row passes every rule against the rest (the effective-set invariant).</summary>
        internal static bool ConflictFree(BindSource[] set, Func<int, int[]> codesFor)
        {
            if (set == null || set.Length != RowCount) return false;
            for (int i = 0; i < RowCount; i++)
            {
                if (set[i].Kind == BindKind.None) continue;
                int o;
                if (Refuse(i, set[i], set, codesFor, out o) != Refusal.None) return false;
            }
            return true;
        }

        // -- the keyboard guide (fix pass 1 F4) ------------------------------

        internal const int BoardMod = 1, BoardGame = 2;

        /// <summary>The Controls guide's board: each cap's id (its English
        /// face), the KeyCodes it stands for, and the role it has whatever the
        /// bindings are (Escape closes this menu and then the game's, Enter is
        /// the room code box and vanilla chat, B adds a practice bot in a
        /// lobby, F5 always opens this menu). Everything else is coloured by
        /// the rows bound to it NOW.</summary>
        private static readonly object[][] BoardCaps =
        {
            new object[] { "ESC", new[] { 27 }, BoardMod | BoardGame },
            new object[] { "F1", new[] { 282 }, 0 }, new object[] { "F2", new[] { 283 }, 0 },
            new object[] { "F3", new[] { 284 }, 0 }, new object[] { "F4", new[] { 285 }, 0 },
            new object[] { "F5", new[] { 286 }, BoardMod }, new object[] { "F6", new[] { 287 }, 0 },
            new object[] { "F7", new[] { 288 }, 0 }, new object[] { "F8", new[] { 289 }, 0 },
            new object[] { "`", new[] { 96 }, 0 },
            new object[] { "1", new[] { 49 }, 0 }, new object[] { "2", new[] { 50 }, 0 }, new object[] { "3", new[] { 51 }, 0 },
            new object[] { "4", new[] { 52 }, 0 }, new object[] { "5", new[] { 53 }, 0 }, new object[] { "6", new[] { 54 }, 0 },
            new object[] { "7", new[] { 55 }, 0 }, new object[] { "8", new[] { 56 }, 0 }, new object[] { "9", new[] { 57 }, 0 },
            new object[] { "0", new[] { 48 }, 0 },
            new object[] { "TAB", new[] { 9 }, 0 },
            new object[] { "Q", new[] { 113 }, 0 }, new object[] { "W", new[] { 119 }, 0 }, new object[] { "E", new[] { 101 }, 0 },
            new object[] { "R", new[] { 114 }, 0 }, new object[] { "T", new[] { 116 }, 0 }, new object[] { "Y", new[] { 121 }, 0 },
            new object[] { "U", new[] { 117 }, 0 }, new object[] { "I", new[] { 105 }, 0 }, new object[] { "O", new[] { 111 }, 0 },
            new object[] { "P", new[] { 112 }, 0 },
            new object[] { "CAPS", new[] { 301 }, 0 },
            new object[] { "A", new[] { 97 }, 0 }, new object[] { "S", new[] { 115 }, 0 }, new object[] { "D", new[] { 100 }, 0 },
            new object[] { "F", new[] { 102 }, 0 }, new object[] { "G", new[] { 103 }, 0 }, new object[] { "H", new[] { 104 }, 0 },
            new object[] { "J", new[] { 106 }, 0 }, new object[] { "K", new[] { 107 }, 0 }, new object[] { "L", new[] { 108 }, 0 },
            new object[] { "ENTER", new[] { 13 }, BoardGame },
            new object[] { "SHIFT", new[] { 304 }, 0 },
            new object[] { "Z", new[] { 122 }, 0 }, new object[] { "X", new[] { 120 }, 0 }, new object[] { "C", new[] { 99 }, 0 },
            new object[] { "V", new[] { 118 }, 0 }, new object[] { "B", new[] { 98 }, BoardGame }, new object[] { "N", new[] { 110 }, 0 },
            new object[] { "M", new[] { 109 }, 0 },
            new object[] { "SPACE", new[] { 32 }, 0 },
            new object[] { "ALT", new[] { 308 }, 0 },
            new object[] { "LMB", new[] { KeyCodeMouse0 }, 0 },
            new object[] { "RMB", new[] { KeyCodeMouse0 + 1 }, 0 },
        };

        internal static int BoardCapCount { get { return BoardCaps.Length; } }
        internal static string BoardCapId(int i) { return (string)BoardCaps[i][0]; }

        /// <summary>The KeyCodes a bound source stands for: a key's table
        /// codes, a mouse button's Mouse0+index, nothing for unbound.</summary>
        internal static int[] SourceCodes(BindSource s, Func<int, int[]> codesFor)
        {
            if (s.Kind == BindKind.Key) return (codesFor ?? StaticCodesForKey)(s.Value);
            if (s.Kind == BindKind.Mouse)
            {
                int u = MouseSourceToUnityIndex(s.Value);
                return u >= 0 ? new[] { KeyCodeMouse0 + u } : new int[0];
            }
            return new int[0];
        }

        /// <summary>Fix pass 1 F4: a board cap's role under <paramref name="set"/>
        /// - BoardMod when a mod row is bound to it, BoardGame when a game row
        /// is, both bits for both, plus its fixed role; -1 for an id the board
        /// does not carry. Mutation 24 is a22f80ed's board, whose colours were
        /// the defaults' whatever the player bound.</summary>
        internal static int BoardCapRole(string id, BindSource[] set, Func<int, int[]> codesFor)
        {
            int at = -1;
            for (int i = 0; i < BoardCaps.Length; i++) if ((string)BoardCaps[i][0] == id) { at = i; break; }
            if (at < 0) return -1;
            var caps = (int[])BoardCaps[at][1];
            int role = (int)BoardCaps[at][2];
            var use = Mut == 24 || set == null ? Defaults() : set;
            for (int r = 0; r < RowCount && r < use.Length; r++)
            {
                foreach (int c in SourceCodes(use[r], codesFor))
                    if (Array.IndexOf(caps, c) >= 0) { role |= IsModRow(r) ? BoardMod : BoardGame; break; }
            }
            return role;
        }

        // -- capture (design section 2.5) ------------------------------------

        /// <summary>One capture-poll input, as the KeyMappings row of the key
        /// that went down (-1: none). Escape cancels; every other key binds;
        /// unbind is the _x control's job and nothing else's.</summary>
        internal static Gesture CaptureGesture(int row, bool armed)
        {
            if (!armed || row <= 0) return Gesture.Ignore;
            if (row == KeyEscape) return Gesture.Cancel;
            if (Mut == 10 && row == KeyBackspace) return Gesture.Cancel;
            return Gesture.Bind;
        }

        /// <summary>Fix pass 1 F7: the capture poll reads the mouse for EVERY
        /// armed row. A mouse press on a mod-control row then goes the one
        /// write path, Refuse answers MouseOnModRow (rule 4), the capture
        /// ends and the refusal shows; only a game-control row can save the
        /// source. Mutation 22 is a22f80ed's poll, which skipped the mouse
        /// for a mod row, so capture stayed armed and nothing was shown.</summary>
        internal static bool CaptureTakesMouse(int row)
        {
            if (row < 0 || row >= RowCount) return false;
            if (Mut == 22) return IsGameRow(row);
            return true;
        }

        /// <summary>The detection order: the LOWEST KeyMappings row among the
        /// rows whose key is down, so a physical left shift captures as
        /// Key.Shift (row 1), never Key.LeftShift (row 5). -1 for none.</summary>
        internal static int FirstHit(int[] rowsDown)
        {
            if (rowsDown == null) return -1;
            int best = -1;
            foreach (int r in rowsDown)
            {
                if (r <= 0 || r >= KeyTableLength) continue;
                if (best < 0) best = r;
                else if (Mut == 12 ? r > best : r < best) best = r;
            }
            return best;
        }

        /// <summary>The ready prompts say SPACE; they are rewritten only when
        /// Jump does not hold key:Space (design section 2.4, T8). A mouse-bound
        /// or unbound Jump cannot be described by the word SPACE either.</summary>
        internal static bool ShouldOverrideReadyPrompt(BindSource jump)
        {
            if (Mut == 16) return false;
            return !(jump.Kind == BindKind.Key && jump.Value == KeySpace);
        }

        // -- the ChatChannel tap detector (design section 2.5, fix pass 1 F2) --

        /// <summary>Unity's KeyCode.Mouse0 and KeyCode.Mouse6: the seven mouse
        /// buttons are KeyCodes too, so one scan of the KeyCode members sees a
        /// keyboard edge and a mouse edge in the same frame, each by identity.</summary>
        internal const int KeyCodeMouse0 = 323, KeyCodeMouse6 = 329;

        internal static bool IsMouseCode(int code) { return code >= KeyCodeMouse0 && code <= KeyCodeMouse6; }

        /// <summary>A keyboard KeyCode: below Mouse0. The joystick buttons
        /// (330 and up) and the mouse buttons are not keyboard keys, so the
        /// independent keyboard-edge source never counts them.</summary>
        internal static bool IsKeyboardCode(int code) { return code > 0 && code < KeyCodeMouse0; }

        /// <summary>The tap detector's state machine. Unity-free: production
        /// feeds it Keybinds' real input, the harness a scripted one.</summary>
        internal sealed class TapDetector
        {
            internal bool Held, Clean;
            internal float DownAt;
            /// <summary>What the most recent Step attributed its edges to.</summary>
            internal EdgeAttribution Last;

            /// <summary>One frame's attribution. Every code of
            /// <paramref name="scan"/> (production: every KeyCode member, the
            /// keys Unity's input can report) that went down is named: an alias
            /// code is Alias, Mouse0-Mouse6 is Mouse, anything else is Key. Text
            /// typed this frame that no named key accounts for is Unknown (the
            /// alias types nothing, rule 6), and so is an edge Input.anyKeyDown
            /// reports that nothing names. Fix pass 2 (M1): the independent
            /// keyboard-edge source (IFrameInput.KeyboardEdges) is compared with
            /// the keyboard keys the KeyCodes named this frame; more keyboard
            /// edges than named keys is Unknown whatever the mouse did in the
            /// frame, and an unreadable source beside a mouse edge is Unknown
            /// too. Unknown is never read as the mouse.</summary>
            internal static EdgeAttribution Attribute(IFrameInput io, int[] alias, int[] scan)
            {
                var a = EdgeAttribution.None;
                var aliasSet = new HashSet<int>(alias ?? new int[0]);
                int named = 0;   // keyboard keys a KeyCode named this frame, the alias's included
                foreach (int c in aliasSet)
                    if (c > 0 && io.KeyDown(c)) { a |= EdgeAttribution.Alias; if (IsKeyboardCode(c)) named++; }
                bool any = io.AnyKeyDown();
                string text = io.TypedText();
                bool typed = !string.IsNullOrEmpty(text);
                // M1: read before the early return - a key no KeyCode names can
                // leave anyKeyDown and the typed text both empty. Mutation 25 is
                // the 2811a621 detector (no independent source); mutation 18 is
                // the a22f80ed one, which had none either.
                int kb = Mut == 25 || Mut == 18 ? 0 : io.KeyboardEdges();
                if (!any && !typed && kb <= 0) return a;
                // Mutation 18 restores the a22f80ed observation: the scan saw only
                // InControl's 127 codes and a mouse edge was a separate yes/no.
                HashSet<int> legacy = Mut == 18 ? new HashSet<int>(StaticKeyScan) : null;
                if (scan != null)
                    foreach (int c in scan)
                    {
                        if (c <= 0 || aliasSet.Contains(c)) continue;
                        if (legacy != null && !IsMouseCode(c) && !legacy.Contains(c)) continue;
                        if (!io.KeyDown(c)) continue;
                        a |= IsMouseCode(c) ? EdgeAttribution.Mouse : EdgeAttribution.Key;
                        if (IsKeyboardCode(c)) named++;
                    }
                if (typed && (a & EdgeAttribution.Key) == 0 && Mut != 18) a |= EdgeAttribution.Unknown;
                if (any && (a & (EdgeAttribution.Alias | EdgeAttribution.Key | EdgeAttribution.Mouse)) == 0) a |= EdgeAttribution.Unknown;
                // M1: a keyboard edge no KeyCode named - beside a click or not.
                if (kb > named) a |= EdgeAttribution.Unknown;
                // M1: the independent source cannot be read, so a frame with a
                // mouse edge may hide a keyboard edge: never mouse-only.
                if (kb < 0 && (a & EdgeAttribution.Mouse) != 0) a |= EdgeAttribution.Unknown;
                // a22f80ed: an edge nothing named, beside a same-frame mouse edge, read as mouse-only.
                if (Mut == 18 && (a & EdgeAttribution.Mouse) != 0) a &= ~EdgeAttribution.Unknown;
                // revision 3: a held button (not an edge) made the unnamed edge the mouse's.
                if ((Mut == 23 || Mut == 107) && (a & EdgeAttribution.Unknown) != 0 && io.AnyMouseHeld()) a = (a & ~EdgeAttribution.Unknown) | EdgeAttribution.Mouse;
                return a;
            }

            /// <summary>One frame. True on the release that is a clean tap: the
            /// alias went down and up within 0.6 s and no frame in between, nor
            /// the arming frame, carried a Key or an Unknown edge. A Mouse edge
            /// alone keeps the tap (a click while holding the key); a Key edge
            /// beside a Mouse edge is attributed to both and disarms.</summary>
            internal bool Step(IFrameInput io, int[] alias, int[] scan)
            {
                bool fire = false, aliasUp = false;
                if (alias != null) foreach (int c in alias) if (c > 0 && io.KeyUp(c)) aliasUp = true;
                var a = Attribute(io, alias, scan);
                Last = a;
                bool aliasDown = (a & EdgeAttribution.Alias) != 0;
                bool foreign = (a & (EdgeAttribution.Key | EdgeAttribution.Unknown)) != 0;
                if (Held && Clean && foreign) Clean = false;
                if (aliasDown && !Held)
                {
                    Held = true;
                    Clean = Mut == 18 || !foreign;
                    DownAt = io.Now();
                }
                if (aliasUp && Held)
                {
                    fire = Clean && io.Now() - DownAt < 0.6f;
                    Held = false;
                    Clean = false;
                }
                if (!io.Focused() && (Held || Clean)) { Held = false; Clean = false; }
                return fire;
            }
        }

        /// <summary>A scripted frame source: the harness's and T2 case j's.</summary>
        internal sealed class ScriptInput : IFrameInput
        {
            internal HashSet<int> Down = new HashSet<int>(), Up = new HashSet<int>();
            internal bool Any, MouseHeldNow;
            internal string Text = "";
            internal float T;
            /// <summary>M1: keyboard keys that went down this frame which no
            /// KeyCode names (the independent source sees them, the scan
            /// cannot), and an unreadable independent source.</summary>
            internal int KbExtra;
            internal bool KbUnavailable;
            public bool KeyDown(int code) { return Down.Contains(code); }
            public bool KeyUp(int code) { return Up.Contains(code); }
            public bool AnyKeyDown() { return Any; }
            public string TypedText() { return Text; }
            public bool AnyMouseHeld() { return MouseHeldNow; }
            public float Now() { return T; }
            public bool Focused() { return true; }
            /// <summary>The independent source's count: every keyboard code
            /// of the frame (named or not, the alias's included) plus the keys
            /// no KeyCode names.</summary>
            public int KeyboardEdges()
            {
                if (KbUnavailable) return -1;
                int n = KbExtra;
                foreach (int c in Down) if (IsKeyboardCode(c)) n++;
                return n;
            }
            internal void Frame(float t, int[] down, int[] up, bool any, string text, bool mouseHeld)
            {
                Frame(t, down, up, any, text, mouseHeld, 0, false);
            }
            internal void Frame(float t, int[] down, int[] up, bool any, string text, bool mouseHeld, int kbExtra, bool kbUnavailable)
            {
                T = t; Down = new HashSet<int>(down ?? new int[0]); Up = new HashSet<int>(up ?? new int[0]);
                Any = any; Text = text ?? ""; MouseHeldNow = mouseHeld;
                KbExtra = kbExtra; KbUnavailable = kbUnavailable;
            }
        }

        /// <summary>One scripted tap on <paramref name="alias"/>[0]: down, an
        /// optional middle frame, up. True when the release rotated the
        /// channel; <paramref name="mid"/> is the middle frame's attribution.</summary>
        internal static bool ScriptTap(int[] alias, int[] scan, int[] midDown, bool midAny, string midText,
                                       bool midMouseHeld, out EdgeAttribution mid)
        {
            return ScriptTap(alias, scan, midDown, midAny, midText, midMouseHeld, 0, false, out mid);
        }

        /// <summary>M1: the same tap with the middle frame's independent
        /// keyboard source scripted: <paramref name="midKbExtra"/> keys no
        /// KeyCode names went down, or the source is unreadable.</summary>
        internal static bool ScriptTap(int[] alias, int[] scan, int[] midDown, bool midAny, string midText,
                                       bool midMouseHeld, int midKbExtra, bool midKbUnavailable, out EdgeAttribution mid)
        {
            var d = new TapDetector();
            var io = new ScriptInput();
            int key = alias != null && alias.Length > 0 ? alias[0] : 0;
            mid = EdgeAttribution.None;
            io.Frame(0f, new[] { key }, null, true, "", midMouseHeld);
            d.Step(io, alias, scan);
            if (midDown != null || midAny || !string.IsNullOrEmpty(midText) || midKbExtra != 0 || midKbUnavailable)
            {
                io.Frame(0.1f, midDown, null, midAny, midText, midMouseHeld, midKbExtra, midKbUnavailable);
                d.Step(io, alias, scan);
                mid = d.Last;
            }
            io.Frame(0.2f, null, new[] { key }, false, "", false);
            return d.Step(io, alias, scan);
        }

        /// <summary>The harness's stand-in for the KeyCode member list: InControl's
        /// 127 codes, plus codes it does not carry (Menu 319, Print 316, the
        /// seven mouse buttons, joystick button 0 at 330).</summary>
        internal static int[] HarnessKeyCodeScan()
        {
            var l = new List<int>(StaticKeyScan);
            foreach (int c in new[] { 316, 319, 323, 324, 325, 326, 327, 328, 329, 330 }) if (!l.Contains(c)) l.Add(c);
            return l.ToArray();
        }

        /// <summary>Fix pass 1 F3: may a join or ready prompt be rewritten with
        /// the bound keyboard key? Only on a keyboard surface: never while the
        /// seat is held by a controller, and never over a vanilla face that
        /// shows a controller glyph (ROUNDS draws every controller button as a
        /// TMP sprite tag, in every locale - PROMPT_SOUTH_TO_JOIN,
        /// PROMPT_START_WHEN_READY). An empty seat with a keyboard face is the
        /// pre-join keyboard prompt, which is rewritten.</summary>
        internal static bool PromptSurfaceIsKeyboard(bool seated, bool seatIsController, string vanillaFace)
        {
            if (Mut == 19) return true;   // a22f80ed: the join override carried no device gate
            if (seated && seatIsController) return false;
            if (vanillaFace != null && vanillaFace.IndexOf("<sprite", StringComparison.OrdinalIgnoreCase) >= 0) return false;
            return true;
        }

        // -- names (design section 2.9) --------------------------------------

        private static readonly Dictionary<string, string> Glyphs = new Dictionary<string, string>
        {
            { "Backquote", "`" }, { "Minus", "-" }, { "Equals", "=" }, { "LeftBracket", "[" }, { "RightBracket", "]" },
            { "Backslash", "\\" }, { "Semicolon", ";" }, { "Quote", "'" }, { "Comma", "," }, { "Period", "." },
            { "Slash", "/" }, { "ExclamationMark", "!" }, { "Tilde", "~" }, { "At", "@" }, { "Hash", "#" },
            { "Dollar", "$" }, { "Percent", "%" }, { "Caret", "^" }, { "Ampersand", "&" }, { "Asterisk", "*" },
            { "LeftParen", "(" }, { "RightParen", ")" }, { "Underscore", "_" }, { "Plus", "+" }, { "LeftBrace", "{" },
            { "RightBrace", "}" }, { "Pipe", "|" }, { "Colon", ":" }, { "DoubleQuote", "\"" }, { "LessThan", "<" },
            { "GreaterThan", ">" }, { "QuestionMark", "?" },
        };

        /// <summary>The glyph arm: A-Z, 0-9 and the 32 punctuation keys (68).</summary>
        internal static bool IsGlyphKey(int keyOrdinal)
        {
            return GlyphFor(keyOrdinal) != null;
        }

        /// <summary>The character a glyph-arm key prints, or null.</summary>
        internal static string GlyphFor(int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeyTableLength) return null;
            string id = KeyIds[keyOrdinal];
            if (id.Length == 1 && id[0] >= 'A' && id[0] <= 'Z') return id;
            if (id.Length == 4 && id.StartsWith("Key", StringComparison.Ordinal) && char.IsDigit(id[3])) return id.Substring(3);
            string g;
            return Glyphs.TryGetValue(id, out g) ? g : null;
        }

        /// <summary>The function arm: F1-F15 (15).</summary>
        internal static int FunctionNumber(int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeyTableLength) return 0;
            string id = KeyIds[keyOrdinal];
            int n;
            if (id.Length >= 2 && id[0] == 'F' && int.TryParse(id.Substring(1), out n) && n >= 1 && n <= 15) return n;
            return 0;
        }

        // ---------------------------------------------------------------------
        // T1 - the executed self-test (design section 5). Every case names
        // the production symbol it drives; every mutation case runs the
        // unmutated build (must pass), the mutated build (the guarded
        // assertion must RED) and the control under the mutation (must stay
        // GREEN), so a mutation that broke everything cannot pass for one
        // that reached its target (#391, #712).
        // ---------------------------------------------------------------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }

        private static BindSource K(string id) { return BindSource.Key(KeyOrdinal(id)); }
        private static BindSource M(string id)
        {
            for (int i = 0; i < MouseIds.Length; i++) if (MouseIds[i] == id) return BindSource.Mouse(i);
            return BindSource.None;
        }

        private static BindSource[] Defaults()
        {
            var a = new BindSource[RowCount];
            for (int i = 0; i < RowCount; i++) a[i] = Default(i);
            return a;
        }

        private static Refusal Ref(int row, BindSource s, BindSource[] cur)
        {
            int other;
            return Refuse(row, s, cur, null, out other);
        }

        private static Refusal Ref(int row, BindSource s)
        {
            var cur = Defaults();
            cur[row] = BindSource.None;   // the row being written does not conflict with itself
            return Ref(row, s, cur);
        }

        /// <summary>One mutation case: <paramref name="guarded"/> must hold
        /// unmutated and fail under the mutation; <paramref name="control"/>
        /// must hold both ways.</summary>
        private static void MutCase(SelfTestResult r, int n, string symbol, string what,
                                    Func<bool> guarded, Func<bool> control, Func<string> measure)
        {
            int saved = Mut;
            bool g0, c0, g1, c1;
            string m0, m1;
            try
            {
                Mut = 0;
                g0 = Safe(guarded); c0 = Safe(control); m0 = SafeS(measure);
                Mut = n;
                g1 = Safe(guarded); c1 = Safe(control); m1 = SafeS(measure);
            }
            finally { Mut = saved; }
            Check(r, "T1 case " + n + " " + symbol + ": " + what + " (unmutated)", g0 && c0,
                  "guarded=" + g0 + " control=" + c0 + " " + m0);
            Check(r, "T1 case " + n + " " + symbol + ": mutation " + n + " reds the guarded assertion", !g1,
                  "guarded=" + g1 + " " + m1);
            Check(r, "T1 case " + n + " " + symbol + ": the control stays green under mutation " + n, c1,
                  "control=" + c1);
        }

        private static bool Safe(Func<bool> f) { try { return f(); } catch { return false; } }
        private static string SafeS(Func<string> f) { try { return f != null ? f() : ""; } catch (Exception e) { return "threw " + e.GetType().Name; } }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            int saved = Mut;
            Mut = 0;
            try { Run(r); }
            finally { Mut = saved; }
            return r;
        }

        private static void Run(SelfTestResult r)
        {
            // -- the table itself ------------------------------------------------
            Check(r, "the key table has 132 rows in each column",
                  KeyIds.Length == KeyTableLength && KeyCode0.Length == KeyTableLength && KeyCode1.Length == KeyTableLength,
                  KeyIds.Length + "/" + KeyCode0.Length + "/" + KeyCode1.Length);
            var scan = StaticKeyScan;
            var scanSet = new HashSet<int>(scan);
            Check(r, "StaticKeyScan holds 127 distinct KeyCodes, KeyCode.None excluded",
                  scan.Length == 127 && scanSet.Count == 127 && !scanSet.Contains(0), "length=" + scan.Length + " distinct=" + scanSet.Count);
            int glyph = 0, func = 0, word = 0, text = 0;
            for (int i = 1; i < KeyTableLength; i++)
            {
                if (IsGlyphKey(i)) glyph++; else if (FunctionNumber(i) > 0) func++; else word++;
                if (IsTextChanging(i)) text++;
            }
            Check(r, "the name arms split 68 glyph / 15 function / 48 word",
                  glyph == 68 && func == 15 && word == 48, glyph + "/" + func + "/" + word);
            Check(r, "rule 6 refuses 87 keys on ChatChannel", text == 87, text.ToString());
            Check(r, "Unity mouse buttons 0-6 map to the sparse Mouse enum",
                  MouseIndexToSource(0).Value == 1 && MouseIndexToSource(1).Value == 2 && MouseIndexToSource(2).Value == 3
                  && MouseIndexToSource(3).Value == 10 && MouseIndexToSource(6).Value == 13 && MouseIndexToSource(7).Kind == BindKind.None,
                  MouseIndexToSource(3).ToString() + "," + MouseIndexToSource(6) + "," + MouseIndexToSource(7));

            // -- defaults: the sixteen, pinned (required behaviour) ----------------
            string[] want = { "key:F5", "key:Tab", "key:Q", "key:E", "key:T", "key:Alt", "key:M", "key:LeftShift", "none",
                              "key:W", "key:S", "key:A", "key:D", "key:Space", "mouse:LeftButton", "mouse:RightButton" };
            var got = new List<string>();
            bool allEq = true;
            for (int i = 0; i < RowCount; i++) { string t = FormatToken(Default(i)); got.Add(t); if (t != want[i]) allEq = false; }
            Check(r, "the sixteen defaults equal today's keys exactly", allEq, string.Join(",", got.ToArray()));
            bool staticEq = true;
            for (int i = 0; i < RowCount; i++)
            {
                var d = Default(i);
                var codes = d.Kind == BindKind.Key ? StaticCodesForKey(d.Value) : new int[0];
                var a = new HashSet<int>(codes);
                if (!a.SetEquals(StaticDefaults[i])) staticEq = false;
            }
            Check(r, "StaticDefaults spells the same sixteen defaults as KeyCodes", staticEq, staticEq ? "16 of 16" : "mismatch");
            var defs = Defaults();
            bool noConflict = true;
            for (int i = 0; i < RowCount; i++) if (OverlapRow(i, defs[i], defs, null) >= 0) noConflict = false;
            Check(r, "no two defaults conflict", noConflict, noConflict.ToString());
            Check(r, "the defaults pass every rule on their own rows", AllDefaultsAccepted(), AllDefaultsAccepted().ToString());

            // -- the seventeen mutation cases (design section 5, T1) ---------------
            MutCase(r, 1, "KeybindRules.Overlap", "Shift against LeftShift conflicts",
                    () => Overlap(K("Shift"), K("LeftShift"), null),
                    () => !Overlap(K("Q"), K("E"), null),
                    () => "Shift~LeftShift=" + Overlap(K("Shift"), K("LeftShift"), null));
            MutCase(r, 2, "KeybindRules.Refuse", "Escape is reserved",
                    () => Ref(Scoreboard, K("Escape")) == Refusal.Reserved,
                    () => Ref(Scoreboard, K("F1")) == Refusal.None,
                    () => "Escape=" + Ref(Scoreboard, K("Escape")));
            MutCase(r, 3, "KeybindRules.Refuse", "Return is reserved",
                    () => Ref(Scoreboard, K("Return")) == Refusal.Reserved,
                    () => Ref(Scoreboard, K("Backspace")) == Refusal.None,
                    () => "Return=" + Ref(Scoreboard, K("Return")));
            MutCase(r, 4, "KeybindRules.Refuse", "F5 is refused on Scoreboard",
                    () => Ref(Scoreboard, K("F5")) == Refusal.RescueKey,
                    () => Ref(MenuToggle, K("F5")) == Refusal.None,
                    () => "F5@Scoreboard=" + Ref(Scoreboard, K("F5")));
            MutCase(r, 5, "KeybindRules.ParseToken", "a corrupt token falls back to the row default",
                    () => FormatToken(LoadToken(Jump, "bogus:???")) == "key:Space",
                    () => FormatToken(LoadToken(Jump, "key:K")) == "key:K",
                    () => "bogus->" + SafeS(() => FormatToken(LoadToken(Jump, "bogus:???"))));
            MutCase(r, 6, "KeybindRules.Refuse", "a mouse source on ChatOpen is refused",
                    () => Ref(ChatOpen, M("MiddleButton")) == Refusal.MouseOnModRow,
                    () => Ref(Fire, M("LeftButton")) == Refusal.None,
                    () => "Middle@ChatOpen=" + Ref(ChatOpen, M("MiddleButton")));
            MutCase(r, 7, "KeybindRules.Overlap", "Fire and Block both on the left button conflict",
                    () => { var c = Defaults(); return Ref(Block, M("LeftButton"), c) == Refusal.Overlap; },
                    () => { var c = Defaults(); c[Block] = BindSource.None; return Ref(Block, M("RightButton"), c) == Refusal.None; },
                    () => { var c = Defaults(); int o; var x = Refuse(Block, M("LeftButton"), c, null, out o); return "Block=Left:" + x + " other=" + o; });
            MutCase(r, 8, "KeybindRules.Refuse", "key:J on ChatChannel types into the box",
                    () => Ref(ChatChannel, K("J")) == Refusal.TypesText,
                    () => Ref(ChatChannel, K("F9")) == Refusal.None && Ref(ChatOpen, K("J")) == Refusal.None,
                    () => "J@ChatChannel=" + Ref(ChatChannel, K("J")));
            MutCase(r, 9, "KeybindRules.MouseIndexToSource", "Unity button 3 resolves to Button4",
                    () => FormatToken(MouseIndexToSource(3)) == "mouse:Button4",
                    () => FormatToken(MouseIndexToSource(0)) == "mouse:LeftButton" && FormatToken(MouseIndexToSource(1)) == "mouse:RightButton"
                          && FormatToken(MouseIndexToSource(2)) == "mouse:MiddleButton",
                    () => "3->" + FormatToken(MouseIndexToSource(3)));
            MutCase(r, 10, "KeybindRules.CaptureGesture", "an armed capture over Backspace binds",
                    () => CaptureGesture(KeyBackspace, true) == Gesture.Bind,
                    () => CaptureGesture(KeyEscape, true) == Gesture.Cancel && CaptureGesture(KeyBackspace, false) == Gesture.Ignore
                          && FormatToken(BindSource.None) == "none",
                    () => "Backspace(armed)=" + CaptureGesture(KeyBackspace, true));
            MutCase(r, 11, "KeybindRules.StaticDefaults", "MapSkinCycle defaults to key:LeftShift",
                    () => DefaultToken(MapSkinCycle) == "key:LeftShift",
                    () => { for (int i = 0; i < RowCount; i++) if (i != MapSkinCycle && DefaultToken(i) != want[i]) return false; return true; },
                    () => "MapSkinCycle=" + DefaultToken(MapSkinCycle));
            MutCase(r, 12, "KeybindRules.FirstHit", "rows {1, 5} down capture as row 1 (Shift)",
                    () => FirstHit(new[] { 5, 1 }) == 1,
                    () => { BindSource s; return ParseToken("key:LeftShift", out s) && s.Value == 5 && KeyIds[s.Value] == "LeftShift"; },
                    () => "FirstHit{5,1}=" + FirstHit(new[] { 5, 1 }));
            int capA = 3;
            MutCase(r, 13, "Keybinds.ReadBoundSource / KeybindRules.GuardedMouseRead", "a mouse button above the cap reads Unreadable",
                    () => { int cap = 3; return GuardedMouseRead(3, ref cap, b => true, null) == Read.Unreadable && MouseUnreadable(M("Button4"), 3); },
                    () => { int cap = 3; return GuardedMouseRead(0, ref cap, b => true, null) == Read.Down
                                               && GuardedMouseRead(0, ref cap, b => false, null) == Read.Up
                                               && !MouseUnreadable(M("LeftButton"), 3); },
                    () => "Button4@cap3=" + GuardedMouseRead(3, ref capA, b => true, null));
            MutCase(r, 14, "KeybindRules.Refuse", "key:Space on ChatChannel types into the box",
                    () => Ref(ChatChannel, K("Space")) == Refusal.TypesText,
                    () => Ref(ChatChannel, K("F9")) == Refusal.None && Ref(ChatChannel, K("LeftAlt")) == Refusal.None
                          && Ref(Jump, K("Space")) == Refusal.None,
                    () => "Space@ChatChannel=" + Ref(ChatChannel, K("Space")));
            MutCase(r, 15, "KeybindRules.Refuse", "key:Backspace on ChatChannel removes text",
                    () => Ref(ChatChannel, K("Backspace")) == Refusal.TypesText,
                    () => Ref(Scoreboard, K("Backspace")) == Refusal.None,
                    () => "Backspace@ChatChannel=" + Ref(ChatChannel, K("Backspace")));
            MutCase(r, 16, "KeybindRules.ShouldOverrideReadyPrompt", "Jump on key:K asks for the prompt override",
                    () => ShouldOverrideReadyPrompt(K("K")),
                    () => !ShouldOverrideReadyPrompt(K("Space")),
                    () => "K=" + ShouldOverrideReadyPrompt(K("K")) + " Space=" + ShouldOverrideReadyPrompt(K("Space")));
            MutCase(r, 17, "KeybindRules.Refuse", "key:Delete and key:Backspace on ChatChannel remove text",
                    () => Ref(ChatChannel, K("Delete")) == Refusal.TypesText && Ref(ChatChannel, K("Backspace")) == Refusal.TypesText,
                    () => Ref(ChatChannel, K("Insert")) == Refusal.None && Ref(ChatChannel, K("Home")) == Refusal.None
                          && Ref(ChatChannel, K("End")) == Refusal.None && Ref(ChatChannel, K("PageUp")) == Refusal.None
                          && Ref(ChatChannel, K("PageDown")) == Refusal.None && Ref(Scoreboard, K("Delete")) == Refusal.None,
                    () => "Delete@ChatChannel=" + Ref(ChatChannel, K("Delete")));

            // -- fix pass 1 F2: the tap detector attributes every edge ---------------
            // Case j rebuilt: a key InControl's table does not carry (Menu, 319)
            // and a mouse edge (Mouse0, 323) in ONE frame are attributed to both,
            // and the tap does not rotate. The UNKNOWN leg: a typed character no
            // KeyCode names beside a mouse edge is Unknown, never mouse-only.
            // Mutation 18 is the a22f80ed detector; both legs were mouse-only there.
            int[] tapAlias = StaticDefaults[ChatChannel], tapScan = HarnessKeyCodeScan();
            Func<int[], bool, string, bool, string> tapRun = (down, any, text, held) =>
            {
                EdgeAttribution mid;
                bool rotated = ScriptTap(tapAlias, tapScan, down, any, text, held, out mid);
                return (rotated ? "rotated" : "kept") + "/" + mid;
            };
            MutCase(r, 18, "KeybindRules.TapDetector", "a simultaneous key edge and mouse edge are attributed to both, and an unnamed edge beside a mouse edge is Unknown",
                    () => tapRun(new[] { 319, KeyCodeMouse0 }, true, "", false) == "kept/" + (EdgeAttribution.Key | EdgeAttribution.Mouse)
                          && tapRun(new[] { KeyCodeMouse0 }, true, "é", false) == "kept/" + (EdgeAttribution.Mouse | EdgeAttribution.Unknown),
                    () => tapRun(null, false, "", false) == "rotated/None"
                          && tapRun(new[] { KeyCodeMouse0 }, true, "", false) == "rotated/" + EdgeAttribution.Mouse
                          && tapRun(new[] { 106 }, true, "j", false) == "kept/" + EdgeAttribution.Key,
                    () => "sim=" + tapRun(new[] { 319, KeyCodeMouse0 }, true, "", false)
                          + " unknown+mouse=" + tapRun(new[] { KeyCodeMouse0 }, true, "é", false));
            // Revision 3's held-button shape, the in-game mutation 7 (107) ported here:
            // an unnamed edge while a button is merely HELD (no edge) is Unknown.
            MutCase(r, 23, "KeybindRules.TapDetector", "an unnamed edge while a mouse button is only held disarms",
                    () => tapRun(null, true, "", true) == "kept/" + EdgeAttribution.Unknown,
                    () => tapRun(new[] { KeyCodeMouse0 }, true, "", true) == "rotated/" + EdgeAttribution.Mouse
                          && tapRun(null, true, "", false) == "kept/" + EdgeAttribution.Unknown,
                    () => "held+unnamed=" + tapRun(null, true, "", true));
            Check(r, "F2 KeybindRules.TapDetector: a foreign key on the ARMING frame keeps the tap from rotating",
                  !TapArmedWithForeign(tapAlias, tapScan), "rotated=" + TapArmedWithForeign(tapAlias, tapScan));

            // -- fix pass 2 M1: the independently latched keyboard-edge source -------
            // ChatChannel armed; in one frame a keyboard key no KeyCode names
            // (no typed text) goes down beside a click: the independent source
            // counts one keyboard edge the scan did not name, so the frame is
            // Unknown as well as Mouse and the release does not rotate. Also
            // with no anyKeyDown at all, on the arming frame, and with the source
            // unreadable beside a click. Mutation 25 is the 2811a621 detector,
            // which had no independent source: every guarded leg rotated there.
            // The controls hold either way: a click alone rotates, a named key
            // beside a click and typed text beside a click do not.
            Func<int[], bool, string, int, bool, string> tapKb = (down, any, text, kbExtra, kbOff) =>
            {
                EdgeAttribution mid;
                bool rotated = ScriptTap(tapAlias, tapScan, down, any, text, false, kbExtra, kbOff, out mid);
                return (rotated ? "rotated" : "kept") + "/" + mid;
            };
            MutCase(r, 25, "KeybindRules.TapDetector", "an unattributable non-text keyboard edge disarms ChatChannel independently of the mouse, a same-frame click included",
                    () => tapKb(new[] { KeyCodeMouse0 }, true, "", 1, false) == "kept/" + (EdgeAttribution.Mouse | EdgeAttribution.Unknown)
                          && tapKb(null, false, "", 1, false) == "kept/" + EdgeAttribution.Unknown
                          && tapKb(new[] { KeyCodeMouse0 }, true, "", 0, true) == "kept/" + (EdgeAttribution.Mouse | EdgeAttribution.Unknown)
                          && !TapArmedWithUnnamed(tapAlias, tapScan),
                    () => tapKb(null, false, "", 0, false) == "rotated/None"
                          && tapKb(new[] { KeyCodeMouse0 }, true, "", 0, false) == "rotated/" + EdgeAttribution.Mouse
                          && tapKb(new[] { 319, KeyCodeMouse0 }, true, "", 0, false) == "kept/" + (EdgeAttribution.Key | EdgeAttribution.Mouse)
                          && tapKb(new[] { KeyCodeMouse0 }, true, "é", 1, false) == "kept/" + (EdgeAttribution.Mouse | EdgeAttribution.Unknown),
                    () => "unnamed+click=" + tapKb(new[] { KeyCodeMouse0 }, true, "", 1, false)
                          + " unnamed-alone=" + tapKb(null, false, "", 1, false)
                          + " unreadable+click=" + tapKb(new[] { KeyCodeMouse0 }, true, "", 0, true)
                          + " armed-with-unnamed-rotated=" + TapArmedWithUnnamed(tapAlias, tapScan));

            // -- fix pass 1 F5: the loaded set is conflict-free ---------------------
            // QuickChat moved off Q, MenuToggle saved on Q, then QuickChat hand-
            // edited to the forbidden F5: QuickChat's default Q is revalidated
            // against MenuToggle and refused, so QuickChat loads unbound.
            // Mutation 20 is the a22f80ed loader: both rows end on Q.
            Func<BindSource[]> handEdited = () =>
            {
                var p = Defaults();
                p[MenuToggle] = K("Q");
                p[QuickChat] = K("F5");
                return p;
            };
            MutCase(r, 20, "KeybindRules.ResolveLoaded", "a fallback default is revalidated: the loaded set is conflict-free",
                    () =>
                    {
                        var e = ResolveLoaded(handEdited(), null, null);
                        return ConflictFree(e, null) && e[MenuToggle].Equals(K("Q")) && e[QuickChat].Kind == BindKind.None;
                    },
                    () =>
                    {
                        var d = ResolveLoaded(Defaults(), null, null);
                        bool same = true;
                        for (int i = 0; i < RowCount; i++) if (!d[i].Equals(Default(i))) same = false;
                        var p = Defaults(); p[Jump] = K("Escape");
                        var j = ResolveLoaded(p, null, null);
                        return same && j[Jump].Equals(K("Space")) && ConflictFree(j, null);
                    },
                    () =>
                    {
                        var e = ResolveLoaded(handEdited(), null, null);
                        return "MenuToggle=" + FormatToken(e[MenuToggle]) + " QuickChat=" + FormatToken(e[QuickChat])
                               + " conflictFree=" + ConflictFree(e, null);
                    });
            Check(r, "F5 KeybindRules.ResolveLoaded: every row refused and its default refused too is noted and left unbound",
                  ResolveNotes(handEdited()).Count == 1 && ResolveNotes(handEdited())[0].StartsWith("QuickChat: key:F5 refused (RescueKey)", StringComparison.Ordinal)
                  && ResolveNotes(handEdited())[0].EndsWith("unbound", StringComparison.Ordinal),
                  string.Join(" | ", ResolveNotes(handEdited()).ToArray()));

            // -- fix pass 1 F6: an accepted write is all or nothing ------------------
            // A two-row write (a reset that frees a row) whose live-set apply
            // throws, and one whose second config write throws: the registry,
            // the entries and the live sets equal the state before, and the
            // commit reports failure. Mutation 21 is a22f80ed's per-step catches.
            MutCase(r, 21, "KeybindRules.Commit", "a throw in the apply or in a config write puts every prior state back and reports failure",
                    () => CommitRestores(1, -1) && CommitRestores(0, Jump),
                    () =>
                    {
                        var reg = Defaults();
                        var store = new FakeStore(Defaults());
                        string f;
                        bool ok = Commit(reg, new[] { QuickChat, Jump }, new[] { K("G"), K("K") }, store, out f);
                        var want = Defaults(); want[QuickChat] = K("G"); want[Jump] = K("K");
                        return ok && f == null && SameSet(reg, want) && StoreMatches(store, want) && store.Applies == 1;
                    },
                    () => "apply-throws=" + CommitRestores(1, -1) + " write-throws=" + CommitRestores(0, Jump));

            // -- fix pass 1 F3: prompt overrides target keyboard surfaces only -------
            const string southJoin = "Press\n[<sprite name=BUTTON_SOUTH>]\nto join", spaceJoin = "Press\n[SPACE]\nto join";
            const string ukSouthJoin = "Натисніть\n[<sprite name=BUTTON_SOUTH>]\nщоб приєднатися";
            MutCase(r, 19, "KeybindRules.PromptSurfaceIsKeyboard", "a controller seat and a controller-glyph face keep the vanilla prompt",
                    () => !PromptSurfaceIsKeyboard(true, true, spaceJoin) && !PromptSurfaceIsKeyboard(false, false, southJoin)
                          && !PromptSurfaceIsKeyboard(false, false, ukSouthJoin) && !PromptSurfaceIsKeyboard(true, true, null),
                    () => PromptSurfaceIsKeyboard(false, false, spaceJoin) && PromptSurfaceIsKeyboard(true, false, spaceJoin)
                          && PromptSurfaceIsKeyboard(false, false, null),
                    () => "controllerSeat=" + PromptSurfaceIsKeyboard(true, true, spaceJoin) + " southFace=" + PromptSurfaceIsKeyboard(false, false, southJoin));

            // -- fix pass 1 F7: a mouse press during capture reaches the refusal ------
            // The poll's two decisions composed: it reads the mouse for the armed
            // row, and the one writer answers it. Every mod row must reach
            // MouseOnModRow (the capture ends, the refusal shows); every game row
            // whose default is a key saves a free mouse button.
            MutCase(r, 22, "KeybindRules.CaptureTakesMouse", "a mouse press on an armed mod-control row reaches the MouseOnModRow refusal",
                    () =>
                    {
                        for (int row = 0; row < FirstGameRow; row++)
                            if (!CaptureTakesMouse(row) || Ref(row, M("MiddleButton")) != Refusal.MouseOnModRow) return false;
                        return true;
                    },
                    () => CaptureTakesMouse(Jump) && Ref(Jump, M("MiddleButton")) == Refusal.None
                          && CaptureTakesMouse(MoveUp) && Ref(MoveUp, M("Button4")) == Refusal.None
                          && !CaptureTakesMouse(-1) && !CaptureTakesMouse(RowCount),
                    () => "menu=" + CaptureTakesMouse(MenuToggle) + "/" + Ref(MenuToggle, M("MiddleButton")) + " jump=" + Ref(Jump, M("MiddleButton")));

            // -- fix pass 1 F4: the keyboard guide colours follow the bindings ------
            // Guarded: DanceWheel moved E -> G and Fire moved LMB -> K recolour
            // exactly those four caps. Control: the defaults reproduce the
            // board a22f80ed hardcoded, cap for cap.
            MutCase(r, 24, "KeybindRules.BoardCapRole", "a moved control recolours the board: its old cap empties and its new cap takes its side",
                    () =>
                    {
                        var set = Defaults(); set[DanceWheel] = K("G"); set[Fire] = K("K");
                        return BoardCapRole("E", set, null) == 0 && BoardCapRole("G", set, null) == BoardMod
                               && BoardCapRole("LMB", set, null) == 0 && BoardCapRole("K", set, null) == BoardGame
                               && BoardCapRole("Q", set, null) == BoardMod;
                    },
                    () => BoardMatchesTheDefaultBoard(),
                    () => { var set = Defaults(); set[DanceWheel] = K("G"); return "E=" + BoardCapRole("E", set, null) + " G=" + BoardCapRole("G", set, null) + " defaults=" + BoardMatchesTheDefaultBoard(); });

            // case 16's own second control, outside the mutation: an unbound or
            // mouse-bound Jump cannot be described by the word SPACE either.
            Check(r, "T1 case 16b KeybindRules.ShouldOverrideReadyPrompt: mouse and unbound Jump also override",
                  ShouldOverrideReadyPrompt(M("LeftButton")) && ShouldOverrideReadyPrompt(BindSource.None) && !ShouldOverrideReadyPrompt(K("Space")),
                  "mouse=" + ShouldOverrideReadyPrompt(M("LeftButton")) + " none=" + ShouldOverrideReadyPrompt(BindSource.None));

            // -- question 6 (wheel rows refuse modifiers) and question 7 (mouse) --
            Check(r, "Q6 KeybindRules.Refuse: QuickChat and DanceWheel refuse Shift, Left Alt and AltGr",
                  Ref(QuickChat, K("Shift")) == Refusal.WheelModifier && Ref(DanceWheel, K("LeftAlt")) == Refusal.WheelModifier
                  && Ref(QuickChat, K("AltGr")) == Refusal.WheelModifier,
                  Ref(QuickChat, K("Shift")) + "," + Ref(DanceWheel, K("LeftAlt")) + "," + Ref(QuickChat, K("AltGr")));
            Check(r, "Q6 control: the wheels still take an ordinary key, and Shift stays bindable elsewhere",
                  Ref(QuickChat, K("G")) == Refusal.None && Ref(DanceWheel, K("H")) == Refusal.None && Ref(MoveUp, K("RightShift")) == Refusal.None,
                  Ref(QuickChat, K("G")) + "," + Ref(DanceWheel, K("H")) + "," + Ref(MoveUp, K("RightShift")));
            bool gameMouse = true, modMouse = true;
            for (int row = 0; row < RowCount; row++)
            {
                var c = Defaults();
                c[row] = BindSource.None;
                var res = Ref(row, M("Button5"), c);
                if (IsGameRow(row) && res != Refusal.None) gameMouse = false;
                if (IsModRow(row) && res != Refusal.MouseOnModRow) modMouse = false;
            }
            Check(r, "Q7 KeybindRules.Refuse: all seven game rows take a mouse button, none of the nine mod rows does",
                  gameMouse && modMouse, "game=" + gameMouse + " mod=" + modMouse);
            Check(r, "rule 5 KeybindRules.Refuse: None is never a bind", Ref(Jump, BindSource.None) == Refusal.NoneAsBind,
                  Ref(Jump, BindSource.None).ToString());
            Check(r, "rule 1 KeybindRules.Refuse names the row that already holds the key",
                  RefOther(MoveLeft, K("W")) == MoveUp, "other=" + RefOther(MoveLeft, K("W")));
            Check(r, "PadEnter is reserved", Ref(Scoreboard, K("PadEnter")) == Refusal.Reserved, Ref(Scoreboard, K("PadEnter")).ToString());

            // -- tokens round-trip ---------------------------------------------------
            bool rt = true;
            for (int i = 1; i < KeyTableLength; i++)
            {
                BindSource s;
                if (!ParseToken(FormatToken(BindSource.Key(i)), out s) || s.Value != i || s.Kind != BindKind.Key) rt = false;
            }
            for (int n = 0; n < 7; n++)
            {
                BindSource s;
                var m = MouseIndexToSource(n);
                if (!ParseToken(FormatToken(m), out s) || !s.Equals(m)) rt = false;
            }
            Check(r, "KeybindRules.ParseToken round-trips every key and every bindable mouse button", rt, rt.ToString());
            BindSource ns;
            Check(r, "KeybindRules.ParseToken: none parses to the unbound source and a mouse axis does not parse",
                  ParseToken("none", out ns) && ns.Kind == BindKind.None && !ParseToken("mouse:NegativeX", out ns) && !ParseToken("key:None", out ns),
                  "ok");
        }

        /// <summary>F6's fake store: entries in a dictionary, live sets as the
        /// last applied copy; ApplyAll throws on the call numbered
        /// <see cref="ThrowOnApply"/> (1-based; 0 never).</summary>
        private sealed class FakeStore : IBindStore
        {
            internal readonly string[] Entries = new string[RowCount];
            internal BindSource[] Applied;
            internal int Applies, ThrowOnApply, ThrowOnWriteRow = -1;
            internal FakeStore(BindSource[] start)
            {
                for (int i = 0; i < RowCount; i++) Entries[i] = FormatToken(start[i]);
                Applied = (BindSource[])start.Clone();
            }
            public string ReadEntry(int row) { return Entries[row]; }
            public void WriteEntry(int row, string token)
            {
                if (row == ThrowOnWriteRow) { ThrowOnWriteRow = -1; throw new InvalidOperationException("config write"); }
                Entries[row] = token;
            }
            public void ApplyAll(BindSource[] b)
            {
                Applies++;
                if (Applies == ThrowOnApply) throw new InvalidOperationException("live set apply");
                Applied = (BindSource[])b.Clone();
            }
        }

        private static bool SameSet(BindSource[] a, BindSource[] b)
        {
            if (a == null || b == null || a.Length != b.Length) return false;
            for (int i = 0; i < a.Length; i++) if (!a[i].Equals(b[i])) return false;
            return true;
        }

        private static bool StoreMatches(FakeStore s, BindSource[] set)
        {
            for (int i = 0; i < RowCount; i++) if (s.Entries[i] != FormatToken(set[i])) return false;
            return SameSet(s.Applied, set);
        }

        /// <summary>A failed commit: false, and the registry, the entries and
        /// the live sets all equal the state before it.</summary>
        private static bool CommitRestores(int throwOnApply, int throwOnWriteRow)
        {
            var reg = Defaults();
            var start = Defaults();
            var store = new FakeStore(start) { ThrowOnApply = throwOnApply, ThrowOnWriteRow = throwOnWriteRow };
            string f;
            bool ok = Commit(reg, new[] { QuickChat, Jump }, new[] { K("G"), K("K") }, store, out f);
            return !ok && f != null && SameSet(reg, start) && StoreMatches(store, start);
        }

        /// <summary>F4's control: under the sixteen defaults every board cap
        /// has the colour a22f80ed's hardcoded board gave it.</summary>
        private static bool BoardMatchesTheDefaultBoard()
        {
            var mod = new[] { "F5", "TAB", "Q", "E", "T", "SHIFT", "M", "ALT" };
            var game = new[] { "W", "A", "S", "D", "ENTER", "B", "SPACE", "LMB", "RMB" };
            var set = Defaults();
            for (int i = 0; i < BoardCapCount; i++)
            {
                string id = BoardCapId(i);
                int want = id == "ESC" ? BoardMod | BoardGame
                         : Array.IndexOf(mod, id) >= 0 ? BoardMod
                         : Array.IndexOf(game, id) >= 0 ? BoardGame : 0;
                if (BoardCapRole(id, set, null) != want) return false;
            }
            return BoardCapCount == 54 && BoardCapRole("NUMLOCK", set, null) == -1;
        }

        private static List<string> ResolveNotes(BindSource[] parsed)
        {
            var n = new List<string>();
            ResolveLoaded(parsed, null, n);
            return n;
        }

        /// <summary>The alias and a foreign key go down in the same frame, then
        /// the alias comes up: true if that rotated the channel.</summary>
        private static bool TapArmedWithForeign(int[] alias, int[] scan)
        {
            var d = new TapDetector();
            var io = new ScriptInput();
            io.Frame(0f, new[] { alias[0], 106 }, null, true, "j", false);
            d.Step(io, alias, scan);
            io.Frame(0.2f, null, new[] { alias[0] }, false, "", false);
            return d.Step(io, alias, scan);
        }

        /// <summary>M1: the alias and a key no KeyCode names go down in the
        /// same frame (the independent source counts two keyboard edges, the
        /// scan names one), then the alias comes up: true if that rotated the
        /// channel.</summary>
        private static bool TapArmedWithUnnamed(int[] alias, int[] scan)
        {
            var d = new TapDetector();
            var io = new ScriptInput();
            io.Frame(0f, new[] { alias[0] }, null, true, "", false, 1, false);
            d.Step(io, alias, scan);
            io.Frame(0.2f, null, new[] { alias[0] }, false, "", false);
            return d.Step(io, alias, scan);
        }

        private static int RefOther(int row, BindSource s)
        {
            var cur = Defaults();
            cur[row] = BindSource.None;
            int other;
            Refuse(row, s, cur, null, out other);
            return other;
        }

        private static bool AllDefaultsAccepted()
        {
            var cur = Defaults();
            for (int i = 0; i < RowCount; i++)
            {
                if (cur[i].Kind == BindKind.None) continue;
                int other;
                if (Refuse(i, cur[i], cur, null, out other) != Refusal.None) return false;
            }
            return true;
        }
    }
}
