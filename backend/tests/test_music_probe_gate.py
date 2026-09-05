"""The streamed-music probe has to be runnable on the hardware in question, and
its result has to be able to come out bad.

The probe exists to settle one disagreement: learning #460 records streamed
playback skipping audibly on a CPU-contended seat, while the v2 spike measured
4.3 ms GetContent and no underrun at 50-140 fps on the broadcast machine. Two
review rounds have now refused it, both times for the same shape of reason — a
measurement that cannot reach its subject, and a measurement that cannot fail.

  * The gate was `BroadcastMode.IsBroadcastIdentity`, so the only seat that
    could run it was the one seat whose numbers nobody disputes. Design review
    dV2 refused a compiled account allowlist for the other seat, and was right
    to: a personal identifier must not ship in source or in the DLL. The gate
    is `[Music] StreamProbe`, default false.
  * With that key in place, r9 found the probe still could not start on a
    player seat. `Config.Bind` reads the file once at launch, the only reload
    in the mod belongs to the broadcast levers, and a run required the value to
    CHANGE after launch — so the launch value was adopted as an inert baseline
    and nothing ever ran. The probe now reloads its own config while enabled,
    and the launch command is EXECUTED.
  * r9 also found the silence measurement blind to the failure it was for:
    `silent_run` counts zero-filled buffers that arrive, and a callback the
    audio thread never reaches supplies no buffer at all. A starved run read
    clean. The tap now records inter-callback gaps and delivered audio.

Everything the earlier rounds put on the probe survives, and is checked here,
because widening the seat is exactly when those refusals start to matter.
"""

import re
from pathlib import Path


PLUGIN = Path(__file__).resolve().parents[2] / "plugin"
PROBE_CS = PLUGIN / "MusicStreamProbe.cs"
PLUGIN_CS = PLUGIN / "Plugin.cs"


def _cs_method_body(path, signature):
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
    out = []
    for line in block.splitlines():
        s = line.strip()
        if s.startswith("//") or s.startswith("///"):
            continue
        out.append(line)
    return "\n".join(out)


# ── the gate ─────────────────────────────────────────────────────────────────

def test_the_gate_is_a_config_key_and_not_a_seat_identity():
    gate = _cs_method_body(PROBE_CS, "private static bool SeatAllowed()")
    assert "Plugin.MusicProbeEnabled" in gate
    assert "IsBroadcastIdentity" not in PROBE_CS.read_text(encoding="utf-8"), (
        "the identity gate is what stopped this measurement reaching player hardware"
    )


def test_nothing_that_could_identify_a_person_is_compiled_in():
    """The dV2 objection, kept as a standing check: a 17-digit account id must
    not appear in source or in the DLL built from it."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert not re.search(r"7656119\d{10}", src)
    assert not re.search(r'"\d{17}"', src)


def test_the_key_is_off_by_default_and_lives_in_a_section_that_already_exists():
    """BepInEx writes a section on first Bind and discards a value hand-added
    to a section that does not exist yet, so a NEW section would mean "edit,
    launch, edit again". [Music] is already there."""
    src = PLUGIN_CS.read_text(encoding="utf-8")
    assert '"Music", "StreamProbe", false,' in src
    assert '"Music", "StreamProbeRun", "",' in src
    assert "internal static ConfigEntry<bool> MusicProbeEnabled;" in src
    assert "internal static ConfigEntry<string> MusicProbeRun;" in src


def test_the_probe_is_actually_ticked():
    src = PLUGIN_CS.read_text(encoding="utf-8")
    assert src.count("try { MusicStreamProbe.Tick(); } catch { }") == 1


# ── r9 HIGH 1: a player seat can actually start it ───────────────────────────

def test_the_launch_command_runs_instead_of_becoming_an_inert_baseline():
    """The r9 HIGH. Setting both keys and restarting is the documented path,
    and it did nothing at all: the first tick adopted the launch value as the
    thing a later value would have to differ from."""
    tick = _code(_cs_method_body(PROBE_CS, "internal static void Tick()"))
    assert "_last = raw; return;" not in tick, "the launch value is being adopted as a baseline again"
    assert "if (raw.Length == 0 || raw == _lastRun) return;" in tick
    assert tick.index("_lastRun = raw;") < tick.index("Start(raw, now);")
    # the memo names what RAN, so nothing else in the file may write it
    src = _code(PROBE_CS.read_text(encoding="utf-8"))
    assert src.count("_lastRun") == 4, "one declaration, one clear, one compare, one write"


