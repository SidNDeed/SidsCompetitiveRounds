"""The client control registry for cf_controls.py: one entry per K, WP and
N11 row of the evidence file (V11:2898-2948, sec8.3), each with its structure
test node(s), its mutants (the assertion tag each must turn red) and its
inert twin. Imported at the end of cf_controls_rows, which owns ROWS.

Every client row copies plugin/ and tools/ into the scratch tree (XT). The
edit texts are computed here, at import, from the lane's own sources: a
needle is matched with each whitespace run flexible, against the
comment-stripped text (literals kept), inside the member span its signatures
name, and must match exactly once; the edit then grows to whole lines of
unique context. A needle that does not resolve yields an edit that can never
apply, so `cf_controls.py check` reports it STALE with the reason: nothing is
skipped silently.

New text may use a newline followed by ^ (the indentation of the matched
first line), ^^ (that plus four spaces) or < (that less four spaces).

K9, K19 and the I4 half of K25 are not here: the upload hook they read does
not exist on this lane (brief C8), as test_ffa_assembly_client_structure says.
"""

import os
import re

from cf_controls_rows import E, M, T, row
import _cs_structure as cs
import test_ffa_assembly_client_structure as st

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
ST = "test_ffa_assembly_client_structure.py::"
XT = ("plugin", "tools")

AC = "plugin/ApiClient.cs"
PL = "plugin/Plugin.cs"
FA = "plugin/FfaAssembly.cs"
FLE = "plugin/FfaLateEntry.cs"
FLR = "plugin/FfaLateRules.cs"
FM = "plugin/FfaMode.cs"
GSW = "plugin/GameStateWatcher.cs"
RA = "plugin/RoomActors.cs"
SP = "plugin/SpectatorPatches.cs"
NUI = "plugin/NativeUI.cs"
CSPROJ = "plugin/CompetitiveRounds.csproj"
GATE = "tools/g3-publish-gate.ps1"
CEN = "tools/kept_view_census/kept_view_census.py"
CLM = "tools/claim_census/claim_census.py"
BM = "tools/boundary_model/boundary_model.py"
HM = "tools/late-rules-harness/Main.cs"
MAINPY = "backend/api/main.py"

NODE = {
    "k01": "test_k01_every_step_once_in_its_anchor",
    "k02": "test_k02_eight_resets_read_realtime",
    "k03": "test_k03_k26_end_attempt_behind_join_gate",
    "k04": "test_k04_region_check_position_and_guard",
    "k05": "test_k05_k50_exit_hook_consumes",
    "k50": "test_k50_exit_routes_release_and_leave",
    "k06": "test_k06_k20_barrier_position",
    "k07": "test_k07_guard_toast_behind_suppression",
    "k07b": "test_k07b_owed_toast_and_stall_warning",
    "k24": "test_k24_suppression_lease",
    "k08": "test_k08_k33_spawn_sites",
    "k33": "test_k33_k43_spawn_gate_and_late_spawn",
    "k10": "test_k10_n11_wp2_every_leave_labelled",
    "k13": "test_k13_label_reaches_only_its_parameter",
    "k11": "test_k11_wp1_caps",
    "k46": "test_k46_g3_build_and_gate",
    "k12": "test_k12_countdown_abort_exemption",
    "k14": "test_k14_attempt_posts",
    "k15": "test_k15_k16_region_rearm",
    "k17": "test_k17_k25_poll_fail_notice_drops",
    "k18": "test_k18_k27_k35_ready_join",
    "k21": "test_k21_k22_k41_barrier_run",
    "k23": "test_k23_timeouts_and_single_flight",
    "k28": "test_k28_k48_wp9_census_body",
    "k29": "test_k29_k30_k31_arrival_master_ready_tick",
    "k32": "test_k32_join_deadline",
    "k34": "test_k34_stall_latch",
    "k36": "test_k36_load_gate",
    "k37": "test_k37_force_start",
    "k38": "test_k38_master_boundary",
    "k39": "test_k39_k40_reporter_rule_and_ghosts",
    "k42": "test_k42_per_site_views_and_fence",
    "k42clean": "test_k42_census_clean",
    "k42red": "test_k42_census_red_pairs",
    "k44": "test_k44_digest",
    "k45": "test_k45_harness_and_boundary_model",
    "k47": "test_k47_gated_roster_freeze",
    "k49": "test_k49_claim_census",
    "wp3": "test_wp3_payload_keys",
    "wp4": "test_wp4_wp8_answer_keys",
    "wp5": "test_wp5_room_and_player_properties",
    "wp6": "test_wp6_late_snapshot_tail",
    "wp7": "test_wp7_wp10_wp11_events",
    "wp7c": "test_wp7_chain_vectors",
    "wp12": "test_wp12_release_route",
}
_unknown = sorted(v for v in NODE.values() if not callable(getattr(st, v, None)))
assert not _unknown, ("client registry: unknown structure nodes", _unknown)


def N(*keys):
    return [ST + NODE[k] for k in keys]


# ---------------------------------------------------------------- locating

class _Miss(Exception):
    pass


_TXT, _MSK, _KPT = {}, {}, {}


def _src(rel):
    if rel not in _TXT:
        with open(os.path.join(ROOT, rel), "rb") as fh:
            _TXT[rel] = fh.read().decode("utf-8")
    return _TXT[rel]


def _mask(rel):
    """mask_code of a C# file (the text itself for any other file); the
    offsets must be the source's, so a length change is refused."""
    if rel not in _MSK:
        t = _src(rel)
        m = cs.mask_code(t) if rel.endswith(".cs") else t
        _MSK[rel] = m if len(m) == len(t) else None
    if _MSK[rel] is None:
        raise _Miss("mask_code changed the length of " + rel)
    return _MSK[rel]


def _kept(rel):
    if rel not in _KPT:
        t = _src(rel)
        k = cs.strip_comments_only(t) if rel.endswith(".cs") else t
        _KPT[rel] = k if len(k) == len(t) else None
    if _KPT[rel] is None:
        raise _Miss("strip_comments_only changed the length of " + rel)
    return _KPT[rel]


def _stale(rel, why):
    return E(rel, "\x00STALE: " + why, "")


def _span(rel, sigs):
    """The block reached by narrowing through each signature in turn, as the
    structure tests' block() does: exactly one block per signature."""
    m = _mask(rel)
    lo, hi = 0, len(m)
    for sig in sigs:
        hits = []
        i = m.find(sig, lo, hi)
        while i >= 0:
            ob = m.find("{", i + len(sig), hi)
            if ob < 0:
                break
            end = st._brace_end(m, ob)
            if end < 0 or end > hi:
                break
            hits.append((ob, end))
            i = m.find(sig, end, hi)
        if len(hits) != 1:
            raise _Miss("%d block(s) for %r" % (len(hits), sig))
        lo, hi = hits[0]
    return lo, hi


def _rx(needle):
    return re.compile(r"\s+".join(re.escape(p) for p in needle.split()))


def _loc(rel, sp, spec):
    """(start, end) of the one match of spec inside sp; a (within, needle)
    spec finds within first, then needle inside it."""
    if isinstance(spec, tuple):
        return _loc(rel, _loc(rel, sp, spec[0]), spec[1])
    hits = [(mm.start(), mm.end()) for mm in _rx(spec).finditer(_kept(rel), sp[0], sp[1])]
    if len(hits) != 1:
        raise _Miss("%d match(es) of %r" % (len(hits), spec[:70]))
    return hits[0]


def _lines(t, s, e):
    a = t.rfind("\n", 0, s) + 1
    if e > s and t[e - 1] == "\n":
        return a, e
    nl = t.find("\n", e)
    return a, (len(t) if nl < 0 else nl + 1)


def _indent(t, a):
    j = a
    while j < len(t) and t[j] in " \t":
        j += 1
    return t[a:j]


def _fmt(text, ind):
    return (text.replace("\n^^", "\n" + ind + "    ").replace("\n^", "\n" + ind)
            .replace("\n<", "\n" + ind[:-4]))


def _grow(rel, s, e, repl):
    """E(rel, old, new): [s, e) replaced by repl, widened to whole lines and
    then line by line until the old text occurs exactly once."""
    t = _src(rel)
    a, b = _lines(t, s, e)
    for _ in range(80):
        old = t[a:b]
        if old and t.count(old) == 1:
            return E(rel, old, t[a:s] + repl + t[e:b])
        if a == 0 and b >= len(t):
            break
        if a > 0:
            a = t.rfind("\n", 0, a - 1) + 1
        if b < len(t):
            nl = t.find("\n", b)
            b = len(t) if nl < 0 else nl + 1
    raise _Miss("no unique context at offset %d" % s)


def _multi(rel, subs):
    """One edit from several (start, end, replacement) parts of one file."""
    t = _src(rel)
    subs = sorted(subs, key=lambda x: (x[0], x[1]))
    for (_, e1, _), (s2, _, _) in zip(subs, subs[1:]):
        if s2 < e1:
            raise _Miss("overlapping operations")
    s0, e0 = subs[0][0], subs[-1][1]
    out, cur = [], s0
    for s, e, r in subs:
        out.append(t[cur:s])
        out.append(r)
        cur = e
    out.append(t[cur:e0])
    return _grow(rel, s0, e0, "".join(out))


def _at(rel, s, e, new):
    try:
        return _grow(rel, s, e, new)
    except _Miss as exc:
        return _stale(rel, str(exc))


def _ins_all(rel, points, text):
    try:
        if not points:
            raise _Miss("nothing to rename")
        return _multi(rel, [(p, p, text) for p in points])
    except _Miss as exc:
        return _stale(rel, str(exc))


