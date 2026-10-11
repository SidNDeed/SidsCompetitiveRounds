using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 17 fix pass 4: the round-4 M2 runtime controls, written to compile
    /// against BOTH the reviewed pin (9cff43c9) and the fix tip, so one
    /// instrument runs red on the first and green on the second (the controls
    /// run overlays it on a detached worktree of the pin). It names only
    /// members both trees carry; what the fix adds - KeybindRules.InfoVisual,
    /// InfoViz.Build's failure rule and RenderInfoBody's segment loop, both
    /// production code - is reached by reflection. Where the pin has no such
    /// member the case runs the same scenario through a model of what the pin
    /// does in production and says so in its got= text: InfoViz.Build at
    /// 9cff43c9 caught a builder's exception, logged it and returned null
    /// (InfoViz.cs:116-123), and RenderInfoBody drew the visual's text form,
    /// or nothing, in its place (NativeUI.cs:13816-13821), so the render
    /// returned and the gate stamped the revision (KeybindRules.cs:856).
    ///
    /// The guide's leaf is the binding read the real keyboard guide makes for
    /// every cap it draws - KeybindRules.BoardCapRole over the registry and
    /// the key table, the call InfoViz.Fill makes through
    /// Keybinds.BoardCapRole - with the key table the case controls. Its
    /// Unity drawing cannot run outside the game; every decision between that
    /// read and the repaint gate is the tree's own code, and the gate is the
    /// real KeybindRules.RepaintGate.
    /// </summary>
    internal static class KeybindFix4Controls
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
            M2(r);
            return r;
        }

        private const BindingFlags Any = BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;

        /// <summary>The tree's failure path between a visual's builder and the
        /// article's render. Fix tip: KeybindRules.InfoVisual.Build (what
        /// InfoViz.Build runs) and KeybindRules.InfoVisual.Lay (what
        /// RenderInfoBody runs), bound as delegates so an exception reaches the
        /// gate unwrapped. Pin: the model named in the class summary.</summary>
        private sealed class FailurePath
        {
            internal readonly string How;
            private readonly Func<string, Func<string>, Action, Action<string>, string> build;
            private readonly Action<int, Func<int, string>, Func<int, string>, Func<string, string>, Func<string, string>,
                Action<string>, Action<string>> lay;

            internal FailurePath()
            {
                var t = typeof(KeybindRules).GetNestedType("InfoVisual", BindingFlags.Public | BindingFlags.NonPublic);
                MethodInfo b = t != null ? t.GetMethod("Build", Any) : null;
                MethodInfo l = t != null ? t.GetMethod("Lay", Any) : null;
                if (b != null && l != null)
                {
                    build = (Func<string, Func<string>, Action, Action<string>, string>)Delegate.CreateDelegate(
                        typeof(Func<string, Func<string>, Action, Action<string>, string>), b.MakeGenericMethod(typeof(string)));
                    lay = (Action<int, Func<int, string>, Func<int, string>, Func<string, string>, Func<string, string>,
                        Action<string>, Action<string>>)Delegate.CreateDelegate(
                        typeof(Action<int, Func<int, string>, Func<int, string>, Func<string, string>, Func<string, string>,
                            Action<string>, Action<string>>), l.MakeGenericMethod(typeof(string)));
                    How = "KeybindRules.InfoVisual.Build and .Lay";
                }
                else
                {
                    build = PinBuild;
                    lay = PinLay;
                    How = "a model of the pin: InfoViz.Build's catch returns null (InfoViz.cs:116-123) and RenderInfoBody "
                          + "draws the text form or nothing in its place (NativeUI.cs:13816-13821)";
                }
            }

            internal string Build(string key, Func<string> b, Action cleanup, Action<string> warn) { return build(key, b, cleanup, warn); }

            internal void Lay(int count, Func<int, string> textAt, Func<int, string> vizAt, Func<string, string> b,
                              Func<string, string> fallback, Action<string> panel, Action<string> text)
            {
                lay(count, textAt, vizAt, b, fallback, panel, text);
            }

            private static string PinBuild(string key, Func<string> b, Action cleanup, Action<string> warn)
            {
                try { return b(); }
                catch (Exception ex)
                {
                    warn("[INFO-VIZ] build '" + key + "' failed: " + ex.Message);
                    cleanup();
                    return null;
                }
            }

            private static void PinLay(int count, Func<int, string> textAt, Func<int, string> vizAt, Func<string, string> b,
                                       Func<string, string> fallback, Action<string> panel, Action<string> text)
            {
                for (int i = 0; i < count; i++)
                {
                    string segText = textAt(i);
                    string viz = vizAt(i);
                    if (!string.IsNullOrEmpty(viz))
                    {
                        string made = b(viz);
                        if (made != null) { panel(made); continue; }
                        segText = fallback(viz);
                        if (string.IsNullOrEmpty(segText)) continue;
                    }
                    if (string.IsNullOrEmpty(segText)) continue;
                    text(segText);
                }
            }
        }

        private static BindSource[] DefaultSet()
        {
            var s = new BindSource[KeybindRules.RowCount];
            for (int i = 0; i < s.Length; i++) s[i] = KeybindRules.Default(i);
            return s;
        }

        /// <summary>The Controls article's reading pane under the real repaint
        /// gate: its three segments - the intro text, the keyboard guide, the
        /// outro text - laid out by the tree's failure path, the guide built
        /// from every cap's role under the registry.</summary>
        private sealed class ControlsArticle
        {
            internal readonly List<string> Shown = new List<string>();
            internal int Logs, Warns, Releases, Renders;
            internal bool KeyTableFails, GuideBuildsNothing;
            internal string Visual = "keyboard";
            internal readonly FailurePath Path = new FailurePath();
            private readonly BindSource[] reg;
            private readonly object gate;
            private readonly MethodInfo painted, due, repaint;

            internal ControlsArticle(BindSource[] registry)
            {
                reg = registry;
                var gt = typeof(KeybindRules).GetNestedType("RepaintGate", BindingFlags.Public | BindingFlags.NonPublic);
                gate = Activator.CreateInstance(gt, true);
                painted = gt.GetMethod("Painted", Any);
                due = gt.GetMethod("Due", Any);
                repaint = gt.GetMethod("Repaint", Any);
            }

            private int[] Codes(int keyOrdinal)
            {
                if (KeyTableFails) throw new InvalidOperationException("the live key table could not be read");
                return KeybindRules.StaticCodesForKey(keyOrdinal);
            }

            /// <summary>The guide's binding read: every cap's role, as the real
            /// guide colours each cap; the panel names two of them.</summary>
            private string Guide()
            {
                if (GuideBuildsNothing) return null;
                int q = 0, g = 0;
                for (int i = 0; i < KeybindRules.BoardCapCount; i++)
                {
                    string id = KeybindRules.BoardCapId(i);
                    int role = KeybindRules.BoardCapRole(id, reg, Codes);
                    if (id == "Q") q = role;
                    if (id == "G") g = role;
                }
                return "guide Q=" + q + " G=" + g;
            }

            internal static string ExpectedGuide(BindSource[] registry)
            {
                return "guide Q=" + KeybindRules.BoardCapRole("Q", registry, KeybindRules.StaticCodesForKey)
                       + " G=" + KeybindRules.BoardCapRole("G", registry, KeybindRules.StaticCodesForKey);
            }

            private void Render()
            {
                Renders++;
                Shown.Clear();
                string[] texts = { "intro", null, "outro" };
                string[] viz = { null, Visual, null };
                Path.Lay(3, i => texts[i], i => viz[i],
                    v => Path.Build(v, Guide, () => { Releases++; }, w => { Warns++; }),
                    v => v == "keyboard" ? null : "text form of " + v,   // InfoViz.TextFallback has no keyboard case
                    p => Shown.Add(p), t => Shown.Add(t));
            }

            /// <summary>The article's first build, painted at revision.</summary>
            internal void Build(int revision)
            {
                Render();
                painted.Invoke(gate, new object[] { revision });
            }

            internal bool Due(int revision) { return (bool)due.Invoke(gate, new object[] { revision }); }

            /// <summary>One tick while the Info tab is up (KbRepaintInfoIfDue): a
            /// due revision repaints through the gate. False when nothing
            /// repainted or the repaint failed.</summary>
            internal bool Tick(int revision)
            {
                if (!Due(revision)) return false;
                Action render = Render;
                Action blank = () => Shown.Clear();
                Action<string> log = what => { Logs++; };
                return (bool)repaint.Invoke(gate, new object[] { revision, render, blank, log });
            }

            internal string State(int revision)
            {
                return "due " + Due(revision) + ", shown '" + string.Join("|", Shown.ToArray()) + "', logged " + Logs
                       + ", warned " + Warns + ", released " + Releases;
            }
        }

        private static void M2(Result r)
        {
            var g = BindSource.Key(KeybindRules.KeyOrdinal("G"));

            // 1. the guide's binding read throws on the repaint after a binding change
            var reg = DefaultSet();
            var a = new ControlsArticle(reg);
            a.Build(0);
            reg[KeybindRules.QuickChat] = g;
            a.KeyTableFails = true;
            bool done = a.Tick(1);
            string got = "repaint completed " + done + ", " + a.State(1);
            Check(r, "M2 fix4 the Controls guide's binding read throws on the real failure path: the revision stays unstamped (due), the article is blank, the failure is logged once",
                  got == "repaint completed False, due True, shown '', logged 1, warned 0, released 1",
                  got + " (" + a.Path.How + ")");

            // 2. the next tick repaints again; once the guide builds, the revision is stamped
            reg = DefaultSet();
            a = new ControlsArticle(reg);
            a.Build(0);
            reg[KeybindRules.QuickChat] = g;
            a.KeyTableFails = true;
            a.Tick(1);
            int renders = a.Renders;
            a.Tick(1);
            string second = "the second tick repainted " + (a.Renders == renders + 1) + ", due " + a.Due(1) + ", logged " + a.Logs;
            a.KeyTableFails = false;
            a.Tick(1);
            string third = "then due " + a.Due(1) + ", shown '" + string.Join("|", a.Shown.ToArray()) + "'";
            string fresh = "then due False, shown 'intro|" + ControlsArticle.ExpectedGuide(reg) + "|outro'";
            Check(r, "M2 fix4 the next tick repaints the failed article again, logs nothing new, and stamps the revision once the guide builds",
                  second == "the second tick repainted True, due True, logged 1" && third == fresh,
                  second + "; " + third + " (" + a.Path.How + ")");

            // 3. a binding visual that builds nothing
            reg = DefaultSet();
            a = new ControlsArticle(reg);
            a.Build(0);
            reg[KeybindRules.QuickChat] = g;
            a.GuideBuildsNothing = true;
            done = a.Tick(1);
            got = "repaint completed " + done + ", " + a.State(1);
            Check(r, "M2 fix4 a keyboard guide that builds nothing is a repaint failure, never an empty guide stamped current",
                  got == "repaint completed False, due True, shown '', logged 1, warned 0, released 0",
                  got + " (" + a.Path.How + ")");

            // 4. control: a visual that reads no binding keeps r1 MEDIUM 5
            reg = DefaultSet();
            a = new ControlsArticle(reg);
            a.Visual = "dot-timeline";
            a.Build(0);
            reg[KeybindRules.QuickChat] = g;
            a.KeyTableFails = true;
            done = a.Tick(1);
            got = "repaint completed " + done + ", " + a.State(1);
            Check(r, "M2 fix4 control: a visual that reads no binding and fails is a warning, its text form is drawn in its place and the revision is stamped",
                  got == "repaint completed True, due False, shown 'intro|text form of dot-timeline|outro', logged 0, warned 1, released 1",
                  got + " (" + a.Path.How + ")");

            // 5. control: a guide that builds is laid out between the texts and stamped
            reg = DefaultSet();
            a = new ControlsArticle(reg);
            a.Build(0);
            reg[KeybindRules.QuickChat] = g;
            done = a.Tick(1);
            got = "repaint completed " + done + ", " + a.State(1);
            string want = "repaint completed True, due False, shown 'intro|" + ControlsArticle.ExpectedGuide(reg)
                          + "|outro', logged 0, warned 0, released 0";
            Check(r, "M2 fix4 control: a guide that builds is laid out between the article's texts and the revision is stamped",
                  got == want, got + " (" + a.Path.How + ")");
        }
    }
}
