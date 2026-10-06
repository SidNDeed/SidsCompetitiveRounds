using System;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>
    /// Item 18, shard on the fly in the card pull tab: the decisions the
    /// strip's per-card Discard button makes, kept free of Unity, Photon,
    /// BepInEx and I18n so they run under a plain compiler. PlayerCardsUI
    /// hands them plain values and acts on what comes back; the same SelfTest
    /// runs under tools/client-rules-harness, so the rules are EXECUTED rather
    /// than asserted about as source text (#391).
    ///
    /// The send itself is the batch shard's (board row 25,
    /// ApiClient.PcDiscardBatch) with ONE print: one server transaction, the
    /// credit one delta (#326), keyed by a nonce kept for that print until an
    /// answer arrives, so the same card asked again after a lost answer is a
    /// replay the server answers from its stored row and never pays twice.
    /// </summary>
    internal static class PcQuickShardRules
    {
        /// <summary>The armed-request identity of one strip card, in the
        /// namespace the batch shard's arming already uses ("pack|...",
        /// "sel|..."), so arming one control disarms the others.</summary>
        internal static string ArmSet(string printId)
        {
            return "one|" + (printId ?? "");
        }

        /// <summary>Whether a tile shows its Discard button. The binder keeps
        /// its rule exactly (hidden only while the binder's Select mode picks
        /// cards; the binder never holds a discarded print). The pull strip
        /// ignores the binder's Select mode, and hides the button on a print
        /// that is discarded or that the server has named as no longer the
        /// player's (a refused shard), since a click there can only be
        /// refused.</summary>
        internal static bool DiscardOffered(bool quickSurface, bool discarded, bool gone, bool selecting)
        {
            if (quickSurface) return !discarded && !gone;
            return !discarded && !selecting;
        }

        /// <summary>Whether a refused or unanswered strip shard reads the
        /// collection and the balance back (once, after the answer; never
        /// concurrently with the shard itself). The screen is never changed
        /// before the server answers, so a failure leaves the card and the
        /// balance as they were; this decides whether they are then re-read.
        ///   * rate_limited: refused by the rate gate before the route ran, so
        ///     nothing happened and the screen is already right, and a read
        ///     now would be charged to the same bucket that just refused us
        ///     (the shape reports 364 and 368 describe). No read.
        ///   * session_required, not_ready: never sent, or refused before the
        ///     actor was read. No read.
        ///   * transport, given_up: no answer, so whether the shard applied is
        ///     unknown. Read back.
        ///   * every other code (not_owned, key_reused, the route missing, a
        ///     5xx): the local copy may be what was wrong. Read back.
        /// A null code is a success, which the answer itself describes: no
        /// read.</summary>
        internal static bool ReadBackAfter(string code)
        {
            if (code == null) return false;
            switch (code)
            {
                case "rate_limited":
                case "session_required":
                case "not_ready":
                    return false;
                default:
                    return true;
            }
        }

        /// <summary>Whether the strip card's nonce is kept after an answer, so
        /// the next send for that card is the same key (a replay). Kept on
        /// every failure but key_reused: a lost answer, a rate limit, a 5xx or
        /// a not_owned all leave the server either with this key's row (a
        /// replay answers it) or without it (the key is unused). key_reused
        /// means the key's row names other prints, so it can never answer
        /// this card. A success ends the key's life.</summary>
        internal static bool KeepKeyAfter(string code)
        {
            if (code == null) return false;
            return code != "key_reused";
        }

        /// <summary>Requests one strip shard sends, including what its answer
        /// triggers: the shard itself, plus the two read-backs (collection and
        /// balance) when ReadBackAfter says so. Never a retry: a second send
        /// takes two more clicks.</summary>
        internal static int RequestsFor(string code)
        {
            return 1 + (ReadBackAfter(code) ? 2 : 0);
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) --------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The strip's button as a pass that "unified" the two
        /// surfaces would write it, reading the binder's Select mode and not
        /// the refused set. The NEGATIVE CONTROL for the visibility cases:
        /// it must disagree with DiscardOffered on the cases that name a
        /// difference (#391). Never called by anything that paints.</summary>
        private static bool OfferedAsTheBinder(bool discarded, bool gone, bool selecting)
        {
            return !discarded && !selecting;
        }

        /// <summary>A read-back on every failure, the drop client's shape
        /// (each discard answer followed by two refetches). NEGATIVE CONTROL
        /// for the request-count cases. Never called by anything that
        /// sends.</summary>
        private static int RequestsWithAlwaysReadBack(string code)
        {
            return code == null ? 1 : 3;
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // visibility: the strip
            Check(r, "strip: a live print offers Discard", DiscardOffered(true, false, false, false), "");
            Check(r, "strip: a discarded print does not", !DiscardOffered(true, true, false, false), "");
            Check(r, "strip: a print the server named gone does not", !DiscardOffered(true, false, true, false), "");
            Check(r, "strip: the binder's Select mode does not hide it", DiscardOffered(true, false, false, true), "");
            Check(r, "control: the binder's rule WOULD hide it in Select mode",
                  OfferedAsTheBinder(false, false, true) != DiscardOffered(true, false, false, true), "");
            Check(r, "control: the binder's rule WOULD offer a gone print",
                  OfferedAsTheBinder(false, true, false) != DiscardOffered(true, false, true, false), "");
            // visibility: the binder, unchanged
            Check(r, "binder: a live print offers Discard", DiscardOffered(false, false, false, false), "");
            Check(r, "binder: Select mode hides it", !DiscardOffered(false, false, false, true), "");
            Check(r, "binder: a gone print keeps it (its own refusal refreshes)", DiscardOffered(false, false, true, false), "");
            Check(r, "binder: the refused set never changes its answer, on every input", BinderUnchanged(), "");

            // the arm identity
            Check(r, "arm: one card's set names the card", ArmSet("abc-1") == "one|abc-1", ArmSet("abc-1"));
            Check(r, "arm: two cards never share a set", ArmSet("abc-1") != ArmSet("abc-2"), "");
            Check(r, "arm: never a pack or a selection set",
                  !ArmSet("x").StartsWith("pack|", StringComparison.Ordinal) && !ArmSet("x").StartsWith("sel|", StringComparison.Ordinal), ArmSet("x"));

            // read-back and request count
            Check(r, "success: one request, no read", RequestsFor(null) == 1 && !ReadBackAfter(null), RequestsFor(null).ToString());
            Check(r, "rate_limited: one request, no read", RequestsFor("rate_limited") == 1, RequestsFor("rate_limited").ToString());
            Check(r, "session_required: no read", !ReadBackAfter("session_required"), "");
            Check(r, "transport: read back (unknown outcome)", ReadBackAfter("transport") && RequestsFor("transport") == 3, RequestsFor("transport").ToString());
            Check(r, "given_up: read back (unknown outcome)", ReadBackAfter("given_up"), "");
            Check(r, "not_owned: read back", ReadBackAfter("not_owned"), "");
            Check(r, "key_reused: read back", ReadBackAfter("key_reused"), "");
            Check(r, "an unknown code fails toward reading back", ReadBackAfter("http"), "");
            Check(r, "control: the always-read shape costs three on a rate limit",
                  RequestsWithAlwaysReadBack("rate_limited") == 3 && RequestsWithAlwaysReadBack("rate_limited") != RequestsFor("rate_limited"), "");
            Check(r, "control: and agrees on success", RequestsWithAlwaysReadBack(null) == RequestsFor(null), "");

            // the key
            Check(r, "key: a success ends it", !KeepKeyAfter(null), "");
            Check(r, "key: kept after a lost answer (the retry is a replay)", KeepKeyAfter("transport") && KeepKeyAfter("given_up"), "");
            Check(r, "key: kept after a rate limit", KeepKeyAfter("rate_limited"), "");
            Check(r, "key: dropped after key_reused", !KeepKeyAfter("key_reused"), "");
            return r;
        }

        private static bool BinderUnchanged()
        {
            foreach (bool d in new[] { false, true })
                foreach (bool g in new[] { false, true })
                    foreach (bool s in new[] { false, true })
                        if (DiscardOffered(false, d, g, s) != DiscardOffered(false, d, false, s)) return false;
            return true;
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
