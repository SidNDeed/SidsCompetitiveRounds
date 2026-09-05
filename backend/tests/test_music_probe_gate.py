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

import pytest


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
    not appear in this file, and must not reach the DLL built from it.

    The second half used to be a promise the body did not keep — it read one
    .cs file and nothing looked at a built artifact, in a project whose rule is
    that a source-level probe is not a binary-level probe (#123, #306; the
    DebugType=none rule exists because a path leaked from a PDB while the
    source was clean). The binary half is now real, and skips rather than
    passes when there is no DLL to read."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert not re.search(r"7656119\d{10}", src)
    assert not re.search(r'"\d{17}"', src)
    # An id could also arrive indirectly, so the file must not reach for the
    # broadcast identity at all — that is the term a future edit crosses first.
    assert "BroadcastMode.SeatSteamId" not in src
    assert not re.search(r"BroadcastMode\.\w*Steam\w*", src)



# Account ids compiled into the mod today, each with the reason it is there. A
# whole-binary scan cannot attribute a hit to one source file, so this is an
# allow-list rather than a prohibition: a FIFTH id appearing means an
# identifier reached the binary that nobody decided to put there. Steam ids are
# public identifiers that every player in a lobby can see; the one hard-coded
# check that uses the maintainer's is a recorded decision to move the check
# server-side in a later batch, and this list is that record.
ACCEPTED_DLL_ACCOUNT_IDS = {
    "76561198040410653",   # maintainer's account — the client-side Regicide check
    "76561198709950406",   # the broadcast seat's account — seat gating
    "76561190000000001",   # synthetic placeholder
    "76561190000000002",   # synthetic placeholder
}


def test_the_dll_carries_only_the_account_ids_this_project_has_accepted():
    """The binary half, as a real check. It used to be a promise in a docstring
    over a body that read one .cs file — and this project's rule is explicit
    that a source-level probe is not a binary-level probe (#123, #306): the
    DebugType=none rule exists because a path leaked from a PDB while the
    source read clean.

    Scanned as BYTES at any offset in both encodings. A text read of a binary
    decodes UTF-16 from byte zero and hides every wide string sitting at an odd
    offset, which is how an ungated build once read clean (#157)."""
    dll = PLUGIN_CS.parent / "bin" / "Release" / "netstandard2.1" / "CompetitiveRounds.dll"
    if not dll.exists():
        pytest.skip("no Release DLL on this seat")
    blob = dll.read_bytes()
    found = set()
    found.update(m.decode("utf-8") for m in re.findall(rb"7656119[0-9]{10}", blob))
    for m in re.findall(rb"(?:7\x006\x005\x006\x001\x001\x009\x00(?:[0-9]\x00){10})", blob):
        found.add(m.decode("utf-16le"))
    unexpected = found - ACCEPTED_DLL_ACCOUNT_IDS
    assert not unexpected, (
        f"account id(s) in the built DLL that nothing accounts for: {sorted(unexpected)}"
    )


def test_the_key_is_off_by_default_and_lives_in_a_section_that_already_exists():
    """BepInEx writes a section on first Bind and discards a value hand-added
    to a section that does not exist yet, so a NEW section would mean "edit,
    launch, edit again". [Music] is already there."""
    src = PLUGIN_CS.read_text(encoding="utf-8")
    assert '"Music", "StreamProbe", false,' in src
    assert '"Music", "StreamProbeRun", "",' in src
    # The load-bearing half is the ORDERING, and it was stated in prose and
    # never asserted: another [Music] key must be bound BEFORE these two, or
    # BepInEx has not written the section yet when a tester hand-adds a value.
    first_music = min(src.index(m) for m in re.findall(r'"Music", "\w+"', src)
                      if "StreamProbe" not in m) if re.findall(
                          r'"Music", "\w+"', src) else None
    assert first_music is not None
    assert first_music < src.index('"Music", "StreamProbe"'), (
        "the probe's keys are the first [Music] binds, so the section does not "
        "exist when a tester edits the file"
    )
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
    assert "!_tap.CallbacksPaused && _src.isPlaying" in play, (
        "wall time must accrue wherever callbacks are owed — which is the whole "
        "of playback except the scripted pause, INCLUDING the post-seek window "
        "whose content is excused but whose cadence is not"
    )


