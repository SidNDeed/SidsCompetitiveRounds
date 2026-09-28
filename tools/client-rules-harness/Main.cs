using System;

namespace CompetitiveRounds.Harness
{
    /// <summary>Runs the client rule self-tests and reports them in a shape a
    /// test can read: one line per case, one summary line per suite, then a
    /// combined summary and an exit code.
    ///
    /// Exit 0 only when every case passed AND at least one ran, per suite. A
    /// harness that runs nothing and exits 0 is the failure this is guarding
    /// against, so "run" is printed and the gate asserts on it.</summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;
            int totalRun = 0, totalFail = 0, suites = 0;

            if (!RunSuite("logscrub", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = LogScrub.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("topstrip", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = TopStripBand.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("ffareport", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = FfaReportRules.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("rostercensus", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = RosterCensusRules.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("bindersort", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = BinderSortRules.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("laddershop", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = TitleLadderRules.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("roomrules", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = RoomRulesStrip.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            if (!RunSuite("musiclevels", quiet, ref totalRun, ref totalFail, ref suites,
                          () =>
                          {
                              var r = MusicLevels.SelfTest();
                              return new Suite(r.Passed + r.Failed, r.Failed, r.Report.ToString());
                          }))
                return 2;

            string verdict = suites > 0 && totalRun > 0 && totalFail == 0 ? "PASS" : "FAIL";
            Console.WriteLine("client-rules-harness suites=" + suites
                              + " run=" + totalRun + " fail=" + totalFail
                              + " verdict=" + verdict);
            return verdict == "PASS" ? 0 : 1;
        }

        private readonly struct Suite
        {
            internal Suite(int run, int fail, string report) { Run = run; Fail = fail; Report = report; }
            internal int Run { get; }
            internal int Fail { get; }
            internal string Report { get; }
        }

        /// <summary>False means the harness THREW, which is its own outcome:
        /// "no failures" and "never reached the assertions" must not print the
        /// same line.</summary>
        private static bool RunSuite(string name, bool quiet, ref int totalRun, ref int totalFail,
                                     ref int suites, Func<Suite> body)
        {
            Suite s;
            try { s = body(); }
            catch (Exception ex)
            {
                Console.WriteLine("[" + name + "] selftest THREW: " + ex);
                Console.WriteLine(name + " run=0 fail=1 verdict=THREW");
                Console.WriteLine("client-rules-harness suites=0 run=0 fail=1 verdict=THREW");
                return false;
            }
            if (!quiet && !string.IsNullOrEmpty(s.Report))
                foreach (string line in s.Report.Split('\n'))
                    if (line.Length > 0) Console.WriteLine("[" + name + "] " + line);
            Console.WriteLine(name + " run=" + s.Run + " fail=" + s.Fail
                              + " verdict=" + (s.Run > 0 && s.Fail == 0 ? "PASS" : "FAIL"));
            totalRun += s.Run;
            totalFail += s.Fail;
            suites++;
            return true;
        }
    }
}
