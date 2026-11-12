"""test_ft_seat_export.py: frame_time_seat.ps1's export forms against the emitter (ruling R6-A3.11.151 (2) class E).

Every test that exports runs the seat script's REAL export code, frame_time_seat.ps1 -SliceOf <log> (function
SliceExport, the code step 4 runs), in a child PowerShell on a synthetic log in a temp folder:
  (a) LEADS: one line, as the emitter prints it, for every lead of ft_parse.py's FORMS table, the attach line and
      Harmony's patch failure. Every line is exported (a failure line whose last field is free text as its typed head
      and "(not-exported)"), nothing is withheld, and every FORMS lead occurs in the export, its line still a line of
      that lead's FORMS pattern;
  (b) PLANTED: lines outside the forms (a window line with one extra unknown key, at its end or inside it, a fourth wa
      type, a writer type twice or outside the set, free text in a typed field) are withheld and counted, and no planted
      text reaches the export;
  (c) IDENTITY: ft_parse.py prints the same lines, with the same exit code, for the export as for the raw log (a
      refusal's line=<n> read as equal): the every-lead log, and test_ft_parse.py's complete sitting-C and sitting-V
      logs, each line put in the emitter's form (the builders' point and settled lines carry fewer keys than the
      emitter's, and their census lines comp=X). The sitting-V pair (--on) differs by VR1's [FPSCAP] hold line, which
      the export prints after every [FRAME-TIME] line: a strict expected failure that needs a ruling;
  -SelfTest: the script's own self-test prints SELFTEST PASS.
Each mutant is a copy of frame_time_seat.ps1 with one route of the forms changed (the V5 window form only, the writer
types without sock, the earlier point form only, no attach form, no redaction, a redaction that exports the text, wa
loosened, the forms unanchored at the end, the window key check skipped), run the same way; each must fail its named
check. frame_time_seat_v.ps1 holds no form and calls frame_time_seat.ps1, so it inherits them (checked from its text).
Where neither powershell nor pwsh exists the export tests SKIP with that reason.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ft_parse as P             # noqa: E402  (read only: FORMS, PHOTON_ENTRIES, expected_entries)
import test_ft_parse as T        # noqa: E402  (read only: the sitting builders)

PS1 = os.path.join(HERE, "frame_time_seat.ps1")
PS1_V = os.path.join(HERE, "frame_time_seat_v.ps1")
PARSE = os.path.join(HERE, "ft_parse.py")
PS = shutil.which("powershell") or shutil.which("pwsh")
need_ps = pytest.mark.skipif(PS is None, reason="no PowerShell on this seat (neither powershell nor pwsh on PATH): "
                                                "the export code is frame_time_seat.ps1's, so these run where one is")

INFO = "[Info   :Competitive ROUNDS] "
WARN = "[Warning:Competitive ROUNDS] "
ERR = "[Error  :Competitive ROUNDS] "
FT = "[FRAME-TIME] "
RED = "(not-exported)"
MARK = "planted-7d1e"                          # the planted free text's marker: never in any export
FREE = "IOException: %s at planted.example/x y=1" % MARK
ROOM = "ft_0123abcd"

W6 = ("w pt=1.1.1 arm=ON plant=0 partial=0 n=120 sF=21600000 sS=0 sC=1000 sP=1000 maxF=1 medF=1 e4=0,0 e8=0,0 "
      "e16=0,0 gc=0 run=1 pos=1 unit=P13 coin=1 wi=1 f0=0 pred=none prun=0 res=0 gcn=0 cG=0 cW=0 cR=0 cS=0 cE=1000 "
      "q=100,100,100,100,100,100,100,100,100,100 r=0,0,0,0,0,0,0,0,0,0 qn=12,12,12,12,12,12,12,12,12,12 "
      "wu=log:1:2;hash:1:2;recv:2:3;sock:3:4 tok=log:0,0,0,0,0,0,0;hash:0,0,0,0,0,0,0;recv:0,0,0,0,0,0,0;"
      "sock:0,0,0,0,0,0,0 nm=4 cP=0 cX=0 aC=12000000 aW=1000 aR=2000 aS=3000 aP=500 aX=1500 wa=log:400;hash:300;sock:300")
# the reference build's window line (plugin/FtUpload.cs:143: sock:NA:NA; no bytes read)
W6_REF = (W6.replace("sock:3:4", "sock:NA:NA").replace("aC=12000000 aW=1000 aR=2000 aS=3000 aP=500 aX=1500",
                                                        "aC=NA aW=NA aR=NA aS=NA aP=NA aX=NA")
          .replace("wa=log:400;hash:300;sock:300", "wa=log:NA;hash:NA;sock:NA"))
P6 = ("p pt=1.1.1 arm=ON gate=1 pred=none n=480 sF=86400000 sS=0 sC=4000 maxF=1 pn=0 psF=0 psS=0 psC=0 sP=4000 psP=0 "
      "excl=0 plant_mixed=0 windows=4 live_frames=480 missing_end=0 span_g=0 span_gn=0 span_u=0 span_un=0 on_calls=0 "
      "guarded=0 zs=0 zl=1 t0=0 t1=86400000 answer=replay off_g=0 off_gn=0 off_on=0 on_guarded=0 own_split=0 "
      "span_class_overflow=0 gc_read_failures=0 recv_offmain=0 ledger_cycle_miss=0 sock_p95=NA sock_n=0 sock_thr=0 "
      "sock_main=0 ab_back=0 ab_retry=0 heap=50000000")
C5 = "counters g=1 frames=480 missing_end=0 cycle_failures=0 span_depth_violations=0"
S6 = ("settled g=1 seed=1 c_plant=80 W=120 vsync=0 target=-1 freq=10000000 hires=1 f_hat=1000000 gc_incremental=1 "
      "gc_slice_ns=0 f18=A answer=replay armfile=1 force=none clock=1 frames=0 missing_end=0 cycle_failures=0 "
      "span_depth_violations=0")

# (prefix, payload after "[FRAME-TIME] ", redacted): one line per FORMS lead and per form the emitter prints. A
# redacted line's export is its head (the payload up to and including the last ": " before the free text) and RED
LEADS = [
    (INFO, "alloc pin=ok planted=1048600/1048576 empty=0", False),
    (INFO, "alloc pin=differs planted=NA/1048576 empty=NA", False),
    (INFO, "alloc_init why=ok", False),
    (WARN, "alloc_init why=failed:DllNotFoundException", False),
    (INFO, "scope plant asked=2000 got=2010", False),
    (INFO, "scope plant asked=2000 got=NA", False),
    (INFO, "scope census entries=40 wrapped=40", False),
    (WARN, "scope census entries=40 wrapped=38 failed=InvalidOperationException", False),
    (INFO, "nest plant asked=2000 x=2020 e=1990 p=NA", False),
    (INFO, "photon patches n=10 names=" + ",".join(P.PHOTON_ENTRIES), False),
    (INFO, "photon patches n=0 names=", False),
    (INFO, "controls k_mutant=none", False),
    (INFO, "controls k_mutant=k2", False),
    (INFO, "counters g=1 frames=480 missing_end=0 cycle_failures=0 span_depth_violations=0 photon_offmain=0 "
           "span_leave_mismatch=0", False),
    (INFO, C5, False),                                      # the counters line of the lane's earlier builds
    (INFO, "census registered=44 expected=44 missing=0 duplicates=0", False),
    (INFO, "mark cost cyc=50 p90=70 n=1000", False),
    (INFO, "ledger log=1 why=ok types=log,hash,recv,sock", False),
    (WARN, "ledger log=0 why=failed:UnauthorizedAccessException types=log,hash,recv,sock", False),
    (INFO, "clock installed freq=10000000 hires=1 cycles=1", False),
    (INFO, "sitting complete g=16", False),
    (INFO, "build variant=FrameTime", False),
    (INFO, "build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS", False),
    (INFO, "a3 g=1 k=CE_Top cap=64 steady=1 reads_on=10 reads_win=5 writes_on=3", False),
    (INFO, "a3 g=1 ref=NA rows=0", False),
    (INFO, "a3drain g=1 k=CE_Top starts=3 nonempty=2 faults=0", False),
    (INFO, "a3rows registered=38 expected=38 missing=0 duplicates=0", False),
    (INFO, "a3rows registered=0 expected=38 ref=NA", False),
    (INFO, "answer_replay g=1 ticks=4000 result=settled", False),
    (WARN, "answer_replay g=2 ticks=0 result=error_IOException", False),
    (INFO, "answer_replay g=3 ticks=0 result=skipped_next_game", False),
    (INFO, "between g=1 after=ON ticks=2000 calls=4", False),
    (INFO, "between g=1 after= ticks=2000 calls=4", False),
    (INFO, "cal i=1 why=game0 kind=fhat f_hat=1000000 spins=1/1", False),
    (INFO, "cal i=1 why=game0 kind=disp shape=CE_p1 n=100000 u=1000000,1000000 p=1030000,1030000", False),
    (INFO, "cal i=1 why=game0 kind=span shape=span.empty n=100000 u=100000,100000 p=150000,150000", False),
    (INFO, "cal i=1 why=game0 kind=a3 k=CE_Top n=10 u=1,2 p=3,4", False),
    (INFO, "cal i=1 why=game0 kind=a3 k=CE_Top live=1 reads=1 scopes=1 ticks=1 tmax=1 unscoped=0 depth_err=0", False),
    (INFO, "cal i=1 why=game0 kind=a3 k=CE_Top withheld=1", False),
    (WARN, "cal i=1 why=game0 kind=a3 k=CE_Top failed: no calibration", False),
    (WARN, "cal i=1 why=game0 kind=a3 k=CE_Top failed: " + FREE, True),
    (INFO, "cal i=0 why=start kind=entries built=0 own_patches=not-applied", False),
    (INFO, "cal i=-1 why=patches kind=entries built=1 own_owner=com.competitiverounds.mod own_targets=30 entries=44 "
           "errors=0", False),
    (INFO, "cal i=-1 why=patches kind=entries reference=1 built=0", False),
    (WARN, "cal i=-1 why=patches kind=entries failed: the built table holds no patched entry", False),
    (WARN, "cal i=-1 why=patches kind=entries failed: " + FREE, True),
    (WARN, "cal i=2 why=game1 kind=disp shape=CE_p1 failed: InvalidOperationException: CombatEvidence_AttackPatch has "
           "a transpiler", False),
    (WARN, "cal i=2 why=game1 kind=disp shape=CE_p1 failed: " + FREE, True),
    (WARN, "cal i=2 kind=fhat failed: " + FREE, True),
    (INFO, "census g=1 entry=HE-p1:PhotonNetwork.ExecuteRpc comp=HitEvidence shape=HE_p1 on=10 guarded=2 outside=0",
     False),
    (INFO, "disarmed input=complete pt=16.1.1", False),
    (INFO, "flushed g=1 why=next_game", False),
    (INFO, "heavy g=1 op=ce_build live=0 between=7 pick=1 over=1 menu=0 at_call=0 edge=0 off=0", False),
    (INFO, "menu seg=1 pair=0 arm=ON gate=1 level=3 c_plant=0 base_us=16000", False),
    (INFO, "menu_armed segments=200 seg_s=10 settle_s=20 force=none seed=1", False),
    (INFO, "menu_base base_us=16000 seg=0", False),
    (INFO, "menu_done why=complete segs=200 of=200 base_us=16000 cycles=0", False),
    (INFO, "offthread g=1 span_off=0 hash_t0=0 hash_t1=0", False),
    (INFO, "opened g=1 se=1 ce=1 ic=1", False),
    (INFO, P6, False),
    (INFO, P6.split(" off_g=")[0], False),                  # the point line of the lane's earlier builds
    (INFO, "plant c_plant=80 ticks=10 from=1.1.1", False),
    (INFO, "refusals why=quit pairs=0", False),
    (INFO, "refusals why=game3 pairs=1 route:GET_local=2", False),
    (INFO, S6, False),
    (INFO, S6.replace("force=none", "force=none problems=bad-seed,stat"), False),
    (INFO, "spans g=1 comp=CombatEvidence live.in.gated=3/4 live.out.writer=1/2", False),
    (INFO, W6, False),
    (INFO, W6_REF, False),
    (INFO, W6.split(" cP=")[0], False),                     # the window line of the lane's V5 builds
    (INFO, "FT-GATE patched 7 entry points expected=7 excluded=JoinLobby,LoadOrCreateSettings", False),
    (WARN, "FT-GATE patched 6 entry points expected=7 excluded=JoinLobby missing=NCH.OnJoinedRoom (absent),"
           "PhotonNetwork.JoinRoom", False),
    (WARN, "FT-GATE patched 6 entry points expected=7 excluded= missing=" + FREE, True),
    (WARN, "FT-GATE report failed: " + FREE, True),
    (INFO, "FT-ROOM joined offline=0 name=" + ROOM, False),
    (WARN, "FT-ROOM read failed: " + FREE, True),
    (INFO, "armed room=%s region=us" % ROOM, False),
    (WARN, "churn freeze failed: " + FREE, True),
    (INFO, "churn timer frozen room=" + ROOM, False),
    (WARN, "clock refused: player-loop phase missing (EarlyUpdate True, PreLateUpdate False, Update True)", False),
    (INFO, "ended why=complete pt=16.1.1", False),
    (INFO, "ft room options max=2 visible=0 room=" + ROOM, False),
    (WARN, "ft_dll staging failed: " + FREE, True),
    (WARN, "game end failed: " + FREE, True),
    (WARN, "game over failed: " + FREE, True),
    (WARN, "game start failed: " + FREE, True),
    (WARN, "game start failed: menu=1 process", False),
    (INFO, "menu_wait input=in_room", False),
    (INFO, "not armed input=error_NullReferenceException", False),
    (INFO, "not armed input=peer", False),
    (WARN, "opened line failed: " + FREE, True),
    (INFO, "peer known actor=2 ft_dll=0123abcd", False),
    (INFO, "peer unknown actor=2 (no matching ft_dll)", False),
    (WARN, "photon patches report failed: " + FREE, True),
    (INFO, "ranked-check skipped", False),
    (INFO, "ranked-check test hook answered true", False),
    (INFO, "reference collectors not installed: patch classes skipped=12 listed=40", False),
    (INFO, "refused what=route route=GET_local n=1", False),
    (WARN, "rematch answer failed: " + FREE, True),
    (INFO, "rematch held: published ft_rm=2", False),
    (INFO, "rematch mutant: answered Yes at once", False),
    (INFO, "rematch not answered (sitting over)", False),
    (WARN, "rematch publish failed: " + FREE, True),
    (INFO, "rematch timeout g=1 own=1 peer=0", False),
    (INFO, "rematch yes g=1 after 1200 ms", False),
    (WARN, "room call refused op=JoinRoom name=%s n=1" % ROOM, False),
    (INFO, "room name=%s region=us cloud_region=us/*" % ROOM, False),
    (INFO, "self-drive armed: inputs are automated", False),
    (INFO, "self-drive disarmed: escape", False),
    (INFO, "self-drive disarmed: input=not evaluated", False),
    (INFO, "self-drive spawn try=1 master=1 actors=2", False),
    (INFO, "self-drive spawn result created=1 players=2", False),
    (INFO, "self-drive spawn waiting why=peer", False),
    (INFO, "self-drive spawn waiting why=actors actors=1", False),
    (INFO, "self-drive spawn refused why=spectator", False),
    (INFO, "self-drive spawn gave up tries=30", False),
    (WARN, "self-drive join failed: " + FREE, True),
    (INFO, "self-drive join room=%s region=us" % ROOM, False),
    (INFO, "self-drive pick index=1", False),
    (WARN, "self-drive spawn threw: " + FREE, True),
    (WARN, "self-drive spawn tick failed: " + FREE, True),
    (INFO, "staged ft_dll=0123abcd in-room", False),
    (WARN, "start failed: " + FREE, True),
    (INFO, "steam ticket withheld route=GET_local", False),
    # lines no FORMS lead reads at this tip (findings for the parser's owner): the attach line (ruling R6-A3.11.151
    # (3), its emitter in the lane's next commit) and FtCalib.cs:126's failure ("kind=disp entries", a word with no =)
    (INFO, "attach n=3 of=4 missing=FtSockPatch names=FtPhotonEPatch:2/2,FtPhotonXPatch:1/1,FtSockPatch:0/1", False),
    (INFO, "attach n=4 of=4 missing=none names=FtPhotonEPatch:2/2,FtPhotonXPatch:1/1,FtSockPatch:1/1,FtRoute_SendPatch:1/1",
     False),
    (WARN, "cal i=2 kind=disp entries failed: " + FREE, True),
]
# the component slice's line of the class: Harmony's patch failure (plugin/Plugin.cs:1483), redacted
HARMONY = (ERR + "[HARMONY] Failed to patch FtSockPatch: " + FREE, ERR + "[HARMONY] Failed to patch FtSockPatch: " + RED)


def exported(payload, redacted):
    """the export of one sample's payload: itself, or its head up to the free text and RED"""
    if not redacted:
        return payload
    i = payload.index(FREE)
    return payload[:i] + RED


