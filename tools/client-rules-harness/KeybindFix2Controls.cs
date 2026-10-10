using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 17 fix pass 2: the round-2 findings' runtime controls, written to
    /// compile against BOTH the reviewed pin (2811a621) and the fix tip, so
    /// one instrument runs red on the first and green on the second (the
    /// controls run overlays it on a detached worktree of the pin). It names
    /// only members both trees carry. What the fix adds is reached without
    /// naming it: IFrameInput.KeyboardEdges by a public method of that name
    /// and shape on the instrument's own frame source (an interface member at
    /// the fix tip, a method nothing calls at the pin); the repaint gate by
    /// reflection (absent at the pin, where nothing decides to repaint).
    /// </summary>
    internal static class KeybindFix2Controls
    {
        internal sealed class Result
        {
            internal int Run, Fail;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private static void Check(Result r, string name, bool ok, string got)
        {
            r.Run++;
            if (!ok) r.Fail++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }

        internal static Result Run()
        {
            var r = new Result();
            M1(r);
            M2(r);
            M3(r);
            return r;
        }

        private static BindSource[] DefaultSet()
        {
            var s = new BindSource[KeybindRules.RowCount];
            for (int i = 0; i < s.Length; i++) s[i] = KeybindRules.Default(i);
            return s;
        }

        private static BindSource Key(string id) { return BindSource.Key(KeybindRules.KeyOrdinal(id)); }

        /// <summary>A store in memory: config entries as tokens, live sets as
        /// the last applied copy. VerifyLive is the fix tip's live-set read
        /// back (an interface member there, unused at the pin). Faults, all
        /// off by default: ApplyAll throws BEFORE applying on the call
        /// numbered ThrowBeforeApplyOn and AFTER applying on the call numbered
        /// ApplyThenThrowOn (1-based); MissingRow has no config entry (reads
        /// null and its write does nothing, the shape the 2811a621 live store
        /// gave a row whose entry was never bound); DropWriteRow's entry does
        /// not keep a write; FailWriteRow's writes throw from the one numbered
        /// FailWriteFrom; IgnoreApply returns without the live sets taking
        /// the change.</summary>
        private sealed class Store : IBindStore
        {
            internal readonly string[] Entries = new string[KeybindRules.RowCount];
            internal BindSource[] Applied;
            internal int Applies, ThrowBeforeApplyOn, ApplyThenThrowOn;
            internal int MissingRow = -1, DropWriteRow = -1, FailWriteRow = -1, FailWriteFrom;
            internal bool IgnoreApply;
            private readonly int[] writes = new int[KeybindRules.RowCount];
            internal Store(BindSource[] start)
            {
                for (int i = 0; i < Entries.Length; i++) Entries[i] = KeybindRules.FormatToken(start[i]);
                Applied = (BindSource[])start.Clone();
            }
            public string ReadEntry(int row) { return row == MissingRow ? null : Entries[row]; }
            public void WriteEntry(int row, string token)
            {
                writes[row]++;
                if (row == FailWriteRow && writes[row] >= FailWriteFrom) throw new InvalidOperationException("config write " + writes[row]);
                if (row == MissingRow || row == DropWriteRow) return;
                Entries[row] = token;
            }
            public void ApplyAll(BindSource[] b)
            {
                Applies++;
                if (Applies == ThrowBeforeApplyOn) throw new InvalidOperationException("live set apply " + Applies);
                if (!IgnoreApply) Applied = (BindSource[])b.Clone();
                if (Applies == ApplyThenThrowOn) throw new InvalidOperationException("live set apply " + Applies + " after the change took");
            }
            public string VerifyLive(BindSource[] b)
            {
                for (int i = 0; i < b.Length; i++) if (!Applied[i].Equals(b[i])) return KeybindRules.RowIds[i] + " live=" + KeybindRules.FormatToken(Applied[i]);
                return null;
            }
        }

        // =================================================================
        // M1 (round-2 F2): an unattributable keyboard edge beside a click
        // =================================================================

        /// <summary>A scripted frame source. KeyboardEdges is the independent
        /// keyboard source of the fix tip: every keyboard code of the frame
        /// plus the keys no KeyCode names.</summary>
        private sealed class Frames : IFrameInput
        {
            private HashSet<int> down = new HashSet<int>(), up = new HashSet<int>();
            private bool any;
            private string text = "";
            private float t;
            private int unnamed;
            public bool KeyDown(int code) { return down.Contains(code); }
            public bool KeyUp(int code) { return up.Contains(code); }
            public bool AnyKeyDown() { return any; }
            public string TypedText() { return text; }
            public bool AnyMouseHeld() { return false; }
            public float Now() { return t; }
            public bool Focused() { return true; }
            public int KeyboardEdges()
            {
                int n = unnamed;
                foreach (int c in down) if (c > 0 && c < 323) n++;
                return n;
            }
            internal void Frame(float at, int[] d, int[] u, bool anyKey, string typed, int unnamedKeys)
            {
                t = at;
                down = new HashSet<int>(d ?? new int[0]);
                up = new HashSet<int>(u ?? new int[0]);
                any = anyKey;
                text = typed ?? "";
                unnamed = unnamedKeys;
            }
        }

        /// <summary>ChatChannel armed (its default key goes down, alone), one
        /// middle frame, the key up: "rotated" or "kept".</summary>
        private static string Tap(int[] midDown, bool midAny, string midText, int midUnnamed)
        {
            int[] alias = KeybindRules.StaticDefaults[KeybindRules.ChatChannel];
            int[] scan = KeybindRules.HarnessKeyCodeScan();
            var det = new KeybindRules.TapDetector();
            var io = new Frames();
            io.Frame(0f, new[] { alias[0] }, null, true, "", 0);
            det.Step(io, alias, scan);
            io.Frame(0.1f, midDown, null, midAny, midText, midUnnamed);
            det.Step(io, alias, scan);
            io.Frame(0.2f, null, new[] { alias[0] }, false, "", 0);
            return det.Step(io, alias, scan) ? "rotated" : "kept";
        }

        private static void M1(Result r)
        {
            const int Mouse0 = 323, Menu = 319;
            string unnamedAndClick = Tap(new[] { Mouse0 }, true, "", 1);
            Check(r, "M1 ChatChannel armed, an unattributable non-text keyboard edge and a click in one frame: the channel is not rotated",
                  unnamedAndClick == "kept", unnamedAndClick);
            string unnamedAlone = Tap(null, false, "", 1);
            Check(r, "M1 ChatChannel armed, an unattributable keyboard edge that Input.anyKeyDown does not report: the channel is not rotated",
                  unnamedAlone == "kept", unnamedAlone);
            string namedAndClick = Tap(new[] { Menu, Mouse0 }, true, "", 0);
            Check(r, "M1 control: a named key and a click in one frame: the channel is not rotated",
                  namedAndClick == "kept", namedAndClick);
            string typedAndClick = Tap(new[] { Mouse0 }, true, "é", 1);
            Check(r, "M1 control: typed text and a click in one frame: the channel is not rotated",
                  typedAndClick == "kept", typedAndClick);
            string clickAlone = Tap(new[] { Mouse0 }, true, "", 0);
            Check(r, "M1 control: a click alone keeps the tap: the channel rotates",
                  clickAlone == "rotated", clickAlone);
        }

        // =================================================================
        // M2 (round-2 F4): a built Controls help surface repaints
        // =================================================================

        /// <summary>The Controls article is built from the bindings (its text
        /// names QuickChat's key, its keyboard guide colours the Q and G
        /// caps); optionally QuickChat moves from Q to G through the commit
        /// and the binding revision counts; then the Info tab is shown again
        /// and whatever repaint decision the tree has is taken. At the pin
        /// there is none: the article stays as it was built.</summary>
        private static string ControlsArticleShown(bool rebind, out string how)
        {
            var reg = DefaultSet();
            Func<string> paint = () => "QuickChat=" + KeybindRules.FormatToken(reg[KeybindRules.QuickChat])
                                       + " Q=" + KeybindRules.BoardCapRole("Q", reg, null)
                                       + " G=" + KeybindRules.BoardCapRole("G", reg, null);
            const BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
            var gateType = typeof(KeybindRules).GetNestedType("RepaintGate", BindingFlags.Public | BindingFlags.NonPublic);
            object gate = gateType != null ? Activator.CreateInstance(gateType, true) : null;
            MethodInfo painted = gateType != null ? gateType.GetMethod("Painted", Any) : null;
            MethodInfo due = gateType != null ? gateType.GetMethod("Due", Any) : null;
            int revision = 0;
            string shown = paint();
            if (painted != null) painted.Invoke(gate, new object[] { revision });
            if (rebind)
            {
                string f;
                var outcome = KeybindRules.Commit(reg, new[] { KeybindRules.QuickChat }, new[] { Key("G") }, new Store(reg), out f);
                revision++;
                how = "commit=" + outcome;
            }
            else how = "no rebind";
            if (due == null) { how += ", no repaint decision in this tree"; return shown; }
            if ((bool)due.Invoke(gate, new object[] { revision }))
            {
                shown = paint();
                painted.Invoke(gate, new object[] { revision });
                how += ", repainted";
            }
            return shown;
        }

        private static void M2(Result r)
        {
            string how;
            string rebound = ControlsArticleShown(true, out how);
            Check(r, "M2 Controls article built, QuickChat rebound from Q to G, Info shown again: the key name and the cap colours read are the new ones",
                  rebound == "QuickChat=key:G Q=0 G=" + KeybindRules.BoardMod, rebound + " (" + how + ")");
            string untouched = ControlsArticleShown(false, out how);
            Check(r, "M2 control: with no rebind the built article already shows the bindings",
                  untouched == "QuickChat=key:Q Q=" + KeybindRules.BoardMod + " G=0", untouched + " (" + how + ")");
        }

        // =================================================================
        // M3 (round-2 F6): success only when every store agrees; a
        // rollback is verified, never claimed
        // =================================================================

        private static readonly int[] M3Rows = { KeybindRules.QuickChat, KeybindRules.Jump };

        /// <summary>The two-row change (QuickChat to G, Jump to K) committed
        /// against <paramref name="s"/>. The outcome is read through var and
        /// ToString so the same line compiles where Commit returns a bool (the
        /// pin: True/False) and where it returns the outcome (the fix tip).</summary>
        private static string CommitM3(Store s, BindSource[] reg, out string failure)
        {
            var outcome = KeybindRules.Commit(reg, M3Rows, new[] { Key("G"), Key("K") }, s, out failure);
            return outcome.ToString();
        }

        private static BindSource[] Changed()
        {
            var set = DefaultSet();
            set[KeybindRules.QuickChat] = Key("G");
            set[KeybindRules.Jump] = Key("K");
            return set;
        }

        private static bool Same(BindSource[] a, BindSource[] b)
        {
            for (int i = 0; i < a.Length; i++) if (!a[i].Equals(b[i])) return false;
            return true;
        }

        private static bool EntriesAre(Store s, BindSource[] set)
        {
            for (int i = 0; i < set.Length; i++) if (s.Entries[i] != KeybindRules.FormatToken(set[i])) return false;
            return true;
        }

        /// <summary>Registry / entries / live sets each read as "start",
        /// "new" or "mixed" against the state before and the change.</summary>
        private static string StateOf(Store s, BindSource[] reg)
        {
            Func<bool, bool, string> word = (atStart, atNew) => atStart ? "start" : atNew ? "new" : "mixed";
            var start = DefaultSet();
            var changed = Changed();
            return "registry=" + word(Same(reg, start), Same(reg, changed))
                   + " entries=" + word(EntriesAre(s, start), EntriesAre(s, changed))
                   + " live=" + word(Same(s.Applied, start), Same(s.Applied, changed))
                   + " applies=" + s.Applies;
        }

        private static string M3Run(Store s, out string state, out string failure)
        {
            var reg = DefaultSet();
            string o = CommitM3(s, reg, out failure);
            state = StateOf(s, reg);
            return o;
        }

        private static void M3(Result r)
        {
            string state, f;

            // a rollback whose live-set restore throws: the forward apply
            // changed the live sets, then the restore apply fails
            string o = M3Run(new Store(DefaultSet()) { ApplyThenThrowOn = 1, ThrowBeforeApplyOn = 2 }, out state, out f);
            Check(r, "M3 a rollback whose live-set restore throws is reported partial, naming the live sets the verified state shows unrestored",
                  o == "Partial" && f != null && f.Contains("NOT restored") && f.Contains("live sets")
                  && state == "registry=start entries=start live=new applies=2",
                  o + " | " + state + " | " + f);

            // a rollback whose config restore throws
            o = M3Run(new Store(DefaultSet()) { ThrowBeforeApplyOn = 1, FailWriteRow = KeybindRules.Jump, FailWriteFrom = 2 }, out state, out f);
            Check(r, "M3 a rollback whose config restore throws is reported partial, naming the entry the verified state shows unrestored",
                  o == "Partial" && f != null && f.Contains("NOT restored") && f.Contains("entry Jump")
                  && state == "registry=start entries=mixed live=start applies=2",
                  o + " | " + state + " | " + f);

            // a row with no config entry
            o = M3Run(new Store(DefaultSet()) { MissingRow = KeybindRules.Jump }, out state, out f);
            Check(r, "M3 a change to a row with no config entry is refused and nothing moves",
                  o == "Refused" && f != null && f.Contains("no config entry for Jump")
                  && state == "registry=start entries=start live=start applies=0",
                  o + " | " + state + " | " + f);

            // an entry that does not keep the saved token
            o = M3Run(new Store(DefaultSet()) { DropWriteRow = KeybindRules.Jump }, out state, out f);
            Check(r, "M3 a config entry that does not keep the saved value is never a success, and the change is rolled back",
                  o == "RolledBack" && state == "registry=start entries=start live=start applies=1",
                  o + " | " + state + " | " + f);

            // live sets that do not take the change
            o = M3Run(new Store(DefaultSet()) { IgnoreApply = true }, out state, out f);
            Check(r, "M3 live sets that do not take the change are never a success, and the change is rolled back",
                  o == "RolledBack" && state == "registry=start entries=start live=start applies=2",
                  o + " | " + state + " | " + f);

            // controls: a clean commit succeeds; a rollback that works is a
            // failure with everything as it was
            o = M3Run(new Store(DefaultSet()), out state, out f);
            Check(r, "M3 control: a change every store takes succeeds and all three hold it",
                  (o == "Committed" || o == "True") && f == null && state == "registry=new entries=new live=new applies=1",
                  o + " | " + state + " | " + (f ?? "no failure"));
            o = M3Run(new Store(DefaultSet()) { ThrowBeforeApplyOn = 1 }, out state, out f);
            Check(r, "M3 control: a change whose apply throws and whose rollback works is a failure with every store as it was",
                  (o == "RolledBack" || o == "False") && state == "registry=start entries=start live=start applies=2",
                  o + " | " + state + " | " + f);
        }
    }
}
