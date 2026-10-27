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

from _cs_structure import code_of, mask_code

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
    # Round 2 (M1): the clip's measured gain MULTIPLIES the slider law on both
    # sources; it never replaces it.
    assert re.search(r"float mainVolume = mult \* s\.mainTrackGain \* baseGain \*", body)
    assert "m.volume = mainVolume;" in body
    assert "p.volume = mult * s.previewTrackGain * baseGain;" in body, (
        "the preview source bypasses the ceiling or its clip's gain")
    assert "pctFrac" not in body, "the uncapped pre-1.41 law is still in the tick"


PREVIEW_WRITE = "mult * s.previewTrackGain * baseGain"


def test_nothing_else_sets_a_music_source_gain():
    """Every other write to a source's volume in the engine is the silent zero
    before a Play or UnPause; a third path writing a gain would bypass the
    ceiling."""
    writes = [w.strip() for w in re.findall(r"\.volume\s*=\s*([^;]+);", code_of(_plugin(ENGINE)))]
    others = [w for w in writes if w not in ("0f", "mainVolume", PREVIEW_WRITE)]
    assert not others, others
    assert writes.count("mainVolume") == 1 and writes.count(PREVIEW_WRITE) == 1, writes


# -- round 2, M1: the per-clip gain table ------------------------------------

def _levels_table():
    """(target, [(clip, rms, peak, gain)]) parsed from MusicLevels.cs."""
    code = code_of(_plugin("MusicLevels.cs"))
    t = re.search(r"internal const float TRACK_TARGET_RMS_DBFS\s*=\s*(-?[0-9.]+)f\s*;", code)
    assert t, "no TRACK_TARGET_RMS_DBFS"
    body = code.split("internal static readonly TrackLevel[] TrackLevels", 1)[1].split("};", 1)[0]
    rows = [(c, float(r), float(p), float(g)) for c, r, p, g in re.findall(
        r'new TrackLevel\("([^"]+)",\s*(-?[0-9.]+)f,\s*(-?[0-9.]+)f,\s*([0-9.]+)f\)', body)]
    assert len(rows) == body.count("new TrackLevel("), "a table row the parser cannot read"
    return float(t.group(1)), rows


def _catalog_clips():
    code = code_of(_plugin("MusicCatalog.cs"))
    clips = re.findall(r'OggFile = "([^"]+)"', code) + re.findall(r'PreviewFile = "([^"]+)"', code)
    assert clips and len(clips) == len(set(clips)), "the catalog names a clip twice"
    return clips


def test_every_clip_the_album_catalog_names_has_a_table_entry():
    """The structure gate: a clip the catalog (and, where the asset manifest is
    on disk, the manifest) names with no measured row fails here, never
    silently plays at gain 1."""
    _target, rows = _levels_table()
    table = [c for c, _r, _p, _g in rows]
    assert len(table) == len(set(table)), "a clip has two rows"
    catalog = _catalog_clips()
    assert sorted(table) == sorted(catalog), (
        "missing: %s; extra: %s" % (sorted(set(catalog) - set(table)), sorted(set(table) - set(catalog))))
    manifest = os.path.join(PLUGIN, "music", "manifest.json")
    if os.path.exists(manifest):
        import json
        with io.open(manifest, encoding="utf-8") as fh:
            oggs = [k for k in json.load(fh) if k.endswith(".ogg")]
        assert sorted(oggs) == sorted(table), sorted(set(oggs) ^ set(table))


def test_the_shipped_gains_bring_every_clip_within_3_db_of_one_target():
    """Recomputes each gain from its recorded measurement and the ONE target,
    and the post-gain RMS spread over the full tracks and over the previews."""
    import math
    target, rows = _levels_table()
    for clip, rms, _peak, gain in rows:
        want = 10 ** ((target - rms) / 20.0)
        assert abs(gain - want) <= 0.00051, (clip, gain, round(want, 4))
    for previews in (False, True):
        post = [rms + 20 * math.log10(gain) for clip, rms, _p, gain in rows
                if clip.endswith("_preview.ogg") == previews]
        assert len(post) == 21, len(post)
        spread = max(post) - min(post)
        assert spread <= 3.0, ("previews" if previews else "tracks", round(spread, 3))
    # the measurement the bar was judged on: without the table, 3.13 dB
    full = [rms for clip, rms, _p, _g in rows if not clip.endswith("_preview.ogg")]
    assert max(full) - min(full) > 3.0, "the recorded measurements no longer need the table"