def lead_of(payload):
    """the FORMS rows whose lead the payload starts with and whose pattern it fullmatches"""
    return [(lead, pat) for lead, pat, _ in P.FORMS if payload.startswith(lead) and re.fullmatch(pat, payload)]


def leads_log():
    raw = [pre + FT + pay for pre, pay, _ in LEADS] + [HARMONY[0]]
    log = [pre + FT + exported(pay, red) for pre, pay, red in LEADS]
    return "\n".join(raw) + "\n", log, [HARMONY[1]]


# ---- the planted lines (b): (line, what it plants); each must be withheld

def _w(old, new):
    assert W6.count(old) == 1, old
    return INFO + FT + W6.replace(old, new)


PLANTED_FT = [
    (INFO + FT + W6 + " zz=1", "a window line with one extra unknown key at its end"),
    (_w(" nm=4", " zz=1 nm=4"), "a window line with one extra unknown key inside it"),
    (_w("wa=log:400;hash:300;sock:300", "wa=log:400;hash:300;sock:300;recv:1"), "a fourth wa type"),
    (_w("wa=log:400;hash:300;sock:300", "wa=hash:300;log:400;sock:300"), "the wa types out of order"),
    (_w("wu=log:1:2;", "wu=log:1:2;log:1:2;"), "a writer type twice in wu"),
    (_w("recv:2:3;sock:3:4", "recv:2:3;sock:3:4;gpu:1:1"), "a writer type outside the set"),
    (_w("aC=12000000", "aC=%s" % MARK), "free text in a typed field"),
    (INFO + FT + "ledger log=1 why=ok types=log,hash,recv,sock,%s" % MARK, "a ledger type outside the set"),
    (INFO + FT + "attach n=1 of=1 missing=none names=Ft %s:1/1" % MARK, "a name with a space"),
    (WARN + FT + "alloc_init why=failed:%s" % MARK, "a type name with a hyphen"),
    (INFO + FT + "self-drive %s" % MARK, "a trace of no form"),
    (INFO + FT + P6 + " zz=1", "a point line with one extra unknown key"),
]
PLANTED_COMP = [(INFO + "[SEAT-EV] %s" % MARK, "a component line of no form")]
PLANTED_REDACT = [(WARN + FT + "start failed: " + FREE, WARN + FT + "start failed: " + RED)]