def test_both_new_numbers_reach_the_log():
    """A measurement nobody can read is not a measurement. Both the periodic
    record and the end record carry them."""
    play = _cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)")
    stop = _cs_method_body(PROBE_CS, "private static void Stop(string why)")
    for field in ("audio_gap_max_ms=", "audio_deficit_ms="):
        assert field in play, f"{field} missing from the play record"
        assert field in stop, f"{field} missing from the end record"


def test_the_content_mask_and_the_pause_mask_are_different_masks():
    """r11. One flag meant two things: "the callback will not be called" (the
    scripted pause) and "the callback's buffers may legally be zero" (the 0.5 s
    after a seek). Spelled as one, the second excused cadence and delivery as
    well as content — so a callback that never arrived inside those 0.5 s left
    no gap, no missing frames and no silence, and starvation in the window was
    invisible to a probe built to find starvation."""
    tap = _code(_cs_method_body(PROBE_CS, "private sealed class ProbeTap : MonoBehaviour"))
    assert "public volatile bool CallbacksPaused;" in tap
    # the pause mask returns first and measures nothing
    assert "if (CallbacksPaused) { SilentRun = 0; LastCallbackTicks = 0; return; }" in tap
    # ...and the content mask returns only AFTER cadence and delivery
    assert "if (SilenceExpected) { SilentRun = 0; return; }" in tap
    for measured in ("if (gap > MaxGapTicks) MaxGapTicks = gap;",
                     "FramesDelivered +=", "Buffers++;"):
        assert tap.index(measured) < tap.index("if (SilenceExpected)"), (
            f"{measured} is excused by the content mask"
        )
    # a reused tap must not inherit either mask
    reset = _code(_cs_method_body(PROBE_CS, "public void Reset()"))
    assert "CallbacksPaused = false; SilenceExpected = false;" in reset


def test_the_silence_mask_does_not_cover_the_audible_steps():
    """Steps 4 and 5 are playing — after the resume and toward the end of the
    track — and masking them hid every zero buffer in the two steps the
    measurement most cares about."""
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "_tap.SilenceExpected = _step == 3 || now < _maskUntil;" in play
    assert "_tap.CallbacksPaused =" not in play, (
        "the pause mask is a transition, not a per-frame poll — see the "
        "MaskCallbacks test below"
    )
    assert "_step >= 3 && _step <= 5" not in play, "the whole-step mask is back"
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    assert controls.count("_maskUntil = now + 0.5f;") == 4, (
        "the running seek, the resume, the near-end seek and the restart each "
        "need their own bounded mask, and only that"
    )


def test_the_pause_mask_is_taken_at_the_call_and_not_at_the_next_poll():
    """r12 MEDIUM, two faults with one shape.

    The flag used to be assigned once a frame from `_step`, AFTER PumpControls
    had already called Pause() or UnPause() — so a callback in between was
    attributed to the wrong side of the mask: one after the resume and before
    the clear was dropped although it carried real audio, one after the pause
    and before the set was counted as content.

    And leaving a HEALTHY pause cleared nothing, because the clear lived in the
    callback that a healthy pause never receives — so the first callback after
    a three-second pause differenced against the pre-pause stamp and reported a
    three-second dropout, in the field whose whole job is finding dropouts."""
    mask = _code(_cs_method_body(PROBE_CS, "private static void MaskCallbacks(bool paused)"))
    assert "if (paused) { tap.CallbacksPaused = true; return; }" in mask
    assert "tap.LastCallbackTicks = 0;" in mask
    assert mask.index("tap.LastCallbackTicks = 0;") < mask.index("tap.CallbacksPaused = false;"), (
        "the clock is cleared before the flag, so no callback lands between"
    )
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    # entering: set AFTER the pause call, so a callback still in flight is
    # counted rather than discarded. Both branches of step 2 pause.
    assert controls.count("_src.Pause(); MaskCallbacks(true);") == 2
    assert "MaskCallbacks(true); _src.Pause();" not in controls
    # leaving: cleared BEFORE the resume, which cannot lose one — a paused
    # source produces no callbacks at all.
    assert "MaskCallbacks(false);\n                    _src.UnPause();" in controls
    assert "MaskCallbacks(false);   // the natural end is an intended silence, not a gap" in controls
    # and the audio thread still clears the clock for a callback that DOES
    # arrive while the flag is set
    tap = _code(_cs_method_body(PROBE_CS, "private sealed class ProbeTap : MonoBehaviour"))
    assert "if (CallbacksPaused) { SilentRun = 0; LastCallbackTicks = 0; return; }" in tap


