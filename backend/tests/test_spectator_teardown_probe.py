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

def test_the_number_is_measured_at_the_writer_not_reconstructed_from_it():
    """The r12 repair. `physDrive` is the position difference across
    `PlayerVelocity.FixedUpdate`, taken by a prefix/postfix pair. Nothing else
    runs between those two halves, so a network lerp, a scripted respawn walk
    and a map rescale — all of which write `transform.position` from elsewhere
    in the frame — contribute nothing, by construction rather than by a rule."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert '[HarmonyPatch(typeof(PlayerVelocity), "FixedUpdate")]' in src, (
        "the bracket must target the one statement that moves a body locally"
    )
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert "__state.pos = __instance.transform.position;" in patch
    assert "Vector3 after = __instance.transform.position;" in patch
    assert "Vector3.Distance(after, __state.pos)" in patch
    assert "NotePhysicsStep(" in patch
    # the sampler moves what the writer banked and computes nothing of its own
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "stepDrive.TryGetValue(velId, out banked)" in tick
    assert "float fresh = banked - st.driveSeen;" in tick
    assert "st.physDrive += fresh;" in tick
    # ...and observed displacement can never reach the attributed number.
    assert not re.search(r"physDrive\s*\+=\s*step", tick)
    assert not re.search(r"maxPhysStep\s*=\s*step", tick)


def test_nothing_reconstructs_the_step_any_more():
    """Two rounds were spent correcting a re-derivation of the writer's work —
    first its predicate, then a term missing from the predicate. The guard
    against a third is that the ingredients are gone: no render delta, no time
    scale, no velocity magnitude anywhere in the sampler."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    for gone in ("Time.deltaTime", "SafeTimeScale", "velocity", "magnitude", "driven"):
        assert gone not in tick, f"{gone} is an ingredient of the refuted reconstruction"
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "private static float SafeTimeScale()" not in src, (
        "the time scale existed only to scale the reconstruction"
    )
    # physDrive has exactly one writer, and it is the drain
    # the log lines print the literal ` physDrive=`, so match the assignment
    writes = re.findall(r"physDrive \+= (\w+)", src)
    assert writes == ["fresh", "totalDrive"], (
        f"expected the drain and the totals fold and nothing else, found {writes}"
    )


def test_observed_displacement_carries_no_attribution():
    """The r10 finding, kept as a standing check: no accumulator may be split
    by the `simulated` flag again. `moved` is context and is reported as such."""
    src = PROBE_CS.read_text(encoding="utf-8")
    for gone in ("movedSim", "movedStop", "maxStepSim", "framesAnySimulated"):
        assert gone not in src, f"{gone} is the measurement r10 refuted"
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "st.moved += step;" in tick


def test_a_control_that_is_revived_stops_being_a_control():
    """A code room is outside CompetitiveRoomDetect, so the vanilla rematch
    popup runs about two seconds into the window and revives the bodies
    (`PopUpHandler.StartPicking`) — on the fighter only, because the spectator
    suppresses that popup. The window ends at the re-enable rather than
    reporting a revived body as one that was never stopped."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "if (!simulatedNow) sawStopped = true;" in tick
    assert "revived = true" in tick
    assert 'CloseWindow("revived")' in tick
    open_body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    for reset in ("sawStopped = false;", "revived = false;"):
        assert reset in open_body, f"{reset} must not leak between windows"


def test_a_window_that_did_not_end_at_the_stop_is_marked_not_comparable():
    """Eight seconds is long enough for the seat to be doing something else.
    The line has to say so, or a horizon window is read beside a stop window
    as though the two measured the same interval. A window with no frame or no
    body carries no measurement either."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    for term in ('!revived', 'why != "horizon"', 'why != "error"',
                 "frames > 0", "bodies.Count > 0"):
        assert term in close, f"comparability is missing {term}"
    assert '" comparable="' in close


def test_only_comparable_windows_feed_the_seat_totals():
    """r11. The totals line is the only place the acceptance criterion in the
    file header is ever read, and that criterion is stated over comparable
    windows — so the totals have to be MADE of them. Banking every window and
    counting the comparable ones separately produced a physDrive nobody could
    evaluate: one eight-second horizon close swamps a dozen real windows."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    decided = close.index("bool comparable =")
    for banked in ("t.physDrive += totalDrive;", "t.moved += totalMoved;",
                   "t.frames += frames;", "t.physFrames += physFrames;",
                   "t.physSteps += physSteps;",
                   "if (maxPhysStep > t.maxPhysStep) t.maxPhysStep = maxPhysStep;"):
        assert banked in close, banked
        assert close.index(banked) > decided, f"{banked} is banked before comparability is known"
    # the window count is the one field that counts everything
    assert "t.windows++;" in close
    # ...and the banking is INSIDE the conditional, not merely after it. A
    # slice from the `if` to the end of the method cannot tell those apart:
    # `if (comparable) t.comparable++;` followed by an unconditional block
    # satisfies it exactly as well as the guarded form does.
    head = close.index("if (comparable)")
    brace = close.index("{", head)
    assert not close[head + len("if (comparable)"):brace].strip(), (
        "the banking must be a braced block attached to the condition"
    )
    depth = 0
    for i in range(brace, len(close)):
        if close[i] == "{":
            depth += 1
        elif close[i] == "}":
            depth -= 1
            if depth == 0:
                guarded = close[brace:i + 1]
                break
    else:
        raise AssertionError("unbalanced braces after if (comparable)")
    assert "t.physDrive += totalDrive;" in guarded
    assert "t.moved += totalMoved;" in guarded
    assert "t.maxPhysStep = maxPhysStep;" in guarded
    assert "t.windows++;" not in guarded


def test_the_line_reports_the_attributed_number_and_the_raw_one():
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    for field in ("physFrames=", "physDrive=", "maxPhysStep=", "moved="):
        assert field in close, field


def test_a_roster_change_is_noted_and_no_longer_costs_the_window():
    """It used to wipe every accumulator, because the accumulators were keyed
    by list position and a changed roster invalidated the baselines. Keyed by
    identity there is nothing to wipe: an arriving body starts its own
    baseline. The note stays on the line: a body APPEARING mid-window is worth
    knowing about when reading the numbers. A body leaving sets nothing — its
    accumulator simply stops growing, which is the right answer."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "rosterChanged = true" in tick
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert 'rosterChanged ? " rosterChanged=1"' in close
    # the wipe is gone, and cannot come back under the old name either
    assert "rebased" not in tick and "rebased" not in close
    for wipe in ("physDrive.Clear()", "moved.Clear()", "lastPos.Clear()"):
        assert wipe not in tick, f"{wipe} discards a window's measurement"


