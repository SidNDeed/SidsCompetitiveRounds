"""The round-teardown probe measures; it does not yet fix anything.

Recourse item 1 says the spectator seat keeps simulating player bodies through
the round teardown, because vanilla stops them from INSIDE
`GM_ArmsRace.RPCA_NextRound` (V/GM_ArmsRace.cs:531) and our observer prefix
skips the whole method. That is an argument from the call graph. The item was
written with "PROVE FIRST" against it, so this ships the measurement and no fix.

Two review rounds have now corrected this probe, each time because it was
measuring something other than what it claimed. Four properties are
load-bearing and this file exists to stop any of them drifting back:

  * **The closing edge is `MOVE PLAYERS START`, not END** (r9). Vanilla logs
    START at the top of `PlayerManager.Move` (V/PlayerManager.cs:384)
    immediately before setting `simulated = false` for that player, then drives
    `transform.position` frame by frame to the spawn point, and logs END at :409
    AFTER the traversal. Closing on END put the whole scripted traversal inside
    the window on BOTH seat kinds, so the reading could never reach the noise
    floor.
  * **The number comes from the writer, not from the result** (r10). Splitting
    observed displacement by `playerVel.simulated` measured the network lerp:
    `Photon.Pun.SyncPlayerMovement.Update` writes `transform.position` on every
    REMOTE body every frame it has a package, without consulting the flag. A
    spectator, for whom every body is remote, banked the whole lerp as movement
    "while simulated"; the fighter banked vanilla's scripted respawn walk as
    movement "while stopped". That manufactures the acceptance differential
    with zero contribution from local physics. `physDrive` instead integrates
    the expression in `PlayerVelocity.FixedUpdate` (V/PlayerVelocity.cs:38-51),
    which is the only thing that moves a body by simulating it.
  * **A control has to stay stopped to be a control** (r10). In a code room the
    vanilla rematch popup runs about two seconds in and revives the bodies,
    and the spectator suppresses that popup — so a fighter window left open to
    the horizon reports revived bodies as if they had never stopped. The window
    ends at the re-enable, and windows that end at the horizon are marked not
    comparable.
  * **Placement above two gates.** The window opens above
    `SpectatorPatchSupport.Suppress` so a fighter seat is a control in the same
    format, and the close runs above `OnUnityLog`'s spectator quiesce, which
    returns at its fourth line on exactly the seat under test. Both are the #376
    class: a diagnostic inside the behaviour it judges is dead where it is
    needed.
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


# ── the window edges ─────────────────────────────────────────────────────────

def test_the_window_closes_on_move_players_start_not_end():
    """The r9 repair. END is emitted after vanilla has already walked every
    body to its spawn point, so a window closing there can never read at the
    noise floor no matter what the seat did."""
    body = _code(_cs_block(GSW_CS, "private static void OnUnityLog("))
    assert 'message.StartsWith("MOVE PLAYERS START")' in body
    assert 'SpectatorTeardownProbe.CloseWindow("move-start")' in body
    # END survives only as a backstop, and must be tested AFTER START —
    # "MOVE PLAYERS END" and "MOVE PLAYERS START" share a prefix.
    assert body.index('"MOVE PLAYERS START"') < body.index('"MOVE PLAYERS END"')
    assert 'CloseWindow("move-end-backstop")' in body


def test_the_close_runs_above_the_spectator_quiesce():
    body = _code(_cs_block(GSW_CS, "private static void OnUnityLog("))
    assert body.index("SpectatorTeardownProbe.CloseWindow") < body.index(
        "if (SpectatorSession.IsLocalSpectator) return;"
    ), "OnUnityLog returns early for a spectator, which is the seat under test"


def test_the_window_is_bound_to_its_room():
    """A seat that leaves mid-teardown must not carry the window into the next
    room. The reliable leave edge is the Photon callback, not an InRoom poll."""
    body = _code(_cs_block(PLUGIN_CS, "public void OnLeftRoom()"))
    assert 'SpectatorTeardownProbe.CloseWindow("room-left")' in body


def test_the_window_closes_on_a_full_disconnect_too():
    """Socket loss reaches OnDisconnected WITHOUT an OnLeftRoom — the same
    asymmetry the telemetry close beside it exists for. Without this the
    window survives to its horizon and samples menu teardown, or the next
    room, under the seat it opened with."""
    body = _code(_cs_block(
        PLUGIN_CS, "public void OnDisconnected(Photon.Realtime.DisconnectCause cause)"))
    assert 'SpectatorTeardownProbe.CloseWindow("disconnected")' in body
    assert body.index("SpectatorTeardownProbe.CloseWindow") < body.index(
        "if (Diag2v2.PendingSlot() < 0) return;"
    ), "the close must run before the diagnostic early return"


def test_the_horizon_is_a_horizon_and_not_a_missing_marker_claim():
    src = PROBE_CS.read_text(encoding="utf-8")
    assert re.search(r"WINDOW_HORIZON_SECONDS\s*=\s*8f", src)
    assert "WINDOW_CAP_SECONDS" not in src
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "Time.time - openedAt > WINDOW_HORIZON_SECONDS" in tick
    assert 'CloseWindow("horizon")' in tick


# ── the reading itself ───────────────────────────────────────────────────────

def test_the_number_is_taken_from_the_writer_not_from_the_result():
    """The r10 repair, and the whole of it. `physDrive` integrates exactly the
    expression `PlayerVelocity.FixedUpdate` uses to move a body — the same
    predicate and the same quantity — so a position written by anything else
    contributes nothing to it. A network lerp, a scripted respawn walk and a
    map rescale all write `transform.position` directly."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "driven = data.isPlaying && vel.simulated && !vel.isKinematic;" in tick, (
        "the predicate must be vanilla's, all three terms of it"
    )
    assert "float travel = speed * dt * scale;" in tick
    assert "physDrive[i] = physDrive[i] + travel;" in tick
    assert "if (travel > maxPhysStep) maxPhysStep = travel;" in tick
    # ...and observed displacement can never reach the attributed number.
    assert not re.search(r"travel\s*=\s*[^;\n]*step", tick)
    assert not re.search(r"physDrive\[i\][^;\n]*step", tick)
    assert not re.search(r"maxPhysStep\s*=\s*step", tick)


