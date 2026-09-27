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
        /// (and, for the binder, a forced collection read). V8 6.4 and 6.6:
        /// after every refusal except busy, since the client's own copy may be
        /// what was wrong. Two server-side codes are excluded, each for its
        /// own reason: busy is retried once instead (V8 1.4) and the retry's
        /// answer is the one reconciled, and transport means no answer reached
        /// the client, so there is no refusal to act on (the build brief's
        /// extension of V8's text). no-consent and in-flight are excluded for
        /// a different reason: they are local short-circuits that never
        /// reached the server, not refusals at all, and a read after them
        /// would stop at the same local gate. A rate limit and the version
        /// floor's outdated are answers the server gave, and are reconciled
        /// like every other refusal (round 2, TC-L3).</summary>
        internal static bool RefetchAfterRefusal(string code)
        {
            switch (code)
            {
                // server-side, excluded: retried instead, or no answer at all
                case "busy":
                case "transport":
                    return false;
                // local short-circuits: nothing reached the server
                case "no-consent":
                case "in-flight":
                    return false;
                // server answers, reconciled like every other refusal
                case "rate_limited":
                case "outdated":
                default:
                    return true;
            }
        }

        /// <summary>A busy answer is retried exactly once.</summary>
        internal static bool RetryBusy(string code, bool alreadyRetried)
        {
            return code == "busy" && !alreadyRetried;
        }

        // -- the busy retry's fence (TC-M1) --------------------------------------

        /// <summary>What a busy retry does when its two seconds are up.</summary>
        internal enum RetryVerdict { Send, IdentityChanged, ComposeChanged }

        /// <summary>The compose value of a retry that belongs to no compose:
        /// accept, decline and cancel act on a listed trade, never on the
        /// compose's terms, so only the identity fence applies to them.</summary>
        internal const int NoComposeFence = int.MinValue;

        /// <summary>A proposal's terms as one string: the target, then each
        /// side sorted (Ordinal). SendProposal binds the nonce to it, and a busy
        /// retry compares the key it was armed with against the compose as it
        /// stands when the retry is due.</summary>
        internal static string TermsKey(string to, IEnumerable<string> give, IEnumerable<string> get)
        {
            var g = give != null ? new List<string>(give) : new List<string>();
            var t = get != null ? new List<string>(get) : new List<string>();
            g.Sort(StringComparer.Ordinal);
            t.Sort(StringComparer.Ordinal);
            return (to ?? "") + "|" + string.Join(",", g.ToArray()) + "|" + string.Join(",", t.ToArray());
        }

        /// <summary>The busy retry's fence, consulted BEFORE the retry is sent
        /// (#98: a retry re-checks the precondition it was armed on before it
        /// fires, not after). An identity edge (uiEpoch) drops every retry. A
        /// compose retry is dropped as well when the compose it was armed on
        /// has ended or been replaced (composeSeq: Back, a new compose, and the
        /// EndCompose calls no click makes - the page build, the Trades view
        /// hiding, a paused discovery) or when its terms no longer match the
        /// compose's. The pickers are frozen while the attempt is pending, so
        /// the terms check is the fence's second line, independent of that
        /// freeze: terms captured at Send are never posted for a compose that
        /// no longer holds them. `termsAtArm` null skips the terms check (a
        /// retry that carries no terms: the binder read).</summary>
        internal static RetryVerdict RetryCheck(int epochAtArm, int epochNow, int composeAtArm, int composeNow,
                                                string termsAtArm, string termsNow)
        {
            if (epochAtArm != epochNow) return RetryVerdict.IdentityChanged;
            if (composeAtArm == NoComposeFence) return RetryVerdict.Send;
            if (composeAtArm != composeNow) return RetryVerdict.ComposeChanged;
            if (termsAtArm != null && !string.Equals(termsAtArm, termsNow, StringComparison.Ordinal))
                return RetryVerdict.ComposeChanged;
            return RetryVerdict.Send;
        }

        /// <summary>The second click confirms only on the armed row, inside the window.</summary>
        internal static bool ConfirmsArmed(string armedTradeId, float armedAt, string tradeId, float now)
        {
            return armedTradeId != null && armedTradeId == tradeId && now - armedAt <= ArmWindowSeconds;
        }

        // -- the shared trades cache's ordering fence (TC-L1) --------------------

        /// <summary>The summary and full reads share one cache: a full answer
        /// carries every summary field, so it refreshes the summary slot too.
        /// Each read takes a dispatch number when it is SENT, and a slot never
        /// takes an answer sent before the answer it already holds, so a late
        /// full answer cannot overwrite a newer summary (a closed trade shown
        /// open again). Ordered by dispatch, not by the server_now both views
        /// carry: a fence keyed on the server's clock refuses every answer for
        /// as long as the clock that set the slot runs ahead of the one
        /// answering now (a step back, or two boxes answering), while the next
        /// read sent always outranks everything held, so this fence never
        /// freezes the cache (#276). ApiClient lands every answer, success or
        /// failure, through LandSummary / LandFull (TC-L5) and writes a slot
        /// only when they let it through; an answer kept out moves no
        /// FetchedAt stamp, writes no error and is never classified.</summary>
        internal sealed class TradeCacheFence
        {
            private int sent;

            /// <summary>The dispatch number of the answer the summary slot holds (0: none).</summary>
            internal int Summary { get; private set; }

            /// <summary>The dispatch number of the answer the full slot holds (0: none).</summary>
            internal int Full { get; private set; }

            /// <summary>A read being sent takes the next number.</summary>
            internal int Dispatch() { return ++sent; }

            /// <summary>Newer (or the same) dispatch wins.</summary>
            internal static bool NotOlder(int incoming, int held) { return incoming >= held; }

            /// <summary>A summary answer writes the summary slot only.</summary>
            internal bool TakeSummary(int order)
            {
                if (!NotOlder(order, Summary)) return false;
                Summary = order;
                return true;
            }

            /// <summary>A full answer writes BOTH slots, so it must be no older than either.</summary>
            internal bool TakeFull(int order)
            {
                if (!NotOlder(order, Summary) || !NotOlder(order, Full)) return false;
                Summary = order;
                Full = order;
                return true;
            }

            /// <summary>One summary answer landing, success or failure (TC-L5).
            /// An answer that bears state competes for the slot exactly as a
            /// success does: behind a newer answer a stale 404 or 503 is kept
            /// out, and a newer one is taken. An answer that bears none is let
            /// through only while nothing newer is held and never advances the
            /// slot: it decides nothing, so it must not keep out an older
            /// answer that does (#276). True: ApiClient may act on it.</summary>
            internal bool LandSummary(int order, bool ok, int httpStatus, string code)
            {
                if (!BearsState(ok, httpStatus, code)) return NotOlder(order, Summary);
                return TakeSummary(order);
            }

            /// <summary>One full answer landing: as LandSummary, against both
            /// slots, since a full answer writes both.</summary>
            internal bool LandFull(int order, bool ok, int httpStatus, string code)
            {
                if (!BearsState(ok, httpStatus, code)) return NotOlder(order, Summary) && NotOlder(order, Full);
                return TakeFull(order);
            }

            /// <summary>The caches were emptied (an identity edge, a consent
            /// revoke): nothing is held. An answer sent before the edge never
            /// reaches the fence - ApiClient's epoch check drops it first - and
            /// the numbers keep counting.</summary>
            internal void Clear() { Summary = 0; Full = 0; }
        }

        /// <summary>Whether one landed read answer carries discovery state
        /// (TC-L5): a success, a 404 or a 503 trading_unavailable - exactly the
        /// answers Classify turns into a state. Every other answer (transport,
        /// 401, busy, a rate limit, any other 5xx, a parse failure) leaves the
        /// state as it was and says nothing about the trades.</summary>
        internal static bool BearsState(bool ok, int httpStatus, string code)
        {
            return ok || Classify(Discovery.Unknown, false, false, httpStatus, code) != Discovery.Unknown;
        }

        // -- a deferred re-read and the identity generation (TC-M2) --------------

        /// <summary>A read ApiClient defers to the next frame (the trades
        /// re-ask and the binder re-read, each scheduled by the answer that
        /// just landed) carries the Player Cards generation that was current
        /// when it was SCHEDULED, and after the yield it is sent only while
        /// that generation is still the current one. An identity or consent
        /// edge in between advances the generation: the deferred read is then
        /// dropped whole - no request is built for the previous identity and
        /// nothing is written - and the new identity's own reads fetch its
        /// own data. A request carries its steam id in the URL and the signed
        /// term, and the session token does not change at an identity edge,
        /// so nothing downstream would refuse it.</summary>
        internal static bool GenerationCurrent(int atSchedule, int now)
        {
            return atSchedule == now;
        }

        // -- the Trades view's entry edge (C12, TC-L2) ----------------------------

        /// <summary>Entering the Trades view forces the full read (C12), and the
        /// read stays owed until it is issued. The edge is re-armed by the two
        /// direct signals that the view was left: a frame off the view (the
        /// overlay's per-frame tick, ahead of its two-second throttle, as the
        /// Settings edge is) and the overlay closing (the view survives a
        /// close, so a reopen shows it again with no frame off it in between).
        /// The old wall-clock proxy stays behind them as a secondary guard for
        /// a hide that skips OverlayClosed; it can only ever re-arm an entry,
        /// never suppress one.</summary>
        internal sealed class TradesEntryEdge
        {
            /// <summary>The secondary guard: a tick this long after the last one forgets it.</summary>
            internal const float GapSeconds = 5f;
            private bool lastOn, owed;
            private float lastTickAt = -100f;

            /// <summary>When the last tick ran.</summary>
            internal float LastTickAt { get { return lastTickAt; } }

            /// <summary>Every frame: a frame off the view re-arms the edge (a
            /// leave and return between two ticks is an entry), and an entry
            /// whose read was not issued lapses with the visit.</summary>
            internal void Frame(bool onTrades)
            {
                if (!onTrades) { lastOn = false; owed = false; }
            }

            /// <summary>The overlay closed: the next tick on the view is an entry.</summary>
            internal void OverlayClosed() { lastOn = false; }

            /// <summary>The two-second tick. True when a forced full read is owed:
            /// this tick entered the view, or an earlier entry's read has not
            /// been issued yet (the session was not ready, or reads were not
            /// allowed) and the view has not been left since.</summary>
            internal bool Tick(bool onTrades, float now)
            {
                if (now - lastTickAt > GapSeconds) lastOn = false;
                lastTickAt = now;
                if (!onTrades) owed = false;
                else if (!lastOn) owed = true;
                lastOn = onTrades;
                return owed;
            }

            /// <summary>The owed read was issued.</summary>
            internal void ReadIssued() { owed = false; }

            /// <summary>An identity edge: back to the state of the first tick.</summary>
            internal void Reset() { lastOn = false; owed = false; lastTickAt = -100f; }
        }

        /// <summary>A full read is due on this tick (C12, V8 6.4): the Trades
        /// view is current and reads are allowed, and an entry is owed its
        /// forced read or the 30 s cadence has come round.</summary>
        internal static bool FullReadDue(bool onTrades, bool readsAllowed, bool owed, float now, float fullAt)
        {
            return onTrades && readsAllowed && (owed || now >= fullAt);
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
            // 9. The refetch and retry rules: V8 6.4 and 6.6 reconcile every
            //    refusal but busy; transport had no answer, and the local
            //    short-circuits never reached the server (round 2, TC-L3).
            {
                bool limit = RefetchAfterRefusal("rate_limited");
                Check(r, "a rate limit is a server refusal: the trades and the binder are re-read",
                      limit, "rate_limited=" + limit);
                bool floor = RefetchAfterRefusal("outdated");
                Check(r, "the version floor's outdated is a server answer: re-read", floor, "outdated=" + floor);
                bool refusals = RefetchAfterRefusal("bad_terms") && RefetchAfterRefusal("print_gone")
                                && RefetchAfterRefusal("not_found") && RefetchAfterRefusal("trading_off")
                                && RefetchAfterRefusal("session_required") && RefetchAfterRefusal("http");
                Check(r, "every other server refusal is re-read", refusals, "ok=" + refusals);
                bool busy = !RefetchAfterRefusal("busy") && RetryBusy("busy", false) && !RetryBusy("busy", true)
                            && !RetryBusy("pair_busy", false);
                bool transport = !RefetchAfterRefusal("transport");
                Check(r, "busy is retried once instead and transport had no answer: neither is re-read",
                      busy && transport, "busy=" + busy + " transport=" + transport);
                bool local = !RefetchAfterRefusal("no-consent") && !RefetchAfterRefusal("in-flight");
                Check(r, "the local short-circuits never reached the server: not re-read", local, "ok=" + local);
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
            // 13. The busy retry's fence (TC-M1), consulted before the retry is
            //     sent. The round-1 report's scenario: the first proposal answers
            //     busy, the player acts during the two-second delay, the delay
            //     ends. Every EndCompose bumps composeSeq and none bumps uiEpoch.
            {
                const int ep = 7, seq = 3;
                string armed = TermsKey(VecS2, new[] { VecA }, new[] { VecC });
                var back = RetryCheck(ep, ep, seq, seq + 1, armed, TermsKey(null, null, null));
                Check(r, "busy retry: Back during the delay drops it (the round-1 scenario)",
                      back == RetryVerdict.ComposeChanged, "verdict=" + back);
                // a new compose over the first, to the same player with the same
                // picks: only composeSeq tells the two apart
                var again = RetryCheck(ep, ep, seq, seq + 2, armed, TermsKey(VecS2, new[] { VecA }, new[] { VecC }));
                Check(r, "busy retry: a new compose with the same terms drops it",
                      again == RetryVerdict.ComposeChanged, "verdict=" + again);
                // print A dropped and B chosen on the same compose: only the terms tell them apart
                var repick = RetryCheck(ep, ep, seq, seq, armed, TermsKey(VecS2, new[] { VecB }, new[] { VecC }));
                Check(r, "busy retry: re-picked terms on the same compose drop it",
                      repick == RetryVerdict.ComposeChanged, "verdict=" + repick);
                // the control: nothing changed, so the retry is sent - and there is one
                var same = RetryCheck(ep, ep, seq, seq, armed, TermsKey(VecS2, new[] { VecA }, new[] { VecC }));
                bool once = same == RetryVerdict.Send && RetryBusy("busy", false) && !RetryBusy("busy", true);
                Check(r, "busy retry: an unchanged compose is sent, and only once", once,
                      "verdict=" + same + " once=" + once);
                // an identity edge drops any retry; accept, decline and cancel have no compose fence
                var ident = RetryCheck(ep, ep + 1, seq, seq, armed, armed);
                var act = RetryCheck(ep, ep, NoComposeFence, seq + 5, null, "changed");
                var actIdent = RetryCheck(ep, ep + 1, NoComposeFence, seq, null, null);
                bool fence = ident == RetryVerdict.IdentityChanged && act == RetryVerdict.Send
                             && actIdent == RetryVerdict.IdentityChanged;
                Check(r, "busy retry: an identity edge drops any retry; an action retry has no compose fence", fence,
                      "ident=" + ident + " act=" + act + " act_ident=" + actIdent);
                // the key: each side sorted, the target named, the two sides kept apart
                string k1 = TermsKey(VecS2, new[] { VecB, VecA }, new[] { VecC });
                bool order = k1 == TermsKey(VecS2, new[] { VecA, VecB }, new[] { VecC });
                bool sorted = k1 == VecS2 + "|" + VecA + "," + VecB + "|" + VecC;
                bool sides = TermsKey(VecS2, new[] { VecC }, new[] { VecA, VecB }) != k1;
                bool target = TermsKey(VecS1, new[] { VecA, VecB }, new[] { VecC }) != k1;
                Check(r, "the terms key sorts each side and keeps the target and the sides apart",
                      order && sorted && sides && target,
                      "order=" + order + " sorted=" + sorted + " sides=" + sides + " target=" + target);
            }
            // 14. The trades cache's ordering fence (TC-L1). Each read takes its
            //     dispatch number when it is sent; the slots are modelled as the
            //     answer each holds, written exactly as ApiClient writes them (a
            //     full answer writes both).
            {
                // the round-1 report's scenario: full A is sent, the trade closes,
                // summary B is sent; B lands first, then A lands late
                var f = new TradeCacheFence();
                int a = f.Dispatch(), b = f.Dispatch();
                string summary = null, full = null;
                if (f.TakeSummary(b)) summary = "closed";
                bool tookA = f.TakeFull(a);
                if (tookA) { full = "open"; summary = "open"; }
                Check(r, "cache fence: a late full answer does not overwrite a newer summary (the round-1 scenario)",
                      !tookA && summary == "closed" && full == null,
                      "took_late_full=" + tookA + " summary=" + (summary ?? "-") + " full=" + (full ?? "-"));
                // every landing order of four reads, S1 F2 S3 F4, with the trade
                // open in the first two and closed in the last two: the summary
                // slot ends on the newest answer, no slot goes back to an older
                // answer, and once the trade shows closed it never shows open
                int orders = 0, bad = 0;
                foreach (var landing in Permutations(new[] { 1, 2, 3, 4 }))
                {
                    orders++;
                    var g = new TradeCacheFence();
                    for (int i = 0; i < 4; i++) g.Dispatch();
                    int sumHeld = 0, fullHeld = 0;
                    bool closedShown = false, ok = true;
                    foreach (int n in landing)
                    {
                        bool isFull = n % 2 == 0;
                        if (!(isFull ? g.TakeFull(n) : g.TakeSummary(n))) continue;
                        if (n < sumHeld || (isFull && n < fullHeld)) ok = false;
                        sumHeld = n;
                        if (isFull) fullHeld = n;
                        bool open = n <= 2;
                        if (open && closedShown) ok = false;
                        if (!open) closedShown = true;
                    }
                    if (sumHeld != 4) ok = false;
                    if (!ok) bad++;
                }
                Check(r, "cache fence: every landing order of four reads ends on the newest and never goes back",
                      orders == 24 && bad == 0, "orders=" + orders + " bad=" + bad);
                // the controls: a full answer genuinely newer than the summary is
                // taken (the fence orders answers, it does not refuse full reads),
                // answers that land in the order they were sent are all taken, and
                // a clear forgets what was held while the numbers keep counting
                var h = new TradeCacheFence();
                int s1 = h.Dispatch(), f2 = h.Dispatch();
                bool newer = h.TakeSummary(s1) && h.TakeFull(f2) && h.Summary == f2 && h.Full == f2;
                var k = new TradeCacheFence();
                int f1 = k.Dispatch();
                bool first = k.TakeFull(f1);
                int s2 = k.Dispatch();
                bool second = k.TakeSummary(s2);
                bool inOrder = first && second && k.Summary == s2 && k.Full == f1;
                k.Clear();
                bool cleared = k.Summary == 0 && k.Full == 0 && k.Dispatch() == 3;
                Check(r, "cache fence: a newer full answer is taken, answers in order are all taken, and a clear forgets",
                      newer && inOrder && cleared, "newer=" + newer + " in_order=" + inOrder + " cleared=" + cleared);
            }
            // 15. The Trades view's entry edge (C12, TC-L2), driven the way
            //     MaybeTick and TickTrades drive it (RunEdge). Reads print as the
            //     tick's time plus f (forced: an entry) or c (the 30 s cadence).
            {
                // the round-1 report's scenario: on the view, the overlay closed
                // and reopened inside five seconds, the 30 s read not yet due
                string reopen = RunEdge(new[] {
                    EdgeStep.Tick(0f, true), EdgeStep.Tick(2f, true), EdgeStep.Tick(4f, true),
                    EdgeStep.Close(5f), EdgeStep.Tick(6f, true) });
                Check(r, "entry edge: close and reopen inside five seconds forces the read (the round-1 scenario)",
                      reopen == "0f,6f", "reads=" + reopen);
                // the view left and returned to between two ticks
                string between = RunEdge(new[] {
                    EdgeStep.Tick(0f, true), EdgeStep.Tick(2f, true),
                    EdgeStep.Frame(2.5f, false), EdgeStep.Frame(3f, true), EdgeStep.Tick(4f, true) });
                Check(r, "entry edge: a leave and return between two ticks forces the read",
                      between == "0f,4f", "reads=" + between);
                // an entry on a tick the session was not ready for stays owed
                string owedRead = RunEdge(new[] {
                    EdgeStep.Tick(0f, true), EdgeStep.Tick(2f, false),
                    EdgeStep.Tick(4f, true, false), EdgeStep.Tick(6f, true) });
                Check(r, "entry edge: an entry the session was not ready for is served on the next tick",
                      owedRead == "0f,6f", "reads=" + owedRead);
                // the controls: staying on the view reads on entry and then only on
                // the cadence (never once per tick, never twice), and the five-second
                // gap still re-arms a hide that skipped the close signal
                var stay = new List<EdgeStep>();
                for (int t = 0; t <= 62; t += 2) stay.Add(EdgeStep.Tick(t, true));
                string steady = RunEdge(stay.ToArray());
                Check(r, "entry edge: staying on the view reads on entry, then on the 30 s cadence only",
                      steady == "0f,30c,60c", "reads=" + steady);
                string gap = RunEdge(new[] { EdgeStep.Tick(0f, true), EdgeStep.Tick(2f, true), EdgeStep.Tick(10f, true) });
                Check(r, "entry edge: the five-second gap still re-arms a hide that skipped the close signal",
                      gap == "0f,10f", "reads=" + gap);
            }
            // 16. A deferred re-read and the identity generation (TC-M2). The
            //     trades re-ask and the binder re-read are scheduled by the answer
            //     that just landed and sent one frame later, carrying the
            //     generation that was current when they were scheduled. Composed
            //     here as ApiClient composes them: the fence, the edge's advance
            //     and clear, then GenerationCurrent after the yield.
            {
                bool same = GenerationCurrent(5, 5), newer = GenerationCurrent(5, 6);
                Check(r, "deferred re-read: the scheduling generation passes, a newer one does not",
                      same && !newer, "same=" + same + " newer=" + newer);
                // the round-2 report's scenario: a full read for A is kept out
                // behind a newer summary, so its answer schedules ONE re-ask bound
                // to A's generation; an identity edge A->B lands before the frame
                // comes round (the generation advances, the fence clears)
                var f = new TradeCacheFence();
                int gen = 7;
                int f1 = f.Dispatch(), s2 = f.Dispatch();
                bool tookS2 = f.TakeSummary(s2);
                bool keptF1 = !f.TakeFull(f1);
                int atSchedule = gen;
                gen++; f.Clear();
                int sentForA = 0;
                if (GenerationCurrent(atSchedule, gen)) { sentForA++; f.TakeFull(f.Dispatch()); }
                Check(r, "deferred re-read: an identity edge before the frame drops the re-ask (the round-2 scenario)",
                      tookS2 && keptF1 && sentForA == 0 && f.Summary == 0 && f.Full == 0,
                      "kept_out=" + keptF1 + " sent_for_a=" + sentForA + " summary=" + f.Summary + " full=" + f.Full);
                // the control: the same kept-out answer with no edge in between
                // re-asks once, and the re-ask is taken (round 2's witnessed path)
                var g = new TradeCacheFence();
                int genNow = 7;
                int g1 = g.Dispatch(), t2 = g.Dispatch();
                bool took2 = g.TakeSummary(t2);
                bool kept1 = !g.TakeFull(g1);
                int at2 = genNow;
                int sent = 0; bool reaskTaken = false;
                if (GenerationCurrent(at2, genNow)) { sent++; reaskTaken = g.TakeFull(g.Dispatch()); }
                Check(r, "deferred re-read: with no edge the kept-out answer re-asks once and the re-ask is taken",
                      took2 && kept1 && sent == 1 && reaskTaken && g.Summary == 3 && g.Full == 3,
                      "sent=" + sent + " reask_taken=" + reaskTaken + " summary=" + g.Summary + " full=" + g.Full);
            }
            // 17. State-bearing failures take the same fence (TC-L5). Discovery is
            //     modelled as PlayerCardsUI keeps it (LandRun): an answer the fence
            //     lets through is classified (a success through the summary cache,
            //     a failure in TradeReadLanded); one kept out is never seen.
            //     LandRun prints the state, the view (shown), the full reads, the
            //     next summary delay, and a (let through) or k (kept out) per answer.
            {
                // the fence is outcome-blind: behind a newer answer a stale
                // success, 404 or 503 is kept out alike, and a newer failure that
                // is held keeps out an older success
                var f = new TradeCacheFence();
                int a = f.Dispatch(), b = f.Dispatch();
                bool newerOk = f.LandFull(b, true, 200, null);
                bool stale404 = f.LandSummary(a, false, 404, "http");
                bool stale503 = f.LandSummary(a, false, 503, "trading_unavailable");
                bool staleOk = f.LandSummary(a, true, 200, null);
                var g = new TradeCacheFence();
                int c = g.Dispatch(), d = g.Dispatch();
                bool newer404 = g.LandFull(d, false, 404, "http");
                bool olderOk = g.LandSummary(c, true, 200, null);
                Check(r, "failure fence: behind a newer answer a stale success, 404 or 503 is kept out alike",
                      newerOk && !stale404 && !stale503 && !staleOk && newer404 && !olderOk && f.Summary == b && g.Summary == d,
                      "newer_ok=" + newerOk + " stale_404=" + stale404 + " stale_503=" + stale503 + " stale_ok=" + staleOk
                      + " newer_404=" + newer404 + " older_ok=" + olderOk + " held=" + f.Summary + "/" + g.Summary);
                // the round-2 report's scenario, the view open (Enabled): summary S1
                // is sent and held, full F2 is sent, lands first and says enabled,
                // then S1 lands as a 404 - and, separately, as a 503
                string s404 = LandRun(Discovery.Enabled, 2, new[] { new Landing(true, 2, "ok"), new Landing(false, 1, "404") });
                Check(r, "failure fence: a stale 404 behind a newer success keeps the view and the 120 s cadence (the round-2 scenario)",
                      s404 == "Enabled shown=1 reads=1 next=120 ak", "after=" + s404);
                string s503 = LandRun(Discovery.Enabled, 2, new[] { new Landing(true, 2, "ok"), new Landing(false, 1, "503") });
                Check(r, "failure fence: a stale 503 behind a newer success keeps the reads and the 120 s cadence",
                      s503 == "Enabled shown=1 reads=1 next=120 ak", "after=" + s503);
                // the control: a genuinely newer 404 or 503 is still let through and
                // classifies (a 404 hides the view and rechecks at 600 s), and a
                // newer success recovers from it
                string n404 = LandRun(Discovery.Enabled, 2, new[] { new Landing(false, 1, "ok"), new Landing(true, 2, "404") });
                string n503 = LandRun(Discovery.Enabled, 2, new[] { new Landing(false, 1, "ok"), new Landing(false, 2, "503") });
                string back = LandRun(Discovery.Enabled, 2, new[] { new Landing(true, 1, "404"), new Landing(false, 2, "ok") });
                Check(r, "failure fence: a genuinely newer 404 or 503 is still taken and classifies, and a newer success recovers",
                      n404 == "Absent shown=0 reads=0 next=600 aa" && n503 == "Unavailable shown=1 reads=0 next=120 aa"
                      && back == "Enabled shown=1 reads=1 next=120 aa",
                      "newer_404=" + n404 + " newer_503=" + n503 + " recovered=" + back);
                // which answers bear state: exactly the ones Classify turns into one
                bool bears = BearsState(true, 200, null) && BearsState(false, 404, "http")
                             && BearsState(false, 503, "trading_unavailable");
                bool none = !BearsState(false, 503, "busy") && !BearsState(false, 0, "transport")
                            && !BearsState(false, 401, "session_required") && !BearsState(false, 429, "rate_limited")
                            && !BearsState(false, 500, "http");
                Check(r, "failure fence: only a success, a 404 and a 503 trading_unavailable bear state",
                      bears && none, "bears=" + bears + " none_of_the_rest=" + none);
                // an answer that bears no state decides nothing and never advances
                // the fence, so an older answer that does is still let through; a
                // stale one is kept out like any other
                string newerNone = LandRun(Discovery.Enabled, 2, new[] { new Landing(true, 2, "transport"), new Landing(false, 1, "paused") });
                string newerNoneS = LandRun(Discovery.Enabled, 2, new[] { new Landing(false, 2, "transport"), new Landing(true, 1, "paused") });
                string staleNone = LandRun(Discovery.Enabled, 2, new[] { new Landing(true, 2, "ok"), new Landing(false, 1, "busy") });
                Check(r, "failure fence: an answer that bears no state neither decides nor keeps out an older answer",
                      newerNone == "Paused shown=1 reads=1 next=120 aa" && newerNoneS == "Paused shown=1 reads=1 next=120 aa"
                      && staleNone == "Enabled shown=1 reads=1 next=120 ak",
                      "newer_full=" + newerNone + " newer_summary=" + newerNoneS + " stale=" + staleNone);
                // every landing order of S1 F2 S3 F4 under every mix of six
                // outcomes: the state ends on the newest answer that bears one
                // (read from the table below, not from BearsState), and the answers
                // let through that bear state never go back in dispatch order
                string[] outs = { "ok", "paused", "404", "503", "busy", "transport" };
                var landings = Permutations(new[] { 1, 2, 3, 4 });
                int runs = 0, bad = 0;
                for (int m = 0; m < 1296; m++)
                {
                    var o = new string[5];
                    int x = m;
                    for (int i = 1; i <= 4; i++) { o[i] = outs[x % 6]; x /= 6; }
                    Discovery want = Discovery.Unknown;
                    for (int i = 4; i >= 1; i--)
                    {
                        if (o[i] == "ok") { want = Discovery.Enabled; break; }
                        if (o[i] == "paused") { want = Discovery.Paused; break; }
                        if (o[i] == "404") { want = Discovery.Absent; break; }
                        if (o[i] == "503") { want = Discovery.Unavailable; break; }
                    }
                    foreach (var landing in landings)
                    {
                        runs++;
                        var h = new TradeCacheFence();
                        for (int i = 0; i < 4; i++) h.Dispatch();
                        var state = Discovery.Unknown;
                        int lastState = 0;
                        bool wentBack = false;
                        foreach (int n in landing)
                        {
                            bool ok, enabled; int http; string code;
                            LandOutcome(o[n], out ok, out enabled, out http, out code);
                            bool through = n % 2 == 0 ? h.LandFull(n, ok, http, code) : h.LandSummary(n, ok, http, code);
                            if (!through) continue;
                            if (o[n] != "busy" && o[n] != "transport")
                            {
                                if (n < lastState) wentBack = true;
                                lastState = n;
                            }
                            state = Classify(state, ok, enabled, http, code);
                        }
                        if (state != want || wentBack) bad++;
                    }
                }
                Check(r, "failure fence: every landing order of four mixed answers ends on the newest that bears state",
                      runs == 31104 && bad == 0, "runs=" + runs + " bad=" + bad);
            }
            return r;
        }

        /// <summary>One step of an entry-edge script: a frame, an overlay close,
        /// or a two-second tick (which runs its own frame first, as MaybeTick
        /// does), on a tick the session may not be ready for.</summary>
        private struct EdgeStep
        {
            internal float T;
            internal char Kind;
            internal bool On, Ready;
            internal static EdgeStep Frame(float t, bool on) { return new EdgeStep { T = t, Kind = 'F', On = on, Ready = true }; }
            internal static EdgeStep Close(float t) { return new EdgeStep { T = t, Kind = 'C', On = false, Ready = true }; }
            internal static EdgeStep Tick(float t, bool on, bool ready = true) { return new EdgeStep { T = t, Kind = 'T', On = on, Ready = ready }; }
        }

        /// <summary>Drives a fresh TradesEntryEdge through `steps` as MaybeTick
        /// and TickTrades drive the real one: Frame on every frame, then Tick,
        /// the session gate, FullReadDue, the read (which sets the next cadence
        /// time) and ReadIssued. Returns the reads issued.</summary>
        private static string RunEdge(EdgeStep[] steps)
        {
            var e = new TradesEntryEdge();
            float fullAt = 0f;
            var reads = new List<string>();
            foreach (var s in steps)
            {
                if (s.Kind == 'C') { e.OverlayClosed(); continue; }
                e.Frame(s.On);
                if (s.Kind == 'F') continue;
                bool owed = e.Tick(s.On, s.T);
                if (!s.Ready) continue;
                if (!FullReadDue(s.On, true, owed, s.T, fullAt)) continue;
                reads.Add(s.T.ToString(CultureInfo.InvariantCulture) + (owed ? "f" : "c"));
                fullAt = s.T + FullPollSeconds;
                e.ReadIssued();
            }
            return string.Join(",", reads.ToArray());
        }

        /// <summary>One landed answer of a discovery script (TC-L5): full or
        /// summary, its dispatch number, and what it said (ok, paused, 404,
        /// 503 = trading_unavailable, busy = a 503 busy, transport).</summary>
        private struct Landing
        {
            internal bool Full;
            internal int Order;
            internal string Outcome;
            internal Landing(bool full, int order, string outcome) { Full = full; Order = order; Outcome = outcome; }
        }

        /// <summary>Lands `steps` through a fresh fence (`sent` reads dispatched
        /// first) as ApiClient lands them, and classifies what the fence lets
        /// through as PlayerCardsUI does, from `start`. Returns the state, shown
        /// (TabShown), reads (ReadsAllowed), next (NextSummaryDelay) and a (let
        /// through) or k (kept out) per answer.</summary>
        private static string LandRun(Discovery start, int sent, Landing[] steps)
        {
            var f = new TradeCacheFence();
            for (int i = 0; i < sent; i++) f.Dispatch();
            var d = start;
            var marks = new StringBuilder();
            foreach (var s in steps)
            {
                bool ok, enabled; int http; string code;
                LandOutcome(s.Outcome, out ok, out enabled, out http, out code);
                bool through = s.Full ? f.LandFull(s.Order, ok, http, code) : f.LandSummary(s.Order, ok, http, code);
                marks.Append(through ? 'a' : 'k');
                if (through) d = Classify(d, ok, enabled, http, code);
            }
            return d + " shown=" + (TabShown(d) ? 1 : 0) + " reads=" + (ReadsAllowed(d) ? 1 : 0)
                   + " next=" + NextSummaryDelay(d).ToString(CultureInfo.InvariantCulture) + " " + marks;
        }

        /// <summary>What one scripted outcome looks like to the landing: the ok
        /// flag, the enabled switch, the HTTP status, and the error code
        /// ApiClient.PcTradeErrorCode reads from such an answer.</summary>
        private static void LandOutcome(string o, out bool ok, out bool enabled, out int http, out string code)
        {
            ok = o == "ok" || o == "paused";
            enabled = o == "ok";
            http = ok ? 200 : o == "404" ? 404 : (o == "503" || o == "busy") ? 503 : 0;
            code = ok ? null : o == "503" ? "trading_unavailable" : o == "busy" ? "busy" : o == "404" ? "http" : "transport";
        }

        /// <summary>Every ordering of `items` (the cache fence's landing orders).</summary>
        private static List<int[]> Permutations(int[] items)
        {
            var outp = new List<int[]>();
            Permute((int[])items.Clone(), 0, outp);
            return outp;
        }

        private static void Permute(int[] a, int k, List<int[]> outp)
        {
            if (k == a.Length) { outp.Add((int[])a.Clone()); return; }
            for (int i = k; i < a.Length; i++)
            {
                int t = a[k]; a[k] = a[i]; a[i] = t;
                Permute(a, k + 1, outp);
                t = a[k]; a[k] = a[i]; a[i] = t;
            }
        }

        private static void Check(SelfTestResult r, string name, bool ok, string got)
        {
            if (ok) r.Passed++; else r.Failed++;
            r.Report.Append(ok ? "PASS" : "FAIL").Append(" | case=").Append(name)
                    .Append(" | got=").Append(got ?? "(null)").Append('\n');
        }
    }
}
