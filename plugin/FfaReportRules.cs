using System;
using System.Collections.Generic;
using System.Text;

namespace CompetitiveRounds
{
    /// <summary>The three decisions the FFA report path makes that are pure
    /// functions of values it has already collected: WHO submits, WHAT KEY the
    /// submission carries, and WHETHER a refusal is final.
    ///
    /// They live here rather than inline at their call sites because all three
    /// are rules rather than plumbing — each has a stated property that has to
    /// hold for every input, not just for the case in front of the author —
    /// and here they can be exercised by a test without a Photon room, a
    /// PlayerManager or a live server. Their call sites keep everything that
    /// is genuinely contextual: which actors are present, what the local
    /// Steam ID is, and what to log.</summary>
    internal static class FfaReportRules
    {
        /// <summary>The one status code that means "understood, and the state
        /// you are reporting about has already settled". Named once so the
        /// string form and the status-code form cannot drift apart.</summary>
        internal const long SettledRefusalStatus = 409;

        /// <summary>"Understood, and this report may not settle this game" —
        /// the hardened FFA endpoint's answer to a key whose tail is not the
        /// lobby's games_played + 1. The report is refused and captured for
        /// recovery; it is not a thing to send again, because the state it was
        /// refused on is in the lobby row and the next attempt finds it in the
        /// same place.</summary>
        internal const long QuarantinedRefusalStatus = 403;

        /// <summary>The one refusal that IS worth another attempt: the server
        /// could not make a decision at all. Named so that "terminal" is a
        /// stated list rather than "anything that is not a success", which is
        /// how a retryable code ends up terminal the day it is first
        /// returned.</summary>
        internal const long RetryableRefusalStatus = 503;

        /// <summary>A settled refusal, from the status code.</summary>
        internal static bool IsSettledRefusal(long statusCode)
        {
            return statusCode == SettledRefusalStatus;
        }

        /// <summary>A refusal this client must NOT retry and must NOT re-key.
        ///
        /// Both codes mean the server read the body, understood it, and
        /// refused on state the next attempt will find in the same place —
        /// 409 because the game is already recorded, 403 because this key's
        /// game number is not the one the lobby is expecting. Retrying either
        /// spends a settlement request on a decision that has been made; the
        /// dangerous variant is re-keying, because a second key is a second
        /// GAME to the server and that is the double-settlement this whole
        /// path exists to prevent.
        ///
        /// 503 is deliberately not here: it is the server declining to decide,
        /// which is the one refusal the transport loop's premise still fits.
        /// </summary>
        internal static bool IsTerminalRefusal(long statusCode)
        {
            return statusCode == SettledRefusalStatus
                || statusCode == QuarantinedRefusalStatus;
        }

        /// <summary>A terminal refusal, from the formatted response text.
        /// Matched on the CODE for the same reason IsSettledRefusal is.</summary>
        internal static bool IsTerminalRefusal(string response)
        {
            return IsSettledRefusal(response) || HasStatus(response, QuarantinedRefusalStatus);
        }

        /// <summary>A settled refusal, from the formatted response text an
        /// outbox entry carries ("HTTP &lt;code&gt;: &lt;body&gt;").
        ///
        /// Matched on the CODE and never on the phrase beside it: the phrase
        /// is product-facing text that gets reworded — the FFA report endpoint
        /// alone refuses with three different ones — and a check keyed on
        /// wording goes on passing silently once the wording moves (#306).</summary>
        internal static bool IsSettledRefusal(string response)
        {
            return HasStatus(response, SettledRefusalStatus);
        }

        private static bool HasStatus(string response, long status)
        {
            if (string.IsNullOrEmpty(response)) return false;
            string code = status.ToString(System.Globalization.CultureInfo.InvariantCulture);
            // The colon is part of the match: without it "HTTP 409" is a
            // PREFIX of codes that do not exist today and would be read as
            // settled if they ever did.
            return response.StartsWith("HTTP " + code + ":", StringComparison.Ordinal)
                || response.IndexOf("HTTP/1.1 " + code + " ", StringComparison.Ordinal) >= 0;
        }

