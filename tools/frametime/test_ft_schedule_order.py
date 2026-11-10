"""FtSchedule's game-edge order (ruling R6-A3.11.99): the scheduler's order ported to Python, the C# bodies pinned
statement by statement to the port, and the two measured sequences driven through it.

The measured sequences (w9, LogOutput-match.log): combat went live before GameStateWatcher.OnMatchStarted called
FtSchedule.GameStart, in every game; and in game 4 OnGameOver ran FtSchedule.GameOver inside the frame in which combat
ended. At c28259c1 the first opened a point before GameStart, whose resets then ran inside it; the second ran
FtReplay's calls inside a frame that started live.

Assertions, each run on the tip's order (must hold) and on a mutant carrying the c28259c1 order (must fail):
  A1 no point straddles GameStart (its resets and calibration run with no point open; a point's label never changes);
  A2 no baseline is taken before a reset that follows it (a point's end reads the sums of the reset epoch its start
     read, and its delta is what it accrued);
  A3 no FtReplay call runs while FrameLive is true, and every game over gets exactly one replay line;
  A4 a point opens only inside a game GameStart has started and GameOver has not ended;
  A5 the settle flush follows the game's replay;
  A6 the frame in which GameOver ran inside an open point is that point's closing frame.
Run: python -I -B -m pytest tools/frametime/test_ft_schedule_order.py -q"""
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


SIG_CLOSING = "internal static bool ClosingFrame(bool live)"
SIG_BOUNDARY = "internal static void Boundary(bool live)"
SIG_START = "private static void StartPoint()"
SIG_END = "private static void EndPoint()"
SIG_GAMESTART = "internal static void GameStart()"
SIG_GAMEOVER = "internal static void GameOver()"

# ------------------------------------------------------------------ the tip's bodies (the port below mirrors each)

