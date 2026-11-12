#if SCR_FRAMETIME
using System;

namespace CompetitiveRounds
{
    /// <summary>FrameTime schedule (METHOD-V4.md 3.3, M3): the point is the unit. A point
    /// starts at the first frame boundary that reads live combat (SeatEvidence.CombatLive,
    /// the components' own predicate) while InGame holds (GameStart has run for the game and
    /// GameOver has not). It ends at the first boundary that reads combat over, or at the
    /// first boundary after GameOver or MatchEnded, or in GameStart or FlushGame when that
    /// end is still owed there (rulings R6-A3.11.99 (2), R6-A3.11.100 (3)). Live frames outside InGame belong to no point.
    /// A card pick ends a round.
    /// The arm is the WINDOW's (ruling R6-A3.11.138 (4), interleaved pairs of .137 (3)): window k of a point holds
    /// its live frames 2 + 120k to 121 + 120k, and its first live frame takes window 0's arm. With k = 4q + r, run q
    /// holds two pairs, positions 1 and 3 (unit P13) and positions 2 and 4 (unit P24); positions 1 and 2 each take a
    /// fresh coin, Mix(seed, game, round, point, 2q + r, ArmStream), ON when it is 1, and positions 3 and 4 take the
    /// opposite of their mate (the arms (A, B, 1-A, 1-B)); under force=ON or force=OFF every window takes that arm
    /// instead (ForcedArm), and coin= still names the coin. A window keeps its committed arm whether it ends full or
    /// partial. pred is the previous window's arm, carried across the points of a game and none at the game's first
    /// window. A plant run (FtPlant.RunPlanted, one run in five per game, B11 SHARED.md D4) plants its OFF windows,
    /// and the first window after it carries res=1. At each window's opening boundary the gate is set to
    /// Armed and OFF (OpenWindow), and it holds for the window unless a disarm opens it. ArmOn, GateThisPoint and
    /// PrevArm hold the open window's arm, gate and pred (FtMenu writes them per segment). A frame whose boundary
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
        internal static int PrevArm = -1;          // -1 none, 0 OFF, 1 ON: the open window's predecessor's arm
        internal static bool RoundOver = true;
        internal static long LiveFrame;            // 1 at a point's first live frame; 0 from each boundary that opens no point
        internal static bool GateThisPoint;
        internal static bool InGame;               // GameStart ran and GameOver has not: only then does Boundary open a point
        // The open window (OpenWindow): its index in the point, run q, position 1-4, unit (P24 or P13), coin, plant run
        // and res; FtFrames captures them when the window's first measured frame closes.
        internal static long WinK = -1, WinRun;
        internal static int WinPos, WinCoin;
        internal static bool WinP24, WinPlant, WinRes;
        internal const ulong ArmStream = 0xA2A1UL;
        private static int _histGame = int.MinValue;   // the game _lastArm, _lastPlant and _gameRun belong to
        private static int _lastArm = -1;              // the previous window's arm in that game (-1 none)
        private static bool _lastPlant, _runPlant;
        private static long _gameRun;                  // runs opened in that game
        private static bool _overOwed;             // GameOver or MatchEnded ran and its point end has not drained
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
            if (_flushAt > 0)
            {
                long now = System.Diagnostics.Stopwatch.GetTimestamp();
                // the settle flush follows the game's owed game-over work (its point end and its replay), waiting
                // for it at most SETTLE_S past its due time; at that cap the owed work drains here, an owed replay
                // as a call when this frame reads not live and as a skipped_live line otherwise (ruling
                // R6-A3.11.100 (3)(a)3)
                if (now >= _flushAt && !_overOwed && _replayOwed == NoReplay) FlushGame("settle");
                else if (now >= _flushAt + SETTLE_S * System.Diagnostics.Stopwatch.Frequency)
                {
                    DrainOwed(true, live ? "skipped_live" : null);
                    FlushGame("settle");
                }
            }
            FtRematch.Poll();
            FtDrive.JoinTick();
            FtDrive.SpawnTick();
            if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary
            if (FtMenu.Boundary()) return;   // the menu self-check owns this frame (menu=1, no room)
            EndOwedPoint(true);   // the first boundary after GameOver or MatchEnded: that point ends here
            bool open = live && InGame;
            if (open && !Live) StartPoint();
            else if (!open && Live) EndPoint();
            else if (!open && FtGate.Off) FtGate.Off = false;   // no point is open: the gate is clear
            Live = open;
            if (open)
            {
                LiveFrame++;
                FtSpan.Moment = FtSpan.Live;
                // window k = (LiveFrame - 2) / W opens at its first live frame (window 0 at StartPoint)
                if (LiveFrame >= 2 && (LiveFrame - 2) / FtFrames.W != WinK) OpenWindow((LiveFrame - 2) / FtFrames.W);
                // round-1 MEDIUM (FtSchedule.cs:55): only a window the armed build actually gated is planted, and only
                // inside a plant run (D4)
                FtPlant.Now = GateThisPoint && WinPlant && FtArm.Armed && FtGate.Off && LiveFrame >= 2 && FtPlant.Us > 0;
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
            // the first boundary after GameOver's point end that reads the frame not live: the replay call
            if (_replayOwed != NoReplay && !live) DrainOwed(true, null);
        }