def test_the_probe_reloads_its_own_config_and_does_not_borrow_another_seats_tick():
    """The other half of the same HIGH. The only ConfigFile.Reload() in the mod
    before this belonged to the broadcast levers, so on a player seat the keys
    were frozen from launch however many times they were edited."""
    reload_fn = _code(_cs_method_body(PROBE_CS, "private static void ReloadIfDue(float now)"))
    assert "Plugin.ConfigFileForLevers?.Reload();" in reload_fn
    assert "_nextReloadAt = now + CONFIG_RELOAD_SECONDS;" in reload_fn
    assert "IsBroadcastIdentity" not in reload_fn and "Broadcast" not in reload_fn, (
        "a seat condition here is the defect this method exists to remove"
    )
    tick = _code(_cs_method_body(PROBE_CS, "internal static void Tick()"))
    assert "if (SeatAllowed()) ReloadIfDue(now);" in tick, (
        "reloading only while enabled keeps a seat that never uses the probe off the disk"
    )
    probe = PROBE_CS.read_text(encoding="utf-8")
    assert "TickTestOpenTab" not in probe, "the probe still claims another tick reloads for it"


def test_turning_the_key_off_ends_a_live_run_instead_of_stranding_it():
    """The tick is the sole releaser of the request, clip, source and host
    object, so an early return there strands all four."""
    tick = _code(_cs_method_body(PROBE_CS, "internal static void Tick()"))
    assert 'if (!SeatAllowed()) { Stop("probe key turned off"); return; }' in tick
    # ...and it is reached only after the maintenance work, which must keep
    # running so a stop in progress can finish releasing.
    assert tick.index("RetryReleases") < tick.index('Stop("probe key turned off")')
    assert tick.index("_cleanupSampleAt") < tick.index('Stop("probe key turned off")')
    # a START, by contrast, simply requires the key, and forgetting the last
    # run is what lets the key itself re-trigger the current command
    assert "if (!SeatAllowed()) { _lastRun = null; return; }" in tick
    assert tick.index("_lastRun = null") < tick.index("Start(raw, now)")


# ── r9 HIGH 2: the result can come out bad ───────────────────────────────────

def test_the_tap_measures_callbacks_that_never_arrived():
    """`silent_run` inspects buffers it was handed. Starvation is the absence
    of a buffer, so the counter it was supposed to move stays at zero — the
    measurement was blind to its own subject."""
    tap = _code(_cs_method_body(PROBE_CS, "private sealed class ProbeTap : MonoBehaviour"))
    assert "public long LastCallbackTicks, MaxGapTicks, FramesDelivered;" in tap
    assert "long stamp = Stopwatch.GetTimestamp();" in tap
    assert "if (gap > MaxGapTicks) MaxGapTicks = gap;" in tap
    assert "FramesDelivered += channels > 0 ? data.Length / channels : data.Length;" in tap


def test_the_delivered_audio_is_compared_with_the_time_it_was_expected_in():
    deficit = _code(_cs_method_body(PROBE_CS, "private static float DeficitMs()"))
    assert "AudioSettings.outputSampleRate" in deficit
    assert "_audioWallSeconds - delivered" in deficit
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "_audioWallSeconds += Time.unscaledDeltaTime;" in play
    assert "!_tap.SilenceExpected && _src.isPlaying" in play, (
        "wall time must only accrue where output was actually expected"
    )


def test_both_new_numbers_reach_the_log():
    """A measurement nobody can read is not a measurement. Both the periodic
    record and the end record carry them."""
    play = _cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)")
    stop = _cs_method_body(PROBE_CS, "private static void Stop(string why)")
    for field in ("audio_gap_max_ms=", "audio_deficit_ms="):
        assert field in play, f"{field} missing from the play record"
        assert field in stop, f"{field} missing from the end record"


def test_the_silence_mask_does_not_cover_the_audible_steps():
    """Steps 4 and 5 are playing — after the resume and toward the end of the
    track — and masking them hid every zero buffer in the two steps the
    measurement most cares about."""
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "_tap.SilenceExpected = _step == 3 || now < _maskUntil;" in play
    assert "_step >= 3 && _step <= 5" not in play, "the whole-step mask is back"
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    assert controls.count("_maskUntil = now + 0.5f;") == 4, (
        "the running seek, the resume, the near-end seek and the restart each "
        "need their own bounded mask, and only that"
    )


def test_the_natural_end_needs_elapsed_time_and_not_one_not_playing_read():
    """The seek is to len-5, so a genuine end arrives about five seconds later.
    An immediate !isPlaying is a source that stopped for some other reason."""
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    assert 'Judge("natural_end", elapsed >= 4.5f,' in controls
    assert 'Judge("natural_end", true' not in controls, "the unconditional pass is back"


