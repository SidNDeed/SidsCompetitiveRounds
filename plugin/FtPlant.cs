#if SCR_FRAMETIME
using System.Diagnostics;

namespace CompetitiveRounds
{
    /// <summary>FrameTime M5 (METHOD-V4.md 3.1 and 3.5): the plant. At OFF points one
    /// 120-frame window in four runs a busy spin of c_plant microseconds at the start of
    /// Update, timed by Stopwatch. The windows of a point fall in blocks of four; in each
    /// block the planted slot is a SplitMix64 draw over seed, game, round, point and block,
    /// so exactly one window in four is planted and the choice is reproducible from the
    /// logged seed. c_plant = round(0.03 x the mean F of the session's first OFF point with
    /// a full unplanted window), fixed for the process and logged on its own line and on
    /// every settled line, unless the sentinel's plant_us names a value (0 turns the plant
    /// off, and with it e_C and U). Until c_plant is fixed nothing is planted. The parser
    /// keeps planted windows out of the OFF means and uses them only for e_C (V4 3.5) and
    /// VR7. The spin runs outside every component span.</summary>
    internal static class FtPlant
    {
        internal static long Us = -1;     // c_plant in microseconds; -1 until fixed
        internal static bool Now;         // the frame in progress is planted (FtSchedule.Boundary)
        private static long _ticks;

        internal static void Init()
        {
            if (FtConfig.PlantUs >= 0) Fix(FtConfig.PlantUs, "sentinel");
        }

        internal static void Fix(long us, string from)
        {
            if (Us >= 0) return;
            if (us < 0) us = 0;
            Us = us;
            _ticks = us * Stopwatch.Frequency / 1000000;
            Plugin.Log.LogInfo("[FRAME-TIME] plant c_plant=" + us + " ticks=" + _ticks + " from=" + from);
        }

        /// <summary>Whether measured window j of the point (0-based) is planted.</summary>
        internal static bool Planted(int seed, int game, int round, int point, long window)
        {
            long block = window / 4;
            long slot = (long)(FtSchedule.Mix(seed, game, round, point, block, 0x51A7UL) & 3UL);
            return window % 4 == slot;
        }

        /// <summary>The menu self-check's level (FtMenu): us >= 0 sets the spin of its planted windows; -1
        /// returns it to the sitting's own c_plant (none while that is unfixed).</summary>
        internal static void SetMenu(long us)
        {
            long u = us >= 0 ? us : (Us > 0 ? Us : 0);
            _ticks = u * Stopwatch.Frequency / 1000000;
        }

        internal static void OnUpdate()
        {
            if (!Now || _ticks <= 0) return;
            long until = Stopwatch.GetTimestamp() + _ticks;
            while (Stopwatch.GetTimestamp() < until) { }
        }
    }
}
#endif