        /// <summary>The point end GameOver or MatchEnded left owed: the open point's line (EndPoint at a boundary;
        /// elsewhere FtFrames.EndPoint, the gate left for the next boundary to write), then the game boundary.</summary>
        private static void EndOwedPoint(bool atBoundary)
        {
            if (!_overOwed) return;
            _overOwed = false;
            if (Live)
            {
                if (atBoundary) EndPoint();
                else FtFrames.EndPoint();
                Live = false;
            }
            FtFrames.GameBoundary();
        }

        /// <summary>All owed game-over work, in GameOver's order: the point end, then the replay line. skip null asks
        /// for the replay call, which only a boundary that read the frame not live, or GameStart in a frame that
        /// started not live, passes; any other caller names the reason no call is made (FtReplay.Skip). A replay
        /// owed at GameOver gets exactly one line here whatever the sentinel reads now: the call while the sentinel
        /// is present, and result=skipped_absent once it is gone (ruling R6-A3.11.101 (2)(b)).</summary>
        private static void DrainOwed(bool atBoundary, string skip)
        {
            EndOwedPoint(atBoundary);
            if (_replayOwed == NoReplay) return;
            int g = _replayOwed;
            _replayOwed = NoReplay;
            if (skip == null && !FtConfig.Present) skip = "skipped_absent";
            if (skip == null) FtReplay.Run(g);
            else FtReplay.Skip(g, skip);
        }

        private static void StartPoint()
        {
            if (RoundOver)
            {
                Round++;
                PointInRound = 0;
                RoundOver = false;
            }
            PointInRound++;
            Points++;
            FtZero.Early();
            LiveFrame = 0;
            OpenWindow(0);
            FtA3.PointStart();
            FtFrames.StartPoint();
        }

        /// <summary>Window k of the open point opens at this boundary: its committed arm by position (ruling .138
        /// (4)), its predecessor's arm, its plant run and res, then the gate.</summary>
        private static void OpenWindow(long k)
        {
            if (_histGame != Game)
            {
                _histGame = Game;
                _lastArm = -1;
                _lastPlant = false;
                _gameRun = 0;
            }
            long q = k / 4;
            int r = (int)(k % 4);
            WinCoin = (int)(Mix(FtConfig.Seed, Game, Round, PointInRound, 2 * q + (r & 1), ArmStream) & 1UL);
            if (r == 0) _runPlant = FtPlant.RunPlanted(FtConfig.Seed, Game, _gameRun++);
            WinK = k;
            WinRun = q;
            WinPos = r + 1;
            WinP24 = (r & 1) == 1;
            WinPlant = _runPlant;
            WinRes = r == 0 && _lastPlant;
            PrevArm = _lastArm;
            ArmOn = ForcedArm(r < 2 ? WinCoin == 1 : WinCoin == 0);
            _lastArm = ArmOn ? 1 : 0;
            _lastPlant = WinPlant;
            GateThisPoint = FtArm.Armed && !ArmOn;
            FtGate.Off = GateThisPoint;
        }

        /// <summary>The window's arm under the sentinel's force= (V6, SHARED.md "The window line, V6 additions"): ON
        /// under force=ON, OFF under force=OFF, the committed arm under force=none. The gate follows it (OpenWindow), so
        /// arm= is the gate's real state while the sitting is armed. FtConfig.Force is written only by FtConfig.Load,
        /// which Plugin.Awake runs once per process, so one force= holds for every game of the process.</summary>
        internal static bool ForcedArm(bool committed)
        {
            return FtConfig.Force == "ON" || (FtConfig.Force == "none" && committed);
        }

        private static void EndPoint()
        {
            FtGate.Off = false;
            FtFrames.EndPoint();
        }

