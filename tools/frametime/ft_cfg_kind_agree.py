# ft_cfg_kind_agree.py [--script <frame_time_seat.ps1>]: the AGREEMENT TEST of ruling R6-A3.11.105 (3). The laptop
# makes VR6's by-kind verdict on the mod cfg itself (frame_time_seat.ps1's CfgKind, a PowerShell port of
# ft_cfg_compare.py's rule), because no cfg value leaves the laptop. This test runs ft_cfg_compare.py (beside this
# file, Python, on the VM) and the port (Windows PowerShell 5.1: powershell -NoProfile -File <script> -CfgKindList)
# over ONE fixture corpus of (pre-image, sitting) pairs and wants identical verdicts on every pair:
#   ft_cfg_compare.py exit 0 = RESTORED-KIND, 1 = NOT-RESTORED-KIND, 2 = REFUSED (its line must start with the same
#   word), against the port's "CFG-KIND <n> <verdict>".
# Each pair also declares the verdict the rule must give, so a corpus whose pairs no longer test what they name fails
# too. The corpus base is the self-test's own fixture cfg ($CfgBase in frame_time_seat.ps1); the pairs the self-test
# also runs as cfg mutants are marked "(self-test cfg_<name>)".
# Prints one line per pair, then "AGREEMENT PASS <n> pairs" (exit 0) or "AGREEMENT FAIL: ..." (exit 1); exit 2 when
# a side cannot run. Reads only its own scratch folder, which it removes.
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CMP = os.path.join(HERE, "ft_cfg_compare.py")
script = os.path.join(HERE, "frame_time_seat.ps1")
if len(sys.argv) == 3 and sys.argv[1] == "--script":
    script = sys.argv[2]
elif len(sys.argv) != 1:
    print("usage: ft_cfg_kind_agree.py [--script <frame_time_seat.ps1>]")
    sys.exit(2)

BOM = b"\xef\xbb\xbf"
BASE = [b"## Settings file was created by plugin Competitive Rounds\r\n", b"## Plugin GUID: com.competitiverounds.mod\r\n",
        b"\r\n", b"[Data]\r\n", b"\r\n", b"AutoLogUpload = true\r\n", b"KeyA = 1\r\n", b"KeyB = 2\r\n", b"\r\n",
        b"[Other]\r\n", b"\r\n", b"KeyC = 3\r\n"]


def f(lines, bom=True):
    return (BOM if bom else b"") + b"".join(lines)


def edit(at, drop, add):
    return BASE[:at] + add + BASE[at + drop:]


R, N, X = "RESTORED-KIND", "NOT-RESTORED-KIND", "REFUSED"
B = f(BASE)
CORPUS = [
    # the ruling's pairs
    ("comment_only (self-test cfg_comment)", B, f(edit(12, 0, [b"## a comment line the sitting wrote\r\n"])), R),
    ("value_changed (self-test cfg_value)", B, f(edit(6, 1, [b"KeyA = 9\r\n"])), N),
    ("key_added (self-test cfg_key_added)", B, f(edit(8, 0, [b"KeyD = 4\r\n"])), N),
    ("key_removed (self-test cfg_key_removed)", B, f(edit(7, 1, [])), N),
    ("keys_swapped (self-test cfg_keys_swapped)", B, f(edit(6, 2, [b"KeyB = 2\r\n", b"KeyA = 1\r\n"])), N),
    ("blank_added (self-test cfg_blank_added)", B, f(edit(8, 0, [b"\r\n"])), N),
    ("crlf_to_lf_one_line (self-test cfg_crlf_lf)", B, f(edit(6, 1, [b"KeyA = 1\n"])), N),
    ("bom_removed (self-test cfg_bom_removed)", B, f(BASE, False), N),
    ("section_renamed (self-test cfg_section_renamed)", B, f(edit(9, 1, [b"[Renamed]\r\n"])), N),
    ("non_grammar_line (self-test cfg_non_grammar)", B, f(edit(8, 0, [b"a line of no kind\r\n"])), X),
    # further pairs of the same rule
    ("identical", B, B, N),
    ("comment_changed", B, f(edit(0, 1, [b"## Settings file was rewritten\r\n"])), R),
    ("comment_removed", B, f(edit(1, 1, [])), R),
    ("comment_crlf_to_lf", B, f(edit(0, 1, [b"## Settings file was created by plugin Competitive Rounds\n"])), R),
    ("comment_indented", B, f(edit(12, 0, [b"   # indented\r\n"])), R),
    ("comment_after_tab", B, f(edit(12, 0, [b"\t# after a tab\r\n"])), R),
    ("comment_after_u001f", B, f(edit(12, 0, [b"\x1f# after U+001F\r\n"])), R),
    ("comment_after_u0085", B, f(edit(12, 0, [b"\xc2\x85# after U+0085\r\n"])), R),
    ("comment_after_u00a0", B, f(edit(12, 0, [b"\xc2\xa0# after U+00A0\r\n"])), R),
    ("comment_after_u3000", B, f(edit(12, 0, [b"\xe3\x80\x80# after U+3000\r\n"])), R),
    ("line_after_u180e", B, f(edit(12, 0, [b"\xe1\xa0\x8e# after U+180E\r\n"])), X),
    ("line_after_nul", B, f(edit(12, 0, [b"\x00# after NUL\r\n"])), X),
    ("comment_utf8", B, f(edit(12, 0, [b"# caf\xc3\xa9\r\n"])), R),
    ("comment_lone_cr_then_comment", B, f(edit(12, 0, [b"# a\r# b\r\n"])), R),
    ("comment_lone_cr_then_key", B, f(edit(12, 0, [b"# a\rKeyZ = 1\r\n"])), N),
    ("comment_without_final_terminator", B, f(BASE) + b"# tail", R),
    ("key_without_final_terminator", B, f(BASE[:-1]) + b"KeyC = 3", N),
    ("value_spacing", B, f(edit(6, 1, [b"KeyA =1\r\n"])), N),
    ("value_utf8", B, f(edit(6, 1, [b"KeyA = caf\xc3\xa9\r\n"])), N),
    ("section_spacing", B, f(edit(9, 1, [b"[ Other ]\r\n"])), N),
    ("comment_to_key", f(edit(12, 0, [b"#KeyX = 1\r\n"])), f(edit(12, 0, [b"KeyX = 1\r\n"])), N),
    ("blank_crlf_to_lf", B, f(edit(2, 1, [b"\n"])), N),
    ("bom_added", f(BASE, False), B, N),
    ("bom_removed_key_first", BOM + b"[Data]\r\nKeyA = 1\r\n", b"[Data]\r\nKeyA = 1\r\n", N),
    ("empty_to_comment", b"", b"# x\n", R),
    ("empty_to_bom_only", b"", BOM, N),
    ("non_grammar_in_pre", f(edit(8, 0, [b"a line of no kind\r\n"])), B, X),
    ("invalid_utf8", B, f(edit(12, 0, [b"# \xff\r\n"])), X),
    ("overlong_utf8", B, f(edit(12, 0, [b"# \xc0\xaf\r\n"])), X),
    ("surrogate_utf8", B, f(edit(12, 0, [b"# \xed\xa0\x80\r\n"])), X),
    ("lone_bracket", B, f(edit(12, 0, [b"[\r\n"])), X),
]

