using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// The harness's half of TitleLadderRules (item 12 follow-up). It lives
    /// HERE, under tools/, and not in plugin/TitleLadderRules.cs, so the
    /// shipped DLL carries no ladder fixture: the plugin build compiles only
    /// the rules half of this partial class, the harness compiles both.
    ///
    /// Every state the Buy / Upgrade button can be in has a case AND a
    /// control that moves exactly the input deciding it, so each branch is
    /// shown to be reachable and to be the thing that decides (#391). The
    /// fixtures are synthetic skus ("a_1" ... "l7_6"), never the catalogue's.
    /// </summary>
    internal static partial class TitleLadderRules
    {
        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        // A six-tier line in the catalogue's shape: the entry rung is sold for
        // 1000, the five above it are granted by play at 10/30/75/150/300.
        private static readonly int[] THRESHOLDS = { 0, 10, 30, 75, 150, 300 };

        private static List<Rung> Line6(string p, int ownedUpTo, int activeTier = 0)
        {
            var l = new List<Rung>();
            for (int t = 1; t <= 6; t++)
                l.Add(new Rung
                {
                    Tier = t, Sku = p + "_" + t, Price = t == 1 ? 1000 : 0,
                    Threshold = THRESHOLDS[t - 1], Owned = t <= ownedUpTo, Active = t == activeTier,
                });
            return l;
        }

        // The rat shape: five tiers, tier 4 carried by two rungs.
        private static List<Rung> RatLike(bool king, bool queen, bool queenWorn)
        {
            return new List<Rung>
            {
                new Rung { Tier = 1, Sku = "r_1", Price = 1000, Threshold = 0, Owned = true },
                new Rung { Tier = 2, Sku = "r_2", Price = 0, Threshold = 10, Owned = true },
                new Rung { Tier = 3, Sku = "r_3", Price = 0, Threshold = 30, Owned = true },
                new Rung { Tier = 4, Sku = "r_4_king", Price = 0, Threshold = 75, Owned = king },
                new Rung { Tier = 4, Sku = "r_4_queen", Price = 0, Threshold = 75, Owned = queen, Active = queenWorn },
                new Rung { Tier = 5, Sku = "r_5", Price = 0, Threshold = 150, Owned = false },
            };
        }

        private static Dictionary<string, int> Listing(params object[] skuPrice)
        {
            var d = new Dictionary<string, int>(StringComparer.Ordinal);
            for (int i = 0; i + 1 < skuPrice.Length; i += 2) d[(string)skuPrice[i]] = (int)skuPrice[i + 1];
            return d;
        }

        private static string Show(Decision d)
        {
            return "label=" + d.Label + " enabled=" + d.Enabled + " reason=" + d.Reason
                   + " held=" + d.Held + " next=" + d.NextTier + " target=" + (d.TargetSku ?? "-")
                   + " price=" + d.Price + " threshold=" + d.Threshold + " togo=" + d.SeriesToGo;
        }

        private static void Plan8(int pool, bool repeat, out SectionPlan plan)
        {
            var ids = new List<string>();
            var skus = new List<IList<string>>();
            for (int i = 0; i < 8; i++)
            {
                ids.Add("l" + i);
                var s = new List<string>();
                for (int t = 1; t <= 6; t++) s.Add("l" + i + "_" + t);
                skus.Add(s);
            }
            if (repeat) { ids.Add("l2"); skus.Add(new List<string> { "l2_1" }); }
            plan = PlanSection(ids, skus, pool);
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // ── S: the section plan (L2 -- every ladder exactly once) ──────
            {
                SectionPlan p;
                Plan8(16, false, out p);
                bool ordered = p.Lines.Count == 8;
                for (int i = 0; ordered && i < 8; i++) ordered = p.Lines[i] == i;
                Check(r, "eight lines render eight entries, each once and in answer order",
                      ordered, "lines=" + string.Join(",", p.Lines));
                Check(r, "every rung of every rendered line is folded",
                      p.Folded.Count == 48 && p.Folded.Contains("l3_4"), "folded=" + p.Folded.Count);
                Check(r, "a title outside every ladder is not folded",
                      !p.Folded.Contains("title_plain"), "folded=" + p.Folded.Count);

                SectionPlan rep;
                Plan8(16, true, out rep);
                Check(r, "a repeated line id renders once",
                      rep.Lines.Count == 8 && rep.Repeats == 1,
                      "lines=" + rep.Lines.Count + " repeats=" + rep.Repeats);

                var none = PlanSection(null, null, 16);
                Check(r, "with no answer in hand nothing renders and nothing is folded",
                      none.Lines.Count == 0 && none.Folded.Count == 0,
                      "lines=" + none.Lines.Count + " folded=" + none.Folded.Count);

                SectionPlan small;
                Plan8(5, false, out small);
                Check(r, "a line past the pool renders nowhere and keeps its listing rows",
                      small.Lines.Count == 5 && small.Unrendered == 3 && !small.Folded.Contains("l6_1"),
                      "lines=" + small.Lines.Count + " unrendered=" + small.Unrendered
                      + " folded_l6=" + small.Folded.Contains("l6_1"));
                SectionPlan exact;
                Plan8(8, false, out exact);
                Check(r, "a pool the size of the answer renders and folds every line (control)",
                      exact.Unrendered == 0 && exact.Folded.Contains("l6_1") && exact.Folded.Contains("l7_6"),
                      "unrendered=" + exact.Unrendered + " folded=" + exact.Folded.Count);
            }

            // ── B: Buy (no tier held) ──────────────────────────────────────
            {
                var line = Line6("a", 0);
                var listed = Listing("a_1", 1000);
                var buy = Decide(line, 0, true, listed, 1000);
                Check(r, "nothing held, entry listed and affordable: Buy, enabled",
                      buy.Label == Label.Buy && buy.Enabled && buy.TargetSku == "a_1" && buy.Price == 1000,
                      Show(buy));
                var shy = Decide(line, 0, true, listed, 999);
                Check(r, "one gold short: Buy, disabled, not enough gold (control)",
                      shy.Label == Label.Buy && !shy.Enabled && shy.Reason == Reason.NotEnoughGold,
                      Show(shy));
                Check(r, "a disabled button carries no target sku",
                      shy.TargetSku == null, Show(shy));
                var unlisted = Decide(line, 0, true, Listing("other", 5), 5000);
                Check(r, "the entry is not in the listing: Buy, disabled, not on sale",
                      !unlisted.Enabled && unlisted.Reason == Reason.NotOnSale && unlisted.Price == 1000,
                      Show(unlisted));
                var noListing = Decide(line, 0, true, null, 5000);
                Check(r, "the listing has not answered: Buy, disabled, shop loading",
                      !noListing.Enabled && noListing.Reason == Reason.ShopLoading, Show(noListing));
                var noStats = Decide(line, 0, true, listed, null);
                Check(r, "the stats have not answered: Buy, disabled, shop loading",
                      !noStats.Enabled && noStats.Reason == Reason.ShopLoading, Show(noStats));
                var noAccount = Decide(line, 0, false, listed, 5000);
                Check(r, "no account: Buy, disabled, no account",
                      !noAccount.Enabled && noAccount.Reason == Reason.NoAccount, Show(noAccount));
                var dearer = Decide(line, 0, true, Listing("a_1", 1200), 1100);
                Check(r, "the listing's price decides the funds check, not the answer's",
                      !dearer.Enabled && dearer.Reason == Reason.NotEnoughGold && dearer.Price == 1200,
                      Show(dearer));
                var same = Decide(line, 0, true, Listing("a_1", 1000), 1100);
                Check(r, "the same balance buys at the answer's price when the listing agrees (control)",
                      same.Enabled && same.Price == 1000, Show(same));
            }

            // ── U: Upgrade (a tier held, the next one earned by play) ──────
            {
                var line = Line6("b", 1);
                var all = Listing("b_1", 1000, "b_2", 1000, "b_3", 1000);
                var up0 = Decide(line, 0, true, all, 1000000);
                Check(r, "entry held, tier 2 granted by play: Upgrade, disabled, earned by play",
                      up0.Label == Label.Upgrade && !up0.Enabled && up0.Reason == Reason.EarnedByPlay
                      && up0.NextTier == 2 && up0.Threshold == 10 && up0.SeriesToGo == 10,
                      Show(up0));
                Check(r, "funds and a listing never enable a tier the answer does not sell",
                      !up0.Enabled && up0.TargetSku == null, Show(up0));
                var up7 = Decide(line, 7, true, all, 0);
                Check(r, "seven series in: three to go", up7.SeriesToGo == 3, Show(up7));
                var up12 = Decide(line, 12, true, all, 0);
                Check(r, "past the threshold before the grant lands: zero to go, never negative",
                      up12.SeriesToGo == 0 && up12.Reason == Reason.EarnedByPlay, Show(up12));

                var priced = Line6("c", 1);
                var p2 = priced[1]; p2.Price = 500; priced[1] = p2;
                var paid = Decide(priced, 0, true, Listing("c_2", 500), 600);
                Check(r, "a priced and listed next tier enables Upgrade (control)",
                      paid.Label == Label.Upgrade && paid.Enabled && paid.TargetSku == "c_2" && paid.Price == 500,
                      Show(paid));
            }

            // ── M: Maxed ───────────────────────────────────────────────────
            {
                var top = Line6("d", 6, 6);
                var maxed = Decide(top, 320, true, Listing("d_1", 1000), 1000000);
                Check(r, "top tier held: Maxed, disabled",
                      maxed.Label == Label.Maxed && !maxed.Enabled && maxed.NextTier == 0, Show(maxed));
                var maxedBlind = Decide(top, 320, false, null, null);
                Check(r, "Maxed does not depend on the account, the listing or the stats",
                      maxedBlind.Label == Label.Maxed && !maxedBlind.Enabled, Show(maxedBlind));
                var below = Line6("d", 5, 5);
                var notTop = Decide(below, 200, true, null, null);
                Check(r, "the same line without its top rung is Upgrade toward tier 6 (control)",
                      notTop.Label == Label.Upgrade && notTop.NextTier == 6 && notTop.SeriesToGo == 100,
                      Show(notTop));
            }

            // ── H: which tier is held ──────────────────────────────────────
            {
                var two = Line6("e", 2);
                var held2 = Decide(two, 45, true, null, null);
                Check(r, "held is the highest OWNED tier, not the tier the games imply",
                      held2.Held == 2 && held2.NextTier == 3, Show(held2));
                var nothing = Decide(Line6("e", 0), 45, true, null, null);
                Check(r, "an account that owns nothing holds no tier and reads Buy",
                      nothing.Held == 0 && nothing.Label == Label.Buy && nothing.NextTier == 1, Show(nothing));
                var gifted = Line6("f", 0);
                var g3 = gifted[2]; g3.Owned = true; gifted[2] = g3;
                var fromThree = Decide(gifted, 0, true, null, null);
                Check(r, "owning only a tier-3 rung reads Upgrade toward tier 4",
                      fromThree.Held == 3 && fromThree.Label == Label.Upgrade && fromThree.NextTier == 4,
                      Show(fromThree));
                var queenOnly = Decide(RatLike(false, true, false), 80, true, null, null);
                Check(r, "either of two tier-4 rungs holds tier 4",
                      queenOnly.Held == 4 && queenOnly.NextTier == 5 && queenOnly.Threshold == 150,
                      Show(queenOnly));
                var both = RatLike(true, true, true);
                int idx = HeldRungIndex(both, 4);
                Check(r, "the worn rung names the held tier", idx == 4, "index=" + idx);
                int kingIdx = HeldRungIndex(RatLike(true, true, false), 4);
                Check(r, "with none worn, the first owned rung of the tier names it (control)",
                      kingIdx == 3, "index=" + kingIdx);
                Check(r, "nothing held names no rung", HeldRungIndex(Line6("g", 0), 0) == -1,
                      "index=" + HeldRungIndex(Line6("g", 0), 0));
            }

            // ── T: the popup's tier rows ───────────────────────────────────
            {
                var line = Line6("h", 2);
                var d = Decide(line, 12, true, null, null);
                var states = new List<TierState>();
                foreach (var rung in line) states.Add(StateOf(rung, d.Held, d.NextTier));
                var want = new[] { TierState.Owned, TierState.Current, TierState.Next,
                                   TierState.Locked, TierState.Locked, TierState.Locked };
                bool same = states.Count == want.Length;
                for (int i = 0; same && i < want.Length; i++) same = states[i] == want[i];
                Check(r, "tier rows read Owned, Current, Next, then Locked",
                      same, string.Join(",", states));

                var fresh = Line6("h", 0);
                var fd = Decide(fresh, 0, true, null, null);
                bool entryNext = StateOf(fresh[0], fd.Held, fd.NextTier) == TierState.Next;
                bool restLocked = true;
                for (int i = 1; i < fresh.Count; i++)
                    restLocked &= StateOf(fresh[i], fd.Held, fd.NextTier) == TierState.Locked;
                Check(r, "not started: the entry rung is Next and every other rung Locked",
                      entryNext && restLocked, "entryNext=" + entryNext + " restLocked=" + restLocked);

                var top = Line6("h", 6);
                var td = Decide(top, 300, true, null, null);
                int nexts = 0, currents = 0;
                foreach (var rung in top)
                {
                    var st = StateOf(rung, td.Held, td.NextTier);
                    if (st == TierState.Next) nexts++;
                    if (st == TierState.Current) currents++;
                }
                Check(r, "a line held at the top has one Current row and no Next row (control)",
                      nexts == 0 && currents == 1, "next=" + nexts + " current=" + currents);
            }

            // ── P: the progress bar ────────────────────────────────────────
            {
                var four = Line6("p", 4);
                var d4 = Decide(four, 80, true, null, null);
                float f4 = Progress(four, 80, d4);
                Check(r, "80 series held at tier 4 fills 5 of 75",
                      Math.Abs(f4 - 5f / 75f) < 0.0001f, f4.ToString("0.0000", CultureInfo.InvariantCulture));
                var zero = Line6("p", 0);
                float f0 = Progress(zero, 0, Decide(zero, 0, true, null, null));
                Check(r, "not started draws an empty bar", f0 == 0f,
                      f0.ToString("0.0000", CultureInfo.InvariantCulture));
                var top = Line6("p", 6);
                float f6 = Progress(top, 300, Decide(top, 300, true, null, null));
                Check(r, "the top draws a full bar", f6 == 1f, f6.ToString("0.0000", CultureInfo.InvariantCulture));
            }

            // ── N: an answer with no rungs for a line ──────────────────────
            {
                var empty = Decide(new List<Rung>(), 0, true, Listing("x", 1), 10);
                Check(r, "a line with no rungs: Buy, disabled, no rungs",
                      empty.Label == Label.Buy && !empty.Enabled && empty.Reason == Reason.NoRungs, Show(empty));
            }

            return r;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
