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

        /// <summary>Points needed to convert a round, as read from the live
        /// GM by the observe patch (host-configurable in private rooms —
        /// never hardcode 2, Aug 10 review). Drives the half-point display.</summary>
        internal static int PointsToWinRound { get; private set; } = 2;

        /// <summary>Session series tally in fighter-array order (snapshot
        /// slots 16/17). -1 = unknown/not applicable — the HUD hides the
        /// line. Cleared before every snapshot parse (find 11).</summary>
        internal static int SessionSeries0 { get; private set; } = -1;
        internal static int SessionSeries1 { get; private set; } = -1;

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

        internal static void RecordPointsToWin(int ptw)
        {
            if (ptw > 0) PointsToWinRound = ptw;
        }

        internal static void RecordSessionSeries(int s0, int s1)
        {
            SessionSeries0 = s0;
            SessionSeries1 = s1;
        }

        internal static void Reset()
        {
            Team0Rounds = Team1Rounds = Team0Points = Team1Points = -1;
            LastWinningTeam = -1;
            LastScoreAt = 0f;
            PointsToWinRound = 2;
            SessionSeries0 = SessionSeries1 = -1;
        }

        /// <summary>Rounds with a live-point fraction (item 3: "doesn't show
        /// half points"): 2 rounds + 1 of 2 points renders "2.5". ASCII only
        /// (#47); fraction in tenths so a 3-point private room reads "2.3".</summary>
        internal static string TeamScoreText(int team)
        {
            int rounds = Math.Max(0, team == 0 ? Team0Rounds : Team1Rounds);
            int points = Math.Max(0, team == 0 ? Team0Points : Team1Points);
            int ptw = Math.Max(1, PointsToWinRound);
            if (points <= 0 || points >= ptw) return rounds.ToString();
            int tenths = (int)Math.Round(10.0 * points / ptw);
            if (tenths <= 0) return rounds.ToString();
            if (tenths >= 10) tenths = 9;
            return rounds + "." + tenths;
        }

        /// <summary>Short line for the spectator HUD.</summary>
        internal static string ScoreLine()
        {
            if (!HasScore) return "";
            return TeamScoreText(0) + " - " + TeamScoreText(1);
        }
    }
}
