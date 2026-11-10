using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Ask 16(a) R4: BoundedDealRules, executed (suite `dealbound`). The cases
    /// are written against a (decide, pick) pair, so the same cases run on the
    /// real rule and on mutants of it; each mutant must turn its named cases
    /// red (#391: a check that cannot fail proves nothing). Every case prints
    /// its name whatever its verdict.
    /// </summary>
    internal static class BoundedDealRulesCases
    {
        internal sealed class Result
        {
            internal int Run, Fail;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        private delegate BoundedDealRules.Answer DecideFn(int handCount, IList<BoundedDealRules.Candidate> pool);
        private delegate int PickFn(BoundedDealRules.Answer level, IList<BoundedDealRules.Candidate> pool, float roll01);

        private static BoundedDealRules.Candidate C(float weight, bool inHand = false, bool gunLock = false,
                                                    bool blacklisted = false, bool held = false)
        {
            return new BoundedDealRules.Candidate(weight, inHand, gunLock, blacklisted, held);
        }

        private static IList<BoundedDealRules.Candidate> P(params BoundedDealRules.Candidate[] cards)
        {
            return cards;
        }

        private static readonly BoundedDealRules.Candidate Ok = C(10f);
        private static readonly BoundedDealRules.Candidate HeldOnly = C(10f, held: true);
        private static readonly BoundedDealRules.Candidate HandOnly = C(10f, inHand: true);
        private static readonly BoundedDealRules.Candidate GunOnly = C(10f, gunLock: true);
        private static readonly BoundedDealRules.Candidate BlackOnly = C(10f, blacklisted: true);
        private static readonly BoundedDealRules.Candidate HandAndHeld = C(10f, inHand: true, held: true);
        private static readonly BoundedDealRules.Candidate AllFour = C(10f, true, true, true, true);
        private static readonly BoundedDealRules.Candidate HeldUncommon = C(4f, held: true);

        private const BoundedDealRules.Answer V = BoundedDealRules.Answer.Vanilla;
        private const BoundedDealRules.Answer RH = BoundedDealRules.Answer.RelaxHeld;
        private const BoundedDealRules.Answer RHH = BoundedDealRules.Answer.RelaxHeldAndHand;
        private const BoundedDealRules.Answer Any = BoundedDealRules.Answer.AnyDrawable;
        private const BoundedDealRules.Answer None = BoundedDealRules.Answer.NothingDrawable;

        private static List<KeyValuePair<string, bool>> Cases(DecideFn decide, PickFn pick)
        {
            var c = new List<KeyValuePair<string, bool>>();
            Action<string, bool> add = (n, ok) => c.Add(new KeyValuePair<string, bool>(n, ok));

            add("first slot: vanilla checks nothing", decide(0, P(AllFour)) == V);
            add("second slot: the same pool is checked", decide(1, P(AllFour)) == Any);
            add("one acceptable card: vanilla's draw runs", decide(1, P(HeldOnly, Ok, HandOnly)) == V);
            add("the held rule alone: relax held", decide(1, P(HeldOnly)) == RH);
            add("the in-hand rule alone: relax held and hand", decide(1, P(HandOnly)) == RHH);
            add("the gun lock alone: only the last level", decide(1, P(GunOnly)) == Any);
            add("the blacklist alone: only the last level", decide(1, P(BlackOnly)) == Any);
            add("held is relaxed before in-hand",
                decide(1, P(HandOnly, HeldOnly)) == RH && pick(RH, P(HandOnly, HeldOnly), 0f) == 1);
            add("the blacklist is kept while a held, in-hand card remains",
                decide(1, P(BlackOnly, HandAndHeld)) == RHH && pick(RHH, P(BlackOnly, HandAndHeld), 0f) == 1);
            add("the gun lock is kept while a held, in-hand card remains",
                decide(1, P(GunOnly, HandAndHeld)) == RHH && pick(RHH, P(GunOnly, HandAndHeld), 0f) == 1);
            add("a weight-0 card is never counted", decide(1, P(C(0f), HeldOnly)) == RH);
            add("control: the same card at weight 1 is counted", decide(1, P(C(1f), HeldOnly)) == V);
            add("nothing drawable", decide(1, P(C(0f, held: true), C(0f))) == None);
            add("a null pool at a later slot", decide(1, null) == None);
            add("pick: roll 0 takes the first admitted card", pick(RH, P(HandOnly, HeldOnly, HeldUncommon), 0f) == 1);
            add("pick: roll 1 takes the last admitted card", pick(RH, P(HandOnly, HeldOnly, HeldUncommon), 1f) == 2);
            add("pick: vanilla's weights, 0.70 of 10+4 is the first", pick(RH, P(HeldOnly, HeldUncommon), 0.70f) == 0);
            add("pick: vanilla's weights, 0.75 of 10+4 is the second", pick(RH, P(HeldOnly, HeldUncommon), 0.75f) == 1);
            add("pick: a weight-0 card is never picked", pick(Any, P(C(0f), C(1f)), 0f) == 1);
            add("pick: a NaN roll reads as 0", pick(RH, P(HeldOnly, HeldUncommon), float.NaN) == 0);
            add("pick: no pick at the vanilla level", pick(V, P(Ok), 0.5f) == -1);
            bool refused = true;
            for (int i = 0; i <= 100; i++)
            {
                int got = pick(RHH, P(BlackOnly, GunOnly, HandOnly, HeldOnly), i / 100f);
                if (got != 2 && got != 3) refused = false;
            }
            add("pick: never a card the level refuses, over 101 rolls", refused);
            return c;
        }

        private static void Check(Result r, string name, bool ok, string got)
        {
            r.Run++;
            if (!ok) r.Fail++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }

        private static IList<BoundedDealRules.Candidate> Map(IList<BoundedDealRules.Candidate> pool,
                                                             Func<BoundedDealRules.Candidate, BoundedDealRules.Candidate> f)
        {
            if (pool == null) return null;
            var o = new List<BoundedDealRules.Candidate>(pool.Count);
            for (int i = 0; i < pool.Count; i++) o.Add(f(pool[i]));
            return o;
        }

        internal static Result Run()
        {
            var r = new Result();
            DecideFn decide = BoundedDealRules.Decide;
            PickFn pick = BoundedDealRules.Pick;

            foreach (var kv in Cases(decide, pick))
                Check(r, "real: " + kv.Key, kv.Value, kv.Value ? "holds" : "broken");

            Control(r, "the first slot is checked",
                    Cases((h, p) => BoundedDealRules.Decide(Math.Max(h, 1), p), pick),
                    "first slot: vanilla checks nothing");
            Control(r, "a weight-0 card is counted",
                    Cases((h, p) => BoundedDealRules.Decide(h, Map(p, x => C(x.Weight > 0f ? x.Weight : 1f, x.InHand, x.GunLock, x.Blacklisted, x.Held))), pick),
                    "a weight-0 card is never counted", "nothing drawable");
            Control(r, "in-hand is relaxed before held",
                    Cases((h, p) => BoundedDealRules.Decide(h, Map(p, x => C(x.Weight, x.Held, x.GunLock, x.Blacklisted, x.InHand))), pick),
                    "the held rule alone: relax held", "the in-hand rule alone: relax held and hand");
            Control(r, "the blacklist is relaxed early",
                    Cases((h, p) => BoundedDealRules.Decide(h, Map(p, x => C(x.Weight, x.InHand, x.GunLock, false, x.Held))), pick),
                    "the blacklist alone: only the last level", "the blacklist is kept while a held, in-hand card remains");
            Control(r, "the gun lock is relaxed early",
                    Cases((h, p) => BoundedDealRules.Decide(h, Map(p, x => C(x.Weight, x.InHand, false, x.Blacklisted, x.Held))), pick),
                    "the gun lock alone: only the last level", "the gun lock is kept while a held, in-hand card remains");
            Control(r, "vanilla's draw always runs",
                    Cases((h, p) => { var a = BoundedDealRules.Decide(h, p); return a == None ? a : V; }, pick),
                    "the held rule alone: relax held", "second slot: the same pool is checked");
            Control(r, "the pick ignores the level",
                    Cases(decide, (l, p, x) => BoundedDealRules.Pick(l == V ? V : Any, p, x)),
                    "pick: never a card the level refuses, over 101 rolls", "held is relaxed before in-hand");
            Control(r, "the pick ignores the roll",
                    Cases(decide, (l, p, x) => BoundedDealRules.Pick(l, p, 0f)),
                    "pick: roll 1 takes the last admitted card", "pick: vanilla's weights, 0.75 of 10+4 is the second");
            return r;
        }

        private static void Control(Result r, string mutant, List<KeyValuePair<string, bool>> cases, params string[] mustFail)
        {
            var failed = new HashSet<string>();
            foreach (var kv in cases)
                if (!kv.Value) failed.Add(kv.Key);
            bool ok = true;
            foreach (var name in mustFail)
                if (!failed.Contains(name)) ok = false;
            Check(r, "mutant (" + mutant + ") is caught by its named cases", ok,
                  failed.Count == 0 ? "no case failed" : string.Join("; ", new List<string>(failed).ToArray()));
        }
    }
}
