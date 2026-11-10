#if SCR_FRAMETIME
using System;

namespace CompetitiveRounds
{
    /// <summary>FrameTime schedule (METHOD-V4.md 3.3, M3): the point is the unit. A point
    /// starts at the first frame boundary that reads live combat (SeatEvidence.CombatLive,
    /// the components' own predicate) while InGame holds (GameStart has run for the game and
    /// GameOver has not). It ends at the first boundary that reads combat over, or at the
    /// first boundary after GameOver, or in GameStart when one is still open there (ruling
    /// R6-A3.11.99 (2)). Live frames outside InGame belong to no point. Each round's first
    /// point takes a seeded coin, and the arms alternate after that. A card pick ends a
    /// round. At an OFF point's first live frame the gate is set. A frame whose boundary
    /// opens no point starts with the gate clear, so it runs every component in both arms
    /// (FtCalib's own loops and the menu self-check's segments aside). The gate sets only
    /// while FtArm.Armed holds (part 4 supplies the full arming
    /// predicate; until then Armed is false and the schedule only logs). Boundary() runs at
    /// FT_Start after the previous frame closed, so frame f's sums carry frame f's state.</summary>
    internal static class FtSchedule
    {
        // The gate (FtGate.Off) is written only by StartPoint, EndPoint and Boundary's own clears, all reached only
        // from Boundary at FT_Start, so it is constant within a frame: a patch's prefix and finalizer in one frame
        // always decide alike (an RPC cannot span a frame boundary). GameStart and GameOver may run mid-frame and never
        // touch it: a point GameStart ends keeps its gate value until the next boundary writes it.
        // The one other writer is FtCalib's dispatch calibration, which sets it around its own patched loops (nothing
        // else runs meanwhile) and restores the value it found. FtMenu, called from Boundary, writes it at its own
        // segment boundaries in a menu self-check process (no room, so no live combat).
        internal static int Game = -1;
        internal static int Round;
        internal static int PointInRound;
        internal static int Points;
        internal static bool Live;
        internal static bool ArmOn;
        internal static int PrevArm = -1;          // -1 none, 0 OFF, 1 ON: the previous point's arm (VR8's predecessor check)
        internal static bool RoundOver = true;
        internal static long LiveFrame;            // 1 at a point's first live frame; 0 from each boundary that opens no point
        internal static bool GateThisPoint;
        internal static bool InGame;               // GameStart ran and GameOver has not: only then does Boundary open a point
        private static bool _overOwed;             // GameOver ran and no boundary has followed: its point end is owed
        private static int _replayOwed = NoReplay; // the game whose FtReplay waits for a boundary that reads not live
        private const int NoReplay = int.MinValue;

        internal static string Label()
        {
            return Game + "." + Round + "." + PointInRound;
        }

        /// <summary>The live state of the frame that starts now, read once by FT_Start before the closed frame is
        /// accumulated (FtClock), so a point's closing frame is known before it is counted.</summary>
        internal static bool ReadLive()
        {
            return SeatEvidence.CombatLive();
        }

        /// <summary>The frame now closing was a combat point's closing frame (it started inside a point, and combat
        /// ended inside it or GameOver ran inside it, so the point ends at this boundary): left out of the point's
        /// frames. Never in the menu self-check, whose segments set Live without combat (round-2 MEDIUM,
        /// FtClock.cs:144: every menu frame was excluded); FtClock calls this before Boundary.</summary>
        internal static bool ClosingFrame(bool live)
        {
            return Live && (!live || _overOwed) && !FtMenu.Active;
        }

        /// <summary>Whether the current frame started with combat live, set once at its boundary and never changed
        /// inside the frame: GameOver's Moment write cannot hide a closing frame's heavy work from FtHeavy (round-2
        /// MEDIUM, FtHeavy.cs:44).</summary>
        internal static bool FrameLive;