def planted_log():
    return "\n".join([x for x, _ in PLANTED_FT + PLANTED_COMP] + [x for x, _ in PLANTED_REDACT] +
                     [INFO + FT + W6]) + "\n"


# ---- running the export and the parser


def run_export(ps1, log):
    p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1, "-SliceOf", log],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
    out = p.stdout.decode("utf-8", "replace").replace("\r\n", "\n")
    assert p.returncode == 0, "-SliceOf exit %d: %s" % (p.returncode, p.stderr.decode("utf-8", "replace")[:600])
    lines = out.split("\n")
    assert lines[0] == "=== log lines" and lines.count("=== component slice") == 1, out[:600]
    i = lines.index("=== component slice")
    return out, lines[1:i], [x for x in lines[i + 1:] if x != ""]


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def parse(args):
    p = subprocess.run([sys.executable, "-I", "-B", PARSE] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=900)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


# ---- the checks (each returns its failures; empty = pass)


def check_leads(ps1, tmp):
    """(a) every sample exported in its section, nothing withheld, every FORMS lead in the export"""
    raw, want_log, want_comp = leads_log()
    out, log, comp = run_export(ps1, write(os.path.join(tmp, "leads.log"), raw))
    f = []
    for x in want_log:
        if x not in log:
            f.append("not exported under === log lines: %s" % x[:160])
    for x in want_comp:
        if x not in comp:
            f.append("not exported under === component slice: %s" % x[:160])
    f += ["withheld: %s" % x for x in log + comp if x.startswith("withheld ")]
    pays = [x.split(FT, 1)[1] for x in log if FT in x]
    for lead in sorted(set(l for l, _, _ in P.FORMS)):
        if not any(pay.startswith(lead) and lead_of(pay) for pay in pays):
            f.append("the FORMS lead %r does not occur in the export" % lead)
    if MARK in out:
        f.append("the planted free text is in the export")
    return f


