"""ft_slice_identity.py: the parse-identity proof of the laptop slice's export rule (ruling R6-A3.11.112 F2).

Usage: python -I -B ft_slice_identity.py <out dir> <list of raw logs> [<list of exported slices>]
       python -I -B ft_slice_identity.py --sets   (prints the seat script's generated closed-set lines)
       python -I -B ft_slice_identity.py --wcount <exported log lines>   (the seat self-test's window-count check)

Each list file names one input per line. A raw log is a whole LogOutput.log (a VM-seat run or a dry fixture); an
exported slice is a log-lines.txt the laptop job printed under the previous selection. For every input it builds
the two exported sections twice:
  - OLD: the substring selection the seat script used before the rule ("=== log lines": every line holding
    "[FRAME-TIME]", the window lines included since ruling R6-A3.11.133 (2); "=== component slice": every other line
    holding a class word);
  - NEW: frame_time_seat.ps1 -SliceOf <input>, the seat script's own selection code;
then runs ft_parse.py on each, alone and as the peer of the first raw log, and compares stdout, stderr and exit code
byte for byte (the old input's path read as the new one's). An exported slice first loses the seat job's own header
lines, by their exact forms, and the count removed is printed (ruling R6-A3.11.113 (2)(c)). Two record refusals
(rc 4, one FT-PARSE REFUSED line each) of a raw input whose reasons differ are identical in rc and listed with both
reasons by input number ((2)(d)); any other difference fails. It also re-derives the generated closed sets (entry, shape, a3k, patch) from the source tables and
refuses when the script's copies differ.

It writes, under <out dir>: identity.txt (one line per input and parse: IDENTICAL or DIFFERENT, with the withheld
counts per class) and corpus-files.txt (the input list, whose md5 identity.txt prints). It prints no line of any
input. Exit 0 when every parse is identical and the sets agree, 1 otherwise, 2 on a usage error.
"""
import glob
import hashlib
import importlib.util
import os
import re
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PS1 = os.path.join(HERE, "frame_time_seat.ps1")
PARSE = os.path.join(HERE, "ft_parse.py")
CLASSES = ["[FRAME-TIME]", "[FPSCAP]", "[COMBAT-PERF]", "[HIT-EVIDENCE]", "[SEAT-EV]", "[HP-POINT-END]", "[SAW-POINT]",
           "[IDENTITY-CLOCK]", "[CARD-EV]", "[COMBAT-EV]", "[PEER-BUILD]", "[BUILD-PROP]", "record queued",
           "record kept for the next launch", "refused", "voided", "Failed to patch", "BepInEx 5."]


def lines_of(path):
    with open(path, "rb") as f:
        t = f.read().decode("utf-8", errors="replace")
    if t.startswith("﻿"):
        t = t[1:]
    return re.split(r"\r?\n", t)


#  the seat job's own header lines, by their exact forms (the previous job's and this one's): the job's output, not
#  lines a mod log call writes, and absent from a raw log (ruling R6-A3.11.113 (2)(c))
JOB_HEADER = re.compile(r"slice class (?:%s): [0-9]+ lines|slice saved: [0-9]+ lines, sha256 [0-9a-f]{64}"
                        r"|component slice: [0-9]+ lines, every saved-slice line without \[FRAME-TIME\]"
                        r"|component slice: [0-9]+ of [0-9]+ saved-slice lines without \[FRAME-TIME\] exported, the rest"
                        r" withheld by class" % "|".join(re.escape(c.strip("[]")) for c in CLASSES))
REFUSAL = re.compile(r"FT-PARSE REFUSED: .*\n?")


def strip_job_headers(lines):
    """the lines of an exported slice without the job's own header lines, and the count removed"""
    kept = [ln for ln in lines if not JOB_HEADER.fullmatch(ln)]
    return kept, len(lines) - len(kept)