def ED(rel, sigs, *ops):
    """One edit from operations located on the original text inside the
    span of sigs (the whole file when empty):
      ("r", spec, new)         replace the match
      ("d", spec)              delete the match's whole lines
      ("a", spec, text)        insert a line after the match's last line
      ("b", spec, text)        insert a line before the match's first line
      ("mv", what, to, after)  move what's lines after (or before) to's lines"""
    try:
        t = _src(rel)
        sp = _span(rel, sigs) if sigs else (0, len(t))
        subs = []
        for op in ops:
            kind = op[0]
            if kind == "r":
                s, e = _loc(rel, sp, op[1])
                a, _ = _lines(t, s, e)
                subs.append((s, e, _fmt(op[2], _indent(t, a))))
            elif kind == "d":
                s, e = _loc(rel, sp, op[1])
                a, b = _lines(t, s, e)
                subs.append((a, b, ""))
            elif kind in ("a", "b"):
                s, e = _loc(rel, sp, op[1])
                a, b = _lines(t, s, e)
                ind = _indent(t, a)
                at = b if kind == "a" else a
                subs.append((at, at, ind + _fmt(op[2], ind) + "\n"))
            elif kind == "mv":
                s1, e1 = _loc(rel, sp, op[1])
                a1, b1 = _lines(t, s1, e1)
                s2, e2 = _loc(rel, sp, op[2])
                a2, b2 = _lines(t, s2, e2)
                at = b2 if op[3] else a2
                if a1 <= at <= b1:
                    raise _Miss("the move lands inside the moved lines")
                subs.append((a1, b1, ""))
                subs.append((at, at, t[a1:b1]))
            else:
                raise _Miss("unknown operation " + kind)
        return _multi(rel, subs)
    except _Miss as exc:
        return _stale(rel, str(exc))


def R(rel, sigs, spec, new):
    return ED(rel, sigs, ("r", spec, new))


def D(rel, sigs, spec):
    return ED(rel, sigs, ("d", spec))


def A(rel, sigs, spec, text):
    return ED(rel, sigs, ("a", spec, text))


def B(rel, sigs, spec, text):
    return ED(rel, sigs, ("b", spec, text))


def MV(rel, sigs, what, to, after=True):
    return ED(rel, sigs, ("mv", what, to, after))


def RR(rel, old, new, count=1):
    """An exact replacement on the raw text (an inactive #if branch, which
    the stripped text blanks)."""
    n = _src(rel).count(old)
    if n != count:
        return _stale(rel, "%d raw match(es) of %r" % (n, old[:60]))
    return E(rel, old, new, count)


