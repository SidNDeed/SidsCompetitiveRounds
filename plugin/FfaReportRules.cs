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

        /// <summary>A settled refusal, from the status code.</summary>
        internal static bool IsSettledRefusal(long statusCode)
        {
            return statusCode == SettledRefusalStatus;
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
            if (string.IsNullOrEmpty(response)) return false;
            string code = SettledRefusalStatus.ToString();
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
        /// seat reads from the same place. No local clock takes part.
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
        /// <paramref name="publishedGame"/> is preferred whenever it is
        /// present, INCLUDING when it is behind the local counter. A value
        /// every seat agrees on is the entire requirement here; being the
        /// larger number is not one. The local counter is the fallback for a
        /// seat that cannot read the property at all — the same residual shape
        /// as the election's own fallback, and the same reason: a key that
        /// cannot be computed is worse than one that might not match.</summary>
        internal static string ReportRoomId(string roomName, int publishedGame, int localGame)
        {
            int game = publishedGame >= 0 ? publishedGame : localGame;
            if (game < 0) game = 0;
            // Invariant formatting: a culture-specific rendering would make the
            // key seat-dependent again, which is the whole defect.
            return (roomName ?? "") + "_r"
                + game.ToString(System.Globalization.CultureInfo.InvariantCulture);
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

            // 1. THE FIX. Two seats holding different local game counters, both
            //    reading the host's published number, file under one key.
            {
                string a = ReportRoomId(room, 4, 4);
                string b = ReportRoomId(room, 4, 7);
                Check(r, "two seats agree on the key", a == b, "a=" + a + " b=" + b);
            }

            // 2. And the key is not a function of anything else: called twice
            //    with the same inputs it is the same string. (The old key read
            //    DateTime.UtcNow, which this shape cannot do.)
            {
                string a = ReportRoomId(room, 4, 4);
                string b = ReportRoomId(room, 4, 4);
                Check(r, "the key is a pure function of its inputs", a == b, "a=" + a + " b=" + b);
            }

            // 3. The published number wins even when it is BEHIND the local
            //    one. Agreement is the requirement; being larger is not.
            {
                string k = ReportRoomId(room, 2, 9);
                Check(r, "the published number wins when behind", k == room + "_r2", "k=" + k);
            }

            // 4. No published number: the local counter is the fallback, which
            //    is the residual mixed case and not an exception to it.
            {
                string k = ReportRoomId(room, -1, 5);
                Check(r, "absent published number falls back to local", k == room + "_r5", "k=" + k);
            }

            // 5. Two different games in one room never share a key.
            {
                Check(r, "different games get different keys",
                    ReportRoomId(room, 3, 3) != ReportRoomId(room, 4, 4),
                    ReportRoomId(room, 3, 3) + " vs " + ReportRoomId(room, 4, 4));
            }

            // 6. THE SERVER CONTRACT. The endpoint keys bet settlement on the
            //    number it pulls out of this string with an anchored _r(\d+)$.
            //    Tested against that regex, not against the format string.
            {
                var m = ServerGameSuffix.Match(ReportRoomId(room, 11, 3));
                Check(r, "the server can recover the game number",
                    m.Success && m.Groups[1].Value == "11",
                    "match=" + m.Success + " value=" + (m.Success ? m.Groups[1].Value : "-"));
            }

            // 7. ffa_matches.photon_room_id is VARCHAR(64). A key longer than
            //    that is a 500 on every report of that room.
            {
                string k = ReportRoomId(room, 999, 999);
                Check(r, "the key fits the column", k.Length <= 64, "len=" + k.Length + " k=" + k);
            }

            // 8. Degenerate inputs cannot throw or emit a negative suffix the
            //    server's regex would refuse.
            {
                string k = ReportRoomId(null, -1, -1);
                Check(r, "degenerate inputs still produce a legal key",
                    k == "_r0" && ServerGameSuffix.IsMatch(k), "k=" + k);
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
