using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 17 fix pass 3: the round-3 findings' runtime controls, written to
    /// compile against BOTH the reviewed pin (6e74c910) and the fix tip, so
    /// one instrument runs red on the first and green on the second (the
    /// controls run overlays it on a detached worktree of the pin). It names
    /// only members both trees carry; what the fix adds is reached by
    /// reflection (KeybindRules.KeyEventAccumulator and
    /// TapDetector.LastNamedKeyboard). Where the pin has no such member the
    /// case runs the same scenario through a model of what the pin does in
    /// production, and says so in its got= text: for M1 the pin's keyboard
    /// channel, Keybinds.KeyboardEdgeLatch in plugin/Keybinds.cs (outside the
    /// harness), a once-a-frame GetKeyboardState copy compared with the
    /// previous frame's.
    /// </summary>
    internal static class KeybindFix3Controls
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

        private const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;

        // =================================================================
        // M1 (round-3 F2): the keyboard channel is an event accumulator
        // =================================================================

        /// <summary>Windows virtual keys the cases deliver: the ChatChannel
        /// default (LeftAlt / RightAlt) arrives as VK_MENU; K is a non-toggle
        /// key; VK_APPS is the key Unity names KeyCode.Menu; VK_OEM_7 stands
        /// for a key that types text.</summary>
        private const int VkMenu = 0x12, VkK = 0x4B, VkL = 0x4C, VkApps = 0x5D, VkOem7 = 0xDE;
        private const int Mouse0 = 323, KeyCodeMenu = 319;

        /// <summary>The tree's keyboard channel: fed the platform's key events
        /// as they are delivered between frames, read once a frame.</summary>
        private interface IKeySource
        {
            string Name { get; }
            void KeyDown(int vk, bool repeat);
            void KeyUp(int vk);
            int Drain(int frame);
            void Corroborate(int namedKeyboard);
            bool Unavailable { get; }
        }

        /// <summary>The fix tip's: KeybindRules.KeyEventAccumulator, reached
        /// by reflection. Null when this tree has none.</summary>
        private sealed class AccumulatorSource : IKeySource
        {
            private readonly object acc;
            private readonly MethodInfo down, up, drain, corroborate;
            private readonly PropertyInfo unavailable;

            private AccumulatorSource(object a, MethodInfo d, MethodInfo u, MethodInfo dr, MethodInfo c, PropertyInfo un)
            { acc = a; down = d; up = u; drain = dr; corroborate = c; unavailable = un; }

            internal static AccumulatorSource TryCreate()
            {
                var t = typeof(KeybindRules).GetNestedType("KeyEventAccumulator", BindingFlags.Public | BindingFlags.NonPublic);
                if (t == null) return null;
                MethodInfo d = t.GetMethod("KeyDown", Any), u = t.GetMethod("KeyUp", Any),
                           dr = t.GetMethod("DrainForFrame", Any), c = t.GetMethod("Corroborate", Any);
                PropertyInfo un = t.GetProperty("Unavailable", Any);
                if (d == null || u == null || dr == null || c == null || un == null) return null;
                return new AccumulatorSource(Activator.CreateInstance(t, true), d, u, dr, c, un);
            }

            public string Name { get { return "KeybindRules.KeyEventAccumulator"; } }
            public void KeyDown(int vk, bool repeat) { down.Invoke(acc, new object[] { vk, repeat }); }
            public void KeyUp(int vk) { up.Invoke(acc, new object[] { vk }); }
            public int Drain(int frame) { return (int)drain.Invoke(acc, new object[] { frame }); }
            public void Corroborate(int namedKeyboard) { corroborate.Invoke(acc, new object[] { namedKeyboard }); }
            public bool Unavailable { get { return (bool)unavailable.GetValue(acc, null); } }
        }

        /// <summary>The pin's keyboard channel, modelled (Keybinds.KeyboardEdgeLatch
        /// at 6e74c910 is Unity code the harness does not compile): a key-state
        /// table the delivered events set and clear, copied once a frame and
        /// compared with the previous frame's copy; a key whose down bit is
        /// newly set counts. The low (toggle) bit, which Microsoft documents
        /// as meaningless for a non-toggle key, never moves for one here, so
        /// a non-toggle key that went down and up between two copies is not
        /// seen. The first read is a baseline (no edges), as the pin's is.</summary>
        private sealed class SnapshotLatchModel : IKeySource
        {
            private readonly bool[] down = new bool[256], prev = new bool[256];
            private int readFrame = int.MinValue, edges;
            public string Name { get { return "a model of the pin's once-a-frame key-state copy (Keybinds.KeyboardEdgeLatch; this tree has no KeyEventAccumulator)"; } }
            public void KeyDown(int vk, bool repeat) { if (vk > 0 && vk < 256) down[vk] = true; }
            public void KeyUp(int vk) { if (vk > 0 && vk < 256) down[vk] = false; }
            public int Drain(int frame)
            {
                if (frame == readFrame) return edges;
                bool baseline = readFrame == int.MinValue || frame != readFrame + 1;
                int n = 0;
                if (!baseline)
                    for (int vk = 3; vk < 255; vk++) if (down[vk] && !prev[vk]) n++;
                Array.Copy(down, prev, 256);
                readFrame = frame;
                edges = n;
                return n;
            }
            public void Corroborate(int namedKeyboard) { }
            public bool Unavailable { get { return false; } }
        }

        private static IKeySource NewSource()
        {
            IKeySource s = AccumulatorSource.TryCreate();
            return s ?? new SnapshotLatchModel();
        }

        /// <summary>A scripted frame whose independent keyboard channel is the
        /// tree's key source, drained by the detector's own read.</summary>
        private sealed class EventFrames : IFrameInput
        {
            private readonly IKeySource src;
            private HashSet<int> down = new HashSet<int>(), up = new HashSet<int>();
            private bool any;
            private string text = "";
            private float t;
            private int frame;
            internal EventFrames(IKeySource s) { src = s; }
            public bool KeyDown(int code) { return down.Contains(code); }
            public bool KeyUp(int code) { return up.Contains(code); }
            public bool AnyKeyDown() { return any; }
            public string TypedText() { return text; }
            public bool AnyMouseHeld() { return false; }
            public float Now() { return t; }
            public bool Focused() { return true; }
            public int KeyboardEdges() { return src.Drain(frame); }
            internal void Frame(int f, float at, int[] d, int[] u, bool anyKey, string typed)
            {
                frame = f;
                t = at;
                down = new HashSet<int>(d ?? new int[0]);
                up = new HashSet<int>(u ?? new int[0]);
                any = anyKey;
                text = typed ?? "";
            }
        }

        /// <summary>The production order of one chat tick: the detector's step
        /// (whose keyboard read drains the source) and then the source's
        /// liveness check against the KeyCodes the step named (fix tip:
        /// TapDetector.LastNamedKeyboard; the pin has neither).</summary>
        private static bool Tick(KeybindRules.TapDetector det, EventFrames io, int[] alias, int[] scan, IKeySource src)
        {
            bool fired = det.Step(io, alias, scan);
            var f = typeof(KeybindRules.TapDetector).GetField("LastNamedKeyboard", Any);
            src.Corroborate(f != null ? (int)f.GetValue(det) : 0);
            return fired;
        }

        /// <summary>ChatChannel armed through the source (the VK_MENU down
        /// message, then its KeyCode edge), one middle frame whose key events
        /// <paramref name="between"/> delivers after the arming frame's drain
        /// and before the middle frame's, then the key up: "rotated" or
        /// "kept"; <paramref name="mid"/> is the middle frame's attribution.</summary>
        private static string Tap(IKeySource src, Action<IKeySource> between, int[] midDown, bool midAny, string midText,
                                  out EdgeAttribution mid)
        {
            int[] alias = KeybindRules.StaticDefaults[KeybindRules.ChatChannel];
            int[] scan = KeybindRules.HarnessKeyCodeScan();
            var det = new KeybindRules.TapDetector();
            var io = new EventFrames(src);
            io.Frame(0, 0f, null, null, false, "");
            Tick(det, io, alias, scan, src);
            src.KeyDown(VkMenu, false);
            io.Frame(1, 0.05f, new[] { alias[0] }, null, true, "");
            Tick(det, io, alias, scan, src);
            if (between != null) between(src);
            io.Frame(2, 0.1f, midDown, null, midAny, midText);
            Tick(det, io, alias, scan, src);
            mid = det.Last;
            src.KeyUp(VkMenu);
            io.Frame(3, 0.2f, null, new[] { alias[0] }, false, "");
            return Tick(det, io, alias, scan, src) ? "rotated" : "kept";
        }

        private static void M1(Result r)
        {
            EdgeAttribution mid;
            var src = NewSource();
            string between = Tap(src, s => { s.KeyDown(VkK, false); s.KeyUp(VkK); }, new[] { Mouse0 }, true, "", out mid);
            bool unknown = (mid & EdgeAttribution.Unknown) != 0;
            Check(r, "M1 ChatChannel armed, a foreign non-toggle key goes down and up wholly between two drains with a click in the same frame: the channel is not rotated and the edge is attributed Unknown",
                  between == "kept" && unknown, between + ", middle frame " + mid + " (source: " + src.Name + ")");

            src = NewSource();
            string named = Tap(src, s => s.KeyDown(VkApps, false), new[] { KeyCodeMenu, Mouse0 }, true, "", out mid);
            Check(r, "M1 control: a named key and a click in one frame, its key event delivered: the channel is not rotated",
                  named == "kept", named + ", middle frame " + mid + " (source: " + src.Name + ")");

            src = NewSource();
            string typed = Tap(src, s => s.KeyDown(VkOem7, false), new[] { Mouse0 }, true, "é", out mid);
            Check(r, "M1 control: typed text and a click in one frame, its key event delivered: the channel is not rotated",
                  typed == "kept", typed + ", middle frame " + mid + " (source: " + src.Name + ")");

            src = NewSource();
            string click = Tap(src, null, new[] { Mouse0 }, true, "", out mid);
            Check(r, "M1 control: a click alone, no key event delivered, keeps the tap: the channel rotates",
                  click == "rotated", click + ", middle frame " + mid + " (source: " + src.Name + ")");

            src = NewSource();
            string repeat = Tap(src, s => s.KeyDown(VkMenu, true), new[] { Mouse0 }, true, "", out mid);
            Check(r, "M1 control: the held ChatChannel key's auto-repeat is no new edge, so a click while it repeats keeps the tap: the channel rotates",
                  repeat == "rotated", repeat + ", middle frame " + mid + " (source: " + src.Name + ")");

            var acc = AccumulatorSource.TryCreate();
            string counts;
            if (acc == null) counts = "no KeyEventAccumulator in this tree";
            else
            {
                acc.KeyDown(VkK, false); acc.KeyUp(VkK);
                acc.KeyDown(VkL, false); acc.KeyDown(VkL, true); acc.KeyDown(VkL, true);
                acc.KeyDown(0, false); acc.KeyDown(255, false);
                int a = acc.Drain(7), b = acc.Drain(7), c = acc.Drain(8);
                counts = a + "," + b + "," + c;
            }
            Check(r, "M1 the accumulator counts each fresh press once: a key down and up between drains is one edge, auto-repeats and out-of-range codes none, a second drain in the frame repeats the count, the next frame starts empty",
                  counts == "2,2,0", counts);

            acc = AccumulatorSource.TryCreate();
            string silent;
            if (acc == null) silent = "no KeyEventAccumulator in this tree";
            else
            {
                int[] alias = KeybindRules.StaticDefaults[KeybindRules.ChatChannel];
                int[] scan = KeybindRules.HarnessKeyCodeScan();
                var det = new KeybindRules.TapDetector();
                var io = new EventFrames(acc);
                // the hook delivers nothing at all while the KeyCodes name the key
                io.Frame(0, 0f, null, null, false, "");
                Tick(det, io, alias, scan, acc);
                io.Frame(1, 0.05f, new[] { alias[0] }, null, true, "");
                Tick(det, io, alias, scan, acc);
                io.Frame(2, 0.2f, null, new[] { alias[0] }, false, "");
                string first = Tick(det, io, alias, scan, acc) ? "rotated" : "kept";
                io.Frame(3, 1.0f, new[] { alias[0] }, null, true, "");
                Tick(det, io, alias, scan, acc);
                io.Frame(4, 1.05f, new[] { Mouse0 }, null, true, "");
                Tick(det, io, alias, scan, acc);
                io.Frame(5, 1.2f, null, new[] { alias[0] }, false, "");
                string second = Tick(det, io, alias, scan, acc) ? "rotated" : "kept";
                silent = "first " + first + ", second " + second + ", unavailable " + acc.Unavailable;
            }
            Check(r, "M1 a source that never delivers while the KeyCodes name keyboard keys is unavailable after two such frames, and a click with the ChatChannel key held then disarms the tap",
                  silent == "first rotated, second kept, unavailable True", silent);
        }

        // =================================================================
        // M2 (round-3 F3): a revision is painted only after its repaint
        // completed
        // =================================================================

        private static BindSource[] DefaultSet()
        {
            var s = new BindSource[KeybindRules.RowCount];
            for (int i = 0; i < s.Length; i++) s[i] = KeybindRules.Default(i);
            return s;
        }

        /// <summary>What the built Controls surface shows for a binding set:
        /// QuickChat's key in the text, and the Q and G caps' colours in the
        /// keyboard guide.</summary>
        private static Func<string> PaintOf(BindSource[] reg)
        {
            return () => "QuickChat=" + KeybindRules.FormatToken(reg[KeybindRules.QuickChat])
                         + " Q=" + KeybindRules.BoardCapRole("Q", reg, null)
                         + " G=" + KeybindRules.BoardCapRole("G", reg, null);
        }

        /// <summary>One built surface and the tree's repaint decision. Fix tip:
        /// RepaintGate.Repaint, reached by reflection. Pin: RepaintGate has no
        /// Repaint, so the pin's order is modelled - SelectInfoArticle at
        /// 6e74c910 stamps the revision (RepaintGate.Painted), then renders,
        /// and its catch logs a throw on every call. The render writes half
        /// its text before it throws, the way a body whose guide fails to
        /// build would.</summary>
        private sealed class Surface
        {
            internal string Shown = "";
            internal int Logs, ThrowsLeft;
            internal string ThrowMessage = "the keyboard guide's cap was missing";
            internal readonly string How;
            private readonly Func<string> paint;
            private readonly object gate;
            private readonly MethodInfo painted, due, repaint;

            internal Surface(Func<string> p)
            {
                paint = p;
                var gt = typeof(KeybindRules).GetNestedType("RepaintGate", BindingFlags.Public | BindingFlags.NonPublic);
                gate = gt != null ? Activator.CreateInstance(gt, true) : null;
                painted = gt != null ? gt.GetMethod("Painted", Any) : null;
                due = gt != null ? gt.GetMethod("Due", Any) : null;
                repaint = gt != null ? gt.GetMethod("Repaint", Any) : null;
                How = repaint != null ? "RepaintGate.Repaint"
                    : "a model of the pin's order: RepaintGate.Painted, then the render (SelectInfoArticle at 6e74c910)";
            }

            private void Render()
            {
                Shown = "partial";
                if (ThrowsLeft > 0)
                {
                    ThrowsLeft--;
                    throw new InvalidOperationException(ThrowMessage);
                }
                Shown = paint();
            }

            internal void Build(int revision)
            {
                Shown = paint();
                painted.Invoke(gate, new object[] { revision });
            }

            internal bool Due(int revision) { return (bool)due.Invoke(gate, new object[] { revision }); }

            /// <summary>One tick of the surface while it is up: a due revision
            /// repaints.</summary>
            internal void Tick(int revision)
            {
                if (!Due(revision)) return;
                if (repaint != null)
                {
                    Action render = Render;
                    Action blank = () => { Shown = ""; };
                    Action<string> log = what => { Logs++; };
                    repaint.Invoke(gate, new object[] { revision, render, blank, log });
                    return;
                }
                painted.Invoke(gate, new object[] { revision });
                try { Render(); }
                catch (Exception) { Logs++; }
            }
        }

        private static void M2(Result r)
        {
            string fresh = "QuickChat=key:G Q=0 G=" + KeybindRules.BoardMod;
            var g = BindSource.Key(KeybindRules.KeyOrdinal("G"));

            var reg = DefaultSet();
            var s = new Surface(PaintOf(reg));
            s.Build(0);
            reg[KeybindRules.QuickChat] = g;
            s.ThrowsLeft = 1;
            s.Tick(1);
            string afterThrow = "due " + s.Due(1) + ", shown '" + s.Shown + "', logged " + s.Logs;
            s.Tick(1);
            string afterNext = "due " + s.Due(1) + ", shown '" + s.Shown + "'";
            Check(r, "M2 a Controls repaint whose render throws leaves the revision unstamped (due), shows nothing and logs once; the next tick repaints and stamps it",
                  afterThrow == "due True, shown '', logged 1" && afterNext == "due False, shown '" + fresh + "'",
                  "after the throw: " + afterThrow + "; after the next tick: " + afterNext + " (" + s.How + ")");

            reg = DefaultSet();
            reg[KeybindRules.QuickChat] = g;
            s = new Surface(PaintOf(reg));
            s.Build(1);
            s.ThrowsLeft = 3;
            for (int i = 0; i < 3; i++) s.Tick(2);
            int same = s.Logs;
            s.ThrowsLeft = 1;
            s.ThrowMessage = "the article body was missing";
            s.Tick(2);
            int other = s.Logs - same;
            s.Tick(2);
            string logs = "the same failure on three ticks logged " + same + ", a different one " + other + ", then due " + s.Due(2);
            Check(r, "M2 the same repaint failure on three ticks is logged once, a different one is logged again, and the surface stays due until a repaint completes",
                  logs == "the same failure on three ticks logged 1, a different one 1, then due False", logs + " (" + s.How + ")");

            reg = DefaultSet();
            s = new Surface(PaintOf(reg));
            s.Build(0);
            reg[KeybindRules.QuickChat] = g;
            s.Tick(1);
            string ok = "due " + s.Due(1) + ", shown '" + s.Shown + "', logged " + s.Logs;
            Check(r, "M2 control: a repaint that completes stamps the revision: nothing more is due and the new bindings show",
                  ok == "due False, shown '" + fresh + "', logged 0", ok + " (" + s.How + ")");
        }
    }
}
