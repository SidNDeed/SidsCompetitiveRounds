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
            new[] { "ingame", "SPing", "SLagNotice", "SInpOv", "SBlkDbg", "SHpPrec" },
            new[] { "chatmail", "SIgChat", "SChatTtl", "SNT" },
            new[] { "sound", "SMuteBg", "SMenuMus", "SMusCredit" },
            new[] { "visuals", "SAnimCos", "SBloom", "SChromAb", "SCursor", "SLight", "SPColor", "SShad", "SShake", "STrail" },
            new[] { "perf", "SPerf_Master", "SPerf_BulletCap", "SPerf_EdgeBn", "SPerf_HitSnd", "SPerf_Menu",
                    "SPerf_OOB", "SPerf_PoolInit", "SPerf_Stun", "SFPS", "SFPSCap", "SDeepIdle" },
            new[] { "langmenus", "SHeavyFont", "SInactiveLb" },
            new[] { "privacy" },
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
            Check(r, "every descriptor's home is one of the seven sub-tabs",
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
            r.Report.Append("INFO | T5-g the seven sets sum to ").Append(sum)
             .Append(" (printed for information, never asserted)").Append('\n');
            return r;
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
