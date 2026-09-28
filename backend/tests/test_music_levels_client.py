"""v1.41.0 item 23 (custom music): the volume ceiling, the long first-track
fade-in and the album note, pinned where the harness cannot reach.

The level math itself -- the ceiling and both fade envelopes -- is EXECUTED by
the client-rules harness (MusicLevels.SelfTest, the "musiclevels" suite in
test_client_rules_harness.py). What a source test decides is that the engine
feeds that math and nothing else: both sources take the slider through the
ceiling, no third path writes a gain, a fresh install takes the measured
default and a stored 100 moves to it once behind its own flag, the menu exit
is what arms the long fade, every armed fade starts from a silent source, and
the album note is authored text rendered at exactly the two places it was
asked for.
"""
import io
import os
import re

from _cs_structure import code_of

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLUGIN = os.path.join(REPO, "plugin")
ENGINE = "MusicEngine.cs"
NOTE = "machine-generated"
FLAGGED_ALBUMS = {"music_album_another_round", "music_album_clavar_la_bala"}


def _read(rel):
    with io.open(os.path.join(REPO, rel), encoding="utf-8") as fh:
        return fh.read()


def _plugin(name):
    return _read(os.path.join("plugin", name))


def _tick():
    return code_of(_plugin(ENGINE), "private static void TickDuckAndVolume(float rt)")


# -- (a) the ceiling ----------------------------------------------------------

def test_the_ceiling_is_at_most_half():
    code = code_of(_plugin("MusicLevels.cs"))
    m = re.search(r"internal const float VOLUME_CEILING\s*=\s*([0-9.]+)f\s*;", code)
    assert m, "no VOLUME_CEILING constant"
    assert 0.0 < float(m.group(1)) <= 0.5, "the slider's 100 must map to at most half: " + m.group(1)


def test_both_sources_take_the_slider_through_the_ceiling():
    body = _tick()
    assert body.count("MusicLevels.SliderGain(VolumeStepPercent)") == 1
    assert re.search(r"float mult = MusicLevels\.SliderGain\(VolumeStepPercent\);", body)
    assert len(re.findall(r"\bmult\s*=", body)) == 1, "mult has a second writer"
    assert re.search(r"float mainVolume = mult \* baseGain \*", body)
    assert "m.volume = mainVolume;" in body
    assert "p.volume = mult * baseGain;" in body, "the preview source bypasses the ceiling"
    assert "pctFrac" not in body, "the uncapped pre-1.41 law is still in the tick"


def test_nothing_else_sets_a_music_source_gain():
    """Every other write to a source's volume in the engine is the silent zero
    before a Play or UnPause; a third path writing a gain would bypass the
    ceiling."""
    writes = [w.strip() for w in re.findall(r"\.volume\s*=\s*([^;]+);", code_of(_plugin(ENGINE)))]
    others = [w for w in writes if w not in ("0f", "mainVolume", "mult * baseGain")]
    assert not others, others
    assert writes.count("mainVolume") == 1 and writes.count("mult * baseGain") == 1, writes


def test_the_slider_doc_no_longer_claims_vanilla_parity():
    assert "vanilla-equivalent loudness ceiling" not in _plugin(ENGINE)


def test_a_fresh_install_takes_the_measured_default():
    levels = code_of(_plugin("MusicLevels.cs"))
    m = re.search(r"internal const int DEFAULT_PERCENT\s*=\s*(\d+)\s*;", levels)
    assert m, "no DEFAULT_PERCENT constant"
    assert 0 < int(m.group(1)) < 100, "the default must sit below the slider's top: " + m.group(1)
    assert re.search(r"internal const int LEGACY_DEFAULT_PERCENT\s*=\s*100\s*;", levels)
    plugin = code_of(_plugin("Plugin.cs"))
    assert re.search(r'"Music",\s*"MusicVolume",\s*MusicLevels\.DEFAULT_PERCENT,', plugin), (
        "MusicVolume must bind MusicLevels.DEFAULT_PERCENT as its default")
    getter = code_of(_plugin(ENGINE), "internal static int VolumeStepPercent")
    assert getter.count("MusicLevels.DEFAULT_PERCENT") == 2, getter
    assert ": 100," not in getter and "return 100;" not in getter, getter
    ui = code_of(_plugin("NativeUI.cs"))
    assert ui.count("int vol = MusicLevels.DEFAULT_PERCENT;") == 1
    assert ": MusicLevels.DEFAULT_PERCENT; } catch { }" in ui
    assert "int vol = 100;" not in ui


