using System;
using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>
    /// The decision rules behind H2HSummary, kept free of Unity, Photon,
    /// BepInEx and I18n so they run under a plain compiler: H2HSummary and
    /// ApiClient hand them what they read and act on what comes back. The
    /// [H2H] H2HRulesSelfTest lever (H2HSummary.EnsureStartup) runs SelfTest
    /// in-game; the same method runs under any console harness that compiles
    /// this one file. No catalogue string lives here — the strings stay at
    /// their I18n.Tr/TrF call sites in H2HSummary, where the extractor reads
    /// them (#464); this file only picks which one.
    /// </summary>
    internal static class H2HRules
    {
        // ── queue-issued attestation (review r6/r7 MEDIUM) ─────────────────

        internal enum IssuedOpponent { NotIssued, Attested, Pending, Suppressed }

        /// <summary>The pairing the queue retained for the room it issued, as
        /// ApiClient holds it: the lifecycle generation it was issued under,
        /// the room name it describes, the opponent the server paired this
        /// seat with, and the (H2HSummary incarnation, other-fighter actor)
        /// the pairing was first consumed for (BoundActor &lt; 0 until then).
        /// Plain ints and strings — nothing Unity, Photon or Steam.</summary>
        internal struct IssuedPairState
        {
            public int Gen;
            public string RoomName;
            public string OpponentSteamId;
            public int BoundIncarnation;
            public int BoundActor;
        }

        /// <summary>The whole queue-issued read, decided here so the self-test
        /// runs the same code the client does (review r7 LOW): ApiClient owns
        /// the record and the lifecycle counter and passes them in; every
        /// check, and the binding write-back, happen in this one place.
        ///
        /// pair: the retained pairing, null when this client holds none.
        /// currentGen: ApiClient's queue lifecycle counter now. roomName: the
        /// room this seat is in. advertisedId: the Steam id the other fighter's
        /// own game advertises (null/"" until its property arrives).
        /// incarnation/actor: H2HSummary's room incarnation and that fighter's
        /// Photon actor number.
        ///
        /// NotIssued for any room other than the one the pairing names — the
        /// caller keys on the advertised id there and the pairing is untouched.
        /// In the room the pairing names:
        /// • Suppressed once the queue lifecycle has moved on. The record is
        ///   KEPT, so the answer stays Suppressed for that room instead of
        ///   falling back to the advertised id (review r7 MEDIUM); it is
        ///   retired by a join to any other room.
        /// • Suppressed for any actor or incarnation other than the one the
        ///   pairing was bound to.
        /// • Pending while the other fighter advertises no id yet: nothing to
        ///   verify against, so no answer — the caller waits exactly as it
        ///   does for an ordinary room's not-yet-arrived id.
        /// • Suppressed when the id that fighter advertises is not the attested
        ///   one. The attestation VERIFIES the identity a fighter claims; it
        ///   never supplies one for a fighter who claims something else, or
        ///   nothing (review r7 MEDIUM).
        /// • Attested otherwise, and the first Attested answer binds the
        ///   pairing to that (incarnation, actor).
        /// attestedId is set on Attested only.</summary>
        internal static IssuedOpponent ConsultIssued(ref IssuedPairState? pair, int currentGen, string roomName,
                                                     string advertisedId, int incarnation, int actor,
                                                     out string attestedId)
        {
            attestedId = null;
            if (pair == null || string.IsNullOrEmpty(roomName)) return IssuedOpponent.NotIssued;
            var p = pair.Value;
            if (!string.Equals(p.RoomName ?? "", roomName, StringComparison.Ordinal)) return IssuedOpponent.NotIssued;
            if (p.Gen != currentGen) return IssuedOpponent.Suppressed;
            if (p.BoundActor >= 0 && (p.BoundIncarnation != incarnation || p.BoundActor != actor))
                return IssuedOpponent.Suppressed;
            if (string.IsNullOrEmpty(advertisedId)) return IssuedOpponent.Pending;
            if (!string.Equals(advertisedId, p.OpponentSteamId ?? "", StringComparison.Ordinal))
                return IssuedOpponent.Suppressed;
            if (p.BoundActor < 0)
            {
                p.BoundIncarnation = incarnation;
                p.BoundActor = actor;
                pair = p;   // the binding, written back (a nullable struct is a copy)
            }
            attestedId = p.OpponentSteamId;
            return IssuedOpponent.Attested;
        }

        // ── failure handling (review r6 LOW) ───────────────────────────────
        // The server debounces one accepted read per (caller, opponent) for
        // SERVER_DEBOUNCE_SECONDS (main.py _H2H_DEBOUNCE_SECONDS) and refuses
        // an echo inside it with 429 + retry_after. Every delay here sits
        // beyond that window: a re-send after an ambiguous transport failure
        // (the server may have accepted the first request and armed the
        // window) waits TRANSPORT_RETRY_DELAY, and a 429 is retried once
        // after retry_after + DEBOUNCE_RETRY_MARGIN when the body carries
        // one (DEBOUNCE_RETRY_MAX at most), DEBOUNCE_RETRY_FALLBACK otherwise.
        // test_h2h_summary.py pins the window and the delays against the
        // server's literal.
        internal const float SERVER_DEBOUNCE_SECONDS = 5f;
        internal const float TRANSPORT_RETRY_DELAY = 6f;
        internal const float DEBOUNCE_RETRY_FALLBACK = 6f;
        internal const float DEBOUNCE_RETRY_MARGIN = 1f;
        internal const float DEBOUNCE_RETRY_MAX = 10f;
        internal const int MAX_SESSION_RESENDS = 1;
        internal const int MAX_TRANSPORT_RETRIES = 1;
        internal const int MAX_DEBOUNCE_RETRIES = 1;

        internal enum FailureAction { ResendAfterNewSession, RetryAfterDelay, Unavailable }

        /// <summary>One unit per failure class, so a key sees at most
        /// 1 + MAX_SESSION_RESENDS + MAX_TRANSPORT_RETRIES + MAX_DEBOUNCE_RETRIES
        /// requests. Reset with the attempt (H2HSummary.ResetAttempt).</summary>
        internal struct RetryBudget
        {
            public int SessionResends;
            public int TransportRetries;
            public int DebounceRetries;
            public int Total => SessionResends + TransportRetries + DebounceRetries;
        }

        /// <summary>err is ApiClient's detailed error ("HTTP nnn: body", or a
        /// transport message with no status); retryAfterSeconds is the 429
        /// body's retry_after as the caller read it (0 when absent). delay is
        /// set for RetryAfterDelay only.</summary>
        internal static FailureAction OnFailure(string err, int retryAfterSeconds, ref RetryBudget budget, out float delay)
        {
            delay = 0f;
            err = err ?? "";
            if (err.StartsWith("HTTP 401", StringComparison.Ordinal))
            {
                if (budget.SessionResends >= MAX_SESSION_RESENDS) return FailureAction.Unavailable;
                budget.SessionResends++;
                return FailureAction.ResendAfterNewSession;
            }
            if (err.StartsWith("HTTP 429", StringComparison.Ordinal))
            {
                if (budget.DebounceRetries >= MAX_DEBOUNCE_RETRIES) return FailureAction.Unavailable;
                budget.DebounceRetries++;
                delay = retryAfterSeconds > 0
                    ? Math.Min(retryAfterSeconds + DEBOUNCE_RETRY_MARGIN, DEBOUNCE_RETRY_MAX)
                    : DEBOUNCE_RETRY_FALLBACK;
                return FailureAction.RetryAfterDelay;
            }
            if (err.StartsWith("HTTP ", StringComparison.Ordinal) || err == "outdated" || err == "no-consent")
                return FailureAction.Unavailable;
            // Transport failure or timeout: no status code at all.
            if (budget.TransportRetries >= MAX_TRANSPORT_RETRIES) return FailureAction.Unavailable;
            budget.TransportRetries++;
            delay = TRANSPORT_RETRY_DELAY;
            return FailureAction.RetryAfterDelay;
        }

        // ── relative-day copy (review r6 LOW) ──────────────────────────────

        /// <summary>The server's last_played_days_ago as ApiClient's int reader
        /// returns it (0 for absent or null): at least 1 is a day count;
        /// anything else means the response carried no server-computed
        /// distance, and the line then states no day at all.</summary>
        internal static int? DaysAgo(int raw) => raw >= 1 ? raw : (int?)null;

        internal enum AgoKind { Yesterday, Days, Weeks, Months, Year, Years }

        /// <summary>Which of H2HSummary.Ago's catalogue strings a day count
        /// takes; n is the number that string formats (0 for the two that
        /// format none).</summary>
        internal static AgoKind AgoBucket(int days, out int n)
        {
            n = 0;
            if (days <= 1) return AgoKind.Yesterday;
            if (days < 14) { n = days; return AgoKind.Days; }
            if (days < 60) { n = days / 7; return AgoKind.Weeks; }
            if (days < 365) { n = days / 30; return AgoKind.Months; }
            if (days < 730) return AgoKind.Year;
            n = days / 365;
            return AgoKind.Years;
        }

        internal enum LineShape { FirstTime, Plain, FirstPlayedToday, LastPlayed, LastPlayedAlsoToday }

        /// <summary>Which of H2HSummary.BuildLine's strings the facts select.
        /// noHistory: no counted game and no series at all. hasEarlierHistory:
        /// the server sent a last_played_at (a counted game before the
        /// caller's UTC day). daysAgo: its server-computed day count, null
        /// when the response carried none — then the line states no day
        /// (Plain) rather than one from the client's clock, and not "first
        /// played today" either, since there is earlier history.</summary>
        internal static LineShape ShapeFor(bool noHistory, bool hasEarlierHistory, int? daysAgo, bool playedToday)
        {
            if (noHistory) return LineShape.FirstTime;
            if (!hasEarlierHistory) return playedToday ? LineShape.FirstPlayedToday : LineShape.Plain;
            if (!daysAgo.HasValue) return LineShape.Plain;
            return playedToday ? LineShape.LastPlayedAlsoToday : LineShape.LastPlayed;
        }

        // ── self-test ──────────────────────────────────────────────────────

        internal const int SELFTEST_CASES = 36;

        /// <summary>Every rule above against canned inputs. A case marked
        /// control expects the WRONG answer and passes only when the harness
        /// reports a mismatch — proof the harness can fail. Logs one line per
        /// case and one summary line; returns the number of cases run, with
        /// the mismatches in fail. A run passes when run == SELFTEST_CASES
        /// and fail == 0.</summary>
        internal static int SelfTest(Action<string> log, out int fail)
        {
            int run = 0, failed = 0;
            void Check(string name, string got, string expected, bool control = false)
            {
                run++;
                bool ok = got == expected;
                if (control) ok = !ok;
                if (!ok) failed++;
                log?.Invoke("[H2H] selftest case=" + name + (control ? " (control)" : "")
                            + " expected=" + expected + " got=" + got + (ok ? " PASS" : " FAIL"));
            }

            try
            {
                // queue-issued attestation — the producer itself: one record,
                // consulted the way ApiClient consults it, so the binding
                // write-back and the lifecycle answer are under test too
                // (review r7 LOW). Rendered as verdict/attested-id/bound.
                const string OPP = "76561190000000001";
                const string OTHER = "76561190000000002";
                IssuedPairState? none = null;
                Check("issued:none-held", Consult(ref none, 7, "ranked_r", OPP, 3, 2), "NotIssued/-/none");
                IssuedPairState? pair = new IssuedPairState { Gen = 7, RoomName = "ranked_r", OpponentSteamId = OPP,
                                                             BoundIncarnation = -1, BoundActor = -1 };
                Check("issued:other-room", Consult(ref pair, 7, "code_room", OPP, 3, 2), "NotIssued/-/-1/-1");
                Check("issued:no-advertised-id", Consult(ref pair, 7, "ranked_r", "", 3, 2), "Pending/-/-1/-1");
                Check("issued:advertised-mismatch", Consult(ref pair, 7, "ranked_r", OTHER, 3, 2), "Suppressed/-/-1/-1");
                Check("issued:verified-first-bind", Consult(ref pair, 7, "ranked_r", OPP, 3, 2), "Attested/" + OPP + "/3/2");
                Check("issued:same-actor-again", Consult(ref pair, 7, "ranked_r", OPP, 3, 2), "Attested/" + OPP + "/3/2");
                Check("issued:other-actor", Consult(ref pair, 7, "ranked_r", OPP, 3, 5), "Suppressed/-/3/2");
                Check("issued:other-incarnation", Consult(ref pair, 7, "ranked_r", OPP, 4, 2), "Suppressed/-/3/2");
                Check("issued:bound-actor-changes-id", Consult(ref pair, 7, "ranked_r", OTHER, 3, 2), "Suppressed/-/3/2");
                Check("issued:bound-actor-drops-id", Consult(ref pair, 7, "ranked_r", "", 3, 2), "Pending/-/3/2");
                Check("issued:original-after-other", Consult(ref pair, 7, "ranked_r", OPP, 3, 2), "Attested/" + OPP + "/3/2");
                Check("issued:lifecycle-moved-suppresses", Consult(ref pair, 8, "ranked_r", OPP, 3, 2), "Suppressed/-/3/2");
                Check("issued:lifecycle-moved-stays-suppressed", Consult(ref pair, 8, "ranked_r", OPP, 3, 2), "Suppressed/-/3/2");
                Check("issued:other-room-keeps-record", Consult(ref pair, 8, "code_room", OPP, 9, 9), "NotIssued/-/3/2");
                Check("control:issued:mismatch-attested", Consult(ref pair, 7, "ranked_r", OTHER, 3, 2),
                      "Attested/" + OPP + "/3/2", control: true);
                Check("control:issued:lifecycle-not-issued", Consult(ref pair, 8, "ranked_r", OPP, 3, 2),
                      "NotIssued/-/3/2", control: true);

                // failures
                var b = new RetryBudget();
                Check("retry:401-once", Describe("HTTP 401: {\"detail\":\"session_required\"}", 0, ref b), "ResendAfterNewSession/0");
                Check("retry:401-twice", Describe("HTTP 401: x", 0, ref b), "Unavailable/0");
                b = new RetryBudget();
                Check("retry:transport-once", Describe("Cannot connect to destination host", 0, ref b), "RetryAfterDelay/6");
                Check("retry:transport-delay-beyond-window", (TRANSPORT_RETRY_DELAY > SERVER_DEBOUNCE_SECONDS).ToString(), "True");
                Check("retry:transport-twice", Describe("Request timeout", 0, ref b), "Unavailable/0");
                b = new RetryBudget();
                Check("retry:429-with-retry-after", Describe("HTTP 429: {\"detail\":{\"error\":\"rate_debounced\",\"retry_after\":3}}", 3, ref b), "RetryAfterDelay/4");
                Check("retry:429-twice", Describe("HTTP 429: x", 3, ref b), "Unavailable/0");
                b = new RetryBudget();
                Check("retry:429-without-retry-after", Describe("HTTP 429: ", 0, ref b), "RetryAfterDelay/6");
                Check("retry:429-fallback-beyond-window", (DEBOUNCE_RETRY_FALLBACK > SERVER_DEBOUNCE_SECONDS).ToString(), "True");
                b = new RetryBudget();
                Check("retry:429-bogus-retry-after-capped", Describe("HTTP 429: x", 999, ref b), "RetryAfterDelay/10");
                b = new RetryBudget();
                Check("retry:other-http",
                      Describe("HTTP 500: x", 0, ref b) + "|" + Describe("HTTP 400: x", 0, ref b) + "|" + Describe("HTTP 403: x", 0, ref b),
                      "Unavailable/0|Unavailable/0|Unavailable/0");
                Check("retry:outdated-no-consent", Describe("outdated", 0, ref b) + "|" + Describe("no-consent", 0, ref b), "Unavailable/0|Unavailable/0");
                b = new RetryBudget();
                Check("retry:each-class-once",
                      Describe("timeout", 0, ref b) + "|" + Describe("HTTP 401: x", 0, ref b) + "|" + Describe("HTTP 429: x", 2, ref b) + "|" + b.Total,
                      "RetryAfterDelay/6|ResendAfterNewSession/0|RetryAfterDelay/3|3");
                Check("retry:bounded-after-budget",
                      Describe("timeout", 0, ref b) + "|" + Describe("HTTP 401: x", 0, ref b) + "|" + Describe("HTTP 429: x", 2, ref b) + "|" + b.Total,
                      "Unavailable/0|Unavailable/0|Unavailable/0|3");
                Check("retry:max-requests-per-key", (1 + MAX_SESSION_RESENDS + MAX_TRANSPORT_RETRIES + MAX_DEBOUNCE_RETRIES).ToString(), "4");
                b = new RetryBudget();
                Check("control:retry:429-permanent", Describe("HTTP 429: x", 2, ref b), "Unavailable/0", control: true);

                // relative day
                Check("days:raw", Str(DaysAgo(0)) + "|" + Str(DaysAgo(-3)) + "|" + Str(DaysAgo(1)) + "|" + Str(DaysAgo(400)), "null|null|1|400");
                Check("days:buckets", Buckets(1, 2, 13, 14, 20, 59, 60, 364, 365, 729, 730, 1500),
                      "Yesterday|Days2|Days13|Weeks2|Weeks2|Weeks8|Months2|Months12|Year|Year|Years2|Years4");
                Check("days:shape",
                      ShapeFor(true, false, null, false) + "|" + ShapeFor(false, false, null, false) + "|"
                      + ShapeFor(false, false, null, true) + "|" + ShapeFor(false, true, 3, false) + "|"
                      + ShapeFor(false, true, 3, true) + "|" + ShapeFor(false, true, null, true) + "|"
                      + ShapeFor(false, true, null, false),
                      "FirstTime|Plain|FirstPlayedToday|LastPlayed|LastPlayedAlsoToday|Plain|Plain");
                Check("control:days:zero-is-a-day", Str(DaysAgo(0)), "0", control: true);
            }
            catch (Exception ex)
            {
                failed++;
                log?.Invoke("[H2H] selftest harness failed: " + ex.GetType().Name + ": " + ex.Message);
            }

            fail = failed;
            bool all = run == SELFTEST_CASES && fail == 0;
            log?.Invoke("[H2H] selftest summary run=" + run + " expected=" + SELFTEST_CASES + " fail=" + fail + (all ? " PASS" : " FAIL"));
            return run;
        }

        /// <summary>verdict/attested-id/binding, where the binding is the
        /// record's own BoundIncarnation/BoundActor after the call ("none"
        /// when no record is held) — so a case reads the write-back, not just
        /// the return value.</summary>
        private static string Consult(ref IssuedPairState? pair, int gen, string room, string advertised, int inc, int actor)
        {
            string id;
            var verdict = ConsultIssued(ref pair, gen, room, advertised, inc, actor, out id);
            return verdict + "/" + (id ?? "-") + "/"
                   + (pair.HasValue ? pair.Value.BoundIncarnation + "/" + pair.Value.BoundActor : "none");
        }

        private static string Describe(string err, int retryAfter, ref RetryBudget b)
        {
            float d;
            var a = OnFailure(err, retryAfter, ref b, out d);
            return a + "/" + d.ToString(CultureInfo.InvariantCulture);
        }

        private static string Str(int? v) => v.HasValue ? v.Value.ToString(CultureInfo.InvariantCulture) : "null";

        private static string Buckets(params int[] days)
        {
            var parts = new string[days.Length];
            for (int i = 0; i < days.Length; i++)
            {
                int n;
                var k = AgoBucket(days[i], out n);
                parts[i] = k + (n > 0 ? n.ToString(CultureInfo.InvariantCulture) : "");
            }
            return string.Join("|", parts);
        }
    }
}
