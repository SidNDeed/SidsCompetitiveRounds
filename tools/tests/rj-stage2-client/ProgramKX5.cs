using System;
using System.Collections.Generic;
using System.Linq;

namespace CompetitiveRounds.Stage2Harness
{
    using R = TeamHoldRules;
    using F = FfaReadmitRules;

    internal static partial class Program
    {
        // ── KX5: the record over the FFA P2 record (V3 S4 step 2) ────────────

        /// <summary>A pool where every shared entry is illegal for a picker
        /// holding "Blocker" (it blacklists category x), so each list is made
        /// of substitutes: N1 (no-repeat, heavy) first, then C1 or C2.</summary>
        private static F.OfferPool KxPool()
        {
            var p = new F.OfferPool();
            p.Add(new F.CardFacts { Name = "X1", Weight = 1, Categories = new[] { "x" } });
            p.Add(new F.CardFacts { Name = "X2", Weight = 1, Categories = new[] { "x" } });
            p.Add(new F.CardFacts { Name = "N1", Weight = 200 });
            p.Add(new F.CardFacts { Name = "C1", Weight = 10 });
            p.Add(new F.CardFacts { Name = "C2", Weight = 10 });
            p.Add(new F.CardFacts { Name = "Blocker", Weight = 1, Blacklisted = new[] { "x" } });
            p.NoRepeat.Add("N1");
            return p;
        }

        private static F.SeqState KxSeq()
        {
            return new F.SeqState { Seed = 77, OpeningDraws = 0, SetAt = idx => new[] { "X1", "X2" }, UsedNoRepeatFold = new HashSet<string>() };
        }

        /// <summary>One seat's view of a run of pick phases in a flagged room.
        /// Each phase: the master builds (or adopts) the record over the
        /// picker set, publishes it as cr_toff, every client adopts it; the
        /// seats' lists are the record's lists; a held seat is granted entry
        /// 0. <paramref name="heldAt"/> names the phase in which seat 1 is
        /// held (-1: nobody leaves).</summary>
        private sealed class RecordRun
        {
            internal readonly F.SpendState MasterSpend = new F.SpendState();
            internal readonly F.SpendState ClientSpend = new F.SpendState();
            internal readonly Dictionary<int, int> Draw = new Dictionary<int, int>();
            internal readonly List<string> Lists = new List<string>();
            internal readonly List<string> Grants = new List<string>();
            internal string Off;

            internal void Phase(int phase, int[] pickers, bool held, bool sameCards = true, Func<string> roll = null, F.SpendState masterSpend = null)
            {
                var spend = masterSpend ?? MasterSpend;
                if (!R.BuildsRecord(true, held)) { Lists.Add(phase + ":none"); return; }
                var rec = R.MasterOff(Off, "g-8", phase, () => R.BuildOff("g-8", phase, pickers, sameCards,
                    pid => (Draw.ContainsKey(pid) ? Draw[pid] : 0) + 1, pid => new List<string> { "Blocker" },
                    KxPool(), KxSeq(), 3, roll, spend));
                string enc = R.EncodeOff(rec);
                if (enc == null) { Lists.Add(phase + ":unencoded"); return; }
                Off = enc;
                R.AdoptOff(rec, spend, (pid, k) => Draw[pid] = k);
                R.AdoptOff(R.ParseOff(Off), ClientSpend, null);
                foreach (var pid in pickers)
                {
                    var l = R.ScreenOf(Off, "g-8", phase, pid);
                    Lists.Add(phase + ":" + pid + "=" + (l == null ? "-" : string.Join(",", l)));
                }
                if (held)
                {
                    string card = R.Entry0Of(Off, "g-8", phase, 1);
                    Grants.Add(card);
                    R.NoteGrantApplied(spend, card);
                }
            }
        }