def test_the_integral_uses_the_same_time_scale_vanilla_does():
    """`fixedDeltaTime * timeScale * velocity` summed over a frame's fixed
    steps is `deltaTime * timeScale * velocity`. Dropping the scale would read
    a slow-motion teardown as more travel than it was."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "float scale = SafeTimeScale();" in tick
    scale_fn = _code(_cs_block(PROBE_CS, "private static float SafeTimeScale()"))
    assert "TimeHandler.timeScale" in scale_fn
    assert "return 1f;" in scale_fn, "an unavailable time scale must not zero the reading"


def test_observed_displacement_carries_no_attribution():
    """The r10 finding, kept as a standing check: no accumulator may be split
    by the `simulated` flag again. `moved` is context and is reported as such."""
    src = PROBE_CS.read_text(encoding="utf-8")
    for gone in ("movedSim", "movedStop", "maxStepSim", "framesAnySimulated"):
        assert gone not in src, f"{gone} is the measurement r10 refuted"
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "moved[i] = moved[i] + step;" in tick


def test_a_control_that_is_revived_stops_being_a_control():
    """A code room is outside CompetitiveRoomDetect, so the vanilla rematch
    popup runs about two seconds into the window and revives the bodies
    (`PopUpHandler.StartPicking`) — on the fighter only, because the spectator
    suppresses that popup. The window ends at the re-enable rather than
    reporting a revived body as one that was never stopped."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "if (!driven) sawStopped = true;" in tick
    assert "revived = true" in tick
    assert 'CloseWindow("revived")' in tick
    open_body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    for reset in ("sawStopped = false;", "revived = false;"):
        assert reset in open_body, f"{reset} must not leak between windows"