def check_planted(ps1, tmp):
    """(b) the planted lines withheld and counted; the redacted line as its head; no planted text exported"""
    out, log, comp = run_export(ps1, write(os.path.join(tmp, "planted.log"), planted_log()))
    f = []
    if MARK in out:
        f.append("planted text exported: %s" % [x[:160] for x in out.split("\n") if MARK in x])
    if "withheld FRAME-TIME %d" % len(PLANTED_FT) not in log:
        f.append("not 'withheld FRAME-TIME %d': %s" % (len(PLANTED_FT), [x for x in log if x.startswith("withheld")]))
    if "withheld SEAT-EV %d" % len(PLANTED_COMP) not in comp:
        f.append("not 'withheld SEAT-EV %d': %s" % (len(PLANTED_COMP), comp))
    for _, want in PLANTED_REDACT:
        if want not in log:
            f.append("the redacted line is not exported as %r" % want)
    if INFO + FT + W6 not in log:
        f.append("the control window line is not exported")
    return f


P_ORDER = ("pt arm gate pred n sF sS sC maxF pn psF psS psC sP psP excl plant_mixed windows live_frames missing_end "
           "span_g span_gn span_u span_un on_calls guarded zs zl t0 t1 answer off_g off_gn off_on on_guarded own_split "
           "span_class_overflow gc_read_failures recv_offmain ledger_cycle_miss sock_p95 sock_n sock_thr sock_main "
           "ab_back ab_retry heap").split()
