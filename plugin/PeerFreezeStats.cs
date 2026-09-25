using System.Globalization;

namespace CompetitiveRounds
{
    /// <summary>What a peer's freeze counters MEAN, and whether a match report may
    /// carry them (v1.41.0 beta review round 2, finding 3). Pure: no Photon or
    /// Unity, so GameStateWatcher's receiver, the 1v1 match report and the
    /// sentinel below all run the same code, and the sentinel also runs outside
    /// the game.
    ///
    /// Report #359 changed how a seat counts its own freezes. The old condition,
    /// `Math.Max(dt, wallGap)`, tripped once on the resume tick and again on the
    /// next, so a client from before the fix reports about twice the stalls it
    /// had. Its cr_gstats fields 9-10 (freezeCount, freezeFocusedCount) look
    /// exactly like ours, and the server flags `freeze_focused_count >= 3`, so
    /// two real focused stalls from such a peer would flag. Nothing else on the
    /// wire says which definition produced the numbers: reporter_mod_version
    /// names the REPORTER, not the peer (the same reason BULLET_STATS_EPOCH
    /// exists).
    ///
    /// So the payload declares its freeze definition as field 24, the same way
    /// field 23 declares the bullet-stats one, and a report carries the peer's
    /// freeze counters only when the peer declared THIS definition. Anything
    /// else (an old client that never sends field 24, a garbled value, a future
    /// definition we do not know) is UNKNOWN and goes to the server as null: the
    /// schema's own "absent", which the lag-flag check reads as no evidence.
    /// A zero would be a fabricated observation, and a negative sentinel would
    /// fail validation (ge=0).</summary>
    internal static class PeerFreezeStats
    {
        /// <summary>1 = one trip per stall, measured on the monotonic stopwatch
        /// alone (report #359). Bump it whenever the counting definition changes
        /// again. 0 is reserved for "the peer never said", so it never names a
        /// definition.</summary>
        internal const int Epoch = 1;

        /// <summary>Field 24 of cr_gstats, after the bullet-stats epoch (field 23).</summary>
        internal const int EpochFieldIndex = 23;

        /// <summary>The freeze definition one cr_gstats payload declares, or 0
        /// when it declares none. TryParse, never Parse: a garbled field must read
        /// as UNKNOWN, not throw and leave a previous peer's epoch standing
        /// beside fresh counters (the bullet epoch's own lesson).</summary>
        internal static int ReadEpoch(string[] parts)
        {
            int ep = 0;
            if (parts != null && parts.Length > EpochFieldIndex
                && !int.TryParse(parts[EpochFieldIndex], NumberStyles.Integer, CultureInfo.InvariantCulture, out ep))
                ep = 0;
            return ep;
        }

        /// <summary>The freeze counters one payload carries, and the definition
        /// it declares for them, both from the SAME payload. False when the
        /// payload predates the freeze fields (fewer than 11 fields). The counts
        /// are parsed as the receiver always has, and a garbled count throws.</summary>
        internal static bool TryRead(string[] parts, out int count, out int focused, out int epoch)
        {
            count = 0; focused = 0; epoch = 0;
            if (parts == null || parts.Length < 11) return false;
            count = int.Parse(parts[8], NumberStyles.Integer, CultureInfo.InvariantCulture);
            focused = int.Parse(parts[9], NumberStyles.Integer, CultureInfo.InvariantCulture);
            epoch = ReadEpoch(parts);
            return true;
        }

        /// <summary>True only when the peer counted its freezes the way we do.</summary>
        internal static bool Usable(int epoch)
        {
            return epoch == Epoch;
        }

        /// <summary>The match report's two opp_freeze fields, trailing comma
        /// included: the numbers when known, null (absent) when not.</summary>
        internal static string ReportFields(bool known, int count, int focused)
        {
            if (!known) return "\"opp_freeze_count\":null,\"opp_freeze_focused_count\":null,";
            return "\"opp_freeze_count\":" + count.ToString(CultureInfo.InvariantCulture)
                 + ",\"opp_freeze_focused_count\":" + focused.ToString(CultureInfo.InvariantCulture) + ",";
        }

