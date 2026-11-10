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
  A8 the settle cap: the last game is flushed by the boundary SETTLE_S past the settle's due time at the latest.
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

_BOUNDARY_TAIL = [
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
    ],
    SIG_END: [
        'FtGate.Off = false;',
        'FtFrames.EndPoint();',
        'PrevArm = ArmOn ? 1 : 0;',
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
        'if (skip == null) FtReplay.Run(g);',
        'else FtReplay.Skip(g, skip);',
    ],
    SIG_GAMESTART: [
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
        '_replayOwed = Game;',
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
        '_pn = 0; _pF = 0; _pS = 0; _pC = 0; _pMaxF = 0; _pMissingEnd = 0; _pP = 0; _excl = 0;',
        '_qn = 0; _qF = 0; _qS = 0; _qC = 0; _plantMixed = 0; _qP = 0;',
        '_g0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);',
        '_gn0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);',
        '_u0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Upkeep);',
        '_un0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Upkeep);',
        '_on0 = FtCensus.SumOn();',
        '_guard0 = FtCensus.SumGuarded();',
        '_windows = 0;',
        '_t0 = System.Diagnostics.Stopwatch.GetTimestamp();',
    ],
    SIG_FR_END: [
        'if (_wn > 0) FlushWindow(true);',
        'Plugin.Log.LogInfo("[FRAME-TIME] p pt=" + FtSchedule.Label() + " arm=" + (FtSchedule.ArmOn ? "ON" : "OFF")',
        '+ " gate=" + (FtSchedule.GateThisPoint ? 1 : 0)',
        '+ " pred=" + (FtSchedule.PrevArm < 0 ? "none" : FtSchedule.PrevArm == 1 ? "ON" : "OFF")',
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
        '+ " t0=" + _t0 + " t1=" + System.Diagnostics.Stopwatch.GetTimestamp() + " answer=" + FtReplay.AnswerField);',
        'LastN = _pn;',
        'LastSF = _pF;',
        '_btT0 = BetweenTicks();',
        '_btC0 = BetweenCalls();',
        '_btArm = FtSchedule.ArmOn ? "ON" : "OFF";',
        'if (FtPlant.Us < 0 && FtSchedule.Game >= 0 && !FtSchedule.ArmOn && _pn >= W)',
        'FtPlant.Fix((long)Math.Round(0.03 * _pF * 1000000.0 / ((double)_pn * System.Diagnostics.Stopwatch.Frequency)),',
        'FtSchedule.Label());',
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
    ] + _BOUNDARY_TAIL[6:],
    SIG_START: TIP[SIG_START],
    SIG_END: TIP[SIG_END],
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
                                 "FtReplay.cs", "FtClock.cs", "GameStateWatcher.cs", "FtCalib.cs")}


def pin_violations(srcs):
    """The scheduler's bodies against the port, FtDrive's completion split, FtFrames' bodies (F3), and every reset
    of the span and census sums (the class F3 names: a reset anywhere but GameStart, or an absolute write to those
    sums anywhere but their Reset bodies and FtCalib's two restores, is a violation)."""
    bad = []
    for name, table in (("FtSchedule.cs", TIP), ("FtDrive.cs", TIP_DRIVE), ("FtFrames.cs", TIP_FRAMES)):
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
    assert _body(_src("FtReplay.cs"), "internal static void Skip(int game, string result)") == [
        'if (FtConfig.F18 != "A" || !FtConfig.Present) return;',
        'Plugin.Log.LogInfo("[FRAME-TIME] answer_replay g=" + game + " ticks=0 result=" + result);']
    gsw = _src("GameStateWatcher.cs")
    assert gsw.count("FtSchedule.GameStart();") == 1 and gsw.count("FtSchedule.GameOver();") == 1
    assert gsw.count("FtSchedule.MatchEnded();") == 2
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
    matchend 'none' is MatchEnded doing nothing."""

    def __init__(self, boundary="tip", gamestart="tip", gameover="tip", closing="tip", open_="tip", settle="tip",
                 flush="tip", sitting="tip", matchend="tip", last_game=99, settle_frames=3):
        self.v = dict(boundary=boundary, gamestart=gamestart, gameover=gameover, closing=closing, open_=open_,
                      settle=settle, flush=flush, sitting=sitting, matchend=matchend)
        self.last_game, self.settle_frames = last_game, settle_frames
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
            return
        self.LiveFrame = 0
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

    # SIG_START (unchanged at the tip); FtZero.Early and FtFrames.StartPoint's baselines are events
    def start_point(self):
        if self.RoundOver:
            self.Round += 1
            self.PointInRound = 0
            self.RoundOver = False
            self.ArmOn = (self.Game + self.Round) % 2 == 0
        else:
            self.ArmOn = not self.ArmOn
        self.PointInRound += 1
        self.ev("zero_early", self.Game)
        self.LiveFrame = 0
        self.gate = not self.ArmOn
        self.point = {"label": self.label(), "base": self.span, "epoch": self.epoch, "acc": 0}
        self.ev("start", self.label())

    # SIG_END
    def end_point(self):
        self.gate = False
        self.frames_end_point()

    # FtFrames.EndPoint (TIP_FRAMES): the point line, its deltas against the baselines StartPoint took
    def frames_end_point(self):
        p = self.point
        self.ev("end", p["label"], self.label(), self.span - p["base"], p["epoch"], self.epoch, p["acc"])
        self.point = None

    # SIG_ENDOWED
    def end_owed_point(self, at_boundary):
        if not self.over_owed:
            return
        self.over_owed = False
        if self.Live:
            if at_boundary:
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
        if skip is None:
            self.replay_run(g)
        else:
            self.ev("replay_skip", g, self.FrameLive, skip)

    # SIG_GAMESTART
    def game_start(self):
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
            self.replay_owed = self.Game
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
        self.ev("replay", g, self.FrameLive)

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
    with no OnGameOver, the quit handler)."""
    for i, (live, calls, pick) in enumerate(frames):
        s.now = i
        s.ev("frame", i, s.closing_frame(live), s.Live)
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
            elif c == "GameOver":
                s.ev("gameover", s.Live, i, s.Game)
                s.game_over()
            elif c == "MatchEnded":
                s.ev("matchend", s.Live, i)
                s.match_ended()
            else:
                s.ev("quit", i)
                s.quit()
    s.ev("frames", len(frames))
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
}
LAST = {"settle": 0, "settle_stuck": 0}


