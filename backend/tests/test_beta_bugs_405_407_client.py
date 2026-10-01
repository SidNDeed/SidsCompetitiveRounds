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

HIT = PLUGIN / "HitEvidence.cs"
HIT_CORE = PLUGIN / "HitEvidenceCore.cs"

TAGS = {"[POISON-LATE]": POISON, "[HP-POINT-END]": POISON, "[SAW-POINT]": POISON, "[DANCE-FIT]": DANCE,
        "[HIT-RECV]": HIT_CORE, "[SHOT-OBS]": HIT_CORE, "[BLOCK-MISS]": HIT_CORE}


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


# -- item D: hits, knockback and blocks as the RECEIVING seat saw them ---------
# The pure half (pairing, buckets, first-hit dedup, the three lines) is
# EXECUTED by tools/tests/hit-evidence-client with its own mutants. Checked
# here: the hooks sit on the received messages, only count, attribute by the
# message's sender, and are flushed per point and per game.

HOOKS = (
    '[HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeDamage")]',
    '[HarmonyPatch(typeof(HealthHandler), "RPCA_SendTakeForce")]',
    '[HarmonyPatch(typeof(HealthHandler), "DoDamage")]',
    '[HarmonyPatch(typeof(Block), "RPCA_DoBlock")]',
    '[HarmonyPatch(typeof(ProjectileInit), "RPCA_Init")]',
    '[HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_noAmmoUse")]',
    '[HarmonyPatch(typeof(ProjectileInit), "RPCA_Init_SeparateGun")]',
    '[HarmonyPatch(typeof(ProjectileHit), "RPCA_DoHit")]',
)


def test_hit_evidence_hooks_sit_on_the_received_messages():
    src = _read(HIT)
    for hook in HOOKS:
        assert src.count(hook) == 1, hook
    sender = _member(src, "internal static class HitEvidence_ExecuteRpcPatch")
    assert 'AccessTools.Method(typeof(PhotonNetwork), "ExecuteRpc"' in sender
    assert "typeof(ExitGames.Client.Photon.Hashtable), typeof(Photon.Realtime.Player)" in sender
    assert "throw new Exception(" in sender            # a missing target is a visible patch failure, never silent


def test_hit_evidence_hooks_only_count():
    src = _read(HIT)
    assert not re.search(r"static\s+bool\s+Prefix", src), "a prefix that can skip the original"
    assert "__result" not in src and not re.search(r"\bref\s+\w", src), "a hook that rewrites a result or an argument"
    finals = len(re.findall(r"\[HarmonyFinalizer\]", src))
    assert finals == src.count("return __exception;") >= 9, "every finalizer returns the exception it was given"
    for body in (src, _read(HIT_CORE)):
        assert not re.search(r"steam", body, re.I), "an account identity in an evidence line"
        assert not re.search(r"\.health\s*[-+]?=[^=]", body), "evidence writes health"
        for call in ("DoDamage(", "TakeDamage(", "TakeForce(", "Heal(", "RaiseEvent(", ".RPC(", "sinceBlock ="):
            assert call not in body, call
        # a knockback write is <body>.AddForce( (playerVel, a rigidbody); the
        # tally's own AddForce is called on P(actor), a call result
        assert not re.search(r"[A-Za-z_\]]\.AddForce\(", body), "evidence applies a force"


def test_hit_evidence_attributes_by_sender_and_counts_the_local_player_only():
    src = _read(HIT)
    sender = _member(src, "internal static class HitEvidence_ExecuteRpcPatch")
    assert "__state = HitEvidence.RpcSender;" in sender and "HitEvidence.RpcSender = __state;" in sender
    for name in ("internal static void NoteDamage(", "internal static void NoteForce("):
        body = _member(src, name)
        assert "RemoteSender(out actor)" in body and "LocalVictim(hh, out data)" in body, name
    for name in ("internal static void NoteSpawn(", "internal static void NoteImpact("):
        assert "RemoteSender(out actor)" in _member(src, name), name
    impact = _member(src, "internal static void NoteImpact(")
    assert "target.IsMine" in impact
    dot = _member(src, "internal static void NoteDot(")
    assert "!healthRemoval" in dot and "LocalVictim(hh, out data)" in dot
    damage = _member(src, "internal static void NoteDamage(")
    assert "HitEvidenceCore.Bucket(_blockedThisPoint, since)" in damage and "data.block.sinceBlock" in damage


def test_hit_evidence_flushes_per_point_and_per_game():
    poison = _read(POISON)
    ev = _member(poison, "internal static class PointEvidence")
    assert _member(ev, "internal static void PointEnd()").count("HitEvidence.PointEnd(_point);") == 1
    assert "HitEvidence.ResetForRoomExit(_point);" in _member(ev, "internal static void ResetForRoomExit()")
    over = _member(ev, "internal static void GameOverCheck(GM_ArmsRace gm)")
    assert "gm.p1Rounds >= gm.roundsToWinGame || gm.p2Rounds >= gm.roundsToWinGame" in over
    assert "HitEvidence.GameEnd(_point);" in over
    assert "PointEvidence.GameOverCheck(__instance);" in _member(poison, "internal static class PointEndEvidencePatch")
    src = _read(HIT)
    start = _member(src, "internal static class HitEvidence_StartGamePatch")
    assert "HitEvidence.GameEnd(PointEvidence.Point);" in start
    point = _member(src, "internal static void PointEnd(int point)")
    assert "_point.Clear();" in point and "_blockedThisPoint = false;" in point
    game = _member(src, "internal static void GameEnd(int point)")
    assert "_game.Clear();" in game and "HitEvidenceCore.ShotObsLine(" in game and "HitEvidenceCore.BlockMissLine(" in game