def test_the_resumed_step_is_measured_rather_than_masked():
    """r12 MEDIUM. Step 3 pauses; step 3's handler resumes and enters step 4, so
    step 4 is AUDIBLE — and it is the step whose entire purpose is to verify
    that the resume took. Treating it as part of the pause suppressed a
    resume-only stall and then reset the reference it would have shown up
    against, so the failure the step exists to find produced zeros.

    `resuming` is separate because isPlaying can lag UnPause by a tick, and an
    unexpected-stop verdict there would pre-empt step 4's own judgement."""
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "bool paused = _step == 3;" in play
    assert "bool resuming = _step == 4;" in play
    assert "_step == 3 || _step == 4" not in play, "step 4 is back inside the pause"
    assert "bool ended = !_src.isPlaying && !paused && !resuming && _step != 5;" in play
    # the drift reference is retaken at the resume, because the one from before
    # the pause and the seek is meaningless
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    resume = controls[controls.index("_src.UnPause();"):]
    assert resume.index("ResetDriftRef();") < resume.index("_step = 4;")


def test_the_natural_end_needs_elapsed_time_and_not_one_not_playing_read():
    """The seek is to len-5, so a genuine end arrives about five seconds later.
    An immediate !isPlaying is a source that stopped for some other reason."""
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    assert "bool timed = elapsed >= 4.5f && elapsed <= 6.5f;" in controls
    assert 'Judge("natural_end", timed && played,' in controls
    assert 'Judge("natural_end", true' not in controls, "the unconditional pass is back"


def test_the_natural_end_also_proves_the_playhead_got_there():
    """r11. Elapsed wall time says five seconds passed, which a source stopped
    by anything else also satisfies — and an upper bound alone would not
    separate them either. The tap must have been handed roughly those five
    seconds of audio, which is the only evidence available here that the
    PLAYHEAD reached the end rather than the clock reaching 4.5."""
    controls = _code(_cs_method_body(PROBE_CS, "private static void PumpControls(float now, float t, float len)"))
    assert "_framesAtEndSeek = (object)_tap != null ? _tap.FramesDelivered : -1L;" in controls
    assert controls.index("_framesAtEndSeek =") < controls.index("_step = 5;"), (
        "the baseline must be taken at the seek, not read at the judgement"
    )
    assert "float owed = EndRunSeconds();" in controls
    assert "bool played = owed >= 4f;" in controls, (
        "r12: an UNAVAILABLE delivery figure is not evidence that the playhead "
        "reached the end — it is a broken probe run, and the timing alone is "
        "satisfied by a source that stopped for any other reason"
    )
    assert "owed < 0f || owed >= 4f" not in controls
    assert 'delivered=" + (owed < 0f ? "unavailable"' in controls
    helper = _code(_cs_method_body(PROBE_CS, "private static float EndRunSeconds()"))
    assert "_tap.FramesDelivered - _framesAtEndSeek" in helper
    assert "if (rate <= 0) return -1f;" in helper

    # r13 LOW: and the CONTRACT above the helper has to say what the line below
    # it does. It read "negative means no evidence, which the caller treats as
    # neutral rather than as failure" -- the exact opposite of `owed >= 4f`, so
    # a maintainer reading the contract would have concluded that an
    # unavailable measurement passes the control, and a maintainer restoring
    # the contract would have made it true. The runtime is right; the sentence
    # was two rounds stale.
    src = PROBE_CS.read_text(encoding="utf-8")
    doc = src[:src.index("private static float EndRunSeconds()")]
    doc = doc[doc.rindex("/// <summary>Seconds of audio the tap was handed"):]
    assert "neutral rather than as failure" not in doc, (
        "the contract says an unavailable measurement is neutral; the code fails it"
    )
    assert "NEGATIVE IS A FAILING ANSWER" in doc
    # and it belongs to the run, like every other counter
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert "_framesAtEndSeek = -1L;" in start


