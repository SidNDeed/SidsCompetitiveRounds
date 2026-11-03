#if SCR_FRAMETIME
using System;
using System.Diagnostics;

namespace CompetitiveRounds
{
    /// <summary>FrameTime menu self-check (METHOD-V4.md section 6 step 2; build decision 14). It runs only with the
    /// sentinel key menu=1, in the main menu, under its own arming (FtArm.MenuCheck: the sentinel clean, the clock,
    /// the shipped probe off, the IC fixture absent, no room and no game). After 20 s armed it alternates the arm in
    /// 10 s segments, in pairs whose first arm is a seeded coin; an OFF segment sets the gate (force=ON never,
    /// force=OFF every segment). The collectors are idle in the menu, so ON against OFF is a true A/A. Each segment
    /// is a point to FtFrames (pt=-1.seg.1) with its window and point lines. Pair 0 is unplanted and its OFF
    /// segment's mean F is the base; from the next pair on, the OFF segments plant (one window in four, FtPlant's
    /// slot draw) at 3 or 5 percent of the base, one level per pair, in the repeating pattern 3, 3, 5. The M6
    /// calibrations run at the first segment and at the first pair of each pattern cycle. One menu line per segment
    /// names its pair, arm, gate, level and c_plant. The run ends with a menu_done line (why=complete, or the input
    /// that failed, which also ends the segment in progress), then a settled line; the mode never runs again in this
    /// process and the plant returns to the sitting's own c_plant. The sentinel key menu_segments (even, 4 to 400)
    /// overrides FtConfig.MenuSegmentsDefault (200). It writes the gate only from the frame boundary, as the
    /// schedule does.
    /// Ruling FRAME-TIME-ROUND-R6-A3.2 (1): the levels and the length come from the power formula, not by choice.
    /// Per planted OFF segment e_C's standard deviation is s = m x w x sqrt(1/n_p + 1/n_u) / c_plant, with w the
    /// window-to-window SD of a 120-frame window's mean C (146.6 us, the 17:35 sitting of 2026-11-03), n_p and n_u
    /// the planted and unplanted windows of a 10 s segment (one in four of 29: 7.25 and 21.75), c_plant 90 and 150 us
    /// (3 and 5 percent of a 3000 us base) and the margin m = 1.6 (that sitting's observed per-segment SE was 1.20x
    /// the model at 3 percent and 1.56x at 5): s is 1.118 at 3 percent and 0.671 at 5. The parser's interval is
    /// hw(k) = t_q(z, floor(k/2) - 1) x s / sqrt(k) at z 2.2414; k segments at a level give e_C_lo >= 0.5 with
    /// probability 0.9 at a true e_C of 1 when hw(k) + 1.2816 x s / sqrt(k) <= 0.5: k >= 66 at 3 percent, 27 at 5.
    /// The pattern 3, 3, 5 over 33 cycles gives 66 and 33 from 99 level pairs: with pair 0, 200 segments, about
    /// 34.4 minutes (20 s settle, 200 x 10 s, 34 calibrations of about 1.3 s). The 0.5 and 1.5 percent levels are
    /// gone: at 0.5 percent the same bar needs k = 280 (6.3 hours), and the method consumes e_C only at the 3
    /// percent plant (M5).</summary>
    internal static class FtMenu
    {
        private const double SegS = 10.0, SettleS = 20.0;
        private static readonly string[] LevelNames = { "3", "5" };
        private static readonly double[] LevelPct = { 3.0, 5.0 };
        // the level of each pair in turn, as indices into LevelNames: 3, 3, 5 (ruling FRAME-TIME-ROUND-R6-A3.2 (1))
        private static readonly int[] Pattern = { 0, 0, 1 };

        private static bool _done, _active;

        /// <summary>A menu self-check segment owns the frames (FtSchedule.Live is the segment's, not combat's): no
        /// menu frame is a combat point's closing frame (round-2 MEDIUM, FtClock.cs:144; FtSchedule.ClosingFrame).</summary>
        internal static bool Active => _active;
        private static string _why = "";
        private static long _armedAt, _segStart;
        private static int _seg, _levelPairs, _cycles;
        private static long _baseUs = -1, _levelUs;
        private static string _level = "0";

