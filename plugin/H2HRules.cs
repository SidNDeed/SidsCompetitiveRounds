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

        /// <summary>The series id the queue published, bound to the ONE room
        /// occupancy it describes rather than to a room NAME (r13 HIGH).
        ///
        /// The name was the whole binding: the id was filed under the room it
        /// was published for, and any later occupancy of a room by that name
        /// answered to it. Room names are reusable -- code rooms are
        /// player-typed, ranked names recur -- so a pairing whose join failed
        /// could leave its id standing, and the next occupancy of that name,
        /// with a different opponent, would file its score against it. The
        /// pairing record beside this one has drawn that distinction since r8;
        /// this one had not.
        ///
        /// JoinIncarnation &lt; 0 means the id was published (at both_ready,
        /// which is BEFORE the seat has joined anything) and no join has
        /// matched it yet -- a staged id, not a played one. OpponentSteamId is
        /// the pairing the queue issued for that room where the queue knew it,
        /// and empty where it did not; empty is permissive, because the seat
        /// filing a leave report is by definition looking at a room the
        /// opponent has left.</summary>
        internal struct RoomBoundSeries
        {
            public string SeriesId;
            public string RoomName;
            public string OpponentSteamId;
            public int JoinIncarnation;
        }

        /// <summary>Same rule as RetireOnJoin, for the series record: the first
        /// join whose name matches stamps its incarnation, and any later join
        /// -- same name or not -- retires the record. Returns true when it
        /// was retired.</summary>
        private static bool RetireSeriesOnJoin(ref RoomBoundSeries? bound, string roomName, int incarnation)
        {
            if (bound == null) return false;
            var b = bound.Value;
            if (!string.Equals(b.RoomName ?? "", roomName ?? "", StringComparison.Ordinal))
            {
                bound = null;
                return true;
            }
            if (b.JoinIncarnation < 0)
            {
                b.JoinIncarnation = incarnation;
                bound = b;
                return false;
            }
            if (b.JoinIncarnation == incarnation) return false;
            bound = null;
            return true;
        }

        /// <summary>Publication, as its own transition rather than a record
        /// the caller assembles.
        ///
        /// A series id is published at both_ready, from the menu, for a room
        /// this seat has not joined -- that is the queue case, and it stages
        /// the record for the join to stamp. It is ALSO published by a
        /// preflight, and a preflight runs from INSIDE the room it is about:
        /// private and tournament rooms, and every game after the first.
        /// Staging those was a live regression (r14 HIGH) -- no further join
        /// is coming to stamp them, so the record answered "" for the rest of
        /// the room and took live points, named disconnect reports and
        /// attestations with it. A publication naming the room this seat is
        /// already in describes THIS occupancy and is stamped with it.</summary>
        private static void PublishSeries(ref RoomBoundSeries? bound, string seriesId, string room,
                                           string opponent, bool inRoomHere, string roomHere,
                                           int incarnation)
        {
            if (string.IsNullOrEmpty(seriesId))
            {
                bound = null;
                return;
            }
            bool alreadyHere = inRoomHere
                               && !string.IsNullOrEmpty(roomHere)
                               && string.Equals(roomHere, room ?? "", StringComparison.Ordinal);
            bound = new RoomBoundSeries
            {
                SeriesId = seriesId,
                RoomName = room ?? "",
                OpponentSteamId = opponent ?? "",
                JoinIncarnation = alreadyHere ? incarnation : -1,
            };
        }

        /// <summary>The queue's pairing for the room, arriving AFTER the id
        /// was published for it.
        ///
        /// Both queue paths publish the series id from the response and
        /// retain the pairing from the same response a few statements later,
        /// so a publication that reads the pairing gets the PREVIOUS one or
        /// none (r14 HIGH): the record was built with an empty opponent, and
        /// an empty opponent is the permissive value, so the one term that
        /// could tell two occupancies of a recurring room name apart was
        /// never populated on the path that had the answer. Retention is the
        /// second half of publication, not a caller's bookkeeping.
        ///
        /// Only a pairing for the room the record already names binds; a
        /// pairing for anywhere else says nothing about this record, and the
        /// join is what retires it. Returns true when the record took it.</summary>
        private static bool RetainSeriesPairing(ref RoomBoundSeries? bound, string room, string opponent)
        {
            if (bound == null) return false;
            if (string.IsNullOrEmpty(opponent)) return false;
            var b = bound.Value;
            if (!string.Equals(b.RoomName ?? "", room ?? "", StringComparison.Ordinal)) return false;
            b.OpponentSteamId = opponent;
            bound = b;
            return true;
        }

        /// <summary>The series id an observation made HERE may be filed under,
        /// or empty. Empty is a real answer and not a failure: it makes the
        /// report a single unnamed attempt, which the server resolves from the
        /// pair.
        ///
        /// Every term is a way the id could belong to something else: no
        /// record; not in a room to compare against; a different room; a room
        /// of the same name this seat has not joined (a staged id); a
        /// different occupancy of that same name; or the same name with the
        /// queue's pairing for it replaced. An unknown opponent is permissive
        /// on purpose -- the seat reporting a leave is looking at a room the
        /// opponent has already left, and the incarnation is what carries the
        /// weight there.</summary>
        internal static string SeriesForRoom(RoomBoundSeries? bound, bool inRoom, string roomHere,
                                             int incarnation, string opponentHere)
        {
            if (bound == null) return "";
            var b = bound.Value;
            if (string.IsNullOrEmpty(b.SeriesId)) return "";
            if (!inRoom) return "";
            if (string.IsNullOrEmpty(roomHere)) return "";
            if (!string.Equals(b.RoomName ?? "", roomHere, StringComparison.Ordinal)) return "";
            if (b.JoinIncarnation < 0) return "";
            if (b.JoinIncarnation != incarnation) return "";
            if (!string.IsNullOrEmpty(opponentHere) && !string.IsNullOrEmpty(b.OpponentSteamId)
                && !string.Equals(b.OpponentSteamId, opponentHere, StringComparison.Ordinal))
                return "";
            return b.SeriesId;
        }

        /// <summary>TRUE only with positive evidence that the held id is not
        /// this room's. Used where an empty answer would cost ranked routing
        /// rather than protect a series, so "no evidence" reads as FALSE.
        ///
        /// The incarnation is checked BEFORE the in-room question, and that
        /// ordering is the point: a leave that never produced Photon's own
        /// callback leaves this seat believing it is nowhere, and the previous
        /// rule read that as "nothing to compare against, not contradicted"
        /// and kept the id. A join stamp that no longer matches the current
        /// incarnation is evidence on its own -- the occupancy the id
        /// describes is over, whatever this seat thinks it is in now.</summary>
        internal static bool SeriesContradictedByRoom(RoomBoundSeries? bound, bool inRoom, string roomHere,
                                                      int incarnation, string opponentHere)
        {
            if (bound == null) return false;
            var b = bound.Value;
            if (string.IsNullOrEmpty(b.SeriesId)) return false;
            if (b.JoinIncarnation >= 0 && b.JoinIncarnation != incarnation) return true;
            if (!inRoom) return false;
            if (string.IsNullOrEmpty(roomHere)) return false;
            if (!string.Equals(b.RoomName ?? "", roomHere, StringComparison.Ordinal)) return true;
            if (!string.IsNullOrEmpty(opponentHere) && !string.IsNullOrEmpty(b.OpponentSteamId)
                && !string.Equals(b.OpponentSteamId, opponentHere, StringComparison.Ordinal))
                return true;
            return false;
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
        private static bool RetireOnJoin(ref IssuedPairState? pair, string roomName, int incarnation)
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

        // ── the room session ───────────────────────────────────────────────

        /// <summary>Everything that describes ONE occupancy of ONE room, in a
        /// single value the self-test can drive through a real sequence.
        ///
        /// These five pieces lived as separate statics on two Unity classes,
        /// and the ORDER their transitions run in was a property of two call
        /// sites forty-one lines apart in Plugin.OnJoinedRoom with nothing
        /// gating the gap. r14 HIGH was exactly that gap: the series record
        /// was stamped from inside the pairing's retirement, with the PAIR
        /// counter, before the series counter had been bumped -- so the stamp
        /// could never equal the value its readers compare it against. The
        /// repair moved the stamp; it did not make the ordering executable,
        /// and a test that hand-builds a consistent record cannot see an
        /// ordering fault at all (r14 LOW 1).
        ///
        /// The two counters stay SEPARATE fields on purpose. What r14 HIGH
        /// forbids is deciding both records from one counter; two named fields
        /// in one struct keep the split and make it inspectable, which is the
        /// opposite of collapsing them.</summary>
        internal struct RoomSessionState
        {
            /// <summary>The series record for this occupancy.</summary>
            public RoomBoundSeries? Bound;
            /// <summary>The occupancy counter the SERIES record is read
            /// against. Bumped by the two reliable Photon room edges.</summary>
            public int Incarnation;
            /// <summary>The queue's attested pairing for the room.</summary>
            public IssuedPairState? IssuedPair;
            /// <summary>The occupancy counter the head-to-head LINE is read
            /// against. A different question with a different lifetime, so a
            /// different counter.</summary>
            public int PairIncarnation;
            /// <summary>The room whose issued pairing a later issuance
            /// replaced while this seat may still be sitting in it.</summary>
            public string SupersededIssuedRoom;
            /// <summary>The incarnation a POLLED exit was last observed in.
            /// Recorded rather than acted on: the polled edge is the lossy
            /// backup for the reliable callback, so it must be distinguishable
            /// from it by something a test can read. Without this the two exit
            /// entry points had identical bodies and calling the wrong one was
            /// invisible.</summary>
            public int ExitObservedAt;
        }

        /// <summary>The room session's transitions, one method per EVENT.
        ///
        /// Each method is the whole ordering for its event, so a caller cannot
        /// perform half of one. The fine-grained steps below are private for
        /// the same reason: outside this type an out-of-order sequence stops
        /// being a test failure and becomes something that will not compile.</summary>
        internal static class RoomSession
        {
            /// <summary>A join, in the order the two records require.
            ///
            /// `roomNameKnown` is false when the caller could not read the
            /// room's name -- Photon threw, or the room was gone by the time
            /// it looked. Both counters still move, because we joined
            /// SOMETHING and every record describing the previous occupancy is
            /// now stale; the series binding is then dropped rather than
            /// stamped, because we cannot prove this is the room it was
            /// published for. That is the conservative direction: an unnamed
            /// report the server resolves from the pair, rather than a report
            /// filed against a series this seat may no longer be in.
            ///
            /// The caller must read the room name into a local BEFORE calling
            /// this. An expression that touches Photon inside this call's
            /// argument list would mean a throw skips the bumps too, which
            /// leaves the previous occupancy's records standing -- the unsafe
            /// direction.</summary>
            internal static void OnRoomJoined(ref RoomSessionState s, string roomName, bool roomNameKnown)
            {
                s.PairIncarnation++;
                // A join anywhere but the superseded room means we are no
                // longer in it; a join BACK to it keeps the tombstone,
                // because its pairing is still the one that was replaced.
                if (!string.IsNullOrEmpty(s.SupersededIssuedRoom)
                    && !string.Equals(s.SupersededIssuedRoom, roomName ?? "", StringComparison.Ordinal))
                    s.SupersededIssuedRoom = null;
                RetireOnJoin(ref s.IssuedPair, roomName, s.PairIncarnation);
                s.Incarnation++;
                if (!roomNameKnown)
                {
                    s.Bound = null;
                    return;
                }
                RetireSeriesOnJoin(ref s.Bound, roomName, s.Incarnation);
            }

            /// <summary>Photon's own OnLeftRoom / OnDisconnected: the edge that
            /// cannot be missed the way a 10 Hz poll can.</summary>
            internal static void OnRoomLeftReliableEdge(ref RoomSessionState s)
            {
                s.PairIncarnation++;
                s.SupersededIssuedRoom = null;
                s.Incarnation++;
                s.Bound = null;
            }

            /// <summary>The polled exit: the lossy backup for the callback
            /// above. It clears the room-bound series id, which the documented
            /// casual-to-ranked flow relies on, but it moves NO counter -- a
            /// poll observing an exit the callback already handled must not
            /// retire a fresh occupancy the callback has since opened.</summary>
            internal static void OnRoomExitPolled(ref RoomSessionState s)
            {
                s.ExitObservedAt = s.Incarnation;
                s.Bound = null;
            }

            /// <summary>A series id published for a room, staged or current.
            /// Reads the issued pairing out of the session itself, so there is
            /// no argument a caller can pass as null.</summary>
            internal static void OnSeriesPublished(ref RoomSessionState s, string seriesId, string room,
                                                   bool inRoomHere, string roomHere)
            {
                string opponent = s.IssuedPair != null
                                  && string.Equals(s.IssuedPair.Value.RoomName ?? "", room ?? "",
                                                   StringComparison.Ordinal)
                                  ? s.IssuedPair.Value.OpponentSteamId
                                  : "";
                PublishSeries(ref s.Bound, seriesId, room, opponent, inRoomHere, roomHere, s.Incarnation);
            }

            /// <summary>The queue's pairing for the room, arriving after the
            /// id was published for it.</summary>
            internal static bool OnSeriesPairingRetained(ref RoomSessionState s, string room, string opponent)
            {
                return RetainSeriesPairing(ref s.Bound, room, opponent);
            }

            /// <summary>The series is over; the record stops answering.</summary>
            internal static void OnSeriesEnded(ref RoomSessionState s)
            {
                s.Bound = null;
            }

            /// <summary>The head-to-head line's own invalidation.</summary>
            internal static void OnPairInvalidated(ref RoomSessionState s)
            {
                s.PairIncarnation++;
                s.SupersededIssuedRoom = null;
            }

            /// <summary>The series id an observation made HERE may be filed
            /// under, or empty.</summary>
            internal static string SeriesHere(RoomSessionState s, bool inRoom, string roomHere,
                                              string opponentHere)
            {
                return SeriesForRoom(s.Bound, inRoom, roomHere, s.Incarnation, opponentHere);
            }

            /// <summary>Positive evidence that the held id is not this
            /// room's.</summary>
            internal static bool ContradictedHere(RoomSessionState s, bool inRoom, string roomHere,
                                                  string opponentHere)
            {
                return SeriesContradictedByRoom(s.Bound, inRoom, roomHere, s.Incarnation, opponentHere);
            }

            /// <summary>One line describing the session, for the self-test:
            /// the bound id, the stamp it carries, and the two counters.</summary>
            internal static string Render(RoomSessionState s)
            {
                string id = s.Bound == null || string.IsNullOrEmpty(s.Bound.Value.SeriesId)
                            ? "-" : s.Bound.Value.SeriesId;
                string stamp = s.Bound == null ? "none"
                               : (s.Bound.Value.JoinIncarnation < 0 ? "staged"
                                  : s.Bound.Value.JoinIncarnation.ToString());
                return id + "/" + stamp + "@" + s.Incarnation + "/p" + s.PairIncarnation;
            }
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
        /// it is the server's retry_after plus DEBOUNCE_RETRY_MARGIN, and the
        /// smallest retry_after the endpoint hands out schedules the re-send
        /// inside this (a test reads both numbers from the source and pins
        /// it, so the sentence cannot rot when either constant moves). Then
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

        /// The number of cases the self-test is supposed to run. It is a
        /// tripwire, not a result: it catches a case that stopped running
        /// (an early return, a case commented out) which a pass count on its
        /// own cannot. Update it deliberately when cases are added.
        internal const int SELFTEST_CASES = 97;

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
                // Inert fixtures, compared and concatenated ordinally and never
                // parsed. Deliberately NOT account-shaped, so a byte scan of the
                // shipped assembly can tell a fixture from an identifier.
                const string OPP = "10000000000000001";
                const string OTHER = "10000000000000002";
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

                // ...and the same rule for the SERIES id, which had only the
                // room name behind it until r13. Rendered as the id the rule
                // hands an observation, then whether the id reads as
                // contradicted, then the record's own join stamp.
                RoomBoundSeries? sb = null;
                Check("series:no-record", Series(ref sb, "ranked_r", 4), "-/no/none");
                sb = new RoomBoundSeries { SeriesId = "S1", RoomName = "ranked_r",
                                           OpponentSteamId = OPP, JoinIncarnation = -1 };
                // published at both_ready, before this seat has joined anything
                Check("series:staged-not-yet-joined", Series(ref sb, "ranked_r", 4), "-/no/-1");
                // ...and an unstamped record must not match a caller that has
                // no incarnation either. The rule does not get to assume the
                // counter it is handed is non-negative: sentinel equals
                // sentinel is not a join.
                Check("series:staged-meets-an-unknown-incarnation", Series(ref sb, "ranked_r", -1), "-/no/-1");
                Check("series:join-stamps", SeriesJoin(ref sb, "ranked_r", 4), "kept/4");
                Check("series:names-its-own-room", Series(ref sb, "ranked_r", 4), "S1/no/4");
                Check("series:another-room-contradicts", Series(ref sb, "other_room", 4), "-/yes/4");
                Check("series:opponent-swapped", Series(ref sb, "ranked_r", 4, OTHER), "-/yes/4");
                // the finding itself: the name is recreated for a new pairing
                Check("series:same-name-new-occupancy", Series(ref sb, "ranked_r", 9), "-/yes/4");
                // ...and the no-room fail-open it also named: a leave that
                // produced no OnLeftRoom leaves this seat believing it is
                // nowhere, and the stamp is evidence with or without a room
                Check("series:nowhere-after-the-occupancy-ended", SeriesNoRoom(ref sb, 9), "-/yes/4");
                Check("series:nowhere-during-it", SeriesNoRoom(ref sb, 4), "-/no/4");
                Check("series:later-join-retires", SeriesJoin(ref sb, "ranked_r", 9), "retired");
                Check("series:retired-answers-nothing", Series(ref sb, "ranked_r", 9), "-/no/none");

                // The lifecycle, EXECUTED. Every case above this line hands
                // the predicates a record built by the test; these run the
                // client's own sequence -- publish, retain, join, read,
                // disconnect, retire -- so an error in the order of those
                // steps has somewhere to show up (r14 LOW).
                RoomBoundSeries? lf = null;
                // (a) the queue path: published from the MENU, for a room not
                // yet joined, before the response's pairing has been retained
                Check("life:published-from-menu", SeriesPublish(ref lf, "S9", "ranked_a", "", false, null, 7),
                      "S9/-/-1");
                Check("life:pairing-arrives-after-publication", SeriesRetain(ref lf, "ranked_a", OPP), OPP);
                Check("life:pairing-for-another-room-is-ignored", SeriesRetain(ref lf, "elsewhere", OTHER), OPP);
                Check("life:the-join-stamps-it", SeriesJoin(ref lf, "ranked_a", 8), "kept/8");
                Check("life:reads-in-its-own-room", Series(ref lf, "ranked_a", 8, OPP), "S9/no/8");
                // the pairing retained in (b) is what makes this answerable at
                // all: with the empty opponent the old order produced, a
                // recurring room name and a different fighter read as this one
                Check("life:another-fighter-in-that-room", Series(ref lf, "ranked_a", 8, OTHER), "-/yes/8");
                // a disconnect produces no room-left callback and no bump, and
                // ranked routing must survive it
                Check("life:disconnect-keeps-routing", SeriesNoRoom(ref lf, 8), "-/no/8");
                Check("life:the-next-join-retires-it", SeriesJoin(ref lf, "ranked_b", 9), "retired");
                Check("life:retired-record-answers-nothing", Series(ref lf, "ranked_a", 9), "-/no/none");

                // (b) the preflight path: published from INSIDE the room, which
                // is every private room, every tournament room and every game
                // after the first. No further join is coming.
                RoomBoundSeries? lp = null;
                Check("life:published-from-inside-the-room",
                      SeriesPublish(ref lp, "S10", "code_x", "", true, "code_x", 12), "S10/-/12");
                Check("life:in-room-publication-answers-at-once", Series(ref lp, "code_x", 12), "S10/no/12");
                // control: the stamp is the CURRENT incarnation and not a
                // constant -- a later occupancy of the same name must not read
                Check("life:control-stamp-is-not-a-constant", Series(ref lp, "code_x", 13), "S10/no/12", true);
                // ...and a publication naming a room this seat is NOT in stays
                // staged even though the seat is in some room
                RoomBoundSeries? lq = null;
                Check("life:publication-for-a-room-not-joined-stays-staged",
                      SeriesPublish(ref lq, "S11", "other_room", "", true, "code_x", 12), "S11/-/-1");
                Check("life:staged-answers-nothing-yet", Series(ref lq, "other_room", 12), "-/no/-1");
                RoomBoundSeries? sctl = new RoomBoundSeries { SeriesId = "S2", RoomName = "ranked_r",
                                                              OpponentSteamId = OPP, JoinIncarnation = 4 };
                Check("control:series:name-alone-answers", Series(ref sctl, "ranked_r", 9), "S2/no/4", control: true);
                Check("control:series:staged-id-answers", Series(ref sb, "ranked_r", 4), "S1/no/none", control: true);

                // ── the room session, driven as SEQUENCES ──────────────────
                //
                // Everything above hands a rule a record somebody built by
                // hand. That cannot see an ORDERING fault, which is what r14
                // HIGH actually was: the stamp was written with the pairing's
                // counter, before the series counter had moved, so it could
                // never equal what its readers compare it against. These cases
                // run the real transitions, in the order the game runs them,
                // against the state each one leaves behind.
                //
                // Rendered as id/stamp@seriesCounter/pPairCounter.
                var s0 = new RoomSessionState();
                Check("seq:menu-is-empty", RoomSession.Render(s0), "-/none@0/p0");

                // The ordinary queue game: an id published from the menu for a
                // room this seat has not joined, the pairing retained from the
                // same response, then the join that stamps it.
                RoomSession.OnSeriesPublished(ref s0, "S1", "ranked_r", false, null);
                Check("seq:queue-publish-is-staged", RoomSession.Render(s0), "S1/staged@0/p0");
                RoomSession.OnSeriesPairingRetained(ref s0, "ranked_r", OPP);
                RoomSession.OnRoomJoined(ref s0, "ranked_r", true);
                Check("seq:join-stamps-with-the-series-counter", RoomSession.Render(s0), "S1/1@1/p1");
                Check("seq:and-the-id-answers-here",
                      RoomSession.SeriesHere(s0, true, "ranked_r", OPP), "S1");
                // The pairing retained BEFORE the join is what tells two
                // occupancies of a recurring name apart; the wrong opponent in
                // the room must not be able to file against this id.
                Check("seq:another-opponent-in-that-room",
                      RoomSession.SeriesHere(s0, true, "ranked_r", OTHER), "");

                // A preflight publishes from INSIDE the room it is about --
                // every game after the first, and every private/tournament
                // room. No further join is coming to stamp it, so it is
                // stamped with the occupancy it is published in (r14 HIGH).
                var s1 = new RoomSessionState();
                RoomSession.OnRoomJoined(ref s1, "code_room", true);
                RoomSession.OnSeriesPublished(ref s1, "S2", "code_room", true, "code_room");
                Check("seq:preflight-publish-is-current", RoomSession.Render(s1), "S2/1@1/p1");
                Check("seq:and-it-answers-immediately",
                      RoomSession.SeriesHere(s1, true, "code_room", ""), "S2");

                // The same room name, left and re-entered: a different room.
                RoomSession.OnRoomLeftReliableEdge(ref s1);
                Check("seq:reliable-exit-moves-both-counters", RoomSession.Render(s1), "-/none@2/p2");
                RoomSession.OnRoomJoined(ref s1, "code_room", true);
                Check("seq:rejoining-the-name-answers-nothing",
                      RoomSession.SeriesHere(s1, true, "code_room", ""), "");

                // A join this seat cannot name still moves both counters and
                // drops the binding: we joined something, and cannot prove it
                // is the room the id was published for.
                var s2 = new RoomSessionState();
                RoomSession.OnSeriesPublished(ref s2, "S3", "ranked_r", false, null);
                RoomSession.OnRoomJoined(ref s2, null, false);
                Check("seq:join-with-an-unreadable-room-name", RoomSession.Render(s2), "-/none@1/p1");

                // The polled exit is the lossy BACKUP for the callback. It
                // clears the id and moves no counter, so a poll observing an
                // exit the callback already handled cannot retire an occupancy
                // the callback has since opened.
                var s3 = new RoomSessionState();
                RoomSession.OnRoomJoined(ref s3, "ranked_r", true);
                RoomSession.OnRoomExitPolled(ref s3);
                Check("seq:polled-exit-alone-does-not-bump", RoomSession.Render(s3), "-/none@1/p1");
                RoomSession.OnRoomLeftReliableEdge(ref s3);
                RoomSession.OnRoomJoined(ref s3, "ranked_r", true);
                RoomSession.OnSeriesPublished(ref s3, "S4", "ranked_r", true, "ranked_r");
                RoomSession.OnRoomExitPolled(ref s3);
                Check("seq:polled-exit-after-the-reliable-edge-is-idempotent",
                      RoomSession.Render(s3), "-/none@3/p3");

                // The head-to-head line's own invalidation moves ITS counter
                // and not the series one. Two questions, two lifetimes.
                var s4 = new RoomSessionState();
                RoomSession.OnRoomJoined(ref s4, "ranked_r", true);
                RoomSession.OnPairInvalidated(ref s4);
                Check("seq:pair-invalidation-is-not-a-series-event",
                      RoomSession.Render(s4), "-/none@1/p2");

                // Controls: each names a way the ordering could be wrong.
                var c0 = new RoomSessionState();
                RoomSession.OnSeriesPublished(ref c0, "S1", "ranked_r", false, null);
                RoomSession.OnRoomJoined(ref c0, "ranked_r", true);
                Check("control:seq:staged-join-stamped-with-the-pair-counter",
                      RoomSession.Render(c0), "S1/0@1/p1", control: true);
                Check("control:seq:unreadable-join-keeps-the-binding",
                      RoomSession.Render(s2), "S3/staged@1/p1", control: true);
                Check("control:seq:polled-exit-bumped-the-counter",
                      RoomSession.Render(s3), "-/none@4/p4", control: true);
                // an unknown opponent is permissive on purpose: the seat that
                // files a leave is looking at a room the opponent has left
                RoomBoundSeries? sopp = new RoomBoundSeries { SeriesId = "S3", RoomName = "ranked_r",
                                                              OpponentSteamId = "", JoinIncarnation = 4 };
                Check("series:unknown-pairing-still-answers", Series(ref sopp, "ranked_r", 4, OTHER), "S3/no/4");

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

        /// <summary>The id the rule hands an observation ("-" for none), then
        /// whether the same state reads as CONTRADICTED, then the record's own
        /// join stamp — so one case reads the permissive rule, the
        /// evidence-only rule and the record together, and a fix that satisfies
        /// one of them by breaking another has nowhere to hide.</summary>
        private static string Series(ref RoomBoundSeries? bound, string roomHere, int incarnation,
                                     string opponentHere = null)
        {
            string id = SeriesForRoom(bound, true, roomHere, incarnation, opponentHere);
            bool no = SeriesContradictedByRoom(bound, true, roomHere, incarnation, opponentHere);
            return (string.IsNullOrEmpty(id) ? "-" : id) + "/" + (no ? "yes" : "no") + "/"
                   + (bound.HasValue ? bound.Value.JoinIncarnation.ToString(CultureInfo.InvariantCulture) : "none");
        }

        /// <summary>The same, for a seat that believes it is in no room at
        /// all — which is what a leave without Photon's callback leaves
        /// behind.</summary>
        private static string SeriesNoRoom(ref RoomBoundSeries? bound, int incarnation)
        {
            string id = SeriesForRoom(bound, false, "", incarnation, null);
            bool no = SeriesContradictedByRoom(bound, false, "", incarnation, null);
            return (string.IsNullOrEmpty(id) ? "-" : id) + "/" + (no ? "yes" : "no") + "/"
                   + (bound.HasValue ? bound.Value.JoinIncarnation.ToString(CultureInfo.InvariantCulture) : "none");
        }

        /// <summary>Publication run through the real entry point, rendered as
        /// id/pairing/stamp. The A1 cases used to hand-build the record these
        /// steps produce, which cannot see an error in the ORDER the client
        /// performs them in -- and the order was the error (r14).</summary>
        private static string SeriesPublish(ref RoomBoundSeries? bound, string id, string room,
                                            string opponent, bool inRoomHere, string roomHere,
                                            int incarnation)
        {
            PublishSeries(ref bound, id, room, opponent, inRoomHere, roomHere, incarnation);
            if (!bound.HasValue) return "none";
            var b = bound.Value;
            return b.SeriesId + "/" + (string.IsNullOrEmpty(b.OpponentSteamId) ? "-" : "opp")
                   + "/" + b.JoinIncarnation.ToString(CultureInfo.InvariantCulture);
        }

        /// <summary>The pairing the record holds after a retention attempt.</summary>
        private static string SeriesRetain(ref RoomBoundSeries? bound, string room, string opponent)
        {
            RetainSeriesPairing(ref bound, room, opponent);
            if (!bound.HasValue) return "none";
            string o = bound.Value.OpponentSteamId;
            return string.IsNullOrEmpty(o) ? "-" : o;
        }

        private static string SeriesJoin(ref RoomBoundSeries? bound, string room, int incarnation)
        {
            if (RetireSeriesOnJoin(ref bound, room, incarnation)) return "retired";
            return "kept/" + (bound.HasValue ? bound.Value.JoinIncarnation.ToString(CultureInfo.InvariantCulture) : "none");
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
