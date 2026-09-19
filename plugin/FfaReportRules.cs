using System;
using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>The two decisions the FFA report path makes that are pure
    /// functions of values it has already collected: WHO submits, and WHETHER
    /// a refusal is final.
    ///
    /// They live here rather than inline at their call sites because both are
    /// rules rather than plumbing — each has a stated property that has to
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

        /// <summary>Elect the seat that submits this game's report: the lowest
        /// Steam ID among the seats that WITNESSED the game's start, falling
        /// back to the lowest among those merely PRESENT when no witness is
        /// known.
        ///
        /// Two properties, both load-bearing.
        ///
        /// TOTAL. For any non-empty <paramref name="present"/> this returns a
        /// seat, and the fallback is what makes that true. A qualifier that
        /// can disqualify every candidate is a guard only the disqualified
        /// seats evaluate: the sitting then ends with nobody submitting and
        /// voids itself silently, which is strictly worse than the defect the
        /// qualifier exists for (#430).
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
                // An unparseable id is not a candidate. It is also invisible
                // to its peers' comparisons, so a seat carrying one can never
                // be deferred TO — which is why the fallback above is about
                // the electorate being empty, not about this skip.
                if (!long.TryParse(sid, out v)) continue;
                if (v < lowVal) { lowVal = v; lowest = sid; }
            }
            return lowest;
        }
    }
}