def run(seq, **variant):
    s = Sched(last_game=LAST.get(seq, 99), **variant)
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
    quitting = False
    for i, e in enumerate(ev):
        if e[0] == "quit":
            quitting = True
        if e[0] == "gameover":
            overs.setdefault(e[3], []).append(i)
        elif e[0] == "replay":
            lines.setdefault(e[1], []).append(i)
            if e[2]:
                bad.append("replay call g=%d in a frame that started live" % e[1])
        elif e[0] == "replay_skip":
            lines.setdefault(e[1], []).append(i)
            why = e[3]
            if not ((why == "skipped_live" and e[2]) or (why == "skipped_quit" and quitting)):
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
    for g in sorted(overs):
        fl = [i for i, e in enumerate(ev) if e[0] == "flush" and e[1] == g]
        if len(fl) != 1:
            bad.append("game %d flushed %d times" % (g, len(fl)))
            continue
        ends = [i for i, e in enumerate(ev) if e[0] == "end" and int(e[1].split(".")[0]) == g]
        if ends and max(ends) > fl[0]:
            bad.append("game %d flushed before its point end" % g)
        rep = [i for i, e in enumerate(ev) if e[0] in ("replay", "replay_skip") and e[1] == g]
        if not rep or rep[0] > fl[0]:
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


CHECKS = {"A1": a1_straddles, "A2": a2_stale_baselines, "A3": a3_replays, "A4": a4_outside_game,
          "A5": a5_flushes, "A6": a6_end_frame_not_closing, "A7": a7_sitting, "A8": a8_settle_cap}

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
    ce1 = [("gameover", False, 0, 0), ("replay", 0, False), ("gameover", False, 1, 1), ("replay", 0, False)]
    assert a3_replays(ce1) != []
    # a flush before EndPoint
    ce2 = [("gameover", True, 0, 0), ("replay", 0, False), ("flush", 0, "settle", 4), _END_G0]
    assert a5_flushes(ce2) != []
    # no flush at all
    ce3 = [("gameover", False, 0, 0), ("replay", 0, False), _END_G0]
    assert a5_flushes(ce3) != []
    # the controls the other way: the same streams in the tip's order pass
    assert a3_replays([("gameover", False, 0, 0), ("replay", 0, False), ("gameover", False, 1, 1),
                       ("replay", 1, False)]) == []
    assert a5_flushes([("gameover", True, 0, 0), _END_G0, ("replay", 0, False), ("flush", 0, "settle", 4)]) == []


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


# ------------------------------------------------------------------ F2: GameStateWatcher's guards, enumerated

class GSW:
    """GameStateWatcher's match lifecycle as the source checks above pin it: OnMatchStarted's callers require
    !isTracking; OnGameOver's guard requires isTracking and no report, then calls FtSchedule.GameOver; ResetMatchState
    and OnFfaGameOver write isTracking = false and then call the hook; OnFfaMatchStarted re-arms tracking without
    GameStart. 'started' is the truth the instrument must follow: a match OnMatchStarted started and nothing ended."""

    def __init__(self, s, hook_reset="tip", hook_ffa="tip"):
        self.s, self.hook_reset, self.hook_ffa = s, hook_reset, hook_ffa
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
        self.s.ev("gameover", self.s.Live, self.s.now, self.s.Game)
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

    def check(self, step):
        if self.s.InGame and not (self.tracking and not self.reported):
            self.bad.append("step %d: InGame with no tracked, unreported match" % step)
        if self.s.InGame != self.started:
            self.bad.append("step %d: InGame %s, a started match %s" % (step, self.s.InGame, self.started))


EVENTS = ("oms", "ogo", "ogo_keep", "reset", "ffa_start", "ffa_over", "live", "quiet")


def enumerate_gsw(length=5, **hooks):
    """Every event sequence of the given length; returns (sequences with an invariant violated, with A1/A2/A4 failed)."""
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
        if g.bad:
            inv.append((seq, g.bad[0]))
        if a1_straddles(s.events) or a2_stale_baselines(s.events) or a4_outside_game(s.events):
            acc.append(seq)
    return inv, acc


def test_gsw_sequences_hold():
    inv, acc = enumerate_gsw()
    assert inv == [] and acc == [], (inv[:3], acc[:3])


@pytest.mark.parametrize("hooks", [dict(hook_reset="none"), dict(hook_reset="start"),
                                   dict(hook_ffa="none"), dict(hook_ffa="start")])
def test_gsw_hook_mutant_fails(hooks):
    inv, _ = enumerate_gsw(**hooks)
    assert inv != []
