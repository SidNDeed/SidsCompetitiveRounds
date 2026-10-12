using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 13 (the settings page reorganisation): the harness's cases for
    /// plugin/SettingsModel.cs. They live HERE, under tools/, so the shipped
    /// DLL carries no fixture; the plugin compiles only the rules. Two of the
    /// design's tests are EXECUTED rather than asserted about (#391):
    ///
    ///   T2a   SplitSettingLabel cuts a painted row string at its FIRST ':'
    ///         outside a rich-text tag. The third case is the design's
    ///         control: a value that carries its own colon ("10:30") must
    ///         come back whole, which a last-colon split cuts in two.
    ///
    ///   T5-g  (selection half) ResetSet(home) is EXACTLY the set the design
    ///         tables for that sub-tab on the client lane (design section
    ///         6.4), compared per tab and never as a total: a reset that
    ///         ignored the home clause would write every row on every tab and
    ///         still sum to the right number. The sets below are typed from
    ///         the design, not derived from the table the rule reads.
    ///         Privacy's set is empty by rule. The effect half (each row's
    ///         writer actually runs) needs the built client.
    ///
    ///   M1    (design 6.3's input table) a destructive row takes Enter
    ///         only, Space and Enter each reach the row as themselves, and
    ///         the keys route to the page action the table names. The same
    ///         dispatch drives the built page in the in-game harness.
    ///
    ///   L3    a disclosure is stepped with Left and Right and never
    ///         activated by Enter or Space.
    ///
    ///   L2    the controller's route (W7's source half): the shoulders move
    ///         between the sub-tabs and the activate button activates the
    ///         focused row, held to the Enter-only rule on a destructive row.
    ///         No pad exists on the build seat, so the hardware half of W7
    ///         stays a witness.
    /// </summary>
    internal static class SettingsModelCases
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        // design section 6.4, the "rows written (lane)" column; the first
        // entry of each row is the sub-tab's home id
        private static readonly string[][] LaneResetSets =
        {
            new[] { "ingame", "SPing", "SLagNotice", "SInpOv", "SBlkDbg", "SHpPrec", "SDmgNum" },
            new[] { "chatmail", "SIgChat", "SChatTtl", "SNT" },
            new[] { "sound", "SMuteBg", "SMenuMus", "SMusCredit" },
            new[] { "visuals", "SAnimCos", "SBloom", "SChromAb", "SCursor", "SLight", "SPColor", "SShad", "SShake", "STrail" },
            new[] { "perf", "SPerf_Master", "SPerf_BulletCap", "SPerf_EdgeBn", "SPerf_HitSnd", "SPerf_Menu",
                    "SPerf_OOB", "SPerf_PoolInit", "SPerf_Stun", "SFPS", "SFPSCap", "SDeepIdle" },
            new[] { "langmenus", "SHeavyFont", "SInactiveLb" },
            new[] { "privacy" },
            // item 17: the Controls tab carries no descriptor rows; its reset-all
            // writes the keybind config through Keybinds.ResetAll, never ResetSet
            new[] { "controls" },
        };

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // -- T2a: the split, the design's four cases first --------------
            Split(r, "T2a the ordinary case",
                  "Glow (bloom): <color=#88FF88>FULL</color>", true, "Glow (bloom)", "<color=#88FF88>FULL</color>");
            Split(r, "T2a parentheses in the value",
                  "Chat fade after: <color=#FF9966>Off (chat hidden in game)</color>", true,
                  "Chat fade after", "<color=#FF9966>Off (chat hidden in game)</color>");
            Split(r, "T2a a colon in the value half stays in the value (control)",
                  "Label: <color=#88FF88>10:30</color>", true, "Label", "<color=#88FF88>10:30</color>");
            Split(r, "T2a a disclosure never splits",
                  "Blocked senders (12)  ^", false, "", "Blocked senders (12)  ^");
            // beyond the design's four: what the tag rule itself decides
            Split(r, "a colon inside a rich-text tag is not a split point",
                  "<link=a:b>Cursor</link>: Default", true, "<link=a:b>Cursor</link>", "Default");
            Split(r, "a plain '<' with no closing '>' does not hide the colon",
                  "a < b: c", true, "a < b", "c");
            Split(r, "null splits to nothing and loses nothing", null, false, "", "");

            Check(r, "StripTags removes every tag",
                  SettingsModel.StripTags("<color=#88FF88>ON</color>") == "ON",
                  SettingsModel.StripTags("<color=#88FF88>ON</color>"));
            Check(r, "StripTags keeps a plain '<'",
                  SettingsModel.StripTags("a < b") == "a < b", SettingsModel.StripTags("a < b"));

            Check(r, "SubTabIndex reads a home id",
                  SettingsModel.SubTabIndex("sound") == 2, SettingsModel.SubTabIndex("sound").ToString());
            Check(r, "SubTabIndex reads a body name",
                  SettingsModel.SubTabIndex("SubPrivacy") == 6, SettingsModel.SubTabIndex("SubPrivacy").ToString());
            Check(r, "SubTabIndex refuses an unknown name",
                  SettingsModel.SubTabIndex("nope") == -1 && SettingsModel.SubTabIndex("") == -1,
                  SettingsModel.SubTabIndex("nope") + "," + SettingsModel.SubTabIndex(""));

            // -- the table the reset reads ----------------------------------
            var homeless = SettingsDescriptors.All.Where(d => SettingsModel.SubTabIndex(d.Home) < 0)
                                                  .Select(d => d.Key).ToList();
            Check(r, "every descriptor's home is one of the eight sub-tabs",
                  homeless.Count == 0 && SettingsDescriptors.All.Length > 0,
                  "rows=" + SettingsDescriptors.All.Length + " homeless={" + string.Join(",", homeless) + "}");
            var storeless = SettingsDescriptors.All.Where(d => d.BulkReset && !d.StoresValue)
                                                   .Select(d => d.Key).ToList();
            Check(r, "no row that stores no value is bulk-written",
                  storeless.Count == 0, "{" + string.Join(",", storeless) + "}");

            // -- A6, the legs the table decides without a client --------------
            // (the help body and the byte-equal recommendation are painted,
            // so they stay with the in-game self-test)
            var noReason = SettingsDescriptors.All.Where(d => string.IsNullOrEmpty(SettingsDescriptors.ReasonTr(d.Key)))
                                                  .Select(d => d.Key).ToList();
            Check(r, "A6 every row has a reason", noReason.Count == 0, "{" + string.Join(",", noReason) + "}");
            var noWhen = SettingsDescriptors.All.Where(d => !d.StoresValue && string.IsNullOrEmpty(SettingsDescriptors.WhenToPressTr(d.Key)))
                                                .Select(d => d.Key).ToList();
            Check(r, "A6 every row that stores no value has a when-to-press line", noWhen.Count == 0,
                  "stores-no-value=" + SettingsDescriptors.All.Count(d => !d.StoresValue) + " without={" + string.Join(",", noWhen) + "}");
            var selfHelp = SettingsDescriptors.All.Where(d => string.IsNullOrEmpty(d.HelpTargetId) || d.HelpTargetId == d.Key)
                                                  .Select(d => d.Key).ToList();
            Check(r, "A6 no row's help target is its own actuating control", selfHelp.Count == 0,
                  "{" + string.Join(",", selfHelp) + "}");

            // -- T5-g, selection half: exact set per sub-tab ------------------
            int sum = 0;
            foreach (var row in LaneResetSets)
            {
                string home = row[0];
                var want = new HashSet<string>(row.Skip(1));
                List<string> got = SettingsModel.ResetSet(home);
                sum += got.Count;
                var gotSet = new HashSet<string>(got);
                var missing = want.Where(k => !gotSet.Contains(k)).OrderBy(k => k, StringComparer.Ordinal).ToList();
                var extra = gotSet.Where(k => !want.Contains(k)).OrderBy(k => k, StringComparer.Ordinal).ToList();
                bool ok = missing.Count == 0 && extra.Count == 0 && got.Count == gotSet.Count;
                Check(r, "T5-g " + home + " writes exactly its " + want.Count, ok,
                      "written=" + got.Count + " {" + string.Join(",", got) + "}"
                      + (missing.Count > 0 ? " missing={" + string.Join(",", missing) + "}" : "")
                      + (extra.Count > 0 ? " extra={" + string.Join(",", extra) + "}" : ""));
            }
            Check(r, "T5-g a home outside the bar writes nothing",
                  SettingsModel.ResetSet("nope").Count == 0, SettingsModel.ResetSet("nope").Count.ToString());
            r.Report.Append("INFO | T5-g the eight sets sum to ").Append(sum)
             .Append(" (printed for information, never asserted)").Append('\n');

            // -- M1 (design 6.3): which source activates which kind ------------
            var enter = SettingsModel.SettingsActivation.Enter;
            var space = SettingsModel.SettingsActivation.Space;
            Accepts(r, "M1 Space never arms or confirms a destructive row", "DESTRUCTIVE", space, false);
            Accepts(r, "M1 Enter arms and confirms a destructive row", "DESTRUCTIVE", enter, true);
            Accepts(r, "M1 Enter activates an action row", "ACTION", enter, true);
            Accepts(r, "M1 Space activates an action row", "ACTION", space, true);
            Accepts(r, "M1 Enter opens a dropdown", "DROPDOWN", enter, true);
            Accepts(r, "M1 Space opens a dropdown", "DROPDOWN", space, true);
            var inert = new List<string>();
            foreach (var kind in new[] { "SWITCH", "SEGMENTED", "SLIDER" })
                foreach (var src in new[] { enter, space })
                    if (SettingsModel.ActivationAccepts(kind, src)) inert.Add(kind + "/" + src);
            Check(r, "M1 Enter and Space never activate a switch, a segmented row or a slider",
                  inert.Count == 0, "accepted={" + string.Join(",", inert) + "}");
            // -- L3 (design 6.3): a disclosure steps with Left and Right only ---
            var disclosure = new List<string>();
            foreach (var src in new[] { enter, space })
                if (SettingsModel.ActivationAccepts("DISCLOSURE", src)) disclosure.Add("DISCLOSURE/" + src);
            Check(r, "L3 Enter and Space never toggle a disclosure row",
                  disclosure.Count == 0, "accepted={" + string.Join(",", disclosure) + "}");
            // -- L2 (design 6.3, W7's source route): the controller's buttons -----
            string pad = Dispatch(SettingsModel.PadKey(false, true, false), 3) + "|"
                       + Dispatch(SettingsModel.PadKey(true, false, false), 3) + "|"
                       + Dispatch(SettingsModel.PadKey(false, false, true), 3) + "|"
                       + Dispatch(SettingsModel.PadKey(false, false, false), 3);
            Check(r, "L2 the shoulders move the sub-tab and the activate button activates the focused row",
                  pad == "switch:4|switch:2|activate:Pad|", pad);
            string wrap = Dispatch(SettingsModel.PadKey(false, true, false), 7) + "|" + Dispatch(SettingsModel.PadKey(true, false, false), 0);
            Check(r, "L2 the shoulders wrap at both ends of the bar", wrap == "switch:0|switch:7", wrap);
            var pads = SettingsModel.SettingsActivation.Pad;
            Accepts(r, "L2 the activate button never arms or confirms a destructive row", "DESTRUCTIVE", pads, false);
            Accepts(r, "L2 the activate button activates an action row", "ACTION", pads, true);
            Accepts(r, "L2 the activate button opens a dropdown", "DROPDOWN", pads, true);
            var padInert = new List<string>();
            foreach (var kind in new[] { "SWITCH", "SEGMENTED", "SLIDER", "DISCLOSURE" })
                if (SettingsModel.ActivationAccepts(kind, pads)) padInert.Add(kind);
            Check(r, "L2 the activate button never activates a switch, a segmented row, a slider or a disclosure",
                  padInert.Count == 0, "accepted={" + string.Join(",", padInert) + "}");
            Keys(r, "M1 the Space key reaches the row as Space, never as Enter",
                 SettingsModel.SettingsKey.Space, 0, "activate:Space");
            Keys(r, "M1 the Enter key reaches the row as Enter", SettingsModel.SettingsKey.Enter, 0, "activate:Enter");
            Keys(r, "Tab moves to the next sub-tab and wraps", SettingsModel.SettingsKey.Tab, 7, "switch:0");
            Keys(r, "Shift+Tab moves to the previous sub-tab and wraps", SettingsModel.SettingsKey.ShiftTab, 0, "switch:7");
            // item 17: a keybind row arms its capture from Enter, Space or the pad
            Accepts(r, "item 17 Enter arms a keybind row's capture", "KEYBIND", enter, true);
            Accepts(r, "item 17 Space arms a keybind row's capture", "KEYBIND", space, true);
            Accepts(r, "item 17 the activate button arms a keybind row's capture", "KEYBIND", pads, true);
            Check(r, "item 17 Controls is the eighth sub-tab",
                  SettingsModel.SubTabIndex("controls") == 7 && SettingsModel.SubTabIndex("SubControls") == 7
                  && SettingsModel.SubTabHomes.Length == 8 && SettingsModel.SubTabBodies.Length == 8,
                  SettingsModel.SubTabIndex("controls") + "," + SettingsModel.SubTabHomes.Length);
            string moves = Dispatch(SettingsModel.SettingsKey.Up, 3) + "|" + Dispatch(SettingsModel.SettingsKey.Down, 3) + "|"
                         + Dispatch(SettingsModel.SettingsKey.Left, 3) + "|" + Dispatch(SettingsModel.SettingsKey.Right, 3) + "|"
                         + Dispatch(SettingsModel.SettingsKey.Pin, 3) + "|" + Dispatch(SettingsModel.SettingsKey.None, 3);
            Check(r, "Up/Down move the focus, Left/Right step the row, F1 pins, no key does nothing",
                  moves == "focus:-1|focus:1|step:-1|step:1|pin|", moves);
            return r;
        }

        private static void Accepts(SelfTestResult r, string name, string kind,
                                    SettingsModel.SettingsActivation source, bool want)
        {
            bool got = SettingsModel.ActivationAccepts(kind, source);
            Check(r, name, got == want, kind + "/" + source + " accepted=" + got);
        }

        /// <summary>Every page action one key reaches, in call order.</summary>
        private static string Dispatch(SettingsModel.SettingsKey key, int subTab)
        {
            var got = new List<string>();
            SettingsModel.DispatchKey(key, subTab, SettingsModel.SubTabHomes.Length,
                t => got.Add("switch:" + t), d => got.Add("focus:" + d), d => got.Add("step:" + d),
                s => got.Add("activate:" + s), () => got.Add("pin"));
            return string.Join(";", got);
        }

        private static void Keys(SelfTestResult r, string name, SettingsModel.SettingsKey key, int subTab, string want)
        {
            string got = Dispatch(key, subTab);
            Check(r, name, got == want, key + " on sub-tab " + subTab + " -> " + (got.Length == 0 ? "nothing" : got));
        }

        private static void Split(SelfTestResult r, string name, string input, bool wantSplit,
                                  string wantLabel, string wantValue)
        {
            string label, value;
            bool split = SettingsModel.SplitSettingLabel(input, out label, out value);
            bool ok = split == wantSplit && label == wantLabel && value == wantValue;
            Check(r, name, ok, "split=" + split + " label=[" + label + "] value=[" + value + "]");
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