def test_the_startup_metric_observes_the_frames_it_claims():
    """The deadline is read as `Time.frameCount >= _openLogFrame`, so +3 keeps
    the peak-frame sampler running over the completion frame and the two whole
    frames after it. The docstring used to say +2 while pinning +3, which left
    the constant unchecked against any stated intent."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "_openLogFrame = Time.frameCount + 3;" in src
    assert "Time.frameCount >= _openLogFrame" in src, (
        "the read site is what gives the constant its meaning"
    )


# ── refusals, all of them, at admission AND on every tick ────────────────────

def test_every_refusal_the_reviews_put_here_survives_the_wider_gate():
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert 'ctx == "online-room" ? "online-room"' in start
    assert '(wanted == Mode.Stress && ctx != "sandbox") ? "stress-needs-offline-sandbox"' in start
    assert 'custom ? "custom-music-playing"' in start
    # r12 MEDIUM: SeatContext returns "?" when the Photon read throws, and "?"
    # is not "online-room" — so a context the probe could not establish used to
    # be admitted, which is the fail-open direction on the one question this
    # guard answers.
    assert 'ctx == "?" ? "seat-context-unreadable"' in start
    refusal = _code(_cs_method_body(PROBE_CS, "private static string RefusalNow()"))
    assert 'if (ctx == "online-room") return "entered online room";' in refusal
    assert 'if (_mode == Mode.Stress && ctx != "sandbox") return "left sandbox";' in refusal
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "string refuseNow = RefusalNow();" in play
    assert "if (refuseNow != null) { Stop(refuseNow); return; }" in play


def test_the_refusal_is_one_question_asked_everywhere():
    """r11. The playback tick asked three questions; the open path asked one of
    them. A run could therefore reach Play() with custom music already sounding,
    or as a stress run outside the Sandbox it is confined to — the open path is
    where the first audible sample is, so it is the path that most needs all
    three."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "private static string RefusalNow()" in src
    for caller in ("private static void PumpPlayback(float now)",
                   "private static void PumpRequest(float now)"):
        body = _code(_cs_method_body(PROBE_CS, caller))
        assert "RefusalNow()" in body, f"{caller} does not ask the question"
    # nobody compares a raw context against one value any more
    for body in (_code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)")),
                 _code(_cs_method_body(PROBE_CS, "private static void PumpRequest(float now)"))):
        assert 'SeatContext() == "online-room"' not in body
        assert 'ctxNow == "online-room"' not in body


def test_a_context_that_cannot_be_read_is_a_refusal():
    """r11. SeatContext returns "?" when the Photon read throws, and "?" is not
    "online-room" — so a context the probe could not establish counted as
    evidence that it was NOT in a match, and the run continued. A context nobody
    can read is not one an online room can be excluded from."""
    refusal = _code(_cs_method_body(PROBE_CS, "private static string RefusalNow()"))
    assert 'if (ctx == "?") return "seat context unreadable";' in refusal
    ctx = _code(_cs_method_body(PROBE_CS, "private static string SeatContext()"))
    assert 'catch { return "?"; }' in ctx, "the sentinel this refuses must still be produced"


def test_exclusive_ownership_is_re_asked_and_not_only_admitted():
    """The normal engine can be paused or mid-load at admission and resume
    after it. Two of this mod's music sources audible at once makes every
    auditory reading in the run ambiguous."""
    refusal = _code(_cs_method_body(PROBE_CS, "private static string RefusalNow()"))
    assert "MusicEngine.IsPlayingNow" in refusal
    assert 'return "custom music started";' in refusal
    play = _code(_cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)"))
    assert "RefusalNow()" in play


def test_the_online_refusal_precedes_the_work_it_refuses():
    """Entering an online room while the request was in flight used to reach
    GetContent() and Play() on that tick, with the playback tick noticing only
    afterwards. GetContent decodes a whole track, so the answer taken at the top
    of the method is milliseconds old by the time anything is audible — it is
    asked again on the line before Play()."""
    pump = _code(_cs_method_body(PROBE_CS, "private static void PumpRequest(float now)"))
    assert pump.index("RefusalNow()") < pump.index("GetContent"), (
        "the refusal must come before the completion block, not after it"
    )
    assert "string refuseAtPlay = RefusalNow();" in pump
    assert pump.index("string refuseAtPlay") < pump.index("_src.Play();"), (
        "the last question must be asked before the first audible sample"
    )
    assert pump.count("RefusalNow()") == 2


