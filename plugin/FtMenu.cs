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
    /// slot draw) at 0.5, 1.5, 3 and 5 percent of the base in turn, one level per pair. The M6 calibrations run at
    /// the first segment and at the first pair of each level cycle. One menu line per segment names its pair, arm,
    /// gate, level and c_plant. The run ends with a menu_done line (why=complete, or the input that failed, which
    /// also ends the segment in progress), then a settled line; the mode never runs again in this process and the
    /// plant returns to the sitting's own c_plant. The sentinel key menu_segments (even, 4 to 400) overrides 64.
    /// It writes the gate only from the frame boundary, as the schedule does.</summary>
    internal static class FtMenu
    {
        private const double SegS = 10.0, SettleS = 20.0;
        private static readonly string[] LevelNames = { "0.5", "1.5", "3", "5" };
        private static readonly double[] LevelPct = { 0.5, 1.5, 3.0, 5.0 };

        private static bool _done, _active;
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
                int li = -1;
                if (_baseUs > 0)
                {
                    li = _levelPairs++ % LevelNames.Length;
                    _level = LevelNames[li];
                    _levelUs = (long)Math.Round(LevelPct[li] / 100.0 * _baseUs);
                }
                else
                {
                    _level = "0";
                    _levelUs = 0;
                }
                if (_seg == 1 || li == 0) FtCalib.Run("menu" + _cycles++);
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