def _close(m, op):
    depth = 0
    for i in range(op, len(m)):
        if m[i] == "(":
            depth += 1
        elif m[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _occ(rel, sp, names):
    """The end offsets of the called names (a regex alternation) in sp."""
    m = _mask(rel)
    out = []
    for mm in re.compile(r"(?<![A-Za-z0-9_])(?:" + names + r")\s*\(").finditer(m, sp[0], sp[1]):
        head = re.match(r"[A-Za-z0-9_.]+", m[mm.start():mm.end()]).group(0)
        out.append(mm.start() + len(head))
    return out


def _slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ---------------------------------------------------------------- K1

def _k1():
    """One mutant per anchor: the token's Step/Emit call deleted from its
    anchor span (qualifier to closing paren; the statement's ';' stays)."""
    muts = []
    for i, (tok, f, sigs) in enumerate(st.K1_ANCHORS):
        rel = "plugin/" + f
        mid = "drop_%02d_%s" % (i, tok)
        try:
            sp = _span(rel, sigs)
            t, m = _src(rel), _mask(rel)
            hits = [mm.start() for mm in re.compile(st._STEP % re.escape(tok)).finditer(_kept(rel), sp[0], sp[1])]
            if len(hits) != 1:
                raise _Miss("%d call(s) of %s in %r" % (len(hits), tok, sigs))
            p = q = hits[0]
            while q > 0 and (t[q - 1].isalnum() or t[q - 1] in "_."):
                q -= 1
            cp = _close(m, t.index("(", p))
            if cp < 0:
                raise _Miss("no closing paren for " + tok)
            muts.append(M(mid, "K1 anchor count", _grow(rel, q, cp + 1, ""),
                          note="the %s call deleted from %s %s" % (tok, f, "/".join(sigs))))
        except _Miss as exc:
            muts.append(M(mid, "K1 anchor count", _stale(rel, str(exc))))
    return muts


_PD = ("void FfaPollDrop(",)
_PDL = 'JoinTimeline.Step("poll_drop", "why=" + why + " status=" + st);'
row("K1", N("k01"), _k1() + [
    M("withdrawn_" + w, "K1 withdrawn tokens", A(AC, _PD, _PDL, 'JoinTimeline.Step("%s", "");' % w),
      note="a withdrawn token planted after poll_drop")
    for w in st.K1_WITHDRAWN
], T("detail_through_local",
     R(AC, _PD, _PDL, 'string dropDetail = "why=" + why + " status=" + st;\n^JoinTimeline.Step("poll_drop", dropDetail);')),
    extra=XT)


# ---------------------------------------------------------------- K2

_QRJ = ("class QueueRoomJoiner",)
_ELAPSED = "private float Elapsed => JoinGate ? Time.realtimeSinceStartup - stateStartedRt : stateTimer;"
_RESET = "stateTimer = 0f; stateStartedRt = Time.realtimeSinceStartup;"


def _k2():
    try:
        sp = _span(PL, _QRJ)
        k = _kept(PL)
        hits = [sp[0] + mm.start() for mm in re.finditer(re.escape(_RESET), k[sp[0]:sp[1]])]
        if len(hits) != 8:
            raise _Miss("%d reset sites, want 8" % len(hits))
    except _Miss as exc:
        return [M("reset_sites", "K2 reset rt", _stale(PL, str(exc)))], None
    muts = [M("reset_%d_no_rt" % (j + 1), "K2 reset rt", _at(PL, s, s + len(_RESET), "stateTimer = 0f;"),
              note="the realtime stamp dropped at reset site %d of 8" % (j + 1))
            for j, s in enumerate(hits)]
    twin = T("site_8_swapped", _at(PL, hits[7], hits[7] + len(_RESET),
                                   "stateStartedRt = Time.realtimeSinceStartup; stateTimer = 0f;"),
             note="the two assignments of reset site 8 in the other order")
    return muts, twin


_k2m, _k2t = _k2()
row("K2", N("k02"), _k2m + [
    M("elapsed_timer_only", "K2 elapsed", R(PL, _QRJ, _ELAPSED, "private float Elapsed => stateTimer;")),
], _k2t, extra=XT)


# ---------------------------------------------------------------- K3, K26

_EAF = 'try { QueueRoomJoiner.Instance?.EndAttemptNow("join_failed"); } catch { }'
_JFALSE = ('if (JoinGate) { try { FfaAssembly.PostFailed("join", int.MinValue); } catch { } '
           'EndAttemptNow("join_false");')
row("K3", N("k03"), [
    M("join_failed_no_end", "K3 join failed", D(PL, (), _EAF)),
    M("join_failed_end_ungated", "K3 join failed",
      R(PL, (), _EAF + " }", "}\n<" + _EAF),
      note="the call moved after the JoinGate block's closing brace"),
    M("returned_false_ungated", "K3 returned false", R(PL, (), (_JFALSE, "if (JoinGate)"), "if (true)")),
], T("joiner_local", R(PL, (), _EAF, 'var joiner = QueueRoomJoiner.Instance;\n^try { joiner?.EndAttemptNow("join_failed"); } catch { }')),
    extra=XT)

_END = "bool end = !match && JoinGate && ApiClient.ServerJoinRegionGuard;"
_LEAVEPOST = 'if (JoinGate) FfaAssembly.PostAttempt(joinAttempts + 1, "leave");'
row("K26", N("k03"), [
    M("elapsed_ungated", "K2 elapsed", R(PL, _QRJ, _ELAPSED, "private float Elapsed => stateTimer;"), nodes=N("k02")),
    M("end_attempt_ungated", "K26 end attempt gate", D(PL, ("internal void EndAttemptNow(",), "if (!JoinGate) return;")),
    M("region_end_ungated", "K4 end guard", R(PL, (), _END, "bool end = !match && ApiClient.ServerJoinRegionGuard;"),
      nodes=N("k04")),
    M("leave_post_ungated", "K14 beside the state entry",
      R(PL, (), _LEAVEPOST, 'if (true) FfaAssembly.PostAttempt(joinAttempts + 1, "leave");'), nodes=N("k14")),
    M("connect_post_ungated", "K14 beside the state entry",
      R(PL, (), 'if (JoinGate) FfaAssembly.PostAttempt(joinAttempts + 1, "connect");',
        'if (true) FfaAssembly.PostAttempt(joinAttempts + 1, "connect");'), nodes=N("k14")),
], T("failed_block_brace_on_if_line",
     R(PL, (), 'if (QueueRoomJoiner.JoinGate) { try { FfaAssembly.PostFailed("join", returnCode); } catch { }',
       'if (QueueRoomJoiner.JoinGate) {\n^^try { FfaAssembly.PostFailed("join", returnCode); } catch { }')),
    extra=XT)


# ---------------------------------------------------------------- K4

row("K4", N("k04"), [
    M("end_without_joingate", "K4 end guard", R(PL, (), _END, "bool end = !match && ApiClient.ServerJoinRegionGuard;")),
    M("end_without_flag", "K4 end guard", R(PL, (), _END, "bool end = !match && JoinGate;")),
    M("log_only_when_ending", "K4 log unguarded",
      R(PL, (), ('if (!match) Plugin.Log.LogWarning("[QUEUE-JOINER] region check: live="', "if (!match)"),
        "if (!match && end)")),
], T("target_through_local",
     R(PL, (), "string want = NormRegion(targetRegion);", "string target = targetRegion;\n^string want = NormRegion(target);")),
    extra=XT)


# ---------------------------------------------------------------- K5, K50

_POLL = ("private static void PollRoomState(",)
_HOOK = "if (!asmHandoff && !asmReleased)"
_CLEAR = ("if (!asmHandoff) { try { Plugin.ClearPendingFfaSlot(); } catch { }", "if (!asmHandoff)")
_ROOMEXIT = ('try { ApiClient.FfaLeaveQueue(FfaMode.GameStartedInRoom ? ApiClient.FfaInRoomExitCause() : "", '
             'label: "room_exit"); } catch { }')
row("K5", N("k05"), [
    M("leave_unconditional", "K5 leave behind consumes", R(GSW, _POLL, _HOOK, "if (true)")),
    M("leave_ignores_release", "K5 leave behind consumes", R(GSW, _POLL, _HOOK, "if (!asmHandoff)")),
    M("clear_skips_release", "K5 clear keeps release", R(GSW, _POLL, _CLEAR, "if (!asmHandoff && !asmReleased)")),
], T("exit_cause_through_local",
     R(GSW, _POLL, _ROOMEXIT,
       'string exitCause = FfaMode.GameStartedInRoom ? ApiClient.FfaInRoomExitCause() : "";\n'
       '^try { ApiClient.FfaLeaveQueue(exitCause, label: "room_exit"); } catch { }'),
     note="deviation: the evidence's twin hoists photonRoomId, which the gate pins by name; this "
          "hoists the leave's cause, the same refactor class on a value the gate does not read"),
    extra=XT)

_EXIT = ("internal static void Exit(",)
_SR = ("private static void SendRelease(",)
_RELURL = 'ApiClient.AsmPost(ApiClient.BaseUrl + "/api/v1/ffa/lobby/" + lobby + "/release", json, (ok, resp) =>'
row("K50", N("k50", "k05"), [
    M("leave_only", "K50 one release",
      R(FA, _EXIT, "if (release) Release(why); else ApiClient.FfaLeaveQueue(label: LabelFor(why));",
        "ApiClient.FfaLeaveQueue(label: LabelFor(why));")),
    M("release_always", "K50 release routing",
      R(FA, _EXIT, 'bool release = why == "fence_expired"', 'bool release = true || why == "fence_expired"')),
    M("hook_ignores_release", "K5 leave behind consumes", R(GSW, _POLL, _HOOK, "if (!asmHandoff)"), nodes=N("k05")),
    M("release_not_consumed", "K50 release consumed once",
      D(FA, ("internal static bool ConsumeRelease(",), "ReleaseRoom = null;"), nodes=N("k05")),
    M("no_try_cap", "K50 try cap", R(FA, _SR, "if (tryNo >= 3)", "if (tryNo >= int.MaxValue)")),
], T("url_through_local",
     R(FA, _SR, _RELURL,
       'string url = ApiClient.BaseUrl + "/api/v1/ffa/lobby/" + lobby + "/release";\n^ApiClient.AsmPost(url, json, (ok, resp) =>'),
     note="deviation: the release URL through a local (the evidence's twin reads a gated name)"),
    extra=XT)


# ---------------------------------------------------------------- K6, K20

_DSG = ("public static IEnumerator FfaDoStartGame(",)
_ROOMTWIN = R(FM, _DSG, 'string asmRoom = PhotonNetwork.CurrentRoom?.Name ?? "";',
              'var curRoom = PhotonNetwork.CurrentRoom;\n^string asmRoom = curRoom?.Name ?? "";')
_STARTED = ("GameStartedInRoom = true; OnGameStart();", "GameStartedInRoom = true;")
row("K6", N("k06"), [
    M("started_before_moved_out", "K6 moved-out before started",
      ED(FM, _DSG, ("b", "if (asmRoom == FfaAssembly.MovedOutOf) yield break;", "GameStartedInRoom = true;"),
         ("d", _STARTED))),
], T("room_through_local", _ROOMTWIN), extra=XT)

row("K20", N("k06"), [
    M("hold_after_started", "K20 barrier order",
      MV(FM, _DSG, "if (FfaAssembly.StartHoldActive) yield break; FfaAssembly.StartHoldActive = true;", _STARTED)),
    M("no_reentry_check", "K20 found", D(FM, _DSG, "if (FfaAssembly.StartHoldActive) yield break;")),
], T("room_through_local", _ROOMTWIN), extra=XT)


# ---------------------------------------------------------------- K7, K7b, K24

row("K7", N("k07"), [
    M("warning_suppressed", "K7 warning unsuppressed",
      A(PL, (), "int wanted = Diag2v2.PlayersNeeded();", "if (!FfaAssembly.SuppressGuardToast)")),
], T("owe_block_one_line",
     R(PL, (), "if (owe) { FfaAssembly.OweGuardToast(present, wanted); yield break; }",
       "if (owe) { FfaAssembly.OweGuardToast(present, wanted); yield break; }")),
    extra=XT)

_STALL = ("if (!rankedRoomStallWarned && waited >= warnAfter && !FfaAssembly.SuppressStallWarn) "
          "{ rankedRoomStallWarned = true; CompetitiveUI.ShowNotification(isTournamentRoom")
_OWED = "Cr2v2DiagCallbacks.ShowGuardToast(_owedPresent, _owedWanted);"
row("K7b", N("k07b"), [
    M("no_reshow", "K7b re-show", D(FA, (), _OWED)),
    M("stall_condition_inside", "K7b stall condition",
      ED(GSW, _POLL, ("r", (_STALL, "&& !FfaAssembly.SuppressStallWarn)"), ")"),
         ("b", (_STALL, "CompetitiveUI.ShowNotification(isTournamentRoom"), "if (!FfaAssembly.SuppressStallWarn)"))),
    M("grant_keeps_owed", "K7b clear on grant",
      D(FA, (), ("_grantLate = true; if (_grantRt <= 0f) _grantRt = a.Rt; GuardToastOwed = false;",
                 "GuardToastOwed = false;"))),
], T("show_args_split", R(FA, (), _OWED, "Cr2v2DiagCallbacks.ShowGuardToast(_owedPresent,\n^^_owedWanted);")),
    extra=XT)

_HOLDIF = 'if (a.Hold == 1 && (a.Status == "assembling" || a.Status == "admitted"))'
row("K24", N("k24"), [
    M("renew_ungated", "K24 hold gated", D(FA, (), _HOLDIF)),
    M("postfail_clears", "K24 one writer",
      A(FA, ("private static void PostFail(",), 'string s = err ?? "";', "if (code != 200) SuppressUntil = 0f;")),
], T("status_through_local",
     R(FA, (), _HOLDIF, 'string holdStatus = a.Status;\n^if (a.Hold == 1 && (holdStatus == "assembling" || holdStatus == "admitted"))'),
     note="deviation: the status through a local of a name no gate reads"),
    extra=XT)


# ---------------------------------------------------------------- K8, K33, K43

_PIN = "if (Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0)"
row("K8", N("k08"), [
    M("pin_skips_gated", "K8 pin condition",
      R(PL, (), (_PIN + " { if (gatedRoom", _PIN),
        "if ((Plugin.Pending2v2Slot >= 0 || Plugin.PendingOvtSlot >= 0 || Plugin.PendingFfaSlot >= 0) && !gatedRoom)")),
], T("inner_if_braced",
     R(PL, (), "if (gatedRoom && FfaAssembly.IsAdmissionRoom(roomName)) "
               "StartCoroutine(FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine)); else StartCoroutine(Auto2v2SpawnCoroutine());",
       "if (gatedRoom && FfaAssembly.IsAdmissionRoom(roomName))\n^{\n^^StartCoroutine(FfaAssembly.GatedSpawn(Auto2v2SpawnCoroutine));"
       "\n^}\n^else\n^{\n^^StartCoroutine(Auto2v2SpawnCoroutine());\n^}"),
     note="deviation: the inner if/else braced"),
    extra=XT)

_SG = ("private static void SpawnGate(",)
_MS = ("internal static bool MaySpawn(",)
_DG = ("internal static bool DigestGate(",)
_MAYRET = "return snapshot && digestOk && seedMatch && scaleMatch && !callInCame;"
_DGIF = "if (p.IsMaster || !p.Kept)"
row("K33", N("k33", "k08", "k45"), [
    M("opens_at_top", "K33 gate opens", A(FA, _SG, "if (_spawnOpenRoom == room) return;", "_spawnOpenRoom = room;")),
    M("opens_while_admitting", "K33 gate opens",
      R(FA, _SG, ('if (a.Status == "admitting") { SpawnHoldLine(a);', "SpawnHoldLine(a);"),
        "_spawnOpenRoom = room; SpawnHoldLine(a);")),
    M("opens_on_client_age", "K33 gate opens",
      A(FA, _SG, "if (_spawnOpenRoom == room) return;", "if (_lastAgeMs >= 40000) _spawnOpenRoom = room;"),
      note="a client-side age estimate opens the gate"),
    M("late_opens", "K33 gate opens", R(FA, _SG, "_spawnLateRoom = room;", "_spawnOpenRoom = room;")),
    M("may_spawn_no_digest", "K45 harness",
      R(FLR, _MS, _MAYRET, "return snapshot && seedMatch && scaleMatch && !callInCame;"), nodes=N("k45")),
    M("may_spawn_no_scale", "K45 harness",
      R(FLR, _MS, _MAYRET, "return snapshot && digestOk && seedMatch && !callInCame;"), nodes=N("k45")),
    M("snapshot_opens_arrival", "K45 harness",
      R(FLR, _MS, "return startOk || stateAInWindow;", "return startOk || stateAInWindow || snapshot;"), nodes=N("k45")),
    M("digest_master_counts", "K45 harness", R(FLR, _DG, _DGIF, "if (!p.Kept)"), nodes=N("k45")),
    M("digest_unkept_counts", "K45 harness", R(FLR, _DG, _DGIF, "if (p.IsMaster)"), nodes=N("k45")),
], T("peers_reversed_and_admission_local",
     R(FLR, _DG, "for (int i = 0; i < peers.Count; i++)", "for (int i = peers.Count - 1; i >= 0; i--)"),
     R(FA, (), "if (IsAdmissionRoom(room) && postEntry) SpawnGate(a);",
       "bool admission = IsAdmissionRoom(room);\n^if (admission && postEntry) SpawnGate(a);")),
    extra=XT)

row("K43", N("k33"), [
    M("no_window_test", "K43 window test", R(FA, _SG, "&& openMs <= SpawnOpenS * 1000f", "")),
    M("client_clock", "K43 open ms",
      R(FA, _SG, "int openMs = a.ServerAgeMs - a.SpawnOkAgeMs;",
        "int openMs = (int)(Time.realtimeSinceStartup * 1000f) - a.SpawnOkAgeMs;")),
    M("judged_every_answer", "K43 judged once", R(FA, _SG, "if (a.SpawnOk == 1 && !_spawnFirstA)", "if (a.SpawnOk == 1)")),
], T("conjuncts_swapped",
     R(FA, _SG, "a.SpawnOkAgeMs >= 0 && a.ServerAgeMs >= 0", "a.ServerAgeMs >= 0 && a.SpawnOkAgeMs >= 0"),
     note="deviation: the window test's two age conjuncts swapped"),
    extra=XT)


# ---------------------------------------------------------------- K10, N11, WP2, K13

def _k10():
    """One mutant per labelled FfaLeaveQueue call in plugin/: its label
    argument (always the last) dropped."""
    muts = []
    for f in sorted(os.listdir(os.path.join(ROOT, "plugin"))):
        rel = "plugin/" + f
        if not f.endswith(".cs") or "FfaLeaveQueue(" not in _src(rel):
            continue
        t = _src(rel)
        try:
            m = _mask(rel)
        except _Miss as exc:
            muts.append(M("unlabel_" + f[:-3], "K10 labelled", _stale(rel, str(exc))))
            continue
        for mm in re.finditer(r"(?<![A-Za-z0-9_])FfaLeaveQueue\s*\(", m):
            op = mm.end() - 1
            cp = _close(m, op)
            lp = m.find("label:", op, cp) if cp > 0 else -1
            if lp < 0:
                continue
            head = m[op + 1:lp].rstrip()
            start = op + len(head) if head.endswith(",") else lp
            line = t.count("\n", 0, mm.start()) + 1
            muts.append(M("unlabel_%s_%d" % (f[:-3], line), "K10 labelled", _at(rel, start, cp, ""),
                          note="the label argument dropped at %s:%d" % (f, line)))
    if len(muts) != 18:
        muts.append(M("site_count", "K10 labelled", _stale(AC, "%d labelled call(s), want 18" % len(muts))))
    return muts


row("K10", N("k10"), _k10(), T("named_cause_first",
    R(FM, (), 'ApiClient.FfaLeaveQueue("fresh_cancel", label: "fresh_cancel");',
      'ApiClient.FfaLeaveQueue(label: "fresh_cancel", cause: "fresh_cancel");')),
    extra=XT)

row("N11", N("k10"), [
    M("label_renamed", "N11 label census",
      R(AC, (), 'FfaLeaveQueue(label: "stale_lobby");', 'FfaLeaveQueue(label: "stale_lobby_x");')),
    M("fresh_cancel_cause_empty", "N11 site table",
      R(FM, (), 'ApiClient.FfaLeaveQueue("fresh_cancel", label: "fresh_cancel");',
        'ApiClient.FfaLeaveQueue("", label: "fresh_cancel");')),
    M("server_label_dropped", "WP2 server labels",
      R(MAINPY, (), '"wrong_region", "start_timeout", "join_timeout",', '"wrong_region", "start_timeout",')),
], T("end_sitting_call_split",
     R(FM, (), 'ApiClient.FfaLeaveQueue(ApiClient.FfaInRoomExitCause(), label: "end_sitting");',
       'ApiClient.FfaLeaveQueue(ApiClient.FfaInRoomExitCause(),\n^^label: "end_sitting");')),
    extra=XT)

row("WP2", N("k10"), [
    M("client_literal_drift", "N11 label census",
      R(NUI, (), 'ApiClient.FfaLeaveQueue(label: "menu_leave");', 'ApiClient.FfaLeaveQueue(label: "menu_leaves");')),
], T("named_cause_seat_abandon",
     R(GSW, (), 'ApiClient.FfaLeaveQueue("seat_abandon", label: "seat_abandon");',
       'ApiClient.FfaLeaveQueue(label: "seat_abandon", cause: "seat_abandon");')),
    extra=XT)

_FLQ = ("public static void FfaLeaveQueue(",)
row("K13", N("k13"), [
    M("label_into_cause", "K13 label once",
      R(AC, _FLQ, "if (string.IsNullOrEmpty(cause)) cause = _ffaLeaveCause;", "cause = label;")),
], T("label_part_local",
     R(AC, _FLQ, 'url += "&label=" + UnityWebRequest.EscapeURL(label);',
       'string labelPart = "&label=" + UnityWebRequest.EscapeURL(label);\n^url += labelPart;')),
    extra=XT)


# ---------------------------------------------------------------- K11, WP1, K46

row("K11", N("k11"), [
    M("advertise_without_adm", "K11 advertise",
      R(FA, (), 'if (asm && adm) return CapsToken + "," + AdmCapsToken;', 'if (asm) return CapsToken + "," + AdmCapsToken;')),
    M("asm_always", "K11 asm source", R(FA, (), "bool asm = AsmCapable();", "bool asm = true;")),
    M("quarantine_without_damage", "K11 quarantine attached",
      R(FLE, (), "&& RegisterPostfixAttached && damage;", "&& RegisterPostfixAttached;")),
    M("production_on", "K11 production flag",
      R(FA, (), "internal const bool AdmProductionEnabled = false;", "internal const bool AdmProductionEnabled = true;")),
    M("adm_without_flag", "K11 adm terms",
      R(FA, (), "bool adm = asm && AdmissionListComplete() && CallInHoldAttached && AdvertiseAdm;",
        "bool adm = asm && AdmissionListComplete() && CallInHoldAttached;")),
], T("caps_try_braced",
     R(AC, (), "try { capsList = FfaAssembly.Caps(); } catch { }",
       "try\n^{\n^^capsList = FfaAssembly.Caps();\n^}\n^catch { }"),
     note="deviation: the caps read's try braced across lines"),
    extra=XT)

row("WP1", N("k11"), [
    M("token_drift", "WP1 tokens",
      R(FA, (), 'internal const string CapsToken = "ffa_asm1";', 'internal const string CapsToken = "ffa_asm2";')),
], T("modifier_order",
     R(FA, (), 'internal const string CapsToken = "ffa_asm1";', 'const internal string CapsToken = "ffa_asm1";')),
    extra=XT)

_G3GROUP = '''<PropertyGroup Condition="'$(Configuration)' == 'G3'">'''
_RELGROUP = ('''<PropertyGroup Condition="'$(Configuration)' == 'Release'">'''
             "\n^  <DefineConstants>$(DefineConstants);SCR_G3</DefineConstants>\n^</PropertyGroup>")
_MARKERS = ('#if THUNDERSTORE\n            "SCR_BUILD_VARIANT=THUNDERSTORE";\n'
            '#elif SCR_G3\n            "SCR_BUILD_VARIANT=G3";')
_MARKERS_SWAPPED = ('#if SCR_G3\n            "SCR_BUILD_VARIANT=G3";\n'
                    '#elif THUNDERSTORE\n            "SCR_BUILD_VARIANT=THUNDERSTORE";')
row("K46", N("k46"), [
    M("utf16_from_byte_0", "K46 odd offset",
      R(GATE, (), "$realHay = $latin1.GetString($bytes)", "$realHay = [System.Text.Encoding]::Unicode.GetString($bytes)")),
    M("void_disabled", "K46 void", R(GATE, (), "if ($controls -ne 2) {", "if ($false) {")),
    M("release_defines_g3", "K46 SCR_G3 only in G3", B(CSPROJ, (), _G3GROUP, _RELGROUP)),
    M("g3_marker_standalone", "K46 marker", RR(AC, '"SCR_BUILD_VARIANT=G3";', '"SCR_BUILD_VARIANT=STANDALONE";')),
    M("copy_includes_g3", "K46 copy exclusion", R(CSPROJ, (), "and '$(Configuration)' != 'G3'", "")),
], T("renamed_control_and_swapped_branches", E(GATE, "$okOdd", "$oddOk", 2), RR(AC, _MARKERS, _MARKERS_SWAPPED)),
    extra=XT)


# ---------------------------------------------------------------- K12, K14, K15, K16

_DFR = ("IEnumerator DelayedFfaRoomJoin(",)
_ICR = ("inCompetitiveRoomNow = PhotonNetwork.InRoom && !PhotonNetwork.OfflineMode && "
        "CompetitiveRoomDetect.IsCompetitiveRoom() && (allowedRoom == null || PhotonNetwork.CurrentRoom?.Name != allowedRoom);")
_ALLOW = "&& (allowedRoom == null || PhotonNetwork.CurrentRoom?.Name != allowedRoom)"
row("K12", N("k12"), [
    M("exemption_dropped", "K12 exemption", R(AC, _DFR, (_ICR, _ALLOW), "")),
    M("exemption_null_only", "K12 exemption", R(AC, _DFR, (_ICR, _ALLOW), "&& allowedRoom == null")),
    M("reform_passes_null", "K12 allowed room",
      R(AC, (), "reform ? FfaAssembly.MovedOutOf : null, reform, gated));", "null, reform, gated));")),
], T("assignment_one_line", R(AC, _DFR, _ICR, _ICR), note="deviation: the abort assignment joined onto one line"),
    extra=XT)

row("K14", N("k14"), [
    M("ordinal_off_by_one", "K14 ordinal",
      R(PL, (), _LEAVEPOST, 'if (JoinGate) FfaAssembly.PostAttempt(joinAttempts, "leave");')),
    M("leave_post_dropped", "K14 two posts", D(PL, (), _LEAVEPOST)),
], T("break_after_gate", R(PL, (), _LEAVEPOST, 'if (JoinGate)\n^^FfaAssembly.PostAttempt(joinAttempts + 1, "leave");'),
     note="deviation: the leave POST's statement on its own line"),
    extra=XT)

_OWR = ("private static void OnWrongRegion(",)
row("K15", N("k15"), [
    M("rejoin_at_leave", "K15 leave only",
      A(FA, _OWR, "try { PhotonNetwork.LeaveRoom(); }", "Plugin.SetPendingRoom(room, RegionRearmRegion, gated: true);")),
], T("target_tuple",
     R(FA, ("internal static void AfterHandoffExit(",), "Plugin.SetPendingRoom(room, region, gated: true);",
       "var target = (Room: room, Region: region);\n^Plugin.SetPendingRoom(target.Room, target.Region, gated: true);")),
    extra=XT)

row("K16", N("k15"), [
    M("move_writes_handoff", "K16 handoff writers",
      A(FA, ("internal static void Move(",), "MovedOutOf = old;", "HandoffRoom = old;")),
], T("handoff_split", R(FA, _OWR, "HandoffRoom = room;", "HandoffRoom =\n^^room;"),
     note="deviation: the region handoff's assignment split across lines"),
    extra=XT)


# ---------------------------------------------------------------- K17, K25

_PF = 'if (!ok && IsFfaQueuePolling && JoinTimeline.Throttle("poll_fail", 10f))'
_NOTICE = "try { FfaAssembly.OnPollNotice(resp); } catch { }"
_DROP = 'if (!IsFfaQueuePolling) { FfaPollDrop("polling", resp); return; }'
row("K17", N("k17"), [
    M("gate_on_lobby", "K17 poll_fail gate",
      R(AC, (), _PF, 'if (!ok && !string.IsNullOrEmpty(ActiveFfaLobbyId) && JoinTimeline.Throttle("poll_fail", 10f))')),
], T("condition_split", R(AC, (), _PF, 'if (!ok && IsFfaQueuePolling\n^^&& JoinTimeline.Throttle("poll_fail", 10f))'),
     note="deviation: the poll_fail condition split across lines"),
    extra=XT)

row("K25", N("k17"), [
    M("notice_after_discard", "K25 notice position", MV(AC, (), _NOTICE, (_NOTICE + " " + _DROP, _DROP))),
    M("notice_clears_any_lobby", "K25 notice guard",
      D(FA, ("internal static void OnNotice(",),
        "if (lobby == ApiClient.ActiveFfaLobbyId || lobby == ApiClient.OpenFfaLobbyId)")),
], T("notice_try_braced", R(AC, (), _NOTICE, "try\n^{\n^^FfaAssembly.OnPollNotice(resp);\n^}\n^catch { }"),
     note="deviation: the notice read's try braced across lines"),
    extra=XT)


# ---------------------------------------------------------------- K18, K27, K35

_RF = ('string reformedFrom = ExtractJsonString(resp, "reformed_from"); '
       'if (!string.IsNullOrEmpty(reformedFrom) && reformedFrom == ActiveFfaLobbyId) '
       '{ FfaAssembly.Move(resp, Time.realtimeSinceStartup); if (!_ffaLeaveIntent) return; }')
_SEEN = ('JoinTimeline.Seen(ExtractJsonString(resp, "lobby_id"), '
         '"src=poll adm=" + (ExtractJsonInt(resp, "admission") == 1 ? "1" : "0"));')
_RESEND = ("FfaAssembly.ReceiptLockSeen(resp); if (FfaAssembly.ResendRelease()) return;",
           "if (FfaAssembly.ResendRelease()) return;")
row("K18", N("k18"), [
    M("reform_after_decline", "K18 move before decline", MV(AC, (), _RF, "if (busyCasual)", after=False)),
], T("reformed_from_assigned",
     R(AC, (), 'string reformedFrom = ExtractJsonString(resp, "reformed_from");',
       'string reformedFrom = null;\n^reformedFrom = ExtractJsonString(resp, "reformed_from");'),
     note="deviation: the re-form id declared, then assigned"),
    extra=XT)

row("K27", N("k18"), [
    M("seen_dropped", "K27 pre-arm first", D(AC, (), _SEEN)),
    M("seen_after_release", "K27 pre-arm first", MV(AC, (), _SEEN, _RESEND)),
], T("seen_args_split",
     R(AC, (), _SEEN, 'JoinTimeline.Seen(\n^^ExtractJsonString(resp, "lobby_id"),\n'
                      '^^"src=poll adm=" + (ExtractJsonInt(resp, "admission") == 1 ? "1" : "0"));')),
    extra=XT)

row("K35", N("k18"), [
    M("decline_spares_admissible", "K35 decline kept",
      R(AC, (), "if (busyInRoom && !busyCasual)", 'if (busyInRoom && !busyCasual && ExtractJsonInt(resp, "admissible") != 1)')),
    M("flag_misread", "K35 flag",
      R(AC, (), 'bool admissibleSeat = ExtractJsonInt(resp, "admissible") == 1;',
        'bool admissibleSeat = ExtractJsonInt(resp, "admission") == 1;')),
], T("refusal_condition_split", R(AC, (), "if (busyInRoom && !busyCasual)", "if (busyInRoom\n^^&& !busyCasual)"),
     note="deviation: the decline condition split across lines"),
    extra=XT)


# ---------------------------------------------------------------- K21, K22, K41

_RUN = ("internal sealed class Barrier", "internal IEnumerator Run(")
_HSG = "if (HoldsStartGrant(_room)) break;"
row("K21", N("k21"), [
    M("admitting_grants", "K21 grant only own start",
      R(FA, (), ('case "admitting": try { FfaLateEntry.FenceMaster(); } catch { }', 'case "admitting":'),
        'case "admitting":\n^^_grantRoom = room;')),
    M("hint_passes", "K21 no hint", R(FA, _RUN, _HSG, "if (HoldsStartGrant(_room) || HintSaysStarted(_room)) break;")),
    M("age_passes", "K21 pass", R(FA, _RUN, _HSG, "if (HoldsStartGrant(_room) || LatestAgeMs >= StartEarlyMs) break;")),
    M("lease_early_exit", "K21 exits", R(FA, _RUN, "if (now >= StartLeaseUntilRt)", "if (now >= StartLeaseUntilRt - 2f)")),
], T("grant_through_local", R(FA, _RUN, _HSG, "bool granted = HoldsStartGrant(_room);\n^if (granted) break;"),
     note="deviation: the grant test through a local"),
    extra=XT)

row("K22", N("k21"), [
    M("sent_once", "K22 cadence",
      R(FA, _RUN, "if (!_startInFlight && now - _startSentRt >= period)",
        "if (!_startInFlight && now - _startSentRt >= period && _startSentRt < 0f)")),
    M("period_one", "K22 cadence", R(FA, _RUN, "float period = LatestIsAssemblingPending0() ? 2f : 5f;", "float period = 1f;")),
    M("reads_start_answer", "K22 cadence",
      R(FA, ("private static bool LatestIsAssemblingPending0(",), "var a = _latest;", "var a = _startLatest;")),
], T("start_body_local",
     R(FA, ("private static void SendStart(",), 'Post("connect", "start", lobby, ConnectBody("start", null), (ok, code, resp) =>',
       'string body = ConnectBody("start", null);\n^Post("connect", "start", lobby, body, (ok, code, resp) =>'),
     note="deviation: the start body through a local"),
    extra=XT)

row("K41", N("k21"), [
    M("every_answer_renews", "K41 lease writers", R(FA, (), "if (IsRenewing(a.Status))", "if (true)")),
    M("excluded_renews", "K41 renewing",
      R(FA, ("private static bool IsRenewing(",), '|| status == "start_ok" || status == "admitted_late";',
        '|| status == "start_ok" || status == "admitted_late" || status == "excluded";')),
    M("game_clock", "K41 realtime", R(FA, _RUN, "float t0 = Time.realtimeSinceStartup;", "float t0 = Time.time;")),
    M("hold_writes_load_gate", "K41 lease writers",
      R(FA, ("private static void HoldScene(",), "StartLeaseUntilRt = Time.realtimeSinceStartup + StartHoldS;",
        "_loadGateUntilRt = Time.realtimeSinceStartup + StartHoldS;")),
    M("no_step_3", "K41 step 3", R(FA, _RUN, "while (!FfaLateEntry.MasterKept())", "while (false)")),
    M("grant_clock_restarts", "K41 grant clock",
      R(FA, (), ("_grantLate = false; if (_grantRt <= 0f) _grantRt = a.Rt;", "if (_grantRt <= 0f) _grantRt = a.Rt;"),
        "_grantRt = a.Rt;")),
], T("waited_local",
     R(FA, ("private static void StartGrantLine(",), "int wait = (int)((now - t0) * 1000f);",
       "float waited = now - t0;\n^int wait = (int)(waited * 1000f);"),
     note="deviation: the barrier's wait through a local"),
    extra=XT)


# ---------------------------------------------------------------- K23

row("K23", N("k23"), [
    M("release_default_timeout", "K23 timeout 4", R(FA, _SR, "}, timeout: PostTimeout);", "});")),
    M("flag_cleared_outside", "K23 single flight", A(FA, _SR, "}, timeout: PostTimeout);", "_releaseInFlight = false;")),
], T("named_arguments",
     ED(FA, _SR, ("r", _RELURL, 'ApiClient.AsmPost(timeout: PostTimeout, url: ApiClient.BaseUrl + "/api/v1/ffa/lobby/" + lobby'
                                ' + "/release", json: json, callback: (ok, resp) =>'),
        ("r", "}, timeout: PostTimeout);", "});"))),
    extra=XT)


# ---------------------------------------------------------------- K28, K48, WP9

_CB = ("internal static string CensusBody(",)
_PRESENT = "foreach (var a in RoomActors.PresentNonSpectators())"
row("K28", N("k28"), [
    M("empty_s_dropped", "K28 empty s kept",
      A(FA, _CB, 'string s = RoomActors.SteamIdOf(a) ?? "";', "if (string.IsNullOrEmpty(s)) continue;")),
    M("b_from_local_actor", "K28 entry",
      R(FA, _CB, "int b = bodies.Contains(an) ? 1 : 0;", "int b = an == PhotonNetwork.LocalPlayer.ActorNumber ? 1 : 0;")),
    M("player_list", "K48 census list", R(FA, _CB, _PRESENT, "foreach (var a in PhotonNetwork.PlayerList)")),
], T("bodies_for_loop",
     R(FA, _CB, "foreach (var p in PlayerManager.instance.players) {",
       "for (int pi = 0; pi < PlayerManager.instance.players.Count; pi++)\n^{\n^^var p = PlayerManager.instance.players[pi];")),
    extra=XT)

row("K48", N("k28"), [
    M("fighter_view", "K48 census list", R(FA, _CB, _PRESENT, "foreach (var a in RoomActors.ActiveFighters())")),
], T("present_local",
     R(FA, _CB, _PRESENT, "var present = RoomActors.PresentNonSpectators();\n^foreach (var a in present)")),
    extra=XT)

row("WP9", N("k28"), [
    M("key_drift", "WP9 census keys", R(FA, _CB, r'.Append(",\"k\":")', r'.Append(",\"kk\":")')),
], T("append_chain_split", R(FA, _CB, ".Append(I(k)).Append('}');", ".Append(I(k))\n^.Append('}');")),
    extra=XT)


# ---------------------------------------------------------------- K29, K30, K31

_OA = ("internal static void OnArrived(",)
_JW = ("IEnumerator JoinWhenMasterReady(",)
_MR = ('JoinTimeline.Step("master_ready", "frames=" + '
       'waitedFrames.ToString(System.Globalization.CultureInfo.InvariantCulture) + " exit=" + exitKind);')
_UPD = ("class QueueRoomJoiner", "void Update(")
row("K29", N("k29"), [
    M("arrived_body_first", "K29 repair first",
      A(FA, _OA, 'ApplyLockConfig("arrived");', 'string early = ConnectBody("arrived", "");')),
    M("no_republish", "K29 repair first",
      R(FA, _OA, "republished = PhotonNetwork.LocalPlayer.SetCustomProperties(StagedPrejoin);", "republished = false;")),
], T("uid_check_local",
     R(FA, _OA, 'if (props != null && props.ContainsKey("u_id")) uid = props["u_id"] as string ?? "";',
       'bool hasUid = props != null && props.ContainsKey("u_id");\n^if (hasUid) uid = props["u_id"] as string ?? "";')),
    extra=XT)

row("K30", N("k29"), [
    M("master_ready_conditional", "K30 unconditional", B(PL, _JW, _MR, "if (waitedFrames > 0)")),
], T("detail_local",
     R(PL, _JW, _MR, 'string readyDetail = "frames=" + '
                     'waitedFrames.ToString(System.Globalization.CultureInfo.InvariantCulture) + " exit=" + exitKind;'
                     '\n^JoinTimeline.Step("master_ready", readyDetail);')),
    extra=XT)

row("K31", N("k29"), [
    M("tick_after_idle", "K31 tick first", MV(PL, _UPD, "FfaAssembly.Tick();", "joinAttempts = 0; return; }")),
], T("tick_split", R(PL, _UPD, "FfaAssembly.Tick();", "FfaAssembly\n^^.Tick();")), extra=XT)


# ---------------------------------------------------------------- K32, K34

row("K32", N("k32"), [
    M("admitting_disarms", "K32 disarm statuses",
      R(FA, (), ('|| a.Status == "excluded") JoinDeadlineRt = 0f;', '"excluded")'), '"excluded" || a.Status == "admitting")')),
    M("joiner_disarms", "K32 disarm sites", A(PL, (), 'JoinTimeline.Step("in_ranked_room",', "FfaAssembly.JoinDeadlineRt = 0f;")),
    M("arm_capped", "K32 arm",
      R(FA, (), "ArmDeadline(now + l.AdmitLeftMs / 1000f + 10f, lobby);",
        "ArmDeadline(Math.Min(now + l.AdmitLeftMs / 1000f + 10f, now + JoinCapS), lobby);")),
    M("no_rederivation", "K32 re-derivation",
      D(FA, (), 'else if (a.AdmitLeftMs >= 0 && a.Status != "reformed") JoinDeadlineRt = a.Rt + a.AdmitLeftMs / 1000f + 10f;')),
], T("deadline_local",
     R(FA, ("private static void ArmDeadline(",), "JoinDeadlineRt = at;", "float deadline = at;\n^JoinDeadlineRt = deadline;"),
     note="deviation: the armed deadline through a local"),
    extra=XT)

_LATCH = "if (FfaMode.GameStartedInRoom || FfaLateEntry.GameRunningFor(photonRoomId)) rankedRoomEverFull = true;"
_RUNNING = "FfaLateEntry.GameRunningFor(photonRoomId)"
row("K34", N("k34"), [
    M("bodies_latch", "K34 gated latch", R(GSW, _POLL, (_LATCH, _RUNNING + ")"), _RUNNING + " || bodies >= fullAt)")),
    M("grant_latch", "K34 gated latch",
      R(GSW, _POLL, (_LATCH, _RUNNING + ")"), _RUNNING + " || FfaAssembly.HoldsStartGrant(photonRoomId))")),
    M("no_started_term", "K34 gated latch", R(GSW, _POLL, (_LATCH, "FfaMode.GameStartedInRoom ||"), "")),
    M("sitting_latch", "K34 gated latch", R(GSW, _POLL, (_LATCH, _RUNNING), "FfaAssembly.SittingStarted()")),
], T("latch_split",
     R(GSW, _POLL, _LATCH, "if (FfaMode.GameStartedInRoom\n^^|| FfaLateEntry.GameRunningFor(photonRoomId)) rankedRoomEverFull = true;")),
    extra=XT)


# ---------------------------------------------------------------- K36, K37

_LG = ("internal static bool LoadGate(",)
row("K36", N("k36"), [
    M("hint_passes_load", "K36 no hint",
      B(FA, _LG, 'HoldScene(room, sceneName); NoteTrigger(room, "load_hold"); return false;',
        'if (FfaLateEntry.RoomProp(PropAsmHint) == "1") return true;')),
    M("replay_by_rpc", "K36 local replay",
      R(FA, ("private static void ReplayHeld(",), "try { MapManager.instance.RPCA_LoadLevel(held); }",
        'try { MapManager.instance.GetComponent<PhotonView>().RPC("RPCA_LoadLevel", RpcTarget.All, held); }')),
    M("held_returns_true", "K36 held", R(FA, _LG, ('NoteTrigger(room, "load_hold"); return false;', "return false;"), "return true;")),
    M("age_grants_load", "K36 no age grant",
      R(FA, ("internal static bool HoldsStartGrant(",), "return !string.IsNullOrEmpty(room) && room == _grantRoom;",
        "return !string.IsNullOrEmpty(room) && room == _grantRoom || LatestAgeMs >= StartEarlyMs;")),
], T("scene_local",
     R(FA, _LG, 'HoldScene(room, sceneName); NoteTrigger(room, "load_hold");',
       'string scene = sceneName;\n^HoldScene(room, scene);\n^NoteTrigger(room, "load_hold");')),
    extra=XT)

row("K37", N("k37"), [
    M("any_body_counts", "K37 roster bodies", R(FA, (), "&& roster.Contains(p.data.view.OwnerActorNr)", "")),
    M("uid_bodies", "K37 roster bodies",
      R(FA, (), "roster.Contains(p.data.view.OwnerActorNr)", 'p.data.view.Owner.CustomProperties.ContainsKey("u_id")')),
    M("every_start_n", "K37 once",
      R(FA, (), "if (_forceStarted.Contains(room) || a.StartN < 3) return;", "if (_forceStarted.Contains(room)) return;")),
], T("roster_local",
     R(FA, (), "foreach (var e in a.Roster) roster.Add(e.Actor);", "var entries = a.Roster;\n^foreach (var e in entries) roster.Add(e.Actor);"),
     note="deviation: the roster through a local"),
    extra=XT)


# ---------------------------------------------------------------- K38

_MB = ("internal static IEnumerator MasterBoundary(",)
_CALLIN = ("Raise(EVT_CALLIN, new object[] { stamp.Lobby8, g, k, n, stamp.Chain, result }, "
           "new RaiseEventOptions { Receivers = ReceiverGroup.Others });")
_STAMPFENCE = ("FfaLateRules.MasterStampDecision(proposed, nStar, ackComplete, PointEpoch, out result, out n, out apply); "
               "if (!MasterMaySend()) yield break;", "if (!MasterMaySend()) yield break;")
_REFUSED = ('JoinTimeline.Step("epoch_refused", "why=" + why + " n=" + I(p.N) + " applied=" + I(EpochApplied) '
            '+ " sender=" + I(e.Sender)); return;', "return;")
_LGU = ("private static void LateGiveUp(",)
_OP = ("private static void OnProposal(",)
_PROPOSE = "FfaLateRules.MayPropose(nStar, PointEpoch, selfKindS)"
row("K38", N("k38"), [
    M("boundary_after_callin", "K38 call sites",
      MV(FM, _DSG, "if (FfaLateEntry.MasterMaySend()) yield return FfaLateEntry.MasterBoundary();",
         'catch (Exception ex) { Plugin.Log.LogError($"[FFA] CallInNewMap(start): {ex.Message}"); }')),
    M("ack_skipped", "K38 stamp",
      R(FLE, _MB, "ackComplete = FfaLateRules.AckComplete(barrier, PresentActors(), _acks, proposal, self, out missing);",
        "ackComplete = true; missing = new List<int>();")),
    M("fence_after_raise", "K38 stamp", MV(FLE, _MB, _STAMPFENCE, _CALLIN)),
    M("refusal_acks", "K38 ack", D(FLE, _OP, _REFUSED)),
    M("late_any_kind", "K38 late request",
      R(FLE, ("internal static void OnLateRequest(",), "if (e.Actor == sender && e.Kind == 'l')", "if (e.Actor == sender)")),
    M("unlisted_answered", "K38 late request",
      D(FLE, _MB, "if (!FfaLateRules.ListedIn(actor, Record, Record != null ? Record.N : 0)) continue;")),
    M("propose_any_kind", "K38 proposal", R(FLE, _MB, _PROPOSE, "FfaLateRules.MayPropose(nStar, PointEpoch, true)")),
    M("propose_above_applied", "K38 proposal", R(FLE, _MB, _PROPOSE, "FfaLateRules.MayPropose(nStar, EpochApplied, selfKindS)")),
    M("third_load_stays", "K38 third load exit", D(FLE, _LGU, 'FfaAssembly.Exit("join_timeout");')),
    M("third_load_plain_leave", "K38 third load exit",
      R(FLE, _LGU, 'FfaAssembly.Exit("join_timeout");', 'ApiClient.FfaLeaveQueue(label: "join_timeout");')),
], T("proposal_fields_local",
     R(FLE, _OP, "var p = new FfaLateRules.Proposal { Lobby8 = S(a, 0), N = N(a, 1, -1), Chain = S(a, 2),",
       "string lobby8 = S(a, 0), chain = S(a, 2);\n^var p = new FfaLateRules.Proposal\n^{\n^^Lobby8 = lobby8, N = N(a, 1, -1), Chain = chain,"),
     note="deviation: the proposal's fields through locals (the evidence's twin hoists the snapshot's)"),
    extra=XT)


# ---------------------------------------------------------------- K39, K40

_TRF = ("bool TryReportFfaMatch(",)
_LIS = ("internal static bool LateInSitting(",)
_LIG = ("internal static bool LaggedInGame(",)
_SELF = "bool selfBarred = FfaLateEntry.LateInSitting(ownActor) || FfaLateEntry.LaggedInGame(ownActor, reportGame);"
_LAGCALL = "FfaLateRules.LagNames(CrOf(ActorByNumber(actor), PropLag), Lobby8, g, 0)"
row("K39", N("k39"), [
    M("own_late_needs_game", "K39 local records",
      R(FLE, _LIS, "if (actor == OwnActor()) return !string.IsNullOrEmpty(AdmittedLateLobby);",
        "if (actor == OwnActor()) return !string.IsNullOrEmpty(AdmittedLateLobby) && FfaMode.GameNumber > 0;")),
    M("late_any_lobby", "K39 late lobby",
      R(FLE, _LIS, "return !string.IsNullOrEmpty(v) && v == Lobby8;", "return !string.IsNullOrEmpty(v);")),
    M("fallback_unbarred", "K39 election",
      R(GSW, _TRF, "if (lowest == null && !selfBarred) lowest = localSteamId;", "if (lowest == null) lowest = localSteamId;")),
    M("barred_by_property", "K39 election",
      R(GSW, _TRF, _SELF, "bool selfBarred = PhotonNetwork.LocalPlayer.CustomProperties.ContainsKey(FfaLateEntry.PropLate);")),
    M("election_ignores_lag", "K39 election",
      R(GSW, _TRF, "a => FfaLateEntry.LaggedInGame(a, reportGame), a => FfaLateEntry.LateInSitting(a));",
        "a => false, a => FfaLateEntry.LateInSitting(a));")),
    M("lag_any_game", "K39 lag lobby",
      R(FLE, _LIG, _LAGCALL, "FfaLateRules.LagNames(CrOf(ActorByNumber(actor), PropLag), Lobby8, -1, 0)")),
    M("self_lag_unbarred", "K39 election", R(GSW, _TRF, _SELF, "bool selfBarred = FfaLateEntry.LateInSitting(ownActor);")),
], T("lag_prop_local",
     R(FLE, _LIG, "return " + _LAGCALL + ";",
       "string lagProp = CrOf(ActorByNumber(actor), PropLag);\n^return FfaLateRules.LagNames(lagProp, Lobby8, g, 0);")),
    extra=XT)

_NPL = ("void NotifyPlayerLeftRoom(",)
row("K40", N("k39"), [
    M("ghost_not_absent", "K40 ghosts",
      R(GSW, _TRF, "leftEarly = true, absent = true, fps = 0,", "leftEarly = true, fps = 0,")),
    M("present_ghosted", "K40 ghosts",
      R(GSW, _TRF, "if (presentSteams.Contains(gm.steam_id) || FfaMode.Leavers.ContainsKey(gm.steam_id)) continue;",
        "if (FfaMode.Leavers.ContainsKey(gm.steam_id)) continue;")),
    M("relay_unfiltered", "K40 relay",
      R(GSW, _NPL, "if (!FfaLateEntry.IsQuarantinedActor(p.ActorNumber)) FfaMode.RecordLeaver(luSid, name, luTeam);",
        "if (true) FfaMode.RecordLeaver(luSid, name, luTeam);")),
], T("ghost_local_and_kept_relay",
     ED(GSW, _TRF,
        ("r", ("entries.Add(new ApiClient.FfaReportPlayer { steamId = gm.steam_id,", "entries.Add(new ApiClient.FfaReportPlayer"),
         "var ghost = new ApiClient.FfaReportPlayer"),
        ("r", ('damageDealt = 0, }); Plugin.Log.LogInfo("[FFA-REPORT] ghost slot="', "});"), "};\n^entries.Add(ghost);")),
     R(GSW, _NPL, "if (!FfaLateEntry.IsQuarantinedActor(p.ActorNumber))", "if (FfaLateEntry.IsKeptActor(p.ActorNumber))")),
    extra=XT)


# ---------------------------------------------------------------- K42

_FENCE_SITES = [("switch", PL, ("class Cr2v2DiagCallbacks", "void OnMasterClientSwitched(")),
                ("grant", FLE, ("void OnGrantedChanged(",)),
                ("answer", FA, ("void HandleAnswer(",)),
                ("gate", FA, ("void OnGateChanged(",)),
                ("keep", FLE, ("void AfterPair(",))]


def _k42():
    """Per site, one mutant per view call (renamed off the view); per sender
    and per fence site, every fence read renamed; the three map-authority
    conjuncts; FenceTarget; each receiver's names and refusal polarity; the
    fighter count's gated path."""
    muts = []

    def add(mid, tag, fn, note=""):
        try:
            muts.append(M(mid, tag, fn(), note=note))
        except _Miss as exc:
            muts.append(M(mid, tag, _stale(FA, str(exc)), note=note))

    seen = set()
    for label, f, sigs, names, want in st.K42_SITES:
        rel = "plugin/" + f
        slug = _slug(label)
        try:
            occ = _occ(rel, _span(rel, sigs), names)
            if len(occ) != want:
                raise _Miss("%d call(s) in %s, want %d" % (len(occ), label, want))
        except _Miss as exc:
            muts.append(M("site_" + slug, "K42 per-site view", _stale(rel, str(exc))))
            continue
        for j, p in enumerate(occ):
            if (rel, p) in seen:
                continue
            seen.add((rel, p))
            muts.append(M("site_%s_%d" % (slug, j + 1), "K42 per-site view", _at(rel, p, p, "Raw"),
                          note="view call %d of %d in %s renamed" % (j + 1, want, label)))
    for f, sigs in st.K42_SENDERS:
        rel = "plugin/" + f
        slug = re.findall(r"\w+", sigs[-1])[-1]
        add("sender_" + slug, "K42 sender fence",
            lambda rel=rel, sigs=sigs: _ins_all(rel, _occ(rel, _span(rel, sigs), "MasterMaySend"), "Raw"))
    for cls in ("Spectator_NoMapAuthority_Load_Patch", "Spectator_NoMapAuthority_CallIn_Patch",
                "Spectator_NoMapAuthority_CallInBare_Patch"):
        muts.append(M("authority_" + cls.split("_")[2].lower(), "K42 map authority",
                      R(SP, ("class " + cls, "Prefix("), "&& !FfaLateEntry.MasterFenced()", "")))
    for name, rel, sigs in _FENCE_SITES:
        add("fence_" + name, "K42 fence sites",
            lambda rel=rel, sigs=sigs: _ins_all(rel, _occ(rel, _span(rel, sigs), "FenceMaster"), "Raw"))
    muts.append(M("fence_target_unread", "K42 fence target",
                  R(FLE, ("void FenceTick(",), "FfaLateRules.FenceTarget(", "FfaLateRules.FenceTargetRaw(")))
    for label, f, sigs, names in st.K42_RECEIVERS:
        rel = "plugin/" + f
        for n in names:
            ident = n.replace("\\", "").split(".")[-1]
            add("receiver_%s_%s" % (_slug(label), ident), "K42 receivers",
                lambda rel=rel, sigs=sigs, n=n: _ins_all(rel, _occ(rel, _span(rel, sigs), n), "Raw"))
        if "RefusedAuthority" not in names:
            continue
        try:
            sp = _span(rel, sigs)
            m = _mask(rel)
            ra = [mm.start() for mm in re.compile(r"(?<![A-Za-z0-9_])RefusedAuthority\s*\(").finditer(m, sp[0], sp[1])]
            nots = [mm.start() for mm in re.compile(r"!\s*(?:FfaLateEntry\.)?MasterKept\s*\(\s*\)").finditer(m, sp[0], sp[1])]
            before = [p for p in nots if ra and p < ra[0]]
            if not before:
                raise _Miss("no negated MasterKept() before RefusedAuthority in " + label)
            muts.append(M("polarity_" + _slug(label), "K42 receivers", _at(rel, before[-1], before[-1] + 1, ""),
                          note="the refusal's guard un-negated"))
        except _Miss as exc:
            muts.append(M("polarity_" + _slug(label), "K42 receivers", _stale(rel, str(exc))))
    muts.append(M("fighter_count_no_gated_path", "K42 fighter count fast path",
                  D(RA, ("int ActiveFighterCount(",), "if (FfaLateEntry.GatedRunning) return ActiveFighters().Length;")))
    return muts


row("K42", N("k42"), _k42(), T("kept_filter_local",
    R(RA, ("PhotonPlayer[] ActiveFighters(",), "if (filter && !FfaLateEntry.IsKeptActor(actor.ActorNumber)) continue;",
      "bool keptActor = !filter || FfaLateEntry.IsKeptActor(actor.ActorNumber);\n^if (!keptActor) continue;")),
    extra=XT)

_READS_OLD = (r'def reads(rx, span, own): if own: span = re.sub(r"\b" + re.escape(own) + r"\s*\(", " ", span) '
              r'return rx.search(span) is not None')
_READS_NEW = "\n".join([
    "def reads(rx, body, own):",
    "    if own:",
    r'        body = re.sub(r"\b" + re.escape(own) + r"\s*\(", " ", body)',
    "    return rx.search(body) is not None"])
row("K42c", N("k42red", "k42clean"), [
    M("alias_needs_current_room", "K42 census alias",
      A(CEN, (), 'rx = needs.get(ckey) or (VIEW if cls == "V" else FENCE)',
        'if key[3] in ("RoomPlayers", "GetPlayer") and "CurrentRoom" not in ctx[key[0]][0][max(0, o - 40):o]:\n^    continue')),
    M("member_read_dominates", "K42 census branch",
      B(CEN, (), "for at in (o, o + 1):", "if hit(clean[lo:hi]):\n^    return True")),
], T("reads_body_name", R(CEN, (), _READS_OLD, _READS_NEW)), extra=XT)


# ---------------------------------------------------------------- K44, K45

_BD = ("internal static string BoundaryDigest(",)
row("K44", N("k44", "k45"), [
    M("kills_in_digest", "K44 digest fields",
      B(FLR, _BD, """.Append(':').Append(string.Join(",", s.Cards""",
        ".Append(':').Append(s.Kills.ToString(CultureInfo.InvariantCulture))")),
    M("any_grant_publishes", "K44 kept publisher",
      R(FLE, ("void DigestTick(",), "if (!(HoldsGrant && Kept(own))) return;", "if (!HoldsGrant) return;")),
    M("gate_needs_no_peer", "K45 harness",
      R(FLR, _DG, "return agree >= 1 && !differ && g >= lateGame;", "return !differ && g >= lateGame;"), nodes=N("k45")),
    M("gate_master_counts", "K45 harness", R(FLR, _DG, _DGIF, "if (!p.Kept)"), nodes=N("k45")),
    M("gate_unkept_counts", "K45 harness", R(FLR, _DG, _DGIF, "if (p.IsMaster)"), nodes=N("k45")),
    M("gate_differ_ignored", "K45 harness", R(FLR, _DG, "{ differ = true; continue; }", "continue;"), nodes=N("k45")),
], T("digest_input_local",
     R(FLR, _BD, "return Hex16(Fnv64(sb.ToString()));", "string input = sb.ToString();\n^return Hex16(Fnv64(input));")),
    extra=XT)

row("K45", N("k45"), [
    M("harness_never_exact", "K45 harness", R(HM, (), "bool exact = red.SequenceEqual(want);", "bool exact = false;")),
    M("model_converges_down_always", "K45 boundary model",
      R(BM, (), 'if master_post < c0 and rule in ("v10", "no_converge_down"):', "if master_post < c0:")),
], T("boundary_terms_swapped",
     R(FLR, (), "if (p.G != ownG || (kKnown && p.K != ownK))", "if ((kKnown && p.K != ownK) || p.G != ownG)")),
    extra=XT)


# ---------------------------------------------------------------- K47, K49

row("K47", N("k47"), [
    M("match_start_reads_fighters", "K47 ungated only", D(GSW, ("private static void OnMatchStarted(",), "if (lockIds == null)")),
    M("ffa_start_reads_fighters", "K47 ungated only", D(GSW, ("public static void OnFfaMatchStarted(",), "if (lockIds == null)")),
    M("first_freeze_fighters", "K47 three freezes",
      R(GSW, (), "RoomActors.FreezeFighterRoster(lockIds ?? sids);", "RoomActors.FreezeFighterRoster(sids);")),
], T("gated_local",
     R(GSW, ("private static List<string> GatedFreezeIds(",), "if (!FfaAssembly.IsGatedRoom(room)) return null;",
       "bool gated = FfaAssembly.IsGatedRoom(room);\n^if (!gated) return null;"),
     note="deviation: the gated test through a local"),
    extra=XT)

row("K49", N("k49"), [
    M("noexc_rule_off", "K49 plant noexc",
      R(CLM, (), ("for name, rx in RULES: if rx.search(sent):", "if rx.search(sent):"),
        'if name != "NOEXC" and rx.search(sent):')),
    M("fig_rule_off", "K49 plant fig",
      R(CLM, (), "if FIG.search(sent) and not COMPLETED.search(sent):",
        "if False and FIG.search(sent) and not COMPLETED.search(sent):")),
], T("fig_terms_swapped",
     R(CLM, (), "if FIG.search(sent) and not COMPLETED.search(sent):", "if not COMPLETED.search(sent) and FIG.search(sent):")),
    extra=XT)


# ---------------------------------------------------------------- WP3, WP4, WP8

row("WP3", N("wp3"), [
    M("server_key_drift", "WP3 server writes", R(MAINPY, (), '"fence_s": ASM_FENCE_S,', '"fence_sec": ASM_FENCE_S,')),
], T("window_key_next_line", R(FA, (), 'FenceS = Window(m, "fence_s", 3f);', 'FenceS = Window(m,\n^^"fence_s", 3f);')),
    extra=XT)

row("WP4", N("wp4"), [
    M("answer_key_drift", "WP4 server writes", R(MAINPY, (), 'ans["spawn_ok_age_ms"] =', 'ans["spawn_ok_age"] =')),
], T("plan_dict_one_key_per_line",
     R(MAINPY, (), 'return {"start_n": start_n, "roster": roster, "admissible": admissible, "late": late, "granted": granted}',
       'return {"start_n": start_n,\n^        "roster": roster,\n^        "admissible": admissible,\n'
       '^        "late": late,\n^        "granted": granted}')),
    extra=XT)

row("WP8", N("wp4"), [
    M("deadline_literal_drift", "WP8 deadline",
      R(MAINPY, (), 'content={"error": "asm_deadline"}', 'content={"error": "asm_deadline_x"}')),
], T("deadline_dict_split", R(MAINPY, (), 'content={"error": "asm_deadline"}', 'content={\n^    "error": "asm_deadline"}')),
    extra=XT)


# ---------------------------------------------------------------- WP5, WP6

row("WP5", N("wp5"), [
    M("lag_literal_inline", "WP5 one literal each",
      R(FLE, _LIG, "CrOf(ActorByNumber(actor), PropLag)", 'CrOf(ActorByNumber(actor), "cr_lag")')),
    M("lag_value_separator", "WP5 formats",
      R(FLR, ("internal static string LagValue(",), 'return lobby8 + ":" + g.ToString(CultureInfo.InvariantCulture) + ":"',
        'return lobby8 + "/" + g.ToString(CultureInfo.InvariantCulture) + ":"')),
    M("lag_parts_two", "WP5 formats",
      R(FLR, (), "if (parts.Length != 3 || parts[0] != lobby8", "if (parts.Length != 2 || parts[0] != lobby8")),
], T("modifier_order", R(FLE, (), 'internal const string PropLag = "cr_lag";', 'const internal string PropLag = "cr_lag";')),
    extra=XT)

_TAIL = ("var tail = new object[] { LateMarker, ptot, kl, g, level, new string[0], (int)seed, PointK, PointEpoch, "
         "AppliedScaleTag() };")
row("WP6", N("wp6"), [
    M("tail_order_swapped", "WP6 append order", R(FLE, (), _TAIL, _TAIL.replace("ptot, kl", "kl, ptot"))),
], T("tail_split",
     R(FLE, (), _TAIL, "var tail = new object[] { LateMarker, ptot, kl, g, level,\n"
                       "^^new string[0], (int)seed, PointK, PointEpoch, AppliedScaleTag() };")),
    extra=XT)


# ---------------------------------------------------------------- WP7, WP10, WP11, WP12

row("WP7", N("wp7", "wp7c"), [
    M("ready_receiver_braced", "WP11 receivers",
      R(FLE, (), "case EVT_READY: OnReady(e); break;", "case EVT_READY: { OnReady(e); break; }")),
    M("ready_parse_shifted", "WP11 parse order", R(FLE, ("void OnReady(",), "int n = N(a, 1, -1);", "int n = N(a, 2, -1);")),
    M("client_hex_upper", "WP7 client chain",
      R(FLR, (), 'return h.ToString("x16", CultureInfo.InvariantCulture);', 'return h.ToString("X16", CultureInfo.InvariantCulture);'),
      nodes=N("wp7c")),
    M("client_offset_basis", "WP7 client chain",
      R(FLR, (), "ulong h = 0xcbf29ce484222325UL;", "ulong h = 0xcbf29ce484222324UL;"), nodes=N("wp7c")),
    M("server_separator", "WP7 server chain",
      R(MAINPY, (), 'f"{prev}:{lobby8}:{n}:{slot}:{actor}"', 'f"{prev}|{lobby8}:{n}:{slot}:{actor}"'), nodes=N("wp7c")),
], T("modifier_order", R(FLE, (), "internal const byte EVT_READY = 53;", "const internal byte EVT_READY = 53;")),
    extra=XT)

row("WP10", N("wp7"), [
    M("scale_receiver_literal", "WP11 receivers",
      R(FLE, (), "case EVT_SCALE: OnScale(e); break;", "case 59: OnScale(e); break;")),
], T("scale_payload_split",
     R(FLE, (), "return Raise(EVT_SCALE, new object[] { Lobby8, g, k, count },",
       "return Raise(EVT_SCALE, new object[] { Lobby8, g,\n^^k, count },"),
     note="deviation: the scale payload split across lines"),
    extra=XT)

row("WP11", N("wp7"), [
    M("result_literal_drift", "WP11 result literals",
      R(FLR, ("internal static string ValidateStamp(",), 'bool raises = s.Result == "commit" ||',
        'bool raises = s.Result == "commited" ||')),
    M("lag_step_renamed", "WP11 lag step", R(FLE, (), 'FfaAssembly.Receipt(lobby, "lag",', 'FfaAssembly.Receipt(lobby, "lagged",')),
    M("stamp_parse_shifted", "WP11 parse order",
      R(FLE, ("void OnStamp(",), "Chain = S(a, 4), Result = S(a, 5),", "Chain = S(a, 4), Result = S(a, 4),")),
], T("callin_payload_split",
     R(FLE, _MB, "Raise(EVT_CALLIN, new object[] { stamp.Lobby8, g, k, n, stamp.Chain, result },",
       "Raise(EVT_CALLIN, new object[] { stamp.Lobby8, g, k,\n^^n, stamp.Chain, result },"),
     note="deviation: the call-in payload split across lines"),
    extra=XT)

_JSON = r'string json = "{\"steam_id\":\"" + Esc(SteamId()) + "\",\"why\":\"" + why + "\"}";'
row("WP12", N("wp12"), [
    M("path_drift", "WP12 path", R(FA, _SR, '+ lobby + "/release", json,', '+ lobby + "/releases", json,')),
    M("why_drift", "WP12 why values", R(FA, _EXIT, 'bool release = why == "fence_expired"', 'bool release = why == "fence_expiry"')),
], T("json_split",
     R(FA, _SR, _JSON, r'string json = "{\"steam_id\":\"" + Esc(SteamId())' + "\n^^" + r'+ "\",\"why\":\"" + why + "\"}";')),
    extra=XT)