def test_the_longest_silent_run_belongs_to_the_run_not_to_the_last_tap():
    """r11, the same shape as the gap and the deficit one round earlier. In
    churn mode the tap is destroyed and rebuilt every cycle, so the number the
    end record printed was the last cycle's, beside a wall time covering ten."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "_runSilentRunMax" in src
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert "_runSilentRunMax = 0;" in start
    close = _code(_cs_method_body(PROBE_CS, "private static void CloseObjects()"))
    assert "if (_tap.SilentRunMax > _runSilentRunMax) _runSilentRunMax = _tap.SilentRunMax;" in close
    assert close.index("_runSilentRunMax") < close.index('Release(_tap, "tap")')
    stop = _code(_cs_method_body(PROBE_CS, "private static void Stop(string why)"))
    assert "Math.Max(_runSilentRunMax, _tap.SilentRunMax)" in stop


def test_an_unknown_mode_suffix_is_refused_rather_than_defaulted():
    """r11. `sku:0:strss` ran a two-minute NORMAL run and said mode=Normal in a
    line nobody re-reads, so the operator's stress measurement silently was not
    one. The refusal happens before the run takes any state — before the
    generation bump and before a pending cleanup is dropped — so a rejected
    lever costs the previous run nothing."""
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert 'LogWarning("[MUSIC-PROBE] unknown mode ' in start
    assert 'LogWarning("[MUSIC-PROBE] too many fields ' in start
    assert "Mode wanted = Mode.Normal;" in start
    assert "_mode = wanted;" in start
    assert start.index("Mode wanted") < start.index("_gen++;"), (
        "a refused lever must not bump the generation or drop a pending cleanup"
    )
    # and there is no path left that reaches a mode without deciding it
    assert start.count("_mode = ") == 1


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
    # r12 MEDIUM: stated as the contexts that are SAFE, not as the one that is
    # not. "?" is an unreadable context, not a proof of anything, and it used
    # to run the collection because it is not equal to "online-room".
    gate = 'if (ctxNow != "menu" && ctxNow != "sandbox" && ctxNow != "offline-idle")'
    assert gate in block
    assert block.index(gate) < block.index("GC.Collect()"), (
        "the context gate must precede the collection, not follow it"
    )
    assert 'ctxNow == "online-room"' not in block, (
        "an unreadable context must defer too"
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


def test_a_refused_command_moves_no_state_at_all():
    """r12 LOW. The mode-suffix refusal was written above the mutations and
    said so; the CONTEXT refusal was written below them. So a command refused
    for being online still bumped the generation — invalidating the outgoing
    tap of a run that was still finishing — and still dropped that run's
    pending cleanup, which is the exact damage the comment above it promised
    could not happen."""
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    refusal = start.index("if (refuse != null)")
    for mutation in ("_gen++;", "_cleanupSampleAt = -1f; _cleanupGcAt = -1f;",
                     "_key = key;", "_audioWallSeconds = 0f;", "_mode = wanted;"):
        assert mutation in start, mutation
        assert start.index(mutation) > refusal, (
            f"{mutation} runs before the command is known to be admitted"
        )
    # ...and the refusal reads the mode this COMMAND asked for, not the one the
    # previous run left in the field
    assert "wanted == Mode.Stress" in start[:refusal]
    assert "_mode == Mode.Stress" not in start[:refusal]


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


def test_a_churn_cycle_does_not_reset_the_counters_without_their_reference():
    """r11 HIGH. In churn mode the tap is destroyed and rebuilt every cycle and
    its Reset zeroes MaxGapTicks and FramesDelivered, while _audioWallSeconds —
    the wall time they are compared against — accrues across the whole run and
    is zeroed only in Start. So the deficit subtracted one cycle's delivered
    audio from the run's expected audio, and the gap reported only the last
    cycle. The counters and their reference must be reset by the same
    statement, so the totals belong to the run and the tap folds into them."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "_runMaxGapTicks" in src and "_runFramesDelivered" in src
    # reset together, in Start, beside the reference they are compared against
    start = _cs_method_body(PROBE_CS, "private static void Start(string raw, float now)")
    for line in ("_audioWallSeconds = 0f;", "_runMaxGapTicks = 0L;", "_runFramesDelivered = 0L;"):
        assert line in start, f"{line} is not reset with the run"
    # and the outgoing tap folds in BEFORE it is released, or a cycle's
    # measurement leaves with the object that recorded it
    close = _cs_method_body(PROBE_CS, "private static void CloseObjects()")
    assert "_runFramesDelivered += _tap.FramesDelivered;" in close
    assert close.index("_runFramesDelivered +=") < close.index('Release(_tap, "tap")')
    # the readers use the run totals, so a churn run reports the whole run
    gap = _cs_method_body(PROBE_CS, "private static float MaxGapMs()")
    deficit = _cs_method_body(PROBE_CS, "private static float DeficitMs()")
    assert "_runMaxGapTicks" in gap
    assert "_runFramesDelivered" in deficit


