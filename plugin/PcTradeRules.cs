using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>Card trading, client half: the decisions the Trades view makes
    /// that are pure functions of values it already holds. The canonical item
    /// list and its digest (the one value that must match the server byte for
    /// byte, or every proposal answers 409 bad_terms with no other symptom),
    /// the signed terms, what a summary read's answer means for the fourth
    /// view, which list a trade belongs in, when a refusal is followed by a
    /// fresh read, which proposals are new since the last summary, and which
    /// of the player's own prints are held by an open offer.
    ///
    /// Unity-free on purpose: tools/client-rules-harness EXECUTES the
    /// SelfTest below under a plain compiler (#391), and the digest cases
    /// there are fixed vectors the SERVER's own player_cards.trade_items /
    /// trade_digest produced, so the client is checked against the server's
    /// function and not against a restatement of itself.</summary>
    internal static class PcTradeRules
    {
        internal const string ItemsVersion = "pctl1";
        /// <summary>Accept is armed by a first click and confirmed by a second
        /// inside this window: the Discard pattern's own constant.</summary>
        internal const float ArmWindowSeconds = 6f;
        /// <summary>A busy answer is retried once after this long (V8 1.4).</summary>
        internal const float BusyRetrySeconds = 2f;
        /// <summary>The summary poll, whether or not Collection is the current tab (V8 6.4).</summary>
        internal const float SummaryPollSeconds = 120f;
        /// <summary>The full read while the Trades view is current (V8 6.4).</summary>
        internal const float FullPollSeconds = 30f;
        /// <summary>An api that answered 404 (a build before trading) is asked
        /// again only this rarely: it will not grow the route mid-session.</summary>
        internal const float AbsentRecheckSeconds = 600f;

        // -- the canonical item list and its digest (V8 2.6, 3.2) --------------

        /// <summary>The lowercase 8-4-4-4-12 text of one print id, or null when
        /// it is not a UUID. Guid.ToString("D") is lowercase already.</summary>
        internal static string CanonicalId(string id)
        {
            if (string.IsNullOrEmpty(id)) return null;
            Guid g;
            if (!Guid.TryParse(id.Trim(), out g)) return null;
            return g.ToString("D");
        }

        /// <summary>Every id of one side made canonical, or null when any one
        /// of them is not a UUID (the server raises on the same input).</summary>
        internal static List<string> CanonicalIds(IList<string> ids)
        {
            if (ids == null) return null;
            var outp = new List<string>(ids.Count);
            foreach (var id in ids)
            {
                string c = CanonicalId(id);
                if (c == null) return null;
                outp.Add(c);
            }
            return outp;
        }

        /// <summary>party + ":" + the side's ids joined by ",", ascending by
        /// ORDINAL text order. Explicitly ordinal: List.Sort() with no comparer
        /// is culture-aware for strings, and Python's sorted() is not.</summary>
        private static string Block(string party, List<string> canonIds)
        {
            var ids = new List<string>(canonIds);
            ids.Sort(StringComparer.Ordinal);
            return party + ":" + string.Join(",", ids.ToArray());
        }

        /// <summary>The canonical item list of a trade in which `steamId`
        /// gives `give` and `to` gives `get`: "pctl1|" + block(X) + "|" +
        /// block(Y), X and Y in ascending steam id text order (ordinal; equal
        /// ids keep the actor first, as Python's stable sort does). Null when
        /// an id is not a UUID or a party is missing.</summary>
        internal static string TradeItems(string steamId, IList<string> give, string to, IList<string> get)
        {
            if (string.IsNullOrEmpty(steamId) || string.IsNullOrEmpty(to)) return null;
            var g = CanonicalIds(give);
            var t = CanonicalIds(get);
            if (g == null || t == null) return null;
            string a = Block(steamId, g), b = Block(to, t);
            bool actorFirst = string.CompareOrdinal(steamId, to) <= 0;
            return ItemsVersion + "|" + (actorFirst ? a + "|" + b : b + "|" + a);
        }

        /// <summary>Lowercase hex SHA-256 of the ASCII bytes of the item list.
        /// Null for a list holding anything outside ASCII: Encoding.ASCII would
        /// hash a '?' where the server refuses to encode at all.</summary>
        internal static string TradeDigest(string items)
        {
            if (items == null) return null;
            foreach (char ch in items) if (ch > (char)0x7F) return null;
            byte[] h;
            using (var sha = SHA256.Create()) h = sha.ComputeHash(Encoding.ASCII.GetBytes(items));
            var sb = new StringBuilder(h.Length * 2);
            foreach (byte x in h) sb.Append(x.ToString("x2", CultureInfo.InvariantCulture));
            return sb.ToString();
        }

        /// <summary>TradeItems then TradeDigest; null when the items are.</summary>
        internal static string Digest(string steamId, IList<string> give, string to, IList<string> get)
        {
            return TradeDigest(TradeItems(steamId, give, to, get));
        }

        /// <summary>The signed term of every trade action (player_cards.canon_trade):
        /// `target` is the counterparty's steam id for a propose and the trade
        /// id for an accept, a decline or a cancel.</summary>
        internal static string CanonTrade(string steamId, string nonce, string action, string target, string digest)
        {
            return "pctrade:" + steamId + ":" + nonce + ":" + action + ":" + target + ":" + digest;
        }

        /// <summary>The signed term of a read (player_cards.canon_read).</summary>
        internal static string CanonRead(string steamId, string what, string target)
        {
            return "pcread:" + steamId + ":" + what + ":" + target;
        }

        // -- discovery: what one summary read means for the fourth view --------

        /// <summary>Unknown: no summary has answered yet (the view stays hidden).
        /// Absent: 404, an api before this release (hidden, re-asked rarely).
        /// Unavailable: 503 trading_unavailable, the schema rule (shown, with
        /// "Trading is not available yet" and nothing to press).
        /// Paused: 200 with enabled false (shown; no propose, no accept;
        /// decline, cancel and the reads still work).
        /// Enabled: 200 with enabled true (shown in full).</summary>
        internal enum Discovery { Unknown = 0, Absent = 1, Unavailable = 2, Paused = 3, Enabled = 4 }

        /// <summary>The state after one summary answer. A read never answers
        /// trading_off (F15), so no branch expects it; every answer that is not
        /// one of the four named ones (transport, 401, a 5xx, busy, a rate
        /// limit) leaves the previous state as it was.</summary>
        internal static Discovery Classify(Discovery previous, bool ok, bool enabled, int httpStatus, string code)
        {
            if (ok) return enabled ? Discovery.Enabled : Discovery.Paused;
            if (httpStatus == 404) return Discovery.Absent;
            if (httpStatus == 503 && code == "trading_unavailable") return Discovery.Unavailable;
            return previous;
        }

        internal static bool TabShown(Discovery d)
        {
            return d == Discovery.Unavailable || d == Discovery.Paused || d == Discovery.Enabled;
        }

        /// <summary>The full read, decline and cancel work while the switch is off (3.13).</summary>
        internal static bool ReadsAllowed(Discovery d)
        {
            return d == Discovery.Paused || d == Discovery.Enabled;
        }

        /// <summary>Propose and accept are offered only while trading is enabled.</summary>
        internal static bool ProposeAllowed(Discovery d)
        {
            return d == Discovery.Enabled;
        }

        internal static float NextSummaryDelay(Discovery d)
        {
            return d == Discovery.Absent ? AbsentRecheckSeconds : SummaryPollSeconds;
        }

        // -- the three lists (V8 6.3) ------------------------------------------

        internal enum Bucket { Incoming = 0, Sent = 1, Recent = 2 }

        /// <summary>An open proposal sent to the viewer is Incoming, one the
        /// viewer sent is Sent; everything else (executed, declined, cancelled,
        /// void, reversed, expired) is Recent. `possible` does not move a row:
        /// an Incoming row that is no longer possible stays in Incoming and
        /// reads No longer possible.</summary>
        internal static Bucket BucketOf(string role, string state)
        {
            if (state == "proposed")
            {
                if (role == "received") return Bucket.Incoming;
                if (role == "sent") return Bucket.Sent;
            }
            return Bucket.Recent;
        }

        // -- after an action ---------------------------------------------------

        /// <summary>Whether a refused action is followed by a forced full read
        /// (and, for the binder, a forced collection read). Every refusal is,
        /// except the answers that taught the client nothing about its own
        /// copy: busy (retried once instead), transport (no answer), a rate
        /// limit (a read on top of a limit that is already refusing), and the
        /// local refusals that never reached the server. The FinishDiscard
        /// rule V8 6.6 names.</summary>
        internal static bool RefetchAfterRefusal(string code)
        {
            switch (code)
            {
                case "busy":
                case "transport":
                case "rate_limited":
                case "no-consent":
                case "outdated":
                case "in-flight":
                    return false;
                default:
                    return true;
            }
        }

        /// <summary>A busy answer is retried exactly once.</summary>
        internal static bool RetryBusy(string code, bool alreadyRetried)
        {
            return code == "busy" && !alreadyRetried;
        }

        /// <summary>The second click confirms only on the armed row, inside the window.</summary>
        internal static bool ConfirmsArmed(string armedTradeId, float armedAt, string tradeId, float now)
        {
            return armedTradeId != null && armedTradeId == tradeId && now - armedAt <= ArmWindowSeconds;
        }

        // -- new proposals (V8 6.4) --------------------------------------------

        /// <summary>The received ids absent from the previous summary, in the
        /// current order. A first summary of the session (previous null)
        /// announces nothing: the comparison is against the last cached
        /// summary, never against an empty set.</summary>
        internal static List<string> NewIds(ICollection<string> previous, IList<string> current)
        {
            var outp = new List<string>();
            if (previous == null || current == null) return outp;
            foreach (var id in current)
                if (!string.IsNullOrEmpty(id) && !previous.Contains(id) && !outp.Contains(id)) outp.Add(id);
            return outp;
        }

        // -- the In a trade badge (V8 6.1) -------------------------------------

        /// <summary>What the badge rule needs of one trade.</summary>
        internal struct TradeRef
        {
            internal string Role, State;
            internal IList<string> Give;
            internal TradeRef(string role, string state, IList<string> give) { Role = role; State = state; Give = give; }
        }

        /// <summary>The print ids held by the viewer's own OPEN offers: the give
        /// side of every proposal the viewer SENT that is still proposed.
        /// sent_open carries TRADE ids, never print ids, so the set is built
        /// from the full read's offers.</summary>
        internal static HashSet<string> OfferedPrintIds(IEnumerable<TradeRef> trades)
        {
            var outp = new HashSet<string>(StringComparer.Ordinal);
            if (trades == null) return outp;
            foreach (var t in trades)
            {
                if (t.Role != "sent" || t.State != "proposed" || t.Give == null) continue;
                foreach (var pid in t.Give)
                {
                    string c = CanonicalId(pid);
                    if (c != null) outp.Add(c);
                }
            }
            return outp;
        }

        /// <summary>One more card may be chosen on a side holding `count`.</summary>
        internal static bool CanAddToSide(int count, int sideMax)
        {
            return sideMax > 0 && count < sideMax;
        }

        // -- the server clock (V8 1.6) -----------------------------------------

        /// <summary>A server ISO timestamp (Python isoformat, with its offset).</summary>
        internal static bool TryParseIso(string iso, out DateTimeOffset v)
        {
            v = default(DateTimeOffset);
            if (string.IsNullOrEmpty(iso)) return false;
            return DateTimeOffset.TryParse(iso, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out v);
        }

        /// <summary>Seconds a proposal has left: expires_at minus the read's
        /// server_now, less the time the answer has sat on this PC since it
        /// landed. Never the PC clock. Negative when past. NaN when either
        /// stamp is unreadable.</summary>
        internal static double SecondsLeft(string expiresAt, string serverNow, double heldSeconds)
        {
            DateTimeOffset e, n;
            if (!TryParseIso(expiresAt, out e) || !TryParseIso(serverNow, out n)) return double.NaN;
            return (e - n).TotalSeconds - Math.Max(0.0, heldSeconds);
        }

        /// <summary>"47h 12m", "12m", "0m" (never below zero).</summary>
        internal static string TimeLeftText(double seconds)
        {
            if (double.IsNaN(seconds) || seconds <= 0) return "0m";
            long mins = (long)Math.Floor(seconds / 60.0);
            long h = mins / 60, m = mins % 60;
            return h > 0
                ? h.ToString(CultureInfo.InvariantCulture) + "h " + m.ToString(CultureInfo.InvariantCulture) + "m"
                : m.ToString(CultureInfo.InvariantCulture) + "m";
        }

        // -- self-test (EXECUTED by tools/client-rules-harness) ------------------

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        // Synthetic parties and prints: 17-digit strings no Steam account has
        // the shape of, and hand-made UUIDs in four spellings (canonical,
        // upper case, braced, 32 hex without hyphens).
        internal const string VecS1 = "11111111111111111";
        internal const string VecS2 = "22222222222222222";
        internal const string VecA = "0f0e0d0c-0b0a-4908-8706-050403020100";
        internal const string VecB = "A0000000-0000-4000-8000-000000000001";
        internal const string VecC = "{00000000-0000-4000-8000-00000000000b}";
        internal const string VecD = "90000000000040008000000000000009";
        // Produced by the SERVER lane's own player_cards.trade_items and
        // trade_digest (backend/api/player_cards.py, claude/trading-server)
        // for exactly the inputs above; see the lane notes for the run.
        internal const string VecItems1 = "pctl1|11111111111111111:0f0e0d0c-0b0a-4908-8706-050403020100,a0000000-0000-4000-8000-000000000001|22222222222222222:00000000-0000-4000-8000-00000000000b";
        internal const string VecDigest1 = "888c16daf6f60428d6960bf6321638eeb9072c294fe7ee8f9d885cd65f91c8b2";
        internal const string VecItems3 = "pctl1|11111111111111111:a0000000-0000-4000-8000-000000000001|22222222222222222:00000000-0000-4000-8000-00000000000b,90000000-0000-4000-8000-000000000009";
        internal const string VecDigest3 = "d8115d6d3180a092cac65e8fa51a6ba58fe735aa0cd439bcd4988691ea5ea2f2";

        /// <summary>The in-game startup check: the digest of the first fixed
        /// vector, so the witness log proves the SHIPPED DLL computes the
        /// server's value, not just the harness build.</summary>
        internal static bool DigestSelfCheck(out string got)
        {
            got = Digest(VecS1, new[] { VecB, VecA }, VecS2, new[] { VecC });
            return got == VecDigest1;
        }

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();

            // 1. The server's own vector: a two-print side given out of order,
            //    one id upper case, the other side braced.
            {
                string items = TradeItems(VecS1, new[] { VecB, VecA }, VecS2, new[] { VecC });
                string d = TradeDigest(items);
                Check(r, "items match the server's trade_items", items == VecItems1, items);
                Check(r, "digest matches the server's trade_digest", d == VecDigest1, d);
            }
            // 2. The same trade seen from the other party: identical list, identical digest.
            {
                string d = Digest(VecS2, new[] { VecC }, VecS1, new[] { VecA, VecB });
                Check(r, "the counterparty's view hashes the same", d == VecDigest1, d);
            }
            // 3. The actor is the HIGHER steam id and gives the two-print side
            //    (one of them spelled as 32 hex digits): the blocks swap.
            {
                string items = TradeItems(VecS2, new[] { VecD, VecC }, VecS1, new[] { VecB });
                string d = TradeDigest(items);
                Check(r, "higher actor: items match the server", items == VecItems3, items);
                Check(r, "higher actor: digest matches the server", d == VecDigest3, d);
            }
            // 4. Negative controls: the fixture tells a wrong list from the right
            //    one. An unsorted side, an upper-case id and upper-case hex all
            //    miss the server's value.
            {
                string unsorted = ItemsVersion + "|" + VecS1 + ":" + CanonicalId(VecB) + "," + CanonicalId(VecA)
                                  + "|" + VecS2 + ":" + CanonicalId(VecC);
                string upperId = ItemsVersion + "|" + VecS1 + ":" + CanonicalId(VecA) + "," + VecB
                                 + "|" + VecS2 + ":" + CanonicalId(VecC);
                string dUnsorted = TradeDigest(unsorted), dUpper = TradeDigest(upperId);
                bool ok = dUnsorted != VecDigest1 && dUpper != VecDigest1
                          && VecDigest1.ToUpperInvariant() != VecDigest1;
                Check(r, "negative controls miss the server's digest", ok,
                      "unsorted=" + dUnsorted + " upper=" + dUpper);
            }
            // 5. A malformed id yields no digest (the server raises): nothing is signed.
            {
                string d = Digest(VecS1, new[] { "not-a-uuid" }, VecS2, new[] { VecC });
                Check(r, "a malformed id yields no digest", d == null, d);
                Check(r, "a non-ASCII list yields no digest", TradeDigest("pctl1|" + (char)0xE9) == null, "n/a");
            }
            // 6. The signed terms, byte for byte as player_cards.canon_trade / canon_read build them.
            {
                string t = CanonTrade(VecS1, "n0nce123", "propose", VecS2, "abababababababababababababababababababababababababababababababab");
                Check(r, "canon_trade", t == "pctrade:11111111111111111:n0nce123:propose:22222222222222222:abababababababababababababababababababababababababababababababab", t);
                string rd = CanonRead(VecS1, "trades", "summary");
                string rc = CanonRead(VecS1, "collection", VecS2);
                Check(r, "canon_read", rd == "pcread:11111111111111111:trades:summary"
                                       && rc == "pcread:11111111111111111:collection:22222222222222222", rd + " " + rc);
            }
            // 7. Discovery, every named answer and the ones that must not move it.
            {
                var u = Discovery.Unknown;
                bool ok = Classify(u, true, true, 200, null) == Discovery.Enabled
                          && Classify(u, true, false, 200, null) == Discovery.Paused
                          && Classify(u, false, false, 404, "http") == Discovery.Absent
                          && Classify(Discovery.Enabled, false, false, 404, "http") == Discovery.Absent
                          && Classify(u, false, false, 503, "trading_unavailable") == Discovery.Unavailable
                          && Classify(Discovery.Enabled, false, false, 0, "transport") == Discovery.Enabled
                          && Classify(Discovery.Paused, false, false, 409, "busy") == Discovery.Paused
                          && Classify(u, false, false, 401, "session_required") == Discovery.Unknown
                          && Classify(u, false, false, 503, "http") == Discovery.Unknown;
                Check(r, "discovery classifies the four answers and keeps state on the rest", ok, "ok=" + ok);
                bool vis = !TabShown(Discovery.Unknown) && !TabShown(Discovery.Absent)
                           && TabShown(Discovery.Unavailable) && TabShown(Discovery.Paused) && TabShown(Discovery.Enabled)
                           && !ProposeAllowed(Discovery.Paused) && ProposeAllowed(Discovery.Enabled)
                           && ReadsAllowed(Discovery.Paused) && !ReadsAllowed(Discovery.Unavailable)
                           && NextSummaryDelay(Discovery.Absent) == AbsentRecheckSeconds
                           && NextSummaryDelay(Discovery.Enabled) == SummaryPollSeconds;
                Check(r, "discovery gates the tab, propose and reads", vis, "ok=" + vis);
            }
            // 8. Buckets.
            {
                bool ok = BucketOf("received", "proposed") == Bucket.Incoming
                          && BucketOf("sent", "proposed") == Bucket.Sent
                          && BucketOf("received", "executed") == Bucket.Recent
                          && BucketOf("sent", "expired") == Bucket.Recent
                          && BucketOf("sent", "void") == Bucket.Recent
                          && BucketOf(null, "proposed") == Bucket.Recent;
                Check(r, "buckets", ok, "ok=" + ok);
            }
            // 9. The refetch and retry rules.
            {
                bool ok = !RefetchAfterRefusal("busy") && !RefetchAfterRefusal("transport")
                          && !RefetchAfterRefusal("rate_limited")
                          && RefetchAfterRefusal("bad_terms") && RefetchAfterRefusal("print_gone")
                          && RefetchAfterRefusal("not_found") && RefetchAfterRefusal("trading_off")
                          && RefetchAfterRefusal("http")
                          && RetryBusy("busy", false) && !RetryBusy("busy", true) && !RetryBusy("pair_busy", false);
                Check(r, "refetch after every refusal but busy/transport/limit; busy retried once", ok, "ok=" + ok);
                bool arm = ConfirmsArmed("t1", 10f, "t1", 15.9f) && !ConfirmsArmed("t1", 10f, "t1", 16.1f)
                           && !ConfirmsArmed("t1", 10f, "t2", 11f) && !ConfirmsArmed(null, 10f, "t1", 11f);
                Check(r, "accept confirms only on the armed row inside six seconds", arm, "ok=" + arm);
            }
            // 10. New ids: never on the first summary; only the ids not seen before.
            {
                var first = NewIds(null, new[] { "a", "b" });
                var next = NewIds(new List<string> { "a" }, new[] { "a", "b", "c", "b" });
                bool ok = first.Count == 0 && next.Count == 2 && next[0] == "b" && next[1] == "c";
                Check(r, "new ids against the last summary, never against zero", ok,
                      "first=" + first.Count + " next=" + string.Join(",", next.ToArray()));
            }
            // 11. The In a trade set: the give side of SENT open proposals only.
            {
                var trades = new List<TradeRef>
                {
                    new TradeRef("sent", "proposed", new[] { VecB }),
                    new TradeRef("received", "proposed", new[] { VecA }),
                    new TradeRef("sent", "executed", new[] { VecD }),
                };
                var set = OfferedPrintIds(trades);
                bool ok = set.Count == 1 && set.Contains(CanonicalId(VecB));
                Check(r, "offered = give of sent open proposals only", ok, "count=" + set.Count);
                bool cap = CanAddToSide(0, 3) && CanAddToSide(2, 3) && !CanAddToSide(3, 3) && !CanAddToSide(0, 0);
                Check(r, "a side is capped at the server's prints_per_side_max", cap, "ok=" + cap);
            }
            // 12. The server clock.
            {
                double s = SecondsLeft("2026-09-28T19:00:00.123456+00:00", "2026-09-26T18:30:00.123456+00:00", 60.0);
                double bad = SecondsLeft("garbage", "2026-09-26T18:30:00+00:00", 0.0);
                bool ok = Math.Abs(s - (48.5 * 3600.0 - 60.0)) < 0.001 && double.IsNaN(bad)
                          && TimeLeftText(s) == "48h 29m" && TimeLeftText(59.0) == "0m"
                          && TimeLeftText(-5.0) == "0m" && TimeLeftText(3599.0) == "59m";
                Check(r, "time left from the server clock", ok, "s=" + s.ToString(CultureInfo.InvariantCulture) + " text=" + TimeLeftText(s));
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