        /// <summary>The key one FFA game's report is filed under. It exists so
        /// that when the election DOES return two reporters, their two reports
        /// carry the SAME key and the server can refuse the second one.
        ///
        /// The election is single-valued across seats except in one case it
        /// chooses deliberately: a client that has received no witness property
        /// at all falls back while its peers do not, and two seats submit (see
        /// ElectReporter — nobody submitting is the worse outcome). That case
        /// is only survivable if the server can SEE the duplicate, and it can
        /// only see it if both reports name the same game.
        ///
        /// The key this replaced was
        /// "{room}_{matchStartTime:HHmmss}_r{GameNumber}", and neither half
        /// after the room name was shared. matchStartTime is DateTime.UtcNow
        /// read locally when each seat's own match-start hook ran, so two seats
        /// a second apart stamp different clocks; GameNumber is a local counter
        /// that drift adoption moves per seat. Two electors therefore produced
        /// two DIFFERENT keys, `uq_ffa_match_room` had nothing to collide with,
        /// and both reports settled — one game, two results.
        ///
        /// So: the room name, which every seat reads from Photon, and the game
        /// number the HOST published in the room's own property, which every
        /// seat reads from the same place — FROZEN at the game-over edge, so
        /// that a host that has already opened the next cycle cannot make two
        /// electors of the same game disagree. No local clock takes part, and
        /// no local counter can stand in.
        ///
        /// THE "_rN" SUFFIX IS A SERVER CONTRACT, not decoration. The report
        /// endpoint recovers the game number from this string with an anchored
        /// "_r(\d+)$" and keys that game's bet settlement on it; a key ending
        /// any other way silently falls back to "the lobby's games_played + 1"
        /// and an out-of-order report then settles the wrong game's wagers. Do
        /// not restyle the suffix. The whole key also has to fit
        /// ffa_matches.photon_room_id, VARCHAR(64) — this form is shorter than
        /// the one it replaced, so that bound only got looser.
        ///
        /// THE NUMBER IS A FROZEN SNAPSHOT, NOT A LIVE READ, AND THERE IS NO
        /// FALLBACK (Codex client r2 HIGH, this method). Two separate things
        /// were wrong with reading `FfaMode.PublishedGameNumber()` here:
        ///
        ///  * cr_ffa_cyc is MUTABLE. The host writes the next game's number
        ///    into it the moment the next pick cycle opens, so an elector
        ///    whose game-over handling ran a little later than its peers' read
        ///    N+1 for the game they keyed as N. Two keys, one physical game.
        ///  * the local counter as a fallback could MINT a number. Drift
        ///    adoption moves that counter per seat — precisely the per-seat
        ///    value the shared key exists to escape — so the fallback
        ///    manufactured exactly the disagreement it was there to avoid.
        ///
        /// So this takes ONE number: whatever FfaMode.FreezeReportGameNumber
        /// captured at the game-over edge, before any election ran. A rollover
        /// after that instant cannot reach the key. A seat that froze nothing
        /// gets NULL — it is ineligible to file, and the caller must not
        /// substitute anything, because there is nothing left to substitute
        /// that every seat would agree on.
        ///
        /// WHY A WRONG NUMBER IS WORSE THAN A MISSING ONE. The hardened FFA
        /// endpoint settles a report only when this tail equals the lobby's
        /// games_played + 1 under the lobby lock, and refuses-and-quarantines
        /// every other tail terminally. A key one game AHEAD of the truth is
        /// therefore not simply rejected for ever: once the real game N
        /// settles, expected progress becomes N+1 and the stale N+1 report
        /// becomes acceptable as a second game. Fail closed.
        ///
        /// Returns null, never a "0" key, when there is no number — "_r0" is a
        /// legal key for game zero and would be filed rather than refused.
        /// </summary>
        internal static string ReportRoomId(string roomName, int frozenGame)
        {
            if (frozenGame < 0) return null;
            // Invariant formatting: a culture-specific rendering would make the
            // key seat-dependent again, which is the whole defect.
            return (roomName ?? "") + "_r"
                + frozenGame.ToString(System.Globalization.CultureInfo.InvariantCulture);
        }

        /// <summary>Whether this seat may file at all. Stated once, so the
        /// eligibility rule and the key cannot disagree: a seat is eligible
        /// exactly when ReportRoomId gave it a key.</summary>
        internal static bool CanFile(string reportRoomId)
        {
            return !string.IsNullOrEmpty(reportRoomId);
        }

