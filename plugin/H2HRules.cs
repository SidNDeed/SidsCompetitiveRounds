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
        // ── queue-issued attestation binding (review r6 MEDIUM) ────────────

        internal enum IssuedOpponent { NotIssued, Attested, Suppressed }

        /// <summary>The queue's retained pairing names a PAIR, not a seat. It
        /// is bound to the first (H2HSummary incarnation, other-fighter actor)
        /// it is consumed for and answers Attested for that binding only; any
        /// other actor or incarnation in the room it was issued for is
        /// Suppressed — the caller shows no line, and never the peer's
        /// advertised id. NotIssued when the room is not the issued one (the
        /// room-code path, which keys on the advertised id); the binding is
        /// untouched then. The bound pair lives with ApiClient's issued pair,
        /// so a new issuance or a retire starts unbound.</summary>
        internal static IssuedOpponent ResolveIssued(bool issuedForRoom, ref int boundIncarnation, ref int boundActor,
                                                     int incarnation, int actor)
        {
            if (!issuedForRoom) return IssuedOpponent.NotIssued;
            if (boundActor < 0)
            {
                boundIncarnation = incarnation;
                boundActor = actor;
                return IssuedOpponent.Attested;
            }
            return boundIncarnation == incarnation && boundActor == actor
                ? IssuedOpponent.Attested
                : IssuedOpponent.Suppressed;
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

        internal const int SELFTEST_CASES = 28;

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
                // binding
                int bi = -1, ba = -1;
                Check("issued:not-issued", Bind(false, ref bi, ref ba, 3, 2), "NotIssued/-1/-1");
                Check("issued:first-bind", Bind(true, ref bi, ref ba, 3, 2), "Attested/3/2");
                Check("issued:same-actor", Bind(true, ref bi, ref ba, 3, 2), "Attested/3/2");
                Check("issued:other-actor", Bind(true, ref bi, ref ba, 3, 5), "Suppressed/3/2");
                Check("issued:original-after-other", Bind(true, ref bi, ref ba, 3, 2), "Attested/3/2");
                Check("issued:other-incarnation", Bind(true, ref bi, ref ba, 4, 2), "Suppressed/3/2");
                Check("issued:other-room-keeps-binding", Bind(false, ref bi, ref ba, 4, 9), "NotIssued/3/2");
                Check("control:issued:other-actor-attested", Bind(true, ref bi, ref ba, 3, 5), "Attested/3/2", control: true);

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

        private static string Bind(bool issued, ref int bi, ref int ba, int inc, int actor)
        {
            return ResolveIssued(issued, ref bi, ref ba, inc, actor) + "/" + bi + "/" + ba;
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
