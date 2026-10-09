using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using BepInEx.Configuration;
using HarmonyLib;
using InControl;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 17 (v1.41.0): the keybind system. Sixteen rows - nine mod
    /// controls and seven of the base game's - each persisted as one string in
    /// the BepInEx config section "Controls" and edited from the settings
    /// page's Controls sub-tab. The rules (overlap, refusal, capture order,
    /// tokens, defaults) are KeybindRules, which the harness executes; this
    /// file is the Unity half.
    ///
    /// Two mechanisms carry the base-game keys (design sections 2.3, 2.4):
    /// A, ApplyGameBindings rewrites the InControl bindings of every
    /// keyboard-created PlayerActions set (a postfix on the keyboard factory
    /// registers each set; every write re-applies all live sets in the same
    /// call); B, three transpilers replace the game's raw
    /// Input.GetKey/GetKeyDown reads of Space (ready-up, twice) and Left
    /// Shift (map art) with Held/Down of the bound row, and four postfixes
    /// keep the ready-up prompts naming the bound key. Nothing here changes
    /// what any seat sends: it is a local remap of local input.
    ///
    /// Carries no player-facing literal: names, labels, refusals and toasts
    /// are NativeUI's (tools/i18n_extract.py scans an explicit file list, #464).
    /// </summary>
    internal static class Keybinds
    {
        internal const int MenuToggle = KeybindRules.MenuToggle, Scoreboard = KeybindRules.Scoreboard,
                           QuickChat = KeybindRules.QuickChat, DanceWheel = KeybindRules.DanceWheel,
                           ChatOpen = KeybindRules.ChatOpen, ChatChannel = KeybindRules.ChatChannel,
                           ChatOverlayMode = KeybindRules.ChatOverlayMode, MapSkinCycle = KeybindRules.MapSkinCycle,
                           AvatarSwap = KeybindRules.AvatarSwap, MoveUp = KeybindRules.MoveUp,
                           MoveDown = KeybindRules.MoveDown, MoveLeft = KeybindRules.MoveLeft,
                           MoveRight = KeybindRules.MoveRight, Jump = KeybindRules.Jump,
                           Fire = KeybindRules.Fire, Block = KeybindRules.Block;

        internal enum Mode { Edge, Held }

        // =================================================================
        // 2.1a - the mapping accessor, the one resolution path
        // =================================================================

        /// <summary>One resolution of InControl's private Key-to-KeyCode
        /// table, validated against the assembly actually loaded.</summary>
        internal sealed class MappingState
        {
            internal bool Ready;
            internal string Failure = "";
            internal int[][] Codes;              // [132][] distinct KeyCode ordinals per Key row
            internal int TableLength;
        }

        private static MappingState live = new MappingState { Failure = "not resolved yet" };

        internal static bool MappingReady { get { return live.Ready; } }
        internal static string MappingFailure { get { return live.Failure; } }

        /// <summary>The five steps of design section 2.1a. A step that
        /// fails leaves Ready false and names itself; nothing throws.
        /// <paramref name="fieldOverride"/> is the T2 mutation-5 seam: a
        /// misspelt field name the validation must catch.</summary>
        internal static MappingState ResolveMapping(string fieldOverride)
        {
            var st = new MappingState();
            try
            {
                var provider = typeof(InputManager).Assembly.GetType("InControl.UnityKeyboardProvider");
                if (provider == null) { st.Failure = "step 1: InControl.UnityKeyboardProvider not found"; return st; }
                var km = provider.GetNestedType("KeyMapping", BindingFlags.Public | BindingFlags.NonPublic);
                if (km == null || !km.IsValueType) { st.Failure = "step 1: KeyMapping " + (km == null ? "not found" : "is not a value type"); return st; }
                const BindingFlags inst = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
                var fSource = km.GetField(fieldOverride ?? "source", inst);
                var fT0 = km.GetField("target0", inst);
                var fT1 = km.GetField("target1", inst);
                if (fSource == null || fT0 == null || fT1 == null)
                {
                    st.Failure = "step 2: KeyMapping." + (fSource == null ? (fieldOverride ?? "source") : fT0 == null ? "target0" : "target1") + " not found";
                    return st;
                }
                if (fSource.FieldType != typeof(Key) || fT0.FieldType != typeof(KeyCode) || fT1.FieldType != typeof(KeyCode))
                { st.Failure = "step 2: KeyMapping field types are not Key / KeyCode / KeyCode"; return st; }
                var fTable = provider.GetField("KeyMappings", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static);
                var table = fTable != null ? fTable.GetValue(null) as Array : null;
                if (table == null || table.Length != KeybindRules.KeyTableLength)
                { st.Failure = "step 3: KeyMappings " + (table == null ? "not found" : "has " + table.Length + " rows, not 132"); return st; }
                var codes = new int[table.Length][];
                for (int i = 0; i < table.Length; i++)
                {
                    object row = table.GetValue(i);
                    int src = (int)(Key)fSource.GetValue(row);
                    if (src != i) { st.Failure = "step 4: KeyMappings[" + i + "].source is " + src + ", the table is not ordinal-indexed"; return st; }
                    int a = (int)(KeyCode)fT0.GetValue(row), b = (int)(KeyCode)fT1.GetValue(row);
                    var l = new List<int>(2);
                    if (a != 0) l.Add(a);
                    if (b != 0 && b != a) l.Add(b);
                    codes[i] = l.ToArray();
                }
                if (!SameSet(codes[(int)Key.Shift], (int)KeyCode.LeftShift, (int)KeyCode.RightShift)
                    || !SameSet(codes[(int)Key.Alt], (int)KeyCode.LeftAlt, (int)KeyCode.RightAlt)
                    || !SameSet(codes[(int)Key.A], (int)KeyCode.A))
                { st.Failure = "step 5: an anchor row (Shift, Alt or A) does not hold its codes"; return st; }
                st.Codes = codes;
                st.TableLength = table.Length;
                st.Ready = true;
                st.Failure = "";
            }
            catch (Exception e) { st.Ready = false; st.Failure = "threw: " + e.GetType().Name + ": " + e.Message; }
            return st;
        }

        private static bool SameSet(int[] got, params int[] want)
        {
            return got != null && new HashSet<int>(got).SetEquals(want);
        }

        /// <summary>The KeyCode ordinals one Key row names, from the
        /// validated table, or the transcribed one while it is not ready.</summary>
        internal static int[] CodesForKey(int keyOrdinal)
        {
            return CodesForKey(live, keyOrdinal);
        }

        private static int[] CodesForKey(MappingState st, int keyOrdinal)
        {
            if (keyOrdinal <= 0 || keyOrdinal >= KeybindRules.KeyTableLength) return new int[0];
            if (st != null && st.Ready && st.Codes != null) return st.Codes[keyOrdinal] ?? new int[0];
            return KeybindRules.StaticCodesForKey(keyOrdinal);
        }

        /// <summary>The 0, 1 or 2 KeyCodes the row's binding names. While
        /// the accessor is not validated, the row's static default.</summary>
        internal static int[] KeyCodesFor(int row)
        {
            return KeyCodesFor(live, row);
        }

        private static int[] KeyCodesFor(MappingState st, int row)
        {
            if (row < 0 || row >= KeybindRules.RowCount) return new int[0];
            if (st == null || !st.Ready) return KeybindRules.StaticDefaults[row];
            var b = bound[row];
            return b.Kind == BindKind.Key ? CodesForKey(st, b.Value) : new int[0];
        }

        /// <summary>The scan set the ChatChannel detector walks: every
        /// distinct KeyCode of the table, from whichever table is in force.</summary>
        internal static int[] ScanSet()
        {
            return ScanSet(live);
        }

        private static int[] ScanSet(MappingState st)
        {
            if (st == null || !st.Ready) return KeybindRules.StaticKeyScan;
            var seen = new HashSet<int>();
            var l = new List<int>();
            for (int i = 1; i < st.Codes.Length; i++)
                foreach (int c in st.Codes[i])
                    if (KeybindRules.Mut == 108 || seen.Add(c)) l.Add(c);
            return l.ToArray();
        }

        // =================================================================
        // 2.8 - persistence, and the one writer
        // =================================================================

        private static readonly BindSource[] bound = new BindSource[KeybindRules.RowCount];
        private static readonly ConfigEntry<string>[] entries = new ConfigEntry<string>[KeybindRules.RowCount];
        private static readonly bool[] announceOwed = new bool[KeybindRules.RowCount];
        private static bool initDone;

        internal static BindSource Bound(int row)
        {
            return row >= 0 && row < KeybindRules.RowCount ? bound[row] : BindSource.None;
        }

        internal static BindSource[] BoundSnapshot() { return (BindSource[])bound.Clone(); }

        /// <summary>The rows can be written only while the accessor is
        /// validated: otherwise every row is read-only and every default
        /// stays in force (design section 2.1a).</summary>
        internal static bool RowsWritable { get { return live.Ready; } }

        /// <summary>Plugin.Awake, before the Harmony loop: resolve the
        /// accessor once, bind the sixteen entries, load them.</summary>
        internal static void Init(ConfigFile cfg)
        {
            if (initDone) return;
            initDone = true;
            live = ResolveMapping(null);
            if (!live.Ready) Plugin.Log.LogWarning("[KEYBIND] mapping unavailable: " + live.Failure + " - every row read-only, every default in force");
            for (int i = 0; i < KeybindRules.RowCount; i++)
            {
                try
                {
                    entries[i] = cfg.Bind("Controls", KeybindRules.RowIds[i], KeybindRules.DefaultToken(i),
                        "One control of the Controls settings tab, as a binding token: key:<name>, mouse:<button> or none. "
                        + "Edit it from that tab; a token this build cannot read falls back to the row's default.");
                }
                catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] bind " + KeybindRules.RowIds[i] + ": " + e.Message); }
            }
            LoadFromConfig();
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < KeybindRules.RowCount; i++)
                sb.Append(i == 0 ? "" : " ").Append(KeybindRules.RowIds[i]).Append('=').Append(KeybindRules.FormatToken(bound[i]));
            Plugin.Log.LogInfo("[KEYBIND] loaded: mapping=" + (live.Ready ? "OK" : "UNAVAILABLE") + " " + sb);
        }

        /// <summary>The loader: a token that parses is the binding,
        /// anything else keeps the default (KeybindRules.LoadToken). A loaded
        /// set that the rules refuse - two rows on one key, a reserved key,
        /// a mouse button on a mod row - is not honoured: the offending row
        /// falls back to its default and the line says so.</summary>
        private static void LoadFromConfig()
        {
            for (int i = 0; i < KeybindRules.RowCount; i++)
            {
                bound[i] = KeybindRules.Default(i);
                if (!live.Ready) continue;
                string tok = null;
                try { tok = entries[i] != null ? entries[i].Value : null; } catch { }
                bound[i] = KeybindRules.LoadToken(i, tok);
            }
            if (!live.Ready) return;
            for (int i = 0; i < KeybindRules.RowCount; i++)
            {
                if (bound[i].Kind == BindKind.None) continue;
                int other;
                var refusal = KeybindRules.Refuse(i, bound[i], bound, CodesForKey, out other);
                if (refusal == Refusal.None) continue;
                Plugin.Log.LogWarning("[KEYBIND] config row " + KeybindRules.RowIds[i] + "=" + KeybindRules.FormatToken(bound[i])
                    + " refused (" + refusal + (other >= 0 ? " with " + KeybindRules.RowIds[other] : "") + "); default kept");
                bound[i] = KeybindRules.Default(i);
            }
        }

        /// <summary>The ONE writer of a binding (validate, write the registry
        /// and the config, re-apply every live set, then the caller refreshes
        /// the face - design section 2.3's order, all inside the handler).
        /// Returns the refusal; Refusal.None means written.</summary>
        internal static Refusal Write(int row, BindSource src, string via, out int other)
        {
            other = -1;
            if (row < 0 || row >= KeybindRules.RowCount || !RowsWritable) return Refusal.NoneAsBind;
            if (src.Kind != BindKind.None)
            {
                var r = KeybindRules.Refuse(row, src, bound, CodesForKey, out other);
                if (r != Refusal.None)
                {
                    Plugin.Log.LogInfo("[KEYBIND] refused " + KeybindRules.RowIds[row] + "=" + KeybindRules.FormatToken(src) + ": " + r
                        + (other >= 0 ? " (held by " + KeybindRules.RowIds[other] + ")" : "") + " via " + via);
                    return r;
                }
            }
            var before = bound[row];
            bound[row] = src;
            try { if (entries[row] != null) entries[row].Value = KeybindRules.FormatToken(src); }
            catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] config write " + KeybindRules.RowIds[row] + ": " + e.Message); }
            ReapplyAllLiveSets();
            if (!before.Equals(src)) announceOwed[row] = true;
            Revision++;
            Plugin.Log.LogInfo("[KEYBIND] write " + KeybindRules.RowIds[row] + " = " + KeybindRules.FormatToken(src)
                + " (was " + KeybindRules.FormatToken(before) + ") via " + via);
            return Refusal.None;
        }

        /// <summary>_x: the only unbind.</summary>
        internal static void Unbind(int row)
        {
            int other;
            Write(row, BindSource.None, "unbind", out other);
        }

        /// <summary>_r: back to today's key, no confirm.</summary>
        internal static Refusal ResetRow(int row)
        {
            int other;
            if (row < 0 || row >= KeybindRules.RowCount || !RowsWritable) return Refusal.NoneAsBind;
            var d = KeybindRules.Default(row);
            // A default can collide with a row the player moved onto it:
            // the per-row reset frees that row rather than refusing the reset.
            for (int r = 0; r < KeybindRules.RowCount; r++)
                if (r != row && KeybindRules.Overlap(d, bound[r], CodesForKey))
                    Write(r, BindSource.None, "reset of " + KeybindRules.RowIds[row] + " freed it", out other);
            return Write(row, d, "reset", out other);
        }

        /// <summary>Reset all, confirmed: every row to its default, applied once.</summary>
        internal static void ResetAll()
        {
            if (!RowsWritable) return;
            for (int i = 0; i < KeybindRules.RowCount; i++)
            {
                var d = KeybindRules.Default(i);
                if (!bound[i].Equals(d)) announceOwed[i] = true;
                bound[i] = d;
                try { if (entries[i] != null) entries[i].Value = KeybindRules.FormatToken(d); } catch { }
            }
            ReapplyAllLiveSets();
            Revision++;
            Plugin.Log.LogInfo("[KEYBIND] reset all: every row at its default");
        }

        // =================================================================
        // Reads - every mod hotkey reader asks these, never Input directly
        // =================================================================

        /// <summary>The capture owns the keyboard and mouse: while armed, on
        /// the frame it consumed an input, and until a mouse button it
        /// consumed has been seen up (design section 2.5 properties 6, 7).
        /// The FIRST statement of every mod hotkey reader.</summary>
        internal static bool CaptureOwnsInput
        {
            get { return captureRow >= 0 || CaptureConsumedFrame == Time.frameCount || ConsumedMouseButtonStillDown(); }
        }

        internal static bool KeybindCaptureActive { get { return captureRow >= 0; } }

        /// <summary>True while any key of the row's binding is held, or its
        /// mouse button is. False while the capture owns input.</summary>
        internal static bool Held(int row)
        {
            if (CaptureOwnsInput) return false;
            return ReadRow(row, Mode.Held) == Read.Down;
        }

        /// <summary>True on the frame a key of the row's binding went down.</summary>
        internal static bool Down(int row)
        {
            if (CaptureOwnsInput) return false;
            return ReadRow(row, Mode.Edge) == Read.Down;
        }

        /// <summary>IMGUI rows: this KeyDown event is the row's key.</summary>
        internal static bool Matches(int row, Event ev)
        {
            if (CaptureOwnsInput) return false;
            if (ev == null || ev.type != EventType.KeyDown || ev.keyCode == KeyCode.None) return false;
            foreach (int c in KeyCodesFor(row)) if ((int)ev.keyCode == c) return true;
            return false;
        }

        /// <summary>The row's key as a KeyUp event (the dance and quick-chat
        /// wheels' release in click mode, and nothing else).</summary>
        internal static bool MatchesUp(int row, Event ev)
        {
            if (ev == null || ev.type != EventType.KeyUp || ev.keyCode == KeyCode.None) return false;
            foreach (int c in KeyCodesFor(row)) if ((int)ev.keyCode == c) return true;
            return false;
        }

        private static Read ReadRow(int row, Mode mode)
        {
            if (row < 0 || row >= KeybindRules.RowCount) return Read.Up;
            var b = live.Ready ? bound[row] : KeybindRules.Default(row);
            if (b.Kind == BindKind.Mouse)
                return MouseRead(KeybindRules.MouseSourceToUnityIndex(b.Value), mode);
            var codes = KeyCodesFor(row);
            if (codes.Length == 0) return Read.Up;
            bool unreadable = false;
            foreach (int c in codes)
            {
                var r = KeyRead(c, mode);
                if (r == Read.Down) return Read.Down;
                if (r == Read.Unreadable) unreadable = true;
            }
            return unreadable ? Read.Unreadable : Read.Up;
        }

        private static Read KeyRead(int code, Mode mode)
        {
            try
            {
                bool d = mode == Mode.Held ? Input.GetKey((KeyCode)code) : Input.GetKeyDown((KeyCode)code);
                return d ? Read.Down : Read.Up;
            }
            catch { return Read.Unreadable; }
        }

        // -- the guarded mouse helper (design section 2.5 property 5) --------

        private static int mouseCap = int.MaxValue;
        private static readonly Func<int, bool> rawHeld = n => Input.GetMouseButton(n);
        private static readonly Func<int, bool> rawDown = n => Input.GetMouseButtonDown(n);
        private static readonly Action<int> onCapped = n => Plugin.Log.LogWarning("[KEYBIND] mouse button " + n + " unavailable");

        internal static Read MouseRead(int button, Mode mode)
        {
            return KeybindRules.GuardedMouseRead(button, ref mouseCap, mode == Mode.Held ? rawHeld : rawDown, onCapped);
        }

        internal static bool MouseHeld(int button) { return MouseRead(button, Mode.Held) == Read.Down; }
        internal static bool MouseDown(int button) { return MouseRead(button, Mode.Edge) == Read.Down; }

        /// <summary>A question the row face and T2 case h ask: the row's
        /// mouse button sits above this seat's cap.</summary>
        internal static bool BoundSourceUnreadable(int row)
        {
            return KeybindRules.MouseUnreadable(Bound(row), mouseCap);
        }

        // =================================================================
        // 2.7 - the one total accessor the achievement path reads through
        // =================================================================

        internal enum SrcKind { Row, LegacyKey, LegacyMouse, ActionFire, ActionMove, ActionJump }

        internal struct Src
        {
            internal readonly SrcKind Kind;
            internal readonly int Value;
            internal Src(SrcKind k, int v) { Kind = k; Value = v; }
            internal static Src Row(int row) { return new Src(SrcKind.Row, row); }
            internal static Src Legacy(KeyCode c) { return new Src(SrcKind.LegacyKey, (int)c); }
            internal static Src LegacyMouse(int n) { return new Src(SrcKind.LegacyMouse, n); }
            public override string ToString()
            {
                return Kind == SrcKind.Row ? KeybindRules.RowIds[Value] : Kind == SrcKind.LegacyKey ? ((KeyCode)Value).ToString()
                     : Kind == SrcKind.LegacyMouse ? "Mouse" + Value : Kind.ToString();
            }
        }

        internal static readonly Src ActionFire = new Src(SrcKind.ActionFire, 0);
        internal static readonly Src ActionMove = new Src(SrcKind.ActionMove, 0);
        internal static readonly Src ActionJump = new Src(SrcKind.ActionJump, 0);

        /// <summary>T2 case h / T4's seam: when set, every read through the
        /// accessor of this source throws inside the accessor, which must
        /// answer Unreadable.</summary>
        internal static SrcKind? ThrowingSourceForTest;
        internal static int ThrowingRowForTest = -1;

        /// <summary>TOTAL by construction: every call inside is contained and
        /// every exception becomes Unreadable. It cannot throw.</summary>
        internal static Read ReadBoundSource(Src src, Mode mode)
        {
            try
            {
                if (ThrowingSourceForTest.HasValue && ThrowingSourceForTest.Value == src.Kind
                    && (src.Kind != SrcKind.Row || ThrowingRowForTest < 0 || ThrowingRowForTest == src.Value))
                    throw new InvalidOperationException("test seam: a throwing read");
                switch (src.Kind)
                {
                    case SrcKind.Row: return ReadRow(src.Value, mode);
                    case SrcKind.LegacyKey: return KeyRead(src.Value, mode);
                    case SrcKind.LegacyMouse: return MouseRead(src.Value, mode);
                    default: return ActionRead(src.Kind, mode);
                }
            }
            catch { return Read.Unreadable; }
        }

        /// <summary>The bound source of one row (the advisory counters' form).</summary>
        internal static Read ReadBoundSource(int row, Mode mode)
        {
            return ReadBoundSource(Src.Row(row), mode);
        }

        /// <summary>This seat's own PlayerAction for the action term (the
        /// OverlayInputGate.FireHeldPhysically shape). No local player is
        /// Up - there is nothing to read; a read that throws is Unreadable.</summary>
        private static Read ActionRead(SrcKind kind, Mode mode)
        {
            PlayerActions a = LocalActions();
            if (a == null) return Read.Up;
            bool hit;
            switch (kind)
            {
                case SrcKind.ActionFire:
                    hit = mode == Mode.Held ? (a.Fire.IsPressed || a.Fire.WasPressed || a.Fire.WasReleased) : a.Fire.WasPressed;
                    break;
                case SrcKind.ActionJump:
                    hit = mode == Mode.Held ? (a.Jump.IsPressed || a.Up.IsPressed) : (a.Jump.WasPressed || a.Up.WasPressed);
                    break;
                default:
                    hit = mode == Mode.Held
                        ? (a.Left.IsPressed || a.Right.IsPressed || a.Up.IsPressed || a.Down.IsPressed || a.Jump.IsPressed)
                        : (a.Left.WasPressed || a.Right.WasPressed || a.Up.WasPressed || a.Down.WasPressed || a.Jump.WasPressed);
                    break;
            }
            return hit ? Read.Down : Read.Up;
        }

        private static int localFrame = -1;
        private static CharacterData localData;

        /// <summary>This seat's own CharacterData, resolved at most once a
        /// frame. Null when none resolves (menu, spawn window).</summary>
        internal static CharacterData LocalCharacter()
        {
            if (localFrame == Time.frameCount) return localData;
            localFrame = Time.frameCount;
            localData = null;
            var pm = PlayerManager.instance;
            if (pm == null || pm.players == null) return null;
            foreach (var p in pm.players)
            {
                if (p == null) continue;
                var pv = p.GetComponent<Photon.Pun.PhotonView>();
                if (pv == null || !pv.IsMine) continue;
                localData = p.GetComponent<CharacterData>();
                break;
            }
            return localData;
        }

        private static PlayerActions LocalActions()
        {
            var d = LocalCharacter();
            return d != null ? d.playerActions : null;
        }

        // =================================================================
        // 2.3 - Mechanism A: the registry and the one writer of game bindings
        // =================================================================

        private static readonly List<WeakReference> liveSets = new List<WeakReference>();
        private static bool suppressRegister;

        /// <summary>Every keyboard-created set, from the factory postfix.</summary>
        internal static void Register(PlayerActions set)
        {
            if (set == null || suppressRegister) return;
            liveSets.RemoveAll(w => !w.IsAlive);
            liveSets.Add(new WeakReference(set));
            ApplyGameBindings(set);
        }

        internal static int LiveSetCount { get { liveSets.RemoveAll(w => !w.IsAlive); return liveSets.Count; } }

        /// <summary>Every accepted capture, every per-row reset and the
        /// reset-all confirm call this before they return: two local sets in
        /// a 2v2 lobby change together, in one synchronous call.</summary>
        internal static void ReapplyAllLiveSets()
        {
            liveSets.RemoveAll(w => !w.IsAlive);
            int n = 0;
            foreach (var w in liveSets.ToArray())
            {
                var s = w.Target as PlayerActions;
                if (s == null) continue;
                try { ApplyGameBindings(s); n++; }
                catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] apply: " + e.Message); }
            }
            try { ReadyPromptPatches.RefreshAll(); } catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] prompt refresh: " + e.Message); }
            Plugin.Log.LogInfo("[KEYBIND] re-applied " + n + " live set(s)");
        }

        internal static void ApplyGameBindings(PlayerActions set)
        {
            ApplyGameBindings(set, bound, live);
        }

        /// <summary>The four steps against one set, no yield between them:
        /// ResetBindings (factory state, no orphans), snapshot, soft-remove
        /// every key/mouse entry not equal to the desired source, add a fresh
        /// source only when none is already equal. Controller sources are
        /// outside the partition. Not run while the accessor is not
        /// validated: the factory defaults are what the player has.</summary>
        private static void ApplyGameBindings(PlayerActions set, BindSource[] cfg, MappingState st)
        {
            if (set == null || st == null || !st.Ready) return;
            ApplyAction(set.Up, cfg[MoveUp]);
            ApplyAction(set.Down, cfg[MoveDown]);
            ApplyAction(set.Left, cfg[MoveLeft]);
            ApplyAction(set.Right, cfg[MoveRight]);
            ApplyAction(set.Jump, cfg[Jump]);
            ApplyAction(set.Fire, cfg[Fire]);
            ApplyAction(set.Block, cfg[Block]);
        }

        private static BindingSource MakeSource(BindSource b)
        {
            if (b.Kind == BindKind.Key) return new KeyBindingSource((Key)b.Value);
            if (b.Kind == BindKind.Mouse) return new MouseBindingSource((Mouse)b.Value);
            return null;
        }

        private static void ApplyAction(PlayerAction action, BindSource want)
        {
            if (action == null) return;
            int mut = KeybindRules.Mut;
            // 1
            if (mut == 102) action.ClearBindings();
            else if (mut != 103) action.ResetBindings();
            // 2
            var desired = MakeSource(want);
            var snapshot = new List<BindingSource>(action.UnfilteredBindings);
            bool haveEqual = false;
            var remove = new List<BindingSource>();
            foreach (var b in snapshot)
            {
                if (!(b is KeyBindingSource) && !(b is MouseBindingSource)) continue;   // controller untouched
                if (desired != null && mut != 101 && b.Equals(desired)) haveEqual = true;
                else remove.Add(b);
            }
            // 3
            foreach (var b in remove) action.RemoveBinding(b);
            // 4
            if (desired != null && !haveEqual) action.AddBinding(MakeSource(want));
        }

        /// <summary>Patch head of Mechanism A: both callers of the keyboard
        /// factory (vanilla PlayerAssigner and the mod's 2v2 CreatePlayer
        /// prefix) reach it.</summary>
        [HarmonyPatch(typeof(PlayerActions), nameof(PlayerActions.CreateWithKeyboardBindings))]
        internal static class KeyboardFactoryPatch
        {
            private static bool logged;

            [HarmonyPostfix]
            private static void Postfix(PlayerActions __result)
            {
                try
                {
                    Register(__result);
                    if (!logged && !suppressRegister && __result != null)
                    {
                        logged = true;
                        Plugin.Log.LogInfo("[KEYBIND] factory hook live: keyboard set registered and applied");
                    }
                }
                catch (Exception e) { VanillaFixSupport.DiagLimited("KeybindFactory", "postfix: " + e.Message, 3); }
            }

            [HarmonyCleanup]
            private static Exception Cleanup(MethodBase original, Exception exception)
            {
                if (original != null) return exception;
                return VanillaFixSupport.Cleanup("KeybindFactory", exception);
            }
        }

        // =================================================================
        // 2.4 - Mechanism B: three raw reads, whole-call transpilers
        // =================================================================

        /// <summary>Target of the transpiled ready-up and map-art reads.
        /// Public: a call target inside game IL. Logs once per row.</summary>
        public static bool VanillaHeld(int row)
        {
            NoteHook(row, "held");
            try { return Held(row); } catch { return false; }
        }

        public static bool VanillaDown(int row)
        {
            NoteHook(row, "edge");
            try { return Down(row); } catch { return false; }
        }

        private static readonly HashSet<string> hooksSeen = new HashSet<string>();
        private static void NoteHook(int row, string kind)
        {
            string k = row + kind;
            if (hooksSeen.Contains(k)) return;
            hooksSeen.Add(k);
            VanillaFixSupport.DiagLimited("KeybindHook" + k, "[KEYBIND] transpiled " + kind + " read live for "
                + (row >= 0 && row < KeybindRules.RowCount ? KeybindRules.RowIds[row] : row.ToString()), 1);
        }

        internal enum MatchMode { Pair, AnyGetKey, OpcodeOnly }

        /// <summary>The matcher every transpiler uses: a constant load whose
        /// VALUE is the KeyCode ordinal (Ldc_I4, Ldc_I4_S or a singleton,
        /// via LoadsConstant) immediately followed by the Input call. The
        /// pair is rewritten to (row id, Keybinds hook): same arity, same
        /// return type, no body copied. Returns the number of pairs found;
        /// the transpiler throws unless it is exactly 1 (#83). The two other
        /// modes are T3's mutations 1 and 3, run against the real IL in the
        /// in-game self-test, never by a patch.</summary>
        internal static int RewritePairs(List<CodeInstruction> code, int keyCode, MethodInfo inputCall, int row,
                                         MethodInfo hook, MatchMode mode)
        {
            int found = 0;
            for (int i = 0; i + 1 < code.Count; i++)
            {
                var next = code[i + 1];
                bool isCall = (next.opcode == OpCodes.Call || next.opcode == OpCodes.Callvirt) && next.operand is MethodInfo;
                if (!isCall) continue;
                var mi = (MethodInfo)next.operand;
                bool callMatch = mode == MatchMode.AnyGetKey
                    ? mi.DeclaringType == typeof(Input) && mi.Name.StartsWith("GetKey", StringComparison.Ordinal)
                    : mi == inputCall;
                if (!callMatch) continue;
                bool loadMatch = mode == MatchMode.OpcodeOnly
                    ? code[i].opcode == OpCodes.Ldc_I4 && code[i].operand is int && (int)code[i].operand == keyCode
                    : mode == MatchMode.AnyGetKey ? true : code[i].LoadsConstant(keyCode);
                if (!loadMatch) continue;
                found++;
                if (hook != null)
                {
                    code[i].opcode = OpCodes.Ldc_I4;
                    code[i].operand = row;
                    next.opcode = OpCodes.Call;
                    next.operand = hook;
                }
            }
            return found;
        }

        private static readonly MethodInfo InputGetKey = AccessTools.Method(typeof(Input), nameof(Input.GetKey), new[] { typeof(KeyCode) });
        private static readonly MethodInfo InputGetKeyDown = AccessTools.Method(typeof(Input), nameof(Input.GetKeyDown), new[] { typeof(KeyCode) });
        private static readonly MethodInfo HookHeld = AccessTools.Method(typeof(Keybinds), nameof(VanillaHeld));
        private static readonly MethodInfo HookDown = AccessTools.Method(typeof(Keybinds), nameof(VanillaDown));

        private static IEnumerable<CodeInstruction> Rewrite(IEnumerable<CodeInstruction> instructions, string site, int keyCode,
                                                            MethodInfo inputCall, int row, MethodInfo hook)
        {
            if (inputCall == null || hook == null)
                throw new InvalidOperationException("Keybind " + site + ": reflection targets missing");
            var code = new List<CodeInstruction>(instructions);
            int n = RewritePairs(code, keyCode, inputCall, row, hook, MatchMode.Pair);
            if (n != 1)
                throw new InvalidOperationException("Keybind " + site + ": expected exactly 1 (load " + keyCode + ", "
                    + inputCall.Name + ") pair, found " + n.ToString(CultureInfo.InvariantCulture));
            return code;
        }

        [HarmonyPatch(typeof(PlayerAssigner), "LateUpdate")]
        internal static class LobbyReadyPatch
        {
            [HarmonyTranspiler]
            private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
            {
                return Rewrite(instructions, "PlayerAssigner.LateUpdate", (int)KeyCode.Space, InputGetKey, Jump, HookHeld);
            }

            [HarmonyCleanup]
            private static Exception Cleanup(MethodBase original, Exception exception)
            {
                if (original != null) return exception;
                return VanillaFixSupport.Cleanup("KeybindLobbyReady", exception);
            }
        }

        [HarmonyPatch(typeof(CharacterSelectionInstance), "Update")]
        internal static class CharacterReadyPatch
        {
            [HarmonyTranspiler]
            private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
            {
                return Rewrite(instructions, "CharacterSelectionInstance.Update", (int)KeyCode.Space, InputGetKeyDown, Jump, HookDown);
            }

            [HarmonyCleanup]
            private static Exception Cleanup(MethodBase original, Exception exception)
            {
                if (original != null) return exception;
                return VanillaFixSupport.Cleanup("KeybindCharacterReady", exception);
            }
        }

        [HarmonyPatch(typeof(ArtHandler), "Update")]
        internal static class MapArtPatch
        {
            [HarmonyTranspiler]
            private static IEnumerable<CodeInstruction> Transpiler(IEnumerable<CodeInstruction> instructions)
            {
                return Rewrite(instructions, "ArtHandler.Update", (int)KeyCode.LeftShift, InputGetKeyDown, MapSkinCycle, HookDown);
            }

            [HarmonyCleanup]
            private static Exception Cleanup(MethodBase original, Exception exception)
            {
                if (original != null) return exception;
                return VanillaFixSupport.Cleanup("KeybindMapArt", exception);
            }
        }

        // =================================================================
        // 2.5 - capture
        // =================================================================

        private static int captureRow = -1;
        private static float captureArmedAt;
        private static readonly bool[] mouseSeenUp = new bool[7];
        internal static int CaptureConsumedFrame = -1;
        private static int consumedMouseButton = -1;
        internal const float CaptureExpirySeconds = 6f;

        internal static int CaptureRow { get { return captureRow; } }
        internal static Refusal LastRefusal { get; private set; }
        internal static int LastRefusalRow { get; private set; } = -1;
        internal static int LastRefusalOther { get; private set; } = -1;
        internal static BindSource LastRefusedSource { get; private set; }
        internal static int Revision { get; private set; }

        /// <summary>The driven-input seam (the item 13 drive precedent, #420):
        /// a KeyMappings row or a Unity mouse button the next capture poll
        /// reads as down, so the in-game check exercises the real capture
        /// path - FirstHit, CaptureGesture, Refuse, Write - end to end.</summary>
        internal static int DriveKeyRow = -1, DriveMouseButton = -1;

        private static bool ConsumedMouseButtonStillDown()
        {
            if (consumedMouseButton < 0) return false;
            if (MouseRead(consumedMouseButton, Mode.Held) == Read.Down || DriveMouseButton == consumedMouseButton) return true;
            consumedMouseButton = -1;
            return false;
        }

        /// <summary>A click on SKb&lt;Id&gt;_b: arm the row. Refused while the
        /// accessor is not validated (the rows are read-only).</summary>
        internal static bool ArmCapture(int row)
        {
            if (row < 0 || row >= KeybindRules.RowCount || !RowsWritable) return false;
            captureRow = row;
            captureArmedAt = Time.unscaledTime;
            for (int n = 0; n < mouseSeenUp.Length; n++) mouseSeenUp[n] = MouseRead(n, Mode.Held) != Read.Down;
            LastRefusal = Refusal.None;
            LastRefusalRow = LastRefusalOther = -1;
            Revision++;
            Plugin.Log.LogInfo("[KEYBIND] capture armed on " + KeybindRules.RowIds[row]);
            return true;
        }

        internal static void CancelCapture(string why)
        {
            if (captureRow < 0) return;
            Plugin.Log.LogInfo("[KEYBIND] capture cancelled on " + KeybindRules.RowIds[captureRow] + " (" + why + ")");
            captureRow = -1;
            CaptureConsumedFrame = Time.frameCount;
            Revision++;
        }

        /// <summary>Per frame, from NativeUI.Tick beside item 13's key poll,
        /// behind its gate ladder. Returns true when the capture consumed
        /// this frame (the page's own key dispatch must then stand down).</summary>
        internal static bool PollCapture()
        {
            if (captureRow < 0) return false;
            if (Time.unscaledTime - captureArmedAt > CaptureExpirySeconds) { CancelCapture("expired after 6 s"); return true; }
            int row = captureRow;
            // keys, in KeyMappings order
            var down = new List<int>(2);
            if (DriveKeyRow > 0) { down.Add(DriveKeyRow); DriveKeyRow = -1; }
            else
            {
                for (int k = 1; k < KeybindRules.KeyTableLength; k++)
                    foreach (int c in CodesForKey(k))
                        if (KeyRead(c, Mode.Edge) == Read.Down) { down.Add(k); break; }
            }
            int hit = KeybindRules.FirstHit(down.ToArray());
            var g = KeybindRules.CaptureGesture(hit, true);
            if (g == Gesture.Cancel) { CancelCapture("escape"); return true; }
            if (g == Gesture.Bind) { Accept(row, BindSource.Key(hit), -1); return true; }
            // mouse, game rows only (rule 4 is a mechanism here: the poll never reads one for a mod row)
            if (!KeybindRules.IsGameRow(row)) return true;
            for (int n = 0; n < mouseSeenUp.Length; n++)
            {
                bool drivenDown = DriveMouseButton == n;
                if (!mouseSeenUp[n])
                {
                    if (!drivenDown && MouseRead(n, Mode.Held) != Read.Down) mouseSeenUp[n] = true;
                    continue;   // the arming click is not the binding
                }
                if (drivenDown || MouseRead(n, Mode.Edge) == Read.Down)
                {
                    if (drivenDown) DriveMouseButton = -1;
                    Accept(row, KeybindRules.MouseIndexToSource(n), n);
                    return true;
                }
            }
            return true;
        }

        /// <summary>T2 case h: would the poll capture Unity button n now?
        /// A capped button never reads Down, so it can never be written.</summary>
        internal static bool CaptureCanSeeMouse(int n)
        {
            return MouseRead(n, Mode.Held) != Read.Unreadable;
        }

        private static void Accept(int row, BindSource src, int mouseButton)
        {
            int other;
            var r = Write(row, src, "capture", out other);
            captureRow = -1;
            CaptureConsumedFrame = Time.frameCount;
            if (mouseButton >= 0) consumedMouseButton = mouseButton;
            LastRefusal = r;
            LastRefusalRow = r == Refusal.None ? -1 : row;
            LastRefusalOther = other;
            LastRefusedSource = src;
            Revision++;
        }

        /// <summary>Per frame from the plugin's Update: the capture expires
        /// and self-cancels when its page is gone, even if nothing polls it
        /// (expiring by default needs no cleanup path, #276/#430).</summary>
        internal static void FrameTick()
        {
            if (captureRow >= 0)
            {
                bool pageUp = false;
                try { pageUp = NativeUI.KeybindCaptureSurfaceVisible(); } catch { }
                if (!pageUp) CancelCapture("the Controls page is not open");
                else if (Time.unscaledTime - captureArmedAt > CaptureExpirySeconds) CancelCapture("expired after 6 s");
            }
            try { SelfTestTick(); } catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] self-test tick: " + e.Message); stState = -1; }
        }

        // =================================================================
        // 2.5 - the ChatChannel physical tap detector
        // =================================================================

        /// <summary>The real frame source (KeybindRules.IFrameInput). KeyDown
        /// is Input.GetKeyDown for any KeyCode, mouse buttons included
        /// (Mouse0-Mouse6); TypedText is Input.inputString, the independent
        /// keyboard channel that carries characters from keys no KeyCode
        /// names. A key read that throws counts as a key edge and a thrown
        /// inputString as typed text; a mouse read that throws counts as no
        /// edge: unreadable input is attributed Key or Unknown, never the
        /// mouse.</summary>
        private sealed class RealInput : IFrameInput
        {
            public bool KeyDown(int code)
            {
                var r = KeyRead(code, Mode.Edge);
                return r == Read.Down || (r == Read.Unreadable && !KeybindRules.IsMouseCode(code));
            }
            public bool KeyUp(int code) { try { return Input.GetKeyUp((KeyCode)code); } catch { return false; } }
            public bool AnyKeyDown() { try { return Input.anyKeyDown; } catch { return true; } }
            public string TypedText() { try { return Input.inputString; } catch { return "?"; } }
            public bool AnyMouseHeld() { for (int n = 0; n < 7; n++) if (MouseHeld(n)) return true; return false; }
            public float Now() { return Time.unscaledTime; }
            public bool Focused() { return Application.isFocused; }
        }

        private static int[] fullKeyScan;

        /// <summary>F2: the detector's scan is every member of Unity's KeyCode
        /// enum - every key, mouse button and joystick button the legacy input
        /// can report, the set Input.anyKeyDown is computed over - not
        /// InControl's 127-code table. Resolved once.</summary>
        internal static int[] FullKeyScan()
        {
            if (fullKeyScan != null) return fullKeyScan;
            var seen = new HashSet<int>();
            var l = new List<int>();
            try
            {
                foreach (var v in Enum.GetValues(typeof(KeyCode)))
                {
                    int c = (int)(KeyCode)v;
                    if (c > 0 && seen.Add(c)) l.Add(c);
                }
            }
            catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] KeyCode enumeration: " + e.Message); }
            foreach (int c in ScanSet()) if (seen.Add(c)) l.Add(c);
            for (int c = KeybindRules.KeyCodeMouse0; c <= KeybindRules.KeyCodeMouse6; c++) if (seen.Add(c)) l.Add(c);
            fullKeyScan = l.ToArray();
            return fullKeyScan;
        }

        private static readonly KeybindRules.TapDetector chatTap = new KeybindRules.TapDetector();
        private static readonly RealInput realInput = new RealInput();

        /// <summary>The chat box opened or closed: drop any half-seen hold.</summary>
        internal static void ResetChatTap() { chatTap.Held = chatTap.Clean = false; }

        /// <summary>Per frame from CompetitiveUI while the chat box is open:
        /// true on the frame the bound ChatChannel key was tapped.</summary>
        internal static bool ChatChannelTapped(bool chatInputOpen)
        {
            if (CaptureOwnsInput) { chatTap.Held = chatTap.Clean = false; return false; }
            if (!chatInputOpen) { chatTap.Held = chatTap.Clean = false; return false; }
            return chatTap.Step(realInput, KeyCodesFor(ChatChannel), FullKeyScan());
        }

        // =================================================================
        // Q5 - one local toast at the next round start after a rebind
        // =================================================================

        internal static void OnRoundStart()
        {
            var rows = new List<int>();
            for (int i = 0; i < KeybindRules.RowCount; i++) if (announceOwed[i]) { rows.Add(i); announceOwed[i] = false; }
            if (rows.Count == 0) return;
            string text = NativeUI.KeybindChangedToast(rows);
            if (string.IsNullOrEmpty(text)) return;
            CompetitiveUI.QueueNotification(text, new Color(0.55f, 0.85f, 1f), 6f);
            Plugin.Log.LogInfo("[KEYBIND] round-start toast for " + string.Join(",", rows.Select(r => KeybindRules.RowIds[r]).ToArray()));
        }

        // =================================================================
        // T2 - SelfTestInControl, on every launch, against throwaway sets
        // =================================================================

        private static int stState;          // 0 not started, 1 built, 2 done, -1 failed
        private static int stApplyFrame;
        private static readonly List<string> stLines = new List<string>();
        private static int stPass, stFail;
        private static int stMutation;
        private static readonly Queue<int> stMutQueue = new Queue<int>();
        private static string stMutTag = "";
        private static PlayerActions sA, sB, sC, sD, sE, sF;
        private static bool sCOnApply;
        private static int sEBuilt;

        /// <summary>The mutation battery is run when the lever
        /// "keybind:mutations" asks for it (one process, every mutation in
        /// turn, each with its expected reds and controls checked).</summary>
        internal static void RequestMutationBattery()
        {
            stMutQueue.Clear();
            foreach (int m in new[] { 101, 102, 103, 104, 105, 106, 107, 108 }) stMutQueue.Enqueue(m);
            if (stState == 2 || stState == -1) stState = 0;
            Plugin.Log.LogInfo("[KEYBIND] mutation battery queued: 8 mutations");
        }

        private static void SelfTestTick()
        {
            if (stState == 2 && stMutQueue.Count > 0 && stMutation == 0) { stMutation = stMutQueue.Dequeue(); stState = 0; }
            if (stState != 0 && stState != 1) return;
            if (stState == 0)
            {
                if (Time.unscaledTime < 8f) return;
                if (!InputManager.IsSetup) return;
                StBuild();
                return;
            }
            if (Time.frameCount <= stApplyFrame) return;
            StCheck();
        }

        private static void StOk(string name, string got) { stPass++; stLines.Add("PASS | " + name + " | " + got); }
        private static void StBad(string name, string got) { stFail++; stLines.Add("FAIL | " + name + " | " + got); }
        private static void St(string name, bool ok, string got) { if (ok) StOk(name, got); else StBad(name, got); }

        private static BindSource[] Cfg(params KeyValuePair<int, BindSource>[] over)
        {
            var a = new BindSource[KeybindRules.RowCount];
            for (int i = 0; i < a.Length; i++) a[i] = KeybindRules.Default(i);
            foreach (var kv in over) a[kv.Key] = kv.Value;
            return a;
        }

        private static KeyValuePair<int, BindSource> P(int row, BindSource s) { return new KeyValuePair<int, BindSource>(row, s); }

        private static MappingState stMapping;

        private static void StBuild()
        {
            stLines.Clear();
            stPass = stFail = 0;
            KeybindRules.Mut = stMutation;
            stMutTag = stMutation == 0 ? "" : " [mutation " + (stMutation - 100) + "]";
            stMapping = stMutation == 105 ? ResolveMapping("sourse") : live;
            suppressRegister = true;
            try
            {
                var kK = BindSource.Key((int)Key.K);
                sA = PlayerActions.CreateWithKeyboardBindings();
                ApplyGameBindings(sA, Cfg(), stMapping);
                sB = PlayerActions.CreateWithKeyboardBindings();
                ApplyGameBindings(sB, Cfg(P(Jump, kK)), stMapping);
                sC = PlayerActions.CreateWithKeyboardBindings();
                ApplyGameBindings(sC, Cfg(P(Jump, kK)), stMapping);
                ApplyGameBindings(sC, Cfg(), stMapping);
                sCOnApply = OneEntry(sC.Jump, BindSource.Key((int)Key.Space));
                sD = PlayerActions.CreateWithKeyboardBindings();
                sD.Jump.AddDefaultBinding(InputControlType.Action1);
                ApplyGameBindings(sD, Cfg(P(Jump, kK)), stMapping);
                sE = PlayerActions.CreateWithControllerBindings();
                sEBuilt = CountSources(sE);
                sF = PlayerActions.CreateWithKeyboardBindings();
                ApplyGameBindings(sF, Cfg(P(Fire, BindSource.None)), stMapping);
            }
            finally { suppressRegister = false; }
            stApplyFrame = Time.frameCount;
            stState = 1;
            // Mutation 4 (T2): read on the APPLY frame instead of the next one.
            if (stMutation == 104) StCheck();
        }

        private static IEnumerable<PlayerAction> Actions(PlayerActions s)
        {
            return new[] { s.Fire, s.Block, s.Jump, s.Up, s.Down, s.Left, s.Right, s.Start, s.MuteBlock, s.Chat,
                           s.AimLeft, s.AimRight, s.AimUp, s.AimDown };
        }

        private static int CountSources(PlayerActions s)
        {
            int n = 0;
            foreach (var a in Actions(s)) if (a != null) n += a.UnfilteredBindings.Count;
            return n;
        }

        private static string Describe(PlayerAction a)
        {
            if (a == null) return "(null)";
            return "[" + string.Join(",", a.UnfilteredBindings.Select(b => b.BindingSourceType + ":" + b.Name
                + (BoundTo(b) == a ? "" : "(orphan)")).ToArray()) + "]";
        }

        // BindingSource.BoundTo is internal to InControl (only Assembly-CSharp is
        // publicized): read it by reflection, resolved once. Unresolved reads
        // null, which no case accepts as "bound to its action".
        private static MemberInfo boundToMember;
        private static bool boundToResolved;
        private static PlayerAction BoundTo(BindingSource b)
        {
            if (b == null) return null;
            if (!boundToResolved)
            {
                boundToResolved = true;
                boundToMember = (MemberInfo)AccessTools.Property(typeof(BindingSource), "BoundTo")
                                ?? AccessTools.Field(typeof(BindingSource), "BoundTo");
                if (boundToMember == null) Plugin.Log.LogWarning("[KEYBIND] T2: BindingSource.BoundTo not found");
            }
            try
            {
                var p = boundToMember as PropertyInfo;
                if (p != null) return p.GetValue(b, null) as PlayerAction;
                var f = boundToMember as FieldInfo;
                if (f != null) return f.GetValue(b) as PlayerAction;
            }
            catch { }
            return null;
        }

        private static bool OneEntry(PlayerAction a, BindSource want)
        {
            if (a == null || a.UnfilteredBindings.Count != 1) return false;
            var b = a.UnfilteredBindings[0];
            return BoundTo(b) == a && b.Equals(MakeSource(want));
        }

        private static void StCheck()
        {
            stState = 2;
            try { StCases(); }
            catch (Exception e) { StBad("self-test threw", e.GetType().Name + ": " + e.Message); }
            finally
            {
                foreach (var s in new[] { sA, sB, sC, sD, sE, sF }) { try { if (s != null) s.Destroy(); } catch { } }
                sA = sB = sC = sD = sE = sF = null;
                KeybindRules.Mut = 0;
            }
            foreach (var l in stLines) Plugin.Log.LogInfo("[KEYBIND] T2" + stMutTag + " " + l);
            string verdict = stFail == 0 ? "PASS" : "FAIL";
            Plugin.Log.LogInfo("[KEYBIND] T2" + stMutTag + " SelfTestInControl run=" + (stPass + stFail) + " fail=" + stFail + " verdict=" + verdict);
            if (stMutation != 0) StMutationVerdict();
            stMutation = 0;
        }

        private static readonly Dictionary<string, bool> stCaseOk = new Dictionary<string, bool>();

        private static void Case(string id, bool ok, string got)
        {
            stCaseOk[id] = ok;
            St("case " + id, ok, got);
        }

        private static void StCases()
        {
            stCaseOk.Clear();
            var kK = BindSource.Key((int)Key.K);
            // a - defaults: nine sources survive, each bound to its action
            int nA = 0; bool boundA = true;
            foreach (var a in Actions(sA)) foreach (var b in a.UnfilteredBindings) { nA++; if (BoundTo(b) != a) boundA = false; }
            Case("a defaults: exactly nine sources, each BoundTo its action", nA == 9 && boundA
                 && OneEntry(sA.Jump, BindSource.Key((int)Key.Space)) && OneEntry(sA.Fire, BindSource.Mouse((int)Mouse.LeftButton)),
                 "sources=" + nA + " bound=" + boundA + " Jump=" + Describe(sA.Jump));
            // b - rebind Jump to K
            bool othersB = OneEntry(sB.Fire, BindSource.Mouse((int)Mouse.LeftButton)) && OneEntry(sB.Block, BindSource.Mouse((int)Mouse.RightButton))
                && OneEntry(sB.Up, BindSource.Key((int)Key.W)) && OneEntry(sB.Down, BindSource.Key((int)Key.S))
                && OneEntry(sB.Left, BindSource.Key((int)Key.A)) && OneEntry(sB.Right, BindSource.Key((int)Key.D))
                && OneEntry(sB.Start, BindSource.Key((int)Key.Return)) && OneEntry(sB.MuteBlock, BindSource.Key((int)Key.Tab));
            Case("b rebind: Jump holds exactly key:K the frame after the apply, the rest unchanged",
                 OneEntry(sB.Jump, kK) && othersB, "Jump=" + Describe(sB.Jump) + " others=" + othersB);
            // c - two writes in one frame
            Case("c two writes, one frame: Jump holds exactly key:Space on the apply frame and after",
                 sCOnApply && OneEntry(sC.Jump, BindSource.Key((int)Key.Space)), "applyFrame=" + sCOnApply + " now=" + Describe(sC.Jump));
            // d - synthetic mixed set: the device source survives
            bool dKey = false, dDev = false; int dN = sD.Jump.UnfilteredBindings.Count;
            foreach (var b in sD.Jump.UnfilteredBindings)
            {
                if (b.Equals(MakeSource(kK)) && BoundTo(b) == sD.Jump) dKey = true;
                if (b is DeviceBindingSource && BoundTo(b) == sD.Jump) dDev = true;
            }
            Case("d mixed: Jump carries key:K and the DeviceBindingSource, nothing else", dKey && dDev && dN == 2, Describe(sD.Jump));
            // e - controller set, never registered, never applied
            int eNow = CountSources(sE);
            Case("e controller (control): all seventeen sources survive both frames", sEBuilt == 17 && eNow == 17,
                 "built=" + sEBuilt + " now=" + eNow + " liveRegistry=" + LiveSetCount);
            // f - unbound Fire
            bool fNone = sF.Fire.UnfilteredBindings.All(b => !(b is KeyBindingSource) && !(b is MouseBindingSource));
            Case("f unbound: Fire carries no key and no mouse source", fNone, Describe(sF.Fire));
            // g - the mapping accessor
            Case("g accessor: MappingReady, five steps passed, the three anchors hold",
                 stMapping.Ready && SameSet(CodesForKey(stMapping, (int)Key.Shift), 304, 303)
                 && SameSet(CodesForKey(stMapping, (int)Key.Alt), 308, 307) && SameSet(CodesForKey(stMapping, (int)Key.A), 97),
                 "ready=" + stMapping.Ready + (stMapping.Ready ? "" : " failure=" + stMapping.Failure));
            // h - an unreadable mouse source
            int savedCap = mouseCap; var savedFire = bound[Fire];
            bool hThrew = false; Read hRead = Read.Up; bool hUnreadable = false, hLow = false, hCapture = true;
            try
            {
                mouseCap = 3;
                bound[Fire] = BindSource.Mouse((int)Mouse.Button4);
                try { hRead = ReadBoundSource(Src.Row(Fire), Mode.Held); } catch { hThrew = true; }
                if (KeybindRules.Mut == 106)
                {
                    // the accessor made partial: the raw read it wraps, unguarded
                    try { hRead = Input.GetMouseButton(KeybindRules.MouseSourceToUnityIndex(bound[Fire].Value) + 100) ? Read.Down : Read.Up; }
                    catch { hThrew = true; }
                }
                hUnreadable = BoundSourceUnreadable(Fire);
                hLow = MouseRead(0, Mode.Held) != Read.Unreadable;
                hCapture = CaptureCanSeeMouse(3);
            }
            finally { mouseCap = savedCap; bound[Fire] = savedFire; }
            Case("h unreadable mouse: Fire on Button4 above the cap reads Unreadable, throws nothing; low buttons answer; capture cannot see button 3",
                 !hThrew && hRead == Read.Unreadable && hUnreadable && hLow && !hCapture,
                 "read=" + hRead + " threw=" + hThrew + " unreadable=" + hUnreadable + " low=" + hLow + " captureSees3=" + hCapture);
            // i - the two scan sets agree
            var union = new HashSet<int>();
            if (stMapping.Ready) for (int k = 1; k < KeybindRules.KeyTableLength; k++) foreach (int c in CodesForKey(stMapping, k)) union.Add(c);
            var st = KeybindRules.StaticKeyScan;
            Case("i scan sets: the runtime union over rows 1-131 set-equals StaticKeyScan, which holds 127 with no duplicate",
                 stMapping.Ready && union.SetEquals(st) && st.Length == 127 && new HashSet<int>(st).Count == st.Length,
                 "union=" + union.Count + " static=" + st.Length + " distinct=" + new HashSet<int>(st).Count);
            // j - the failed-validation state, end to end
            CaseJ();
        }

        private static void CaseJ()
        {
            var failed = ResolveMapping("sourse");    // forced to fail through the seam
            bool notReady = !failed.Ready;
            // every row reads its default in that state, whatever the config holds
            bool defaults = true;
            for (int i = 0; i < KeybindRules.RowCount; i++)
            {
                var want = KeybindRules.StaticDefaults[i];
                if (!new HashSet<int>(KeyCodesFor(failed, i)).SetEquals(want)) defaults = false;
            }
            // The production scan (every KeyCode member), not a table: F2.
            int[] alias = KeyCodesFor(failed, ChatChannel), scan = FullKeyScan();
            const int Menu = (int)KeyCode.Menu, M0 = (int)KeyCode.Mouse0;
            EdgeAttribution m;
            bool tap = KeybindRules.ScriptTap(alias, scan, null, false, "", false, out m);
            bool jDisarms = !KeybindRules.ScriptTap(alias, scan, new[] { (int)KeyCode.J }, true, "j", false, out m)
                            && m == EdgeAttribution.Key;
            bool clickKeeps = KeybindRules.ScriptTap(alias, scan, new[] { M0 }, true, "", true, out m) && m == EdgeAttribution.Mouse;
            // the simultaneous edge, ONE step: a key and a click are attributed to both
            bool simBoth = !KeybindRules.ScriptTap(alias, scan, new[] { Menu, M0 }, true, "", true, out m)
                           && m == (EdgeAttribution.Key | EdgeAttribution.Mouse);
            // the unscannable edge: text no KeyCode names, beside a click, is Unknown
            bool unknownLeg = !KeybindRules.ScriptTap(alias, scan, new[] { M0 }, true, "é", true, out m)
                              && (m & EdgeAttribution.Unknown) != 0;
            bool unattributed = !KeybindRules.ScriptTap(alias, scan, null, true, "", false, out m) && m == EdgeAttribution.Unknown;
            bool heldMouseLeg = !KeybindRules.ScriptTap(alias, scan, null, true, "", true, out m);   // LMB held from before, no same-frame edge
            bool f5 = KeyCodesFor(failed, MenuToggle).Contains(KeybindRules.CodeF5);
            bool readOnly = !failed.Ready;   // RowsWritable reads the same flag on the live state
            stCaseOk["j-mouse"] = clickKeeps;
            stCaseOk["j-unattributed"] = unattributed && heldMouseLeg && unknownLeg;
            stCaseOk["j-simultaneous"] = simBoth;
            Case("j failed validation: defaults in force, the tap rotates on LeftAlt, J disarms, a same-frame click keeps it, a key and a click in one frame are attributed to both, an unnamed edge is Unknown (also beside a click and with LMB held), F5 answers, rows read-only",
                 notReady && defaults && tap && jDisarms && clickKeeps && simBoth && unknownLeg && unattributed && heldMouseLeg && f5 && readOnly,
                 "notReady=" + notReady + " defaults=" + defaults + " tap=" + tap + " J=" + jDisarms + " click=" + clickKeeps
                 + " simultaneous=" + simBoth + " unknown+click=" + unknownLeg
                 + " unattributed=" + unattributed + " heldMouse=" + heldMouseLeg + " f5=" + f5 + " readOnly=" + readOnly
                 + " scan=" + scan.Length + " failure=" + failed.Failure);
        }

        /// <summary>The mutation battery's own verdict: each mutation must
        /// red exactly the cases it is aimed at, and its controls stay green.</summary>
        private static void StMutationVerdict()
        {
            int m = stMutation - 100;
            string[] mustRed, mustGreen;
            switch (stMutation)
            {
                case 101: mustRed = new[] { "a" }; mustGreen = new[] { "e" }; break;
                case 102: mustRed = new[] { "d" }; mustGreen = new[] { "e" }; break;
                case 103: mustRed = new[] { "c" }; mustGreen = new[] { "e" }; break;
                case 104: mustRed = new[] { "b" }; mustGreen = new[] { "c", "a", "e" }; break;
                case 105: mustRed = new[] { "g", "b", "d", "f" }; mustGreen = new[] { "a", "e", "j" }; break;
                case 106: mustRed = new[] { "h" }; mustGreen = new[] { "a", "b", "c", "d", "e", "f", "g", "i" }; break;
                case 107: mustRed = new[] { "j-unattributed" }; mustGreen = new[] { "j-mouse", "i", "e" }; break;
                case 108: mustRed = new[] { "i" }; mustGreen = new[] { "j", "e" }; break;
                default: return;
            }
            bool ok = true;
            var sb = new System.Text.StringBuilder();
            foreach (var id in mustRed) { bool v = CaseOk(id); if (v) ok = false; sb.Append(id).Append(v ? "=green(WRONG) " : "=red "); }
            foreach (var id in mustGreen) { bool v = CaseOk(id); if (!v) ok = false; sb.Append(id).Append(v ? "=green " : "=red(WRONG) "); }
            Plugin.Log.LogInfo("[KEYBIND] T2 MUTATION " + m + " " + (ok ? "PASS" : "FAIL") + " | " + sb.ToString().Trim());
        }

        private static bool CaseOk(string id)
        {
            foreach (var kv in stCaseOk)
                if (kv.Key == id || kv.Key.StartsWith(id + " ", StringComparison.Ordinal)) return kv.Value;
            return false;
        }

        /// <summary>T3 run in process against the REAL IL of the three
        /// targets: unmutated each matches exactly one pair; mutation 1 (any
        /// GetKey call) finds two in PlayerAssigner.LateUpdate; mutation 2
        /// (a method with no pair) finds zero; mutation 3 (the Ldc_I4 opcode
        /// alone) finds zero at both Space sites while the LeftShift site,
        /// a real Ldc_I4, still matches.</summary>
        /// <summary>The method's original IL as Harmony's instruction list.
        /// PatchProcessor.GetOriginalInstructions takes an optional
        /// ILGenerator, a type this netstandard compile cannot name (CS7069),
        /// so the overload is found and called by reflection.</summary>
        private static List<CodeInstruction> OriginalInstructions(MethodBase mb)
        {
            foreach (var m in typeof(PatchProcessor).GetMethods(BindingFlags.Public | BindingFlags.Static))
            {
                if (m.Name != "GetOriginalInstructions") continue;
                var ps = m.GetParameters();
                if (ps.Length == 2 && ps[0].ParameterType == typeof(MethodBase) && !ps[1].IsOut && !ps[1].ParameterType.IsByRef)
                    return new List<CodeInstruction>((IEnumerable<CodeInstruction>)m.Invoke(null, new object[] { mb, null }));
            }
            throw new MissingMethodException("PatchProcessor.GetOriginalInstructions(MethodBase, ILGenerator)");
        }

        internal static void TranspilerMatcherBattery()
        {
            try
            {
                var lobby = AccessTools.Method(typeof(PlayerAssigner), "LateUpdate");
                var csel = AccessTools.Method(typeof(CharacterSelectionInstance), "Update");
                var art = AccessTools.Method(typeof(ArtHandler), "Update");
                var nextArt = AccessTools.Method(typeof(ArtHandler), "NextArt");
                Func<MethodBase, int, MethodInfo, MatchMode, int> count = (mb, code, call, mode) =>
                {
                    var il = OriginalInstructions(mb);
                    return RewritePairs(il, code, call, 0, null, mode);
                };
                int u1 = count(lobby, 32, InputGetKey, MatchMode.Pair), u2 = count(csel, 32, InputGetKeyDown, MatchMode.Pair),
                    u3 = count(art, 304, InputGetKeyDown, MatchMode.Pair);
                int m1 = count(lobby, 32, InputGetKey, MatchMode.AnyGetKey);
                int m2 = count(nextArt, 304, InputGetKeyDown, MatchMode.Pair);
                int m3a = count(lobby, 32, InputGetKey, MatchMode.OpcodeOnly), m3b = count(csel, 32, InputGetKeyDown, MatchMode.OpcodeOnly),
                    m3c = count(art, 304, InputGetKeyDown, MatchMode.OpcodeOnly);
                Plugin.Log.LogInfo("[KEYBIND] T3 unmutated pairs: lobby=" + u1 + " charselect=" + u2 + " mapart=" + u3
                    + " " + (u1 == 1 && u2 == 1 && u3 == 1 ? "PASS" : "FAIL"));
                Plugin.Log.LogInfo("[KEYBIND] T3 MUTATION 1 any-GetKey matcher: lobby=" + m1 + " " + (m1 == 2 ? "PASS (count 2, the transpiler would throw)" : "FAIL"));
                Plugin.Log.LogInfo("[KEYBIND] T3 MUTATION 2 no pair in the target: ArtHandler.NextArt=" + m2 + " " + (m2 == 0 ? "PASS (count 0, the transpiler would throw)" : "FAIL"));
                Plugin.Log.LogInfo("[KEYBIND] T3 MUTATION 3 Ldc_I4-only matcher: lobby=" + m3a + " charselect=" + m3b + " mapart=" + m3c
                    + " " + (m3a == 0 && m3b == 0 && m3c == 1 ? "PASS (both Space sites 0, the LeftShift control still 1)" : "FAIL"));
            }
            catch (Exception e) { Plugin.Log.LogWarning("[KEYBIND] T3 matcher battery threw: " + e.Message); }
        }
    }

    /// <summary>Design section 2.4: the ready-up prompts name the bound
    /// Jump key. Four postfixes, one predicate, one restore. At the default
    /// every postfix returns having touched nothing.</summary>
    internal static class ReadyPromptPatches
    {
        private static readonly FieldInfo fText = AccessTools.Field(typeof(UILocalizedString), "m_text");
        private static readonly HashSet<CharacterSelectionInstance> overridden = new HashSet<CharacterSelectionInstance>();

        private static bool Override()
        {
            return KeybindRules.ShouldOverrideReadyPrompt(Keybinds.Bound(Keybinds.Jump)) && Keybinds.MappingReady;
        }

        private static bool KeyboardSeat(CharacterSelectionInstance c)
        {
            try { return c.currentPlayer != null && c.currentPlayer.data.input.inputType != GeneralInput.InputType.Controller; }
            catch { return false; }
        }

        private static void WriteLabel(GameObject obj, string text)
        {
            if (obj == null) return;
            var ui = obj.GetComponentInChildren<UILocalizedString>(true);
            if (ui == null) return;
            ui.enabled = false;   // stop the localizer rewriting it on the next locale event
            object tmp = fText != null ? fText.GetValue(ui) : null;
            if (tmp != null) UIFactory.SetTextNoHook(tmp, text);
        }

        private static void RestoreJoin(CharacterSelectionInstance c)
        {
            var ui = c.joinObj != null ? c.joinObj.GetComponentInChildren<UILocalizedString>(true) : null;
            if (ui != null && !ui.enabled) ui.enabled = true;   // OnEnable re-renders its own reference
        }

        private static void RestoreReady(CharacterSelectionInstance c)
        {
            var ui = c.getReadyObj != null ? c.getReadyObj.GetComponentInChildren<UILocalizedString>(true) : null;
            if (ui == null) return;
            if (!ui.enabled) ui.enabled = true;
            if (KeyboardSeat(c)) ui.SetReference(c.isReady ? c.m_localizedReady : c.m_localizedReadySpace);
        }

        internal static void ApplyJoin(CharacterSelectionInstance c)
        {
            if (c == null) return;
            if (!Override()) { if (overridden.Remove(c)) RestoreJoin(c); return; }
            WriteLabel(c.joinObj, NativeUI.KeybindJoinPrompt());
            overridden.Add(c);
        }

        internal static void ApplyReady(CharacterSelectionInstance c)
        {
            if (c == null || !KeyboardSeat(c)) return;
            if (!Override()) { if (overridden.Contains(c)) RestoreReady(c); return; }
            if (c.isReady) { RestoreReady(c); return; }   // the ready word names no key
            WriteLabel(c.getReadyObj, NativeUI.KeybindReadyPrompt());
            overridden.Add(c);
        }

        /// <summary>From ReapplyAllLiveSets: the row reset and reset-all
        /// restore the prompts for free.</summary>
        internal static void RefreshAll()
        {
            CharacterSelectionInstance[] all;
            try { all = UnityEngine.Object.FindObjectsOfType<CharacterSelectionInstance>(); } catch { return; }
            foreach (var c in all)
            {
                if (c == null) continue;
                bool wasOverridden = overridden.Contains(c);
                if (!Override())
                {
                    if (wasOverridden) { RestoreJoin(c); RestoreReady(c); overridden.Remove(c); }
                    continue;
                }
                if (c.joinObj != null && c.joinObj.activeInHierarchy) ApplyJoin(c);
                if (c.getReadyObj != null && c.getReadyObj.activeInHierarchy) ApplyReady(c);
            }
            overridden.RemoveWhere(x => x == null);
        }

        [HarmonyPatch(typeof(CharacterSelectionInstance), nameof(CharacterSelectionInstance.ResetMenu))]
        internal static class ResetMenuPatch
        {
            [HarmonyPostfix] private static void Postfix(CharacterSelectionInstance __instance) { try { ApplyJoin(__instance); } catch { } }
            [HarmonyCleanup] private static Exception Cleanup(MethodBase original, Exception exception)
            { return original != null ? exception : VanillaFixSupport.Cleanup("KeybindPromptResetMenu", exception); }
        }

        [HarmonyPatch(typeof(CharacterSelectionInstance), "OnEnable")]
        internal static class OnEnablePatch
        {
            [HarmonyPostfix] private static void Postfix(CharacterSelectionInstance __instance) { try { ApplyJoin(__instance); } catch { } }
            [HarmonyCleanup] private static Exception Cleanup(MethodBase original, Exception exception)
            { return original != null ? exception : VanillaFixSupport.Cleanup("KeybindPromptOnEnable", exception); }
        }

        [HarmonyPatch(typeof(CharacterSelectionInstance), nameof(CharacterSelectionInstance.StartPicking))]
        internal static class StartPickingPatch
        {
            [HarmonyPostfix] private static void Postfix(CharacterSelectionInstance __instance) { try { ApplyReady(__instance); } catch { } }
            [HarmonyCleanup] private static Exception Cleanup(MethodBase original, Exception exception)
            { return original != null ? exception : VanillaFixSupport.Cleanup("KeybindPromptStartPicking", exception); }
        }

        [HarmonyPatch(typeof(CharacterSelectionInstance), nameof(CharacterSelectionInstance.ReadyUp))]
        internal static class ReadyUpPatch
        {
            [HarmonyPostfix] private static void Postfix(CharacterSelectionInstance __instance) { try { ApplyReady(__instance); } catch { } }
            [HarmonyCleanup] private static Exception Cleanup(MethodBase original, Exception exception)
            { return original != null ? exception : VanillaFixSupport.Cleanup("KeybindPromptReadyUp", exception); }
        }
    }
}