        /// <summary>Elect the seat that submits this game's report: the lowest
        /// Steam ID among the seats that WITNESSED the game's start, falling
        /// back to the lowest among those merely PRESENT when no witness is
        /// known.
        ///
        /// Two properties, both load-bearing.
        ///
        /// TOTAL. For any <paramref name="present"/> holding at least one
        /// non-empty id this returns a seat. The witness fallback is one half
        /// of that; the ordinal pass below is the other, and it was missing.
        /// A qualifier that can disqualify every candidate is a guard only the
        /// disqualified seats evaluate: the sitting then ends with nobody
        /// submitting and voids itself silently, which is strictly worse than
        /// the defect the qualifier exists for (#430). "Every id in the
        /// electorate fails long.TryParse" was exactly such a qualifier — the
        /// method returned null, every caller took its own last resort, and
        /// every seat self-elected. One unparseable id costs that seat its
        /// candidacy; ALL of them used to cost the game its single reporter.
        ///
        /// SINGLE-VALUED ACROSS SEATS. Both inputs are derived from replicated
        /// Photon state, so every client computes the same answer and exactly
        /// one of them submits. The exception is a client that has received no
        /// witness property at all while its peers have: it falls back while
        /// they do not, and two seats can submit. That direction is chosen
        /// deliberately — the server settles a game once and answers the
        /// second report terminally, whereas nobody submitting loses the
        /// game's result outright.
        ///
        /// Returns null only when there is nobody to elect at all; the caller
        /// supplies its own last resort for that.</summary>
        internal static string ElectReporter(List<string> present, List<string> witnesses,
                                             out bool usedFallback)
        {
            usedFallback = witnesses == null || witnesses.Count == 0;
            var electorate = usedFallback ? present : witnesses;
            if (electorate == null) return null;

            string lowest = null;
            long lowVal = long.MaxValue;
            foreach (var sid in electorate)
            {
                long v;
                // An unparseable id is not a candidate WHILE ANY id parses. It
                // is also invisible to its peers' comparisons, so a seat
                // carrying one can never be deferred TO.
                if (!long.TryParse(sid, out v)) continue;
                if (v < lowVal) { lowVal = v; lowest = sid; }
            }
            if (lowest != null) return lowest;

            // Nothing parsed, and the electorate is not empty. Numeric order
            // has no meaning over these ids, but ORDINAL order does, and it is
            // a property of the SET rather than of the order it arrived in —
            // so every seat, reading the same replicated membership, picks the
            // same one and exactly one submits. Returning null here made each
            // caller fall back to self-election, i.e. all of them submitting.
            // Empty entries are not seats and take no part.
            foreach (var sid in electorate)
            {
                if (string.IsNullOrEmpty(sid)) continue;
                if (lowest == null || string.CompareOrdinal(sid, lowest) < 0) lowest = sid;
            }
            return lowest;
        }

        // ── self-test (EXECUTED by tools/client-rules-harness) ──────────────
        // These are the rules whose stated properties have to hold for every
        // input, so they are RUN rather than asserted about (#391, #340).

        internal sealed class SelfTestResult
        {
            internal int Passed;
            internal int Failed;
            internal readonly StringBuilder Report = new StringBuilder();
        }

        /// <summary>The suffix the server recovers this key's game number from,
        /// anchored exactly as backend/api/main.py's _ffa_room_game_no anchors
        /// it. Kept here so the case below tests the CONTRACT and not a
        /// restatement of whatever ReportRoomId happens to emit.</summary>
        private static readonly System.Text.RegularExpressions.Regex ServerGameSuffix =
            new System.Text.RegularExpressions.Regex(@"_r(\d+)$");

