"""The round-teardown probe measures; it does not yet fix anything.

Recourse item 1 says the spectator seat keeps simulating player bodies through
the ~2.5-3.5 s round teardown, because vanilla stops them from INSIDE
`GM_ArmsRace.RPCA_NextRound` (V/GM_ArmsRace.cs:531) and our observer prefix
skips the whole method. That is an argument from the call graph. The item was
written with "PROVE FIRST" against it, so this commit adds the measurement and
no fix.

What is easy to get wrong here is not the arithmetic, it is the PLACEMENT. Two
of the three call sites sit deliberately above a gate:

  * the window opens above `SpectatorPatchSupport.Suppress`, so a fighter seat
    -- where vanilla's own stop runs microseconds later -- emits the same line
    as a positive control, and so a suppression that fails to engage still
    produces a reading rather than silence;
  * the close runs above `OnUnityLog`'s spectator quiesce, which returns at its
    fourth line on exactly the seat under investigation. Below it, every
    spectator window would time out on the cap with the next round's combat
    folded into the number.

Both are the #376 class: a diagnostic placed inside the behaviour it is meant
to judge is dead where it is needed. These tests are what stops either from
drifting back down.
"""

import re
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
PROBE_CS = PLUGIN / "SpectatorTeardownProbe.cs"
SPEC_CS = PLUGIN / "SpectatorPatches.cs"
GSW_CS = PLUGIN / "GameStateWatcher.cs"
PLUGIN_CS = PLUGIN / "Plugin.cs"


def _cs_block(path, signature):
    """The brace-balanced block that follows `signature`."""
    src = path.read_text(encoding="utf-8")
    start = src.index(signature)
    open_brace = src.index("{", start)
    depth = 0
    for i in range(open_brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace : i + 1]
    raise AssertionError(f"unbalanced braces after {signature}")


def _code(block):
    """Strip comments so a phrase in prose cannot satisfy a code assertion."""
    out = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("///"):
            continue
        out.append(line)
    return "\n".join(out)


# ── placement: the two sites that must sit above a gate ──────────────────────

def test_the_window_opens_above_the_suppression_gate():
    body = _code(_cs_block(SPEC_CS, "internal static class Spectator_ObserveNextRound_Patch"))
    assert "SpectatorTeardownProbe.OpenWindow" in body
    assert body.index("SpectatorTeardownProbe.OpenWindow") < body.index(
        "if (!SpectatorPatchSupport.Suppress) return true;"
    ), "below the gate the probe never runs on the seat it is measuring (#376)"


def test_both_seat_kinds_emit_a_line_so_the_fighter_is_a_control():
    body = _code(_cs_block(SPEC_CS, "internal static class Spectator_ObserveNextRound_Patch"))
    assert '"spectator"' in body and '"fighter"' in body, (
        "without the fighter control a non-zero reading cannot be attributed "
        "to the suppression rather than to teardown motion generally"
    )


def test_the_close_runs_above_the_spectator_quiesce():
    body = _code(_cs_block(GSW_CS, "private static void OnUnityLog("))
    assert "SpectatorTeardownProbe.CloseWindow" in body
    assert body.index("SpectatorTeardownProbe.CloseWindow") < body.index(
        "if (SpectatorSession.IsLocalSpectator) return;"
    ), "OnUnityLog returns early for a spectator, which is the seat under test"


def test_the_probe_is_ticked_every_frame():
    src = PLUGIN_CS.read_text(encoding="utf-8")
    assert src.count("try { SpectatorTeardownProbe.Tick(); } catch { }") == 1


# ── it measures, it does not fix ─────────────────────────────────────────────

def test_the_probe_writes_nothing_to_the_game():
    """The fix is deliberately not in this commit. A probe that also stopped
    the bodies would make its own reading meaningless."""
    src = PROBE_CS.read_text(encoding="utf-8")
    code = _code(src)
    assert "SetPlayersSimulated" not in code
    assert not re.search(r"\.simulated\s*=", code), "the probe assigns the flag it measures"
    assert not re.search(r"\.velocity\s*=", code)
    assert not re.search(r"\.position\s*=", code)


# ── the reading has to be trustworthy ────────────────────────────────────────

def test_a_duplicate_call_in_does_not_restart_the_clock():
    """Vanilla dedupes bunched round broadcasts with `isTransitioning`, which
    lives in the suppressed machine; the observer sees them all. Teardown
    began at the first one."""
    body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    assert "if (open) return;" in body


def test_the_window_cannot_outlive_the_teardown():
    """Without a cap, a window whose closing marker never arrives keeps
    sampling into the next round's combat and reports that as teardown
    movement."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert re.search(r"WINDOW_CAP_SECONDS\s*=\s*8f", src)
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "Time.time - openedAt > WINDOW_CAP_SECONDS" in tick
    assert 'CloseWindow("cap")' in tick


def test_a_roster_change_rebases_instead_of_counting_as_movement():
    """Positions are held by list index. A player leaving mid-teardown shifts
    every index below them, which would read as a large simultaneous jump."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "players.Count != lastPos.Count" in tick
    rebase = tick.index("players.Count != lastPos.Count")
    assert "lastPos.Clear();" in tick[rebase:]


def test_the_log_volume_is_bounded():
    """A broadcast seat sits in matches all day; this runs on it."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert re.search(r"MAX_REPORTS\s*=\s*20", src)
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert "if (reports >= MAX_REPORTS)" in close
    assert "windowsTotal % MAX_REPORTS == 0" in close, (
        "after the budget the totals must still surface, or a log opened late "
        "in a sitting carries no answer at all"
    )


def test_one_line_per_round_not_one_per_frame():
    """~60 fps over a 3 s teardown is ~180 lines a round. The per-frame
    maximum is carried as a field instead."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "Plugin.Log" not in tick
    assert "maxStep" in tick


def test_the_line_carries_the_flag_the_argument_is_about():
    """`moved` alone cannot distinguish "bodies are simulating" from "bodies
    are being moved by something else"; simFrames reads the flag directly."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert "simFrames=" in close
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "p.data.playerVel.simulated" in tick
