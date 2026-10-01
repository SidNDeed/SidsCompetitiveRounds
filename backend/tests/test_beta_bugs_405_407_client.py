"""Client source checks for the 1.41.0 beta reports 405, 406 and 407.

Bug 405, item A: a dance capture's frames must pass the server's edge band
(pc_motion.check_frame, motion_edge). The pure half -- FirstEdgePixel and
FitDrawn -- is EXECUTED by tools/tests/dance-cards-client (cases
edge_first_pixel and fit_drawn, mutants edge_row_buffer_order, fit_solid_only
and fit_cap_cuts_solid). What is checked here is the wiring a harness cannot
reach: the capture measures what the particles draw at every pose of the
pre-pass, the camera is made from the fitted square (never the solid one
alone), and a band refusal writes the [DANCE-FIT] line.

Bug 405, item B: the playback's view names come from the View enum, so a
View value can never index past them (the Trades view threw on every frame).

Bugs 406/407, item C: evidence only. The late-verdict line on the watching
seat, the per-point health line and the per-point Saw damage line exist once
each, under tags used for nothing else, are bounded (no per-frame log), carry
no account identity, and write no health.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"
DANCE = PLUGIN / "PortraitRenderDance.cs"
CARDS = PLUGIN / "PlayerCardsUI.cs"
POISON = PLUGIN / "PoisonSync.cs"


def _read(path):
    return path.read_text(encoding="utf-8")


def _member(src, signature):
    """The member whose declaration starts with `signature`, to its matching
    brace (strings and comments are not special-cased: the members read here
    carry no unbalanced brace in a literal). The signature must occur once."""
    assert src.count(signature) == 1, "%r occurs %d times" % (signature, src.count(signature))
    start = src.index(signature)
    i = src.index("{", start)
    depth = 0
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError("no end for %r" % signature)


# -- item A: bug 405 ----------------------------------------------------------

def test_dance_camera_is_made_from_the_fitted_square():
    run = _member(_read(DANCE), "private static IEnumerator DanceRun(")
    prepass = run[run.index('clock.Phase = "prepass";'):run.index('clock.Phase = "alloc";')]
    loop = prepass[prepass.index("for (int k = -1; k < n; k++)"):prepass.index("arms.Rest(rigRoot);\n                DanceEmotes.PortraitPose = null;")]
    assert loop.count("DanceDrawnPose(drawn, clone);") == 1, "the particles are not measured at every pre-pass pose"
    assert prepass.count("Bounds fit = DanceFitDrawn(drawn, solidFit, opt, out cullFail);") == 1
    alloc = run[run.index('clock.Phase = "alloc";'):]
    assert alloc.count("var cam = MakeCamera(fit, DEFAULT_SIZE);") == 1
    assert "MakeCamera(solidFit" not in run
    # the measurement starts from the pinned, paused particles
    pinned = run.index("if (!rig.Pinned(gunStill))")
    assert run.index("drawn = DanceDrawnSnap();") > pinned


def test_band_refusal_logs_the_pixel_bounds_and_fit():
    src = _read(DANCE)
    run = _member(src, "private static IEnumerator DanceRun(")
    fin = run[run.index("finally"):]
    assert fin.count('Plugin.Log.LogInfo("[DANCE-FIT] " + DanceFitLine(') == 1
    assert 'checkFail.Contains("edge band")' in fin
    line = _member(src, "private static string DanceFitLine(")
    for field in ('" solid="', '" all="', '" solid_side="', '" fit_side="', '" band=frame "', '" px=("', '") alpha="', '" owner="'):
        assert field in line, field
    assert "Steam" not in line and "steam" not in line


def test_cull_happens_before_any_render():
    run = _member(_read(DANCE), "private static IEnumerator DanceRun(")
    assert run.index("DanceFitDrawn(") < run.index("DanceRenderPair(")
    assert run.index("DanceFitDrawn(") < run.index("cam.Render()")


# -- item B: bug 405's log, the Trades view ----------------------------------

def test_motion_view_names_come_from_the_enum():
    src = _read(CARDS)
    enum = re.search(r"private enum View \{([^}]*)\}", src)
    assert enum, "the View enum was not found"
    members = [m.strip() for m in enum.group(1).split(",") if m.strip()]
    assert "Trades" in members and len(members) >= 4
    assert "private static readonly string[] MotionViews = MotionViewNames();" in src
    assert not re.search(r"MotionViews\s*=\s*\{", src), "a hand-written MotionViews list is back"
    names = _member(src, "private static string[] MotionViewNames()")
    assert "Enum.GetValues(typeof(View))" in names
    tick = _member(src, "private static void MotionTick(bool onTab)")
    assert tick.count("MotionViews[(int)view]") == 1
    assert "MotionPageKey((int)view, 0, null)" in tick


# -- item C: bugs 406/407, evidence only --------------------------------------

TAGS = {"[POISON-LATE]": POISON, "[HP-POINT-END]": POISON, "[SAW-POINT]": POISON, "[DANCE-FIT]": DANCE}


def test_evidence_tags_exist_for_nothing_else():
    for tag, home in TAGS.items():
        hits = [p.name for p in PLUGIN.glob("*.cs") if tag in _read(p)]
        assert hits == [home.name], (tag, hits)


def test_late_verdict_line_on_the_watching_seat():
    src = _read(POISON)
    shadow = _member(src, "internal static IEnumerator ShadowDot(")
    assert shadow.count("NoteSilence(actor, viewId, anchor);") == 1
    assert shadow.index("[POISON-SILENT]") < shadow.index("NoteSilence(")
    on_event = _member(src, "private static void OnEvent(EventData e)")
    seq = on_event.index("_lastSeq[e.Sender] = seq;")
    call = on_event.index("NoteVerdictAfterSilence(e.Sender, viewId, streamId,")
    assert on_event.count("NoteVerdictAfterSilence(") == 1 and call > seq
    late = _member(src, "private static void NoteVerdictAfterSilence(")
    for field in ("stream=", "tick=", "delay_from_arm_ms=", "delay_from_silence_ms="):
        assert field in late, field
    assert "_silence.Remove(actor);" in late          # one line per silence, never a stream of them


def test_point_end_lines_and_saw_bracket():
    src = _read(POISON)
    patch = src[src.index("internal static class PointEndEvidencePatch") - 200:]
    assert '[HarmonyPatch(typeof(GM_ArmsRace), "RPCA_NextRound"' in patch
    assert "PointEvidence.PointEnd();" in _member(src, "internal static class PointEndEvidencePatch")
    saw = _member(src, "internal static class SawPointEvidencePatch")
    assert "PointEvidence.SawBefore();" in saw and "PointEvidence.SawAfter();" in saw
    assert "[HarmonyFinalizer]" in saw and "return __exception;" in saw
    end = _member(src, "internal static void PointEnd()")
    assert end.count('"[HP-POINT-END] point="') == 1 and end.count('"[SAW-POINT] point="') == 1
    assert ".health" in end and ".MaxHealth" in end


def test_evidence_is_bounded_identity_free_and_writes_nothing():
    src = _read(POISON)
    ev = _member(src, "internal static class PointEvidence")
    for per_frame in ("internal static void SawBefore()", "internal static void SawAfter()"):
        body = _member(ev, per_frame)
        assert "Log." not in body, per_frame + " logs"
    for body in (ev, _member(src, "private static void NoteVerdictAfterSilence("),
                 _member(src, "internal static void ReportUnansweredSilences()")):
        assert not re.search(r"steam", body, re.I), "an account identity in an evidence line"
        assert not re.search(r"\.health\s*[-+]?=[^=]", body), "evidence writes health"
        for call in ("DoDamage(", "TakeDamage(", "Heal(", "RaiseEvent(", ".RPC("):
            assert call not in body, call