P_DEFAULT = dict(answer="unmeasured", sock_p95="NA")
S_ORDER = ("g seed c_plant W vsync target freq hires f_hat gc_incremental gc_slice_ns f18 answer armfile force problems "
           "clock frames missing_end cycle_failures span_depth_violations").split()
S_DEFAULT = dict(gc_incremental="1", f18="A", answer="replay", armfile="1", force="none", clock="1")
COMP = dict(HE="HitEvidence", CE="CombatEvidence", SE="SeatEvidence", PT="PointEvidence", IC="IdentityClockEvidence",
            CD="CardDrawEvidence", PB="PeerBuild")


def _rebuild(kind, payload, order, default):
    kv = dict(t.split("=", 1) for t in payload[len(kind) + 1:].split(" "))
    extra = set(kv) - set(order)
    assert not extra, "a key the emitter does not print: %s" % extra
    return kind + " " + " ".join("%s=%s" % (k, kv.get(k, default.get(k, "0"))) for k in order
                                 if k != "problems" or k in kv)


def emitter_form(text):
    """test_ft_parse.py's sitting log with each line in the emitter's form: the point and settled lines rebuilt in the
    emitter's key order (the keys the builder omits at 0, or the default above), the census lines' comp= the entry's
    component; every other line as it is"""
    out = []
    for ln in text.split("\n"):
        pre, sep, pay = ln.partition(FT)
        if sep and pay.startswith("p pt="):
            pay = _rebuild("p", pay, P_ORDER, P_DEFAULT)
        elif sep and pay.startswith("settled g="):
            pay = _rebuild("settled", pay, S_ORDER, S_DEFAULT)
        elif sep and pay.startswith("census g=") and " comp=X " in pay:
            pay = pay.replace(" comp=X ", " comp=%s " % COMP[pay.split(" entry=")[1][:2]])
        out.append(pre + sep + pay)
    return "\n".join(out) + "\n"


