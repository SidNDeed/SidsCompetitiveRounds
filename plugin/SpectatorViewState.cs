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

        /* Bug #272: last-VALID series watermark, kept apart from
         * SessionSeries0/1 because the display-clearing (-1,-1) sentinel
         * overwrites those on every snapshot. Pair-keyed so a match rotation
         * resets rather than reads as an increase. */
        private static string _seriesWatermarkPair;
        private static int _seriesWatermarkTotal = -1;

        internal static void RecordSessionSeries(int s0, int s1)
        {
            // Bug #272: this is the spectator's only observation that a SERIES
            // finished, so it is where the lifetime head-to-head cache learns it
            // is out of date. Without this the "Overall Series" segment sat up to
            // 300s behind the "Session Series" printed next to it.
            //
            // Fire only on a genuine INCREASE, compared against a SEPARATE
            // last-VALID watermark rather than against the live fields.
            //
            // Review find (HIGH): comparing against SessionSeries0/1 made this a
            // production no-op. The caller writes the (-1, -1) display-clearing
            // sentinel before EVERY snapshot parse, and that call lands here and
            // STORES -1, -1 — so by the time the real values arrive the previous
            // reading is always negative and the "both previous >= 0" test can
            // never pass. Guarding against the sentinel with a test the sentinel
            // itself poisons blocked the signal entirely.
            //
            // The watermark is keyed by the fighter PAIR so a rotation to a new
            // match cannot read as a jump (a different pair's 3-1 is not an
            // increase over this pair's 1-0); a pair change resets it instead of
            // signalling.
            try
            {
                if (s0 >= 0 && s1 >= 0)
                {
                    var sids = SpectatorSync.FighterSteamIds;
                    string pair = (sids != null && sids.Length == 2)
                        ? (string.CompareOrdinal(sids[0], sids[1]) <= 0
                            ? sids[0] + "|" + sids[1] : sids[1] + "|" + sids[0])
                        : null;
                    if (pair != null)
                    {
                        if (pair != _seriesWatermarkPair)
                        {
                            // First reading for this pair — a BASELINE, not an
                            // increase, so it announces nothing. But the H2H
                            // cache is process-wide and Reset() does not clear
                            // it (review find 3): a spectator who watched A/B,
                            // left while A/B finished a series, and came back
                            // inside the 300s TTL would otherwise be served the
                            // pre-series count with no signal that anything
                            // changed. Marking the pair stale here costs one
                            // floored refetch per rotation and closes that hole;
                            // the cached value keeps rendering meanwhile.
                            _seriesWatermarkPair = pair;
                            _seriesWatermarkTotal = s0 + s1;
                            ApiClient.MarkHeadToHeadStale(sids[0], sids[1]);
                        }
                        else if ((s0 + s1) > _seriesWatermarkTotal)
                        {
                            _seriesWatermarkTotal = s0 + s1;
                            ApiClient.MarkHeadToHeadStale(sids[0], sids[1]);
                        }
                    }
                }
            }
            catch { }
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
            _seriesWatermarkPair = null; _seriesWatermarkTotal = -1;
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