def compare(a, b, path_a, path_b):
    """IDENTICAL when rc, stdout and stderr are byte-identical (the old input's path read as the new one's);
    'REASON' when both are the record refusal (rc 4, one FT-PARSE REFUSED line each, stderr identical) whose
    reasons differ (ruling R6-A3.11.113 (2)(d)); DIFFERENT otherwise"""
    oa = (a[1].decode("utf-8", "replace").replace(path_a, path_b), a[2])
    ob = (b[1].decode("utf-8", "replace"), b[2])
    if a[0] == b[0] and oa == ob:
        return "IDENTICAL", None
    if a[0] == b[0] == 4 and oa[1] == ob[1] and REFUSAL.fullmatch(oa[0]) and REFUSAL.fullmatch(ob[0]):
        return "REASON", (oa[0].strip(), ob[0].strip())
    return "DIFFERENT", None


def old_export(lines):
    log, comp = [], []
    for ln in lines:
        if not any(c in ln for c in CLASSES):
            continue
        if "[FRAME-TIME]" in ln:
            # the window lines included: the seat script exports them since ruling R6-A3.11.133 (2)
            log.append(ln)
        else:
            comp.append(ln)
    return "\n".join(["=== log lines"] + log + ["=== component slice"] + comp) + "\n"


def new_export(path):
    p = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", PS1, "-SliceOf", path],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("-SliceOf exit %d: %s" % (p.returncode, p.stderr.decode("utf-8", "replace")[:300]))
    return p.stdout.decode("utf-8").replace("\r\n", "\n")


def parse(args):
    p = subprocess.run([sys.executable, "-I", "-B", PARSE] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=600)
    return p.returncode, p.stdout, p.stderr


def withheld(text):
    return " ".join("%s=%s" % (m.group(1).replace(" ", "_"), m.group(2))
                    for m in re.finditer(r"^withheld (.+) ([0-9]+)$", text, re.M)) or "none"


def derive_sets():
    """the generated closed sets of the seat script, from the source tables: the census entries and shapes
    (gate_specs/entries.py), the A3 rows (gate_specs/a3.py), every class named *Patch, and every path segment of an
    /api/v1/ url in plugin/*.cs (interpolation holes dropped; a segment holding a digit is "{n}" in a route name)"""
    w = os.path.dirname(os.path.dirname(HERE))
    e = runpy.run_path(os.path.join(HERE, "gate_specs", "entries.py"))["ENTRIES"]
    a = runpy.run_path(os.path.join(HERE, "gate_specs", "a3.py"))["A3"]
    src = "".join(open(f, encoding="utf-8-sig", errors="replace").read()
                  for f in sorted(glob.glob(os.path.join(w, "plugin", "*.cs"))))
    hole = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}")
    segs = set()
    for q in re.findall(r"/api/v1/[^\"?\n]*", src):
        for s in hole.sub("", q).split("/"):
            if re.fullmatch(r"[a-z][a-z0-9._-]*", s) and not re.search(r"[0-9]", s):
                segs.add(s)
    return {
        "entry": [n.replace(" ", ":") for c, n, k, s in e],
        "shape": sorted(set(s for c, n, k, s in e)) + ["span.empty"],
        "a3k": [r[0] for r in a],
        "patch": sorted(set(re.findall(r"\bclass ([A-Za-z0-9_]+Patch)\b", src))),
        "seg": sorted(segs),
    }


def sets_agree():
    """the script's generated closed sets equal the ones the source tables give today"""
    want = derive_sets()
    t = open(PS1, encoding="utf-8").read()
    bad = []
    for k, v in want.items():
        m = re.search(r"^    %s +=  ?'([^']*)'$" % k, t, re.M)
        if not m or m.group(1).split(" ") != v:
            bad.append(k)
    return bad


def wcount(path):
    """ft_parse.py's window-count rule (records_missing: per point, as many window lines as its point line's
    windows=) on an exported "=== log lines" section, each line read by ft_parse.parse_line. The section's withheld
    lines are not judged here (ft_parse.read refuses them before any record; the self-test checks them itself).
    Prints "WCOUNT misses <k>" and then each miss of that rule."""
    spec = importlib.util.spec_from_file_location("ft_parse_wcount", PARSE)
    fp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fp)
    recs = [r for r in (fp.parse_line(ln) for ln in lines_of(path)) if r is not None]
    miss = [m for m in fp.records_missing(recs) if WCOUNT_MISS.fullmatch(m)]
    print("WCOUNT misses %d" % len(miss))
    for m in miss:
        print(m)
    return 0


