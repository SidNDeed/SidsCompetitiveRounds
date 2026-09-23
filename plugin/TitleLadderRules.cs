using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>
    /// The animal title ladders as entries of the Shop's Titles section
    /// (v1.41.0 item 12 follow-up): which ladders the section renders, which
    /// listing rows each rendered ladder replaces, which tier a player holds,
    /// and what the Buy / Upgrade button on an entry and in its tier popup
    /// says and does. Kept free of Unity, Photon, BepInEx and I18n so it runs
    /// under a plain compiler: TitleLaddersUI resolves every value from the
    /// ladder answer, the shop listing and the player's stats, hands them in,
    /// and paints what comes back.
    ///
    /// EXECUTED, not asserted about (#391): tools/client-rules-harness
    /// compiles this file beside TitleLadderRulesSelfTest.cs, the harness's
    /// own half of this partial class. The cases live THERE rather than in
    /// this file so the shipped DLL carries no ladder fixture -- the rule the
    /// removed parser self-check left behind (see TitleLaddersUI's closing
    /// note).
    ///
    /// No catalogue string lives here: every label and reason is translated
    /// at its I18n.Tr call site in TitleLaddersUI, where the extractor reads
    /// it, so this file is deliberately absent from tools/i18n_extract.py's
    /// FILES list (#464). A string moved in here is a string nobody harvests.
    /// </summary>
    internal static partial class TitleLadderRules
    {
        /// <summary>One rung, reduced to what the rules read. `Price` is the
        /// ladder answer's price, where 0 means "granted by play, never sold"
        /// (the purchase endpoint refuses every rung above the first by its
        /// pool); `Threshold` is the series count on the line that grants it.
        /// </summary>
        internal struct Rung
        {
            public int Tier;
            public string Sku;
            public int Price;
            public int Threshold;
            public bool Owned;
            public bool Active;
        }

        /// <summary>What the entry's button reads. Buy while no tier is held,
        /// Upgrade once one is, Maxed at the top.</summary>
        internal enum Label { Buy, Upgrade, Maxed }

        /// <summary>Why the button is disabled. One reason per refusal, and
        /// "the listing has not answered" is never folded into "not on sale":
        /// the first clears itself, the second is a statement about the item
        /// (#430 -- one refusal must not mean two things).</summary>
        internal enum Reason
        {
            /// <summary>Enabled -- or Maxed, where the label is the whole message.</summary>
            None,
            /// <summary>The answer carried no rung for this line.</summary>
            NoRungs,
            /// <summary>No Steam account is resolved, so nothing can be bought.</summary>
            NoAccount,
            /// <summary>The shop listing or the player's stats have not answered yet.</summary>
            ShopLoading,
            /// <summary>The shop listing does not offer the next tier's sku.</summary>
            NotOnSale,
            /// <summary>The balance is below the price the listing charges.</summary>
            NotEnoughGold,
            /// <summary>The next tier is granted by ranked series, not sold.</summary>
            EarnedByPlay,
        }

        /// <summary>The button's whole state for one line.</summary>
        internal struct Decision
        {
            public Label Label;
            public bool Enabled;
            public Reason Reason;
            /// <summary>Highest tier the player owns a rung of; 0 = none.</summary>
            public int Held;
            /// <summary>The tier the button is about; 0 at the top.</summary>
            public int NextTier;
            /// <summary>The sku an ENABLED button buys; null whenever disabled,
            /// so no caller can buy off a refusal by accident.</summary>
            public string TargetSku;
            /// <summary>The price shown and checked: the LISTING's price when the
            /// listing offers the sku (what the purchase endpoint charges), the
            /// answer's price otherwise; 0 when the next tier is not sold.</summary>
            public int Price;
            /// <summary>The next tier's series threshold (0 at the top).</summary>
            public int Threshold;
            /// <summary>Series still to play to reach it, never negative.</summary>
            public int SeriesToGo;
        }

        /// <summary>A rung's row in the tier popup.</summary>
        internal enum TierState { Current, Owned, Next, Locked }

        /// <summary>The highest tier the player owns a rung of, or 0. Held is
        /// read from OWNERSHIP, not from the answer's progress tier: the
        /// answer reports tier 1 for an account that owns nothing, so its
        /// tier cannot tell "holds the entry rung" from "holds no rung".</summary>
        internal static int HeldTier(IList<Rung> rungs)
        {
            int held = 0;
            if (rungs == null) return 0;
            for (int i = 0; i < rungs.Count; i++)
                if (rungs[i].Owned && rungs[i].Tier > held) held = rungs[i].Tier;
            return held;
        }

        /// <summary>The lowest tier above `held` that the line defines, or 0
        /// when there is none (the top is held).</summary>
        internal static int NextTier(IList<Rung> rungs, int held)
        {
            int next = 0;
            if (rungs == null) return 0;
            for (int i = 0; i < rungs.Count; i++)
            {
                int t = rungs[i].Tier;
                if (t > held && (next == 0 || t < next)) next = t;
            }
            return next;
        }

        /// <summary>The button's state for one line.
        ///
        /// `listing` maps every sku the shop listing offers to the price it
        /// charges, or is null while the listing has not answered; `balance`
        /// is null while the player's stats have not answered. Both are what
        /// the server said, never a guess: the listing is how the server
        /// says an item is for sale, and the purchase endpoint refuses
        /// exactly what it leaves out.</summary>
        internal static Decision Decide(IList<Rung> rungs, int games, bool account,
                                        IDictionary<string, int> listing, int? balance)
        {
            var d = new Decision();
            if (rungs == null || rungs.Count == 0)
            {
                d.Label = Label.Buy;
                d.Reason = Reason.NoRungs;
                return d;
            }
            d.Held = HeldTier(rungs);
            d.NextTier = NextTier(rungs, d.Held);
            if (d.NextTier == 0)
            {
                // Rungs exist, so NextTier(…, 0) is never 0: reaching here
                // means the top tier is held.
                d.Label = Label.Maxed;
                d.Reason = Reason.None;
                return d;
            }
            d.Label = d.Held == 0 ? Label.Buy : Label.Upgrade;

            // The next tier's threshold, and the first rung at it that is for
            // sale at all. Two rungs can share a tier (rat's King and Queen),
            // and reaching the tier grants both, so either one is the tier.
            bool haveThreshold = false;
            int target = -1;
            for (int i = 0; i < rungs.Count; i++)
            {
                var r = rungs[i];
                if (r.Tier != d.NextTier) continue;
                if (!haveThreshold) { d.Threshold = r.Threshold; haveThreshold = true; }
                if (target < 0 && !r.Owned && r.Price > 0 && !string.IsNullOrEmpty(r.Sku)) target = i;
            }
            d.SeriesToGo = Math.Max(0, d.Threshold - games);
            if (target < 0)
            {
                d.Reason = Reason.EarnedByPlay;
                return d;
            }

            var t = rungs[target];
            d.Price = t.Price;
            if (!account) { d.Reason = Reason.NoAccount; return d; }
            if (listing == null) { d.Reason = Reason.ShopLoading; return d; }
            int listed;
            if (!listing.TryGetValue(t.Sku, out listed)) { d.Reason = Reason.NotOnSale; return d; }
            // What the purchase endpoint charges is the listing's price
            // (shop_items.price); the answer's price is a catalogue constant
            // that can drift from it. Show and check the one that is charged.
            d.Price = listed;
            if (balance == null) { d.Reason = Reason.ShopLoading; return d; }
            if (balance.Value < listed) { d.Reason = Reason.NotEnoughGold; return d; }
            d.Enabled = true;
            d.TargetSku = t.Sku;
            d.Reason = Reason.None;
            return d;
        }

        /// <summary>A rung's row state in the popup. Current is the held tier
        /// (the row the popup highlights); a rung the player does not own is
        /// Next when it sits on the tier the button is about, Locked
        /// otherwise.</summary>
        internal static TierState StateOf(Rung r, int held, int next)
        {
            if (r.Owned) return r.Tier == held ? TierState.Current : TierState.Owned;
            return r.Tier == next ? TierState.Next : TierState.Locked;
        }

        /// <summary>Which rung names the held tier: the worn one when a rung of
        /// that tier is worn, else the first owned one at that tier; -1 when
        /// nothing is held.</summary>
        internal static int HeldRungIndex(IList<Rung> rungs, int held)
        {
            if (rungs == null || held <= 0) return -1;
            int first = -1;
            for (int i = 0; i < rungs.Count; i++)
            {
                var r = rungs[i];
                if (!r.Owned || r.Tier != held) continue;
                if (r.Active) return i;
                if (first < 0) first = i;
            }
            return first;
        }

        /// <summary>The progress bar's fill, 0..1. It spans the HELD tier's
        /// threshold to the next tier's, not 0 to the next: 80 series held at
        /// tier 4 (threshold 75) toward tier 5 (150) is 5 of 75, under 7 %,
        /// where a 0-to-next bar would show 80 of 150. Nothing held draws an
        /// empty bar -- a player who has not started is in no countdown --
        /// and the top draws a full one.</summary>
        internal static float Progress(IList<Rung> rungs, int games, Decision d)
        {
            if (d.Held <= 0) return 0f;
            if (d.NextTier == 0) return 1f;
            int floor = 0;
            if (rungs != null)
                for (int i = 0; i < rungs.Count; i++)
                    if (rungs[i].Tier == d.Held && rungs[i].Threshold > floor) floor = rungs[i].Threshold;
            int span = d.Threshold - floor;
            if (span <= 0) return 0f;
            float f = (float)(games - floor) / span;
            return f < 0f ? 0f : (f > 1f ? 1f : f);
        }

        /// <summary>What the Titles section renders from one answer.</summary>
        internal sealed class SectionPlan
        {
            /// <summary>Answer indices to render, in answer order, each line id once.</summary>
            internal readonly List<int> Lines = new List<int>();
            /// <summary>Listing skus the rendered entries stand in for.</summary>
            internal readonly HashSet<string> Folded = new HashSet<string>(StringComparer.Ordinal);
            /// <summary>Distinct lines past the entry pool. Their rungs are NOT
            /// folded, so their ordinary listing rows stay on screen.</summary>
            internal int Unrendered;
            /// <summary>Repeated line ids skipped (the first occurrence renders).</summary>
            internal int Repeats;
        }

        /// <summary>The section plan: every distinct ladder the answer carries,
        /// once, up to the entry pool; and the listing rows those entries
        /// replace. A rung's listing row is folded into its ladder's entry ONLY
        /// when that entry renders, so a ladder the pool cannot show keeps its
        /// ordinary rows and nothing becomes unreachable. With no answer in
        /// hand the plan is empty and nothing is folded.</summary>
        internal static SectionPlan PlanSection(IList<string> lineIds, IList<IList<string>> lineSkus, int pool)
        {
            var plan = new SectionPlan();
            if (lineIds == null) return plan;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < lineIds.Count; i++)
            {
                string id = lineIds[i];
                if (string.IsNullOrEmpty(id)) continue;
                if (!seen.Add(id)) { plan.Repeats++; continue; }
                if (plan.Lines.Count >= pool) { plan.Unrendered++; continue; }
                plan.Lines.Add(i);
                var skus = lineSkus != null && i < lineSkus.Count ? lineSkus[i] : null;
                if (skus == null) continue;
                for (int k = 0; k < skus.Count; k++)
                    if (!string.IsNullOrEmpty(skus[k])) plan.Folded.Add(skus[k]);
            }
            return plan;
        }
    }
}