LINE_NO = re.compile(r"(?<![A-Za-z_])line=[0-9]+")


def _same(a, b, path_a, path_b):
    """rc, stdout and stderr equal, the raw path read as the export's and a refusal's line=<n> as line=<n> (the export
    starts with its section header and moves the component lines after the [FRAME-TIME] ones, so an input line number
    differs by construction)"""
    ra = lambda s: LINE_NO.sub("line=<n>", s.replace(path_a, path_b))
    rb = lambda s: LINE_NO.sub("line=<n>", s)
    return a[0] == b[0] and ra(a[1]) == rb(b[1]) and ra(a[2]) == rb(b[2])


def check_identity(ps1, tmp, logs=None, on=False):
    """(c) ft_parse.py's output and exit code equal for each raw log and its export (_same); with on, a V log also as a
    pair (--on)"""
    f = []
    if logs is None:
        logs = [("leads", leads_log()[0], False)]
    for name, raw, v in logs:
        rp = write(os.path.join(tmp, name + ".raw.log"), raw)
        out = run_export(ps1, rp)[0]
        xp = write(os.path.join(tmp, name + ".export.log"), out)
        wh = [x for x in out.split("\n") if x.startswith("withheld ")]
        a, b = parse([rp]), parse([xp])
        if not _same(a, b, rp, xp):
            f.append("%s: report differs (raw rc %d, export rc %d; withheld %s): %r / %r"
                     % (name, a[0], b[0], wh, a[1][-400:], b[1][-400:]))
        if v and on:
            a, b = parse(["--on", "a=" + rp, "b=" + rp]), parse(["--on", "a=" + xp, "b=" + xp])
            if not _same(a, b, rp, xp):
                f.append("%s: --on differs (raw rc %d, export rc %d): %r / %r" % (name, a[0], b[0], a[1][-400:],
                                                                                b[1][-400:]))
    return f