def test_the_revive_latch_cannot_be_tripped_by_a_stun():
    """r11 HIGH. StunHandler sets isKinematic true on StartStun and false on
    StopStun (V/StunHandler.cs:57,65) and never touches simulated, and stuns
    reach every seat. Latching the control's validity on the composite
    predicate therefore discarded a window every time a stun expired inside it
    — losing precisely the windows whose bodies were live enough to collide,
    and leaving the acceptance number computed over what survived."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    latch = [ln for ln in tick.splitlines()
             if "sawStopped" in ln or "revived = true" in ln or "wasSimulated =" in ln]
    assert latch, "no latch found"
    joined = "\n".join(latch)
    assert "isKinematic" not in joined, (
        "the latch reads a term a stun flips; it must read simulated alone"
    )
    assert "driven" not in joined, "the latch must not read the composite predicate"
    assert "simulatedNow" in joined


def test_a_body_local_physics_is_not_touching_contributes_nothing():
    """r11 HIGH, closed differently in r12. HealthHandler.RPCA_Die deactivates
    the body (V/HealthHandler.cs:374) and leaves isPlaying, simulated and
    isKinematic untouched with its death velocity still on it — so a restated
    predicate has to carry the writer's REACHABILITY as well as its guards, and
    the restatement was short that term for a round. Bracketing FixedUpdate
    needs no term: Unity does not call it on a deactivated component, so the
    prefix never runs and nothing is banked. The guard is that the sampler
    contains no such restatement to go stale."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    for term in ("isActiveAndEnabled", "isPlaying", "isKinematic"):
        assert term not in tick, (
            f"{term} is vanilla's guard restated; the bracket is what decides now"
        )


def test_an_unarmed_bracket_cannot_report_a_body_at_the_origin():
    """The prefix skips the transform read while the window is shut. If the
    skipped state were a zero Vector3 the postfix would read the distance from
    the origin as travel — which is exactly what a body sitting at the origin
    is. The state carries its own flag, and the postfix requires it."""
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert "internal bool armed;" in patch
    assert "__state.armed = true;" in patch
    assert "if (dead || !__state.armed) return;" in patch
    # and the prefix does not touch the transform while the window is shut
    prefix = _code(_cs_block(PROBE_CS, "private static void Prefix(PlayerVelocity __instance, out DriveState __state)"))
    assert prefix.index("WindowOpen()") < prefix.index("transform.position")


def test_the_bracket_fails_dead_rather_than_breaking_movement():
    """It runs inside vanilla's own FixedUpdate on every body. A throw that
    escapes would stop bodies moving, which is a far worse outcome than a probe
    that reports nothing (#376)."""
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert patch.count("catch { dead = true; }") == 2, "both halves must swallow"
    assert patch.count("if (dead") == 2, "and both must honour the latch"


def test_a_replaced_velocity_component_starts_a_fresh_baseline():
    """The accumulator is keyed by PlayerVelocity instance and the body holds a
    baseline into it. A body whose component is replaced would otherwise compare
    the new instance's running total against the old one's — reading zero
    forever if the new total is lower, and a jump if it is higher."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "if (velId != st.velId) { st.velId = velId; st.driveSeen = 0f; }" in tick
    assert tick.index("st.driveSeen = 0f;") < tick.index("float fresh = banked - st.driveSeen;")


def test_the_step_accumulator_is_bounded_and_window_scoped():
    """It is written from the physics step for the life of the session, so it
    must not grow without limit, and it must not carry one window's travel into
    the next."""
    note = _code(_cs_block(PROBE_CS, "internal static void NotePhysicsStep(int velId, float distance)"))
    assert "stepDrive.Count >= MAX_BODIES_TRACKED" in note
    assert "if (!(distance > 0f)) return;" in note, (
        "NaN fails every comparison, so the accepted range is what must be tested"
    )
    open_body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    assert "stepDrive.Clear();" in open_body
    assert "physSteps = 0;" in open_body


def test_accumulators_are_keyed_by_the_games_player_identity():
    """A list index is not an identity. A slot whose occupant changes without
    changing the roster count carries the previous body's position baseline
    forward and banks the gap between two different bodies as one frame of
    movement."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "Dictionary<int, BodyState>" in src
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "id = p.PlayerID;" in tick
    assert "bodies.TryGetValue(id, out st)" in tick
    # nothing may address a per-body accumulator by position any more
    assert not re.search(r"(lastPos|physDrive|moved|wasSimulated)\s*\[", tick)
    # and the map is bounded, because a probe must not grow without limit
    assert "bodies.Count >= MAX_BODIES_TRACKED" in tick


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
