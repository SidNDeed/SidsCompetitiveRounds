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
        /// the pairing was first consumed for (BoundActor &lt; 0 until then),
        /// and the incarnation of the join that first matched its room name
        /// (JoinIncarnation &lt; 0 until then — review r8 LOW 1).
        /// Plain ints and strings — nothing Unity, Photon or Steam.</summary>
        internal struct IssuedPairState
        {
            public int Gen;
            public string RoomName;
            public string OpponentSteamId;
            public int BoundIncarnation;
            public int BoundActor;
            public int JoinIncarnation;
        }

        /// <summary>What a join does to the retained pairing (review r8
        /// LOW 1). A room NAME does not identify a room — code rooms are
        /// player-typed and reusable, and ApiClient keeps a whole incarnation
        /// counter for exactly that reason — so "the name still matches"
        /// cannot be the rule that keeps a pairing alive across joins. The
        /// pairing describes ONE join to the room it names: the first join
        /// whose name matches stamps its incarnation, and any later join,
        /// same name or not, retires it. Returns true when the record was
        /// retired.</summary>
        internal static bool RetireOnJoin(ref IssuedPairState? pair, string roomName, int incarnation)
        {
            if (pair == null) return false;
            var p = pair.Value;
            if (!string.Equals(p.RoomName ?? "", roomName ?? "", StringComparison.Ordinal))
            {
                pair = null;
                return true;
            }
            if (p.JoinIncarnation < 0)
            {
                p.JoinIncarnation = incarnation;
                pair = p;
                return false;
            }
            if (p.JoinIncarnation == incarnation) return false;
            pair = null;
            return true;
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
        /// WHAT THIS DECIDES, EXACTLY (review r8 MEDIUM 1). advertisedId is a
        /// Photon custom property the other fighter's OWN game writes, and
        /// nothing here — or anywhere on this client — can bind a Photon actor
        /// to a Steam identity: the queue tells this seat WHO it was paired
        /// with, never WHICH ACTOR that is. So this is an AGREEMENT check
        /// between the peer's claim and the server's pairing, not an
        /// authentication of the peer. A fighter whose game claims the paired
        /// id is taken at its word here exactly as it is in an ordinary room,
        /// where the advertised id is all there is. What the check buys is
        /// only ever LESS shown, never more: a claim that disagrees with the
        /// pairing, a later actor, and a moved-on lifecycle each produce no
        /// line at all, where the ordinary path would show a line for whoever
        /// the claim named.
        ///
        /// supersededRoom (review r8 MEDIUM 2): a room this seat may still be
        /// sitting in whose issued pairing a LATER issuance has already
        /// replaced. One record describes one room, so the replacement leaves
        /// the occupied room with no pairing of its own — and a bare room-name
        /// mismatch would read as NotIssued and release the line to the
        /// advertised id, in the one room that was supposed to be attested.
        /// It suppresses instead, until the leave edge clears it.
        ///
        /// ONE room is remembered, not every superseded room (review r10). The
        /// caller decides which: a later supersession may take the slot only
        /// from a room this seat has already left, so the room the seat is IN
        /// keeps its tombstone for as long as it is occupied. Nothing here
        /// promises anything about a third room.
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
        /// • Suppressed when the id that fighter advertises is not the paired
        ///   one. The pairing is never handed out as a fighter's identity: it
        ///   is only ever compared with the claim that fighter's own game
        ///   makes, and a fighter who claims something else, or nothing, gets
        ///   no line rather than the paired player's name and record (review
        ///   r7 MEDIUM).
        /// • Attested otherwise, and the first Attested answer binds the
        ///   pairing to that (incarnation, actor).
        /// attestedId is set on Attested only.</summary>
        internal static IssuedOpponent ConsultIssued(ref IssuedPairState? pair, string supersededRoom,
                                                     int currentGen, string roomName,
                                                     string advertisedId, int incarnation, int actor,
                                                     out string attestedId)
        {
            attestedId = null;
            if (string.IsNullOrEmpty(roomName)) return IssuedOpponent.NotIssued;
            // Before the record, because a later issuance may have replaced or
            // emptied it entirely: this room's pairing is gone, and gone is not
            // the same as never issued.
            if (string.Equals(supersededRoom ?? "", roomName, StringComparison.Ordinal))
                return IssuedOpponent.Suppressed;
            if (pair == null) return IssuedOpponent.NotIssued;
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

        // ── per-room request budget (review r8 MEDIUM 3) ───────────────────

        /// <summary>The most reads one room incarnation may ask for, however
        /// many times the opponent key changes inside it. A key change IS a
        /// legitimate new question — a replacement fighter is a different
        /// opponent — but the key is built from a property the peer's own game
        /// publishes, so the number of key changes is not ours to bound, and
        /// without this neither is the number of requests. The read shares one
        /// per-IP rate bucket with every other sensitive endpoint, the
        /// disconnect report among them, and that write is one-shot: a room
        /// that keeps asking spends a budget another player's record needs.
        /// One key's whole retry ladder fits inside this (a self-test case
        /// pins it), which is all an ordinary room ever uses.</summary>
        internal const int MAX_REQUESTS_PER_ROOM = 6;

        /// <summary>Least time between two reads under one incarnation.
        ///
        /// The delays this file CHOOSES are longer than it — TRANSPORT_RETRY_DELAY
        /// and DEBOUNCE_RETRY_FALLBACK both clear the server's 5 s window — so
        /// for those it constrains key churn only. A 429 retry is the
        /// exception, and it is the exception because that delay is not ours:
        /// it is the server's retry_after plus DEBOUNCE_RETRY_MARGIN, and a
        /// retry_after of 1 schedules the re-send 2 s out, inside this. Then
        /// the retry waits for the spacing and goes on the first admissible
        /// tick, because TooSoon is not a refusal — later than asked, never
        /// dropped.</summary>
        internal const float MIN_REQUEST_SPACING_SECONDS = 3f;

        /// <summary>Reads spent under one room incarnation, and when the last
        /// went out. H2HSummary holds this ACROSS key changes and resets it
        /// with the incarnation — that is the whole mechanism; a reset on the
        /// key would restore exactly the unbounded behaviour.</summary>
        internal struct RoomBudget
        {
            public int Requests;
            public float LastSentAt;
        }

        internal enum RoomGate { Send, TooSoon, Exhausted }

        /// <summary>Admit one read under the room budget AND record it in the
        /// same call, so a caller cannot ask without paying. now is a
        /// monotonic seconds clock (Time.realtimeSinceStartup). TooSoon is not
        /// a refusal — the caller asks again on a later tick; Exhausted ends
        /// the reads for this incarnation.</summary>
        internal static RoomGate AdmitRoomRequest(ref RoomBudget budget, float now)
        {
            if (budget.Requests >= MAX_REQUESTS_PER_ROOM) return RoomGate.Exhausted;
            if (budget.Requests > 0 && now - budget.LastSentAt < MIN_REQUEST_SPACING_SECONDS)
                return RoomGate.TooSoon;
            budget.Requests++;
            budget.LastSentAt = now;
            return RoomGate.Send;
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

        internal const int SELFTEST_CASES = 52;

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

                // a room NAME is not a room INCARNATION (review r8 LOW 1)
                IssuedPairState? rejoin = new IssuedPairState { Gen = 7, RoomName = "code_room", OpponentSteamId = OPP,
                                                                BoundIncarnation = -1, BoundActor = -1, JoinIncarnation = -1 };
                Check("rejoin:first-join-stamps", Retire(ref rejoin, "code_room", 4), "kept/4");
                Check("rejoin:same-join-again", Retire(ref rejoin, "code_room", 4), "kept/4");
                Check("rejoin:same-name-later-join-retires", Retire(ref rejoin, "code_room", 9), "retired");
                IssuedPairState? elsewhere = new IssuedPairState { Gen = 7, RoomName = "code_room", OpponentSteamId = OPP,
                                                                   BoundIncarnation = -1, BoundActor = -1, JoinIncarnation = -1 };
                Check("rejoin:another-room-retires", Retire(ref elsewhere, "other_room", 4), "retired");
                IssuedPairState? ctl = new IssuedPairState { Gen = 7, RoomName = "code_room", OpponentSteamId = OPP,
                                                             BoundIncarnation = -1, BoundActor = -1, JoinIncarnation = 4 };
                Check("control:rejoin:name-alone-keeps-it", Retire(ref ctl, "code_room", 9), "kept/4", control: true);

                // a later issuance replaced the pairing of a room this seat
                // may still be in (review r8 MEDIUM 2)
                IssuedPairState? next = new IssuedPairState { Gen = 7, RoomName = "ranked_next", OpponentSteamId = OPP,
                                                              BoundIncarnation = -1, BoundActor = -1 };
                Check("superseded:occupied-room-suppressed", Consult(ref next, 7, "ranked_r", OPP, 3, 2, "ranked_r"),
                      "Suppressed/-/-1/-1");
                Check("superseded:survives-an-emptied-record",
                      Consult(ref none, 7, "ranked_r", OPP, 3, 2, "ranked_r"), "Suppressed/-/none");
                Check("superseded:the-new-room-still-answers", Consult(ref next, 7, "ranked_next", OPP, 3, 2, "ranked_r"),
                      "Attested/" + OPP + "/3/2");
                Check("control:superseded:released-to-advertised",
                      Consult(ref none, 7, "ranked_r", OPP, 3, 2, "ranked_r"), "NotIssued/-/none", control: true);

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

                // per-room request budget
                var rb = new RoomBudget();
                Check("room:first-admitted", Room(ref rb, 100f), "Send/1");
                Check("room:second-too-soon", Room(ref rb, 101f), "TooSoon/1");
                Check("room:after-spacing", Room(ref rb, 103f), "Send/2");
                Check("room:cap-exhausts",
                      Room(ref rb, 200f) + "|" + Room(ref rb, 300f) + "|" + Room(ref rb, 400f) + "|" + Room(ref rb, 500f),
                      "Send/3|Send/4|Send/5|Send/6");
                Check("room:exhausted-stays", Room(ref rb, 600f), "Exhausted/6");
                Check("room:cap-fits-one-keys-ladder",
                      (MAX_REQUESTS_PER_ROOM >= 1 + MAX_SESSION_RESENDS + MAX_TRANSPORT_RETRIES + MAX_DEBOUNCE_RETRIES).ToString(),
                      "True");
                Check("control:room:cap-not-enforced", Room(ref rb, 700f), "Send/7", control: true);

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
        private static string Consult(ref IssuedPairState? pair, int gen, string room, string advertised, int inc, int actor,
                                      string supersededRoom = null)
        {
            string id;
            var verdict = ConsultIssued(ref pair, supersededRoom, gen, room, advertised, inc, actor, out id);
            return verdict + "/" + (id ?? "-") + "/"
                   + (pair.HasValue ? pair.Value.BoundIncarnation + "/" + pair.Value.BoundActor : "none");
        }

        /// <summary>"retired", or "kept/" the join incarnation the record
        /// now carries — a case reads the stamp, not just the verdict.</summary>
        private static string Retire(ref IssuedPairState? pair, string room, int incarnation)
        {
            if (RetireOnJoin(ref pair, room, incarnation)) return "retired";
            return "kept/" + (pair.HasValue ? pair.Value.JoinIncarnation.ToString(CultureInfo.InvariantCulture) : "none");
        }

        /// <summary>gate/requests-spent after the call — a case reads the
        /// budget the admission wrote, not just its answer.</summary>
        private static string Room(ref RoomBudget b, float now)
        {
            var gate = AdmitRoomRequest(ref b, now);
            return gate + "/" + b.Requests.ToString(CultureInfo.InvariantCulture);
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
