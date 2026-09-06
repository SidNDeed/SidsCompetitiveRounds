using System;

namespace CompetitiveRounds.Harness
{
    /// <summary>Runs H2HRules.SelfTest and reports it in a shape a test can
    /// read: one line per case, then a summary line, then an exit code.
    ///
    /// Exit 0 only when every case passed AND at least one ran. A harness that
    /// runs nothing and exits 0 is the failure mode this is guarding against,
    /// so "run" is printed and the gate asserts on it.</summary>
    internal static class Program
    {
        private static int Main(string[] args)
        {
            bool quiet = Array.IndexOf(args, "--quiet") >= 0;
            int fail;
            int run;
            try
            {
                run = H2HRules.SelfTest(quiet ? (Action<string>)null : Console.WriteLine, out fail);
            }
            catch (Exception ex)
            {
                Console.WriteLine("[H2H] selftest THREW: " + ex);
                Console.WriteLine("h2h-harness run=0 fail=1 verdict=THREW");
                return 2;
            }

            string verdict = run > 0 && fail == 0 ? "PASS" : "FAIL";
            Console.WriteLine("h2h-harness run=" + run + " fail=" + fail + " verdict=" + verdict);
            return verdict == "PASS" ? 0 : 1;
        }
    }
}