def test_the_engine_resolves_each_clips_gain_at_every_start_and_logs_it():
    arm = code_of(_plugin(ENGINE), "private static void ArmFade()")
    assert "s.mainTrackGain = s.current.HasValue ? ResolveTrackGain(s.current.Value, false) : 1f;" in arm
    code = code_of(_plugin(ENGINE))
    assert code.count("s.previewTrackGain = ResolveTrackGain(s.previewTrack.Value, true);") == 1
    pre = code.split("s.previewTrackGain = ResolveTrackGain(s.previewTrack.Value, true);", 1)[1][:80]
    assert "p.Play();" in pre, "the preview's gain is not resolved at its start"
    assert len(re.findall(r"\bmainTrackGain\s*=[^=]", code)) == 2   # the field's 1f and ArmFade
    assert len(re.findall(r"\bpreviewTrackGain\s*=[^=]", code)) == 2
    res = code_of(_plugin(ENGINE), "private static float ResolveTrackGain(TrackRef t, bool preview)")
    assert "MusicLevels.TryTrackGain(clip, out gain)" in res
    assert "preview ? album.Tracks[t.Idx].PreviewFile : album.Tracks[t.Idx].OggFile" in res
    assert res.count('"[MUSIC] level "') == 3, "one [MUSIC] line per start naming the clip and its gain"
    assert "LogLevel.Warning" in res, "a clip without a row must not play at 1 silently"


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
    """The decision lives in MusicLevels.FirstTrackFade (executed by the
    harness); the engine closes it on the menu-to-game edge and resets it on
    the way back in, and nowhere else."""
    body = code_of(_plugin(ENGINE), "internal static void NotePrefixContext(bool menuCall, bool isCard)")
    assert body.count("if (leavingMenu)") == 1 and body.count("else if (c == Ctx.Menu)") == 1
    exit_at = body.index("if (leavingMenu)")
    enter_at = body.index("else if (c == Ctx.Menu)")
    assert body.count("s.firstFade.LeaveMenu();") == 1 and body.count("s.firstFade.EnterMenu();") == 1
    assert exit_at < body.index("s.firstFade.LeaveMenu();") < enter_at, \
        "the long fade is not decided on the menu-to-game edge"
    assert body.index("s.firstFade.EnterMenu();") > enter_at, "entering the menu keeps a stale decision"
    code = code_of(_plugin(ENGINE))
    for call in ("firstFade.LeaveMenu(", "firstFade.EnterMenu(", "firstFade.SampleMenu(", "firstFade.Arm("):
        assert code.count(call) == 1, (call, code.count(call))
    # the round-1 fields are gone, so nothing can decide beside FirstTrackFade
    assert "longFadePending" not in code and "menuAudible" not in code


def test_menu_audibility_counts_the_games_own_menu_music():
    """Round 2 (M2): the menu is audible when the mod's own Main or Preview
    source plays OR the game's own menu music plays -- the engine does not own
    the menu (vanilla menu mode, nothing selected, fault, dead patch) and the
    game's music is not muted at its mixer. Sampled only while in the menu."""
    body = _tick()
    assert re.search(r"bool mainAudible = m != null && m\.isPlaying && !s\.mainPausedByUs && !s\.paused;", body)
    assert re.search(r"if \(s\.ctx == Ctx\.Menu\) SampleMenuAudibility\(mainAudible, rt\);", body)
    assert _plugin(ENGINE).count("SampleMenuAudibility(") == 2   # definition + the one call
    sample = code_of(_plugin(ENGINE), "private static void SampleMenuAudibility(bool mainAudible, float rt)")
    assert "bool gamePlays = !IsEngineOwned(s.mode) || s.faultPending || s.faultDurable || _patchDead;" in sample
    assert "s.gameMusicMuted = GameMusicMuted(out s.gameMenuWhy);" in sample
    assert "h.Preview.isPlaying" in sample
    assert ("s.firstFade.SampleMenu(mainAudible || previewAudible, gamePlays, s.gameMusicMuted, s.gameMenuWhy);"
            in sample)
    muted = code_of(_plugin(ENGINE), "private static bool GameMusicMuted(out string why)")
    assert "SoundVolumeManager.Instance" in muted
    assert "mixer.GetFloat(svm.masterName, out master)" in muted and "mixer.GetFloat(svm.musName, out mus)" in muted
    assert "return (okM && master <= GAME_MUTED_DB) || (okU && mus <= GAME_MUTED_DB);" in muted
    assert re.search(r"private const float GAME_MUTED_DB = -79f;", code_of(_plugin(ENGINE)))


