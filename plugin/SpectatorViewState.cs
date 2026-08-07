using System;
using UnityEngine;

namespace CompetitiveRounds
{
    /// <summary>
    /// Aug 6 item 13 (spectator mode), PHASE 1 — what the spectator client
    /// believes about the match it is watching.
    ///
    /// Deliberately OBSERVATION-ONLY. The spectator never simulates: it
    /// records what the fighters' own replicated RPCs say and renders that.
    /// Every field here is written from a suppressed vanilla path (see
    /// SpectatorPatches.cs) and read by the spectator HUD.
    ///
    /// Nothing in this file can affect a fighter — it holds no RPC sender,
    /// no Photon write, and no vanilla state mutation.
    /// </summary>
    internal static class SpectatorViewState
    {
        /// <summary>Team 0/1 round wins and live points, as last announced
        /// by the fighters' own RPCA_NextRound. -1 = not yet observed.</summary>
        internal static int Team0Rounds { get; private set; } = -1;
        internal static int Team1Rounds { get; private set; } = -1;
        internal static int Team0Points { get; private set; } = -1;
        internal static int Team1Points { get; private set; } = -1;
        internal static int LastWinningTeam { get; private set; } = -1;
        internal static float LastScoreAt { get; private set; }

        /// <summary>True once we have seen any score traffic — the HUD shows
        /// "synchronising" until then rather than a fake 0-0.</summary>
        internal static bool HasScore => Team0Rounds >= 0 || Team1Rounds >= 0;

        internal static void RecordScore(int winningTeamId, int p1Points, int p2Points,
                                         int p1Rounds, int p2Rounds)
        {
            Team0Points = p1Points;
            Team1Points = p2Points;
            Team0Rounds = p1Rounds;
            Team1Rounds = p2Rounds;
            LastWinningTeam = winningTeamId;
            LastScoreAt = Time.unscaledTime;
        }

        internal static void Reset()
        {
            Team0Rounds = Team1Rounds = Team0Points = Team1Points = -1;
            LastWinningTeam = -1;
            LastScoreAt = 0f;
        }

        /// <summary>Short line for the spectator HUD.</summary>
        internal static string ScoreLine()
        {
            if (!HasScore) return "";
            return $"{Math.Max(0, Team0Rounds)} - {Math.Max(0, Team1Rounds)}";
        }
    }
}
