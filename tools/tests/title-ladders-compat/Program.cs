using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;

namespace CompetitiveRounds
{
    /// <summary>
    /// Merge pass 5, item 4: the title ladders client against the server's
    /// CURRENT answer. backend/tests/test_title_ladders_current_server_compat.py
    /// copies the shipped parser (ApiClient's title-ladder members and the
    /// json helpers they call) and the Titles section's text and rung members
    /// (TitleLaddersUI) out of the plugin sources into Extracted.g.cs, compiles
    /// them here beside the real plugin/TitleLadderRules.cs, and runs this
    /// program over each answer file it is given.
    ///
    /// For each answer it prints one tab-separated ANSWER line, one PLAN line
    /// and one LINE line per parsed ladder: what the client parsed, what the
    /// section renders, what the button decides and the progress text the
    /// dropdown shows. The Python test is the oracle: it reads the same answer
    /// file and compares. Any exception prints THREW and exits 1.
    /// </summary>
    internal static class Program
    {
        private static string F(string v) => v ?? "null";

        private static int Main(string[] args)
        {
            int rc = 0;
            foreach (var path in args)
            {
                string name = Path.GetFileName(path);
                try { Run(name, File.ReadAllText(path)); }
                catch (Exception e)
                {
                    Console.WriteLine("THREW\tfile=" + name + "\t" + e.GetType().Name + ": " + e.Message);
                    rc = 1;
                }
            }
            return rc;
        }

        private static void Run(string name, string body)
        {
            var d = ApiClient.ParseTitleLadders(body);
            if (d == null)
            {
                Console.WriteLine("ANSWER\tfile=" + name + "\tnull=True");
                return;
            }
            Console.WriteLine("ANSWER\tfile=" + name + "\tnull=False\tsteam_id=" + F(d.steam_id)
                + "\tactive_line=" + F(d.active_line) + "\tlines=" + d.lines.Count);

            var ids = new List<string>();
            var skus = new List<IList<string>>();
            foreach (var ln in d.lines)
            {
                ids.Add(ln.line);
                skus.Add(ln.rungs.Select(r => r.sku).ToList());
            }
            var plan = TitleLadderRules.PlanSection(ids, skus, TitleLaddersUI.MAX_LINES);
            Console.WriteLine("PLAN\tfile=" + name
                + "\trendered=" + string.Join(",", plan.Lines.Select(i => ids[i]))
                + "\tunrendered=" + plan.Unrendered
                + "\tfolded=" + string.Join(",", plan.Folded.OrderBy(s => s, StringComparer.Ordinal)));

            foreach (var ln in d.lines)
            {
                var rungs = TitleLaddersUI.RulesRungs(ln, null);
                var dec = TitleLadderRules.Decide(rungs, ln.games, true, null, null);
                int heldIdx = TitleLadderRules.HeldRungIndex(rungs, dec.Held);
                var states = rungs.Select(r => TitleLadderRules.StateOf(r, dec.Held, dec.NextTier).ToString());
                Console.WriteLine("LINE\tfile=" + name + "\tline=" + ln.line
                    + "\tskus=" + string.Join(",", ln.rungs.Select(r => r.sku))
                    + "\ttiers=" + string.Join(",", ln.rungs.Select(r => r.tier.ToString(CultureInfo.InvariantCulture)))
                    + "\towned=" + string.Join(",", ln.rungs.Where(r => r.owned).Select(r => r.sku))
                    + "\tactive=" + string.Join(",", ln.rungs.Where(r => r.active).Select(r => r.sku))
                    + "\treached=" + string.Join(",", ln.rungs.Where(r => r.reached).Select(r => r.sku))
                    + "\tunit=" + F(ln.unit) + "\tgroup=" + F(ln.group) + "\tkind=" + F(ln.kind)
                    + "\tmodes=" + F(ln.modes) + "\tcondition=" + F(ln.condition)
                    + "\thas_streak=" + ln.has_streak + "\tstreak=" + ln.streak
                    + "\theld=" + dec.Held + "\tnext=" + dec.NextTier
                    + "\tlabel=" + dec.Label + "\treason=" + dec.Reason
                    + "\theldsku=" + (heldIdx >= 0 ? rungs[heldIdx].Sku : "-")
                    + "\tstates=" + string.Join(",", states)
                    + "\tprogress=" + TitleLaddersUI.ProgressText(ln, dec)
                    + "\twhy=" + F(TitleLaddersUI.ReasonText(dec, ln.unit)));
            }
        }
    }

    /// <summary>The catalogue lookups the extracted members call, as identity
    /// and string.Format: this program checks which sentence is chosen, not
    /// its translation.</summary>
    internal static class I18n
    {
        internal static string Tr(string s) => s;
        internal static string TrF(string f, params object[] a) => string.Format(CultureInfo.InvariantCulture, f, a);
    }
}
