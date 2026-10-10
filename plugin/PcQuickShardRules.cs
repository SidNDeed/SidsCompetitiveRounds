using System;
using System.Collections.Generic;
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

        /// <summary>The pull tab's Shard dupes (fix pass 1, finding 3; design
        /// section 2.3's pull-wide control, sent through the batch shard's
        /// route): which of the shown pack's prints are DUPLICATES, so that
        /// one live copy of every exact face survives.
        ///   pageFaceKeys   the pack's prints in display order, each print's
        ///                  exact face (PlayerCardsUI.FaceKey: card, rarity,
        ///                  foil, signed), null for a print that is not live
        ///                  (discarded, or named gone by the server);
        ///   pagePrintIds   parallel to pageFaceKeys;
        ///   liveCountByFaceKey  the player's live copies of each face, over
        ///                  the whole collection;
        ///   livePrintIds   the collection's live print ids.
        /// liveCountByFaceKey and livePrintIds come from ONE collection read
        /// (PlayerCardsUI.PackDupeIds builds both in one walk).
        /// Fix pass 2, finding 2: that read is the CURRENT ownership of the
        /// pack's prints. The pack history describes a print as the pull made
        /// it, so a print traded away since still reads live there. A page
        /// print that is not in livePrintIds is not the player's now (traded
        /// away, or a read from before the pack): it is neither taken nor
        /// counted, and it never makes the action not ready. A print traded
        /// away and back is in the read again, so it counts. ready is false
        /// (and the list empty) only when an input is missing. Walking the
        /// owned page prints in display order, a print is taken only while its
        /// face has MORE than one live copy left, so the first owned copy in
        /// order of a face new to the player is kept, and a face the binder
        /// holds outside this pack has every owned pack copy taken while that
        /// copy survives. Never the last copy: within the read, what is left
        /// of every face is at least one.</summary>
        internal static List<string> DuplicateShardIds(IList<string> pageFaceKeys, IList<string> pagePrintIds,
            IDictionary<string, int> liveCountByFaceKey, ICollection<string> livePrintIds, out bool ready)
        {
            var queue = new List<string>();
            ready = false;
            if (pageFaceKeys == null || pagePrintIds == null || pageFaceKeys.Count != pagePrintIds.Count
                || liveCountByFaceKey == null || livePrintIds == null) return queue;
            ready = true;
            // the page as the player owns it now: a face for an owned live print, null otherwise
            var owned = new string[pageFaceKeys.Count];
            for (int i = 0; i < pageFaceKeys.Count; i++)
                owned[i] = pageFaceKeys[i] != null && pagePrintIds[i] != null && livePrintIds.Contains(pagePrintIds[i]) ? pageFaceKeys[i] : null;
            var onPage = new Dictionary<string, int>(StringComparer.Ordinal);
            var seen = new HashSet<string>(StringComparer.Ordinal);
            for (int i = 0; i < owned.Length; i++)
            {
                string k = owned[i];
                if (k == null || !seen.Add(pagePrintIds[i])) continue;
                int m; onPage.TryGetValue(k, out m); onPage[k] = m + 1;
            }
            // A face the binder also holds OUTSIDE this pack keeps that copy,
            // so every page copy goes; a face only this pack holds keeps its
            // FIRST page copy in display order. A count below the page's own
            // copies disagrees with the page: nothing of that face is taken.
            var kept = new HashSet<string>(StringComparer.Ordinal);
            seen.Clear();
            for (int i = 0; i < owned.Length; i++)
            {
                string k = owned[i];
                if (k == null || !seen.Add(pagePrintIds[i])) continue;
                int total; liveCountByFaceKey.TryGetValue(k, out total);
                int outside = total - onPage[k];
                if (outside < 0) continue;
                if (outside == 0 && kept.Add(k)) continue;
                queue.Add(pagePrintIds[i]);
            }
            return queue;
        }

        /// <summary>Fix pass 2, finding 2: whether the Shard dupes button is
        /// up -- a ready answer naming at least one duplicate and no more than
        /// one batch may carry. A pack whose only duplicate was traded away
        /// has none, so the button is hidden; a pack with other owned
        /// duplicates shows it.</summary>
        internal static bool DupesOffered(bool ready, int count, int cap)
        {
            return ready && count > 0 && count <= cap;
        }

        /// <summary>Fix pass 3, finding 2: PlayerCardsUI.PackDupeIds' two
        /// walks, free of Unity, with the not_owned tombstones applied to
        /// both, so the client rules harness drives the whole path the
        /// button reads and not the duplicate rule alone.
        ///   pageFaceKeys / pagePrintIds  the shown pack's prints in display
        ///                  order; a face is null for a print the strip itself
        ///                  knows is not live (discarded, no usable id);
        ///   colFaceKeys / colPrintIds    the collection read's prints,
        ///                  parallel; both null for a print the read does not
        ///                  hold live (discarded);
        ///   gone           the tombstones (PcShardTombstones): prints a
        ///                  refused shard named not_owned that no collection
        ///                  read dispatched after that refusal has held since.
        /// A tombstoned print is neither taken nor counted on either walk;
        /// what is left goes through DuplicateShardIds, sorted. ready is false
        /// (and the list empty) when an input is missing.</summary>
        internal static List<string> PackDupes(IList<string> pageFaceKeys, IList<string> pagePrintIds,
            IList<string> colFaceKeys, IList<string> colPrintIds, PcShardTombstones gone, out bool ready)
        {
            ready = false;
            if (pageFaceKeys == null || pagePrintIds == null || pageFaceKeys.Count != pagePrintIds.Count
                || colFaceKeys == null || colPrintIds == null || colFaceKeys.Count != colPrintIds.Count || gone == null)
                return new List<string>();
            var faces = new List<string>(pageFaceKeys.Count);
            for (int i = 0; i < pageFaceKeys.Count; i++)
                faces.Add(pageFaceKeys[i] != null && !gone.Contains(pagePrintIds[i]) ? pageFaceKeys[i] : null);
            var held = new HashSet<string>(StringComparer.Ordinal);
            var counts = new Dictionary<string, int>(StringComparer.Ordinal);
            for (int i = 0; i < colPrintIds.Count; i++)
            {
                string c = colPrintIds[i], k = colFaceKeys[i];
                if (c == null || k == null || gone.Contains(c) || !held.Add(c)) continue;
                int n; counts.TryGetValue(k, out n); counts[k] = n + 1;
            }
            var ids = DuplicateShardIds(faces, pagePrintIds, counts, held, out ready);
            ids.Sort(StringComparer.Ordinal);
            return ids;
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

        /// <summary>Every live print of the pack, the Shard pack's set
        /// (PlayerCardsUI.PackShardIds), which is all the pull-wide action
        /// 6804a7e7 offered. NEGATIVE CONTROL for the duplicate cases: on a
        /// pack holding a unique or last copy it must disagree with
        /// DuplicateShardIds. Never called by anything that sends.</summary>
        private static List<string> AllLivePrints(IList<string> pageFaceKeys, IList<string> pagePrintIds)
        {
            var all = new List<string>();
            for (int i = 0; i < pageFaceKeys.Count; i++) if (pageFaceKeys[i] != null) all.Add(pagePrintIds[i]);
            return all;
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

            FlightCases(r);
            DupesCases(r);
            RecoveryCases(r);
            TombstoneCases(r);
            return r;
        }

        // -- fix pass 3, finding 2: a not_owned tombstone lifts when a later read holds the print --

        private static readonly string[] TombFaces = { "A", "A", "B" };
        private static readonly string[] TombIds = { "a1", "a2", "b1" };

        /// <summary>One landing of the tombstone path: the collection read
        /// `held` (each id's face is its first letter, upper-cased) walked
        /// with the tombstones by PackDupes, then the button's answer.</summary>
        private static string TombDupes(PcShardTombstones gone, string[] held, out bool offered)
        {
            var colFaces = new List<string>(); var colIds = new List<string>();
            foreach (var id in held) { colIds.Add(id); colFaces.Add(id.Substring(0, 1).ToUpperInvariant()); }
            bool ready;
            var ids = PackDupes(TombFaces, TombIds, colFaces, colIds, gone, out ready);
            offered = DupesOffered(ready, ids.Count, 40);
            return Ids(ids);
        }

        /// <summary>The tombstone path the client runs, step by step, on a
        /// pack of A (a1), A (a2), B (b1) the player owned whole when it was
        /// pulled. Step 0: the cached collection read holds all three. a2 is
        /// traded away and the strip's Discard on it is refused not_owned:
        /// FailShard tombstones a2 (step 1, the cached read still holding it).
        /// Step 2: the refusal's read-back, dispatched after it, lacks a2.
        /// a2 is traded back; step 3: a read holds it again. Each read is
        /// numbered at dispatch and reconciles the set when it lands, as
        /// ApiClient.FetchPcCollection does. reconcile false is the NEGATIVE
        /// CONTROL: 8fb4ea4b's tombstone, which nothing ever lifted.</summary>
        private static void TombstonePath(bool reconcile, string[] dupes, bool[] offered, bool[] tomb)
        {
            var gone = new PcShardTombstones();
            var whole = new[] { "a1", "a2", "b1" };
            int r0 = gone.Dispatched();
            if (reconcile) gone.Reconcile(whole, r0);
            dupes[0] = TombDupes(gone, whole, out offered[0]); tomb[0] = gone.Contains("a2");
            gone.Add("a2");
            dupes[1] = TombDupes(gone, whole, out offered[1]); tomb[1] = gone.Contains("a2");
            var absent = new[] { "a1", "b1" };
            int r1 = gone.Dispatched();
            if (reconcile) gone.Reconcile(absent, r1);
            dupes[2] = TombDupes(gone, absent, out offered[2]); tomb[2] = gone.Contains("a2");
            int r2 = gone.Dispatched();
            if (reconcile) gone.Reconcile(whole, r2);
            dupes[3] = TombDupes(gone, whole, out offered[3]); tomb[3] = gone.Contains("a2");
        }

        /// <summary>Every order of up to six events drawn from "a collection
        /// read is dispatched", "a refusal names the print" and "the oldest
        /// read on the wire lands holding the print": the print is tombstoned
        /// exactly when a refusal named it and no read dispatched after the
        /// LATEST refusal has landed since. The expectation counts refusals;
        /// the class compares dispatch numbers.</summary>
        private static bool TombstoneOnEveryOrder()
        {
            for (int len = 1; len <= 6; len++)
            {
                int total = 1; for (int i = 0; i < len; i++) total *= 3;
                for (int code = 0; code < total; code++)
                {
                    var g = new PcShardTombstones();
                    var wire = new Queue<KeyValuePair<int, int>>();   // (read number, refusals at its dispatch)
                    int refusals = 0, c = code;
                    bool expect = false;
                    for (int i = 0; i < len; i++, c /= 3)
                    {
                        int ev = c % 3;
                        if (ev == 0) wire.Enqueue(new KeyValuePair<int, int>(g.Dispatched(), refusals));
                        else if (ev == 1) { g.Add("p"); refusals++; expect = true; }
                        else if (wire.Count > 0)
                        {
                            var rd = wire.Dequeue();
                            g.Reconcile(new[] { "p" }, rd.Key);
                            if (refusals > 0 && rd.Value == refusals) expect = false;
                        }
                        if (g.Contains("p") != expect) return false;
                    }
                }
            }
            return true;
        }

        private static void TombstoneCases(SelfTestResult r)
        {
            var dupes = new string[4]; var offered = new bool[4]; var tomb = new bool[4];
            TombstonePath(true, dupes, offered, tomb);
            Check(r, "tombstone path: before the refusal the pack's duplicate a2 is offered",
                  dupes[0] == "[a2]" && offered[0] && !tomb[0], dupes[0]);
            Check(r, "tombstone path: a print the server named not_owned leaves both walks at once (the cached read still holds it)",
                  tomb[1] && dupes[1] == "[]" && !offered[1], dupes[1]);
            Check(r, "tombstone path: a refresh that lacks the print keeps it excluded",
                  tomb[2] && dupes[2] == "[]", dupes[2]);
            Check(r, "tombstone path: and the button state is unchanged by that refresh", offered[2] == offered[1], offered[2].ToString());
            Check(r, "tombstone path: a refresh that holds the print again lifts its tombstone", !tomb[3], tomb[3].ToString());
            Check(r, "tombstone path: the reacquired print is included", dupes[3] == "[a2]", dupes[3]);
            Check(r, "tombstone path: and the button shows, the reacquired print being the pack's only duplicate", offered[3], offered[3].ToString());
            Check(r, "tombstone path: the strip's Discard on the reacquired print is offered again",
                  DiscardOffered(true, false, tomb[3], false), tomb[3].ToString());
            var cd = new string[4]; var co = new bool[4]; var ct = new bool[4];
            TombstonePath(false, cd, co, ct);
            Check(r, "control: without the reconcile (8fb4ea4b's permanent tombstone) the reacquired print stays excluded",
                  ct[3] && cd[3] == "[]" && cd[3] != dupes[3], cd[3]);
            Check(r, "control: and the button stays hidden", !co[3] && co[3] != offered[3], co[3].ToString());

            var g = new PcShardTombstones();
            int stale = g.Dispatched();
            g.Add("a2");
            g.Reconcile(new[] { "a1", "a2", "b1" }, stale);
            Check(r, "tombstone: a read dispatched before the refusal does not lift it, though it holds the print", g.Contains("a2"), "");
            int fresh = g.Dispatched();
            g.Reconcile(new[] { "a1", "a2", "b1" }, fresh);
            Check(r, "tombstone: a read dispatched after the refusal that holds the print lifts it", !g.Contains("a2"), "");
            g.Add("x"); g.Add("y");
            int both = g.Dispatched();
            g.Reconcile(new[] { "x" }, both);
            Check(r, "tombstone: a read lifts only the prints it holds", !g.Contains("x") && g.Contains("y") && g.Count == 1, g.Count.ToString());
            g.Add("x");
            Check(r, "tombstone: a print named again after it was lifted is out again", g.Contains("x"), "");
            g.Clear();
            Check(r, "tombstone: an identity change clears every tombstone", g.Count == 0 && !g.Contains("y"), g.Count.ToString());
            g.Add(null); g.Add("");
            Check(r, "tombstone: no id is never a tombstone", g.Count == 0 && !g.Contains(null), g.Count.ToString());
            Check(r, "tombstone: on every order of up to six dispatches, refusals and landings, a print is out exactly while no read "
                  + "dispatched after the latest refusal has landed holding it", TombstoneOnEveryOrder(), "");
            bool ready;
            var none = PackDupes(TombFaces, TombIds, null, new List<string>(), new PcShardTombstones(), out ready);
            Check(r, "pack dupes: a missing input is not ready and takes nothing", !ready && none.Count == 0, Ids(none));
        }

        // -- fix pass 2, finding 1: a read-back never undoes a newer shard ----

        /// <summary>Request A (strip card a) is given up at 25 s, so its
        /// collection and balance read-backs are dispatched, and the server
        /// answers them from its state before B. Request B (strip card b,
        /// +40) then succeeds and its answer writes the balance and removes b.
        /// A's read-backs land LAST. honourFence false is the NEGATIVE
        /// CONTROL: the read callbacks as a0a66027 wrote them, which replace
        /// both caches unconditionally and must restore B's old balance and
        /// its discarded card. rereads counts the reads sent again.</summary>
        private static void RecoveryRead(bool honourFence, out int balance, out bool cardRestored, out int rereads)
        {
            var f = new PcShardFlight();
            var fence = new PcCacheFence();
            int minted = 0;
            Func<string> mint = () => "nonce" + (++minted);
            int cacheBal = 100, srvBal = 100;
            var cache = new List<string> { "a", "b" };
            var srv = new List<string> { "a", "b" };
            f.KeyFor(ArmSet("a"), mint);
            f.Begin(0f, null, "a");
            bool quick;
            f.GiveUp(26f, 25f, out quick);
            // A's read-backs: stamped at dispatch, answered from the state before B.
            int stampMe = fence.Stamp(), stampCol = fence.Stamp();
            int snapBal = srvBal;
            var snapCol = new List<string>(srv);
            // B: the server commits, then answers; the answer writes the caches.
            f.KeyFor(ArmSet("b"), mint);
            int sB = f.Begin(30f, null, "b");
            srvBal += 40; srv.Remove("b");
            Func<bool> currentB = () => f.IsCurrent(sB);
            if (PcShardFlight.Admits(currentB)) { cacheBal = srvBal; fence.Wrote(); }
            if (f.Settle(sB, null)) { cache.Remove("b"); fence.Wrote(); }
            // A's read-backs land last. A dropped read is owed and sent again
            // once no shard is out (ApiClient.PcSendOwedReads), stamped then,
            // and answered from the state after B.
            if (f.InFlight) { balance = -1; cardRestored = true; rereads = -1; return; }
            rereads = 0;
            if (!honourFence || fence.Admits(stampMe)) cacheBal = snapBal;
            else { rereads++; int again = fence.Stamp(); if (fence.Admits(again)) cacheBal = srvBal; }
            if (!honourFence || fence.Admits(stampCol)) cache = snapCol;
            else { rereads++; int again = fence.Stamp(); if (fence.Admits(again)) cache = new List<string>(srv); }
            balance = cacheBal;
            cardRestored = cache.Contains("b");
        }

        /// <summary>Every order of up to five events drawn from "a read is
        /// dispatched", "a confirmed write" and "the read lands" (one read):
        /// the read is admitted exactly when no write happened between its
        /// dispatch and its landing.</summary>
        private static bool FenceOnEveryOrder()
        {
            for (int len = 1; len <= 5; len++)
            {
                int total = 1; for (int i = 0; i < len; i++) total *= 3;
                for (int code = 0; code < total; code++)
                {
                    var fence = new PcCacheFence();
                    int c = code, stamp = -1;
                    bool wroteSince = false;
                    for (int i = 0; i < len; i++, c /= 3)
                    {
                        int ev = c % 3;
                        if (ev == 0) { stamp = fence.Stamp(); wroteSince = false; }
                        else if (ev == 1) { fence.Wrote(); wroteSince = true; }
                        else if (stamp >= 0)
                        {
                            if (fence.Admits(stamp) != !wroteSince) return false;
                            stamp = -1;
                        }
                    }
                }
            }
            return true;
        }

        private static void RecoveryCases(SelfTestResult r)
        {
            int bal, rr;
            bool card;
            RecoveryRead(true, out bal, out card, out rr);
            Check(r, "recovery: a retired shard's balance read-back landing after a newer shard keeps the newer balance",
                  bal == 140, bal.ToString());
            Check(r, "recovery: a retired shard's collection read-back landing after a newer shard keeps the newer shard's card discarded",
                  !card, card.ToString());
            Check(r, "recovery: each dropped read-back is sent again once, stamped after the newer write", rr == 2, rr.ToString());
            RecoveryRead(false, out bal, out card, out rr);
            Check(r, "control: without the fence the late read-back restores the newer shard's old balance", bal == 100, bal.ToString());
            Check(r, "control: without the fence the late read-back restores the newer shard's discarded card", card, card.ToString());

            var fence = new PcCacheFence();
            int s0 = fence.Stamp();
            Check(r, "fence: a read with no confirmed write while it flew lands", fence.Admits(s0), "");
            fence.Wrote();
            Check(r, "fence: a read dispatched before a confirmed write is dropped", !fence.Admits(s0), "");
            int s1 = fence.Stamp();
            Check(r, "fence: a read dispatched after the write lands", fence.Admits(s1), "");
            fence.Wrote(); fence.Wrote();
            Check(r, "fence: two writes while it flew: still dropped", !fence.Admits(s1), "");
            Check(r, "fence: on every order of dispatch, write and landing, a read lands exactly when no write happened in between",
                  FenceOnEveryOrder(), "");
        }

        // -- fix pass 1, finding 3: the pack's duplicates, never a last copy --

        private static List<string> Dupes(string[] faces, string[] ids, string counts, string[] live, out bool ready)
        {
            var map = new Dictionary<string, int>(StringComparer.Ordinal);
            foreach (var part in counts.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var kv = part.Split('=');
                map[kv[0]] = int.Parse(kv[1]);
            }
            return DuplicateShardIds(faces, ids, map, new HashSet<string>(live ?? ids, StringComparer.Ordinal), out ready);
        }

        private static string Ids(List<string> l) { return l == null ? "(null)" : "[" + string.Join(",", l.ToArray()) + "]"; }

        private static void DupesCases(SelfTestResult r)
        {
            bool ready;
            var faces = new[] { "A", "A", "A", "B", "C" };
            var ids = new[] { "a1", "a2", "a3", "b1", "c1" };
            var got = Dupes(faces, ids, "A=3,B=1,C=1", null, out ready);
            Check(r, "dupes: a pack of A, A, A, B, C (C the last copy) yields exactly the two later A prints",
                  ready && Ids(got) == "[a2,a3]", Ids(got));
            Check(r, "dupes: never B, never C", !got.Contains("b1") && !got.Contains("c1"), Ids(got));
            var all = AllLivePrints(faces, ids);
            Check(r, "control: the all-prints set (Shard pack's) takes all five, B and C included",
                  all.Count == 5 && all.Contains("b1") && all.Contains("c1") && Ids(all) != Ids(got), Ids(all));

            got = Dupes(new[] { "A", "B", "C", "D", "E" }, new[] { "a", "b", "c", "d", "e" }, "A=1,B=1,C=1,D=1,E=1", null, out ready);
            Check(r, "dupes: five faces, one live copy each: nothing", ready && got.Count == 0, Ids(got));
            got = Dupes(new[] { "A", "A" }, new[] { "a1", "a2" }, "A=3", new[] { "a1", "a2", "a0" }, out ready);
            Check(r, "dupes: a face the binder already holds has both pack copies taken (the binder's survives)",
                  ready && Ids(got) == "[a1,a2]", Ids(got));
            got = Dupes(new[] { "A", "A", "B" }, new[] { "a1", "a2", "b1" }, "A=1,B=1", new[] { "a1", "b1" }, out ready);
            Check(r, "dupes: a pack print absent from the collection read is not the player's: ready, neither taken nor counted",
                  ready && got.Count == 0, Ids(got));
            got = Dupes(new[] { "A", "A", "B" }, new[] { "a1", "a2", "b1" }, "A=2,B=1", null, out ready);
            Check(r, "dupes: a collection read holding every pack print: ready", ready && Ids(got) == "[a2]", Ids(got));
            got = Dupes(new[] { "A|foil", "A|plain" }, new[] { "f", "p" }, "A|foil=1,A|plain=1", null, out ready);
            Check(r, "dupes: a foil and a plain copy are different faces: nothing", ready && got.Count == 0, Ids(got));
            got = Dupes(new[] { null, "A" }, new[] { "gone", "a1" }, "A=1", new[] { "a1" }, out ready);
            Check(r, "dupes: a print not live (discarded or gone) is neither taken nor counted", ready && got.Count == 0, Ids(got));
            got = Dupes(new[] { "A", "A" }, new[] { "a1", "a2" }, "A=2", null, out ready);
            Check(r, "dupes: the first copy in display order survives", ready && Ids(got) == "[a2]", Ids(got));
            got = Dupes(new string[0], new string[0], "", null, out ready);
            Check(r, "dupes: an empty pack: ready, nothing", ready && got != null && got.Count == 0, Ids(got));
            got = DuplicateShardIds(faces, ids, null, new HashSet<string>(ids), out ready);
            Check(r, "dupes: a missing input is not ready and takes nothing", !ready && got.Count == 0, Ids(got));
            Check(r, "dupes: on every pack of up to five A/B prints over every binder count, each face keeps a live copy",
                  EveryFaceKeepsOne(), "");
            OwnershipCases(r);
        }

        // -- fix pass 2, finding 2: the duplicates the player owns NOW --------

        /// <summary>The readiness rule as fix pass 1 wrote it: not ready while
        /// any live page print is absent from the collection read. NEGATIVE
        /// CONTROL for the ownership cases: on a pack holding a print traded
        /// away it must disagree with DuplicateShardIds. Never called by
        /// anything that paints or sends.</summary>
        private static bool ReadyAsFixPass1(IList<string> pageFaceKeys, IList<string> pagePrintIds, ICollection<string> livePrintIds)
        {
            for (int i = 0; i < pageFaceKeys.Count; i++)
                if (pageFaceKeys[i] != null && (pagePrintIds[i] == null || !livePrintIds.Contains(pagePrintIds[i]))) return false;
            return true;
        }

        private static void OwnershipCases(SelfTestResult r)
        {
            const int cap = 40;
            bool ready;
            // A pack of A, A, A, B; a2 traded away (the history still shows it
            // live, the collection read omits it); a1 and a3 are still owned.
            var faces = new[] { "A", "A", "A", "B" };
            var ids = new[] { "a1", "a2", "a3", "b1" };
            var live = new[] { "a1", "a3", "b1" };
            var got = Dupes(faces, ids, "A=2,B=1", live, out ready);
            Check(r, "ownership: a traded-away pack print with other owned duplicates: ready, the other duplicate taken",
                  ready && Ids(got) == "[a3]", Ids(got));
            Check(r, "ownership: the traded-away print is never in the set", !got.Contains("a2"), Ids(got));
            Check(r, "ownership: and the button shows", DupesOffered(ready, got.Count, cap), "");
            bool old = ReadyAsFixPass1(faces, ids, new HashSet<string>(live, StringComparer.Ordinal));
            Check(r, "control: fix pass 1's readiness is not ready there, so its button stays hidden",
                  !old && !DupesOffered(old, old ? got.Count : 0, cap), old.ToString());
            // a2 traded away and back: the collection read holds it again
            got = Dupes(faces, ids, "A=3,B=1", new[] { "a1", "a2", "a3", "b1" }, out ready);
            Check(r, "ownership: a reacquired print is included", ready && Ids(got) == "[a2,a3]", Ids(got));
            // a2 traded away and no other duplicate owned
            got = Dupes(new[] { "A", "A", "B" }, new[] { "a1", "a2", "b1" }, "A=1,B=1", new[] { "a1", "b1" }, out ready);
            Check(r, "ownership: no owned duplicates: nothing, and the button is hidden",
                  ready && got.Count == 0 && !DupesOffered(ready, got.Count, cap), Ids(got));
            // a collection read from before the pack: none of its prints, one older A
            got = Dupes(new[] { "A", "A" }, new[] { "a1", "a2" }, "A=1", new[] { "a0" }, out ready);
            Check(r, "ownership: a collection read from before the pack takes nothing (no pack print is counted)",
                  ready && got.Count == 0, Ids(got));
            Check(r, "offered: not ready hides it", !DupesOffered(false, 3, cap), "");
            Check(r, "offered: over one batch hides it", !DupesOffered(true, cap + 1, cap) && DupesOffered(true, cap, cap), "");
            Check(r, "ownership: on every pack of up to five A/B prints with any of them traded away, over every binder count, "
                  + "no traded print is taken and each owned face keeps exactly one copy", EveryOwnedFaceKeepsOne(), "");
        }

        /// <summary>Exhaustive: every pack of one to five prints drawn from
        /// faces A and B, every subset of them traded away (absent from the
        /// collection read), and every binder holding of 0 or 1 copy of each
        /// face outside the pack. Nothing traded is taken, and every face the
        /// read holds keeps exactly one live copy.</summary>
        private static bool EveryOwnedFaceKeepsOne()
        {
            for (int len = 1; len <= 5; len++)
                for (int mask = 0; mask < (1 << len); mask++)
                    for (int gone = 0; gone < (1 << len); gone++)
                        for (int extraA = 0; extraA <= 1; extraA++)
                            for (int extraB = 0; extraB <= 1; extraB++)
                            {
                                var faces = new List<string>(); var ids = new List<string>();
                                var live = new HashSet<string>(StringComparer.Ordinal);
                                var count = new Dictionary<string, int>(StringComparer.Ordinal) { { "A", extraA }, { "B", extraB } };
                                if (extraA == 1) live.Add("xA");
                                if (extraB == 1) live.Add("xB");
                                for (int i = 0; i < len; i++)
                                {
                                    string f = ((mask >> i) & 1) == 1 ? "B" : "A";
                                    faces.Add(f); ids.Add(f + i);
                                    if (((gone >> i) & 1) == 0) { live.Add(f + i); count[f]++; }
                                }
                                bool ready;
                                var took = DuplicateShardIds(faces, ids, count, live, out ready);
                                if (!ready) return false;
                                foreach (var t in took) if (!live.Contains(t)) return false;
                                foreach (var f in new[] { "A", "B" })
                                {
                                    int taken = 0;
                                    foreach (var t in took) if (t.StartsWith(f, StringComparison.Ordinal)) taken++;
                                    if (count[f] > 0 && count[f] - taken != 1) return false;
                                }
                            }
            return true;
        }

        /// <summary>Exhaustive over every pack of one to five prints drawn
        /// from faces A and B and every binder holding of 0 or 1 extra copy
        /// of each: what is taken never reaches a face's last live copy, and
        /// every face with two or more live copies keeps exactly one.</summary>
        private static bool EveryFaceKeepsOne()
        {
            for (int len = 1; len <= 5; len++)
                for (int mask = 0; mask < (1 << len); mask++)
                    for (int extraA = 0; extraA <= 1; extraA++)
                        for (int extraB = 0; extraB <= 1; extraB++)
                        {
                            var faces = new List<string>(); var ids = new List<string>();
                            var live = new HashSet<string>(StringComparer.Ordinal);
                            var count = new Dictionary<string, int>(StringComparer.Ordinal) { { "A", extraA }, { "B", extraB } };
                            for (int i = 0; i < len; i++)
                            {
                                string f = ((mask >> i) & 1) == 1 ? "B" : "A";
                                faces.Add(f); ids.Add(f + i); live.Add(f + i); count[f]++;
                            }
                            bool ready;
                            var took = DuplicateShardIds(faces, ids, count, live, out ready);
                            if (!ready) return false;
                            foreach (var f in new[] { "A", "B" })
                            {
                                int taken = 0;
                                foreach (var t in took) if (t.StartsWith(f, StringComparison.Ordinal)) taken++;
                                if (count[f] > 0 && count[f] - taken != 1) return false;
                            }
                        }
            return true;
        }

        // -- fix pass 1, finding 2: a retired generation touches nothing ------

        /// <summary>One shard given up at 25 s, a newer strip shard started,
        /// then the OLD request's answer arriving late (a success carrying a
        /// balance). honourSerial false is the NEGATIVE CONTROL: the callback
        /// and the cache write as 6804a7e7 wrote them (no generation), which
        /// must change the newer request's latch, nonce and cached balance.</summary>
        private static void LateAnswer(bool honourSerial, out bool settled, out bool latchKept, out bool keyKept, out bool balanceKept)
        {
            var f = new PcShardFlight();
            int minted = 0;
            Func<string> mint = () => "nonce" + (++minted);
            int balance = 100;
            f.KeyFor(ArmSet("A"), mint);
            int sA = f.Begin(0f, null, "A");
            bool quick;
            f.GiveUp(26f, 25f, out quick);
            string kB = f.KeyFor(ArmSet("B"), mint);
            int sB = f.Begin(30f, null, "B");
            // A's late success: ApiClient's cache write, then the callback.
            Func<bool> currentA = () => f.IsCurrent(sA);
            if (honourSerial ? PcShardFlight.Admits(currentA) : true) balance = 250;
            settled = honourSerial ? f.Settle(sA, null) : f.SettleIgnoringSerial(true, null);
            latchKept = f.InFlight && f.QuickId == "B" && f.Serial == sB;
            keyKept = f.QuickKey == kB && f.QuickKeyFor == ArmSet("B");
            balanceKept = balance == 100;
        }

        private static void FlightCases(SelfTestResult r)
        {
            bool settled, latch, key, bal;
            LateAnswer(true, out settled, out latch, out key, out bal);
            Check(r, "late answer: a retired generation settles nothing", !settled, settled.ToString());
            Check(r, "late answer: the newer request's latch is unchanged", latch, latch.ToString());
            Check(r, "late answer: the newer request's nonce is unchanged", key, key.ToString());
            Check(r, "late answer: the cached balance is unchanged", bal, bal.ToString());
            LateAnswer(false, out settled, out latch, out key, out bal);
            Check(r, "control: without the generation the late answer clears the newer latch", !latch, latch.ToString());
            Check(r, "control: without the generation the late answer drops the newer nonce", !key, key.ToString());
            Check(r, "control: without the generation the late answer overwrites the balance", !bal, bal.ToString());

            var f = new PcShardFlight();
            int minted = 0;
            Func<string> mint = () => "n" + (++minted);
            string k1 = f.KeyFor(ArmSet("A"), mint), k2 = f.KeyFor(ArmSet("A"), mint);
            Check(r, "key: the same card keeps its nonce until an answer", k1 == k2 && minted == 1, k1 + "/" + k2);
            int s = f.Begin(0f, "P", null);
            bool quick;
            Check(r, "give-up: not before its bound", !f.GiveUp(25f, 25f, out quick) && f.IsCurrent(s), "");
            Check(r, "give-up: past its bound it releases the latch and retires the generation",
                  f.GiveUp(25.5f, 25f, out quick) && !quick && !f.InFlight && !f.IsCurrent(s) && f.PackId == null, "");
            int sel = f.Begin(30f, null, null);
            Check(r, "late pack answer after a newer selection: nothing settles, the selection stays in flight",
                  !f.Settle(s, "transport") && f.IsCurrent(sel) && f.PackId == null, "");
            Check(r, "the current answer settles once", f.Settle(sel, null) && !f.InFlight, "");
            Check(r, "the same answer delivered twice settles nothing the second time", !f.Settle(sel, null), "");

            var q = new PcShardFlight();
            string kq = q.KeyFor(ArmSet("C"), mint);
            int sq = q.Begin(0f, null, "C");
            Check(r, "a current strip refusal keeps the card's nonce (the retry is a replay)",
                  q.Settle(sq, "transport") && q.QuickKey == kq, q.QuickKey);
            sq = q.Begin(1f, null, "C");
            Check(r, "a current strip success ends the card's nonce", q.Settle(sq, null) && q.QuickKey == null && q.QuickKeyFor == null, q.QuickKey);
            q.KeyFor(ArmSet("C"), mint);
            sq = q.Begin(2f, null, "C");
            Check(r, "a current key_reused drops the card's nonce", q.Settle(sq, "key_reused") && q.QuickKey == null, q.QuickKey);
            q.KeyFor(ArmSet("C"), mint);
            sq = q.Begin(3f, null, "C");
            q.Reset();
            Check(r, "an identity reset retires the flight and its nonce",
                  !q.IsCurrent(sq) && !q.Settle(sq, null) && !q.InFlight && q.QuickKey == null, "");
            Check(r, "the cache write fails closed without a generation check", !PcShardFlight.Admits(null), "");

            // finding 3: a Shard dupes is keyed by the flight's nonce too
            var d = new PcShardFlight();
            string kd = d.KeyFor("dupes|P|a2,a3", mint);
            d.Begin(0f, null, null, "P");
            bool dq;
            Check(r, "a Shard dupes given up is read back and keeps its nonce",
                  d.GiveUp(26f, 25f, out dq) && dq && d.QuickKey == kd && d.DupesOf == null, d.QuickKey);
            int sd = d.Begin(30f, null, null, "P");
            Check(r, "a Shard dupes success ends its nonce", d.Settle(sd, null) && d.QuickKey == null && d.DupesOf == null, d.QuickKey);
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

    /// <summary>
    /// Fix pass 1, finding 2: the batch shard's one in-flight request (a Shard
    /// pack, a binder selection or a pull-strip card) and the strip card's
    /// kept nonce, with ONE writer. Every request is stamped with a
    /// generation (Begin); the 25 s give-up and an identity reset retire it.
    /// An answer settles only when its generation is still the current one
    /// (Settle), and the balance in its body is written into the cache only
    /// then (Admits, ApiClient.PcDiscardBatch): a retired request's late
    /// answer changes neither the cached balance or collection nor the latch
    /// or nonce of a newer request. Free of Unity so the client rules harness
    /// executes it (#391).
    /// </summary>
    internal sealed class PcShardFlight
    {
        internal bool InFlight { get; private set; }
        internal float At { get; private set; }
        internal string PackId { get; private set; }   // the pack a Shard pack in flight came from
        internal string QuickId { get; private set; }  // the strip card a one-card shard is for
        internal string DupesOf { get; private set; }  // the pack a Shard dupes in flight came from (finding 3)
        internal int Serial { get; private set; }      // the current generation
        // The flight's own nonce, kept until an answer: a strip card's, or a
        // pack's duplicates set's (Shard dupes). One slot.
        internal string QuickKey { get; private set; }
        internal string QuickKeyFor { get; private set; }  // the set (ArmSet, or the dupes set) the nonce is for

        /// <summary>Whether the request in flight is keyed by the flight's own
        /// nonce (a strip card or a Shard dupes): its outcome is read back
        /// after a give-up, and its nonce follows KeepKeyAfter.</summary>
        internal bool Keyed { get { return QuickId != null || DupesOf != null; } }

        /// <summary>A new request: a new generation, the latch taken.</summary>
        internal int Begin(float now, string packId, string quickId, string dupesOf = null)
        {
            Serial++;
            InFlight = true; At = now; PackId = packId; QuickId = quickId; DupesOf = dupesOf;
            return Serial;
        }

        /// <summary>Whether an answer stamped `serial` is the current request's.</summary>
        internal bool IsCurrent(int serial)
        {
            return InFlight && serial == Serial;
        }

        /// <summary>The cache write's test: true only when a generation check
        /// is given and passes. Null (no check) fails closed.</summary>
        internal static bool Admits(Func<bool> current)
        {
            return current != null && current();
        }

        /// <summary>The answer stamped `serial`: false, and NOTHING changed,
        /// when that generation is retired; else the latch is released and a
        /// keyed request's nonce (a strip card's or a Shard dupes') is kept or
        /// dropped by PcQuickShardRules.KeepKeyAfter(code) (null code: a
        /// success).</summary>
        internal bool Settle(int serial, string code)
        {
            if (!IsCurrent(serial)) return false;
            bool quick = Keyed;
            InFlight = false; PackId = null; QuickId = null; DupesOf = null;
            if (quick && !PcQuickShardRules.KeepKeyAfter(code)) { QuickKey = null; QuickKeyFor = null; }
            return true;
        }

        /// <summary>The give-up: past `after` seconds with no answer the latch
        /// is released and the generation retired, so a late answer settles
        /// nothing. `quick` says whether it was keyed by the flight's nonce, a
        /// strip card or a Shard dupes (whose outcome is read back; its nonce
        /// is kept, the given_up rule).</summary>
        internal bool GiveUp(float now, float after, out bool quick)
        {
            quick = false;
            if (!InFlight || now - At <= after) return false;
            quick = Keyed;
            Serial++;
            InFlight = false; PackId = null; QuickId = null; DupesOf = null;
            return true;
        }

        /// <summary>The flight's nonce for `set` (a strip card's ArmSet, or a
        /// Shard dupes' exact set): kept while it names the same set, minted
        /// otherwise.</summary>
        internal string KeyFor(string set, Func<string> mint)
        {
            if (QuickKeyFor != set || string.IsNullOrEmpty(QuickKey)) { QuickKey = mint(); QuickKeyFor = set; }
            return QuickKey;
        }

        /// <summary>An identity change: whatever is in flight is retired and
        /// the previous account's nonce dropped.</summary>
        internal void Reset()
        {
            Serial++;
            InFlight = false; At = 0f; PackId = null; QuickId = null; DupesOf = null; QuickKey = null; QuickKeyFor = null;
        }

        /// <summary>NEGATIVE CONTROL for the harness only: the callback as
        /// 6804a7e7 wrote it, which settled every answer whatever its
        /// generation. Never called by anything that sends.</summary>
        internal bool SettleIgnoringSerial(bool quick, string code)
        {
            InFlight = false; PackId = null; QuickId = null; DupesOf = null;
            if (quick && !PcQuickShardRules.KeepKeyAfter(code)) { QuickKey = null; QuickKeyFor = null; }
            return true;
        }
    }

    /// <summary>
    /// Fix pass 2, finding 1: the generation of the Player Cards caches'
    /// confirmed writes. A /pc/me or /pc/collection read is stamped when it
    /// is dispatched (Stamp). Every answer that writes either cache from a
    /// server confirmation moves the generation (Wrote): a shard's or a
    /// discard's balance and the prints it removed, and a trade accept's
    /// drawn prints. A read lands in the cache only when no such write
    /// happened while it was on the wire (Admits). Otherwise its snapshot may
    /// predate that write, so ApiClient drops it and owes the read, sent again
    /// (stamped then) once no shard and no discard is out. A read-back
    /// launched by a retired shard (the 25 s
    /// give-up's) therefore cannot put back a balance or a print that a newer
    /// shard's answer confirmed. The fence orders reads against this
    /// client's own confirmed writes only. Free of Unity so the client rules
    /// harness executes it (#391).
    /// </summary>
    internal sealed class PcCacheFence
    {
        internal int Writes { get; private set; }

        /// <summary>The generation a read carries from its dispatch.</summary>
        internal int Stamp() { return Writes; }

        /// <summary>A confirmed answer wrote a cache.</summary>
        internal void Wrote() { Writes++; }

        /// <summary>Whether a read stamped `stamp` may land: no confirmed
        /// write happened since it was dispatched.</summary>
        internal bool Admits(int stamp)
        {
            return stamp == Writes;
        }
    }

    /// <summary>
    /// Fix pass 3, finding 2: the prints a refused shard's not_owned named
    /// (PlayerCardsUI.FailShard), kept out of the strip's Discard, the Shard
    /// pack's set and both Shard dupes walks (PcQuickShardRules.PackDupes).
    /// A tombstone is not permanent: every successful own-collection read
    /// reconciles the set when it lands (ApiClient.FetchPcCollection), lifting
    /// each tombstone whose print the read positively holds, so a print traded
    /// away and back returns to both walks. Only a read DISPATCHED after the
    /// refusal that wrote a tombstone can lift it: a read already on the wire
    /// when the refusal landed describes the collection from before that
    /// answer, so it cannot say the print came back. Each read carries its
    /// dispatch number (Dispatched) to its landing. An identity change clears
    /// the set (PlayerCardsUI). Free of Unity so the client rules harness
    /// executes it (#391).
    /// </summary>
    internal sealed class PcShardTombstones
    {
        // print id -> the number of own-collection reads dispatched when a refusal named it
        private readonly Dictionary<string, int> gone = new Dictionary<string, int>(StringComparer.Ordinal);
        private int dispatched;

        internal int Count { get { return gone.Count; } }

        /// <summary>Whether `printId` is tombstoned.</summary>
        internal bool Contains(string printId)
        {
            return printId != null && gone.ContainsKey(printId);
        }

        /// <summary>An own-collection read is dispatched: its number, carried
        /// to its landing (Reconcile).</summary>
        internal int Dispatched()
        {
            return ++dispatched;
        }

        /// <summary>A refused shard named `printId` not_owned: out until a read
        /// dispatched after this holds it.</summary>
        internal void Add(string printId)
        {
            if (!string.IsNullOrEmpty(printId)) gone[printId] = dispatched;
        }

        /// <summary>A successful own-collection read, number `read`, that
        /// positively holds `heldPrintIds`: every tombstone it names that was
        /// written before the read was dispatched is lifted. Returns how many
        /// were.</summary>
        internal int Reconcile(IEnumerable<string> heldPrintIds, int read)
        {
            if (heldPrintIds == null || gone.Count == 0) return 0;
            int lifted = 0;
            foreach (var id in heldPrintIds)
            {
                int at;
                if (id != null && gone.TryGetValue(id, out at) && read > at) { gone.Remove(id); lifted++; }
            }
            return lifted;
        }

        /// <summary>An identity change: the previous account's tombstones go.</summary>
        internal void Clear()
        {
            gone.Clear();
        }
    }
}