        /// <summary>Frame boundary: decide the state of the frame that starts now (live: ReadLive's value).</summary>
        internal static void Boundary(bool live)
        {
            FrameLive = live;
            FtArm.Evaluate();
            // the settle flush follows the game's owed game-over work (its point end and its replay)
            if (_flushAt > 0 && !_overOwed && _replayOwed == NoReplay && System.Diagnostics.Stopwatch.GetTimestamp() >= _flushAt)
                FlushGame("settle");
            FtRematch.Poll();
            FtDrive.JoinTick();
            FtDrive.SpawnTick();
            if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary
            if (FtMenu.Boundary()) return;   // the menu self-check owns this frame (menu=1, no room)
            if (_overOwed)
            {
                // the first boundary after GameOver: the point open then ends here, before the game boundary
                _overOwed = false;
                if (Live) { EndPoint(); Live = false; }
                FtFrames.GameBoundary();
            }
            bool open = live && InGame;
            if (open && !Live) StartPoint();
            else if (!open && Live) EndPoint();
            else if (!open && FtGate.Off) FtGate.Off = false;   // no point is open: the gate is clear
            Live = open;
            if (open)
            {
                LiveFrame++;
                FtSpan.Moment = FtSpan.Live;
                // round-1 MEDIUM (FtSchedule.cs:55): only a point the armed build actually gated is planted
                FtPlant.Now = GateThisPoint && FtArm.Armed && FtGate.Off && LiveFrame >= 2 && FtPlant.Us > 0
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
            if (_replayOwed != NoReplay && !live)
            {
                // the first boundary after GameOver's point end that reads the frame not live
                int g = _replayOwed;
                _replayOwed = NoReplay;
                FtReplay.Run(g);
            }
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
            FtA3.PointStart();
            FtFrames.StartPoint();
        }

        private static void EndPoint()
        {
            FtGate.Off = false;
            FtFrames.EndPoint();
            PrevArm = ArmOn ? 1 : 0;
        }

        /// <summary>GameStateWatcher.OnMatchStarted: a game starts. Combat may already be live in this frame; this
        /// call opens no point, and Boundary opens none until InGame holds, which this call sets last. So the
        /// resets, the fixture read and the calibration below run with no point open, and this game's first point,
        /// and its FtZero.Early read, start at the first boundary after this call that reads live combat. On entry,
        /// work a previous game still owes runs first. A point still open (its game ended without GameOver, or
        /// GameOver ran with no boundary since) has its line written here, before the game boundary and the resets,
        /// with the gate left as it is until the next boundary writes it. When GameOver ran with no boundary since,
        /// its replay runs here if this frame started not live, and otherwise no replay call is made (under reading
        /// A its answer_replay line says result=skipped_live). Then the previous game's accounting is finalised,
        /// after that game-over work (round-1 MEDIUM, GameStateWatcher.cs:6079).</summary>
        internal static void GameStart()
        {
            if (Live) { FtFrames.EndPoint(); Live = false; }
            _overOwed = false;
            if (_replayOwed != NoReplay)
            {
                int g = _replayOwed;
                _replayOwed = NoReplay;
                if (FrameLive) FtReplay.Skip(g);
                else FtReplay.Run(g);
            }
            FlushGame("next_game");
            FtFrames.GameBoundary();
            Game++;
            Round = 0;
            PointInRound = 0;
            RoundOver = true;
            PrevArm = -1;
            FtSpan.Moment = FtSpan.Between;
            FtCensus.Reset();
            FtSpan.Reset();
            FtHeavy.Reset();
            FtA3.Reset();
            FtArm.ReadFixture();
            FtCalib.Run("game" + Game);
            FtCalib.Settled(Game, FtPlant.Us);
            InGame = true;
        }

        /// <summary>GameStateWatcher.OnGameOver, at its start: records that the game is over. The game-over moment
        /// begins, InGame clears so no further point opens, and the point open now, if any, is not ended here: the
        /// next boundary ends it (EndPoint, this frame left out as its closing frame) and then takes the game
        /// boundary (FtFrames.GameBoundary), unless GameStart runs first and does both, as stated there. FtReplay
        /// runs at the first boundary from that one on that reads the frame not live (or at GameStart, as stated
        /// there). The one call this makes is FtDrive.GameOver, unchanged in place, so what it sets (FtDrive.Complete
        /// after the last game) is set within this call; the network restart it then requests is the self-drive's,
        /// not the instrument's. The game's census, heavy and refusal lines are NOT written here: OnGameOver's own work (the collectors' Dispatch, builds, queue writes) runs after this call, and the
        /// work it defers runs in the frames that follow, so the lines are written by FlushGame once that work is in
        /// the sums (round-1 MEDIUM, GameStateWatcher.cs:6079): at the next game's start, at quit, or for the
        /// sitting's last game at the first boundary SETTLE_S seconds after it ends at which no point end or replay
        /// is owed.</summary>
        internal static void GameOver()
        {
            FtSpan.Moment = FtSpan.GameOver;
            InGame = false;
            _overOwed = true;
            _replayOwed = Game;
            _owed = Game;
            FtDrive.GameOver(Game);
            if (FtDrive.Complete && _flushAt == 0)
                _flushAt = System.Diagnostics.Stopwatch.GetTimestamp() + SETTLE_S * System.Diagnostics.Stopwatch.Frequency;
        }

        private const long SETTLE_S = 20;
        private static int _owed = -1;
        private static long _flushAt;

        /// <summary>The ended game's lines, once, after its game-over work: census, heavy, refusals.</summary>
        internal static void FlushGame(string why)
        {
            if (_owed < 0) return;
            int g = _owed;
            _owed = -1;
            // 0, not -1: GameOver arms the settle flush only from 0, so a -1 left by game 0's flush made the last
            // game's settle flush unreachable (round-2 MEDIUM, FtSchedule.cs:141)
            _flushAt = 0;
            FtCensus.LogGame(g);
            FtHeavy.LogGame(g);
            FtA3.LogGame(g);
            FtUpload.LogCounts("game" + g);
            // round-3 MEDIUM (FtSchedule.cs:140): the game's settled line is written at its start, before its play;
            // this snapshot, after the game's work, is what VR2 judges for the game's frames (the last game's included)
            Plugin.Log.LogInfo("[FRAME-TIME] counters g=" + g + " frames=" + FtClock.Frames + " missing_end=" + FtClock.MissingEnd
                + " cycle_failures=" + FtClock.CycleFailures + " span_depth_violations=" + FtClock.DepthViolations);
            Plugin.Log.LogInfo("[FRAME-TIME] flushed g=" + g + " why=" + why);
        }

        /// <summary>After the three collectors' BeginGame calls (GameStateWatcher.OnMatchStarted): whether each
        /// opened this game's collection (V4 3.7 VR5's first requirement).</summary>
        internal static void Opened()
        {
            Plugin.Log.LogInfo("[FRAME-TIME] opened g=" + Game + " se=" + (SeatEvidence.FtOpen ? 1 : 0)
                + " ce=" + (CombatEvidence.FtOpen ? 1 : 0) + " ic=" + (IdentityClockEvidence.FtOpen ? 1 : 0));
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
}
#endif