def sitting_logs():
    return [("leads", leads_log()[0], False),
            ("sitting-C", emitter_form(T._c_text()), False),
            ("sitting-V", emitter_form(T._v_text()), True)]


# ---- the tests


def test_fixture_covers_every_forms_lead():
    """every FORMS lead has a sample that fullmatches its pattern, and every sample's export is still read by the same
    FORMS row as its raw line (a redacted line keeps its lead); needs no PowerShell"""
    pays = [pay for _, pay, _ in LEADS]
    miss = [lead for lead, pat, _ in P.FORMS if not any(p.startswith(lead) and re.fullmatch(pat, p) for p in pays)]
    assert miss == [], "FORMS leads with no sample: %s" % miss
    for _, pay, red in LEADS:
        rows = lead_of(pay)
        if not rows:
            # the lines the parser reads by no row at this tip: the attach line, FtCalib.cs:126's failure, and the
            # earlier builds' 5-key counters line (FORMS holds the 7-key one)
            known = pay.startswith(("attach ", "cal i=2 kind=disp entries failed: ")) or pay == C5
            assert known, "a sample of no FORMS row: " + pay
            continue
        assert lead_of(exported(pay, red)), "the export of %r is read by no FORMS row" % pay


def test_sitting_logs_in_the_emitter_form():
    """the normalized builder logs keep every line (no line dropped or added) and carry the emitter's p and settled
    keys"""
    for name, raw, _ in sitting_logs()[1:]:
        src = T._c_text() if name == "sitting-C" else T._v_text()
        lines = raw.rstrip("\n").split("\n")
        assert len(lines) == len(src.split("\n")), name
        keys = lambda x: [t.split("=", 1)[0] for t in x.split(FT, 1)[1].split(" ")[1:]]
        p = [keys(x) for x in lines if FT + "p pt=" in x]
        s = [keys(x) for x in lines if FT + "settled g=" in x]
        assert p and s, name
        assert all(k == P_ORDER for k in p), name
        assert all(k == [x for x in S_ORDER if x != "problems"] for k in s), name


@need_ps
def test_every_lead_exported(tmp_path):
    f = check_leads(PS1, str(tmp_path))
    assert f == [], f


@need_ps
def test_planted_lines_withheld(tmp_path):
    f = check_planted(PS1, str(tmp_path))
    assert f == [], f


@need_ps
def test_parse_identity(tmp_path):
    f = check_identity(PS1, str(tmp_path), sitting_logs())
    assert f == [], f


class Vr1Order(AssertionError):
    """the one known difference of (c), raised only when every failure is it"""


VR1_HOLD = "no '[FPSCAP] held by frame-time calibration' line: the hold is not proven reached"


@need_ps
@pytest.mark.xfail(raises=Vr1Order, strict=True,
                   reason="needs a ruling: VR1 (ft_parse.py vr1) reads the [FPSCAP] hold line up to the last settled "
                          "line, and the export prints [FPSCAP] lines under '=== component slice', after every "
                          "[FRAME-TIME] line, so --on on an exported sitting-V log withholds what the raw log passes")
def test_parse_identity_on_v(tmp_path):
    """(c) for the sitting-V log as a pair (--on): differs only by VR1's hold line (Vr1Order); any other difference
    fails this test outright, and its disappearance fails it too (strict)"""
    f = check_identity(PS1, str(tmp_path), [x for x in sitting_logs() if x[2]], on=True)
    if f and all(" --on differs " in x and VR1_HOLD in x for x in f):
        raise Vr1Order(f)
    assert f == [], f


