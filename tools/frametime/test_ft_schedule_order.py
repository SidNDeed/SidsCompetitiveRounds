"""FtSchedule's game-edge order (rulings R6-A3.11.99 and R6-A3.11.100): the scheduler's order ported to Python, the C#
bodies pinned statement by statement to the port, the measured sequences driven through it, and GameStateWatcher's
match ends checked against the instrument's game.

The measured sequences (w9, LogOutput-match.log): combat went live before GameStateWatcher.OnMatchStarted called
FtSchedule.GameStart, in every game; and in game 4 OnGameOver ran FtSchedule.GameOver inside the frame in which combat
ended. At c28259c1 the first opened a point before GameStart, whose resets then ran inside it; the second ran
FtReplay's calls inside a frame that started live.

Assertions, each run on the tip's order (must hold) and on a mutant (must fail):
  A1 no point straddles GameStart (its resets and calibration run with no point open; a point's label never changes);
  A2 no baseline is taken before a reset that follows it (a point's end reads the sums of the reset epoch its start
     read, and its delta is what it accrued);
  A3 per game: each GameOver(g) gives exactly one answer_replay line for g after it, a replay call in a frame that
     started not live or a skip line where no call may run (skipped_live in a frame that started live, skipped_quit
     at quit); no line for a game with no game over;
  A4 a point opens only inside a game GameStart has started and neither GameOver nor MatchEnded has ended;
  A5 per game: each game with a game over is flushed exactly once, after every point end of the game and after its
     replay line;
  A6 the frame in which GameOver or MatchEnded ran inside an open point is that point's closing frame;
  A7 the "sitting complete" line: exactly one when the sitting completed, after its last game's flush and replay line;
  A8 the settle cap: the last game is flushed by the boundary SETTLE_S past the settle's due time at the latest;
  A9 every opened point has exactly one end record, before its game's next boundary and its game's flush (N4);
  A10 in a menu=1 process GameStart writes its failure line and resets nothing (ruling R6-A3.11.101 (2)(e)).
A3 counts the games that owe a replay (reading A with the sentinel present at GameOver), and admits skipped_absent
where a call was allowed but the sentinel had gone (N2). Plugin's Photon room callbacks end the game as a match end
(N1); the caller sets of ResetMatchState and MatchEnded are pinned, and no match end is reachable from a start (N3).
GameStateWatcher (F2): every isTracking = false is an OnGameOver after FtSchedule.GameOver, or a hooked
FtSchedule.MatchEnded; OnMatchStarted runs only with isTracking false; a port of those guards, enumerated over every
event sequence of length 5, keeps InGame equal to "a match OnMatchStarted started is being tracked".
Run: python -I -B -m pytest tools/frametime/test_ft_schedule_order.py -q"""
import itertools
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
OLD_SHA = "c28259c1"


def _src(name):
    return (PLUGIN / name).read_text(encoding="utf-8-sig")


def _block(text, start):
    """(index of the first '{' at or after start, index just past its matching '}')."""
    j = text.index("{", start)
    depth = 0
    for k in range(j, len(text)):
        if text[k] == "{":
            depth += 1
        elif text[k] == "}":
            depth -= 1
            if depth == 0:
                return j, k + 1
    raise AssertionError("unbalanced block at %d" % start)


def _body(src, signature):
    assert src.count(signature) == 1, "%s: %d occurrences" % (signature, src.count(signature))
    j, k = _block(src, src.index(signature))
    return [ln.strip() for ln in src[j + 1:k - 1].splitlines() if ln.strip()]


def _span(src, signature):
    j, k = _block(src, src.index(signature))
    return j, k


SIG_CLOSING = "internal static bool ClosingFrame(bool live)"
SIG_BOUNDARY = "internal static void Boundary(bool live)"
SIG_START = "private static void StartPoint()"
SIG_END = "private static void EndPoint()"
SIG_ENDOWED = "private static void EndOwedPoint(bool atBoundary)"
SIG_DRAIN = "private static void DrainOwed(bool atBoundary, string skip)"
SIG_GAMESTART = "internal static void GameStart()"
SIG_GAMEOVER = "internal static void GameOver()"
SIG_MATCHENDED = "internal static void MatchEnded()"
SIG_FLUSH = "internal static void FlushGame(string why)"
SIG_DRIVE_OVER = "internal static void GameOver(int game)"
SIG_DRIVE_LOG = "internal static void LogComplete(int game)"
SIG_FR_START = "internal static void StartPoint()"
SIG_FR_END = "internal static void EndPoint()"

_FLUSH_TAIL = [
    'if (_owed < 0) return;',
    'int g = _owed;',
    '_owed = -1;',
    "// 0, not -1: GameOver arms the settle flush only from 0, so a -1 left by game 0's flush made the last",
    "// game's settle flush unreachable (round-2 MEDIUM, FtSchedule.cs:141)",
    '_flushAt = 0;',
    'FtCensus.LogGame(g);',
    'FtHeavy.LogGame(g);',
    'FtA3.LogGame(g);',
    'FtUpload.LogCounts("game" + g);',
    "// round-3 MEDIUM (FtSchedule.cs:140): the game's settled line is written at its start, before its play;",
    "// this snapshot, after the game's work, is what VR2 judges for the game's frames (the last game's included)",
    'Plugin.Log.LogInfo("[FRAME-TIME] counters g=" + g + " frames=" + FtClock.Frames + " missing_end=" + FtClock.MissingEnd',
    '+ " cycle_failures=" + FtClock.CycleFailures + " span_depth_violations=" + FtClock.DepthViolations);',
    'Plugin.Log.LogInfo("[FRAME-TIME] flushed g=" + g + " why=" + why);',
]

_OLD_BOUNDARY_TAIL = [
    'bool open = live && InGame;',
    'if (open && !Live) StartPoint();',
    'else if (!open && Live) EndPoint();',
    'else if (!open && FtGate.Off) FtGate.Off = false;   // no point is open: the gate is clear',
    'Live = open;',
    'if (open)',
    '{',
    'LiveFrame++;',
    'FtSpan.Moment = FtSpan.Live;',
    '// round-1 MEDIUM (FtSchedule.cs:55): only a point the armed build actually gated is planted',
    'FtPlant.Now = GateThisPoint && FtArm.Armed && FtGate.Off && LiveFrame >= 2 && FtPlant.Us > 0',
    '&& FtPlant.Planted(FtConfig.Seed, Game, Round, PointInRound, (LiveFrame - 2) / FtFrames.W);',
    'return;',
    '}',
    'LiveFrame = 0;',
    'FtPlant.Now = false;',
    'bool picking = false;',
    'try { picking = CardChoice.instance != null && CardChoice.instance.IsPicking; } catch { }',
    'if (picking)',
    '{',
    'FtSpan.Moment = FtSpan.Pick;',
    'RoundOver = true;',
    '}',
    'else if (Game < 0) FtSpan.Moment = FtSpan.Menu;',
    'else if (FtSpan.Moment != FtSpan.GameOver) FtSpan.Moment = FtSpan.Between;',
]

# B11 P1 (ruling R6-A3.11.138 (4)): the window opens at its first live frame and the plant is the plant run's
_BOUNDARY_TAIL = _OLD_BOUNDARY_TAIL[:9] + [
    '// window k = (LiveFrame - 2) / W opens at its first live frame (window 0 at StartPoint)',
    'if (LiveFrame >= 2 && (LiveFrame - 2) / FtFrames.W != WinK) OpenWindow((LiveFrame - 2) / FtFrames.W);',
    '// round-1 MEDIUM (FtSchedule.cs:55): only a window the armed build actually gated is planted, and only',
    '// inside a plant run (D4)',
    'FtPlant.Now = GateThisPoint && WinPlant && FtArm.Armed && FtGate.Off && LiveFrame >= 2 && FtPlant.Us > 0;',
] + _OLD_BOUNDARY_TAIL[12:]

# the point start and end as at c28259c1 and bd673226 (point arms; OLD below and the mutants mirror these)
_OLD_START = [
    'if (RoundOver)',
    '{',
    'Round++;',
    'PointInRound = 0;',
    'RoundOver = false;',
    'ArmOn = Coin(FtConfig.Seed, Game, Round);',
    '}',
    'else ArmOn = !ArmOn;',
    'PointInRound++;',
    'Points++;',
    'FtZero.Early();',
    'LiveFrame = 0;',
    'bool off = FtConfig.Force == "OFF" || (FtConfig.Force == "none" && !ArmOn);',
    'GateThisPoint = FtArm.Armed && off;',
    'FtGate.Off = GateThisPoint;',
    'FtA3.PointStart();',
    'FtFrames.StartPoint();',
]
_OLD_END = [
    'FtGate.Off = false;',
    'FtFrames.EndPoint();',
    'PrevArm = ArmOn ? 1 : 0;',
]

# ------------------------------------------------------------------ the tip's bodies (the port below mirrors each)

TIP = {
    SIG_CLOSING: [
        'return Live && (!live || _overOwed) && !FtMenu.Active;',
    ],
    SIG_BOUNDARY: [
        'FrameLive = live;',
        'FtArm.Evaluate();',
        'if (_flushAt > 0)',
        '{',
        'long now = System.Diagnostics.Stopwatch.GetTimestamp();',
        "// the settle flush follows the game's owed game-over work (its point end and its replay), waiting",
        '// for it at most SETTLE_S past its due time; at that cap the owed work drains here, an owed replay',
        '// as a call when this frame reads not live and as a skipped_live line otherwise (ruling',
        '// R6-A3.11.100 (3)(a)3)',
        'if (now >= _flushAt && !_overOwed && _replayOwed == NoReplay) FlushGame("settle");',
        'else if (now >= _flushAt + SETTLE_S * System.Diagnostics.Stopwatch.Frequency)',
        '{',
        'DrainOwed(true, live ? "skipped_live" : null);',
        'FlushGame("settle");',
        '}',
        '}',
        'FtRematch.Poll();',
        'FtDrive.JoinTick();',
        'FtDrive.SpawnTick();',
        'if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary',
        'if (FtMenu.Boundary()) return;   // the menu self-check owns this frame (menu=1, no room)',
        'EndOwedPoint(true);   // the first boundary after GameOver or MatchEnded: that point ends here',
    ] + _BOUNDARY_TAIL + [
        "// the first boundary after GameOver's point end that reads the frame not live: the replay call",
        'if (_replayOwed != NoReplay && !live) DrainOwed(true, null);',
    ],
    SIG_START: [
        'if (RoundOver)',
        '{',
        'Round++;',
        'PointInRound = 0;',
        'RoundOver = false;',
        '}',
        'PointInRound++;',
        'Points++;',
        'FtZero.Early();',
        'LiveFrame = 0;',
        'OpenWindow(0);',
        'FtA3.PointStart();',
        'FtFrames.StartPoint();',
    ],
    SIG_END: [
        'FtGate.Off = false;',
        'FtFrames.EndPoint();',
    ],
    SIG_ENDOWED: [
        'if (!_overOwed) return;',
        '_overOwed = false;',
        'if (Live)',
        '{',
        'if (atBoundary) EndPoint();',
        'else FtFrames.EndPoint();',
        'Live = false;',
        '}',
        'FtFrames.GameBoundary();',
    ],
    SIG_DRAIN: [
        'EndOwedPoint(atBoundary);',
        'if (_replayOwed == NoReplay) return;',
        'int g = _replayOwed;',
        '_replayOwed = NoReplay;',
        'if (skip == null && !FtConfig.Present) skip = "skipped_absent";',
        'if (skip == null) FtReplay.Run(g);',
        'else FtReplay.Skip(g, skip);',
    ],
    SIG_GAMESTART: [
        'if (FtConfig.Menu)',
        '{',
        'Plugin.Log.LogWarning("[FRAME-TIME] game start failed: menu=1 process");',
        'return;',
        '}',
        'if (Live) { FtFrames.EndPoint(); Live = false; }',
        'DrainOwed(false, FrameLive ? "skipped_live" : null);',
        'FlushGame("next_game");',
        'FtFrames.GameBoundary();',
        'Game++;',
        'Round = 0;',
        'PointInRound = 0;',
        'RoundOver = true;',
        'PrevArm = -1;',
        'FtSpan.Moment = FtSpan.Between;',
        'FtCensus.Reset();',
        'FtSpan.Reset();',
        'FtHeavy.Reset();',
        'FtA3.Reset();',
        'FtArm.ReadFixture();',
        'FtCalib.Run("game" + Game);',
        'FtCalib.Settled(Game, FtPlant.Us);',
        'InGame = true;',
    ],
    SIG_GAMEOVER: [
        'FtSpan.Moment = FtSpan.GameOver;',
        'InGame = false;',
        '_overOwed = true;',
        '// whether this game owes a replay line is decided here, once, by the F18 reading (reading A of a present',
        '// sentinel); DrainOwed then writes exactly one line for it (ruling R6-A3.11.101 (2)(b))',
        '_replayOwed = FtConfig.F18 == "A" && FtConfig.Present ? Game : NoReplay;',
        '_owed = Game;',
        'FtDrive.GameOver(Game);',
        'if (FtDrive.Complete && _flushAt == 0)',
        '_flushAt = System.Diagnostics.Stopwatch.GetTimestamp() + SETTLE_S * System.Diagnostics.Stopwatch.Frequency;',
    ],
    SIG_MATCHENDED: [
        'if (!InGame) return;',
        'InGame = false;',
        '_overOwed = true;',
    ],
    SIG_FLUSH: ['DrainOwed(false, "skipped_" + why);'] + _FLUSH_TAIL + [
        'if (FtDrive.Complete && g == FtDrive.CompleteGame) FtDrive.LogComplete(g);',
    ],
}

TIP_DRIVE = {
    SIG_DRIVE_OVER: [
        'if (game < LAST_GAME || Complete) return;',
        'Complete = true;',
        'CompleteGame = game;',
        'try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }',
    ],
    SIG_DRIVE_LOG: [
        'if (_completeLogged) return;',
        '_completeLogged = true;',
        'Plugin.Log.LogInfo("[FRAME-TIME] sitting complete g=" + game);',
    ],
}

# F3: FtFrames' baselines and subtractions, whole bodies (the order of every statement, no reset among them)
TIP_FRAMES = {
    SIG_FR_START: [
        'if (_btT0 >= 0)',
        'Plugin.Log.LogInfo("[FRAME-TIME] between g=" + FtSchedule.Game + " after=" + _btArm + " ticks=" + (BetweenTicks() - _btT0)',
        '+ " calls=" + (BetweenCalls() - _btC0));',
        '_btT0 = -1;',
        '_wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0; _wP = 0;',
        'ResetPartition();',
        '_pn = 0; _pF = 0; _pS = 0; _pC = 0; _pMaxF = 0; _pMissingEnd = 0; _pP = 0; _excl = 0;',
        '_qn = 0; _qF = 0; _qS = 0; _qC = 0; _plantMixed = 0; _qP = 0;',
        '_g0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);',
        '_gn0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);',
        '_u0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep);',
        '_un0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep);',
        '_on0 = FtCensus.SumOn();',
        '_guard0 = FtCensus.SumGuarded();',
        '_vG = _g0; _vGn = _gn0; _vOn = _on0; _vGd = _guard0;',
        '_offG = 0; _offGn = 0; _offOn = 0; _onGuarded = 0;',
        '_offN = 0; _offF = 0; _ownSplit = 0;',
        '_windows = 0;',
        '_ptLabel = FtSchedule.Label();',
        '_ptArm = FtSchedule.ArmOn;',
        '_ptGate = FtSchedule.GateThisPoint;',
        '_ptPred = FtSchedule.PrevArm;',
        '_ptLastArm = _ptArm;',
        '_ptOpen = true;',
        'FtLedger.Take(_lb);',
        'FtLedger.SockTake(_sk0);',
        '_t0 = System.Diagnostics.Stopwatch.GetTimestamp();',
    ],
    SIG_FR_END: [
        'if (!_ptOpen) return;',
        '_ptOpen = false;',
        'if (_wn > 0) FlushWindow(true);',
        'Vr5Take(FtGate.Off);',
        'FtLedger.SockTake(_sk1);',
        'Plugin.Log.LogInfo("[FRAME-TIME] p pt=" + _ptLabel + " arm=" + (_ptArm ? "ON" : "OFF")',
        '+ " gate=" + (_ptGate ? 1 : 0)',
        '+ " pred=" + Arm(_ptPred)',
        '+ " n=" + _pn + " sF=" + _pF + " sS=" + _pS + " sC=" + _pC + " maxF=" + _pMaxF',
        '+ " pn=" + _qn + " psF=" + _qF + " psS=" + _qS + " psC=" + _qC + " sP=" + _pP + " psP=" + _qP',
        '+ " excl=" + _excl + " plant_mixed=" + _plantMixed',
        '+ " windows=" + _windows + " live_frames=" + FtSchedule.LiveFrame + " missing_end=" + _pMissingEnd',
        '+ " span_g=" + (FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated) - _g0)',
        '+ " span_gn=" + (FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated) - _gn0)',
        '+ " span_u=" + (FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep) - _u0)',
        '+ " span_un=" + (FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep) - _un0)',
        '+ " on_calls=" + (FtCensus.SumOn() - _on0) + " guarded=" + (FtCensus.SumGuarded() - _guard0)',
        '+ " zs=" + FtZero.Mask + " zl=" + FtZero.LateSeen',
        '+ " t0=" + _t0 + " t1=" + System.Diagnostics.Stopwatch.GetTimestamp() + " answer=" + FtReplay.AnswerField',
        '+ " off_g=" + _offG + " off_gn=" + _offGn + " off_on=" + _offOn + " on_guarded=" + _onGuarded',
        '+ " own_split=" + _ownSplit + " span_class_overflow=" + FtSpan.ClassOverflow',
        '+ " gc_read_failures=" + FtSpan.GcReadFailures + " recv_offmain=" + FtLedger.RecvOffMain',
        '+ " ledger_cycle_miss=" + FtLedger.CycleMiss + " " + FtLedger.SockStats(_sk0, _sk1));',
        'LastN = _pn;',
        'LastSF = _pF;',
        '_btT0 = BetweenTicks();',
        '_btC0 = BetweenCalls();',
        '_btArm = _ptLastArm ? "ON" : "OFF";',
        'if (FtPlant.Us < 0 && FtSchedule.Game >= 0 && _offN >= W)',
        'FtPlant.Fix((long)Math.Round(0.03 * _offF * 1000000.0 / ((double)_offN * System.Diagnostics.Stopwatch.Frequency)),',
        '_ptLabel);',
    ],
}

# B11 P1: the window schedule, ownership, the partition, the plant run and the writer ledger, whole bodies
SIG_OPENWIN = 'private static void OpenWindow(long k)'
SIG_MIX = 'internal static ulong Mix(int seed, int game, int round, int point, long block, ulong stream)'
SIG_FR_FRAME = 'internal static void Frame(long f, long s, ulong c, ulong p, int gc0, int gc1, bool ended, bool closing,'
SIG_FR_CURK = 'private static long CurrentK()'
SIG_FR_OWNER = 'private static void CaptureOwner()'
SIG_FR_VR5 = 'private static void Vr5Take(bool off)'
SIG_FR_FLUSH = 'private static void FlushWindow(bool partial)'
SIG_FR_RESETP = 'private static void ResetPartition()'
SIG_SP_MARK = 'private static void Mark(ulong k, long g, bool gok)'
SIG_SP_SWITCH = 'private static void Switch(int cls)'
SIG_SP_CUT = 'internal static void Cut(ulong k, long g, bool gok)'
SIG_SP_REBASE = 'internal static void Rebase(long g, bool gok)'
SIG_SP_OPEN = 'internal static bool Open(int component, int kind)'
SIG_SP_CLOSE = 'internal static void Close(bool opened)'
SIG_SP_PUSHW = 'internal static void PushWriter()'
SIG_SP_POPW = 'internal static void PopWriter()'
SIG_SP_CAL = 'internal static void CalibrateMarks(int n)'
SIG_CL_START = 'private static void OnStart()'
SIG_CL_GCREAD = 'internal static bool GcRead(System.Func<long> fn, out long g)'
SIG_PL_RUN = 'internal static bool RunPlanted(int seed, int game, long run)'
SIG_LG_WRITELINE = 'public override void WriteLine(string value)'
SIG_LG_FLUSH = 'public override void Flush()'
SIG_LG_TAKE = 'internal static void Take(long[] into)'
SIG_LG_LEVEL = 'internal static long Level(long[] s, int t)'
SIG_LG_WU = 'internal static void AppendWu(StringBuilder sb, long[] a, long[] b)'
SIG_LG_TOK = 'internal static void AppendTok(StringBuilder sb, long[] a, long[] b)'
SIG_LG_ENQ = 'private static void Enq(int t, long n)'
SIG_LG_SERVE = 'private static void Serve(int t, long n, bool ok, ulong k0, ulong k1)'
SIG_LG_HBEGIN = 'internal static ulong HashBegin()'
SIG_LG_HEND = 'internal static void HashEnd(ulong k0, bool ok)'
SIG_LG_RENTER = 'internal static ulong RecvEnter()'
SIG_LG_REXIT = 'internal static void RecvExit(ulong k0)'
SIG_LG_RCYC = 'internal static void RecvCycles(ulong k0)'
SIG_LG_SBUCKET = 'internal static int SockBucket(long c)'
SIG_LG_SENTER = 'internal static ulong SockEnter()'
SIG_LG_SEXIT = 'internal static void SockExit(ulong k0)'
SIG_LG_STAKE = 'internal static void SockTake(long[] into)'
SIG_LG_STATS = 'internal static string SockStats(long[] a, long[] b)'
SIG_LG_SEDGES = 'private static long[] SockEdges()'
SIG_SOCK_TARGET = 'private static MethodBase TargetMethod()'
SIG_SOCK_PRE = 'private static void Prefix(out ulong __state)'
SIG_SOCK_FIN = 'private static void Finalizer(ulong __state)'