        // ── Sentinel ────────────────────────────────────────────────────────
        //
        // The report's scenario: a pre-fix peer that had two real focused stalls
        // and, counting each twice, advertises 4 and 4. The same two numbers on a
        // payload that declares this definition are a real 4 and 4. Each payload
        // goes through TryRead -> Usable -> ReportFields, the path the receiver
        // and the 1v1 report run. GameStateWatcher.DevFreezeEpochSentinelTest adds
        // the one in-game check this cannot make: that the real payload builder
        // declares the epoch.

        internal const string SentinelTag = "[FREEZE-EPOCH-SENTINEL]";

        private const string Unknown = "\"opp_freeze_count\":null,\"opp_freeze_focused_count\":null,";
        private const string TrustedFour = "\"opp_freeze_count\":4,\"opp_freeze_focused_count\":4,";

        /// <summary>A synthetic cr_gstats payload: `fields` fields, freeze count
        /// and focused count 4 at fields 9-10, the bullet epoch 2 at field 23 when
        /// there is one, and `freezeEpoch` at field 24 when there is one. Every
        /// position is written as a literal of the wire format, never through
        /// EpochFieldIndex: a probe built from the constant it tests would move
        /// with that constant and could not catch it being wrong.</summary>
        private static string[] Payload(int fields, string freezeEpoch)
        {
            var p = new string[fields];
            for (int i = 0; i < fields; i++) p[i] = "0";
            p[8] = "4"; p[9] = "4";
            if (fields > 22) p[22] = "2";
            if (fields > 23 && freezeEpoch != null) p[23] = freezeEpoch;
            return p;
        }

        private static string Verdict(string[] parts)
        {
            int count, focused, epoch;
            if (!TryRead(parts, out count, out focused, out epoch)) return "no-fields";
            return ReportFields(Usable(epoch), count, focused);
        }

        /// <summary>Returns the log line; `pass` is its verdict. `builtPayload`,
        /// when given, is a payload from the real builder, split on '|': it must
        /// declare this epoch at field 24.</summary>
        internal static string RunSentinel(out bool pass, string[] builtPayload = null)
        {
            pass = true;
            int checks = 0;
            string detail = "";
            var cases = new[]
            {
                // name, payload, the report fields it must produce
                new { Name = "old-11-fields",   Parts = Payload(11, null), Want = Unknown },
                new { Name = "old-22-fields",   Parts = Payload(22, null), Want = Unknown },
                // 23 fields: the bullet epoch (2) is present and must NOT be read
                // as a freeze epoch - field 23 is not field 24.
                new { Name = "old-23-fields",   Parts = Payload(23, null), Want = Unknown },
                new { Name = "new-epoch",       Parts = Payload(24, Epoch.ToString(CultureInfo.InvariantCulture)), Want = TrustedFour },
                new { Name = "new-epoch-extra", Parts = Payload(26, Epoch.ToString(CultureInfo.InvariantCulture)), Want = TrustedFour },
                new { Name = "epoch-zero",      Parts = Payload(24, "0"), Want = Unknown },
                new { Name = "epoch-future",    Parts = Payload(24, (Epoch + 1).ToString(CultureInfo.InvariantCulture)), Want = Unknown },
                new { Name = "epoch-garbled",   Parts = Payload(24, "x"), Want = Unknown },
                new { Name = "epoch-empty",     Parts = Payload(24, ""), Want = Unknown },
            };
            foreach (var c in cases)
            {
                checks++;
                string got = Verdict(c.Parts);
                if (got != c.Want) { pass = false; detail += " " + c.Name + ":" + got; }
            }
            // A payload from before the freeze fields existed carries nothing to gate.
            checks++;
            if (Verdict(Payload(10, null)) != "no-fields") { pass = false; detail += " ten-fields:read"; }
            if (builtPayload != null)
            {
                checks++;
                int declared = ReadEpoch(builtPayload);
                if (declared != Epoch) { pass = false; detail += " builder-declares:" + declared; }
            }
            return SentinelTag + " " + (pass ? "PASS" : "FAIL") + ": " + checks + " checks" + detail;
        }
    }
}