@need_ps
def test_selftest_passes():
    p = subprocess.run([PS, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, "-SelfTest"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=1800)
    out = p.stdout.decode("utf-8", "replace")
    assert p.returncode == 0 and "SELFTEST PASS" in out, out[-3000:] + p.stderr.decode("utf-8", "replace")[-1000:]


def test_seat_v_inherits_the_forms():
    """frame_time_seat_v.ps1 holds no form and no export code of its own and runs frame_time_seat.ps1"""
    with open(PS1_V, encoding="ascii") as f:
        code = [ln for ln in f.read().split("\n") if ln.strip() and not ln.lstrip().startswith("#")]
    text = "\n".join(code)
    for word in ("FormText", "FormSets", "FormPh", "RedactText", "ExportLine", "SliceExport", "[FRAME-TIME]"):
        assert word not in text, word
    assert text.count("Join-Path $PSScriptRoot 'frame_time_seat.ps1'") == 1 and text.count("& $seat") == 1, text


# ---- the mutants: a copy of frame_time_seat.ps1 with one route changed, each failing its named check

def _ps1_text():
    with open(PS1, encoding="ascii") as f:
        return f.read()


MUTANTS = [
    # (name, the check it must fail, "line" to drop the one line holding old, or "text" to replace old by new)
    ("the V5 window form only (V6's dropped)", check_leads, "line",
     "nm=<u> cP=<n> cX=<n> aC=<ina> aW=<ina> aR=<ina> aS=<ina> aP=<ina> aX=<ina> wa=<wa>'", None),
    ("the writer types without sock", check_leads, "text", "wtype    = 'log hash recv sock'", "wtype    = 'log hash recv'"),
    ("the earlier point form only (V6's dropped)", check_leads, "line", "ab_back=<n> ab_retry=<n> heap=<n>'", None),
    ("no attach form", check_leads, "line", "'[FRAME-TIME] attach n=<u> of=<u> missing=<attmissing> names=<attnames>'",
     None),
    ("no redaction", check_leads, "text", "$Redacts = @($RedactText | ForEach-Object { RedactRegex $_ })",
     "$Redacts = @()"),
    ("a redaction that exports the text", check_planted, "text",
     "if ($m.Success) { return $m.Groups['keep'].Value + $RedactToken }", "if ($m.Success) { return $ln }"),
    ("wa loosened", check_planted, "text",
     "$FormPh.wa = 'log:' + $FormPh.una + ';hash:' + $FormPh.una + ';sock:' + $FormPh.una", "$FormPh.wa = '[^ ]*'"),
    ("the forms unanchored at the end", check_planted, "text",
     "Regex(('^' + (FormPattern $t) + '$'),", "Regex(('^' + (FormPattern $t)),"),
    ("the window key check skipped", check_planted, "text",
     "    if ($script:Mutant -eq 'no_wkeys') { return $false }\n", "    return $false\n"),
    ("the V5 window form only, read by the parser", check_identity, "line",
     "nm=<u> cP=<n> cX=<n> aC=<ina> aW=<ina> aR=<ina> aS=<ina> aP=<ina> aX=<ina> wa=<wa>'", None),
]


def mutant_text(how, old, new):
    text = _ps1_text()
    assert text.count(old) == 1, "the anchor %r occurs %d times" % (old, text.count(old))
    if how == "text":
        return text.replace(old, new)
    lines = text.split("\n")
    hit = [i for i, ln in enumerate(lines) if old in ln]
    assert len(hit) == 1
    return "\n".join(lines[:hit[0]] + lines[hit[0] + 1:])


@need_ps
@pytest.mark.parametrize("name,check,how,old,new", MUTANTS, ids=[m[0] for m in MUTANTS])
def test_mutant_fails(tmp_path, name, check, how, old, new):
    ps1 = os.path.join(str(tmp_path), "frame_time_seat.ps1")
    with open(ps1, "w", encoding="ascii", newline="\n") as f:
        f.write(mutant_text(how, old, new))
    fails = check(ps1, str(tmp_path))
    print("MUTANT %s: %s fails: %s" % (name, check.__name__, [x[:200] for x in fails[:3]]))
    assert fails, "mutant %s: %s passed" % (name, check.__name__)


def test_mutant_anchors_hold():
    """every mutant's anchor occurs exactly once in the tracked script (a moved anchor would test nothing)"""
    for name, _, how, old, new in MUTANTS:
        mutant_text(how, old, new)


if __name__ == "__main__":
    # python test_ft_seat_export.py <dir>: each mutant's copy written to <dir>, for the record; and the three fixture
    # logs (raw) beside them
    d = sys.argv[1]
    os.makedirs(d, exist_ok=True)
    for i, (name, check, how, old, new) in enumerate(MUTANTS, 1):
        p = os.path.join(d, "m%02d-frame_time_seat.ps1" % i)
        with open(p, "w", encoding="ascii", newline="\n") as f:
            f.write(mutant_text(how, old, new))
        print("%s -> %s: %s" % (p, check.__name__, name))
    for name, raw, _ in sitting_logs():
        print(write(os.path.join(d, name + ".raw.log"), raw))
    print(write(os.path.join(d, "planted.raw.log"), planted_log()))
