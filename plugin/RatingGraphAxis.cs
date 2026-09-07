using System.Collections.Generic;

namespace CompetitiveRounds
{
    /// <summary>Sept 6 (item f) — the x-axis rule shared by every rating graph
    /// in the mod: the leaderboard profile graph and the Compare tab's Elo
    /// charts. Pure (no Unity objects), so both graphs draw the same polyline
    /// from the same rows and the rule can be read in one place (#279). Mirrors
    /// the Discord bot's `_rating_axis_points`.
    ///
    /// Modes (Plugin.RatingGraphAxisMode, written by the buttons on the graphs):
    ///   updates     — x = index of the rating update. One rating_history row is
    ///                 one completed ranked series, never a game count. The
    ///                 default, i.e. what the graphs drew before Sept 6.
    ///   calendar    — x = the update's timestamp (period_end).
    ///   since_first — x = days since THIS series' first plotted update, so
    ///                 every player's line starts at x = 0.
    /// The two time axes are STEP plots (the previous rating is repeated at
    /// each new timestamp before the jump), so a player idle for weeks draws a
    /// flat run — a slope between two updates would be invented movement. The
    /// first drawn point is the first row's rating: the table carries no
    /// pre-update value and no baseline is prepended (the old synthetic 1500
    /// point is gone).</summary>
    internal static class RatingGraphAxis
    {
        public const string Updates = "updates";
        public const string Calendar = "calendar";
        public const string SinceFirst = "since_first";
        public static readonly string[] Modes = { Updates, Calendar, SinceFirst };

        /// <summary>The configured mode, sanitised (anything unknown reads as Updates).</summary>
        public static string Current
        {
            get { try { return Normalise(Plugin.RatingGraphAxisMode?.Value); } catch { return Updates; } }
        }

        public static string Normalise(string v) => v == Calendar || v == SinceFirst ? v : Updates;

        /// <summary>F-2: the time axes are step plots; the index axis is a line.</summary>
        public static bool IsStep(string mode) => Normalise(mode) != Updates;

        /// <summary>Persist a mode (BepInEx writes the cfg on assignment).</summary>
        public static void Set(string mode)
        {
            try { if (Plugin.RatingGraphAxisMode != null) Plugin.RatingGraphAxisMode.Value = Normalise(mode); } catch { }
        }

        /// <summary>Button label. Explicit switch: `I18n.Tr(variable)` harvests
        /// nothing (#295a), so each literal sits inside its own Tr call.</summary>
        public static string Label(string mode)
        {
            switch (Normalise(mode))
            {
                case Calendar: return I18n.Tr("Calendar");
                case SinceFirst: return I18n.Tr("Since first");
                default: return I18n.Tr("Updates");
            }
        }

        /// <summary>The axis caption drawn on the plot — names the active axis.</summary>
        public static string Caption(string mode)
        {
            switch (Normalise(mode))
            {
                case Calendar: return I18n.Tr("date ->");
                case SinceFirst: return I18n.Tr("days since first rating update ->");
                default: return I18n.Tr("rating updates ->");
            }
        }

        /// <summary>Build the polyline for one series. `ratings` and `times` are
        /// parallel, oldest first (times = fractional days since 2020-01-01, as
        /// ApiClient parses them; unused for Updates). Output x: the update index
        /// (Updates), days since the 2020 epoch (Calendar) or days since this
        /// series' first point (SinceFirst); y: the rating. On the time axes each
        /// update after the first contributes TWO vertices — (x_i, r_i-1) then
        /// (x_i, r_i) — so callers see the step; the update itself is every EVEN
        /// vertex.
        ///
        /// `maxPoints` (0 = uncapped) is the density cap. On the Updates axis a
        /// longer series is bucket-AVERAGED down to maxPoints — the profile graph
        /// has always drawn it that way and that axis is the preserved default.
        /// On the time axes the series is DECIMATED instead (the last row of each
        /// bucket is kept, a real (time, rating) pair): a step plot's whole point
        /// is to never invent a value, and an averaged pair straddling an idle gap
        /// would put a half-step in the middle of it.
        ///
        /// Returns false when nothing can be drawn: fewer than two rows, or a
        /// time axis whose times are missing or not parallel.</summary>
        public static bool Build(List<float> ratings, List<float> times, string mode, int maxPoints,
                                 out float[] xs, out float[] ys)
        {
            xs = null; ys = null;
            if (ratings == null || ratings.Count < 2) return false;
            mode = Normalise(mode);
            bool timeAxis = mode != Updates;
            if (timeAxis && (times == null || times.Count != ratings.Count)) return false;

            int n = ratings.Count;
            float[] r, t = null;
            if (maxPoints >= 2 && n > maxPoints)
            {
                r = new float[maxPoints];
                if (timeAxis)
                {
                    // Decimate, keeping the FIRST fetched row verbatim (review f-M2): it
                    // is the baseline the design names and the since-first day zero.
                    // The remaining rows fall into maxPoints-1 buckets and each bucket
                    // keeps its newest row -- a value the player really held (the last
                    // bucket ends at the newest row, so the current rating survives too).
                    t = new float[maxPoints];
                    r[0] = ratings[0]; t[0] = times[0];
                    int rest = n - 1, buckets = maxPoints - 1;
                    for (int b = 0; b < buckets; b++)
                    {
                        int s = 1 + (int)((long)b * rest / buckets);
                        int e = 1 + (int)((long)(b + 1) * rest / buckets);
                        if (e <= s) e = s + 1;
                        if (e > n) e = n;
                        r[b + 1] = ratings[e - 1];
                        t[b + 1] = times[e - 1];
                    }
                }
                else
                {
                    for (int b = 0; b < maxPoints; b++)
                    {
                        int s = (int)((long)b * n / maxPoints);
                        int e = (int)((long)(b + 1) * n / maxPoints);
                        if (e <= s) e = s + 1;
                        if (e > n) e = n;
                        // Average: the profile graph's long-standing density rule.
                        float sr = 0f; int cnt = 0;
                        for (int i = s; i < e; i++) { sr += ratings[i]; cnt++; }
                        r[b] = cnt > 0 ? sr / cnt : ratings[s];
                    }
                }
            }
            else
            {
                r = ratings.ToArray();
                if (timeAxis) t = times.ToArray();
            }

            int m = r.Length;
            if (!timeAxis)
            {
                xs = new float[m]; ys = new float[m];
                for (int i = 0; i < m; i++) { xs[i] = i; ys[i] = r[i]; }
                return true;
            }

            // Step polyline: hold the previous rating up to each new timestamp,
            // then jump. Times arrive ascending from the server; a step is never
            // allowed to run backwards if a stray timestamp ever does not.
            float t0 = t[0];
            xs = new float[2 * m - 1]; ys = new float[2 * m - 1];
            xs[0] = mode == SinceFirst ? 0f : t0; ys[0] = r[0];
            int k = 1;
            for (int i = 1; i < m; i++)
            {
                float x = mode == SinceFirst ? t[i] - t0 : t[i];
                if (x < xs[k - 1]) x = xs[k - 1];
                xs[k] = x; ys[k] = r[i - 1]; k++;
                xs[k] = x; ys[k] = r[i]; k++;
            }
            return true;
        }
    }
}
