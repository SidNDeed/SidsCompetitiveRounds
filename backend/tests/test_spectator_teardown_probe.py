"""The round-teardown probe measures; it does not yet fix anything.

Recourse item 1 says the spectator seat keeps simulating player bodies through
the round teardown, because vanilla stops them from INSIDE
`GM_ArmsRace.RPCA_NextRound` (V/GM_ArmsRace.cs:531) and our observer prefix
skips the whole method. That is an argument from the call graph. The item was
written with "PROVE FIRST" against it, so this ships the measurement and no fix.

Three review rounds have now corrected this probe, each time because it was
measuring something other than what it claimed. Five properties are
load-bearing and this file exists to stop any of them drifting back:

  * **The closing edge is `MOVE PLAYERS START`, not END** (r9). Vanilla logs
    START at the top of `PlayerManager.Move` (V/PlayerManager.cs:384)
    immediately before setting `simulated = false` for that player, then drives
    `transform.position` frame by frame to the spawn point, and logs END at :409
    AFTER the traversal. Closing on END put the whole scripted traversal inside
    the window on BOTH seat kinds, so the reading could never reach the noise
    floor.
  * **The number is not observed displacement** (r10). Splitting displacement
    by `playerVel.simulated` measured the network lerp:
    `Photon.Pun.SyncPlayerMovement.Update` writes `transform.position` on every
    REMOTE body every frame it has a package, without consulting the flag. A
    spectator, for whom every body is remote, banked the whole lerp as movement
    "while simulated"; the fighter banked vanilla's scripted respawn walk as
    movement "while stopped". That manufactures the acceptance differential
    with zero contribution from local physics.
  * **...and it is not a distance at all** (r12). The repair for the above
    bracketed `PlayerVelocity.FixedUpdate` with a prefix/postfix pair and took
    the position difference. A bracket measures the whole METHOD: vanilla's own
    z-flattening (V/PlayerVelocity.cs:50) reports a metre for a body at z=1 that
    travelled nowhere, a co-patch's movement is attributed to vanilla, and
    `PlayerCollision.FixedUpdate` writes player transforms under physics too
    (V/PlayerCollision.cs:67 and :100), so the bracket was never all of local
    physics anyway. What is counted now is vanilla's own branch DECISION,
    read from the three fields it is about to read: `driveSteps` out of
    `steps`. A count of branches taken cannot be moved by another writer.
  * **A probe that is not measuring must not report a zero** (r12). A Harmony
    patch can silently fail to attach (#83) and one exception latches the hook
    dead; either way the acceptance counter reads zero, which is also what a
    correctly stopped body reads. The patch latches its own liveness during
    ordinary play and a window without it is `bracket=absent` and not
    comparable.
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

def test_the_number_is_vanillas_own_branch_decision_not_a_distance():
    """The r13 repair, and the third method for this item.

    r12 refuted measuring the position difference across the patched method:
    the difference is the NET EFFECT OF THE WHOLE METHOD, so vanilla's own
    z-flattening on V/PlayerVelocity.cs:50 reports a metre of travel for a body
    that started at z=1 and went nowhere, and any co-patch is attributed to
    vanilla. `PlayerCollision.FixedUpdate` also writes player transforms under
    physics, so the bracket was never the whole of local physics either.

    Counting the branch instead has none of those failure modes: it is read
    from the three fields vanilla is about to read, in the same invocation,
    before it acts on them, so nothing else that writes a transform can
    contribute to it."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert '[HarmonyPatch(typeof(PlayerVelocity), "FixedUpdate")]' in src
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert "bool integrating = data != null && data.isPlaying" in patch
    assert "&& __instance.simulated && !__instance.isKinematic;" in patch
    assert "NotePhysicsStep(__instance.GetInstanceID(), integrating);" in patch
    # no distance is taken anywhere in the patch any more
    assert "Vector3" not in patch, "the patch must not read a position at all"
    assert "Distance" not in patch
    # the sampler folds what the step counted and computes nothing of its own
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "if (DrainSteps(st)) anyDriven = true;" in tick
    drain = _code(_cs_block(PROBE_CS, "private static bool DrainSteps(BodyState st)"))
    assert "int freshSteps = c.steps - st.stepsSeen;" in drain
    assert "int freshDrive = c.driveSteps - st.driveStepsSeen;" in drain
    # ...and observed displacement can never reach the acceptance counter
    assert not re.search(r"driveSteps\s*\+=\s*step\b", tick)