def test_the_volume_migration_runs_once_behind_its_own_flag():
    plugin = code_of(_plugin("Plugin.cs"))
    assert re.search(r'MusicVolumeMigrated = Config\.Bind\(\s*"Music",\s*"MusicVolumeMigrated",\s*false,',
                     plugin), "the migration flag must bind false"
    gate = "if (!MusicVolumeMigrated.Value)"
    assert plugin.count(gate) == 1
    block = plugin.split(gate, 1)[1]
    block = block[:block.index("catch (Exception")]
    assert "int migratedVolume = MusicLevels.MigratedPercent(storedVolume, false);" in block
    assert "if (migratedVolume != storedVolume) MusicVolume.Value = migratedVolume;" in block
    assert "MusicVolumeMigrated.Value = true;" in block
    # Both keys are bound before the migration reads them.
    assert plugin.index('"MusicVolume", MusicLevels.DEFAULT_PERCENT') < plugin.index(gate)
    assert plugin.index('"MusicVolumeMigrated", false') < plugin.index(gate)
    # Nothing else sets the flag, and nothing outside Plugin and MusicLevels
    # runs the migration.
    for name in sorted(os.listdir(PLUGIN)):
        if not name.endswith(".cs"):
            continue
        code = code_of(_plugin(name))
        flag_writes = len(re.findall(r"MusicVolumeMigrated\.Value\s*=[^=]", code))
        assert flag_writes == (1 if name == "Plugin.cs" else 0), (name, flag_writes)
        if name not in ("Plugin.cs", "MusicLevels.cs"):
            assert "MigratedPercent(" not in code, name
    assert plugin.count("MusicLevels.MigratedPercent(") == 1


# -- (b) the long first-track fade -------------------------------------------

def test_the_menu_exit_decides_the_long_fade():
    body = code_of(_plugin(ENGINE), "internal static void NotePrefixContext(bool menuCall, bool isCard)")
    assert body.count("s.longFadePending = !s.menuAudible;") == 1
    assert body.count("if (leavingMenu)") == 1 and body.count("else if (c == Ctx.Menu)") == 1
    exit_at = body.index("if (leavingMenu)")
    enter_at = body.index("else if (c == Ctx.Menu)")
    assert exit_at < body.index("s.longFadePending = !s.menuAudible;") < enter_at, \
        "the long fade is not decided on the menu-to-game edge"
    assert "s.longFadePending = false;" in body[enter_at:], "entering the menu keeps a stale decision"
    # The engine has no other writer of the decision besides ArmFade's consume.
    code = code_of(_plugin(ENGINE))
    assert len(re.findall(r"\blongFadePending\s*=", code)) == 3, \
        re.findall(r".*\blongFadePending\s*=.*", code)


def test_menu_audibility_is_sampled_only_in_the_menu():
    body = _tick()
    assert re.search(r"bool mainAudible = m != null && m\.isPlaying && !s\.mainPausedByUs && !s\.paused;", body)
    assert re.search(r"if \(s\.ctx == Ctx\.Menu\) s\.menuAudible = mainAudible;", body)
    assert len(re.findall(r"\bmenuAudible\s*=", code_of(_plugin(ENGINE)))) == 1, "menuAudible has a second writer"


def test_arm_fade_consumes_the_pending_long_fade_once():
    body = code_of(_plugin(ENGINE), "private static void ArmFade()")
    decide = "s.fadeLong = s.longFadePending && s.ctx != Ctx.Menu;"
    consume = "if (s.fadeLong) s.longFadePending = false;"
    assert body.count(decide) == 1 and body.count(consume) == 1
    assert body.index(decide) < body.index(consume)
    assert "[MUSIC-FADE] armed long" in body and "[MUSIC-FADE] armed short" in body


def test_the_envelope_is_the_harnessed_math():
    body = _tick()
    assert "MusicLevels.AdvanceFade(s.fadeProgress, dt, s.fadeLong)" in body
    assert "fade = MusicLevels.FadeGain(s.fadeProgress, s.fadeLong);" in body
    assert "/ 0.6f" not in body, "an inline envelope survives beside MusicLevels"
    levels = code_of(_plugin("MusicLevels.cs"))
    assert re.search(r"LONG_FADE_SECONDS\s*=\s*2\.5f\s*;", levels)
    assert re.search(r"SHORT_FADE_SECONDS\s*=\s*0\.6f\s*;", levels)


def test_every_armed_fade_starts_from_a_silent_source():
    """The first in-game track starts at zero gain on the seat, not only in the
    harness: every ArmFade call follows a volume = 0f written before the
    source's Play or UnPause."""
    code = code_of(_plugin(ENGINE))
    sites = [m.start() for m in re.finditer(r"\bArmFade\(\);", code)]
    assert len(sites) == 3, "ArmFade call sites changed: %d" % len(sites)
    for pos in sites:
        before = code[max(0, pos - 900):pos]
        assert "volume = 0f" in before, code[max(0, pos - 300):pos + 12]
        tail = before[before.rindex("volume = 0f"):]
        assert re.search(r"\.(Play|UnPause)\(\)", tail), tail


def test_the_fade_witness_tag_is_written_in_two_places():
    code = code_of(_plugin(ENGINE))
    assert code.count('"[MUSIC-FADE]') == 3, code.count('"[MUSIC-FADE]')
    arm = code_of(_plugin(ENGINE), "private static void ArmFade()")
    sample = code_of(_plugin(ENGINE), "private static void LogLongFadeSample(float mainVolume, float fade)")
    assert arm.count('"[MUSIC-FADE]') == 2 and sample.count('"[MUSIC-FADE]') == 1