        private static void RegisterKX5()
        {
            // T4.1 twin run: identical seeds and decks; in run A seat 1 stays,
            // in run B it is held in phase 2. Every seat's lists are identical
            // in both runs, and the held seat's grant is entry 0 of the same
            // list run A showed it.
            Add("t41_twin_run", () =>
            {
                var a = new RecordRun(); var b = new RecordRun();
                for (int ph = 1; ph <= 3; ph++)
                {
                    a.Phase(ph, new[] { 0, 1 }, false);
                    b.Phase(ph, new[] { 0, 1 }, ph == 2);
                }
                string listA = string.Join(" ", a.Lists), listB = string.Join(" ", b.Lists);
                string shown = a.Lists.First(x => x.StartsWith("2:1=")).Substring(4).Split(',')[0];
                return All(Expect("lists", listB, listA), Expect("grant", b.Grants.Count == 1 ? b.Grants[0] : null, shown),
                           Expect("record", listA.Contains("none"), false));
            });
            // T4.2 ledger: a substitute spent in phase 2 never appears in a
            // later phase for any seat, on the master and on every client
            // (the client ledger is the record's), and across a promotion.
            Add("t42_ledger", () =>
            {
                var r = new RecordRun();
                r.Phase(2, new[] { 0 }, false);
                bool spent = r.Lists[0].Contains("N1");
                var promoted = new F.SpendState();
                promoted.Ledger.AddRange(r.ClientSpend.Ledger);   // the new master's ledger is the one it adopted
                r.Phase(4, new[] { 0, 1 }, false, masterSpend: promoted);
                bool again = r.Lists.Skip(1).Any(x => x.Contains("N1"));
                return All(Expect("spent in 2", spent, true), Expect("again in 4", again, false),
                           Expect("client ledger", r.ClientSpend.Ledger.Contains("N1"), true));
            });
            // T4.4 same-card off and promotion: rule p holds the master's own
            // roll; a promoted master adopts the readable record and never
            // rewrites it, so the grant is the first master's entry 0.
            Add("t44_rule_p_promotion", () =>
            {
                var r = new RecordRun();
                int n1 = 0; string[] rollA = { "C1", "C2", "N1" };
                r.Phase(3, new[] { 0, 1 }, true, sameCards: false, roll: () => rollA[n1++ % rollA.Length]);
                string first = r.Grants[0];
                var rec = R.ParseOff(r.Off);
                int n2 = 0; string[] rollB = { "C2", "N1", "C1" };
                r.Phase(3, new[] { 0, 1 }, true, sameCards: false, roll: () => rollB[n2++ % rollB.Length]);
                return All(Expect("rule", rec != null ? rec.Rule : '?', 'p'), Expect("adopted", r.Grants[1], first),
                           Expect("first roll", first, rec != null ? rec.FirstOf(1) : null));
            });
            // The codec: cr_toff round-trips {G}:{phase}:{rule}:{ledger}:{entries};
            // a name with a reserved separator writes no record; another G or
            // phase reads as no record.
            Add("tx5_off_codec", () =>
            {
                var r = new F.FfaOfferRecord { Epoch = "g-8", Game = 2, Cycle = 0, Rule = 's' };
                r.Ledger.Add("N1");
                var e = new F.OfferEntry { K = 3 }; e.Names.AddRange(new[] { "A", "B" }); r.Entries[1] = e;
                string enc = R.EncodeOff(r);
                var back = R.ParseOff(enc);
                var bad = new F.FfaOfferRecord { Epoch = "g-8", Game = 2, Rule = 's' };
                var be = new F.OfferEntry { K = 1 }; be.Names.Add("A:B"); bad.Entries[0] = be;
                return All(Expect("enc", enc, "g-8:2:s:N1:1/3/A,B"), Expect("back", back != null ? back.FirstOf(1) : null, "A"),
                           Expect("bad", R.EncodeOff(bad), null), Expect("other G", R.Entry0Of(enc, "g-9", 2, 1), null),
                           Expect("other phase", R.Entry0Of(enc, "g-8", 3, 1), null), Expect("entry0", R.Entry0Of(enc, "g-8", 2, 1), "A"));
            });
        }
    }
}