def test_a_window_that_did_not_end_at_the_stop_is_marked_not_comparable():
    """Eight seconds is long enough for the seat to be doing something else.
    The line has to say so, or a horizon window is read beside a stop window
    as though the two measured the same interval."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert 'bool comparable = !revived && why != "horizon" && why != "error";' in close
    assert '" comparable="' in close


def test_the_line_reports_the_attributed_number_and_the_raw_one():
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    for field in ("physFrames=", "physDrive=", "maxPhysStep=", "moved="):
        assert field in close, field


def test_a_truncated_window_says_so():
    """A roster change clears the accumulators. Without a marker in the line a
    truncated window is indistinguishable from a window with no movement."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "players.Count != lastPos.Count" in tick
    rebase = tick.index("players.Count != lastPos.Count")
    assert "rebased = true" in tick[rebase:]
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert 'rebased ? " rebased=1"' in close


def test_a_duplicate_call_in_does_not_restart_the_clock():
    """Vanilla dedupes bunched round broadcasts with `isTransitioning`, which
    lives in the suppressed machine; the observer sees them all. The teardown
    began at the first one."""
    body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    assert "if (open) return;" in body


# ── placement and control ────────────────────────────────────────────────────

def test_the_window_opens_above_the_suppression_gate():
    body = _code(_cs_block(SPEC_CS, "internal static class Spectator_ObserveNextRound_Patch"))
    assert "SpectatorTeardownProbe.OpenWindow" in body
    assert body.index("SpectatorTeardownProbe.OpenWindow") < body.index(
        "if (!SpectatorPatchSupport.Suppress) return true;"
    ), "below the gate the probe never runs on the seat it is measuring (#376)"


def test_both_seat_kinds_emit_a_line_so_the_fighter_is_a_control():
    body = _code(_cs_block(SPEC_CS, "internal static class Spectator_ObserveNextRound_Patch"))
    assert 'SpectatorPatchSupport.Suppress ? "spectator" : "fighter"' in body, (
        "without the fighter control a non-zero reading cannot be attributed "
        "to the suppression rather than to teardown motion generally"
    )


def test_the_probe_is_ticked_from_the_per_frame_update():
    """Asserting the string occurs somewhere in Plugin.cs would pass with the
    call sitting in an unreachable method. Require it in the SAME block as the
    per-frame work it runs beside."""
    update = None
    src = PLUGIN_CS.read_text(encoding="utf-8")
    # Plugin.cs has several Update() hosts. Brace-match forward from each and
    # keep the one that also ticks the overlay idle close — the established
    # per-frame host this call was placed beside.
    for m in re.finditer(r"private void Update\(\)", src):
        open_brace = src.index("{", m.end())
        depth = 0
        for i in range(open_brace, len(src)):
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
                if depth == 0:
                    body = src[open_brace : i + 1]
                    break
        if "OverlayIdleClose.Tick()" in body:
            update = body
            break
    assert update is not None, "could not find the per-frame Update host"
    assert _code(update).count("SpectatorTeardownProbe.Tick()") == 1


# ── it measures, it does not fix ─────────────────────────────────────────────

def test_the_probe_writes_nothing_to_the_game():
    """The fix is deliberately not in this commit. A probe that also stopped
    the bodies would make its own reading meaningless."""
    code = _code(PROBE_CS.read_text(encoding="utf-8"))
    assert "SetPlayersSimulated" not in code
    assert not re.search(r"\.simulated\s*=", code), "the probe assigns the flag it measures"
    assert not re.search(r"\.velocity\s*=", code)
    assert not re.search(r"\.isKinematic\s*=", code)
    assert not re.search(r"\.position\s*=", code)


def test_one_line_per_round_not_one_per_frame():
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "Plugin.Log" not in tick


def test_the_heartbeat_keeps_each_seats_numbers_apart():
    """One process can play a round and then watch one. A single set of
    counters reports the LAST window's seat beside both seats' totals, and a
    maximum that resets every window — a heartbeat that cannot be read. The
    comparison between seats IS the reading, so it goes on one line."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert "totals.TryGetValue(seat, out t)" in close
    assert "if (maxPhysStep > t.maxPhysStep) t.maxPhysStep = maxPhysStep;" in close, (
        "the per-seat maximum must survive the per-window reset"
    )
    heartbeat = _code(_cs_block(PROBE_CS, "private static void LogTotals()"))
    assert "foreach (var kv in totals)" in heartbeat
    for field in ("windows=", "comparable=", "physFrames=", "physDrive=", "maxPhysStep=", "moved="):
        assert field in heartbeat, field
