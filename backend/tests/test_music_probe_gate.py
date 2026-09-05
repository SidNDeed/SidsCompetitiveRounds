"""The streamed-music probe is gated by a config key, not by an identity.

The probe exists to settle one disagreement: learning #460 records streamed
playback skipping audibly on a CPU-contended seat, while the v2 spike measured
4.3 ms GetContent and no underrun at 50-140 fps on the broadcast machine. The
gate was `BroadcastMode.IsBroadcastIdentity`, so the only seat that could run it
was the one seat whose numbers nobody disputes — the measurement could never
reach the hardware the question is about.

Design review dV2 refused a compiled account allowlist for the other seat, and
was right to: a personal identifier must not ship in source or in the DLL. A
config key is not one. So the gate is `[Music] StreamProbe`, default false.

Two things this file guards that are easy to lose:

  * the key can go FALSE while a run is live — an identity could not — and this
    probe's tick is the only thing that releases its request, clip, audio source
    and host object. An early return there strands all four;
  * every refusal the earlier reviews put on the probe (no online room, stress
    only in an offline Sandbox, not while custom music is already playing) must
    survive the re-gating, because widening the seat is exactly when they start
    to matter.
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


def test_turning_the_key_off_ends_a_live_run_instead_of_stranding_it():
    """The difference between a config key and the identity it replaces. The
    tick is the sole releaser of the request, clip, source and host object."""
    tick = _cs_method_body(PROBE_CS, "internal static void Tick()")
    assert 'if (!SeatAllowed()) { Stop("probe key turned off"); return; }' in tick
    # ...and it is reached only after the maintenance work, which must keep
    # running so a stop in progress can finish releasing.
    assert tick.index("RetryReleases") < tick.index('Stop("probe key turned off")')
    assert tick.index("_cleanupSampleAt") < tick.index('Stop("probe key turned off")')
    # a START, by contrast, simply requires the key
    assert "if (!SeatAllowed()) { _last = null; return; }" in tick
    assert tick.index("_last = null") < tick.index("Start(raw, now)")


def test_every_refusal_the_reviews_put_here_survives_the_wider_gate():
    start = _cs_method_body(PROBE_CS, "private static void Start(string raw, float now)")
    assert 'ctx == "online-room" ? "online-room"' in start
    assert '(_mode == Mode.Stress && ctx != "sandbox") ? "stress-needs-offline-sandbox"' in start
    assert 'custom ? "custom-music-playing"' in start
    # and re-checked every tick while playing, not only at the start
    play = _cs_method_body(PROBE_CS, "private static void PumpPlayback(float now)")
    assert 'if (ctxNow == "online-room") { Stop("entered online room"); return; }' in play
    assert 'if (_mode == Mode.Stress && ctxNow != "sandbox") { Stop("left sandbox"); return; }' in play


def test_the_probe_keeps_its_own_audio_source_and_never_drives_the_engine():
    """It measures playback; it must not become a second music owner."""
    src = PROBE_CS.read_text(encoding="utf-8")
    for forbidden in ("MusicEngine.Play", "MusicEngine.Stop", "MusicEngine.Prepare"):
        assert forbidden not in src, f"the probe reaches into the engine: {forbidden}"
