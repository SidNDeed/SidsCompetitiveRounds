using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug 392: what this seat knows about a room exit it did not choose, and
    /// the warning that precedes one.
    ///
    /// Two jobs, both of them decisions rather than effects:
    ///   * item B - when socket silence has lasted long enough that the player
    ///     should be told, before Photon gives up on the connection;
    ///   * item A step 2 - the DisconnectCause this seat last saw, held for a
    ///     short validity window, so the room-exit hooks can attest an
    ///     involuntary departure instead of a voluntary one.
    ///
    /// Deliberately free of Unity, Photon and BepInEx - the same rule
    /// H2HRules.cs follows - so every decision below can be EXECUTED by a
    /// harness instead of being asserted about as source text. The clock is a
    /// parameter at every predicate; NowSeconds() is the one place production
    /// reads a real clock, and it is the SAME monotonic base at every call
    /// site (mixing two clocks is what made an earlier receive-gap check fire
    /// falsely - see the SampleConnectionQuality comment).
    /// </summary>
    internal static class TransportExit
    {
        // ── item B: the pre-disconnect notice ────────────────────────────

        /// <summary>Socket silence, in ms, at which the player is told.
        /// SampleConnectionQuality latches _recvGapOpen at 2 s and samples on
        /// the 3 s cadence, so the notice is raised on the first sample at or
        /// past this value. The threshold is a constant and nothing reads a
        /// literal 5000 anywhere else - the harness derives its cases from
        /// this field, so moving it moves the tests with it (#342).</summary>
        internal const int SilenceNoticeMs = 5000;

        /// <summary>How long a raised notice stays up without a fresh
        /// over-threshold sample. The notice EXPIRES by default (#276): the
        /// sample loop that raises it runs only while connected and in a
        /// room, so on the disconnect it is warning about, no further sample
        /// arrives to clear it. An expiring notice self-heals; a
        /// clear-on-recovery-only notice would be stuck on screen for the
        /// rest of the session on exactly the failure it exists for. Long
        /// enough to cover two missed 3 s samples.</summary>
        internal const double NoticeHoldSeconds = 12.0;

        // ── item A step 2: the cause of an involuntary exit ──────────────

        /// <summary>How long a recorded cause may be read back. A cause is
        /// evidence about the exit that FOLLOWS it by a poll tick or two, not
        /// a property of the session: past this window the exit hooks fall
        /// back to today's untagged behaviour rather than inherit a stale
        /// cause into another room (#430).</summary>
        internal const double CauseValidSeconds = 10.0;

        /// <summary>Today's in-room tag. Anything that is not this (or the
        /// involuntary tag below) reads as a PRE-room leave on the server and
        /// does not veto lobby dissolution.</summary>
        internal const string InRoomExitTag = "in_room_exit";

        /// <summary>The in-room INVOLUNTARY tag. 15 characters against the
        /// endpoint's cause: str = Query("", max_length=16) - a longer, more
        /// descriptive tag 422s the request. Asserted by the harness so the
        /// bound is checked rather than remembered.</summary>
        internal const string InRoomInvoluntaryTag = "in_room_timeout";

        /// <summary>The wire bound the tag above is measured against.</summary>
        internal const int MaxCauseTagLength = 16;

        /// <summary>The field in the /api/v1/mod-version response by which the
        /// server advertises that it recognises the involuntary tag. Absent =
        /// not advertised = this client sends exactly what it sends today.
        /// Named here, next to the tag it gates, so the client's half of the
        /// contract is one place.</summary>
        internal const string CapabilityField = "ffa_involuntary_cause";

        /// <summary>The Photon DisconnectCause values that are NOT this
        /// player's choice, enumerated from the DisconnectCause enum in the
        /// PhotonRealtime build ROUNDS ships (19 members; the whole enum is
        /// accounted for here or in NotInvoluntary below, so this is a sweep
        /// and not a sample - #432).
        ///
        /// An ALLOW-list on purpose. A member that is missing - a future
        /// Photon version, a name spelled differently - is treated as NOT
        /// involuntary, which is exactly today's behaviour and costs only the
        /// softening. A deny-list would fail the other way: a new VOLUNTARY
        /// member would be attested as a transport failure, which is a client
        /// attesting a cause in the non-conservative direction (#283).</summary>
        private static readonly string[] InvoluntaryCauses =
        {
            "ClientTimeout",                    // this bug: no inbound delivery, peer gave up
            "ServerTimeout",                    // the relay stopped hearing us
            "Exception",                        // socket/receive thread died
            "ExceptionOnConnect",
            "DnsExceptionOnConnect",
            "ServerAddressInvalid",
            "DisconnectByServerLogic",          // the relay ended it
            "DisconnectByServerReasonUnknown",
            "DisconnectByDisconnectMessage",
            "DisconnectByOperationLimit",
            "MaxCcuReached",
            "InvalidRegion",
            "OperationNotAllowedInCurrentState",
            "CustomAuthenticationFailed",
            "AuthenticationTicketExpired",
            "InvalidAuthentication",
        };

        /// <summary>The remaining members of the same enum, listed so the
        /// sweep is visible and a reviewer can count 16 + 3 = 19: "None" (no
        /// disconnect happened), "DisconnectByClientLogic" (this client asked
        /// to leave - the Leave button, the menu, our own teardown) and
        /// "ApplicationQuit". None of the three may ever be attested as
        /// involuntary; a departure the player chose is the thing the tag
        /// exists to be distinguishable FROM.</summary>
        private static readonly string[] NotInvoluntary =
        {
            "None", "DisconnectByClientLogic", "ApplicationQuit",
        };

        internal static int InvoluntaryCauseCount { get { return InvoluntaryCauses.Length; } }
        internal static int VoluntaryCauseCount { get { return NotInvoluntary.Length; } }

        /// <summary>Whether a DisconnectCause name is one this seat may
        /// attest as involuntary. Ordinal, exact: a name that is not in the
        /// list - including null, empty and anything unrecognised - is not
        /// involuntary.</summary>
        internal static bool IsInvoluntaryCause(string causeName)
        {
            if (string.IsNullOrEmpty(causeName)) return false;
            for (int i = 0; i < InvoluntaryCauses.Length; i++)
                if (string.Equals(InvoluntaryCauses[i], causeName, StringComparison.Ordinal)) return true;
            return false;
        }

        /// <summary>True when the name is a known member of the enum at all
        /// (either list). Used by the harness to prove the two lists together
        /// cover the shipped enum rather than a chosen subset of it.</summary>
        internal static bool IsKnownCause(string causeName)
        {
            if (IsInvoluntaryCause(causeName)) return true;
            if (string.IsNullOrEmpty(causeName)) return false;
            for (int i = 0; i < NotInvoluntary.Length; i++)
                if (string.Equals(NotInvoluntary[i], causeName, StringComparison.Ordinal)) return true;
            return false;
        }

        // ── state ────────────────────────────────────────────────────────

        private static string _cause;          // null/empty = nothing recorded
        private static double _causeAtS;
        private static double _noticeUntilS;   // 0 = no notice raised
        private static int _noticeSilentMs;

        /// <summary>The one real clock. Monotonic, process-wide, unaffected by
        /// timeScale or system clock changes.</summary>
        internal static double NowSeconds()
        {
            return System.Diagnostics.Stopwatch.GetTimestamp()
                 / (double)System.Diagnostics.Stopwatch.Frequency;
        }

        /// <summary>Every piece of state this type holds. Room edges call it;
        /// the harness calls it between cases.</summary>
        internal static void ResetAll()
        {
            _cause = null;
            _causeAtS = 0.0;
            _noticeUntilS = 0.0;
            _noticeSilentMs = 0;
        }

        // ── cause recording ──────────────────────────────────────────────

        /// <summary>Record a disconnect. An involuntary cause is stored with
        /// its timestamp; ANY other cause CLEARS the store, because the newest
        /// disconnect is the truth about the exit that follows it and a
        /// voluntary one must never be shadowed by an older transport
        /// failure.</summary>
        internal static void NoteDisconnect(string causeName, double nowSeconds)
        {
            if (!IsInvoluntaryCause(causeName)) { ClearCause(); return; }
            _cause = causeName;
            _causeAtS = nowSeconds;
        }

        internal static void ClearCause()
        {
            _cause = null;
            _causeAtS = 0.0;
        }

        /// <summary>The recorded involuntary cause, if one was recorded inside
        /// the validity window. A negative age (a clock that went backwards,
        /// or a cause recorded by a harness case that has since reset the
        /// clock) reads as NOT fresh - the unhandled direction is "no tag",
        /// which is today's behaviour.</summary>
        internal static bool TryGetFreshInvoluntary(double nowSeconds, out string cause)
        {
            cause = null;
            if (string.IsNullOrEmpty(_cause)) return false;
            double age = nowSeconds - _causeAtS;
            if (age < 0.0 || age > CauseValidSeconds) return false;
            cause = _cause;
            return true;
        }

        // ── the pre-disconnect notice ────────────────────────────────────

        /// <summary>Whether this silence sample is the player's business.</summary>
        internal static bool ShouldWarnOnSilence(int silentMs)
        {
            return silentMs >= SilenceNoticeMs;
        }

        /// <summary>Raise (or re-arm) the notice from a silence sample.
        /// Returns TRUE only on the rising edge, so the caller's log line is
        /// one line per episode and not one per sample.</summary>
        internal static bool NoteSilence(int silentMs, double nowSeconds)
        {
            if (!ShouldWarnOnSilence(silentMs)) return false;
            bool wasActive = SilenceNoticeActive(nowSeconds, out _);
            if (silentMs > _noticeSilentMs) _noticeSilentMs = silentMs;
            _noticeUntilS = nowSeconds + NoticeHoldSeconds;
            return !wasActive;
        }

        /// <summary>Recovery, room edge, disconnect handled: the notice goes
        /// away. Idempotent - the sample loop calls it on every healthy
        /// sample.</summary>
        internal static void ClearSilence()
        {
            _noticeUntilS = 0.0;
            _noticeSilentMs = 0;
        }

        /// <summary>Whether a notice should be on screen now, and the worst
        /// silence it was raised on.</summary>
        internal static bool SilenceNoticeActive(double nowSeconds, out int silentMs)
        {
            silentMs = _noticeSilentMs;
            if (_noticeUntilS <= 0.0) return false;
            if (nowSeconds > _noticeUntilS) return false;
            return true;
        }

        /// <summary>The number the notice shows. Integer seconds, FLOORED, so
        /// the line never claims more silence than was measured.</summary>
        internal static int SilenceSeconds(int silentMs)
        {
            if (silentMs <= 0) return 0;
            return silentMs / 1000;
        }

        // ── the leave tag ────────────────────────────────────────────────

        /// <summary>The cause tag for an exit from a room whose game had
        /// STARTED. Both possible return values are IN-ROOM tags, so this
        /// substitution can never turn an in-room exit into one the server
        /// reads as a pre-room leave - it cannot reach the dissolution path
        /// that cancels a live game for the other seats.
        ///
        /// Returns today's tag unless BOTH hold: this seat recorded a fresh
        /// involuntary cause, and the server advertised that it recognises the
        /// involuntary tag. With the capability absent - an older server, a
        /// startup read that never landed - the result is byte-for-byte what
        /// this client sends today.</summary>
        internal static string InRoomLeaveTag(bool serverRecognisesInvoluntary, double nowSeconds)
        {
            if (!serverRecognisesInvoluntary) return InRoomExitTag;
            string cause;
            return TryGetFreshInvoluntary(nowSeconds, out cause)
                ? InRoomInvoluntaryTag
                : InRoomExitTag;
        }

        /// <summary>Whether a tag is one the server reads as in-room. The
        /// upgrade bookkeeping in ApiClient.FfaLeaveQueue keys on this instead
        /// of on a bare equality with one literal, so the involuntary tag is
        /// carried by the retry paths exactly like in_room_exit is (#432).</summary>
        internal static bool IsInRoomTag(string tag)
        {
            return string.Equals(tag, InRoomExitTag, StringComparison.Ordinal)
                || string.Equals(tag, InRoomInvoluntaryTag, StringComparison.Ordinal);
        }
    }
}