#  the miss records_missing() writes for a point whose window lines differ from its point line's windows=
WCOUNT_MISS = re.compile(r"point \S+: [0-9]+ window lines, the point line counts \S+")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--wcount":
        return wcount(sys.argv[2])
    if sys.argv[1:] == ["--sets"]:
        # the generated lines, as the seat script carries them
        for k, v in derive_sets().items():
            print("    %-6s = '%s'" % (k, " ".join(v)))
        return 0
    if len(sys.argv) not in (3, 4):
        print(__doc__.split("\n\n")[1])
        return 2
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    raw = [x for x in open(sys.argv[2], encoding="utf-8").read().split("\n") if x.strip()]
    sl = [x for x in open(sys.argv[3], encoding="utf-8").read().split("\n") if x.strip()] if len(sys.argv) == 4 else []
    files = ["raw " + x for x in raw] + ["slice " + x for x in sl]
    flist = "\n".join(files) + "\n"
    open(os.path.join(out, "corpus-files.txt"), "w", encoding="utf-8", newline="\n").write(flist)
    rep = ["corpus: %d raw logs, %d exported slices; file list md5 %s"
           % (len(raw), len(sl), hashlib.md5(flist.encode("utf-8")).hexdigest())]
    bad = sets_agree()
    rep.append("generated closed sets: %s" % ("AGREE with the source tables" if not bad else "DIFFER: " + ",".join(bad)))
    ok = not bad
    tmp = os.path.join(out, "tmp")
    os.makedirs(tmp, exist_ok=True)
    peer0 = raw[0] if raw else None
    reasons = []
    for i, f in enumerate(files):
        kind, path = f.split(" ", 1)
        o = os.path.join(tmp, "old-%d.txt" % i)
        n = os.path.join(tmp, "new-%d.txt" % i)
        src = path
        lines = lines_of(path)
        hdr = ""
        if kind == "slice":
            lines, removed = strip_job_headers(lines)
            hdr = "; job header lines removed %d" % removed
            src = os.path.join(tmp, "in-%d.txt" % i)
            open(src, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
        open(o, "w", encoding="utf-8", newline="\n").write(old_export(lines))
        nt = new_export(src)
        open(n, "w", encoding="utf-8", newline="\n").write(nt)
        res = []
        for label, args_o, args_n in (("alone", [o], [n]),
                                      ("as peer", [peer0, o] if peer0 else None, [peer0, n] if peer0 else None)):
            if args_o is None:
                continue
            verdict, why = compare(parse(args_o), parse(args_n), o, n)
            ok = ok and verdict != "DIFFERENT"
            if verdict == "REASON":
                ok = ok and kind == "raw"
                reasons.append("%d %s: old '%s' | new '%s'" % (i, label, why[0].replace(n, "<input>"),
                                                            why[1].replace(n, "<input>")))
                verdict = "IDENTICAL in rc 4, refusal reason differs (listed below)"
            res.append("%s %s" % (label, verdict))
        rep.append("%d %s: parse %s; withheld %s%s" % (i, kind, ", ".join(res), withheld(nt), hdr))
        os.remove(o)
        os.remove(n)
        if src != path:
            os.remove(src)
    os.rmdir(tmp)
    rep.append("refusal reasons that differ (rc 4 under both selections; raw inputs only): %d" % len(reasons))
    rep += ["  " + r for r in reasons]
    rep.append("RESULT %s" % ("PASS: every parse identical in rc and output, the refusal reasons listed aside"
                              if ok else "FAIL"))
    open(os.path.join(out, "identity.txt"), "w", encoding="utf-8", newline="\n").write("\n".join(rep) + "\n")
    print("\n".join(rep))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