TIP_P1_SCHED = {
    SIG_OPENWIN: [
        'if (_histGame != Game)',
        '{',
        '_histGame = Game;',
        '_lastArm = -1;',
        '_lastPlant = false;',
        '_gameRun = 0;',
        '}',
        'long q = k / 4;',
        'int r = (int)(k % 4);',
        'WinCoin = (int)(Mix(FtConfig.Seed, Game, Round, PointInRound, 2 * q + (r & 1), ArmStream) & 1UL);',
        'if (r == 0) _runPlant = FtPlant.RunPlanted(FtConfig.Seed, Game, _gameRun++);',
        'WinK = k;',
        'WinRun = q;',
        'WinPos = r + 1;',
        'WinP24 = (r & 1) == 1;',
        'WinPlant = _runPlant;',
        'WinRes = r == 0 && _lastPlant;',
        'PrevArm = _lastArm;',
        'ArmOn = r < 2 ? WinCoin == 1 : WinCoin == 0;',
        '_lastArm = ArmOn ? 1 : 0;',
        '_lastPlant = WinPlant;',
        'bool off = FtConfig.Force == "OFF" || (FtConfig.Force == "none" && !ArmOn);',
        'GateThisPoint = FtArm.Armed && off;',
        'FtGate.Off = GateThisPoint;',
    ],
    SIG_MIX: [
        'ulong z = unchecked((ulong)(uint)seed * 0x9E3779B97F4A7C15UL + (ulong)(uint)game * 0xBF58476D1CE4E5B9UL',
        '+ (ulong)(uint)round * 0x94D049BB133111EBUL + (ulong)(uint)point * 0xD6E8FEB86659FD93UL',
        '+ (ulong)block * 0xA0761D6478BD642FUL + stream);',
        'z = unchecked((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL);',
        'z = unchecked((z ^ (z >> 27)) * 0x94D049BB133111EBUL);',
        'return z ^ (z >> 31);',
    ],
}

TIP_P1_FRAMES = {
    SIG_FR_FRAME: [
        'if (!FtSchedule.Live) return;',
        'Vr5Take(FtGate.Off);',
        'if (FtSchedule.LiveFrame < 2)',
        '{',
        "FtLedger.Take(_lb);   // the point's first live frame closed: window 0 starts with the next frame",
        'return;',
        '}',
        'if (closing) { _excl++; return; }   // combat ended inside this frame: partial, never measured',
        'if (_wn > 0 && (CurrentK() != _oK || FtSchedule.Game != _oGame || FtSchedule.Round != _oRound || FtSchedule.PointInRound != _oPoint))',
        '{',
        '_ownSplit++;',
        'FlushWindow(true);',
        '}',
        'if (!ended) _pMissingEnd++;',
        'if (_wn == 0) { _wGc0 = gc0; _wPlant = FtPlant.Now; CaptureOwner(); }',
        'else if (FtPlant.Now != _wPlant) _plantMixed++;',
        '_wGc1 = gc1;',
        'int bin = _wn / Bin;',
        'WinF[_wn++] = f;',
        '_wF += f; _wS += s; _wC += c; _wP += p;',
        'if (f > _wMaxF) _wMaxF = f;',
        'if (_wPlant) { _qn++; _qF += f; _qS += s; _qC += c; _qP += p; }',
        'else { _pn++; _pF += f; _pS += s; _pC += c; _pP += p; }',
        'if (f > _pMaxF) _pMaxF = f;',
        'if (!gok) _wGok = false;',
        '_wG += cg; _wW += cw; _wR += cr; _wS2 += cs; _wE += ce;',
        '_tq[bin] += unchecked((long)c) - cg - cw;',
        '_tr[bin] += cr;',
        '_tn[bin]++;',
        'FtLedger.Take(_le);',
        'if (_wn == W) FlushWindow(false);',
    ],
    SIG_FR_CURK: [
        'return FtMenu.Active ? (FtSchedule.LiveFrame - 2) / W : FtSchedule.WinK;',
    ],
    SIG_FR_OWNER: [
        '_oPt = FtSchedule.Label();',
        '_oGame = FtSchedule.Game; _oRound = FtSchedule.Round; _oPoint = FtSchedule.PointInRound;',
        '_oK = CurrentK();',
        '_oF0 = FtSchedule.LiveFrame;',
        '_oArm = FtSchedule.ArmOn;',
        'if (FtMenu.Active)',
        '{',
        '// a menu segment holds one arm: its windows follow position by index, with no coin of their own',
        '_oRun = _oK / 4; _oPos = (int)(_oK % 4) + 1; _oP24 = (_oK & 1) == 1; _oCoin = _oArm ? 1 : 0;',
        '_oPred = _oK == 0 ? FtSchedule.PrevArm : (_oArm ? 1 : 0);',
        '_oPlantRun = false; _oRes = false;',
        '}',
        'else',
        '{',
        '_oRun = FtSchedule.WinRun; _oPos = FtSchedule.WinPos; _oP24 = FtSchedule.WinP24; _oCoin = FtSchedule.WinCoin;',
        '_oPred = FtSchedule.PrevArm; _oPlantRun = FtSchedule.WinPlant; _oRes = FtSchedule.WinRes;',
        '}',
        '_ptLastArm = _oArm;',
    ],
    SIG_FR_VR5: [
        'long g = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);',
        'long gn = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);',
        'long on = FtCensus.SumOn();',
        'long gd = FtCensus.SumGuarded();',
        'if (off) { _offG += g - _vG; _offGn += gn - _vGn; _offOn += on - _vOn; }',
        'else _onGuarded += gd - _vGd;',
        '_vG = g; _vGn = gn; _vOn = on; _vGd = gd;',
    ],
    SIG_FR_FLUSH: [
        '_windows++;',
        'if (!partial && !_oArm && !_wPlant) { _offN += _wn; _offF += _wF; }',
        'var sb = new StringBuilder(512);',
        'sb.Append("[FRAME-TIME] w pt=").Append(_oPt).Append(" arm=").Append(_oArm ? "ON" : "OFF")',
        '.Append(" plant=").Append(_wPlant ? 1 : 0).Append(" partial=").Append(partial ? 1 : 0).Append(" n=").Append(_wn).Append(" sF=").Append(_wF)',
        '.Append(" sS=").Append(_wS).Append(" sC=").Append(_wC).Append(" sP=").Append(_wP).Append(" maxF=").Append(_wMaxF);',
        'if (!partial)',
        '{',
        'long med = LowerMedian();',
        'sb.Append(" medF=").Append(med);',
        'for (int h = 0; h < HMs.Length; h++)',
        '{',
        'long ticks = HMs[h] * System.Diagnostics.Stopwatch.Frequency / 1000;',
        'int kmin, kmax;',
        'RunBounds(med, ticks, out kmin, out kmax);',
        'sb.Append(" e").Append(HMs[h]).Append(\'=\').Append(kmin).Append(\',\').Append(kmax);',
        '}',
        '}',
        'sb.Append(" gc=").Append(_wGc1 - _wGc0);   // first measured frame\'s start to the last one\'s end',
        'sb.Append(" run=").Append(_oRun).Append(" pos=").Append(_oPos).Append(" unit=").Append(_oP24 ? "P24" : "P13")',
        '.Append(" coin=").Append(_oCoin).Append(" wi=").Append(_oK).Append(" f0=").Append(_oF0)',
        '.Append(" pred=").Append(Arm(_oPred)).Append(" prun=").Append(_oPlantRun ? 1 : 0).Append(" res=").Append(_oRes ? 1 : 0)',
        '.Append(" gcn=").Append(_wGc1 - _wGc0).Append(" cG=");',
        'if (_wGok) sb.Append(_wG); else sb.Append("NA");',
        'sb.Append(" cW=").Append(_wW).Append(" cR=").Append(_wR).Append(" cS=").Append(_wS2).Append(" cE=").Append(_wE);',
        'AppendBins(sb, " q=", _tq);',
        'AppendBins(sb, " r=", _tr);',
        'AppendBins(sb, " qn=", _tn);',
        'sb.Append(" wu=");',
        'FtLedger.AppendWu(sb, _lb, _le);',
        'sb.Append(" tok=");',
        'FtLedger.AppendTok(sb, _lb, _le);',
        'sb.Append(" nm=").Append(FtLedger.Marks(_lb, _le));',
        'Plugin.Log.LogInfo(sb.ToString());',
        'Array.Copy(_le, _lb, FtLedger.Fields);',
        '_wn = 0; _wF = 0; _wS = 0; _wC = 0; _wMaxF = 0; _wP = 0;',
        'ResetPartition();',
    ],
    SIG_FR_RESETP: [
        '_wG = 0; _wW = 0; _wR = 0; _wS2 = 0; _wE = 0; _wGok = true;',
        'for (int j = 0; j < Bins; j++) { _tq[j] = 0; _tr[j] = 0; _tn[j] = 0; }',
    ],
}

TIP_P1_SPAN = {
    SIG_SP_MARK: [
        'long d = unchecked((long)(k - _k));',
        'if (gok && _gok) d -= g - _g;',
        'Acc[_cls] += d;',
        '_k = k;',
        '_g = g;',
        '_gok = gok;',
    ],
    SIG_SP_SWITCH: [
        'Marks++;',
        'long g;',
        'bool gok = FtClock.GcRead(FtClock.GcFn, out g);',
        'Mark(FtClock.Cycles(), g, gok);',
        '_cls = cls;',
    ],
    SIG_SP_CUT: [
        'Mark(k, g, gok);',
    ],
    SIG_SP_REBASE: [
        '_g = g;',
        '_gok = gok;',
    ],
    SIG_SP_OPEN: [
        'if (Thread.CurrentThread.ManagedThreadId != MainThread) { Interlocked.Increment(ref OffThread); return false; }',
        'int d = _depth++;',
        'if (d < StackCap)',
        '{',
        '_prev[d] = _cls;',
        'int cls = _cls == ClsW ? ClsW : ClassOfKind[kind];',
        'if (cls != _cls) Switch(cls);',
        '}',
        'else ClassOverflow++;',
        'if (d != 0) return false;',
        '_component = component;',
        '_kind = kind;',
        '_t0 = Stopwatch.GetTimestamp();',
        'return true;',
    ],
    SIG_SP_CLOSE: [
        'if (Thread.CurrentThread.ManagedThreadId != MainThread) return;',
        'int d = --_depth;',
        'if (opened)',
        '{',
        'long dt = Stopwatch.GetTimestamp() - _t0;',
        'int i = Index(_component, Moment, FtClock.InScript ? 0 : 1, _kind);',
        'Ticks[i] += dt;',
        'Calls[i]++;',
        '}',
        'if (d >= 0 && d < StackCap && _prev[d] != _cls) Switch(_prev[d]);',
    ],
    SIG_SP_PUSHW: [
        'int d = _depth++;',
        'if (d < StackCap)',
        '{',
        '_prev[d] = _cls;',
        'if (_cls != ClsW) Switch(ClsW);',
        '}',
        'else ClassOverflow++;',
    ],
    SIG_SP_POPW: [
        'int d = --_depth;',
        'if (d >= 0 && d < StackCap && _prev[d] != _cls) Switch(_prev[d]);',
    ],
    SIG_SP_CAL: [
        'var acc = (long[])Acc.Clone();',
        'int cls = _cls;',
        'ulong k = _k;',
        'long g = _g, marks = Marks;',
        'bool gok = _gok;',
        'var s = new long[n];',
        'for (int i = 0; i < n; i++)',
        '{',
        'ulong a = FtClock.Cycles();',
        'Switch((i & 1) == 0 ? ClsS : ClsR);',
        's[i] = unchecked((long)(FtClock.Cycles() - a));',
        '}',
        'System.Array.Copy(acc, Acc, Classes);',
        '_cls = cls;',
        '_k = k;',
        '_g = g;',
        '_gok = gok;',
        'Marks = marks;',
        'System.Array.Sort(s);',
        'Plugin.Log.LogInfo("[FRAME-TIME] mark cost cyc=" + s[(n - 1) / 2] + " p90=" + s[(int)((n - 1) * 9L / 10)] + " n=" + n);',
    ],
}

TIP_P1_CLOCK = {
    SIG_CL_START: [
        'long t = Stopwatch.GetTimestamp();',
        'ulong k = Cycles();',
        'ulong pk = ProcessCycles();',
        'int gc = GC.CollectionCount(0);',
        'long g;',
        'bool gok = GcRead(GcFn, out g);',
        'FtSpan.Cut(k, g, gok);',
        'bool live = FtSchedule.ReadLive();',
        'if (_open)',
        '{',
        'Frames++;',
        'if (!_ended) MissingEnd++;',
        'bool fok = gok && _gOk && FtSpan.GcReadFailures == _gcFail0;',
        'long[] a = FtSpan.Acc;',
        'OnFrameClosed(t - _t0, _ended ? _s : 0, k - _k0, pk - _p0, _gc0, gc, _ended, FtSchedule.ClosingFrame(live),',
        'fok ? g - _gPrev : 0, fok, a[FtSpan.ClsW] - _acc0[FtSpan.ClsW], a[FtSpan.ClsR] - _acc0[FtSpan.ClsR],',
        'a[FtSpan.ClsS] - _acc0[FtSpan.ClsS], a[FtSpan.ClsE] - _acc0[FtSpan.ClsE]);',
        '}',
        'System.Array.Copy(FtSpan.Acc, _acc0, FtSpan.Classes);',
        'var fn = GcCycles;   // the hook, read once per frame: a hook set or changed counts from this frame on',
        'if (fn != GcFn)',
        '{',
        'GcFn = fn;',
        'gok = GcRead(fn, out g);',
        'FtSpan.Rebase(g, gok);',
        '}',
        '_gPrev = g;',
        '_gOk = gok;',
        '_gcFail0 = FtSpan.GcReadFailures;',
        '_t0 = t;',
        '_k0 = k;',
        '_p0 = pk;',
        '_gc0 = gc;',
        '_s = 0;',
        '_ended = false;',
        '_open = true;',
        'if (!_marksCal)',
        '{',
        '_marksCal = true;   // once, at the first frame boundary: before game 0',
        'FtSpan.CalibrateMarks(MarkCalN);',
        '}',
        'if (FtSpan.Depth != 0) DepthViolations++;',
        'InScript = true;',
        'FtSchedule.Boundary(live);',
    ],
    SIG_CL_GCREAD: [
        'g = 0;',
        'if (fn == null) return false;',
        'try { g = fn(); return true; }',
        'catch { FtSpan.GcReadFailures++; return false; }',
    ],
}

TIP_P1_PLANT = {
    SIG_PL_RUN: [
        'long block = run / 5;',
        'long slot = (long)(FtSchedule.Mix(seed, game, 0, 0, block, RunStream) % 5UL);',
        'return run % 5 == slot;',
    ],
}

TIP_P1_LEDGER = {
    SIG_LG_WRITELINE: [
        'if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread || !FtSpan.CollectorOpen)',
        '{',
        '_in.WriteLine(value);',
        'return;',
        '}',
        'FtSpan.PushWriter();',
        'try { _in.WriteLine(value); }',
        'finally { FtSpan.PopWriter(); }',
        '// counted after the write, so a concurrent flush can never mark done a line not yet in the buffer',
        'lock (_lock) { _c[Log * Per + (FtGate.Off ? EnqOff : EnqOn)]++; _pendingLog++; }',
    ],
    SIG_LG_FLUSH: [
        'ulong k0 = FtClock.Cycles();',
        '_in.Flush();',
        'ulong k1 = FtClock.Cycles();',
        'long n;',
        'lock (_lock) { n = _pendingLog; _pendingLog = 0; }',
        '// the whole flush is charged to the lines it carries (ruled conservative, SHARED.md D5); a flush that',
        '// carries none charges nothing',
        'if (n > 0) Serve(Log, n, true, k0, k1);',
    ],
    SIG_LG_TAKE: [
        'lock (_lock) System.Array.Copy(_c, into, Nm);',
        'into[Nm] = FtSpan.Marks;',
    ],
    SIG_LG_LEVEL: [
        'int b = t * Per;',
        'return s[b + EnqOn] + s[b + EnqOff] - s[b + DoneOn] - s[b + DoneOff] - s[b + Disc];',
    ],
    SIG_LG_WU: [
        'for (int t = 0; t < Types; t++)',
        '{',
        'int o = t * Per;',
        "if (t > 0) sb.Append(';');",
        '#if SCR_FT_NOCOLLECTORS',
        'if (t == Sock) { sb.Append(TypeNames[t]).Append(":NA:NA"); continue; }',
        '#endif',
        "sb.Append(TypeNames[t]).Append(':').Append(b[o + Units] - a[o + Units]).Append(':').Append(b[o + Cyc] - a[o + Cyc]);",
        '}',
    ],
    SIG_LG_TOK: [
        'for (int t = 0; t < Types; t++)',
        '{',
        'int o = t * Per;',
        "if (t > 0) sb.Append(';');",
        "sb.Append(TypeNames[t]).Append(':').Append(Level(a, t))",
        ".Append(',').Append(b[o + EnqOn] - a[o + EnqOn]).Append(',').Append(b[o + EnqOff] - a[o + EnqOff])",
        ".Append(',').Append(b[o + DoneOn] - a[o + DoneOn]).Append(',').Append(b[o + DoneOff] - a[o + DoneOff])",
        ".Append(',').Append(b[o + Disc] - a[o + Disc]).Append(',').Append(Level(b, t));",
        '}',
    ],
    SIG_LG_ENQ: [
        'lock (_lock) _c[t * Per + (FtGate.Off ? EnqOff : EnqOn)] += n;',
    ],
    SIG_LG_SERVE: [
        'long c = 0;',
        'if (k0 == 0 || k1 == 0) Interlocked.Increment(ref CycleMiss); else c = unchecked((long)(k1 - k0));',
        'lock (_lock)',
        '{',
        'int o = t * Per;',
        'if (ok) { _c[o + (FtGate.Off ? DoneOff : DoneOn)] += n; _c[o + Units] += n; }',
        'else _c[o + Disc] += n;',
        '_c[o + Cyc] += c;',
        '}',
    ],
    SIG_LG_HBEGIN: [
        'Enq(Hash, 1);',
        'return FtClock.Cycles();',
    ],
    SIG_LG_HEND: [
        'Serve(Hash, 1, ok, k0, FtClock.Cycles());',
    ],
    SIG_LG_RENTER: [
        'if (Thread.CurrentThread.ManagedThreadId != FtSpan.MainThread) Interlocked.Increment(ref RecvOffMain);',
        'Enq(Recv, 1);',
        'return FtClock.Cycles();',
    ],
    SIG_LG_REXIT: [
        'Serve(Recv, 1, true, k0, FtClock.Cycles());',
    ],
    SIG_LG_RCYC: [
        'Serve(Recv, 0, true, k0, FtClock.Cycles());',
    ],
    SIG_LG_SBUCKET: [
        'int i = System.Array.BinarySearch(SockEdge, c);',
        'return i >= 0 ? i + 1 : ~i;',
    ],
    SIG_LG_SENTER: [
        'int id = Thread.CurrentThread.ManagedThreadId;',
        'if (id == FtSpan.MainThread) Interlocked.Increment(ref SockMain);',
        'if (id != _sockThread)',
        '{',
        'if (_sockThread != -1) Interlocked.Increment(ref SockSwitches);',
        '_sockThread = id;',
        '}',
        'lock (_lock) _c[Sock * Per + EnqOn]++;',
        'return FtClock.Cycles();',
    ],
    SIG_LG_SEXIT: [
        'ulong k1 = FtClock.Cycles();',
        'Serve(Sock, 1, true, k0, k1);',
        'long c = k0 == 0 || k1 == 0 ? 0 : unchecked((long)(k1 - k0));',
        'Interlocked.Increment(ref _sockHist[SockBucket(c)]);',
    ],
    SIG_LG_STAKE: [
        'for (int i = 0; i < SockBuckets; i++) into[i] = Interlocked.Read(ref _sockHist[i]);',
        'into[SockBuckets] = Interlocked.Read(ref SockMain);',
        'into[SockBuckets + 1] = Interlocked.Read(ref SockSwitches);',
    ],
    SIG_LG_STATS: [
        'long n = 0;',
        'for (int i = 0; i < SockBuckets; i++) n += b[i] - a[i];',
        'string p95 = "NA";',
        'if (n > 0)',
        '{',
        'long rank = (95 * n + 99) / 100, cum = 0;',
        'for (int i = 0; i < SockBuckets; i++)',
        '{',
        'cum += b[i] - a[i];',
        'if (cum < rank) continue;',
        'if (i < SockEdge.Length) p95 = SockEdge[i].ToString();',
        'break;',
        '}',
        '}',
        'return "sock_p95=" + p95 + " sock_n=" + n + " sock_thr=" + (b[SockBuckets + 1] - a[SockBuckets + 1])',
        '+ " sock_main=" + (b[SockBuckets] - a[SockBuckets]);',
    ],
    SIG_LG_SEDGES: [
        'var e = new long[SockBuckets - 1];',
        'long prev = 0;',
        'for (int i = 0; i < e.Length; i++)',
        '{',
        'long v = (long)System.Math.Ceiling(System.Math.Pow(2.0, (i + 1) / 4.0));',
        'e[i] = v > prev ? v : prev + 1;',
        'prev = e[i];',
        '}',
        'return e;',
    ],
    SIG_SOCK_TARGET: [
        'var m = AccessTools.Method(typeof(ExitGames.Client.Photon.IPhotonSocket), "HandleReceivedDatagram",',
        'new[] { typeof(byte[]), typeof(int), typeof(bool) });',
        'if (m == null) throw new System.Exception("IPhotonSocket.HandleReceivedDatagram(byte[], int, bool) not found - no sock scope");',
        'return m;',
    ],
    SIG_SOCK_PRE: [
        '__state = FtLedger.SockEnter();',
    ],
    SIG_SOCK_FIN: [
        'FtLedger.SockExit(__state);',
    ],
}