def test_arm_fade_takes_the_decision_once_and_names_an_audible_menu():
    body = code_of(_plugin(ENGINE), "private static void ArmFade()")
    assert body.count("s.fadeLong = s.firstFade.Arm(s.ctx == Ctx.Menu, out audibleWhy);") == 1
    assert '" s (first track after a silent main menu) perceptual ctx="' in body
    assert '" (menu was audible: " + audibleWhy + ")"' in body
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
    style = re.search(r'private const string MUSIC_NOTE_STYLE\s*=\s*"([^"]*)"\s*;', ui)
    assert style, "no MUSIC_NOTE_STYLE constant"
    m = re.search(r'private const string MUSIC_ALBUM_NOTE\s*=\s*"  " \+ MUSIC_NOTE_STYLE \+ "([^"]*)"\s*;', ui)
    assert m, "MUSIC_ALBUM_NOTE is not built on MUSIC_NOTE_STYLE"
    assert re.sub(r"<[^>]+>", "", style.group(1) + m.group(1)).strip() == "(" + NOTE + ")", m.group(1)
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


def test_the_readout_and_the_byline_share_one_absolute_note_style():
    """Round 2 (L2): both lines render the note through the SAME style
    constant, at an ABSOLUTE size of at least 14 pt, never a size relative to
    each line's own base -- which is what made the readout's note another size
    than the by-line's. 14, not CreateText's 12 pt floor: the round-2 seat
    capture found no hyphen pixel at 12 pt in either line and one partly
    covered row at 14 pt in both (an observation at that scale, not a
    guarantee of the font)."""
    ui = code_of(_plugin("NativeUI.cs"))
    style = re.search(r'private const string MUSIC_NOTE_STYLE\s*=\s*"([^"]*)"\s*;', ui).group(1)
    size = re.search(r"<size=([0-9.]+)>", style)
    assert size and float(size.group(1)) >= 14.0, style
    assert "%" not in style and "<size=+" not in style and "<size=-" not in style, style
    assert ui.count("MUSIC_NOTE_STYLE") == 2, "a second style for the note: %d" % ui.count("MUSIC_NOTE_STYLE")
    assert ui.count("<size=85%><color=#888>(") == 0
    note = re.search(r'private const string MUSIC_ALBUM_NOTE\s*=\s*([^;]+);', ui).group(1)
    assert "<size" not in note.replace("MUSIC_NOTE_STYLE", ""), note
    # Both render sites reach the note only through MusicAlbumNote (one helper,
    # one constant): the readout's helper returns MusicAlbumNote(...), the
    # by-line calls it directly.
    readout = code_of(_plugin("NativeUI.cs"), "private static string NowPlayingAlbumNote()")
    assert "MusicAlbumNote(MusicCatalog.Get(sku))" in readout and "<size" not in readout
    refresh = code_of(_plugin("NativeUI.cs"), "private static void RefreshMusicTab()")
    assert "np + NowPlayingAlbumNote()" in refresh


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
    # Nor through the constant or either helper: none of them sits inside an
    # I18n.Tr/TrF argument list (balanced parentheses, literals and comments
    # masked), so the translation layer never sees the note at all.
    masked = mask_code(_plugin("NativeUI.cs"))
    wrapped = []
    calls = 0
    for m in re.finditer(r"\bI18n\.Tr\w*\(", masked):
        calls += 1
        depth, i = 1, m.end()
        while depth and i < len(masked):
            depth += {"(": 1, ")": -1}.get(masked[i], 0)
            i += 1
        args = masked[m.end():i - 1]
        wrapped += [(ident, masked[m.start():i][:120]) for ident in
                    ("MUSIC_ALBUM_NOTE", "MusicAlbumNote(", "NowPlayingAlbumNote(") if ident in args]
    assert calls > 100, "the I18n call scan found only %d calls" % calls
    assert not wrapped, wrapped


def test_the_readout_names_no_album_the_now_playing_line_does_not():
    body = code_of(_plugin(ENGINE), "internal static string NowPlayingAlbumSku()")
    assert "s.mode == MusicMode.Preview && s.previewTrack.HasValue && s.previewStarted" in body
    assert "s.mode == MusicMode.Custom && s.current.HasValue && s.currentStarted" in body