        /// <summary>GameStateWatcher.OnMatchStarted: a game starts. Combat may already be live in this frame; this
        /// call opens no point, and Boundary opens none until InGame holds, which this call sets last. So the
        /// resets, the fixture read and the calibration below run with no point open, and this game's first point,
        /// and its FtZero.Early read, start at the first boundary after this call that reads live combat. On entry,
        /// work a previous game still owes runs first, in GameOver's order. A point still open has its line written
        /// here, before the game boundary and the resets, with the gate left as it is until the next boundary writes
        /// it: OnMatchStarted runs only while GameStateWatcher tracks no match, and every end of a tracked match
        /// clears InGame (GameOver, MatchEnded), so a point is open here only when that end ran in this frame. A
        /// replay still owed runs here if this frame started not live; otherwise no replay call is made, and its
        /// line says result=skipped_live. Then the previous game's accounting is finalised, after that game-over work
        /// (round-1 MEDIUM, GameStateWatcher.cs:6079). In a menu=1 process (the menu self-check, which holds no room
        /// and never arms the sitting) a game start is a failure: its line is written and nothing resets, so FtMenu
        /// keeps sole ownership of its segments (ruling R6-A3.11.101 (2)(e)).</summary>
        internal static void GameStart()
        {
            if (FtConfig.Menu)
            {
                Plugin.Log.LogWarning("[FRAME-TIME] game start failed: menu=1 process");
                return;
            }
            if (Live) { FtFrames.EndPoint(); Live = false; }
            DrainOwed(false, FrameLive ? "skipped_live" : null);
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
        /// there). The one call this makes is FtDrive.GameOver, so what it sets (FtDrive.Complete after the last
        /// game) is set within this call; the network restart it then requests is the self-drive's, not the
        /// instrument's, and the "sitting complete" line waits for that game's flush (FlushGame). The game's census,
        /// heavy and refusal lines are NOT written here: OnGameOver's own work (the collectors' Dispatch, builds,
        /// queue writes) runs after this call, and the work it defers runs in the frames that follow, so the lines
        /// are written by FlushGame once that work is in the sums (round-1 MEDIUM, GameStateWatcher.cs:6079): at the
        /// next game's start, at quit, or for the sitting's last game at the first boundary SETTLE_S seconds after it
        /// ends at which no point end or replay is owed, and at the latest SETTLE_S seconds after that.</summary>
        internal static void GameOver()
        {
            FtSpan.Moment = FtSpan.GameOver;
            InGame = false;
            _overOwed = true;
            // whether this game owes a replay line is decided here, once, by the F18 reading (reading A of a present
            // sentinel); DrainOwed then writes exactly one line for it (ruling R6-A3.11.101 (2)(b))
            _replayOwed = FtConfig.F18 == "A" && FtConfig.Present ? Game : NoReplay;
            _owed = Game;
            FtDrive.GameOver(Game);
            if (FtDrive.Complete && _flushAt == 0)
                _flushAt = System.Diagnostics.Stopwatch.GetTimestamp() + SETTLE_S * System.Diagnostics.Stopwatch.Frequency;
        }

        private const long SETTLE_S = 20;
        private static int _owed = -1;
        private static long _flushAt;

        /// <summary>GameStateWatcher, where it ends a tracked match with no OnGameOver (ResetMatchState: a room exit
        /// or a spectator quiesce; OnFfaGameOver), each right after its isTracking = false, and Plugin's Photon
        /// room callbacks (OnJoinedRoom, OnLeftRoom), first, for a leave and join the poll misses: InGame clears, and a game
        /// GameStart started owes its point end as after GameOver (the next boundary runs EndPoint, then the game
        /// boundary). No game over was reported, so it owes no replay line and no flush. Outside a game it does
        /// nothing.</summary>
        internal static void MatchEnded()
        {
            if (!InGame) return;
            InGame = false;
            _overOwed = true;
        }

        /// <summary>The ended game's lines, once, after its game-over work: census, heavy, refusals. Owed game-over
        /// work drains first on every path (ruling R6-A3.11.100 (3)(a)1): GameStart and the settle cap drain it
        /// before they call this, so what is still owed here is the quit path's, where no replay call is made and the
        /// line says skipped_quit. After the flush of the game FtDrive completed the sitting with, the "sitting
        /// complete" line.</summary>
        internal static void FlushGame(string why)
        {
            DrainOwed(false, "skipped_" + why);
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
                + " cycle_failures=" + FtClock.CycleFailures + " span_depth_violations=" + FtClock.DepthViolations
                + " photon_offmain=" + System.Threading.Interlocked.Read(ref FtSpan.PhotonOffMain)
                + " span_leave_mismatch=" + FtSpan.LeaveMismatch);
            Plugin.Log.LogInfo("[FRAME-TIME] flushed g=" + g + " why=" + why);
            if (FtDrive.Complete && g == FtDrive.CompleteGame) FtDrive.LogComplete(g);
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

        /// <summary>The seeded coin over (seed, game, round): the menu self-check's segment-pair arm (FtMenu).</summary>
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