def test_the_startup_metric_observes_the_frames_it_claims():
    """+2 observes the completion frame and one complete frame after it."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "_openLogFrame = Time.frameCount + 3;" in src


# ── refusals, all of them, at admission AND on every tick ────────────────────

def test_every_refusal_the_reviews_put_here_survives_the_wider_gate():
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert 'ctx == "online-room" ? "online-room"' in start
    assert '(_mode == Mode.Stress && ctx != "sandbox") ? "stress-needs-offline-sandbox"' in start
    assert 'custom ? "custom-music-playing"' in start
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert 'if (ctxNow == "online-room") { Stop("entered online room"); return; }' in play
    assert 'if (_mode == Mode.Stress && ctxNow != "sandbox") { Stop("left sandbox"); return; }' in play


def test_exclusive_ownership_is_re_asked_and_not_only_admitted():
    """The normal engine can be paused or mid-load at admission and resume
    after it. Two of this mod's music sources audible at once makes every
    auditory reading in the run ambiguous."""
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "customNow = MusicEngine.IsPlayingNow;" in play
    assert 'if (customNow) { Stop("custom music started"); return; }' in play


def test_the_online_refusal_precedes_the_work_it_refuses():
    """Entering an online room while the request was in flight used to reach
    GetContent() and Play() on that tick, with the playback tick noticing only
    afterwards."""
    pump = _code(_cs_method_body(PROBE_CS, "private static void PumpRequest(float now)"))
    assert 'if (SeatContext() == "online-room") { Stop("entered online room"); return; }' in pump
    assert pump.index("SeatContext()") < pump.index("GetContent"), (
        "the refusal must come before the completion block, not after it"
    )


def test_sandbox_means_a_live_sandbox_round_and_not_two_photon_flags():
    """`InRoom && OfflineMode` stays true at the post-Sandbox menu, where
    ':stress' would launch busy workers with a queue poll a keystroke away."""
    ctx = _code(_cs_method_body(PROBE_CS, "private static string SeatContext()"))
    assert "SandboxLive() ? \"sandbox\" : \"offline-idle\"" in ctx
    live = _code(_cs_method_body(PROBE_CS, "private static bool SandboxLive()"))
    assert "GM_Test.instance" in live and "isActiveAndEnabled" in live
    assert "GameManager.instance" in live and "isPlaying" in live
    assert "MainMenuHandler.instance" in live and "isOpen" in live


def test_no_blocking_collection_runs_while_a_room_is_live():
    """Entering an online room ends the run and schedules the cleanup; a full
    blocking collection five seconds later is a hitch inside somebody's game."""
    tick = _code(_cs_method_body(PROBE_CS, "internal static void Tick()"))
    gc_at = tick.index("_cleanupGcAt > 0f && now >= _cleanupGcAt")
    block = tick[gc_at:]
    assert block.index('SeatContext() == "online-room"') < block.index("GC.Collect()"), (
        "the context gate must precede the collection, not follow it"
    )
    assert "_cleanupGcDeadline" in block, "a deferral with no bound never ends"
    stop = _code(_cs_method_body(PROBE_CS, "private static void Stop(string why)"))
    assert "_cleanupGcDeadline = Time.realtimeSinceStartup + 120f;" in stop


def test_a_pending_cleanup_belongs_to_the_run_that_scheduled_it():
    """Starting run B inside run A's cleanup window overwrote A's memory
    baselines, so A's cleanup compared against B's and forced a collection
    inside B."""
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert "_cleanupSampleAt = -1f; _cleanupGcAt = -1f;" in start
    assert "_gen++;" in start


def test_a_late_tap_destruction_cannot_stop_a_later_run():
    """A tap whose destruction threw is kept for a bounded retry. Its eventual
    OnDestroy sets a static flag that the owner reads as "release everything"."""
    tap = _code(_cs_method_body(PROBE_CS, "private sealed class ProbeTap : MonoBehaviour"))
    assert "private void OnDestroy() { if (Gen == _gen) HostDestroyed = true; }" in tap
    open_block = _code(_cs_method_body(PROBE_CS, "private static void PumpRequest(float now)"))
    assert "_tap.Gen = _gen;" in open_block


def test_the_probe_keeps_its_own_audio_source_and_never_drives_the_engine():
    """It measures playback; it must not become a second music owner."""
    src = PROBE_CS.read_text(encoding="utf-8")
    for forbidden in ("MusicEngine.Play", "MusicEngine.Stop", "MusicEngine.Prepare"):
        assert forbidden not in src, f"the probe reaches into the engine: {forbidden}"


def test_the_operator_text_matches_what_the_code_does():
    """r9 LOW: the descriptions still promised broadcast identity, N-1 workers
    and a two-second player reload the implementation did not provide. A key's
    description is the only instruction anyone gets."""
    src = PLUGIN_CS.read_text(encoding="utf-8")
    enabled = src[src.index('"Music", "StreamProbe", false,'):]
    enabled = enabled[: enabled.index(");")]
    assert "RESTART" in enabled, "the restart the enable path needs is not stated"
    assert "re-read from disk every 2 seconds" in enabled
    run = src[src.index('"Music", "StreamProbeRun", "",'):]
    run = run[: run.index(");")]
    assert "runs once when the probe turns on, including at startup" in run
    assert "live offline Sandbox round" in run
    header = PROBE_CS.read_text(encoding="utf-8")[:6000]
    assert "Gate: the broadcast identity" not in header
    assert "N-1 busy threads" not in header
