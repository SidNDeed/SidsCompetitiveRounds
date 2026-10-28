// RJ readmission client rules harness: a registry of named cases, each a
// falsifiable sentence run against the REAL rule files. `RjRules --list`
// prints the case names; `RjRules <case>` runs one case and exits 0 on pass.
using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds
{
    internal sealed class CaseFailed : Exception { internal CaseFailed(string m) : base(m) { } }

    internal static class Check
    {
        internal static void True(bool c, string what) { if (!c) throw new CaseFailed(what); }
        internal static void Eq<T>(T want, T got, string what)
        {
            if (!EqualityComparer<T>.Default.Equals(want, got))
                throw new CaseFailed(what + ": want <" + want + "> got <" + got + ">");
        }
        internal static void Seq<T>(IEnumerable<T> want, IEnumerable<T> got, string what)
        {
            var a = want.ToList(); var b = got.ToList();
            if (!a.SequenceEqual(b))
                throw new CaseFailed(what + ": want [" + string.Join(",", a) + "] got [" + string.Join(",", b) + "]");
        }
    }

    internal static class RulesProgram
    {
        internal static readonly SortedDictionary<string, Action> Cases = new SortedDictionary<string, Action>(StringComparer.Ordinal);

        internal static void Add(string name, Action body)
        {
            if (Cases.ContainsKey(name)) throw new InvalidOperationException("duplicate case " + name);
            Cases[name] = body;
        }

        private static int Main(string[] args)
        {
            // Every static class named Cases* registers its cases (one file per
            // piece), in name order so the registry is the same on every run.
            foreach (var t in typeof(RulesProgram).Assembly.GetTypes()
                         .Where(t => t.Name.StartsWith("Cases", StringComparison.Ordinal))
                         .OrderBy(t => t.Name, StringComparer.Ordinal))
            {
                var m = t.GetMethod("Register", System.Reflection.BindingFlags.Static
                                                | System.Reflection.BindingFlags.NonPublic
                                                | System.Reflection.BindingFlags.Public);
                if (m != null) m.Invoke(null, null);
            }
            if (args.Length == 1 && args[0] == "--list")
            {
                foreach (var k in Cases.Keys) Console.WriteLine(k);
                return 0;
            }
            var names = args.Length == 0 || args[0] == "all" ? Cases.Keys.ToList() : args.ToList();
            int pass = 0;
            foreach (var n in names)
            {
                Action body;
                if (!Cases.TryGetValue(n, out body)) { Console.WriteLine("FAIL " + n + " (no such case)"); continue; }
                try { body(); Console.WriteLine("PASS " + n); pass++; }
                catch (CaseFailed f) { Console.WriteLine("FAIL " + n + ": " + f.Message); }
                catch (Exception ex) { Console.WriteLine("FAIL " + n + ": threw " + ex.GetType().Name + " " + ex.Message); }
            }
            if (names.Count == 0) { Console.WriteLine("FAIL no cases"); return 1; }
            return pass == names.Count ? 0 : 1;
        }
    }
}
