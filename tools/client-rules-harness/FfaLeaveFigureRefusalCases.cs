using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// FAQ-R2 M2: the client's reading of the server's leave-figure refusal,
    /// EXECUTED. submit_ffa_match answers a report with a left_early, non-absent
    /// entry and no game_points_at_leave with 422. The cases run on both
    /// overloads of FfaReportRules.IsTerminalRefusal (the status code; the
    /// formatted response text) and assert: 422 is not terminal, 409 and 403
    /// are terminal, 400 is not terminal, and the 422 text has the
    /// "HTTP 422: " form. The response text is built by the client's own rule
    /// (SecureRouteRules.RequestErrorText), with a body in the server's form
    /// whose two ids carry the digits 409 and 403. The ids are placeholders
    /// outside the SteamID64 shape: the text overload reads the code only from
    /// an "HTTP &lt;code&gt;:" prefix or an "HTTP/1.1 &lt;code&gt; " status line,
    /// so a placeholder reads as a real id would, and an id in SteamID64 shape
    /// must be on the accepted list in backend/tests/test_music_probe_gate.py.
    ///
    /// The cases are written against a pair of functions, so the same cases run
    /// on the real overloads and on two mutants: one that makes 422 terminal in
    /// the code overload and one that does it in the text overload. Each mutant
    /// must fail exactly one case, its own overload's 422 case.
    /// </summary>
    internal static class FfaLeaveFigureRefusalCases
    {
        internal sealed class Result
        {
            internal int Run, Fail;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private const string Body =
            "{\"detail\":\"game_points_at_leave is required on every left_early entry that is not absent; "
            + "missing for 00000000000000409, 00000000000000403\"}";

        private static string Text(long code, string body)
        {
            return SecureRouteRules.RequestErrorText(code, body, "HTTP/1.1 " + code, null, false);
        }

        /// <summary>(case name, passed) for every case, on the given pair.</summary>
        private static List<KeyValuePair<string, bool>> Cases(Func<long, bool> byCode, Func<string, bool> byText)
        {
            var c = new List<KeyValuePair<string, bool>>();
            string text422 = Text(422, Body);
            c.Add(new KeyValuePair<string, bool>("code 422 is not terminal", !byCode(422L)));
            c.Add(new KeyValuePair<string, bool>("text 422 is not terminal", !byText(text422)));
            c.Add(new KeyValuePair<string, bool>("text 422 is the HTTP <code>: <body> form",
                text422.StartsWith("HTTP 422: ", StringComparison.Ordinal)));
            c.Add(new KeyValuePair<string, bool>("code 409 is terminal", byCode(409L)));
            c.Add(new KeyValuePair<string, bool>("text 409 is terminal", byText(Text(409, "{\"detail\":\"Duplicate room id\"}"))));
            c.Add(new KeyValuePair<string, bool>("code 403 is terminal", byCode(403L)));
            c.Add(new KeyValuePair<string, bool>("text 403 is terminal", byText(Text(403, "{\"detail\":\"report quarantined\"}"))));
            c.Add(new KeyValuePair<string, bool>("code 400 is not terminal", !byCode(400L)));
            c.Add(new KeyValuePair<string, bool>("text 400 is not terminal", !byText(Text(400, "{\"detail\":\"bad signature\"}"))));
            return c;
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
            Func<long, bool> code = FfaReportRules.IsTerminalRefusal;
            Func<string, bool> text = FfaReportRules.IsTerminalRefusal;

            // The real overloads: every case holds.
            foreach (var kv in Cases(code, text))
                Check(r, "real: " + kv.Key, kv.Value, kv.Value ? "holds" : "broken");

            // The mutation controls: each mutant fails its own overload's 422
            // case, and only cases of its own overload.
            Func<long, bool> codeMutant = s => s == 422L || FfaReportRules.IsTerminalRefusal(s);
            Func<string, bool> textMutant = s => (s != null && s.StartsWith("HTTP 422:", StringComparison.Ordinal))
                                                 || FfaReportRules.IsTerminalRefusal(s);
            Control(r, "code overload makes 422 terminal", Cases(codeMutant, text), "code 422 is not terminal");
            Control(r, "text overload makes 422 terminal", Cases(code, textMutant), "text 422 is not terminal");
            return r;
        }

        private static void Control(Result r, string mutant, List<KeyValuePair<string, bool>> cases, string itsCase)
        {
            var failed = new List<string>();
            foreach (var kv in cases)
                if (!kv.Value) failed.Add(kv.Key);
            bool ok = failed.Count == 1 && failed[0] == itsCase;
            Check(r, "mutant (" + mutant + ") is caught by its own case", ok,
                  failed.Count == 0 ? "no case failed" : string.Join("; ", failed));
        }
    }
}