        /// <summary>At FT_Start, before the schedule reads live combat: true when the menu self-check owns this
        /// frame (the schedule then leaves it alone).</summary>
        internal static bool Boundary()
        {
            if (_done || !FtConfig.Menu) return false;
            string why = FtArm.MenuCheck();
            if (why != null)
            {
                if (_active)
                {
                    EndSeg();
                    Stop(why);
                    return false;
                }
                _armedAt = 0;
                if (why != _why) Plugin.Log.LogInfo("[FRAME-TIME] menu_wait input=" + why);
                _why = why;
                return false;
            }
            long now = Stopwatch.GetTimestamp();
            if (!_active)
            {
                if (_armedAt == 0)
                {
                    _armedAt = now;
                    _why = "";
                    Plugin.Log.LogInfo("[FRAME-TIME] menu_armed segments=" + FtConfig.MenuSegments + " seg_s=10 settle_s=20"
                        + " force=" + FtConfig.Force + " seed=" + FtConfig.Seed);
                }
                if (now - _armedAt < (long)(SettleS * Stopwatch.Frequency)) return false;
                _active = true;
                StartSeg(now);
            }
            else if (now - _segStart >= (long)(SegS * Stopwatch.Frequency))
            {
                EndSeg();
                if (_seg >= FtConfig.MenuSegments)
                {
                    Stop("complete");
                    return false;
                }
                StartSeg(now);
            }
            FtSchedule.LiveFrame++;
            FtSpan.Moment = FtSpan.Menu;
            FtPlant.Now = !FtSchedule.ArmOn && _levelUs > 0 && FtSchedule.LiveFrame >= 2
                && FtPlant.Planted(FtConfig.Seed, -1, _seg, 1, (FtSchedule.LiveFrame - 2) / FtFrames.W);
            FtGate.Off = FtSchedule.GateThisPoint;
            return true;
        }

        private static void StartSeg(long now)
        {
            _seg++;
            int pair = (_seg - 1) / 2;
            if ((_seg - 1) % 2 == 0)
            {
                FtSchedule.ArmOn = FtSchedule.Coin(FtConfig.Seed, -1, pair);
                int pi = -1;
                if (_baseUs > 0)
                {
                    pi = _levelPairs++ % Pattern.Length;
                    int li = Pattern[pi];
                    _level = LevelNames[li];
                    _levelUs = (long)Math.Round(LevelPct[li] / 100.0 * _baseUs);
                }
                else
                {
                    _level = "0";
                    _levelUs = 0;
                }
                if (_seg == 1 || pi == 0) FtCalib.Run("menu" + _cycles++);
            }
            else FtSchedule.ArmOn = !FtSchedule.ArmOn;
            FtPlant.SetMenu(_levelUs);
            FtSchedule.Round = _seg;
            FtSchedule.PointInRound = 1;
            FtSchedule.Live = true;
            FtSchedule.LiveFrame = 0;
            FtSchedule.GateThisPoint = FtConfig.Force == "OFF" || (FtConfig.Force == "none" && !FtSchedule.ArmOn);
            Plugin.Log.LogInfo("[FRAME-TIME] menu seg=" + _seg + " pair=" + pair + " arm=" + (FtSchedule.ArmOn ? "ON" : "OFF")
                + " gate=" + (FtSchedule.GateThisPoint ? 1 : 0) + " level=" + _level + " c_plant=" + _levelUs
                + " base_us=" + _baseUs);
            _segStart = Stopwatch.GetTimestamp();
            FtFrames.StartPoint();
        }

        private static void EndSeg()
        {
            FtFrames.EndPoint();
            FtSchedule.PrevArm = FtSchedule.ArmOn ? 1 : 0;
            if (_baseUs < 0 && !FtSchedule.ArmOn && FtFrames.LastN >= FtFrames.W)
            {
                _baseUs = (long)Math.Round(FtFrames.LastSF * 1000000.0 / ((double)FtFrames.LastN * Stopwatch.Frequency));
                Plugin.Log.LogInfo("[FRAME-TIME] menu_base base_us=" + _baseUs + " seg=" + _seg);
            }
        }

        private static void Stop(string why)
        {
            _active = false;
            _done = true;
            FtSchedule.Live = false;
            FtSchedule.LiveFrame = 0;
            FtSchedule.Round = 0;
            FtSchedule.PointInRound = 0;
            FtSchedule.PrevArm = -1;
            FtSchedule.GateThisPoint = false;
            FtGate.Off = false;
            FtPlant.Now = false;
            FtPlant.SetMenu(-1);
            Plugin.Log.LogInfo("[FRAME-TIME] menu_done why=" + why + " segs=" + _seg + " of=" + FtConfig.MenuSegments
                + " base_us=" + _baseUs + " cycles=" + _cycles);
            FtCalib.Settled(-1, FtPlant.Us);
        }
    }
}
#endif