        internal static SelfTestResult SelfTest()
        {
            var r = new SelfTestResult();
            const string room = "ffa_7f3a9c21b4e8";

            // 0. The electorate exists but nothing in it parses. Before the
            //    ordinal pass this returned null and every seat self-elected.
            {
                bool fb;
                var odd = new List<string> { "steam:beta", "steam:alpha", "steam:gamma" };
                string a = ElectReporter(odd, null, out fb);
                var shuffled = new List<string> { "steam:gamma", "steam:alpha", "steam:beta" };
                string b = ElectReporter(shuffled, null, out fb);
                Check(r, "an unparseable electorate still elects one seat",
                      a != null && a == b && a == "steam:alpha",
                      "a=" + (a ?? "<null>") + " b=" + (b ?? "<null>"));
            }

            // 0b. A single parseable id among unparseable ones still wins: the
            //     ordinal pass is a LAST resort, not a peer of the numeric one.
            {
                bool fb;
                // "007-alpha" sorts ORDINALLY BEFORE the Steam id, so a
                //     build that let the ordinal pass outrank the numeric
                //     one picks it and this case reds. An unparseable id
                //     sorting after would have passed either way.
                var mixed = new List<string> { "007-alpha", "76561198040410653" };
                string a = ElectReporter(mixed, null, out fb);
                Check(r, "one parseable id outranks the ordinal fallback",
                      a == "76561198040410653", "a=" + (a ?? "<null>"));
            }

            // 1. THE FIX. Two seats whose LOCAL counters have drifted apart
            //    froze the same published number at game over, so they file
            //    under one key. The local counter is not an input at all any
            //    more, which is what makes this true by construction.
            {
                string a = ReportRoomId(room, 4);
                string b = ReportRoomId(room, 4);
                Check(r, "two seats agree on the key", a == b && a == room + "_r4",
                      "a=" + a + " b=" + b);
            }

            // 2. And the key is not a function of anything else: called twice
            //    with the same inputs it is the same string. (The old key read
            //    DateTime.UtcNow, which this shape cannot do.)
            {
                string a = ReportRoomId(room, 4);
                string b = ReportRoomId(room, 4);
                Check(r, "the key is a pure function of its inputs", a == b, "a=" + a + " b=" + b);
            }

            // 3. THE ROLLOVER. This is the r2 HIGH, driven end to end: the
            //    host publishes N+1 while a lagging elector is still handling
            //    game N. The lagging seat froze N at the game-over edge and
            //    the later value cannot reach its key, so both electors still
            //    file N — one key, one game.
            {
                const int frozenAtGameOver = 7;
                const int publishedAfterRollover = 8;
                string prompt = ReportRoomId(room, frozenAtGameOver);
                string lagging = ReportRoomId(room, frozenAtGameOver);
                Check(r, "a rollover after the freeze cannot change the key",
                      prompt == lagging && prompt == room + "_r7"
                      && prompt != ReportRoomId(room, publishedAfterRollover),
                      "prompt=" + prompt + " lagging=" + lagging);
            }

            // 3b. NEGATIVE CONTROL for case 3. The rollover is only harmless
            //     because the number is frozen; a seat that read the property
            //     LATE would key N+1 and settle a second game. If this case
            //     ever fails, the two keys have stopped being distinguishable
            //     and case 3 proves nothing.
            {
                Check(r, "a seat keying the rolled-over number would file a different game",
                      ReportRoomId(room, 7) != ReportRoomId(room, 8),
                      ReportRoomId(room, 7) + " vs " + ReportRoomId(room, 8));
            }

            // 4. NO SNAPSHOT IS NO KEY. There is no local fallback: a seat
            //    that froze nothing is ineligible, and CanFile says the same
            //    thing the key does.
            {
                string k = ReportRoomId(room, -1);
                Check(r, "an absent snapshot yields no key and no eligibility",
                      k == null && !CanFile(k) && CanFile(ReportRoomId(room, 0)),
                      "k=" + (k ?? "<null>"));
            }

            // 4b. MIXED SNAPSHOTS ACROSS THE ELECTORATE. Three seats: one
            //     froze N, one froze N+1, one froze nothing. Exactly one
            //     distinct key may exist among the ELIGIBLE seats that agree,
            //     the ineligible seat files nothing, and the disagreeing seat
            //     is a different key — which is the residual this fails closed
            //     against and the reason the freeze happens before any await.
            {
                string atN = ReportRoomId(room, 5);
                string atNPlus1 = ReportRoomId(room, 6);
                string none = ReportRoomId(room, -1);
                int eligible = (CanFile(atN) ? 1 : 0) + (CanFile(atNPlus1) ? 1 : 0)
                             + (CanFile(none) ? 1 : 0);
                Check(r, "mixed snapshots: the unsnapshotted seat cannot file and the others are distinguishable",
                      eligible == 2 && atN != atNPlus1 && none == null,
                      "atN=" + atN + " atN+1=" + atNPlus1 + " none=" + (none ?? "<null>")
                      + " eligible=" + eligible);
            }

            // 5. Two different games in one room never share a key.
            {
                Check(r, "different games get different keys",
                    ReportRoomId(room, 3) != ReportRoomId(room, 4),
                    ReportRoomId(room, 3) + " vs " + ReportRoomId(room, 4));
            }

            // 6. THE SERVER CONTRACT. The endpoint keys bet settlement on the
            //    number it pulls out of this string with an anchored _r(\d+)$.
            //    Tested against that regex, not against the format string.
            {
                var m = ServerGameSuffix.Match(ReportRoomId(room, 11));
                Check(r, "the server can recover the game number",
                    m.Success && m.Groups[1].Value == "11",
                    "match=" + m.Success + " value=" + (m.Success ? m.Groups[1].Value : "-"));
            }

            // 7. ffa_matches.photon_room_id is VARCHAR(64). A key longer than
            //    that is a 500 on every report of that room.
            {
                string k = ReportRoomId(room, 999);
                Check(r, "the key fits the column", k.Length <= 64, "len=" + k.Length + " k=" + k);
            }

            // 8. Degenerate inputs: a missing room name with a real snapshot
            //    still produces a legal suffix, and a missing snapshot is
            //    still no key whatever the room name is.
            {
                string k = ReportRoomId(null, 0);
                string none = ReportRoomId(null, -1);
                Check(r, "degenerate inputs are legal or absent, never invented",
                    k == "_r0" && ServerGameSuffix.IsMatch(k) && none == null,
                    "k=" + k + " none=" + (none ?? "<null>"));
            }

            // 9. ElectReporter is TOTAL over a non-empty present set, even with
            //    no witnesses at all.
            {
                var present = new List<string> { "76561198040410653", "76561198720512419" };
                string who = ElectReporter(present, new List<string>(), out bool fb);
                Check(r, "election is total without witnesses",
                    who == "76561198040410653" && fb, "who=" + who + " fallback=" + fb);
            }

            // 10. With witnesses it elects from the witnesses, not from the
            //     wider present set — the seat that never saw the game holds
            //     the lowest id here on purpose.
            {
                var present = new List<string> { "76561198000000001", "76561198040410653" };
                var witnesses = new List<string> { "76561198040410653" };
                string who = ElectReporter(present, witnesses, out bool fb);
                Check(r, "witnesses are the electorate",
                    who == "76561198040410653" && !fb, "who=" + who + " fallback=" + fb);
            }

            // 11. Every seat computes the same winner regardless of the order
            //     its own census produced.
            {
                var one = new List<string> { "76561198000000009", "76561198000000002", "76561198000000005" };
                var two = new List<string> { "76561198000000005", "76561198000000009", "76561198000000002" };
                string a = ElectReporter(one, null, out bool _);
                string b = ElectReporter(two, null, out bool _);
                Check(r, "election is order-independent", a == b && a == "76561198000000002",
                    "a=" + a + " b=" + b);
            }

            // 12. Nobody to elect is the only null, and the caller's own last
            //     resort covers it.
            {
                string who = ElectReporter(new List<string>(), new List<string>(), out bool fb);
                Check(r, "an empty room elects nobody", who == null && fb,
                    "who=" + (who ?? "(null)") + " fallback=" + fb);
            }

            // 13. A settled refusal is recognised from the code and from the
            //     formatted response alike, and a neighbouring code is not.
            {
                bool ok = IsSettledRefusal(409L)
                          && IsSettledRefusal("HTTP 409: Duplicate room id")
                          && !IsSettledRefusal(400L)
                          && !IsSettledRefusal("HTTP 4090: nope");
                Check(r, "a settled refusal is recognised, a neighbour is not", ok, "ok=" + ok);
            }

            // 14. TERMINAL vs RETRYABLE, as the hardened endpoint answers
            //     them. 409 (already recorded) and 403 (this tail is not the
            //     game the lobby expects, refused and captured) are both
            //     terminal at attempt 1; 503 is the server declining to
            //     decide and must stay retryable. A build that folded 503 in
            //     would silently turn a transient outage into lost results.
            {
                bool ok = IsTerminalRefusal(409L)
                          && IsTerminalRefusal(403L)
                          && IsTerminalRefusal("HTTP 403: report quarantined")
                          && !IsTerminalRefusal(RetryableRefusalStatus)
                          && !IsTerminalRefusal("HTTP 503: try again")
                          && !IsTerminalRefusal(500L)
                          && !IsTerminalRefusal("HTTP 4030: nope");
                Check(r, "409 and 403 are terminal, 503 is not", ok, "ok=" + ok);
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