tmp = tempfile.mkdtemp(prefix="ft-cfg-kind-agree-")
try:
    lst = []
    for i, (name, a, b, want) in enumerate(CORPUS):
        pa, pb = os.path.join(tmp, "%02d-pre.cfg" % i), os.path.join(tmp, "%02d-sitting.cfg" % i)
        open(pa, "wb").write(a)
        open(pb, "wb").write(b)
        lst.append((pa, pb))
    lf = os.path.join(tmp, "pairs.txt")
    open(lf, "w", encoding="utf-8", newline="\r\n").write("".join("%s\t%s\n" % p for p in lst))
    try:
        p = subprocess.run(["powershell", "-NoProfile", "-File", script, "-CfgKindList", lf], capture_output=True, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as e:
        print("AGREEMENT CANNOT RUN: the port did not run (%s)" % e.__class__.__name__)
        sys.exit(2)
    port = {}
    for ln in p.stdout.decode("utf-8", "replace").replace("\r", "").split("\n"):
        w = ln.split(" ")
        if len(w) == 3 and w[0] == "CFG-KIND" and w[1].isdigit():
            port.setdefault(int(w[1]), []).append(w[2])
    if p.returncode != 0:
        print("AGREEMENT CANNOT RUN: the port exited %d" % p.returncode)
        sys.exit(2)
    names = {0: R, 1: N, 2: X}
    bad, odd = [], []
    for i, (name, a, b, want) in enumerate(CORPUS):
        q = subprocess.run([sys.executable, "-I", CMP, lst[i][0], lst[i][1]], capture_output=True, timeout=60)
        qo = q.stdout.decode("utf-8", "replace").replace("\r", "").strip()
        py = names.get(q.returncode, "EXIT-%d" % q.returncode)
        if not (qo.startswith(py + ":") or qo.startswith(py + " ")) or len(qo.split("\n")) != 1:
            py = "PY-ODD(" + py + ")"
        pv = port.get(i, [])
        pv = pv[0] if len(pv) == 1 else "PORT-LINES-%d" % len(pv)
        agree = py == pv
        if not agree:
            bad.append(name.split(" ")[0])
        if py != want:
            odd.append(name.split(" ")[0])
        print("pair %02d %s: python %s (the rule wants %s), port %s: %s" % (i, name, py, want, pv, "AGREE" if agree else "DISAGREE"))
    if bad or odd:
        print("AGREEMENT FAIL: %d of %d pairs disagree: %s; python not the declared verdict: %s"
              % (len(bad), len(CORPUS), ",".join(bad) or "none", ",".join(odd) or "none"))
        sys.exit(1)
    print("AGREEMENT PASS %d pairs" % len(CORPUS))
    sys.exit(0)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
