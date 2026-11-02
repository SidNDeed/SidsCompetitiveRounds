#if SCR_FRAMETIME
using System;

namespace CompetitiveRounds
{
    /// <summary>FrameTime schedule (METHOD-V4.md 3.3, M3): the point is the unit. A point
    /// starts at the first frame boundary that reads live combat (SeatEvidence.CombatLive,
    /// the components' own predicate) and ends at the first boundary that reads it over.
    /// Each round's first point takes a seeded coin, and the arms alternate after that.
    /// A card pick ends a round. At an OFF point's first live frame the gate is set; it is
    /// cleared when live combat ends, so outside live combat every component runs in both
    /// arms. The gate sets only while FtArm.Armed holds (part 4 supplies the full arming
    /// predicate; until then Armed is false and the schedule only logs). Boundary() runs at
    /// FT_Start after the previous frame closed, so frame f's sums carry frame f's state.</summary>
    internal static class FtSchedule
    {
        // The gate (FtGate.Off) is written only by StartPoint and EndPoint, both reached only from Boundary at
        // FT_Start, so it is constant within a frame: a patch's prefix and finalizer in one frame always decide
        // alike (an RPC cannot span a frame boundary). GameStart and GameOver may run mid-frame and never touch it.
        // The one other writer is FtCalib's dispatch calibration, which sets it around its own patched loops (nothing
        // else runs meanwhile) and restores the value it found.
        internal static int Game = -1;
        internal static int Round;
        internal static int PointInRound;
        internal static int Points;
        internal static bool Live;
        internal static bool ArmOn;
        internal static int PrevArm = -1;          // -1 none, 0 OFF, 1 ON: the previous point's arm (VR8's predecessor check)
        internal static bool RoundOver = true;
        internal static long LiveFrame;            // 1 at a point's first live frame, 0 outside live combat
        internal static bool GateThisPoint;

        internal static string Label()
        {
            return Game + "." + Round + "." + PointInRound;
        }

        /// <summary>Frame boundary: decide the state of the frame that starts now.</summary>
        internal static void Boundary()
        {
            FtArm.Evaluate();
            if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary
            bool live = SeatEvidence.CombatLive();
            if (live && !Live) StartPoint();
            else if (!live && Live) EndPoint();
            Live = live;
            if (live)
            {
                LiveFrame++;
                FtSpan.Moment = FtSpan.Live;
                FtPlant.Now = !ArmOn && LiveFrame >= 2 && FtPlant.Us > 0
                    && FtPlant.Planted(FtConfig.Seed, Game, Round, PointInRound, (LiveFrame - 2) / FtFrames.W);
                return;
            }
            LiveFrame = 0;
            FtPlant.Now = false;
            bool picking = false;
            try { picking = CardChoice.instance != null && CardChoice.instance.IsPicking; } catch { }
            if (picking)
            {
                FtSpan.Moment = FtSpan.Pick;
                RoundOver = true;
            }
            else if (Game < 0) FtSpan.Moment = FtSpan.Menu;
            else if (FtSpan.Moment != FtSpan.GameOver) FtSpan.Moment = FtSpan.Between;
        }

        private static void StartPoint()
        {
            if (RoundOver)
            {
                Round++;
                PointInRound = 0;
                RoundOver = false;
                ArmOn = Coin(FtConfig.Seed, Game, Round);
            }
            else ArmOn = !ArmOn;
            PointInRound++;
            Points++;
            FtZero.Early();
            LiveFrame = 0;
            bool off = FtConfig.Force == "OFF" || (FtConfig.Force == "none" && !ArmOn);
            GateThisPoint = FtArm.Armed && off;
            FtGate.Off = GateThisPoint;
            FtFrames.StartPoint();
        }

        private static void EndPoint()
        {
            FtGate.Off = false;
            FtFrames.EndPoint();
            PrevArm = ArmOn ? 1 : 0;
        }

        /// <summary>GameStateWatcher.OnMatchStarted: a game starts (outside live combat).</summary>
        internal static void GameStart()
        {
            Game++;
            Round = 0;
            PointInRound = 0;
            RoundOver = true;
            PrevArm = -1;
            FtSpan.Moment = FtSpan.Between;
            FtCensus.Reset();
            FtSpan.Reset();
            FtHeavy.Reset();
            FtArm.ReadFixture();
            FtCalib.Run("game" + Game);
            FtCalib.Settled(Game, FtPlant.Us);
        }

        /// <summary>GameStateWatcher.OnGameOver: the census line for the game.</summary>
        internal static void GameOver()
        {
            FtSpan.Moment = FtSpan.GameOver;
            FtReplay.Run(Game);
            FtCensus.LogGame(Game);
            FtHeavy.LogGame(Game);
            FtUpload.LogCounts("game" + Game);
        }

        /// <summary>SplitMix64 over five integers and a stream constant (the plant's slot draw).</summary>
        internal static ulong Mix(int seed, int game, int round, int point, long block, ulong stream)
        {
            ulong z = unchecked((ulong)(uint)seed * 0x9E3779B97F4A7C15UL + (ulong)(uint)game * 0xBF58476D1CE4E5B9UL
                                + (ulong)(uint)round * 0x94D049BB133111EBUL + (ulong)(uint)point * 0xD6E8FEB86659FD93UL
                                + (ulong)block * 0xA0761D6478BD642FUL + stream);
            z = unchecked((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL);
            z = unchecked((z ^ (z >> 27)) * 0x94D049BB133111EBUL);
            return z ^ (z >> 31);
        }

        /// <summary>The seeded coin for a round's first arm: SplitMix64 over (seed, game, round).</summary>
        internal static bool Coin(int seed, int game, int round)
        {
            ulong z = unchecked((ulong)(uint)seed * 0x9E3779B97F4A7C15UL + (ulong)(uint)game * 0xBF58476D1CE4E5B9UL
                                + (ulong)(uint)round * 0x94D049BB133111EBUL);
            z = unchecked((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL);
            z = unchecked((z ^ (z >> 27)) * 0x94D049BB133111EBUL);
            z ^= z >> 31;
            return (z & 1UL) == 1UL;
        }
    }

    /// <summary>The arming predicate of FORMAT-M-PLAN.md V2 part b (matchIsRanked false,
    /// the ft_ room, FT_REGION, exactly two fighters, the arm file present), evaluated on
    /// every frame the drive runs. Part 4 of the build brief implements it; until then the
    /// build never arms, so the gate never sets.</summary>
}
#endif