# ------------------------------------------------------------------ the c28259c1 bodies (the mutants mirror these)

OLD = {
    SIG_CLOSING: [
        'return Live && !live && !FtMenu.Active;',
    ],
    SIG_BOUNDARY: [
        'FrameLive = live;',
        'FtArm.Evaluate();',
        'if (_flushAt > 0 && System.Diagnostics.Stopwatch.GetTimestamp() >= _flushAt) FlushGame("settle");',
        'FtRematch.Poll();',
        'FtDrive.JoinTick();',
        'FtDrive.SpawnTick();',
        'if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary',
        'if (FtMenu.Boundary()) return;   // the menu self-check owns this frame (menu=1, no room)',
        'if (live && !Live) StartPoint();',
        'else if (!live && Live) EndPoint();',
        'Live = live;',
        'if (live)',
    ] + _OLD_BOUNDARY_TAIL[6:],
    SIG_START: _OLD_START,
    SIG_END: _OLD_END,
    SIG_GAMESTART: [
        'FlushGame("next_game");',
        'FtFrames.GameBoundary();',
        'Game++;',
        'Round = 0;',
        'PointInRound = 0;',
        'RoundOver = true;',
        'PrevArm = -1;',
        'FtSpan.Moment = FtSpan.Between;',
        'FtCensus.Reset();',
        'FtSpan.Reset();',
        'FtHeavy.Reset();',
        'FtA3.Reset();',
        'FtArm.ReadFixture();',
        'FtCalib.Run("game" + Game);',
        'FtCalib.Settled(Game, FtPlant.Us);',
    ],
    SIG_GAMEOVER: [
        'FtSpan.Moment = FtSpan.GameOver;',
        'FtFrames.GameBoundary();',
        'FtReplay.Run(Game);',
        '_owed = Game;',
        'FtDrive.GameOver(Game);',
        'if (FtDrive.Complete && _flushAt == 0)',
        '_flushAt = System.Diagnostics.Stopwatch.GetTimestamp() + SETTLE_S * System.Diagnostics.Stopwatch.Frequency;',
    ],
    SIG_FLUSH: _FLUSH_TAIL,
}

OLD_DRIVE = {
    SIG_DRIVE_OVER: [
        'if (game < LAST_GAME || Complete) return;',
        'Complete = true;',
        'Plugin.Log.LogInfo("[FRAME-TIME] sitting complete g=" + game);',
        'try { NetworkConnectionHandler.instance?.NetworkRestart(); } catch { }',
    ],
}


# ------------------------------------------------------------------ source checks (each returns its violations)

HOOK = 'try { FtSchedule.MatchEnded(); } catch (Exception ex) { Plugin.Log.LogWarning("[FRAME-TIME] game end failed: " + ex.Message); }'
SIG_RESET = "private static void ResetMatchState()"
SIG_FFA_OVER = "public static void OnFfaGameOver(int winnerTeam)"
SIG_GSW_OVER = "private static void OnGameOver(int winnerTeam)"
SIG_OMS = "private static void OnMatchStarted()"


def _sources():
    return {n: _src(n) for n in ("FtSchedule.cs", "FtDrive.cs", "FtFrames.cs", "FtSpan.cs", "FtCensus.cs",
                                 "FtReplay.cs", "FtClock.cs", "GameStateWatcher.cs", "FtCalib.cs", "FtPlant.cs",
                                 "FtUpload.cs")}


def pin_violations(srcs):
    """The scheduler's bodies against the port, FtDrive's completion split, FtFrames' bodies (F3), and every reset
    of the span and census sums (the class F3 names: a reset anywhere but GameStart, or an absolute write to those
    sums anywhere but their Reset bodies and FtCalib's two restores, is a violation)."""
    bad = []
    for name, table in (("FtSchedule.cs", TIP), ("FtDrive.cs", TIP_DRIVE), ("FtFrames.cs", TIP_FRAMES),
                        ("FtSchedule.cs", TIP_P1_SCHED), ("FtFrames.cs", TIP_P1_FRAMES), ("FtSpan.cs", TIP_P1_SPAN),
                        ("FtClock.cs", TIP_P1_CLOCK), ("FtPlant.cs", TIP_P1_PLANT), ("FtUpload.cs", TIP_P1_LEDGER)):
        for sig, want in table.items():
            try:
                got = _body(srcs[name], sig)
            except (AssertionError, ValueError) as ex:
                bad.append("%s %s: %s" % (name, sig, ex))
                continue
            if got != want:
                bad.append("%s %s: body differs from the port" % (name, sig))
    resets = []
    for name, text in srcs.items():
        for m in re.finditer(r"\b(FtSpan|FtCensus)\.Reset\(\)", text):
            resets.append((name, m.start()))
    sched = srcs["FtSchedule.cs"]
    try:
        j, k = _span(sched, SIG_GAMESTART)
    except ValueError:
        j, k = 0, 0
    inside = [r for r in resets if r[0] == "FtSchedule.cs" and j < r[1] < k]
    if len(resets) != 2 or len(inside) != 2:
        bad.append("span/census resets outside GameStart: %s" % [r for r in resets if r not in inside])
    writes = re.compile(r"\b(?:FtSpan\.|FtCensus\.)?(Ticks|Calls|OnLive|Guarded|Outside)\[[^\]]*\]\s*(?:=(?!=)|-=)")
    for name, text in srcs.items():
        for m in writes.finditer(text):
            if name == "FtSpan.cs" and m.group(1) in ("Ticks", "Calls"):
                rj, rk = _span(text, "internal static void Reset()")
                if rj < m.start() < rk:
                    continue
            if name == "FtCensus.cs" and m.group(1) in ("OnLive", "Guarded", "Outside"):
                rj, rk = _span(text, "internal static void Reset()")
                if rj < m.start() < rk:
                    continue
            if name == "FtCalib.cs" and text[m.start():m.end()].startswith("FtCensus.Guarded["):
                continue   # the calibration's restore of the count it read (FtCalib.cs, two sites)
            if name in ("FtSpan.cs", "FtCensus.cs") or text[m.start():m.end()].startswith(("FtSpan.", "FtCensus.")):
                bad.append("%s: absolute write %r" % (name, text[m.start():m.end()]))
    if srcs["FtCalib.cs"].count("FtCensus.Guarded[") != 4:
        bad.append("FtCalib.cs: the Guarded restores changed (%d reads/writes)" % srcs["FtCalib.cs"].count("FtCensus.Guarded["))
    return bad


def _code_lines(text):
    """(offset, stripped code) per line, comments and preprocessor-free text kept as is."""
    out, off = [], 0
    for ln in text.splitlines(keepends=True):
        s = ln.strip()
        if s and not s.startswith("//"):
            out.append((off, s.split("//", 1)[0].strip() if not s.startswith("#") else s))
        off += len(ln)
    return out


def gsw_violations(src):
    """F2 (ruling R6-A3.11.100 (3)(b)): the match ends GameStateWatcher has, and why each hooked one is an end.
    1. Every isTracking = false is in OnGameOver after its FtSchedule.GameOver call, or immediately followed by the
       MatchEnded hook (ResetMatchState, OnFfaGameOver): once it runs, OnGameOver's first guard returns, so the game
       GameStart started gets no OnGameOver, and the hook is that game's end.
    2. OnMatchStarted, the only GameStart caller, is called only under a !isTracking guard, and sets isTracking with
       no return between its GameStart call and that write: a start never runs inside a tracked match.
    3. The hooked bodies never start: no isTracking = true, no OnMatchStarted or GameStart call."""
    bad = []
    spans = {}
    for sig in (SIG_RESET, SIG_FFA_OVER, SIG_GSW_OVER, SIG_OMS):
        if src.count(sig) != 1:
            bad.append("%s: %d occurrences" % (sig, src.count(sig)))
            return bad
        spans[sig] = _span(src, sig)
    lines = _code_lines(src)
    over_call = src.find("FtSchedule.GameOver();", spans[SIG_GSW_OVER][0])
    for i, (off, s) in enumerate(lines):
        if s != "isTracking = false;":
            continue
        nxt = [x[1] for x in lines[i + 1:i + 3]]
        hooked = nxt == ["#if SCR_FRAMETIME", HOOK]
        j, k = spans[SIG_GSW_OVER]
        if j < off < k and off > over_call > 0:
            continue
        if hooked and any(spans[s_][0] < off < spans[s_][1] for s_ in (SIG_RESET, SIG_FFA_OVER)):
            continue
        bad.append("isTracking = false at offset %d is neither after FtSchedule.GameOver nor hooked" % off)
    for sig in (SIG_RESET, SIG_FFA_OVER):
        body = src[spans[sig][0]:spans[sig][1]]
        if body.count(HOOK) != 1:
            bad.append("%s: %d MatchEnded hooks" % (sig, body.count(HOOK)))
        for start in ("isTracking = true", "OnMatchStarted(", "FtSchedule.GameStart"):
            if start in body:
                bad.append("%s starts a match (%s)" % (sig, start))
    calls = [m.start() for m in re.finditer(r"(?<![\w.])OnMatchStarted\(\);", src)]
    if len(calls) != 2:
        bad.append("%d OnMatchStarted call sites (pinned 2)" % len(calls))
    for c in calls:
        before = [s for off, s in lines if off < c][-3:]
        if not any(s.startswith("if (") and "!isTracking" in s for s in before):
            bad.append("OnMatchStarted call at offset %d has no !isTracking guard" % c)
    if src.count("FtSchedule.GameStart();") != 1:
        bad.append("FtSchedule.GameStart has %d call sites" % src.count("FtSchedule.GameStart();"))
    j, k = spans[SIG_OMS]
    oms = src[j:k]
    a, b = oms.find("FtSchedule.GameStart();"), oms.find("isTracking = true;")
    if not 0 < a < b or re.search(r"\breturn\b", oms[a:b]):
        bad.append("OnMatchStarted: a return between GameStart and isTracking = true, or the order changed")
    head = _body(src, SIG_GSW_OVER)[:5]
    if head[1:3] != ["if (!isTracking || gameOverReported) return;", "gameOverReported = true;"] \
            or not head[4].startswith("try { FtSchedule.GameOver(); }"):
        bad.append("OnGameOver's guards or its GameOver call moved: %s" % head)
    return bad