def test_the_restated_guard_still_matches_vanilla():
    """Method 3 copies three of vanilla's fields, which is the class of thing
    r11 caught going stale. Both sides of the contract are read here, so the
    copy cannot drift silently: if ROUNDS changes the guard, this fails.

    Reachability is deliberately NOT in the copy — Unity does not call
    FixedUpdate on a component that fails it, so the prefix does not run."""
    vanilla = (Path(__file__).resolve().parents[2] / "logs-snapshot" / "decompiled"
               / "full" / "PlayerVelocity.cs")
    if not vanilla.exists():
        return  # decompile not present on this seat; the patch test still runs
    text = vanilla.read_text(encoding="utf-8")
    body = text[text.index("private void FixedUpdate()"):]
    body = body[:body.index("internal void AddForce")]
    assert "if (data.isPlaying)" in body
    assert "if (simulated && !isKinematic)" in body
    assert "base.transform.position +=" in body
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    for term in ("data.isPlaying", "__instance.simulated", "!__instance.isKinematic"):
        assert term in patch, term
    assert "isActiveAndEnabled" not in patch, (
        "reachability is structural here; copying it is what went stale before"
    )


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
    assert "physDrive" not in src, "the refuted distance measure is gone entirely"
    assert "maxPhysStep" not in src, "a per-step maximum of a distance went with it"
    # the acceptance counter has exactly two writers: the drain into a body, and
    # the fold of the bodies into the seat
    writes = re.findall(r"driveSteps \+= (\w+)", src)
    assert writes == ["freshDrive", "totalDrive"], (
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
    for term in ("why == COMPARABLE_CLOSE", "!revived", "frames > 0",
                 "bodies.Count > 0", "bracketLive"):
        assert term in close, f"comparability is missing {term}"
    assert '" comparable="' in close
    src = PROBE_CS.read_text(encoding="utf-8")
    assert 'COMPARABLE_CLOSE = "move-start"' in src
    # an ALLOWLIST, not a list of exclusions: r12 found that a room-left, a
    # disconnect and the late move-end backstop all satisfied the old
    # exclusions while covering a differently shaped interval, and an edge
    # added later would have joined them silently.
    for excluded in ('why != "horizon"', 'why != "error"',
                     'why != "room-left"', 'why != "disconnected"'):
        assert excluded not in close, (
            "comparability must be stated as the one edge it accepts"
        )


def test_a_window_the_patch_did_not_measure_is_not_reported_as_a_zero():
    """r12 HIGH. Zero integrating steps from a patch that never attached reads
    exactly like zero from a body that is not being integrated — and the second
    is the finding this probe exists to produce. A Harmony patch CAN silently
    fail to attach (#83), and a single exception in the prefix latches the
    channel dead for the session.

    So the instrument reports its own liveness. `Alive` is latched by the
    prefix running at all, before the window check, so ordinary play sets it;
    a window closed without it is banked nowhere and says `bracket=absent`."""
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert "internal static bool Alive { get { return ran && !dead; } }" in patch
    prefix = _code(_cs_block(PROBE_CS, "private static void Prefix(PlayerVelocity __instance)"))
    assert prefix.index("ran = true;") < prefix.index("WindowOpen()"), (
        "liveness must be established by ordinary play, not by an open window"
    )
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert "bool bracketLive = PlayerVelocity_TeardownDrive_Patch.Alive;" in close
    assert '.Append(bracketLive ? "live" : "absent")' in close
    assert "else if (!bracketLive) t.notMeasured++;" in close
    heartbeat = _code(_cs_block(PROBE_CS, "private static void LogTotals()"))
    assert "notMeasured=" in heartbeat, (
        "the heartbeat has to say how many windows the instrument missed"
    )


def test_the_last_step_before_the_close_is_not_dropped():
    """r12. The physics step banks into a per-instance map and the render tick
    drains it. A fixed step taken after the last tick but before the close was
    left in the map and never reached the line, so the window under-reported
    exactly the steps closest to the stop — the ones the question is about."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert "DrainSteps(st);" in close
    assert close.index("DrainSteps(st);") < close.index("totalSteps += st.steps;")
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "DrainSteps(st)" in tick, "and the tick still drains as it goes"


def test_only_comparable_windows_feed_the_seat_totals():
    """r11. The totals line is the only place the acceptance criterion in the
    file header is ever read, and that criterion is stated over comparable
    windows — so the totals have to be MADE of them. Banking every window and
    counting the comparable ones separately produced a physDrive nobody could
    evaluate: one eight-second horizon close swamps a dozen real windows."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    decided = close.index("bool comparable =")
    for banked in ("t.driveSteps += totalDrive;", "t.moved += totalMoved;",
                   "t.frames += frames;", "t.physFrames += physFrames;",
                   "t.steps += totalSteps;"):
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
    assert "t.driveSteps += totalDrive;" in guarded
    assert "t.steps += totalSteps;" in guarded
    assert "t.moved += totalMoved;" in guarded
    assert "t.windows++;" not in guarded


def test_the_line_reports_the_acceptance_counter_its_sample_size_and_the_raw_one():
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    for field in ("physFrames=", "driveSteps=", "bracket=", "moved="):
        assert field in close, field
    # driveSteps is printed over its own sample size, so a small count and a
    # small window cannot be confused
    assert '.Append(" driveSteps=").Append(totalDrive).Append("/")' in close
    assert '.Append(totalSteps)' in close


def test_the_per_body_figures_are_labelled_with_the_games_player_id():
    """r12. The line claimed PlayerID attribution and printed `p0`/`p1`, which
    are positions in a sorted list. Two bodies with ids 7 and 2 could not be
    matched to either figure."""
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert '.Append(" p").Append(ordered[i].playerId)' in close
    assert '.Append(" p").Append(i)' not in close, "that is a list position"
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "playerId = id," in tick, "the id has to be stored to be printed"


def test_a_roster_change_is_noted_and_no_longer_costs_the_window():
    """It used to wipe every accumulator, because the accumulators were keyed
    by list position and a changed roster invalidated the baselines. Keyed by
    identity there is nothing to wipe: an arriving body starts its own
    baseline. The note stays on the line: a body APPEARING mid-window is worth
    knowing about when reading the numbers. A body leaving sets nothing — its
    accumulator simply stops growing, which is the right answer."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "rosterChanged = true" in tick
    # r12 LOW: the flag used to be set whenever the map was already non-empty,
    # so the SECOND body of an ordinary 1v1 set it on the very first sampled
    # frame and every baseline window printed rosterChanged=1. Only an arrival
    # on a LATER frame is a change, and `frames` is incremented at the end of
    # the tick, so it is zero throughout the first one.
    assert "if (frames > 0) rosterChanged = true;" in tick
    assert "if (bodies.Count != 0) rosterChanged = true;" not in tick
    close = _code(_cs_block(PROBE_CS, "internal static void CloseWindow(string why)"))
    assert 'rosterChanged ? " rosterChanged=1"' in close
    # the wipe is gone, and cannot come back under the old name either
    assert "rebased" not in tick and "rebased" not in close
    for wipe in ("driveSteps.Clear()", "moved.Clear()", "lastPos.Clear()"):
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


def test_there_is_no_bracket_left_to_straddle_a_window_edge():
    """r12 LOW, retired by construction rather than repaired. A prefix/postfix
    pair carries state across the middle of the patched method, and a log line
    reached from inside it runs `OnUnityLog` on this thread — so a window could
    close, or close and reopen, between the two halves and the second half
    would report into the wrong window. There is no second half now: the
    decision is complete in the prefix."""
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert "Postfix" not in patch
    assert "__state" not in patch
    assert "DriveState" not in patch
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "Window state cannot change between the two halves" not in src, (
        "that claim was false and is now unnecessary"
    )


def test_the_bracket_fails_dead_rather_than_breaking_movement():
    """It runs inside vanilla's own FixedUpdate on every body. A throw that
    escapes would stop bodies moving, which is a far worse outcome than a probe
    that reports nothing (#376)."""
    patch = _code(_cs_block(PROBE_CS, "internal static class PlayerVelocity_TeardownDrive_Patch"))
    assert patch.count("catch { dead = true; }") == 1, "the hook must swallow"
    assert patch.count("if (dead) return;") == 1, "and honour the latch"
    # and a dead channel is visible rather than silent: Alive goes false, which
    # is what makes the window non-comparable instead of a zero
    assert "return ran && !dead;" in patch


def test_a_replaced_velocity_component_starts_a_fresh_baseline():
    """The accumulator is keyed by PlayerVelocity instance and the body holds a
    baseline into it. A body whose component is replaced would otherwise compare
    the new instance's running total against the old one's — reading zero
    forever if the new total is lower, and a jump if it is higher."""
    tick = _code(_cs_block(PROBE_CS, "internal static void Tick()"))
    assert "st.stepsSeen = 0;" in tick and "st.driveStepsSeen = 0;" in tick
    assert tick.index("if (velId != 0 && velId != st.velId)") < tick.index("DrainSteps(st)")
    drain = _code(_cs_block(PROBE_CS, "private static bool DrainSteps(BodyState st)"))
    assert "int freshDrive = c.driveSteps - st.driveStepsSeen;" in drain


def test_the_step_accumulator_is_bounded_and_window_scoped():
    """It is written from the physics step for the life of the session, so it
    must not grow without limit, and it must not carry one window's travel into
    the next."""
    note = _code(_cs_block(PROBE_CS, "internal static void NotePhysicsStep(int velId, bool willIntegrate)"))
    assert "stepCounts.Count >= MAX_BODIES_TRACKED" in note
    assert "if (!open) return;" in note
    # counts, not floats: there is no NaN and no noise floor to get wrong, and
    # a step that did NOT integrate is still counted, because the sample size
    # is what tells a stopped body from an absent instrument
    assert "c.steps++;" in note
    assert "if (willIntegrate) c.driveSteps++;" in note
    open_body = _code(_cs_block(PROBE_CS, "internal static void OpenWindow(string seat)"))
    assert "stepCounts.Clear();" in open_body
    assert "physSteps = 0;" in open_body
    assert "driveSteps = 0;" in open_body


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
    heartbeat = _code(_cs_block(PROBE_CS, "private static void LogTotals()"))
    assert "foreach (var kv in totals)" in heartbeat
    for field in ("windows=", "comparable=", "notMeasured=", "physFrames=",
                  "driveSteps=", "moved="):
        assert field in heartbeat, field