TIP = {
    SIG_CLOSING: [
        'return Live && (!live || _overOwed) && !FtMenu.Active;',
    ],
    SIG_BOUNDARY: [
        'FrameLive = live;',
        'FtArm.Evaluate();',
        "// the settle flush follows the game's owed game-over work (its point end and its replay)",
        'if (_flushAt > 0 && !_overOwed && _replayOwed == NoReplay && System.Diagnostics.Stopwatch.GetTimestamp() >= _flushAt)',
        'FlushGame("settle");',
        'FtRematch.Poll();',
        'FtDrive.JoinTick();',
        'FtDrive.SpawnTick();',
        'if (!FtArm.Armed && FtGate.Off) FtGate.Off = false;   // a disarm opens the gate at this boundary',
        'if (FtMenu.Boundary()) return;   // the menu self-check owns this frame (menu=1, no room)',
        'if (_overOwed)',
        '{',
        '// the first boundary after GameOver: the point open then ends here, before the game boundary',
        '_overOwed = false;',
        'if (Live) { EndPoint(); Live = false; }',
        'FtFrames.GameBoundary();',
        '}',
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
        'if (_replayOwed != NoReplay && !live)',
        '{',
        "// the first boundary after GameOver's point end that reads the frame not live",
        'int g = _replayOwed;',
        '_replayOwed = NoReplay;',
        'FtReplay.Run(g);',
        '}',
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
    SIG_GAMESTART: [
        'if (Live) { FtFrames.EndPoint(); Live = false; }',
        '_overOwed = false;',
        'if (_replayOwed != NoReplay)',
        '{',
        'int g = _replayOwed;',
        '_replayOwed = NoReplay;',
        'if (FrameLive) FtReplay.Skip(g);',
        'else FtReplay.Run(g);',
        '}',
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
    ],
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
}


# ------------------------------------------------------------------ pins

@pytest.mark.parametrize("sig", sorted(TIP))
def test_tip_bodies_are_the_port(sig):
    assert _body(_src("FtSchedule.cs"), sig) == TIP[sig]


def test_old_bodies_are_c28259c1():
    """The mutants' bodies are c28259c1's, read from git where the commit is reachable."""
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "show", OLD_SHA + ":plugin/FtSchedule.cs"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as ex:
        pytest.skip("git not runnable here: %s" % ex)
    if out.returncode != 0:
        pytest.skip("%s not reachable here: %s" % (OLD_SHA, out.stderr.strip()[:200]))
    for sig, want in OLD.items():
        assert _body(out.stdout, sig) == want, sig


def test_the_port_s_neighbours_are_pinned():
    """What the port assumes of the other classes: FtFrames takes its baselines at StartPoint and subtracts them at
    EndPoint; GameBoundary only drops the owed between line; the resets zero the sums; FtClock asks ClosingFrame
    before Boundary; FtReplay.Skip makes no replay call; GameStateWatcher calls GameStart and GameOver once each."""
    fr = _src("FtFrames.cs")
    start = _body(fr, "internal static void StartPoint()")
    for ln in ("_g0 = FtSpan.Sum(FtSpan.Ticks, FtSpan.Live, FtSpan.Gated);",
               "_gn0 = FtSpan.Sum(FtSpan.Calls, FtSpan.Live, FtSpan.Gated);",
               "_on0 = FtCensus.SumOn();",
               "_guard0 = FtCensus.SumGuarded();"):
        assert start.count(ln) == 1, ln
    end = "\n".join(_body(fr, "internal static void EndPoint()"))
    for frag in ("- _g0)", "- _gn0)", "- _on0)", "- _guard0)"):
        assert end.count(frag) == 1, frag
    assert fr.count("internal static void GameBoundary() { _btT0 = -1; }") == 1
    assert _body(_src("FtCensus.cs"), "internal static void Reset()") == [
        "for (int e = 0; e < Count; e++) { OnLive[e] = 0; Guarded[e] = 0; Outside[e] = 0; }"]
    assert _body(_src("FtSpan.cs"), "internal static void Reset()") == [
        "for (int i = 0; i < Ticks.Length; i++) { Ticks[i] = 0; Calls[i] = 0; }"]
    clock = "\n".join(_body(_src("FtClock.cs"), "private static void OnStart()"))
    i = clock.index("FtSchedule.ClosingFrame(live)")
    j = clock.index("FtSchedule.Boundary(live);")
    assert i < j and clock.count("FtSchedule.Boundary(live);") == 1
    assert _body(_src("FtReplay.cs"), "internal static void Skip(int game)") == [
        'if (FtConfig.F18 != "A" || !FtConfig.Present) return;',
        'Plugin.Log.LogInfo("[FRAME-TIME] answer_replay g=" + game + " ticks=0 result=skipped_live");']
    gsw = _src("GameStateWatcher.cs")
    assert gsw.count("FtSchedule.GameStart();") == 1 and gsw.count("FtSchedule.GameOver();") == 1
    sched = _src("FtSchedule.cs")
    assert sched.count("FtReplay.Run(") == 2 and sched.count("FtReplay.Skip(") == 1
    assert sched.count("FtFrames.StartPoint();") == 1 and sched.count("FtFrames.EndPoint();") == 2


# ------------------------------------------------------------------ the port

NO = None


class Sched:
    """FtSchedule's order. Each method mirrors the pinned body named beside it, statement by statement; calls into
    other classes are events; FtSpan's and FtCensus's live sums are one counter (span) with a reset epoch. Each
    method's variant is 'tip' or 'old' (c28259c1); open_ and settle are single-statement mutants of the tip's
    Boundary (open = live, the c28259c1 settle line)."""

    def __init__(self, boundary="tip", gamestart="tip", gameover="tip", closing="tip", open_="tip", settle="tip",
                 last_game=99, settle_frames=3):
        self.v = dict(boundary=boundary, gamestart=gamestart, gameover=gameover, closing=closing, open_=open_,
                      settle=settle)
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
        guard = (not self.over_owed and self.replay_owed is NO) if self.v["settle"] == "tip" else True
        if self.flush_at > 0 and guard and self.now >= self.flush_at:
            self.flush_game("settle")
        if self.over_owed:
            self.over_owed = False
            if self.Live:
                self.end_point()
                self.Live = False
            self.ev("game_boundary")
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
            g = self.replay_owed
            self.replay_owed = NO
            self.replay_run(g)

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

    # FtFrames.EndPoint: the point line, its deltas against the baselines StartPoint took
    def frames_end_point(self):
        p = self.point
        self.ev("end", p["label"], self.label(), self.span - p["base"], p["epoch"], self.epoch, p["acc"])
        self.point = None

    # SIG_GAMESTART
    def game_start(self):
        if self.v["gamestart"] == "old":
            return self._game_start_old()
        if self.Live:
            self.frames_end_point()
            self.Live = False
        self.over_owed = False
        if self.replay_owed is not NO:
            g = self.replay_owed
            self.replay_owed = NO
            if self.FrameLive:
                self.ev("replay_skip", g, self.FrameLive)
            else:
                self.replay_run(g)
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

    # SIG_GAMEOVER
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
        if self.Game >= self.last_game:    # FtDrive.GameOver
            self.complete = True
        if self.complete and self.flush_at == 0:
            self.flush_at = self.now + self.settle_frames

    def replay_run(self, g):
        self.ev("replay", g, self.FrameLive)

    def flush_game(self, why):
        if self.owed < 0:
            return
        g = self.owed
        self.owed = -1
        self.flush_at = 0
        self.ev("flush", g, why)


def drive(s, frames):
    """FtClock.OnStart per frame (the closed frame's ClosingFrame, then Boundary), the frame's live spans (one per
    frame with the moment live), then the frame's mid-frame calls in order (OnMatchStarted, OnGameOver)."""
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
            else:
                s.ev("gameover", s.Live, i, s.Game)
                s.game_over()
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

SEQS = {
    # measured: OnMatchStarted after combat went live
    "start_after_live": opening() + mid() + END_AFTER + opening() + mid() + END_AFTER + opening() + END_AFTER,
    # measured: OnGameOver inside the frame where combat ended (w9 game 4)
    "over_inside": opening() + mid() + END_INSIDE + opening() + END_INSIDE + opening() + END_AFTER,
    "over_inside_live": opening() + END_INSIDE_LIVE + opening() + END_AFTER,
    "abandoned": opening() + [F(False)] * 3 + opening() + END_AFTER,
    "same_frame_live": opening() + [F(True, "GameOver", "GameStart")] + [F(True)] * 3 + END_AFTER,
    "same_frame_quiet": opening() + [F(False), F(False, "GameOver", "GameStart")] + [F(True)] * 3 + END_AFTER,
    "settle": opening() + [F(True, "GameOver")] + [F(True)] * 6 + [F(False)] * 4,
}
LAST = {"settle": 0}


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


def a3_live_replays(ev):
    bad = ["replay g=%d in a frame that started live" % e[1] for e in ev if e[0] == "replay" and e[2]]
    overs = sum(1 for e in ev if e[0] == "gameover")
    lines = sum(1 for e in ev if e[0] in ("replay", "replay_skip"))
    if lines != overs:
        bad.append("%d replay lines for %d game overs" % (lines, overs))
    return bad


def a4_outside_game(ev):
    bad = []
    in_game, games = False, -1
    for e in ev:
        if e[0] == "gamestart":
            in_game, games = True, games + 1
        elif e[0] == "gameover":
            in_game = False
        elif e[0] == "start" and (not in_game or int(e[1].split(".")[0]) != games):
            bad.append("point %s opened outside its game (games started %d, in game %s)" % (e[1], games + 1, in_game))
    return bad


def a5_flush_before_replay(ev):
    bad = []
    replayed = set()
    over = set()
    for e in ev:
        if e[0] in ("replay", "replay_skip"):
            replayed.add(e[1])
        elif e[0] == "gameover":
            over.add(e[3])
        elif e[0] == "flush" and e[1] in over and e[1] not in replayed:
            bad.append("game %d flushed (%s) before its replay" % (e[1], e[2]))
    return bad


def a6_gameover_frame_not_closing(ev):
    bad = []
    owed = None
    for e in ev:
        if e[0] == "gameover" and e[1]:
            owed = e[2] + 1
        elif e[0] == "frame" and owed is not None and e[1] == owed:
            if e[3] and not e[2]:   # closed inside a point (FtFrames.Frame measures it) and not excluded
                bad.append("frame %d (GameOver ran in it, a point open) was measured" % (e[1] - 1))
            owed = None
    return bad


CHECKS = {"A1": a1_straddles, "A2": a2_stale_baselines, "A3": a3_live_replays, "A4": a4_outside_game,
          "A5": a5_flush_before_replay, "A6": a6_gameover_frame_not_closing}

OLD_ALL = dict(boundary="old", gamestart="old", gameover="old", closing="old")
MUTANTS = {
    "c28259c1": OLD_ALL,
    "c28259c1_start": dict(boundary="old", gamestart="old"),   # the game-start pair as at c28259c1
    "c28259c1_over": dict(gameover="old"),                     # GameOver as at c28259c1
    "c28259c1_open": dict(open_="old"),                        # Boundary's open rule as at c28259c1 (open = live)
    "c28259c1_settle": dict(settle="old"),                     # the settle flush line as at c28259c1
    "c28259c1_closing": dict(closing="old"),                   # ClosingFrame as at c28259c1
}

# (assertion, mutant, sequence): each assertion has its c28259c1-order mutant, which must fail it
MUST_FAIL = [
    ("A1", "c28259c1", "start_after_live"), ("A1", "c28259c1_start", "start_after_live"),
    ("A2", "c28259c1", "start_after_live"), ("A2", "c28259c1_start", "start_after_live"),
    ("A3", "c28259c1", "over_inside"), ("A3", "c28259c1_over", "over_inside"),
    ("A4", "c28259c1", "start_after_live"), ("A4", "c28259c1_start", "start_after_live"),
    ("A4", "c28259c1_open", "start_after_live"),
    ("A5", "c28259c1_settle", "settle"),
    ("A6", "c28259c1_closing", "over_inside_live"),
]


@pytest.mark.parametrize("seq", sorted(SEQS))
@pytest.mark.parametrize("name", sorted(CHECKS))
def test_tip_order_holds(name, seq):
    assert CHECKS[name](run(seq)) == []


@pytest.mark.parametrize("name,mutant,seq", MUST_FAIL)
def test_c28259c1_order_fails(name, mutant, seq):
    assert CHECKS[name](run(seq, **MUTANTS[mutant])) != []


def test_every_assertion_has_a_failing_mutant():
    assert sorted(set(m[0] for m in MUST_FAIL)) == sorted(CHECKS)


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


def test_tip_labels_and_replays():
    """At the tip each game's first point is g.1.1 and opens after GameStart; the replay waits for a frame that starts
    not live; GameOver and GameStart in one live frame write the skip line instead of a replay call."""
    ev = run("start_after_live")
    starts = [e[1] for e in ev if e[0] == "start"]
    assert starts[0] == "0.1.1" and "1.1.1" in starts and "2.1.1" in starts
    assert not any(s.endswith(".0.0") for s in starts)
    ev = run("over_inside_live")
    i_over = next(i for i, e in enumerate(ev) if e[0] == "gameover")
    i_rep = next(i for i, e in enumerate(ev) if e[0] == "replay")
    live_frames_between = [e for e in ev[i_over:i_rep] if e[0] == "frame"]
    assert len(live_frames_between) == 3
    assert [e for e in run("same_frame_live") if e[0] == "replay_skip"]
    quiet = run("same_frame_quiet")
    assert not [e for e in quiet if e[0] == "replay_skip"]
    assert [e for e in quiet if e[0] == "replay"][0][2] is False