def test_the_level_step_is_a_testscript_verb_behind_the_seat_guard():
    begin = code_of(_plugin(ENGINE), "private static void TsBegin()")
    assert begin.count('case "level":') == 1
    run = code_of(_plugin(ENGINE), "private static void TsRun()")
    assert 'case "level": TsRunLevel(rt); return;' in run
    guard = code_of(_plugin(ENGINE), "internal static void TickTestScript()")
    assert "BroadcastMode.IsBroadcastIdentity" in guard
    level = code_of(_plugin(ENGINE), "private static void TsRunLevel(float rt)")
    assert ".volume =" not in level and ".Play(" not in level, "the measurement step writes"
    assert code_of(_plugin(ENGINE)).count('"[MUSIC-LEVEL]') == 2


# -- (c) the album note ---------------------------------------------------------

def _album_heads():
    code = code_of(_plugin("MusicCatalog.cs"))
    albums = code.split("internal static readonly MusicAlbumDef[] Albums", 1)[1]
    return [b.split("Tracks =", 1)[0] for b in re.split(r"new MusicAlbumDef\s*\{", albums)[1:]]


def test_the_flag_defaults_false_and_marks_exactly_the_custom_albums():
    code = code_of(_plugin("MusicCatalog.cs"))
    decl = re.search(r"public bool MachineGenerated\s*(=[^;]*)?;", code)
    assert decl, "MusicAlbumDef has no MachineGenerated flag"
    assert decl.group(1) is None, "the flag must default to false (no initializer)"
    heads = _album_heads()
    assert len(heads) >= 2
    flagged = set()
    for head in heads:
        sku = re.search(r'Sku\s*=\s*"([^"]+)"', head).group(1)
        if re.search(r"MachineGenerated\s*=\s*true\s*,", head):
            flagged.add(sku)
            assert re.search(r'ArtistName\s*=\s*"Sid"', head), sku
        assert not re.search(r"MachineGenerated\s*=\s*false", head), "spell the default by omission: " + sku
    assert flagged == FLAGGED_ALBUMS, flagged


def test_the_note_is_authored_text_beside_the_byline_and_in_the_readout():
    raw = _plugin("NativeUI.cs")
    ui = code_of(raw)
    m = re.search(r'private const string MUSIC_ALBUM_NOTE\s*=\s*"([^"]*)"\s*;', ui)
    assert m, "no MUSIC_ALBUM_NOTE constant"
    assert re.sub(r"<[^>]+>", "", m.group(1)).strip() == "(" + NOTE + ")", m.group(1)
    helper = code_of(raw, "private static string MusicAlbumNote(MusicAlbumDef alb)")
    assert "alb.MachineGenerated" in helper and "MUSIC_ALBUM_NOTE" in helper
    byline = [ln for ln in ui.splitlines() if 'I18n.TrF("by {0}", HomeSan(alb.ArtistName' in ln]
    assert len(byline) == 1 and "MusicAlbumNote(alb)" in byline[0], byline
    readout = code_of(raw, "private static string NowPlayingAlbumNote()")
    assert "MusicEngine.NowPlayingAlbumSku()" in readout and "MusicAlbumNote(" in readout
    refresh = code_of(raw, "private static void RefreshMusicTab()")
    assert refresh.count("NowPlayingAlbumNote()") == 1 and "np + NowPlayingAlbumNote()" in refresh
    # Exactly those render sites: the helper's definition and its two callers,
    # the readout helper's definition and its one caller.
    assert ui.count("MusicAlbumNote(") == 3, ui.count("MusicAlbumNote(")
    assert ui.count("NowPlayingAlbumNote()") == 2, ui.count("NowPlayingAlbumNote()")
    assert ui.count("MUSIC_ALBUM_NOTE") == 2, ui.count("MUSIC_ALBUM_NOTE")


def test_the_note_never_goes_through_i18n_and_is_shown_nowhere_else():
    carriers = {}
    for name in sorted(os.listdir(PLUGIN)):
        if not name.endswith(".cs"):
            continue
        src = _plugin(name)
        for ln in src.splitlines():
            if NOTE in ln:
                carriers[name] = carriers.get(name, 0) + 1
                assert "I18n.Tr" not in ln, (name, ln.strip())
    assert set(carriers) <= {"NativeUI.cs", "MusicCatalog.cs"}, carriers
    assert code_of(_plugin("MusicCatalog.cs")).count(NOTE) == 0, "the catalog renders the note"
    assert code_of(_plugin("NativeUI.cs")).count(NOTE) == 1
    assert NOTE not in _read("tools/i18n_source.json")
    assert NOTE not in _read("plugin/I18nCatalogues.cs")


def test_the_readout_names_no_album_the_now_playing_line_does_not():
    body = code_of(_plugin(ENGINE), "internal static string NowPlayingAlbumSku()")
    assert "s.mode == MusicMode.Preview && s.previewTrack.HasValue && s.previewStarted" in body
    assert "s.mode == MusicMode.Custom && s.current.HasValue && s.currentStarted" in body
