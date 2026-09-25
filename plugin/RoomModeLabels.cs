using System;

namespace CompetitiveRounds
{
    /// <summary>
    /// Bug 392 item D: name the mode a room actually is.
    ///
    /// The 1v1 room-exit path derived its label from matchIsRanked, which the
    /// poll forces true for ANY mod-issued room. The result was a log line
    /// reading "=== RANKED Canceled === Disconnect at 0-0 (not counted)"
    /// written about an FFA game that was at three rounds each and that WAS
    /// counted - a false mechanism claim sitting in the log for the next
    /// diagnosis to read (#432/#459), and one that already steered a revision
    /// of this bug's own diagnosis wrong.
    ///
    /// Free of Unity, Photon and BepInEx so a harness executes it. The room id
    /// is the only input: the mod issues these prefixes itself, and the match
    /// is anchored at the start - a substring test would classify a room whose
    /// code merely contains the prefix.
    /// </summary>
    internal static class RoomModeLabels
    {
        internal const string FfaPrefix = "ffa_";
        internal const string TeamPrefix = "team_";
        internal const string OvtPrefix = "ovt_";

        /// <summary>The label for the mode this room is, falling back to the
        /// ranked/casual pair for a plain 1v1 or a room-code game.</summary>
        internal static string ModeLabel(string roomId, bool ranked)
        {
            if (StartsWithOrdinal(roomId, FfaPrefix)) return "FFA";
            if (StartsWithOrdinal(roomId, TeamPrefix)) return "2v2";
            if (StartsWithOrdinal(roomId, OvtPrefix)) return "1v2";
            return ranked ? "RANKED" : "CASUAL";
        }

        /// <summary>Whether the 1v1 outcome cascade must NOT run for this room.
        ///
        /// True for FFA only. The 1v1 tracker's round counters do not advance
        /// in an FFA sitting - the FFA engine keeps that score - so every
        /// outcome the cascade could derive from them is derived from zeros:
        /// the DC-win branches, the awarded 4-4 tiebreak, and the cancel line
        /// that calls the game "(not counted)" while the FFA reporter counts
        /// it. 2v2 and 1v2 keep their existing behaviour and only gain an
        /// honest label; this returns false for them deliberately.</summary>
        internal static bool SuppressOneVOneOutcome(string roomId)
        {
            return StartsWithOrdinal(roomId, FfaPrefix);
        }

        private static bool StartsWithOrdinal(string text, string prefix)
        {
            if (string.IsNullOrEmpty(text) || string.IsNullOrEmpty(prefix)) return false;
            if (text.Length < prefix.Length) return false;
            return string.CompareOrdinal(text, 0, prefix, 0, prefix.Length) == 0;
        }
    }
}
