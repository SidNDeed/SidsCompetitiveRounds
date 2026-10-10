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
        /// back (an interface member there, unused at the pin).</summary>
        private sealed class Store : IBindStore
        {
            internal readonly string[] Entries = new string[KeybindRules.RowCount];
            internal BindSource[] Applied;
            internal int Applies, ThrowOnApplyFrom;
            internal Store(BindSource[] start)
            {
                for (int i = 0; i < Entries.Length; i++) Entries[i] = KeybindRules.FormatToken(start[i]);
                Applied = (BindSource[])start.Clone();
            }
            public string ReadEntry(int row) { return Entries[row]; }
            public void WriteEntry(int row, string token) { Entries[row] = token; }
            public void ApplyAll(BindSource[] b)
            {
                Applies++;
                if (ThrowOnApplyFrom > 0 && Applies >= ThrowOnApplyFrom) throw new InvalidOperationException("live set apply " + Applies);
                Applied = (BindSource[])b.Clone();
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
    }
}