def test_stop_releases_before_it_reports():
    """The end record builds a string, formats six numbers and calls the
    logger. With every release underneath it, a throw anywhere in that stranded
    the tap, the host object and up to seven spinning background threads."""
    stop = _code(_cs_method_body(PROBE_CS, "private static void Stop(string why)"))
    for release in ("StopBusy();", "CloseObjects();"):
        assert release in stop, release
        assert stop.index(release) < stop.index("[MUSIC-PROBE] end key="), (
            f"{release} runs after the record it can be prevented by"
        )
    # the one value that does not survive the release is read first
    assert stop.index("int silentRunMax") < stop.index("CloseObjects();")


def test_the_starvation_claim_is_scoped_to_the_source_callback():
    """r11. The gap and the deficit are taken at an OnAudioFilterRead tap on the
    probe's own AudioSource, so they answer whether Unity kept pulling audio out
    of that source. A dropout introduced downstream of the tap — mixer, output
    device, driver — leaves both numbers clean, and a reader who takes them as
    "the player heard no gap" has been told something the measurement cannot
    say. Both the file header and the number's own docstring name the
    boundary."""
    src = PROBE_CS.read_text(encoding="utf-8")
    assert "scoped to the SOURCE callback path" in src
    assert "downstream of the tap" in src
    # _cs_method_body returns the brace block, so the doc comment lives just
    # above it — read the 700 characters before the signature instead.
    sig = src.index("private static float DeficitMs()")
    doc = " ".join(src[max(0, sig - 700):sig].replace("///", " ").split())
    assert "Scoped to the source callback" in doc
    assert "mixer or the output device" in doc


def test_the_room_entry_edge_ends_the_run_rather_than_the_next_poll():
    """r12 LOW. The playback tick asks RefusalNow every frame, but Photon can
    join a room AFTER that tick has already read "menu" — so the probe's
    private source stayed audible for the rest of the frame and into the next
    one, and "never runs inside an online room" was true only by the next poll.

    Offline joins raise the same callback and are NOT an end: the Sandbox is
    where this probe is meant to run. A read that throws is treated as online,
    because the run ending early costs a measurement and the other direction
    costs somebody else's match."""
    hook = _code(_cs_method_body(PROBE_CS, "internal static void OnRoomJoined()"))
    assert "online = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode;" in hook
    assert "catch { online = true; }" in hook, "an unreadable room state ends the run"
    assert "if (!online) return;" in hook
    assert 'Stop("entered online room")' in hook
    caller = _code(_cs_method_body(PLUGIN_CS, "public void OnJoinedRoom()"))
    assert "MusicStreamProbe.OnRoomJoined();" in caller


def test_a_tap_that_reported_a_clean_zero_is_not_no_measurement():
    """r12 LOW. `-1` on the end line means no tap ever existed. It was decided
    by whether the run-scoped maximum was greater than zero, so a churn cycle
    whose tap reported a clean zero — the best possible result — came out as
    -1, i.e. as no measurement at all."""
    stop = _code(_cs_method_body(PROBE_CS, "private static void Stop(string why)"))
    assert "(_runHadTap ? _runSilentRunMax : -1)" in stop
    assert "_runSilentRunMax > 0 ? _runSilentRunMax : -1" not in stop
    close = _code(_cs_method_body(PROBE_CS, "private static void CloseObjects()"))
    assert "_runHadTap = true;" in close, "the flag is set where the tap is folded in"
    start = _code(_cs_method_body(PROBE_CS, "private static void Start(string raw, float now)"))
    assert "_runHadTap = false;" in start, "and it belongs to one run"
