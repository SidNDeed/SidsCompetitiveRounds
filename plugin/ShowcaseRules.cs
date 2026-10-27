using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Board row 31: the broadcast idle showcase's rotation, kept free of
    /// Unity, Photon, BepInEx and I18n so it runs under a plain compiler. The
    /// SelfTest below is EXECUTED by tools/client-rules-harness (#391);
    /// IdleShowcase hands these rules the Compare tab's own metric list
    /// (NativeUI.CompareMetricNames: COMPARE_METRICS, in its order) and the
    /// configured dwell, and plays the views that come back.
    ///
    /// The rotation is Home, then every Compare metric in the list's order
    /// with one dwell each ([Broadcast] ShowcaseMetricSeconds, default 15 s),
    /// then two leaderboard profiles, the 2v2 tab and the FFA tab. Only the
    /// metric walk changed with row 31; Home, the profiles and the two tabs
    /// keep the dwells they had before it (18, 30, 30, 22 and 22 s), and the
    /// skip rule (Next) is the one IdleShowcase used before the walk.
    ///
    /// No catalogue string lives here: the metric names are the array's raw
    /// English switch keys and the only text this file builds is a log line,
    /// so it is deliberately NOT in tools/i18n_extract.py's FILES list (#464).
    /// </summary>
    internal static class ShowcaseRules
    {
        internal const int KIND_HOME = 0, KIND_COMPARE = 1, KIND_PROFILE = 2, KIND_TEAM = 3, KIND_FFA = 4;

        internal const float HOME_SECONDS = 18f, PROFILE_SECONDS = 30f, TEAM_SECONDS = 22f, FFA_SECONDS = 22f;

        /// <summary>The per-metric dwell when the config names none (or a
        /// value that cannot be a dwell), and the bounds any other value is
        /// held to: a typo can neither strobe the walk nor freeze it.</summary>
        internal const float DEFAULT_METRIC_SECONDS = 15f, MIN_METRIC_SECONDS = 3f, MAX_METRIC_SECONDS = 300f;

        /// <summary>One view of the rotation. Arg: the metric's index in the
        /// list for a Compare view (index 0 also sets the Compare selection
        /// up), the profile's turn for a profile view, 0 otherwise.</summary>
        internal struct View
        {
            public int Kind;
            public int Arg;
            public float Dwell;
            public View(int kind, int arg, float dwell) { Kind = kind; Arg = arg; Dwell = dwell; }
        }

        /// <summary>The configured dwell, bounded: zero, negative, NaN or
        /// infinite reads as the default; anything else is held to
        /// [MIN_METRIC_SECONDS, MAX_METRIC_SECONDS].</summary>
        internal static float MetricDwell(float configured)
        {
            if (float.IsNaN(configured) || float.IsInfinity(configured) || configured <= 0f)
                return DEFAULT_METRIC_SECONDS;
            return Math.Min(MAX_METRIC_SECONDS, Math.Max(MIN_METRIC_SECONDS, configured));
        }

        /// <summary>The rotation for this metric list: Home, one Compare view
        /// per metric in list order, two profiles, 2v2, FFA.</summary>
        internal static List<View> Script(IList<string> metrics, float configuredMetricSeconds)
        {
            float d = MetricDwell(configuredMetricSeconds);
            int n = metrics == null ? 0 : metrics.Count;
            var s = new List<View>(n + 5);
            s.Add(new View(KIND_HOME, 0, HOME_SECONDS));
            for (int i = 0; i < n; i++) s.Add(new View(KIND_COMPARE, i, d));
            s.Add(new View(KIND_PROFILE, 0, PROFILE_SECONDS));
            s.Add(new View(KIND_PROFILE, 1, PROFILE_SECONDS));
            s.Add(new View(KIND_TEAM, 0, TEAM_SECONDS));
            s.Add(new View(KIND_FFA, 0, FFA_SECONDS));
            return s;
        }

        /// <summary>The view after `cur` (-1 = the rotation's start), skipping
        /// whole view classes that lack their data, as before the walk: a
        /// Compare view past the setup needs 2+ candidates and a profile needs
        /// 1+ (a cold start with nobody known degrades to Home, 2v2 and FFA).
        /// `wrapped` is true when the step passed the end of the rotation.</summary>
        internal static int Next(IList<View> script, int cur, int candidates, out bool wrapped)
        {
            wrapped = false;
            int len = script == null ? 0 : script.Count;
            if (len == 0) return -1;
            int next = cur + 1;
            if (next >= len || next < 0) next = 0;
            int guard = 0;
            while (guard++ < len)
            {
                var v = script[next];
                bool skip = (v.Kind == KIND_COMPARE && v.Arg > 0 && candidates < 2)
                         || (v.Kind == KIND_PROFILE && candidates < 1);
                if (!skip) break;
                next++;
                if (next >= len) next = 0;
            }
            wrapped = cur >= 0 && next <= cur;
            return next;
        }

        /// <summary>The one log line per metric shown ([SHOWCASE] metric k/n:
        /// name), 1-based so the last line of a full walk reads n/n.</summary>
        internal static string MetricLine(int index, int count, string name)
        {
            return "[SHOWCASE] metric " + (index + 1) + "/" + count + ": " + (name ?? "");
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) --------------

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

        private static string Describe(List<View> s, int from, int to)
        {
            var sb = new StringBuilder();
            for (int i = from; i < to && i < s.Count; i++)
            {
                if (sb.Length > 0) sb.Append(' ');
                sb.Append(s[i].Kind).Append(':').Append(s[i].Arg).Append('@').Append(s[i].Dwell.ToString(System.Globalization.CultureInfo.InvariantCulture));
            }
            return sb.ToString();
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            // 34 distinct names, the length of COMPARE_METRICS at row 31; the
            // cases below hold for any list, which is the point of building
            // the rotation from the tab's own array.
            var metrics = new List<string>();
            for (int i = 0; i < 34; i++) metrics.Add("m" + i.ToString(System.Globalization.CultureInfo.InvariantCulture));

            {
                var s = Script(metrics, 15f);
                bool walk = s.Count == metrics.Count + 5;
                for (int i = 0; walk && i < metrics.Count; i++)
                    walk = s[1 + i].Kind == KIND_COMPARE && s[1 + i].Arg == i && s[1 + i].Dwell == 15f;
                Check(r, "showcase: every metric is one Compare view, in list order, one dwell each",
                      walk, "views=" + s.Count + " first " + Describe(s, 1, 3) + " last " + Describe(s, s.Count - 6, s.Count - 4));
            }

            {
                var s = Script(metrics, 15f);
                int n = s.Count;
                bool rest = s[0].Kind == KIND_HOME && s[0].Dwell == HOME_SECONDS
                         && s[n - 4].Kind == KIND_PROFILE && s[n - 4].Arg == 0 && s[n - 4].Dwell == 30f
                         && s[n - 3].Kind == KIND_PROFILE && s[n - 3].Arg == 1 && s[n - 3].Dwell == 30f
                         && s[n - 2].Kind == KIND_TEAM && s[n - 2].Dwell == 22f
                         && s[n - 1].Kind == KIND_FFA && s[n - 1].Dwell == 22f
                         && HOME_SECONDS == 18f;
                Check(r, "showcase: Home, the two profiles, 2v2 and FFA keep their places and dwells",
                      rest, Describe(s, 0, 1) + " ... " + Describe(s, n - 4, n));
            }

            {
                float a = Script(metrics, 0f)[1].Dwell, b = Script(metrics, -4f)[1].Dwell, c = Script(metrics, float.NaN)[1].Dwell;
                float lo = Script(metrics, 0.5f)[1].Dwell, hi = Script(metrics, 9000f)[1].Dwell, mid = Script(metrics, 21f)[1].Dwell;
                Check(r, "showcase: the metric dwell defaults to 15 s and is held to 3-300 s",
                      a == 15f && b == 15f && c == 15f && lo == 3f && hi == 300f && mid == 21f,
                      "0->" + a + " -4->" + b + " NaN->" + c + " 0.5->" + lo + " 9000->" + hi + " 21->" + mid);
            }

            {
                var s = Script(metrics, 15f);
                // One full rotation with two candidates: every view once, the
                // wrap reported only on the step past FFA.
                var seen = new List<int>();
                int cur = -1, wraps = 0, steps = 0;
                bool w;
                do
                {
                    cur = Next(s, cur, 2, out w);
                    if (w) wraps++; else seen.Add(cur);
                } while (!w && ++steps < 200);
                bool order = seen.Count == s.Count;
                for (int i = 0; order && i < seen.Count; i++) order = seen[i] == i;
                var shown = new StringBuilder();
                foreach (int v in seen)
                    if (s[v].Kind == KIND_COMPARE) shown.Append(MetricLine(s[v].Arg, metrics.Count, metrics[s[v].Arg])).Append('|');
                string lines = shown.ToString();
                bool logs = lines.StartsWith("[SHOWCASE] metric 1/34: m0|", StringComparison.Ordinal)
                         && lines.EndsWith("[SHOWCASE] metric 34/34: m33|", StringComparison.Ordinal);
                Check(r, "showcase: one rotation shows all 34 metrics in order and logs each once",
                      order && wraps == 1 && cur == 0 && logs,
                      "views seen " + seen.Count + "/" + s.Count + ", wraps " + wraps + ", back at " + cur
                      + ", metric lines " + (lines.Length - lines.Replace("|", "").Length));
            }

            {
                var s = Script(metrics, 15f);
                bool w1, w2, w3;
                // The setup view (metric 0) is never skipped here: it gathers
                // the candidates itself and re-steps when it finds fewer than 2.
                int afterHome = Next(s, 0, 0, out w1);
                int afterSetupNobody = Next(s, 1, 0, out w2);   // cold start: nobody known
                int afterSetupOne = Next(s, 1, 1, out w3);      // one candidate: profiles, no metric walk
                bool ok = afterHome == 1 && !w1
                       && s[afterSetupNobody].Kind == KIND_TEAM && !w2
                       && s[afterSetupOne].Kind == KIND_PROFILE && s[afterSetupOne].Arg == 0 && !w3;
                Check(r, "showcase (control): with fewer than 2 candidates the metric walk is skipped, as before",
                      ok, "home->" + afterHome + " setup+nobody->" + afterSetupNobody + " setup+one->" + afterSetupOne);
            }

            return r;
        }
    }
}