def _code_only(text):
    """text with comments and string/char literal contents blanked (offsets and newlines kept)."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a, b):
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c == '"':
            verbatim = (i > 0 and text[i - 1] == "@") or (i > 1 and text[i - 2:i] in ("$@", "@$"))
            j = i + 1
            while j < n:
                if verbatim:
                    if text[j] == '"':
                        if j + 1 < n and text[j + 1] == '"':
                            j += 2
                            continue
                        break
                else:
                    if text[j] == "\\":
                        j += 2
                        continue
                    if text[j] in '"\n':
                        break
                j += 1
            blank(i + 1, j)
            i = j + 1
            continue
        if c == "'":
            j = i + 2 if i + 1 < n and text[i + 1] == "\\" else i + 1
            j += 1
            if j < n and text[j] == "'":
                blank(i + 1, j)
                i = j + 1
                continue
        i += 1
    return "".join(out)


_SIG_RE = re.compile(r"(?m)^[ \t]*(?:(?:public|private|internal|protected|static|override|virtual|async|unsafe)\s+)+"
                     r"[\w<>\[\],.?]+\s+(\w+)\s*\((?:[^()]|\([^()]*\))*\)\s*\{")


def _methods(code):
    """[(name, open-brace offset, end offset)] of the methods in a comment- and string-blanked text."""
    out = []
    for m in _SIG_RE.finditer(code):
        j, k = _block(code, m.end() - 1)
        out.append((m.group(1), j, k))
    return out


def _enclosing(methods, off):
    best = None
    for name, j, k in methods:
        if j < off < k and (best is None or j > best[1]):
            best = (name, j, k)
    return best


def _inside_if(code, off, cond):
    """off lies inside the braced block of an `if` whose condition text is cond."""
    for m in re.finditer(re.escape(cond), code):
        if m.start() < off:
            try:
                j, k = _block(code, m.end())
            except (AssertionError, ValueError):
                continue
            if code[m.end():j].strip() == "" and j < off < k:
                return True
    return False


_RESET_CALL = re.compile(r"(?<![\w.])(?<!void )ResetMatchState\(\)|(?<=GameStateWatcher\.)ResetMatchState\(\)")
_TRAIL_CALL = re.compile(r"(?<![\w.])(?<!void )ResetMatchStateWithTrail\(\)|(?<=GameStateWatcher\.)ResetMatchStateWithTrail\(\)")
_END_CALL = re.compile(r"(?<![\w.])(?<!void )MatchEnded\(\)|(?<=FtSchedule\.)MatchEnded\(\)")
# the pinned caller sets (ruling R6-A3.11.101 (2)(c)): (file, enclosing method) -> the guard each site sits under
RESET_CALLERS = {("GameStateWatcher.cs", "Poll"): ("if (RoomActors.LocalIsSpectator)", "if (!spectatorQuiesced)"),
                 ("GameStateWatcher.cs", "PollRoomState"): ("if (!inRoom && wasInRoom)",),
                 ("GameStateWatcher.cs", "ResetMatchStateWithTrail"): ()}
END_CALLERS = {("GameStateWatcher.cs", "ResetMatchState"), ("GameStateWatcher.cs", "OnFfaGameOver"),
               ("Plugin.cs", "OnJoinedRoom"), ("Plugin.cs", "OnLeftRoom")}
# where a match end can be reached from: none of these may be reachable from a start
END_ROOTS = {"ResetMatchState", "ResetMatchStateWithTrail", "MatchEnded", "OnFfaGameOver", "OnJoinedRoom",
             "OnLeftRoom", "Poll", "PollRoomState"}
GRAPH_FILES = {"GameStateWatcher": "GameStateWatcher.cs", "FtSchedule": "FtSchedule.cs", "Plugin": "Plugin.cs"}


def _all_sources():
    return {f.name: f.read_text(encoding="utf-8-sig") for f in sorted(PLUGIN.glob("*.cs"))}


def caller_violations(srcs):
    """N3 (ruling R6-A3.11.101 (2)(c)): the exact caller sets of ResetMatchState and MatchEnded, each site with its
    guard; ResetMatchStateWithTrail has no caller; Plugin's two room-callback hooks are each the callback's first
    statement; and no match end is reachable from OnMatchStarted or FtSchedule.GameStart (a name-resolved call graph
    over GameStateWatcher, FtSchedule and Plugin, followed to its closure)."""
    bad = []
    code = {n: _code_only(t) for n, t in srcs.items()
            if "ResetMatchState" in t or "MatchEnded" in t or n in GRAPH_FILES.values()}
    meth = {n: _methods(c) for n, c in code.items()}
    resets, ends, trails = [], [], 0
    for n, c in code.items():
        for m in _RESET_CALL.finditer(c):
            e = _enclosing(meth[n], m.start())
            resets.append((n, e[0] if e else None, m.start()))
        for m in _END_CALL.finditer(c):
            e = _enclosing(meth[n], m.start())
            ends.append((n, e[0] if e else None, m.start()))
        trails += len(_TRAIL_CALL.findall(c))
    if sorted((n, e) for n, e, _ in resets) != sorted(RESET_CALLERS):
        bad.append("ResetMatchState callers %s, pinned %s" % (sorted((n, e) for n, e, _ in resets), sorted(RESET_CALLERS)))
    for n, e, off in resets:
        for cond in RESET_CALLERS.get((n, e), ()):
            if not _inside_if(code[n], off, cond):
                bad.append("ResetMatchState in %s is not under %s" % (e, cond))
    if trails:
        bad.append("ResetMatchStateWithTrail has %d callers (pinned none)" % trails)
    if sorted((n, e) for n, e, _ in ends) != sorted(END_CALLERS):
        bad.append("MatchEnded callers %s, pinned %s" % (sorted((n, e) for n, e, _ in ends), sorted(END_CALLERS)))
    for n, e, off in ends:
        if n == "Plugin.cs":
            body = [s for _, s in _code_lines(srcs[n][_enclosing(meth[n], off)[1]:])][1:3]
            if body != ["#if SCR_FRAMETIME", HOOK]:
                bad.append("Plugin.%s: the hook is not the first statement: %s" % (e, body))
        if e == "OnFfaGameOver":
            j = _enclosing(meth[n], off)[1]
            if "if (gameOverReported) return;" not in srcs[n][j:off]:
                bad.append("OnFfaGameOver's hook is not under its gameOverReported guard")
    # the call graph: bare names resolve in the same file, Class.Name( in that class's file
    index = {}
    for cls, fname in GRAPH_FILES.items():
        for name, j, k in meth.get(fname, []):
            index.setdefault((fname, name), []).append((j, k))
    starts = [("GameStateWatcher.cs", "OnMatchStarted"), ("FtSchedule.cs", "GameStart")]
    seen, todo = set(starts), list(starts)
    while todo:
        fname, name = todo.pop()
        if name in END_ROOTS:
            bad.append("%s.%s, a match end, is reachable from a start" % (fname, name))
            continue
        for j, k in index.get((fname, name), []):
            body = code[fname][j:k]
            nxt = [(fname, m.group(1)) for m in re.finditer(r"(?<![\w.])(\w+)\s*\(", body)]
            nxt += [(GRAPH_FILES[m.group(1)], m.group(2))
                    for m in re.finditer(r"\b(GameStateWatcher|FtSchedule|Plugin)\.(\w+)\s*\(", body)]
            for node in nxt:
                if node[1] in END_ROOTS or (node in index and node not in seen):
                    if node not in seen:
                        seen.add(node)
                        todo.append(node)
    return bad


def test_callers_hold():
    assert caller_violations(_all_sources()) == []


_OMS_TRACK = "            isTracking = true;\n            gameOverReported = false;\n"
_HOOK_LINE = "            " + HOOK + "\n"
CALLER_MUTANTS = {
    # Codex's N3 mutant: ResetMatchState() appended to OnMatchStarted
    "n3_reset_in_oms": ("GameStateWatcher.cs", SIG_OMS, _OMS_TRACK, _OMS_TRACK + "            ResetMatchState();\n"),
    # a MatchEnded call at a start: in FtSchedule.GameStart, and in OnMatchStarted
    "n3_matchended_in_gamestart": ("FtSchedule.cs", SIG_GAMESTART, "            InGame = true;\n",
                                   "            InGame = true;\n            MatchEnded();\n"),
    "n3_matchended_in_oms": ("GameStateWatcher.cs", SIG_OMS, _OMS_TRACK,
                             _OMS_TRACK + "            try { FtSchedule.MatchEnded(); } catch { }\n"),
    # N1: a room-callback hook removed
    "n1_join_hook_removed": ("Plugin.cs", "        public void OnJoinedRoom()", _HOOK_LINE, ""),
    "n1_leave_hook_removed": ("Plugin.cs", "        public void OnLeftRoom()", _HOOK_LINE, ""),
}


def _mut_after(srcs, name, within, old, new):
    """srcs with the first `old` after `within` in file `name` replaced by `new`."""
    s = dict(srcs)
    text = s[name]
    i = text.index(old, text.index(within))
    s[name] = text[:i] + new + text[i + len(old):]
    return s


@pytest.mark.parametrize("name", sorted(CALLER_MUTANTS))
def test_caller_mutant_fails(name):
    fname, within, old, new = CALLER_MUTANTS[name]
    srcs = _all_sources()
    mutated = _mut_after(srcs, fname, within, old, new)
    assert mutated[fname] != srcs[fname]
    assert caller_violations(mutated) != []


@pytest.mark.parametrize("sig", sorted(TIP))
def test_tip_bodies_are_the_port(sig):
    assert _body(_src("FtSchedule.cs"), sig) == TIP[sig]


def test_pins_hold():
    assert pin_violations(_sources()) == []


def test_gsw_ends_hold():
    assert gsw_violations(_src("GameStateWatcher.cs")) == []


def _mut(srcs, name, old, new):
    s = dict(srcs)
    assert s[name].count(old) == 1, (name, old)
    s[name] = s[name].replace(old, new)
    return s


SOURCE_MUTANTS = {
    # F3: Codex's mutant, a reset first in FtFrames.EndPoint
    "f3_reset_in_endpoint": ("FtFrames.cs", "            if (_wn > 0) FlushWindow(true);\n",
                             "            FtSpan.Reset();\n            if (_wn > 0) FlushWindow(true);\n", pin_violations),
    # F1: the quit drain removed (FlushGame as at c28259c1)
    "f1_quit_drain_removed": ("FtSchedule.cs", '            DrainOwed(false, "skipped_" + why);\n', "", pin_violations),
    # F1: the completion line back inside FtDrive.GameOver (the c28259c1 order)
    "f1_sitting_at_gameover": ("FtDrive.cs", "            CompleteGame = game;\n",
                               '            CompleteGame = game;\n            Plugin.Log.LogInfo("[FRAME-TIME] sitting complete g=" + game);\n',
                               pin_violations),
    # F1: the settle cap removed
    "f1_settle_cap_removed": ("FtSchedule.cs", '                    DrainOwed(true, live ? "skipped_live" : null);\n', "",
                              pin_violations),
}


def _gsw_mutants(src):
    reset_hook_line = "            " + HOOK + "\n"
    i = src.index(SIG_RESET)
    j = src.index(reset_hook_line, i)
    no_reset = src[:j] + src[j + len(reset_hook_line):]
    k = src.index(SIG_FFA_OVER)
    m = src.index(reset_hook_line, k)
    no_ffa = src[:m] + src[m + len(reset_hook_line):]
    anchor = "            catch { }\n            isTracking = true;"
    o = src.index(anchor, src.index(SIG_OMS))
    early = src[:o] + "            catch { }\n            if (sharedGameT0Set) return;\n            isTracking = true;" \
        + src[o + len(anchor):]
    return {
        "f2_reset_hook_removed": no_reset,
        "f2_ffa_hook_removed": no_ffa,
        # never a start: a hooked body that starts a match
        "f2_reset_starts": src[:j] + reset_hook_line + "            isTracking = true;\n" + src[j + len(reset_hook_line):],
        # never a start: a return between GameStart and isTracking = true
        "f2_oms_early_return": early,
        # an unguarded OnMatchStarted call
        "f2_unguarded_start": src.replace("                if (!isTracking)\n                {\n                    try { OnMatchStarted(); }",
                                          "                if (true)\n                {\n                    try { OnMatchStarted(); }", 1),
    }


@pytest.mark.parametrize("name", sorted(SOURCE_MUTANTS))
def test_source_mutant_fails(name):
    fname, old, new, check = SOURCE_MUTANTS[name]
    assert check(_mut(_sources(), fname, old, new)) != []


@pytest.mark.parametrize("name", ["f2_reset_hook_removed", "f2_ffa_hook_removed", "f2_reset_starts",
                                  "f2_oms_early_return", "f2_unguarded_start"])
def test_gsw_mutant_fails(name):
    src = _src("GameStateWatcher.cs")
    mutated = _gsw_mutants(src)[name]
    assert mutated != src
    assert gsw_violations(mutated) != []


def test_old_bodies_are_c28259c1():
    """The mutants' bodies are c28259c1's, read from git where the commit is reachable."""
    def show(path):
        return subprocess.run(["git", "-C", str(ROOT), "show", OLD_SHA + ":" + path],
                              capture_output=True, text=True, timeout=60)
    try:
        out = show("plugin/FtSchedule.cs")
    except (OSError, subprocess.SubprocessError) as ex:
        pytest.skip("git not runnable here: %s" % ex)
    if out.returncode != 0:
        pytest.skip("%s not reachable here: %s" % (OLD_SHA, out.stderr.strip()[:200]))
    for sig, want in OLD.items():
        assert _body(out.stdout, sig) == want, sig
    drive = show("plugin/FtDrive.cs")
    assert drive.returncode == 0
    for sig, want in OLD_DRIVE.items():
        assert _body(drive.stdout, sig) == want, sig


def test_the_port_s_neighbours_are_pinned():
    """What the port assumes of the other classes: GameBoundary only drops the owed between line; FtClock asks
    ClosingFrame before Boundary; FtReplay.Skip makes no replay call; GameStateWatcher calls GameStart and GameOver
    once each and MatchEnded twice; the quit handler calls FlushGame("quit")."""
    fr = _src("FtFrames.cs")
    assert fr.count("internal static void GameBoundary() { _btT0 = -1; }") == 1
    clock = "\n".join(_body(_src("FtClock.cs"), "private static void OnStart()"))
    i = clock.index("FtSchedule.ClosingFrame(live)")
    j = clock.index("FtSchedule.Boundary(live);")
    assert i < j and clock.count("FtSchedule.Boundary(live);") == 1
    # N2: Skip writes for every owed game, and Run has no sentinel guard of its own (DrainOwed decides)
    assert _body(_src("FtReplay.cs"), "internal static void Skip(int game, string result)") == [
        'Plugin.Log.LogInfo("[FRAME-TIME] answer_replay g=" + game + " ticks=0 result=" + result);']
    run_body = "\n".join(_body(_src("FtReplay.cs"), "internal static void Run(int game)"))
    assert "FtConfig" not in run_body and "return" not in run_body
    gsw = _src("GameStateWatcher.cs")
    assert gsw.count("FtSchedule.GameStart();") == 1 and gsw.count("FtSchedule.GameOver();") == 1
    assert gsw.count("FtSchedule.MatchEnded();") == 2
    assert _src("Plugin.cs").count("FtSchedule.MatchEnded();") == 2
    sched = _src("FtSchedule.cs")
    assert sched.count("FtReplay.Run(") == 1 and sched.count("FtReplay.Skip(") == 1
    assert sched.count("FtFrames.StartPoint();") == 1 and sched.count("FtFrames.EndPoint();") == 3
    assert _src("Plugin.cs").count('FtSchedule.FlushGame("quit");') == 1
    assert sum(1 for f in PLUGIN.glob("*.cs") if "sitting complete g=" in f.read_text(encoding="utf-8-sig")) == 1


# ------------------------------------------------------------------ the port

NO = None


class Sched:
    """FtSchedule's order. Each method mirrors the pinned body named beside it, statement by statement; calls into
    other classes are events; FtSpan's and FtCensus's live sums are one counter (span) with a reset epoch; one frame
    is one tick of the Stopwatch, so SETTLE_S is settle_frames. Each knob is 'tip' or a mutant: 'old' is c28259c1's
    body; open_ 'old' is open = live; settle 'old' is c28259c1's settle line, 'nocap' the tip without its cap;
    flush 'old' is FlushGame without the drain; sitting 'old' writes the completion line in FtDrive.GameOver;
    matchend 'none' is MatchEnded doing nothing; photon 'none' is the room callbacks without their hook (N1);
    replay 'old' is 8905732e's replay accounting (owed always, and no line once the sentinel is gone, N2);
    endowed 'noop' is EndOwedPoint's boundary arm doing nothing (N4); menu_guard 'none' is GameStart without its
    menu=1 refusal. present is FtConfig.Present; menu is FtConfig.Menu."""

    def __init__(self, boundary="tip", gamestart="tip", gameover="tip", closing="tip", open_="tip", settle="tip",
                 flush="tip", sitting="tip", matchend="tip", photon="tip", replay="tip", endowed="tip",
                 menu_guard="tip", last_game=99, settle_frames=3, menu=False, schedule="tip", plant="tip",
                 owner="tip", W=2, seed=7):
        self.v = dict(boundary=boundary, gamestart=gamestart, gameover=gameover, closing=closing, open_=open_,
                      settle=settle, flush=flush, sitting=sitting, matchend=matchend, photon=photon, replay=replay,
                      endowed=endowed, menu_guard=menu_guard, schedule=schedule, plant=plant)
        # B11 P1: the window schedule (OpenWindow) and FtFrames' ownership (FramesPort); W is the port's window
        # length (C#'s 120 is pinned), 2 so the short sequences fill windows
        self.W, self.seed = W, seed
        self.WinK, self.WinRun, self.WinPos, self.WinCoin = -1, 0, 0, 0
        self.WinP24 = self.WinPlant = self.WinRes = False
        self.PrevArm = -1
        self.hist_game, self.last_arm, self.last_plant, self.run_plant, self.game_run = None, -1, False, False, 0
        self.plant_now = False
        self.fr = FramesPort(W, owner)
        self.last_game, self.settle_frames = last_game, settle_frames
        self.present, self.menu = True, menu
        self.Game, self.Round, self.PointInRound = -1, 0, 0
        self.Live = self.FrameLive = self.InGame = self.over_owed = self.gate = self.ArmOn = False
        self.RoundOver = True
        self.LiveFrame = 0
        self.replay_owed = NO
        self.moment = "menu"
        self.flush_at = 0
        self.owed = -1
        self.complete = False
        self.complete_game = None
        self.sitting_logged = False
        self.now = 0
        self.picking = False
        self.span = 0
        self.epoch = 0
        self.point = None
        self.events = []

    def ev(self, *e):
        self.events.append(e)

    def label(self):
        return "%d.%d.%d" % (self.Game, self.Round, self.PointInRound)

    # SIG_CLOSING
    def closing_frame(self, live):
        if self.v["closing"] == "tip":
            return self.Live and ((not live) or self.over_owed)
        return self.Live and not live

    # SIG_BOUNDARY
    def boundary(self, live):
        if self.v["boundary"] == "old":
            return self._boundary_old(live)
        self.FrameLive = live
        if self.flush_at > 0:
            now = self.now
            if self.v["settle"] == "old":
                if now >= self.flush_at:
                    self.flush_game("settle")
            elif now >= self.flush_at and not self.over_owed and self.replay_owed is NO:
                self.flush_game("settle")
            elif self.v["settle"] == "tip" and now >= self.flush_at + self.settle_frames:
                self.drain_owed(True, "skipped_live" if live else None)
                self.flush_game("settle")
        self.end_owed_point(True)
        open_ = (live and self.InGame) if self.v["open_"] == "tip" else live
        if open_ and not self.Live:
            self.start_point()
        elif not open_ and self.Live:
            self.end_point()
        elif not open_ and self.gate:
            self.gate = False
        self.Live = open_
        if open_:
            self.LiveFrame += 1
            self.moment = "live"
            if self.LiveFrame >= 2 and (self.LiveFrame - 2) // self.W != self.WinK:
                self.open_window((self.LiveFrame - 2) // self.W)
            self.plant_now = self.gate and (self.WinPlant or self.v["plant"] == "any") and self.LiveFrame >= 2
            return
        self.LiveFrame = 0
        self.plant_now = False
        if self.picking:
            self.moment = "pick"
            self.RoundOver = True
        elif self.Game < 0:
            self.moment = "menu"
        elif self.moment != "gameover":
            self.moment = "between"
        if self.replay_owed is not NO and not live:
            self.drain_owed(True, None)

    # OLD[SIG_BOUNDARY]
    def _boundary_old(self, live):
        self.FrameLive = live
        if self.flush_at > 0 and self.now >= self.flush_at:
            self.flush_game("settle")
        if live and not self.Live:
            self.start_point()
        elif not live and self.Live:
            self.end_point()
        self.Live = live
        if live:
            self.LiveFrame += 1
            self.moment = "live"
            return
        self.LiveFrame = 0
        if self.picking:
            self.moment = "pick"
            self.RoundOver = True
        elif self.Game < 0:
            self.moment = "menu"
        elif self.moment != "gameover":
            self.moment = "between"

    # SIG_START; FtZero.Early and FtFrames.StartPoint's baselines are events
    def start_point(self):
        if self.RoundOver:
            self.Round += 1
            self.PointInRound = 0
            self.RoundOver = False
        self.PointInRound += 1
        self.ev("zero_early", self.Game)
        self.LiveFrame = 0
        self.open_window(0)
        self.point = {"label": self.label(), "base": self.span, "epoch": self.epoch, "acc": 0}
        self.fr.start_point(self)
        self.ev("start", self.label())

    # SIG_OPENWIN (TIP_P1_SCHED); schedule 'adjacent' is the mutant with pairs (1,2),(3,4) and arms (A,1-A,B,1-B)
    def open_window(self, k):
        if self.hist_game != self.Game:
            self.hist_game, self.last_arm, self.last_plant, self.game_run = self.Game, -1, False, 0
        q, r = k // 4, k % 4
        if self.v["schedule"] == "adjacent":
            self.WinCoin = mix(self.seed, self.Game, self.Round, self.PointInRound, 2 * q + (r >> 1), ARM_STREAM) & 1
            on = self.WinCoin == 1 if r % 2 == 0 else self.WinCoin == 0
        else:
            self.WinCoin = mix(self.seed, self.Game, self.Round, self.PointInRound, 2 * q + (r & 1), ARM_STREAM) & 1
            on = self.WinCoin == 1 if r < 2 else self.WinCoin == 0
        if r == 0:
            self.run_plant = run_planted(self.seed, self.Game, self.game_run)
            self.game_run += 1
        self.WinK, self.WinRun, self.WinPos, self.WinP24 = k, q, r + 1, (r & 1) == 1
        self.WinPlant = self.run_plant
        self.WinRes = (r == 0 and self.last_plant) if self.v["plant"] != "res_last" else (r == 3 and self.WinPlant)
        self.PrevArm = self.last_arm
        self.ArmOn = on
        self.last_arm = 1 if on else 0
        self.last_plant = self.WinPlant
        self.gate = not on
        self.ev("window", self.label(), k, on, self.PrevArm, self.WinPos, self.WinPlant, self.WinRes, self.WinP24)

    # SIG_END
    def end_point(self):
        self.gate = False
        self.frames_end_point()

    # FtFrames.EndPoint (TIP_FRAMES): the point line, its deltas against the baselines StartPoint took; a second call
    # before the next StartPoint writes nothing (_ptOpen)
    def frames_end_point(self):
        p = self.point
        if p is None:
            return
        self.fr.end_point(self)
        self.ev("end", p["label"], self.label(), self.span - p["base"], p["epoch"], self.epoch, p["acc"])
        self.point = None

    # SIG_ENDOWED
    def end_owed_point(self, at_boundary):
        if not self.over_owed:
            return
        self.over_owed = False
        if self.Live:
            if at_boundary:
                if self.v["endowed"] == "tip":
                    self.end_point()
            else:
                self.frames_end_point()
            self.Live = False
        self.ev("game_boundary")

    # SIG_DRAIN
    def drain_owed(self, at_boundary, skip):
        self.end_owed_point(at_boundary)
        if self.replay_owed is NO:
            return
        g = self.replay_owed
        self.replay_owed = NO
        if self.v["replay"] == "old" and not self.present:
            return                         # 8905732e: Run and Skip returned with no line
        if skip is None and not self.present:
            skip = "skipped_absent"
        if skip is None:
            self.replay_run(g)
        else:
            self.ev("replay_skip", g, self.FrameLive, skip)

    # SIG_GAMESTART
    def game_start(self):
        if self.menu and self.v["menu_guard"] == "tip":
            self.ev("game_start_failed")
            return
        if self.v["gamestart"] == "old":
            return self._game_start_old()
        if self.Live:
            self.frames_end_point()
            self.Live = False
        self.drain_owed(False, "skipped_live" if self.FrameLive else None)
        self.flush_game("next_game")
        self.ev("game_boundary")
        self._relabel_and_reset()
        self.InGame = True

    # OLD[SIG_GAMESTART]
    def _game_start_old(self):
        self.flush_game("next_game")
        self.ev("game_boundary")
        self._relabel_and_reset()

    def _relabel_and_reset(self):
        self.Game += 1
        self.Round = 0
        self.PointInRound = 0
        self.RoundOver = True
        self.moment = "between"
        self.span = 0                      # FtCensus.Reset, FtSpan.Reset
        self.epoch += 1
        self.ev("reset", self.Live)
        self.ev("calib", self.Live)        # FtCalib.Run

    # SIG_GAMEOVER (OLD[SIG_GAMEOVER] under gameover='old'); FtDrive.GameOver (TIP_DRIVE / OLD_DRIVE) inline
    def game_over(self):
        self.moment = "gameover"
        if self.v["gameover"] == "old":
            self.ev("game_boundary")
            self.replay_run(self.Game)
        else:
            self.InGame = False
            self.over_owed = True
            self.replay_owed = self.Game if (self.present or self.v["replay"] == "old") else NO
        self.owed = self.Game
        if self.Game >= self.last_game and not self.complete:
            self.complete = True
            self.complete_game = self.Game
            self.ev("complete", self.Game, self.now)
            if self.v["sitting"] == "old":
                self.ev("sitting", self.Game)
        if self.complete and self.flush_at == 0:
            self.flush_at = self.now + self.settle_frames

    # SIG_MATCHENDED
    def match_ended(self):
        if self.v["matchend"] == "none":
            return
        if not self.InGame:
            return
        self.InGame = False
        self.over_owed = True

    def replay_run(self, g):
        self.ev("replay", g, self.FrameLive, self.present)

    # SIG_FLUSH (OLD[SIG_FLUSH] under flush='old'); FtDrive.LogComplete inline
    def flush_game(self, why):
        if self.v["flush"] == "tip":
            self.drain_owed(False, "skipped_" + why)
        if self.owed < 0:
            return
        g = self.owed
        self.owed = -1
        self.flush_at = 0
        self.ev("flush", g, why, self.now)
        if self.v["sitting"] == "tip" and self.complete and g == self.complete_game and not self.sitting_logged:
            self.sitting_logged = True
            self.ev("sitting", g)

    # Plugin's quit handler
    def quit(self):
        self.flush_game("quit")


def drive(s, frames):
    """FtClock.OnStart per frame (the closed frame's ClosingFrame, then Boundary), the frame's live spans (one per
    frame with the moment live), then the frame's mid-frame calls in order (OnMatchStarted, OnGameOver, a match end
    with no OnGameOver, Plugin's Photon room callbacks, the sentinel going absent, the quit handler)."""
    if s.menu:
        s.ev("menu")
    started, on = -1, False         # the truth: games GameStart started, and a started game not yet ended
    truth = None
    for i, (live, calls, pick) in enumerate(frames):
        s.now = i
        closing = s.closing_frame(live)
        s.ev("frame", i, closing, s.Live)
        if truth is not None:
            s.fr.frame(s, i - 1, closing, truth)     # FtClock.OnFrameClosed: frame i-1, before frame i's boundary
        truth = (started, on)
        s.picking = pick
        s.boundary(live)
        if s.moment == "live":
            s.span += 1
            if s.point is not None:
                s.point["acc"] += 1
        for c in calls:
            if c == "GameStart":
                s.ev("gamestart", s.Live)
                s.game_start()
                if not s.menu:
                    started, on = started + 1, True
            elif c == "GameOver":
                s.ev("gameover", s.Live, i, s.Game, s.present)
                s.game_over()
                on = False
            elif c == "MatchEnded":
                s.ev("matchend", s.Live, i)
                s.match_ended()
                on = False
            elif c in ("Leave", "Join"):     # Plugin.OnLeftRoom / OnJoinedRoom: the room changed, the game ended
                on = False
                s.ev("matchend", s.Live, i)
                if s.v["photon"] == "tip":
                    s.match_ended()
            elif c == "Absent":              # FtConfig's refresh finds the sentinel gone
                s.present = False
                s.ev("absent", i)
            else:
                s.ev("quit", i)
                s.quit()
    s.ev("frames", len(frames), s.Live)
    return s.events


# ------------------------------------------------------------------ the sequences

def F(live, *calls, pick=False):
    return (live, calls, pick)


def opening():
    """Combat goes live three frames before OnMatchStarted (w9: every game), then five live frames."""
    return [F(False)] * 2 + [F(True)] * 3 + [F(True, "GameStart")] + [F(True)] * 5


def mid():
    """A round ends, a card pick, the next point."""
    return [F(False), F(False, pick=True), F(False)] + [F(True)] * 5


END_AFTER = [F(False), F(False, "GameOver"), F(False), F(False)]            # combat over at a boundary, then OnGameOver
END_INSIDE = [F(True, "GameOver"), F(False), F(False)]                       # OnGameOver in the frame combat ended in
END_INSIDE_LIVE = [F(True, "GameOver"), F(True), F(True), F(False), F(False)]   # ...and the next frames still read live
QUIT = [F(False, "Quit")]

SEQS = {
    # measured: OnMatchStarted after combat went live
    "start_after_live": opening() + mid() + END_AFTER + opening() + mid() + END_AFTER + opening() + END_AFTER + QUIT,
    # measured: OnGameOver inside the frame where combat ended (w9 game 4)
    "over_inside": opening() + mid() + END_INSIDE + opening() + END_INSIDE + opening() + END_AFTER + QUIT,
    "over_inside_live": opening() + END_INSIDE_LIVE + opening() + END_AFTER + QUIT,
    # a match end with no OnGameOver (room exit), inside a live point and between points
    "exit_mid_point": opening() + [F(True, "MatchEnded")] + [F(True)] * 2 + [F(False)] + opening() + END_AFTER + QUIT,
    "exit_quiet": opening() + [F(False), F(False, "MatchEnded")] + opening() + END_AFTER + QUIT,
    "same_frame_live": opening() + [F(True, "GameOver", "GameStart")] + [F(True)] * 3 + END_AFTER + QUIT,
    "same_frame_quiet": opening() + [F(False), F(False, "GameOver", "GameStart")] + [F(True)] * 3 + END_AFTER + QUIT,
    # the last game (LAST below): its settle, with the frames live past the due time and back to quiet before the cap
    "settle": opening() + [F(True, "GameOver")] + [F(True)] * 4 + [F(False)] * 4 + QUIT,
    # ...and live past the cap (no boundary reads not live before quit)
    "settle_stuck": opening() + [F(True, "GameOver")] + [F(True)] * 10 + [F(True, "Quit")],
    # quit with the point end and the replay still owed
    "quit_owed": opening() + [F(True, "GameOver", "Quit")],
    "quit_after": opening() + END_AFTER + QUIT,
    # N1: a leave and a join inside one poll tick (GameStateWatcher's poll sees no room exit and keeps tracking, so
    # room B's combat gets no OnMatchStarted), in a live frame and in a quiet one
    "fast_rejoin": opening() + [F(True, "Leave", "Join")] + [F(False)] + [F(True)] * 5 + [F(False)] + QUIT,
    "fast_rejoin_quiet": opening() + [F(False), F(False, "Leave", "Join")] + [F(True)] * 5 + [F(False)] + QUIT,
    # N2: the sentinel goes absent after GameOver, before the replay drains: at a boundary, at quit, at the settle cap
    "absent_boundary": opening() + [F(True, "GameOver"), F(True, "Absent"), F(False), F(False)] + QUIT,
    "absent_quit": opening() + [F(True, "GameOver", "Absent", "Quit")],
    "absent_settle": opening() + [F(True, "GameOver"), F(True, "Absent")] + [F(True)] * 4 + [F(False)] * 2 + QUIT,
    # (2)(e): a menu=1 process (MENU below) sees a game start
    "menu_start": opening() + [F(False)] * 2 + QUIT,
}
LAST = {"settle": 0, "settle_stuck": 0, "absent_settle": 0}
MENU = {"menu_start"}


def run(seq, **variant):
    s = Sched(last_game=LAST.get(seq, 99), menu=seq in MENU, **variant)
    return drive(s, SEQS[seq])


# ------------------------------------------------------------------ the assertions

def a1_straddles(ev):
    bad = []
    for e in ev:
        if e[0] in ("reset", "calib") and e[1]:
            bad.append("%s with a point open" % e[0])
        if e[0] == "end" and e[1] != e[2]:
            bad.append("point started as %s ended as %s" % (e[1], e[2]))
    return bad


def a2_stale_baselines(ev):
    bad = []
    for e in ev:
        if e[0] == "end":
            _, lab, _, delta, e0, e1, acc = e
            if e0 != e1:
                bad.append("point %s: baselines from reset epoch %d, read at %d" % (lab, e0, e1))
            if delta != acc:
                bad.append("point %s: delta %d, accrued %d" % (lab, delta, acc))
    return bad


def a3_replays(ev):
    bad = []
    overs, lines = {}, {}
    quitting = absent = False
    for i, e in enumerate(ev):
        if e[0] == "quit":
            quitting = True
        if e[0] == "absent":
            absent = True
        if e[0] == "gameover" and e[4]:     # a replay is owed: reading A with the sentinel present at GameOver
            overs.setdefault(e[3], []).append(i)
        elif e[0] == "replay":
            lines.setdefault(e[1], []).append(i)
            if e[2]:
                bad.append("replay call g=%d in a frame that started live" % e[1])
            if not e[3]:
                bad.append("replay call g=%d with the sentinel absent" % e[1])
        elif e[0] == "replay_skip":
            lines.setdefault(e[1], []).append(i)
            why = e[3]
            if not ((why == "skipped_live" and e[2]) or (why == "skipped_quit" and quitting)
                    or (why == "skipped_absent" and absent and not e[2])):
                bad.append("replay g=%d skipped (%s) where a call may run" % (e[1], why))
    for g, idx in overs.items():
        ls = lines.get(g, [])
        if len(idx) != 1:
            bad.append("game %d: %d game overs" % (g, len(idx)))
        if len(ls) != 1:
            bad.append("game %d: %d replay lines for its game over" % (g, len(ls)))
        elif ls[0] < idx[0]:
            bad.append("game %d: replay line before its game over" % g)
    for g in lines:
        if g not in overs:
            bad.append("replay line for game %d, which had no game over" % g)
    return bad


def a4_outside_game(ev):
    bad = []
    in_game, games = False, -1
    for e in ev:
        if e[0] == "gamestart":
            in_game, games = True, games + 1
        elif e[0] in ("gameover", "matchend"):
            in_game = False
        elif e[0] == "start" and (not in_game or int(e[1].split(".")[0]) != games):
            bad.append("point %s opened outside its game (games started %d, in game %s)" % (e[1], games + 1, in_game))
    return bad


def a5_flushes(ev):
    bad = []
    overs = set(e[3] for e in ev if e[0] == "gameover")
    owing = set(e[3] for e in ev if e[0] == "gameover" and e[4])
    for g in sorted(overs):
        fl = [i for i, e in enumerate(ev) if e[0] == "flush" and e[1] == g]
        if len(fl) != 1:
            bad.append("game %d flushed %d times" % (g, len(fl)))
            continue
        ends = [i for i, e in enumerate(ev) if e[0] == "end" and int(e[1].split(".")[0]) == g]
        if ends and max(ends) > fl[0]:
            bad.append("game %d flushed before its point end" % g)
        rep = [i for i, e in enumerate(ev) if e[0] in ("replay", "replay_skip") and e[1] == g]
        if g in owing and (not rep or rep[0] > fl[0]):
            bad.append("game %d flushed before its replay line" % g)
    for e in ev:
        if e[0] == "flush" and e[1] not in overs:
            bad.append("game %d flushed with no game over" % e[1])
    return bad


def a6_end_frame_not_closing(ev):
    bad = []
    owed = None
    for e in ev:
        if (e[0] == "gameover" and e[1]) or (e[0] == "matchend" and e[1]):
            owed = e[2] + 1
        elif e[0] == "frame" and owed is not None and e[1] == owed:
            if e[3] and not e[2]:   # closed inside a point (FtFrames.Frame measures it) and not excluded
                bad.append("frame %d (the game ended in it, a point open) was measured" % (e[1] - 1))
            owed = None
    return bad


def a7_sitting(ev):
    bad = []
    done = [e[1] for e in ev if e[0] == "complete"]
    sit = [i for i, e in enumerate(ev) if e[0] == "sitting"]
    if not done:
        return ["a sitting line with no completed sitting"] if sit else []
    g = done[0]
    if len(sit) != 1:
        return ["%d sitting lines" % len(sit)]
    fl = [i for i, e in enumerate(ev) if e[0] == "flush" and e[1] == g]
    rep = [i for i, e in enumerate(ev) if e[0] in ("replay", "replay_skip") and e[1] == g]
    if not fl or sit[0] < fl[0]:
        bad.append("sitting line before game %d's flush" % g)
    if not rep or sit[0] < rep[0]:
        bad.append("sitting line before game %d's replay line" % g)
    return bad


def a8_settle_cap(ev, settle_frames=3):
    bad = []
    done = [e for e in ev if e[0] == "complete"]
    if not done:
        return bad
    g, f = done[0][1], done[0][2]
    cap = f + 2 * settle_frames          # due at f + SETTLE_S; the cap SETTLE_S after that
    n = [e[1] for e in ev if e[0] == "frames"][0]
    if n - 1 > cap:
        fl = [e for e in ev if e[0] == "flush" and e[1] == g]
        if not fl or fl[0][3] > cap:
            bad.append("game %d not flushed by the cap (frame %d): %s" % (g, cap, fl))
    return bad


def a9_point_ends(ev):
    """N4: every opened point has exactly one end record, written before its game's next boundary and before its
    game's flush; only a point still open when the trace ends (the last event says Live) may have none."""
    bad = []
    tail_live = ev[-1][-1] if ev and ev[-1][0] in ("frames", "end_of_trace") else False
    starts = [(i, e[1]) for i, e in enumerate(ev) if e[0] == "start"]
    for n, (i, lab) in enumerate(starts):
        ends = [j for j, e in enumerate(ev) if e[0] == "end" and e[1] == lab and j > i]
        gb = [j for j in range(i, len(ev)) if ev[j][0] == "game_boundary"]
        fl = [j for j in range(i, len(ev)) if ev[j][0] == "flush" and ev[j][1] == int(lab.split(".")[0])]
        if not ends:
            if not (n == len(starts) - 1 and tail_live and not gb and not fl):
                bad.append("point %s has no end record" % lab)
            continue
        if len(ends) != 1:
            bad.append("point %s has %d end records" % (lab, len(ends)))
        if gb and gb[0] < ends[0]:
            bad.append("point %s ends after its game's boundary" % lab)
        if fl and fl[0] < ends[0]:
            bad.append("point %s ends after its game's flush" % lab)
    return bad


def a10_menu(ev):
    """(2)(e): in a menu=1 process GameStart writes its failure line and resets nothing; no point opens."""
    if not any(e[0] == "menu" for e in ev):
        return []
    bad = ["%s in a menu=1 process" % e[0] for e in ev if e[0] in ("reset", "calib", "start", "game_boundary")]
    starts = sum(1 for e in ev if e[0] == "gamestart")
    fails = sum(1 for e in ev if e[0] == "game_start_failed")
    if starts != fails:
        bad.append("%d game starts, %d failure lines" % (starts, fails))
    return bad


CHECKS = {"A1": a1_straddles, "A2": a2_stale_baselines, "A3": a3_replays, "A4": a4_outside_game,
          "A5": a5_flushes, "A6": a6_end_frame_not_closing, "A7": a7_sitting, "A8": a8_settle_cap,
          "A9": a9_point_ends, "A10": a10_menu}

OLD_ALL = dict(boundary="old", gamestart="old", gameover="old", closing="old", flush="old", sitting="old",
               settle="old")
MUTANTS = {
    "c28259c1": OLD_ALL,
    "c28259c1_start": dict(boundary="old", gamestart="old"),   # the game-start pair as at c28259c1
    "c28259c1_over": dict(gameover="old"),                     # GameOver as at c28259c1
    "c28259c1_open": dict(open_="old"),                        # Boundary's open rule as at c28259c1 (open = live)
    "c28259c1_settle": dict(settle="old"),                     # the settle flush line as at c28259c1
    "c28259c1_closing": dict(closing="old"),                   # ClosingFrame as at c28259c1
    "c28259c1_flush": dict(flush="old"),                       # FlushGame as at c28259c1: the quit drain removed
    "c28259c1_sitting": dict(sitting="old"),                   # the completion line in FtDrive.GameOver
    "no_cap": dict(settle="nocap"),                            # the settle wait without its cap
    "no_matchend": dict(matchend="none"),                      # MatchEnded doing nothing
    "no_room_hook": dict(photon="none"),                       # N1: the room callbacks without their hook
    "replay_8905732e": dict(replay="old"),                     # N2: 8905732e's replay accounting
    "endowed_noop": dict(endowed="noop"),                      # N4: EndOwedPoint's boundary arm a no-op
    "no_menu_guard": dict(menu_guard="none"),                  # (2)(e): GameStart without its menu=1 refusal
}

# (assertion, mutant, sequence): each must fail
MUST_FAIL = [
    ("A1", "c28259c1", "start_after_live"), ("A1", "c28259c1_start", "start_after_live"),
    ("A2", "c28259c1", "start_after_live"), ("A2", "c28259c1_start", "start_after_live"),
    ("A3", "c28259c1", "over_inside"), ("A3", "c28259c1_over", "over_inside"),
    ("A3", "c28259c1_flush", "quit_owed"), ("A3", "c28259c1_settle", "settle"),
    ("A4", "c28259c1", "start_after_live"), ("A4", "c28259c1_start", "start_after_live"),
    ("A4", "c28259c1_open", "start_after_live"), ("A4", "no_matchend", "exit_mid_point"),
    ("A4", "no_matchend", "exit_quiet"),
    ("A5", "c28259c1_flush", "quit_owed"),
    ("A6", "c28259c1_closing", "over_inside_live"), ("A6", "c28259c1_closing", "exit_mid_point"),
    ("A7", "c28259c1", "settle"), ("A7", "c28259c1_sitting", "settle"),
    ("A8", "no_cap", "settle_stuck"),
    ("A4", "no_room_hook", "fast_rejoin"), ("A4", "no_room_hook", "fast_rejoin_quiet"),
    ("A3", "replay_8905732e", "absent_boundary"), ("A3", "replay_8905732e", "absent_quit"),
    ("A3", "replay_8905732e", "absent_settle"),
    ("A9", "endowed_noop", "over_inside"), ("A9", "endowed_noop", "exit_mid_point"),
    ("A9", "endowed_noop", "fast_rejoin"),
    ("A10", "no_menu_guard", "menu_start"),
]


@pytest.mark.parametrize("seq", sorted(SEQS))
@pytest.mark.parametrize("name", sorted(CHECKS))
def test_tip_order_holds(name, seq):
    assert CHECKS[name](run(seq)) == []


@pytest.mark.parametrize("name,mutant,seq", MUST_FAIL)
def test_mutant_fails(name, mutant, seq):
    assert CHECKS[name](run(seq, **MUTANTS[mutant])) != []


def test_every_assertion_and_mutant_is_used():
    assert sorted(set(m[0] for m in MUST_FAIL)) == sorted(CHECKS)
    assert sorted(set(m[1] for m in MUST_FAIL)) == sorted(MUTANTS)


# F4: Codex's counterexamples, as event streams
_END_G0 = ("end", "0.1.1", "0.1.1", 0, 1, 1, 0)


def test_f4_counterexamples_fail():
    # g0's replay twice, none for g1, all frames not live
    ce1 = [("gameover", False, 0, 0, True), ("replay", 0, False, True), ("gameover", False, 1, 1, True),
           ("replay", 0, False, True)]
    assert a3_replays(ce1) != []
    # a flush before EndPoint
    ce2 = [("gameover", True, 0, 0, True), ("replay", 0, False, True), ("flush", 0, "settle", 4), _END_G0]
    assert a5_flushes(ce2) != []
    # no flush at all
    ce3 = [("gameover", False, 0, 0, True), ("replay", 0, False, True), _END_G0]
    assert a5_flushes(ce3) != []
    # N4: a point opened and never ended, its game's boundary and flush written anyway
    ce4 = [("start", "0.1.1"), ("gameover", True, 0, 0, True), ("game_boundary",), ("replay", 0, False, True),
           ("flush", 0, "settle", 4), ("frames", 9, False)]
    assert a9_point_ends(ce4) != []
    # the controls the other way: the same streams in the tip's order pass
    assert a3_replays([("gameover", False, 0, 0, True), ("replay", 0, False, True), ("gameover", False, 1, 1, True),
                       ("replay", 1, False, True)]) == []
    assert a5_flushes([("gameover", True, 0, 0, True), _END_G0, ("replay", 0, False, True),
                       ("flush", 0, "settle", 4)]) == []
    assert a9_point_ends([("start", "0.1.1"), ("gameover", True, 0, 0, True), _END_G0, ("game_boundary",),
                          ("replay", 0, False, True), ("flush", 0, "settle", 4), ("frames", 9, False)]) == []


def test_old_port_reproduces_the_measured_symptoms():
    """The c28259c1 port shows w9's signatures: a game's first point opens under the previous game's label and ends
    relabelled g.0.0 with a negative delta (VR5's negative sums), its FtZero.Early read before GameStart (zs bit 14),
    and in the inside sequence the replay runs in a frame that started live (B3's two edge calls)."""
    ev = run("start_after_live", **OLD_ALL)
    ends = [e for e in ev if e[0] == "end"]
    relabelled = [e for e in ends if e[1] != e[2] and e[2].endswith(".0.0")]
    assert relabelled and any(e[3] < 0 for e in relabelled)
    assert [e for e in ev if e[0] == "zero_early"][0][1] == -1
    assert any(e[0] == "replay" and e[2] for e in run("over_inside", **OLD_ALL))


def test_tip_labels_replays_and_drains():
    """At the tip each game's first point is g.1.1 and opens after GameStart; the replay waits for a frame that starts
    not live; GameOver and GameStart in one live frame write the skip line; the quit flush ends the owed point and
    writes skipped_quit before the flush; the settle cap writes skipped_live and flushes at the cap."""
    ev = run("start_after_live")
    starts = [e[1] for e in ev if e[0] == "start"]
    assert starts[0] == "0.1.1" and "1.1.1" in starts and "2.1.1" in starts
    assert not any(s.endswith(".0.0") for s in starts)
    ev = run("over_inside_live")
    i_over = next(i for i, e in enumerate(ev) if e[0] == "gameover")
    i_rep = next(i for i, e in enumerate(ev) if e[0] == "replay")
    assert len([e for e in ev[i_over:i_rep] if e[0] == "frame"]) == 3
    assert [e for e in run("same_frame_live") if e[0] == "replay_skip"][0][3] == "skipped_live"
    quiet = run("same_frame_quiet")
    assert not [e for e in quiet if e[0] == "replay_skip"]
    assert [e for e in quiet if e[0] == "replay"][0][2] is False
    kinds = [e[0] for e in run("quit_owed") if e[0] in ("end", "game_boundary", "replay_skip", "flush")]
    assert kinds[-4:] == ["end", "game_boundary", "replay_skip", "flush"]
    stuck = run("settle_stuck")
    assert [e[3] for e in stuck if e[0] == "replay_skip"] == ["skipped_live"]
    assert [(e[2], e[3]) for e in stuck if e[0] == "flush"] == [("settle", 11 + 2 * 3)]
    assert [e[0] for e in stuck].count("sitting") == 1
    ex = run("exit_mid_point")
    assert not [e for e in ex if e[0] in ("replay", "replay_skip") and e[1] == 0]   # MatchEnded owes no replay
    assert not [e for e in ex if e[0] == "flush" and e[1] == 0]                     # ...and no flush
    # N1: after the leave and join no point opens, under the old game's label or any other, until a GameStart
    for seq in ("fast_rejoin", "fast_rejoin_quiet"):
        ev = run(seq)
        i_leave = next(i for i, e in enumerate(ev) if e[0] == "matchend")
        assert not [e for e in ev[i_leave:] if e[0] == "start"], seq
        assert [e for e in run(seq, photon="none")[i_leave:] if e[0] == "start"], seq   # the mutant opens one
    # N2: one line per owed game whatever the sentinel reads at drain time
    assert [e[3] for e in run("absent_boundary") if e[0] == "replay_skip"] == ["skipped_absent"]
    assert [e[3] for e in run("absent_quit") if e[0] == "replay_skip"] == ["skipped_quit"]
    assert [e[3] for e in run("absent_settle") if e[0] == "replay_skip"] == ["skipped_absent"]
    for seq in ("absent_boundary", "absent_quit", "absent_settle"):
        assert not [e for e in run(seq, replay="old") if e[0] in ("replay", "replay_skip")], seq
    # (2)(e): the menu process writes the failure line and stays at game -1 with no point
    menu = run("menu_start")
    assert [e[0] for e in menu].count("game_start_failed") == 1
    assert not [e for e in menu if e[0] in ("reset", "start")]


# ------------------------------------------------------------------ F2: GameStateWatcher's guards, enumerated

class GSW:
    """GameStateWatcher's match lifecycle as the source checks above pin it: OnMatchStarted's callers require
    !isTracking; OnGameOver's guard requires isTracking and no report, then calls FtSchedule.GameOver; ResetMatchState
    and OnFfaGameOver write isTracking = false and then call the hook; OnFfaMatchStarted re-arms tracking without
    GameStart. 'started' is the truth the instrument must follow: a match OnMatchStarted started and nothing ended."""

    def __init__(self, s, hook_reset="tip", hook_ffa="tip", hook_photon="tip"):
        self.s, self.hook_reset, self.hook_ffa, self.hook_photon = s, hook_reset, hook_ffa, hook_photon
        self.tracking = self.reported = self.started = False
        self.bad = []

    def _hook(self, v):
        self.s.ev("matchend", self.s.Live, self.s.now)   # the match end itself, whatever the hook does
        if v == "tip":
            self.s.match_ended()
        elif v == "start":
            self.s.InGame = True

    def oms(self):
        if self.tracking:
            return
        if self.s.InGame:
            self.bad.append("GameStart with InGame set")
        self.s.ev("gamestart", self.s.Live)
        self.s.game_start()
        self.tracking, self.reported, self.started = True, False, True

    def ogo(self, keep=False):
        if not self.tracking or self.reported:
            return
        self.reported = True
        self.s.ev("gameover", self.s.Live, self.s.now, self.s.Game, self.s.present)
        self.s.game_over()
        self.started = False
        if not keep:
            self.tracking = False

    def reset(self):
        self.tracking = False
        self._hook(self.hook_reset)
        self.reported = False
        self.started = False

    def ffa_start(self):
        self.tracking, self.reported = True, False

    def ffa_over(self):
        if self.reported:
            return
        self.reported = True
        self.tracking = False
        self._hook(self.hook_ffa)
        self.started = False

    def photon(self):
        """Plugin.OnLeftRoom or OnJoinedRoom with GameStateWatcher's poll missing the exit (N1): tracking is left as
        it was, and the room's game has ended."""
        self._hook(self.hook_photon)
        self.started = False

    def check(self, step):
        if self.s.InGame and not (self.tracking and not self.reported):
            self.bad.append("step %d: InGame with no tracked, unreported match" % step)
        if self.s.InGame != self.started:
            self.bad.append("step %d: InGame %s, a started match %s" % (step, self.s.InGame, self.started))


EVENTS = ("oms", "ogo", "ogo_keep", "reset", "ffa_start", "ffa_over", "photon", "live", "quiet")


def enumerate_gsw(length=5, **hooks):
    """Every event sequence of the given length; returns (sequences with an invariant violated, with A1/A2/A4/A9
    failed)."""
    inv, acc = [], []
    for seq in itertools.product(EVENTS, repeat=length):
        s = Sched()
        g = GSW(s, **hooks)
        for i, e in enumerate(seq):
            if e in ("live", "quiet"):
                s.now += 1
                s.ev("frame", s.now, s.closing_frame(e == "live"), s.Live)
                s.boundary(e == "live")
            elif e == "ogo_keep":
                g.ogo(keep=True)
            else:
                getattr(g, e)()
            g.check(i)
        s.ev("end_of_trace", s.Live)
        if g.bad:
            inv.append((seq, g.bad[0]))
        if a1_straddles(s.events) or a2_stale_baselines(s.events) or a4_outside_game(s.events) \
                or a9_point_ends(s.events):
            acc.append(seq)
    return inv, acc


def test_gsw_sequences_hold():
    inv, acc = enumerate_gsw()
    assert inv == [] and acc == [], (inv[:3], acc[:3])


def test_gsw_endowed_noop_fails_behaviourally():
    """N4 in the enumeration: EndOwedPoint's boundary arm as a no-op leaves a point with no end record."""
    s = Sched(endowed="noop")
    g = GSW(s)
    for e in ("oms", "live", "ogo", "quiet"):
        if e in ("live", "quiet"):
            s.now += 1
            s.boundary(e == "live")
        else:
            getattr(g, e)()
    s.ev("end_of_trace", s.Live)
    assert a9_point_ends(s.events) != []


@pytest.mark.parametrize("hooks", [dict(hook_reset="none"), dict(hook_reset="start"),
                                   dict(hook_ffa="none"), dict(hook_ffa="start"),
                                   dict(hook_photon="none"), dict(hook_photon="start")])
def test_gsw_hook_mutant_fails(hooks):
    inv, _ = enumerate_gsw(**hooks)
    assert inv != []


# ================================================================== B11 P1: windows, ownership, records, plants, ledger
# The window schedule of ruling R6-A3.11.138 (4) (interleaved pairs, ruling .137 (3)), FtFrames' captured ownership,
# the partition C = G + W + R + S + E with its tenths (method-v54.md (a), ruling .138 (5)), the plant runs (SHARED.md
# D4) and the writer ledger's tokens (D5). Each port mirrors the C# body pinned beside it in the P1 tables above.

M64 = (1 << 64) - 1
ARM_STREAM = 0xA2A1
RUN_STREAM = 0x51A75
BIN = 12


def mix(seed, game, rnd, point, block, stream):
    """SIG_MIX: SplitMix64 over five integers and a stream constant (C#'s uint and ulong casts as masks)."""
    u = lambda x: x & 0xFFFFFFFF
    z = (u(seed) * 0x9E3779B97F4A7C15 + u(game) * 0xBF58476D1CE4E5B9 + u(rnd) * 0x94D049BB133111EB
         + u(point) * 0xD6E8FEB86659FD93 + (block & M64) * 0xA0761D6478BD642F + stream) & M64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
    return z ^ (z >> 31)


def run_planted(seed, game, run):
    """SIG_PL_RUN: one run in five, the slot of each block of five drawn per game."""
    return run % 5 == mix(seed, game, 0, 0, run // 5, RUN_STREAM) % 5


def test_p1_constants_are_the_port_s():
    assert _src("FtSchedule.cs").count("internal const ulong ArmStream = 0x%XUL;" % ARM_STREAM) == 1
    assert _src("FtPlant.cs").count("internal const ulong RunStream = 0x%XUL;" % RUN_STREAM) == 1
    fr = _src("FtFrames.cs")
    assert fr.count("internal const int W = 120;") == 1 and fr.count("internal const int Bin = 12, Bins = W / Bin;") == 1
    # the plant stream the menu self-check keeps is not the run stream
    assert _src("FtPlant.cs").count("0x51A7UL") == 1


@pytest.mark.parametrize("table", ["TIP_P1_SCHED", "TIP_P1_FRAMES", "TIP_P1_SPAN", "TIP_P1_CLOCK", "TIP_P1_PLANT",
                                   "TIP_P1_LEDGER"])
def test_p1_bodies_are_the_port(table):
    fname = {"TIP_P1_SCHED": "FtSchedule.cs", "TIP_P1_FRAMES": "FtFrames.cs", "TIP_P1_SPAN": "FtSpan.cs",
             "TIP_P1_CLOCK": "FtClock.cs", "TIP_P1_PLANT": "FtPlant.cs", "TIP_P1_LEDGER": "FtUpload.cs"}[table]
    for sig, want in globals()[table].items():
        assert _body(_src(fname), sig) == want, sig


P1_SOURCE_MUTANTS = {
    # the adjacent-pair schedule written into the C# body: the pin refuses it
    "adjacent_in_source": ("FtSchedule.cs", "2 * q + (r & 1), ArmStream)", "2 * q + (r >> 1), ArmStream)"),
    # EndPoint without its open flag
    "endpoint_reentrant": ("FtFrames.cs", "            if (!_ptOpen) return;\n", ""),
    # the window line labelled at write time (the bd673226 form)
    "label_at_write": ("FtFrames.cs", 'sb.Append("[FRAME-TIME] w pt=").Append(_oPt)',
                       'sb.Append("[FRAME-TIME] w pt=").Append(FtSchedule.Label())'),
    # GC left inside the classes
    "class_keeps_gc": ("FtSpan.cs", "            if (gok && _gok) d -= g - _g;\n", ""),
    # the tenths filled from F
    "q_from_f_source": ("FtFrames.cs", "_tq[bin] += unchecked((long)c) - cg - cw;", "_tq[bin] += f;"),
    # a token counted before its line is written
    "tok_before_write": ("FtUpload.cs", "                FtSpan.PushWriter();\n                try { _in.WriteLine(value); }",
                         "                lock (_lock) { _pendingLog++; }\n                FtSpan.PushWriter();\n"
                         "                try { _in.WriteLine(value); }"),
}


@pytest.mark.parametrize("name", sorted(P1_SOURCE_MUTANTS))
def test_p1_source_mutant_fails(name):
    fname, old, new = P1_SOURCE_MUTANTS[name]
    assert pin_violations(_sources()) == []                       # the negative control: the tip passes
    assert pin_violations(_mut(_sources(), fname, old, new)) != []


# ------------------------------------------------------------------ the schedule (ruling .138 (4), D1)

def window_events(schedule="tip", plant="tip", seeds=range(60), games=3, points=8):
    """OpenWindow driven directly over many points: per seed and game, points of 1 to 14 windows each, in order."""
    out = []
    for seed in seeds:
        s = Sched(schedule=schedule, plant=plant, seed=seed)
        for g in range(games):
            s.Game = g
            for p in range(points):
                s.Round, s.PointInRound = 1 + p // 3, 1 + p % 3
                n = 1 + mix(seed, g, p, 0, 0, 0x77) % 14
                for k in range(n):
                    s.open_window(k)
                    e = s.events[-1]
                    out.append(dict(seed=seed, game=g, pt=e[1], k=e[2], on=e[3], pred=e[4], pos=e[5], plant=e[6],
                                    res=e[7]))
    return out


def joint_violations(ws, positions, lo=0.21, hi=0.29, least=1500):
    """P(own arm, predecessor arm) at the given positions: each of the four cells in [lo, hi] (the true value is 1/4
    for any two windows that are not mates, D1)."""
    cells = {}
    for w in ws:
        if w["pos"] in positions and w["pred"] >= 0:
            key = (w["on"], w["pred"] == 1)
            cells[key] = cells.get(key, 0) + 1
    n = sum(cells.values())
    if n < least:
        return ["%d windows at positions %s" % (n, sorted(positions))]
    return ["P(own=%s, pred=%s) = %.3f" % (a, b, cells.get((a, b), 0) / n)
            for a in (True, False) for b in (True, False) if not lo <= cells.get((a, b), 0) / n <= hi]


def mate_violations(ws, mates):
    """Mates take opposite arms: P(ON, ON) = 0 and P(ON, OFF) = 1/2 (D1)."""
    bad, by = [], {}
    for w in ws:
        by[(w["seed"], w["game"], w["pt"], w["k"])] = w
    for w in ws:
        for a, b in mates:
            if w["pos"] == b:
                m = by.get((w["seed"], w["game"], w["pt"], w["k"] - (b - a)))
                if m is not None and m["on"] == w["on"]:
                    bad.append("%s window %d: mates share arm %s" % (w["pt"], w["k"], w["on"]))
    return bad


def test_p1_interleaved_schedule_holds():
    ws = window_events()
    assert joint_violations(ws, {3, 4}) == []              # the second members, (1,3) and (2,4)
    assert joint_violations(ws, {1, 2}) == []              # and the first members
    assert mate_violations(ws, [(1, 3), (2, 4)]) == []
    # the predecessor carries across points within a game and is none only at a game's first window
    for i, w in enumerate(ws):
        first = i == 0 or ws[i - 1]["game"] != w["game"] or ws[i - 1]["seed"] != w["seed"]
        assert (w["pred"] == -1) == first, w
        if not first:
            assert w["pred"] == (1 if ws[i - 1]["on"] else 0)


def test_p1_adjacent_pairs_fail_the_joint_check():
    ws = window_events(schedule="adjacent")
    assert mate_violations(ws, [(1, 2), (3, 4)]) == []     # it is a valid pair schedule...
    assert joint_violations(ws, {2, 4}) != []              # ...whose second members' predecessor is the mate


def test_p1_partial_window_keeps_its_arm():
    """A window's arm is committed by position before it runs: the same (seed, game, round, point, k) gives the same
    arm whatever the point's length."""
    a = window_events(seeds=[3], points=8)
    s = Sched(seed=3)
    s.Game, s.Round, s.PointInRound = 0, 1, 1
    for k in range(3):                                      # the same point cut after three windows
        s.open_window(k)
    assert [e[3] for e in s.events if e[0] == "window"] == [w["on"] for w in a if w["pt"] == "0.1.1"][:3]


# ------------------------------------------------------------------ plant runs (D4)

def plant_violations(ws):
    bad = []
    runs = {}
    for i, w in enumerate(ws):
        first_of_game = i == 0 or ws[i - 1]["game"] != w["game"] or ws[i - 1]["seed"] != w["seed"]
        if w["pos"] == 1:
            runs.setdefault((w["seed"], w["game"]), []).append(w["plant"])
        elif not first_of_game and w["plant"] != ws[i - 1]["plant"]:
            bad.append("%s window %d: plant changes inside a run" % (w["pt"], w["k"]))
        want_res = (not first_of_game) and w["pos"] == 1 and ws[i - 1]["plant"]
        if w["res"] != want_res:
            bad.append("%s window %d: res=%s, the window before it plant=%s" % (w["pt"], w["k"], w["res"],
                                                                               None if first_of_game else ws[i - 1]["plant"]))
    for key, flags in runs.items():
        for b in range(len(flags) // 5):
            if sum(flags[5 * b:5 * b + 5]) != 1:
                bad.append("%s block %d: %d plant runs of five" % (key, b, sum(flags[5 * b:5 * b + 5])))
    return bad


def test_p1_plant_runs_hold():
    assert plant_violations(window_events()) == []


def test_p1_res_on_the_last_window_fails():
    assert plant_violations(window_events(plant="res_last")) != []


def spin_frames(plant="tip", frames=600, seed=11):
    """Boundary over a long point: per live frame (plant_now, gate, WinPlant, LiveFrame)."""
    s = Sched(plant=plant, seed=seed)
    s.game_start()
    out = []
    for _ in range(frames):
        s.boundary(True)
        out.append((s.plant_now, s.gate, s.WinPlant, s.LiveFrame))
    return out


def spin_violations(fs):
    bad = ["frame %d planted outside a plant run's OFF window" % lf for now, gate, wp, lf in fs if now and not (gate and wp)]
    bad += ["frame %d: a plant run's OFF window not planted" % lf for now, gate, wp, lf in fs
            if gate and wp and lf >= 2 and not now]
    return bad


def test_p1_spin_only_in_plant_runs():
    fs = spin_frames()
    assert any(f[0] for f in fs) and spin_violations(fs) == []
    assert spin_violations(spin_frames(plant="any")) != []


# ------------------------------------------------------------------ ownership (FtFrames: captured owners)

class FramesPort:
    """FtFrames' ownership (TIP_P1_FRAMES: Frame, CaptureOwner, FlushWindow; TIP_FRAMES' StartPoint and EndPoint):
    a window's owner is captured when its first measured frame closes, a frame whose schedule window differs first
    writes the open window as partial, and lines are written from the captured owner. owner 'emit' reads the owner
    at write time (bd673226's form); 'relabel' flips the captured arm at write time (the totals unchanged);
    'reentrant' is EndPoint without its open flag."""

    def __init__(self, W, owner="tip"):
        self.W, self.mode = W, owner
        self.wn, self.o, self.oid, self.f0, self.frames = 0, None, None, 0, []
        self.pt_open, self.pt = False, None

    @staticmethod
    def owner_of(s):
        return (s.label(), s.WinK, s.ArmOn, s.PrevArm, s.WinP24, s.WinRun, s.WinPos, s.WinCoin, s.WinPlant, s.WinRes)

    def frame(self, s, fid, closing, truth):
        if not s.Live or s.LiveFrame < 2 or closing:
            return
        if self.wn > 0 and (s.WinK, s.Game, s.Round, s.PointInRound) != self.oid:
            self.flush(s, True)
        if self.wn == 0:
            self.o, self.oid, self.f0 = self.owner_of(s), (s.WinK, s.Game, s.Round, s.PointInRound), s.LiveFrame
        self.frames.append((fid, self.owner_of(s), truth))
        self.wn += 1
        if self.wn == self.W:
            self.flush(s, False)

    def flush(self, s, partial):
        owner = self.o
        if self.mode == "emit":
            owner = self.owner_of(s)
        elif self.mode == "relabel":
            owner = owner[:2] + (not owner[2],) + owner[3:]
        s.ev("w", owner, self.f0, list(self.frames), self.wn, partial)
        self.wn, self.frames = 0, []

    def start_point(self, s):
        self.wn, self.frames, self.pt_open, self.pt = 0, [], True, s.label()

    def end_point(self, s):
        if not self.pt_open and self.mode != "reentrant":
            return
        self.pt_open = False
        if self.wn > 0:
            self.flush(s, True)
        s.ev("p", self.pt)


def a11_ownership(ev, W=2):
    """Every window line's frames were measured under the line's owner, in the game the line names while that game
    was on; its n is its frames' count, f0 its first frame, a full line holds W frames, and no frame is in two."""
    bad, seen = [], set()
    for e in ev:
        if e[0] != "w":
            continue
        _, owner, f0, frames, n, partial = e
        if n != len(frames):
            bad.append("%s: n=%d over %d frames" % (owner[0], n, len(frames)))
        if not partial and n != W:
            bad.append("%s: a full window of %d frames" % (owner[0], n))
        if f0 != 2 + W * owner[1]:
            bad.append("%s window %d: f0=%d" % (owner[0], owner[1], f0))
        for fid, fo, (started, on) in frames:
            if fo != owner:
                bad.append("frame %d measured under %s, written as %s" % (fid, fo, owner))
            if not on or started != int(owner[0].split(".")[0]):
                bad.append("frame %d (game %d, on %s) written in %s" % (fid, started, on, owner[0]))
            if fid in seen:
                bad.append("frame %d in two lines" % fid)
            seen.add(fid)
    return bad


@pytest.mark.parametrize("seq", sorted(SEQS))
def test_p1_ownership_holds(seq):
    ev = run(seq)
    assert a11_ownership(ev) == []
    assert sum(1 for e in ev if e[0] == "p") == sum(1 for e in ev if e[0] == "end")


def test_p1_window_lines_are_written():
    """The control has content: the sequences fill windows, and a game's first point's windows are owned by it."""
    ev = run("start_after_live")
    ws = [e for e in ev if e[0] == "w"]
    assert len(ws) >= 6 and any(not e[5] for e in ws) and any(e[5] for e in ws)
    assert {e[1][0] for e in ws} >= {"0.1.1", "1.1.1"}


def test_p1_c28259c1_ownership_order_refused():
    for seq in ("start_after_live", "over_inside"):
        assert a11_ownership(run(seq, owner="emit", **OLD_ALL)) != [], seq
        assert a11_ownership(run(seq, **OLD_ALL)) != [], seq
        assert a11_ownership(run(seq, owner="emit")) == [], seq     # the tip's order: write time equals open time


def test_p1_relabel_keeping_totals_refused():
    ev = run("start_after_live", owner="relabel")
    ws = [e for e in ev if e[0] == "w"]
    assert ws and all(e[4] == len(e[3]) for e in ws)              # the totals are the tip's
    assert a11_ownership(ev) != []


def test_p1_endpoint_writes_once():
    for mode, lines in (("tip", 1), ("reentrant", 2)):
        s = Sched(owner=mode)
        s.game_start()
        s.boundary(True)
        s.fr.end_point(s)
        s.fr.end_point(s)
        assert sum(1 for e in s.events if e[0] == "p") == lines, mode


# ------------------------------------------------------------------ the partition and its tenths

CLS_G, CLS_W, CLS_R, CLS_S, CLS_E = range(5)
CLASS_OF_KIND = {"gated": CLS_S, "upkeep": CLS_R, "replay": CLS_R, "writer": CLS_W}


class Thread:
    """The main thread: k its executed cycles, gc the GC hook's cycles, t the Stopwatch."""

    def __init__(self):
        self.k = self.gc = self.t = 0


class SpanPort:
    """FtSpan's class stack (TIP_P1_SPAN: Mark, Switch, Cut, Open, Close, PushWriter, PopWriter). mutant 'drop_g'
    leaves GC inside the classes."""

    def __init__(self, th, mutant="tip"):
        self.th, self.m = th, mutant
        self.acc, self.cls, self.prev = [0] * 5, CLS_E, []
        self.k, self.g, self.gok = 0, 0, False
        self.marks = 0

    def mark(self, k, g, gok):
        d = k - self.k
        if gok and self.gok and self.m != "drop_g":
            d -= g - self.g
        self.acc[self.cls] += d
        self.k, self.g, self.gok = k, g, gok

    def switch(self, cls):
        self.marks += 1
        self.mark(self.th.k, self.th.gc, True)
        self.cls = cls

    def calibrate(self, n, step=7):
        """CalibrateMarks: n transitions between S and R, then Acc, Marks and the class state restored (mutant
        'cal_no_restore' keeps what the transitions did)."""
        saved = (list(self.acc), self.cls, self.k, self.g, self.gok, self.marks)
        for i in range(n):
            self.th.k += step
            self.switch(CLS_S if i % 2 == 0 else CLS_R)
        if self.m != "cal_no_restore":
            self.acc, self.cls, self.k, self.g, self.gok, self.marks = saved

    def cut(self, k, g, gok):
        self.mark(k, g, gok)

    def open(self, kind):
        self.prev.append(self.cls)
        cls = CLS_W if self.cls == CLS_W else CLASS_OF_KIND[kind]
        if cls != self.cls:
            self.switch(cls)

    def close(self):
        p = self.prev.pop()
        if p != self.cls:
            self.switch(p)

    def push_writer(self):
        self.prev.append(self.cls)
        if self.cls != CLS_W:
            self.switch(CLS_W)

    pop_writer = close


class LedgerPort:
    """FtLedger's cumulative counters (Take, Level, AppendTok): an enqueue in the gate's arm when the producer runs,
    done in the gate's arm when the service runs. mutant 'enq_at_service' loses the producer's identity: the token
    is counted in the arm of its service."""

    def __init__(self, mutant="tip"):
        self.m = mutant
        self.c = dict(enqON=0, enqOFF=0, doneON=0, doneOFF=0, disc=0)
        self.pending = []

    def enq(self, on):
        self.pending.append(on)
        if self.m != "enq_at_service":
            self.c["enqON" if on else "enqOFF"] += 1

    def done(self, on):
        n = len(self.pending)
        if self.m == "enq_at_service":
            self.c["enqON" if on else "enqOFF"] += n
        self.c["doneON" if on else "doneOFF"] += n
        self.pending = []
        return n

    def take(self):
        return dict(self.c)

    @staticmethod
    def level(t):
        return t["enqON"] + t["enqOFF"] - t["doneON"] - t["doneOFF"] - t["disc"]


class RecordsPort:
    """FtClock.OnStart's per-frame partition and FtFrames' window sums and tenths (TIP_P1_CLOCK, TIP_P1_FRAMES).
    mutant 'q_from_f' fills q from the frame period."""

    def __init__(self, th, span, ledger, W=24, mutant="tip"):
        self.th, self.span, self.ledger, self.W, self.m = th, span, ledger, W, mutant
        self.open, self.acc0, self.gprev, self.k0, self.t0 = False, [0] * 5, 0, 0, 0
        self.recs, self.arm = [], None
        self.lb = ledger.take()
        self._reset()

    def _reset(self):
        self.w = dict(n=0, sF=0, sC=0, cG=0, cW=0, cR=0, cS=0, cE=0, q=[0] * (self.W // BIN), r=[0] * (self.W // BIN),
                      qn=[0] * (self.W // BIN))

    def on_start(self, arm):
        """FT_Start: the closing frame's readings, the cut, the frame's partition, then the next frame's arm."""
        th, a = self.th, self.span.acc
        self.span.cut(th.k, th.gc, True)
        if self.open:
            self.frame(th.t - self.t0, th.k - self.k0, th.gc - self.gprev, a[CLS_W] - self.acc0[CLS_W],
                       a[CLS_R] - self.acc0[CLS_R], a[CLS_S] - self.acc0[CLS_S], a[CLS_E] - self.acc0[CLS_E])
        self.acc0, self.gprev, self.k0, self.t0, self.open = list(a), th.gc, th.k, th.t, True
        if arm is not None and self.w["n"] == 0:
            self.arm = arm

    def frame(self, f, c, cg, cw, cr, cs, ce):
        w, b = self.w, self.w["n"] // BIN
        w["n"] += 1
        w["sF"] += f
        w["sC"] += c
        w["cG"] += cg
        w["cW"] += cw
        w["cR"] += cr
        w["cS"] += cs
        w["cE"] += ce
        w["q"][b] += f if self.m == "q_from_f" else c - cg - cw
        w["r"][b] += cr
        w["qn"][b] += 1
        if w["n"] == self.W:
            le = self.ledger.take()
            w["arm"], w["tok"] = self.arm, (LedgerPort.level(self.lb), le["enqON"] - self.lb["enqON"],
                                            le["enqOFF"] - self.lb["enqOFF"], le["doneON"] - self.lb["doneON"],
                                            le["doneOFF"] - self.lb["doneOFF"], le["disc"] - self.lb["disc"],
                                            LedgerPort.level(le))
            self.recs.append(w)
            self.lb = le
            self._reset()


def partition_violations(recs):
    """SHARED.md's invariants: sC = cG + cW + cR + cS + cE; sum(q) = sC - cG - cW; sum(r) = cR; sum(qn) = n; and the
    tok reconciliation open0 + enqON + enqOFF = doneON + doneOFF + disc + open1."""
    bad = []
    for i, w in enumerate(recs):
        if w["sC"] != w["cG"] + w["cW"] + w["cR"] + w["cS"] + w["cE"]:
            bad.append("window %d: sC %d, partition %d" % (i, w["sC"], w["cG"] + w["cW"] + w["cR"] + w["cS"] + w["cE"]))
        if sum(w["q"]) != w["sC"] - w["cG"] - w["cW"]:
            bad.append("window %d: sum(q) %d, sC - cG - cW %d" % (i, sum(w["q"]), w["sC"] - w["cG"] - w["cW"]))
        if sum(w["r"]) != w["cR"]:
            bad.append("window %d: sum(r) %d, cR %d" % (i, sum(w["r"]), w["cR"]))
        if sum(w["qn"]) != w["n"]:
            bad.append("window %d: sum(qn) %d, n %d" % (i, sum(w["qn"]), w["n"]))
        t = w["tok"]
        if t[0] + t[1] + t[2] != t[3] + t[4] + t[5] + t[6]:
            bad.append("window %d: tok %s does not reconcile" % (i, t))
    return bad


def arms_for(nwin, seed=5, points=4):
    """The tip's window arms over consecutive points of one game (Sched.open_window)."""
    s = Sched(seed=seed)
    s.Game, s.Round = 0, 1
    out = []
    for p in range(points):
        s.PointInRound = p + 1
        for k in range(nwin):
            s.open_window(k)
            out.append(s.ArmOn)
    return out


def simulate(scenario, span_m="tip", rec_m="tip", ledger_m="tip", W=24, nwin=24, points=4,
             e0=4000, r0=700, s0=1000, alpha=5, gamma=100, wbuf=60, sigma=240):
    """Collectors in format M over the tip's window arms: every frame does e0 outside any scope and r0 in an upkeep
    scope (R, both arms); an ON frame also runs a gated scope (S) of s0 cycles with a nested upkeep read, allocates
    alpha units (scenarios 'alloc', 'both') and writes one log line as a W scope of wbuf cycles (a token;
    'enqueue', 'both'). Payment: GC of gamma per unit and the line's service of sigma, as W, at the window's last
    frame ('direct') or at the next window's first frame (otherwise; the last window pays directly). Returns the
    window records and the always-ON truth per frame."""
    th = Thread()
    span = SpanPort(th, span_m)
    ledger = LedgerPort(ledger_m)
    rec = RecordsPort(th, span, ledger, W, rec_m)
    arms = arms_for(nwin, points=points)
    alloc = scenario in ("alloc", "both", "alloc_direct", "both_direct")
    enq = scenario in ("enqueue", "both", "enqueue_direct", "both_direct")
    direct = scenario.endswith("direct")
    owed_units = 0

    def work(n, gc=False):
        th.k += n
        th.t += n + 37          # the frame period runs past the executed cycles (waits, other threads)
        if gc:
            th.gc += n

    def pay(on):
        nonlocal owed_units
        if owed_units:
            work(gamma * owed_units, gc=True)
            owed_units = 0
        if ledger.pending:
            span.push_writer()
            work(sigma * len(ledger.pending))
            span.pop_writer()
            ledger.done(on)

    for wi, on in enumerate(arms):
        for fi in range(W):
            rec.on_start(on)
            last = wi == len(arms) - 1
            if fi == 0 and not direct and wi > 0:
                pay(on)
            work(e0)
            span.open("upkeep")
            work(r0)
            span.close()
            if on:
                span.open("gated")
                work(s0 // 2)
                span.open("upkeep")                 # a nested retained read stays R and suspends S
                work(50)
                span.close()
                work(s0 // 2 - 50)
                if alloc:
                    owed_units += alpha
                if enq:
                    span.push_writer()
                    work(wbuf)
                    span.pop_writer()
                    ledger.enq(on)
                span.close()
            if fi == W - 1 and (direct or last):
                pay(on)
    rec.on_start(None)
    truth = r0 + s0 + (alpha * gamma if alloc else 0) + (wbuf + sigma if enq else 0)
    return rec.recs, truth


def _means(recs):
    on = [w for w in recs if w["arm"]]
    off = [w for w in recs if not w["arm"]]
    return on, off, sum(w["n"] for w in on), sum(w["n"] for w in off)


def recovery(recs):
    """The contrast on C-degree, R_OFF restored (method-v54.md:17-19), plus the always-ON GC and writer charges once
    outside it: GC by its frame rate over the ON frames (every collection here is collector-attributable, so this is
    the envelope), the writer by its service cost per token times the ON windows' tokens per ON frame."""
    on, off, n1, n0 = _means(recs)
    contrast = sum(sum(w["q"]) for w in on) / n1 - sum(sum(w["q"]) - sum(w["r"]) for w in off) / n0
    g = sum(w["cG"] for w in recs) / n1
    units = sum(w["tok"][1] + w["tok"][2] for w in recs)
    per_unit = sum(w["cW"] for w in recs) / units if units else 0.0
    return contrast + g + per_unit * sum(w["tok"][1] for w in recs) / n1


def subtraction(recs):
    """The same contrast on C with no partition: what the records replace."""
    on, off, n1, n0 = _means(recs)
    return sum(w["sC"] for w in on) / n1 - sum(w["sC"] - w["cR"] for w in off) / n0


SCENARIOS = ["direct", "alloc", "enqueue", "both", "alloc_direct", "enqueue_direct", "both_direct"]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_p1_partition_identities_hold(scenario):
    recs, _ = simulate(scenario)
    assert len(recs) == 96 and {w["arm"] for w in recs} == {True, False}
    assert partition_violations(recs) == []
    assert all(w["cS"] > 0 for w in recs if w["arm"]) and all(w["cS"] == 0 for w in recs if not w["arm"])


@pytest.mark.parametrize("mutant", ["drop_g", "q_from_f"])
def test_p1_partition_mutant_breaks_an_identity(mutant):
    kw = dict(span_m="drop_g") if mutant == "drop_g" else dict(rec_m="q_from_f")
    recs, _ = simulate("both", **kw)
    assert partition_violations(recs) != []


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_p1_records_recover_the_always_on_cost(scenario):
    """Moving payment across a switch does not change recovery (method-v54.md:50)."""
    recs, truth = simulate(scenario)
    assert abs(recovery(recs) - truth) < 1e-6, (recovery(recs), truth)


@pytest.mark.parametrize("scenario,lost", [("alloc", 500), ("enqueue", 240), ("both", 740)])
def test_p1_payment_across_a_switch_is_caught(scenario, lost):
    """Allocate ON, collect OFF and enqueue ON, service OFF (method-v54.md:47-48): subtraction on C misses the payment
    that lands in the next window, whose arm is independent; the records' recovery does not."""
    recs, truth = simulate(scenario)
    assert abs(subtraction(recs) - truth) > 0.3 * lost
    assert abs(recovery(recs) - truth) < 1e-6


@pytest.mark.parametrize("scenario", ["direct", "alloc_direct", "enqueue_direct", "both_direct"])
def test_p1_direct_timing_passes(scenario):
    """The negative control: payment in its own window, so subtraction on C is already right."""
    recs, truth = simulate(scenario)
    assert abs(subtraction(recs) - truth) < 1e-6 and abs(recovery(recs) - truth) < 1e-6


def test_p1_token_without_producer_identity_fails():
    """The token survives switching (method-v54.md:48): counted in its service window's arm, the writer charge is
    wrong once service moves across the switch, and right while it does not."""
    recs, truth = simulate("enqueue", ledger_m="enq_at_service")
    assert abs(recovery(recs) - truth) > 10
    recs, truth = simulate("enqueue_direct", ledger_m="enq_at_service")
    assert abs(recovery(recs) - truth) < 1e-6


# ------------------------------------------------------------------ r1 (ftb/to-p1-r1.md; SHARED.md md5 18fdafea)

import hashlib  # noqa: E402

# SHARED.md, the window line: the keys FlushWindow appends after the w line's own fields, in order
WINDOW_KEYS = ["run", "pos", "unit", "coin", "wi", "f0", "pred", "prun", "res", "gcn", "cG", "cW", "cR", "cS", "cE",
               "q", "r", "qn", "wu", "tok", "nm"]
# the writer type keys of wu and tok (FtLedger.TypeNames), in their print order
LEDGER_TYPES = ["log", "hash", "recv", "sock"]


def window_keys(src):
    """Every `" key=` literal FlushWindow prints, in order (AppendBins' " q=" included)."""
    return re.findall(r'" (\w+)=', "\n".join(_body(src, SIG_FR_FLUSH)))


def window_key_violations(src):
    keys = window_keys(src)
    bad = []
    if len(set(keys)) != len(keys):
        bad.append("duplicate keys: %s" % sorted(k for k in set(keys) if keys.count(k) > 1))
    tail = keys[keys.index("run"):] if "run" in keys else []
    if tail != WINDOW_KEYS:
        bad.append("appended keys %s, SHARED.md %s" % (tail, WINDOW_KEYS))
    return bad


def test_window_keys_are_shared_md():
    assert window_key_violations(_src("FtFrames.cs")) == []


@pytest.mark.parametrize("old,new", [
    # the 2dcde737 block: plant= and partial= appended a second time
    ('.Append(" prun=").Append(_oPlantRun ? 1 : 0).Append(" res=").Append(_oRes ? 1 : 0)\n              .Append(" gcn=")',
     '.Append(" plant=").Append(_oPlantRun ? 1 : 0).Append(" res=").Append(_oRes ? 1 : 0)\n'
     '              .Append(" partial=").Append(partial ? 1 : 0).Append(" gcn=")'),
    # nm missing
    ('            sb.Append(" nm=").Append(FtLedger.Marks(_lb, _le));\n', ''),
])
def test_window_keys_mutant_fails(old, new):
    src = _src("FtFrames.cs")
    assert window_key_violations(src) == []                     # the negative control
    old, new = old.replace("\n", "\r\n" if "\r\n" in src else "\n"), new.replace("\n", "\r\n" if "\r\n" in src else "\n")
    assert src.count(old) == 1
    assert window_key_violations(src.replace(old, new)) != []


def test_ledger_type_keys():
    src = _src("FtUpload.cs")
    m = re.search(r'TypeNames = \{ ([^}]*) \};', src)
    assert [x.strip().strip('"') for x in m.group(1).split(",")] == LEDGER_TYPES
    assert src.count("internal const int Log = 0, Hash = 1, Recv = 2, Sock = 3, Types = 4;") == 1


class TypedLedgerPort:
    """FtLedger per type (TIP_P1_LEDGER: Enq, Serve, Take, Level, AppendWu, AppendTok): enqueued in the gate's arm
    at the producer; done (or discarded) in the gate's arm at the service, with its units and cycles. mutant
    'cross_type' books a hash job's service on log: one type loses a token and another gains one."""

    PER = 7

    def __init__(self, mutant="tip"):
        self.m = mutant
        self.c = [0] * (len(LEDGER_TYPES) * self.PER)
        self.marks = 0

    def enq(self, t, on, n=1):
        self.c[t * self.PER + (0 if on else 1)] += n

    def serve(self, t, n, ok, on, cyc):
        if self.m == "cross_type" and t == 1:
            t = 0
        o = t * self.PER
        if ok:
            self.c[o + (2 if on else 3)] += n
            self.c[o + 5] += n
        else:
            self.c[o + 4] += n
        self.c[o + 6] += cyc

    def take(self):
        return list(self.c) + [self.marks]

    @classmethod
    def level(cls, s, t):
        o = t * cls.PER
        return s[o] + s[o + 1] - s[o + 2] - s[o + 3] - s[o + 4]

    @classmethod
    def tok(cls, a, b):
        out = []
        for t, name in enumerate(LEDGER_TYPES):
            o = t * cls.PER
            out.append("%s:%d,%d,%d,%d,%d,%d,%d" % (name, cls.level(a, t), b[o] - a[o], b[o + 1] - a[o + 1],
                                                    b[o + 2] - a[o + 2], b[o + 3] - a[o + 3], b[o + 4] - a[o + 4],
                                                    cls.level(b, t)))
        return ";".join(out)

    @classmethod
    def wu(cls, a, b):
        return ";".join("%s:%d:%d" % (name, b[t * cls.PER + 5] - a[t * cls.PER + 5], b[t * cls.PER + 6] - a[t * cls.PER + 6])
                        for t, name in enumerate(LEDGER_TYPES))


def ledger_windows(mutant="tip", windows=12, frames=10, seed=3):
    """A sitting's windows with all three types live. log: collector lines on the main thread, flushed every 7th
    frame on the timer thread; hash: two jobs, each spanning several windows; recv: one message per frame, entered and
    exited inside it. Returns (tok strings, wu strings, the true per-type inventory at each window's end)."""
    import random
    rng = random.Random(seed)
    L = TypedLedgerPort(mutant)
    pending = [0] * len(LEDGER_TYPES)
    toks, wus, truth = [], [], []
    hash_jobs = {15: "begin", 40: "end", 41: "begin", 70: "end"}
    lb = L.take()
    f = 0
    for w in range(windows):
        on = w % 2 == 0
        for _ in range(frames):
            for _ in range(rng.randrange(3)):
                L.enq(0, on)
                pending[0] += 1
            if f % 7 == 6 and pending[0]:
                L.serve(0, pending[0], True, on, 1000)
                pending[0] = 0
            if hash_jobs.get(f) == "begin":
                L.enq(1, on)
                pending[1] += 1
            elif hash_jobs.get(f) == "end":
                L.serve(1, 1, True, on, 50000)
                pending[1] -= 1
            L.enq(2, on)
            L.serve(2, 1, True, on, 300)
            f += 1
        le = L.take()
        toks.append(L.tok(lb, le))
        wus.append(L.wu(lb, le))
        truth.append(list(pending))
        lb = le
    return toks, wus, truth


def _parse_tok(tok):
    out = []
    for part in tok.split(";"):
        k, v = part.split(":")
        out.append((k, [int(x) for x in v.split(",")]))
    return out


def tok_violations(toks, keys=LEDGER_TYPES, summed=False):
    """What the parser can check from the lines alone, per type (summed=True: the pre-r1 single sum over the types):
    the key set, open0 + enqON + enqOFF = doneON + doneOFF + disc + open1, no negative inventory, and each window's
    open0 equal to the window before's open1."""
    bad, prev = [], None
    for i, tok in enumerate(toks):
        items = _parse_tok(tok)
        if [k for k, _ in items] != keys:
            bad.append("window %d: keys %s" % (i, [k for k, _ in items]))
            continue
        if summed:
            items = [("all", [sum(v[j] for _, v in items) for j in range(7)])]
        for k, (o0, e1, e0, d1, d0, x, o1) in items:
            if o0 + e1 + e0 != d1 + d0 + x + o1:
                bad.append("window %d %s: does not reconcile" % (i, k))
            if o0 < 0 or o1 < 0:
                bad.append("window %d %s: negative inventory %d,%d" % (i, k, o0, o1))
        if prev is not None:
            for (k, v), (_, p) in zip(items, prev):
                if v[0] != p[6]:
                    bad.append("window %d %s: open0 %d, previous open1 %d" % (i, k, v[0], p[6]))
        prev = items
    return bad


def test_tok_per_type_reconciles():
    toks, wus, truth = ledger_windows()
    assert tok_violations(toks) == []
    for tok, inv in zip(toks, truth):                           # the emitted inventory is the true one, per type
        assert [v[6] for _, v in _parse_tok(tok)] == inv
    for wu in wus:
        assert [p.split(":")[0] for p in wu.split(";")] == LEDGER_TYPES
        assert "NA" not in wu                                    # every type's cycles measured (D5, r1 item 4)
    assert any(int(p.split(":")[1]) for wu in wus for p in wu.split(";") if p.startswith("hash"))


def test_tok_cross_type_offset_fails_per_type_only():
    toks, _, truth = ledger_windows("cross_type")
    assert tok_violations(toks) != []                            # per type: log goes negative, hash never drains
    assert tok_violations(toks, summed=True) == []               # summed over the types the offset is invisible
    sums = [sum(v[6] for _, v in _parse_tok(t)) for t in toks]
    assert sums == [sum(inv) for inv in truth]                   # ... the total even matches the truth


def test_span_marks_and_calibration_restore():
    th = Thread()
    sp = SpanPort(th)
    sp.open("upkeep"); th.k += 10; sp.close()                   # E -> R -> E: two transitions
    sp.open("writer"); sp.open("gated"); th.k += 5; sp.close(); sp.close()   # W dominates: E -> W -> E
    assert sp.marks == 4
    before = (list(sp.acc), sp.cls, sp.k, sp.marks)
    sp.calibrate(1000)
    assert (sp.acc, sp.cls, sp.k, sp.marks) == before            # nothing moved between classes, nm unchanged
    th.k += 3
    sp.cut(th.k, th.gc, True)
    assert sum(sp.acc) == th.k                                   # the calibration's cycles fall to the class open
    assert sp.acc[CLS_E] == th.k - 15
    th2 = Thread()
    bad = SpanPort(th2, mutant="cal_no_restore")
    bad.calibrate(1000)
    assert bad.marks != 0 and (bad.acc[CLS_R] or bad.acc[CLS_S])


# D5 scopes 2 and 3: FrameTime-only code at the writer sites. The release view (no SCR_FRAMETIME) of each file is
# the base's (bd673226), byte for byte; each ledger call sits in the method it measures.
RELEASE_VIEW_SHA = {
    "SeatEvidence.cs": "19bc0c83188b28d3e7b124b6410b875467ccfa4bad5f1fad7ba395be0790b36a",
    "PeerBuild.cs": "07588406df16ff6b8329c7419b6135b96489c90804183a914eb116d82d19516d",
}
SITE_CALLS = {
    "SeatEvidence.cs": [
        ("private static void HashPending()", "FtLedger.HashBegin()", 2),
        ("private static void HashPending()", "FtLedger.HashEnd(ftK, ftOk)", 2),
        ("internal static int EnterRpc(ExitGames.Client.Photon.Hashtable data, Photon.Realtime.Player sender)",
         "FtLedger.RecvEnter()", 1),
        ("internal static int EnterRpc(ExitGames.Client.Photon.Hashtable data, Photon.Realtime.Player sender)",
         "FtLedger.RecvExit(ftRecv)", 1),
        ("internal static void ExitRpc(int before)", "FtLedger.RecvCycles(ftRecv)", 1),
    ],
    "PeerBuild.cs": [
        ("internal static void Tick()", "FtLedger.RecvEnter()", 1),
        ("internal static void Tick()", "FtLedger.RecvExit(ftRecv)", 1),
    ],
}


def release_view(text):
    """The source as a build without SCR_FRAMETIME compiles it: each `#if SCR_FRAMETIME` branch dropped, its `#else`
    kept, its directives removed; any other directive block kept as written. None when the directives do not nest."""
    out, stack = [], []
    for ln in text.replace("\r\n", "\n").split("\n"):
        d = ln.strip()
        if d.startswith("#if"):
            if d == "#if SCR_FRAMETIME":
                stack.append(["ft", True])
                continue
            stack.append(["other", None])
        elif d.startswith("#elif") or d == "#else":
            if not stack:
                return None
            if stack[-1][0] == "ft":
                if d != "#else":
                    return None
                stack[-1][1] = False
                continue
        elif d.startswith("#endif"):
            if not stack:
                return None
            if stack.pop()[0] == "ft":
                continue
        if not any(e[0] == "ft" and e[1] for e in stack):
            out.append(ln)
    return None if stack else "\n".join(out)


def site_violations(srcs):
    bad = []
    for f, calls in SITE_CALLS.items():
        rv = release_view(srcs[f])
        if rv is None or hashlib.sha256(rv.encode()).hexdigest() != RELEASE_VIEW_SHA[f]:
            bad.append("%s: the release view differs from bd673226's" % f)
        for sig, call, n in calls:
            j, k = _span(srcs[f], sig)
            got, total = srcs[f][j:k].count(call), srcs[f].count(call)
            if got != n or total != n:
                bad.append("%s %s: %s %d in the method, %d in the file, want %d" % (f, sig, call, got, total, n))
    return bad


def _site_sources():
    return {f: (PLUGIN / f).read_text(encoding="utf-8-sig") for f in SITE_CALLS}


SITE_MUTANTS = {
    # the recv entry moved out of the FrameTime block: the release build changes
    "recv_in_release": ("SeatEvidence.cs",
                        "#if SCR_FRAMETIME\n            ulong ftRecv = FtLedger.RecvEnter();",
                        "            ulong ftRecv = FtLedger.RecvEnter();\n#if SCR_FRAMETIME\n"),
    # a peer read entered and never exited
    "peer_no_exit": ("PeerBuild.cs", "finally { FtLedger.RecvExit(ftRecv); }", "finally { }"),
    # the game DLL's job unmeasured
    "hash_one_job": ("SeatEvidence.cs", "                ftJob = _gameState == ID_PENDING; ftOk = false;\n"
                     "                ftK = ftJob ? FtLedger.HashBegin() : 0;\n",
                     "                ftJob = false; ftOk = false;\n"),
}


def test_site_release_view_and_calls():
    assert site_violations(_site_sources()) == []


@pytest.mark.parametrize("name", sorted(SITE_MUTANTS))
def test_site_mutant_fails(name):
    f, old, new = SITE_MUTANTS[name]
    srcs = _site_sources()
    assert site_violations(srcs) == []                           # the negative control
    e = "\r\n" if "\r\n" in srcs[f] else "\n"
    old, new = old.replace("\n", e), new.replace("\n", e)
    assert srcs[f].count(old) == 1
    srcs[f] = srcs[f].replace(old, new)
    assert site_violations(srcs) != []


P1_R1_SOURCE_MUTANTS = {
    # every type's service booked on one type (the loss-and-surplus offset, in the C#)
    "serve_one_type": ("FtUpload.cs", "                int o = t * Per;\n                if (ok)", "                int o = 0;\n                if (ok)"),
    # tok summed over the types (the 2dcde737 form)
    "level_summed": ("FtUpload.cs", "            int b = t * Per;\n", "            int b = 0;\n"),
    # nm never counted
    "nm_dropped": ("FtSpan.cs", "            Marks++;\n", ""),
    # the calibration leaves its transitions in the classes
    "cal_no_restore": ("FtSpan.cs", "            System.Array.Copy(acc, Acc, Classes);\n", ""),
    # the hash thread's cycles back to NA (no job measured on its thread)
    "hash_cycles_main": ("FtUpload.cs", "            Enq(Hash, 1);\n            return FtClock.Cycles();", "            Enq(Hash, 1);\n            return 0;"),
}


@pytest.mark.parametrize("name", sorted(P1_R1_SOURCE_MUTANTS))
def test_p1_r1_source_mutant_fails(name):
    fname, old, new = P1_R1_SOURCE_MUTANTS[name]
    assert pin_violations(_sources()) == []                       # the negative control: the tip passes
    assert pin_violations(_mut(_sources(), fname, old, new)) != []


# ------------------------------------------------------------------ r2 (ftb/to-p1-r2.md; SHARED.md md5 2119eb2e): sock

import bisect  # noqa: E402
import math  # noqa: E402

# the four builds' define sets: the sock patch may compile only into FrameTime
BUILDS = {"Release": set(), "Thunderstore": {"THUNDERSTORE"}, "FrameTimeRef": {"SCR_FRAMETIME", "SCR_FT_NOCOLLECTORS"},
          "FrameTime": {"SCR_FRAMETIME"}}
SOCK_MARKS = ["class FtSockPatch", '"HandleReceivedDatagram"']


def _pp_eval(expr, defines):
    py = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: {"true": "True", "false": "False"}.get(
        m.group(0), str(m.group(0) in defines)), expr)
    py = py.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
    return bool(eval(py, {"__builtins__": {}}, {}))


def build_view(text, defines):
    """The source as a compiler with these defines sees it (#if, #elif, #else, #endif; ! && || and true). None when
    the directives do not nest."""
    out, stack = [], []   # each: [taking now, some branch taken, parent taking]
    for ln in text.replace("\r\n", "\n").split("\n"):
        d = ln.strip()
        live = all(e[0] for e in stack)
        if d.startswith("#if"):
            t = _pp_eval(d[3:], defines)
            stack.append([t, t, live])
            continue
        if d.startswith("#elif") or d == "#else":
            if not stack:
                return None
            e = stack[-1]
            t = (not e[1]) and (True if d == "#else" else _pp_eval(d[5:], defines))
            e[0], e[1] = t, e[1] or t
            continue
        if d.startswith("#endif"):
            if not stack:
                return None
            stack.pop()
            continue
        if live:
            out.append(ln)
    return None if stack else "\n".join(out)


def sock_build_violations(srcs):
    bad = []
    for b, defines in BUILDS.items():
        for f, text in srcs.items():
            v = build_view(text, defines)
            if v is None:
                bad.append("%s %s: directives do not nest" % (b, f))
                continue
            for mark in SOCK_MARKS:
                want = 1 if b == "FrameTime" and f == "FtUpload.cs" else 0
                if v.count(mark) != want:
                    bad.append("%s %s: %s %d, want %d" % (b, f, mark, v.count(mark), want))
    return bad


def _plugin_sources():
    return {p.name: p.read_text(encoding="utf-8-sig") for p in sorted(PLUGIN.glob("*.cs"))}


def test_build_view_evaluates_directives():
    # a check of the checker: nesting, #elif/#else, negation
    t = "\n".join(["a", "#if SCR_FRAMETIME", "b", "#if !SCR_FT_NOCOLLECTORS", "c", "#endif", "#else", "d", "#endif",
                   "#if THUNDERSTORE", "e", "#elif X", "f", "#else", "g", "#endif"])
    assert build_view(t, set()).split("\n") == ["a", "d", "g"]
    assert build_view(t, {"SCR_FRAMETIME"}).split("\n") == ["a", "b", "c", "g"]
    assert build_view(t, {"SCR_FRAMETIME", "SCR_FT_NOCOLLECTORS"}).split("\n") == ["a", "b", "g"]
    assert build_view(t, {"THUNDERSTORE"}).split("\n") == ["a", "d", "e"]
    assert build_view(t, {"X"}).split("\n") == ["a", "d", "f"]
    assert build_view(t + "\n#endif", set()) is None
    for f in SITE_CALLS:                                         # no ledger call in the D5 sites' release view
        v = build_view((PLUGIN / f).read_text(encoding="utf-8-sig"), set())
        assert v is not None and "FtLedger." not in v


def test_sock_patch_only_in_frametime():
    assert sock_build_violations(_plugin_sources()) == []


def _sock_block(src):
    i = src.index("#if !SCR_FT_NOCOLLECTORS\n    /// <summary>FtLedger's sock scope")
    j = src.index("#endif\n", i) + len("#endif\n")
    return i, j


@pytest.mark.parametrize("mutant", ["moved_past_gate", "ref_unguarded"])
def test_sock_patch_build_mutant_fails(mutant):
    srcs = _plugin_sources()
    assert sock_build_violations(srcs) == []                    # the negative control
    s = srcs["FtUpload.cs"].replace("\r\n", "\n")
    i, j = _sock_block(s)
    block = s[i:j]
    if mutant == "moved_past_gate":                              # the patch after the file's FrameTime #endif
        s = s[:i] + s[j:] + "namespace CompetitiveRounds\n{\n" + block + "}\n"
    else:                                                        # the reference build's guard removed
        inner = block.split("\n", 1)[1].rsplit("#endif\n", 1)[0]
        s = s[:i] + inner + s[j:]
    srcs["FtUpload.cs"] = s
    assert sock_build_violations(srcs) != []


def test_sock_target_is_the_per_datagram_handler():
    # the patch names IPhotonSocket.HandleReceivedDatagram(byte[], int, bool): the one method every Photon3Unity3D
    # 4.1.7.0 transport's receive loop calls per datagram (SocketUdp.ReceiveLoop and the five other transports)
    body = "\n".join(_body(_src("FtUpload.cs"), SIG_SOCK_TARGET))
    assert 'typeof(ExitGames.Client.Photon.IPhotonSocket), "HandleReceivedDatagram",' in body
    assert "new[] { typeof(byte[]), typeof(int), typeof(bool) });" in body
    assert "throw new System.Exception(" in body                  # a missing target is a Failed to patch line


class RecvThread(Thread):
    """A thread with its own executed-cycle counter."""


SOCK_EDGES = []
_prev = 0
for _i in range(176):
    _v = math.ceil(2.0 ** ((_i + 1) / 4.0))
    _prev = _v if _v > _prev else _prev + 1
    SOCK_EDGES.append(_prev)
del _i, _v, _prev


def sock_bucket(c):
    """FtLedger.SockBucket: the first edge above c."""
    return bisect.bisect_right(SOCK_EDGES, c)


class SockPort:
    """FtLedger's sock scope (SockEnter, SockExit, SockStats) driven by FtSockPatch on the receive thread: the
    prefix reads the calling thread's counter, the finalizer reads it again. mutant 'main_clock' reads the main
    thread's counter; 'double' counts a datagram twice."""

    def __init__(self, main, mutant="tip"):
        self.main, self.m = main, mutant
        self.hist = [0] * 177
        self.units = self.cyc = self.enq_on = self.done = 0

    def handle(self, th, cost, main_drift=0):
        clock = self.main if self.m == "main_clock" else th
        self.enq_on += 1
        k0 = clock.k
        th.k += cost
        self.main.k += main_drift
        k1 = clock.k
        n = 2 if self.m == "double" else 1
        self.units += n
        self.done += n
        self.cyc += k1 - k0
        self.hist[sock_bucket(k1 - k0)] += 1

    def stats(self):
        n = sum(self.hist)
        rank, cum = (95 * n + 99) // 100, 0
        for i, h in enumerate(self.hist):
            cum += h
            if cum >= rank:
                return (SOCK_EDGES[i] if i < len(SOCK_EDGES) else None), n


def sock_run(mutant="tip", datagrams=400, seed=9):
    import random
    rng = random.Random(seed)
    main, rx = Thread(), RecvThread()
    port = SockPort(main, mutant)
    costs = []
    for _ in range(datagrams):
        c = rng.choice([800, 1200, 2000, 5000]) + rng.randrange(400)
        costs.append(c)
        port.handle(rx, c, main_drift=rng.randrange(20000))
    return port, costs


def sock_violations(port, costs):
    bad = []
    if port.units != len(costs):
        bad.append("units %d, datagrams %d" % (port.units, len(costs)))
    if port.cyc != sum(costs):
        bad.append("cycles %d, the receive thread's %d" % (port.cyc, sum(costs)))
    if port.enq_on + 0 != port.done:
        bad.append("tok: enqON %d, done %d" % (port.enq_on, port.done))
    p95, n = port.stats()
    true95 = sorted(costs)[(95 * len(costs) + 99) // 100 - 1]
    if n != len(costs) or p95 is None or not (true95 < p95 <= true95 * 2 ** 0.25 + 2):
        bad.append("sock_p95 %s for a true p95 of %d (n %d)" % (p95, true95, n))
    return bad


def test_sock_port_tip():
    assert sock_violations(*sock_run()) == []


@pytest.mark.parametrize("mutant", ["main_clock", "double"])
def test_sock_port_mutant_fails(mutant):
    assert sock_violations(*sock_run()) == []                   # the negative control
    assert sock_violations(*sock_run(mutant)) != []


def test_sock_edges_are_the_csharp_edges():
    # SockEdges' loop, ported: the same 176 edges, strictly increasing, the last 2^44
    body = _body(_src("FtUpload.cs"), SIG_LG_SEDGES)
    assert "long v = (long)System.Math.Ceiling(System.Math.Pow(2.0, (i + 1) / 4.0));" in body
    assert "e[i] = v > prev ? v : prev + 1;" in body
    assert _src("FtUpload.cs").count("internal const int SockBuckets = 177;") == 1
    assert all(b > a for a, b in zip(SOCK_EDGES, SOCK_EDGES[1:])) and SOCK_EDGES[-1] == 2 ** 44


P1_R2_SOURCE_MUTANTS = {
    # a datagram counted twice
    "sock_double": ("FtUpload.cs", "            Serve(Sock, 1, true, k0, k1);\n", "            Serve(Sock, 2, true, k0, k1);\n"),
    # the bucket counted twice
    "sock_hist_double": ("FtUpload.cs", "            Interlocked.Increment(ref _sockHist[SockBucket(c)]);\n",
                         "            Interlocked.Increment(ref _sockHist[SockBucket(c)]);\n"
                         "            Interlocked.Increment(ref _sockHist[SockBucket(c)]);\n"),
    # sock's start cycles read from the main thread's last frame boundary, not the calling thread
    "sock_main_clock": ("FtUpload.cs", "            lock (_lock) _c[Sock * Per + EnqOn]++;\n            return FtClock.Cycles();",
                        "            lock (_lock) _c[Sock * Per + EnqOn]++;\n            return (ulong)FtSpan.Acc[FtSpan.ClsE];"),
    # a sock token enqueued in the gate's arm (the producer's arm is not known here)
    "sock_enq_gate": ("FtUpload.cs", "            lock (_lock) _c[Sock * Per + EnqOn]++;\n",
                      "            Enq(Sock, 1);\n"),
}


@pytest.mark.parametrize("name", sorted(P1_R2_SOURCE_MUTANTS))
def test_p1_r2_source_mutant_fails(name):
    fname, old, new = P1_R2_SOURCE_MUTANTS[name]
    assert pin_violations(_sources()) == []                       # the negative control: the tip passes
    assert pin_violations(_mut(_sources(), fname, old, new)) != []


def test_sock_clock_is_the_calling_threads():
    # FtClock.Cycles reads QueryThreadCycleTime on GetCurrentThread's pseudo-handle: the calling thread, whichever it is
    clock = _src("FtClock.cs")
    assert clock.count("private static readonly IntPtr Self = GetCurrentThread();") == 1
    assert clock.count("if (!QueryThreadCycleTime(Self, out k)) { CycleFailures++; return 0; }") == 1
    for sig in (SIG_LG_SENTER, SIG_LG_SEXIT):
        assert "FtClock.Cycles()" in "\n".join(_body(_src("FtUpload.cs"), sig))
