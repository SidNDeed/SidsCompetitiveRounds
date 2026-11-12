"""ft_quiet.py: the quiet protocol's acceptance of one sitting (ruling R6-A3.11.131 E, ruling R6-A3.11.133 (3) MEDIUM 6;
method-v52.md section 6, method-v54.md:187). A breach invalidates the whole sitting.

Usage: python -I -B ft_quiet.py <guest trace> <host trace|-> [--window <utc ms from> <utc ms to>]
       python -I -B ft_quiet.py --guest <guest trace> [--window <utc ms from> <utc ms to>]
         (the guest half alone, printed "QUIET GUEST-HALF <verdict>": never the sitting's verdict)

Inputs: the guest trace ft_quiet_guest.ps1 writes on the VM (one G line a second) and the host trace
ft_quiet_host.sh writes on the Proxmox host (a header naming the vCPU threads and the reserved cores, then one group
of V and C lines a second, X lines around the contention fixture). Both carry utc=<epoch ms>; the window is judged on
that clock, each trace's own intervals on its mono=<ns>. The window is the given one, or by default the span of guest
samples that show the ROUNDS process (calibration through terminal drain). Each trace must cover the window: a sample
before its start, one after its end, and no interval over two seconds from the one to the other.

The rules, every interval of the window:
  guest  non-game cores = total% x ncpu / 100 - ROUNDS cores: p95 <= 0.05 and every interval <= 0.20;
         each physical disk's Avg. Disk Queue Length <= 3; Available MBytes >= 3000; % Committed Bytes In Use <= 85;
         Pages Input/sec, Page Reads/sec, Pages Output/sec: every rolling ten-second integral <= 10, where a sample's
         rate holds over the interval ending at it and ten seconds take from each interval the part they overlap;
  host   each vCPU's delay (d wait / d wall, schedstat): <= 1% over the window and <= 5% every interval; each reserved
         core's non-VM execution (d busy - d run of the vCPUs pinned to it alone) <= 0.05 core; the host intervals
         judged run from the last host sample before the window to the first one after it;
  fixture before the window: the X fixture=start..stop span lasts ten seconds or more and host samples cover it (one
         at or before its start, one at or after its stop, no interval over two seconds between); over those samples
         a vCPU shows run growth and d wait / d wall >= 10%; then at least QUIET_AFTER host intervals between its stop
         and the window, each within the host interval limits (contention removed, quietness regained). Counters
         frozen at zero fail.
REFUSED (no verdict): a trace missing or unreadable, no host evidence, a line of an unknown kind, a missing,
non-numeric or negative field, a trace that does not cover the window, an interval longer than two seconds, utc not increasing,
the ROUNDS identity (pid and start) changing inside the window or not single (rpid=NA), the default window's start or
end not observed (the guest trace starting or ending while ROUNDS runs), a host header that does not name the vCPU
threads and the reserved cores (reserved=- names none), a host sample group that lacks a record for one of them or
holds one twice, no fixture start or stop before the window, a fixture shorter than ten seconds or not covered by host
samples, a schedstat or busy counter going backwards, a reserved core's busy counter not advancing while the vCPUs
pinned to it ran.
Prints one line per rule and "QUIET RESULT PASS|FAIL|REFUSED"; exit 0 PASS, 1 FAIL, 3 REFUSED, 2 usage.
"""
import bisect
import math
import sys

NONGAME_P95 = 0.05
NONGAME_MAX = 0.20
DISKQ_MAX = 3.0
AVAIL_MIN = 3000.0
COMMIT_MAX = 85.0
PAGING_MAX = 10.0          # units in any rolling ten seconds
PAGING_SPAN_NS = 10000000000
GAP_NS = 2000000000        # an interval longer than this refuses
DELAY_ALL = 0.01
DELAY_EACH = 0.05
RESERVED_MAX = 0.05        # cores of non-VM execution per reserved core
FIXTURE_WAIT = 0.10
FIXTURE_MS = 10000         # the contention fixture's shortest span, start mark to stop mark
QUIET_AFTER = 3            # quiet host intervals between the fixture's stop and the window
PAGING = (("pin", "Pages Input/sec"), ("prd", "Page Reads/sec"), ("pout", "Pages Output/sec"))
G_KEYS = ("utc", "mono", "total", "rpid", "rstart", "rcpu", "dq", "avail", "commit", "pin", "prd", "pout")


class Refused(Exception):
    pass


def fields(line):
    out = {}
    for tok in line.split()[1:]:
        k, sep, v = tok.partition("=")
        if not sep:
            raise Refused("a field without '=': %r" % tok)
        out[k] = v
    return out


def num(rec, k, what):
    v = rec.get(k)
    if v is None:
        raise Refused("%s lacks %s" % (what, k))
    try:
        x = float(v)
    except ValueError:
        raise Refused("%s: %s=%r is not a number" % (what, k, v))
    if math.isnan(x) or math.isinf(x):
        raise Refused("%s: %s=%r is not finite" % (what, k, v))
    # every numeric field of both traces is a clock reading, a counter or a rate: none is below zero
    if x < 0:
        raise Refused("%s: %s=%r is negative" % (what, k, v))
    return x


def read_lines(path):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return [ln.rstrip("\r\n") for ln in f if ln.strip()]
    except OSError as e:
        raise Refused("trace %s unreadable: %s" % (path, e))


def read_guest(path):
    lines = read_lines(path)
    if not lines or not lines[0].startswith("QG v1 "):
        raise Refused("guest trace: no 'QG v1' header")
    head = fields(lines[0][3:])
    ncpu = num(head, "ncpu", "guest header")
    if ncpu < 1:
        raise Refused("guest header ncpu=%s" % head.get("ncpu"))
    ndisk = len([d for d in head.get("disks", "").split(",") if d])
    if ndisk < 1:
        raise Refused("guest header names no physical disk")
    recs = []
    for i, ln in enumerate(lines[1:], 2):
        if not ln.startswith("G "):
            raise Refused("guest line %d is not a G record: %r" % (i, ln[:40]))
        r = fields(ln)
        for k in G_KEYS:
            if k not in r:
                raise Refused("guest line %d lacks %s" % (i, k))
        g = {"line": i, "utc": num(r, "utc", "guest line %d" % i), "mono": num(r, "mono", "guest line %d" % i),
             "rpid": r["rpid"], "rstart": r["rstart"]}
        for k in ("total", "avail", "commit", "pin", "prd", "pout"):
            g[k] = num(r, k, "guest line %d" % i)
        # a process's first sample has no interval for its CPU (the sampler writes NA there): kept as None, and
        # refused only if an interval of the window ends on it
        first = not recs or (recs[-1]["rpid"], recs[-1]["rstart"]) != (g["rpid"], g["rstart"])
        g["rcpu"] = None if (r["rcpu"] == "NA" and first and g["rpid"].isdigit()) else num(r, "rcpu", "guest line %d" % i)
        dq = r["dq"].split(",")
        if len(dq) != ndisk:
            raise Refused("guest line %d: %d disk readings for %d disks" % (i, len(dq), ndisk))
        g["dq"] = [num({"dq": q}, "dq", "guest line %d" % i) for q in dq]
        recs.append(g)
    return ncpu, recs


def head_set(head, key, what):
    """the host header's comma list for key; absent, '-', empty or not distinct numbers refuses"""
    v = head.get(key)
    if v is None:
        raise Refused("host header lacks %s= (the %s the capture expects)" % (key, what))
    if v in ("", "-"):
        raise Refused("host header names no %s (%s=%s): the rule that needs them has no evidence" % (what, key, v))
    items = v.split(",")
    if not all(x.isdigit() for x in items) or len(set(items)) != len(items):
        raise Refused("host header %s=%r is not a list of distinct numbers" % (key, v))
    return set(items)


def read_host(path):
    """the host trace's sample groups, sorted by mono, and its fixture marks. Every group holds exactly one V record
    for each vCPU the header names and one C record for each reserved core it names, or the trace refuses."""
    if path == "-":
        raise Refused("no host evidence (missing host evidence refuses, method-v52.md section 6)")
    lines = read_lines(path)
    if not lines or lines[0].split()[:2] != ["QH", "v1"]:
        raise Refused("host trace: no 'QH v1' header")
    head = fields(lines[0][3:])
    want = {"v": head_set(head, "vcpus", "vCPU threads"), "c": head_set(head, "reserved", "reserved cores")}
    groups = {}       # mono -> {"utc", "v": {tid: rec}, "c": {cpu: busy}}
    marks = []
    for i, ln in enumerate(lines[1:], 2):
        kind = ln.split(" ", 1)[0]
        what = "host line %d" % i
        if kind not in ("V", "C", "X"):
            raise Refused("%s is not a V, C or X record: %r" % (what, ln[:40]))
        r = fields(ln)
        utc, mono = num(r, "utc", what), num(r, "mono", what)
        if kind == "X":
            if r.get("fixture") not in ("start", "stop"):
                raise Refused("%s: fixture=%r" % (what, r.get("fixture")))
            marks.append((utc, r["fixture"]))
            continue
        g = groups.setdefault(mono, {"utc": utc, "v": {}, "c": {}})
        if g["utc"] != utc:
            raise Refused("%s: utc %d differs from the utc %d of its group (mono %d)" % (what, utc, g["utc"], mono))
        if kind == "V":
            key = r.get("tid")
            if not key:
                raise Refused("%s lacks tid" % what)
            if r.get("cpus", "NA") in ("", "NA"):
                raise Refused("%s lacks cpus (the vCPU's affinity)" % what)
            rec = {"cpus": r["cpus"], "run": num(r, "run", what), "wait": num(r, "wait", what)}
        else:
            key = r.get("cpu")
            if not key:
                raise Refused("%s lacks cpu" % what)
            rec = num(r, "busy", what)
        slot = g[kind.lower()]
        if key in slot:
            raise Refused("%s: a second %s record for %s in the group at mono %d" % (what, kind, key, mono))
        slot[key] = rec
    out = [dict(mono=m, **groups[m]) for m in sorted(groups)]
    if not out:
        raise Refused("no host evidence: the host trace holds no sample group")
    for a, b in zip(out, out[1:]):
        if b["utc"] <= a["utc"]:
            raise Refused("host trace: utc does not increase with mono at utc %d" % b["utc"])
    names = {"v": "vCPU", "c": "reserved core"}
    for g in out:
        for k in ("v", "c"):
            lack, extra = sorted(want[k] - set(g[k])), sorted(set(g[k]) - want[k])
            if lack:
                raise Refused("host trace: the group at utc %d lacks %s %s that the header names"
                              % (g["utc"], names[k], ",".join(lack)))
            if extra:
                raise Refused("host trace: the group at utc %d holds %s %s that the header does not name"
                              % (g["utc"], names[k], ",".join(extra)))
    return out, marks


def intervals(recs, label):
    """consecutive pairs; an interval over two seconds or a clock that does not advance refuses"""
    out = []
    for a, b in zip(recs, recs[1:]):
        d = b["mono"] - a["mono"]
        if d <= 0 or d > GAP_NS:
            raise Refused("%s: an interval of %.3f s (line %s to %s); gaps over two seconds refuse"
                          % (label, d / 1e9, a.get("line", a["utc"]), b.get("line", b["utc"])))
        out.append((a, b, d))
    return out


def cover(recs, w0, w1, label):
    """the samples that cover the window [w0, w1] (utc): every sample inside it, the last one before w0 and the first
    one after w1. Returns (first index, last index, the intervals between them). Refuses when no sample is inside,
    when the trace does not reach before w0 or after w1, when utc does not increase from the first to the last, or
    when any of those intervals is longer than two seconds."""
    idx = [i for i, r in enumerate(recs) if w0 <= r["utc"] <= w1]
    if not idx:
        raise Refused("%s: no sample inside the window (utc %d to %d)" % (label, w0, w1))
    lo, hi = idx[0] - 1, idx[-1] + 1
    if lo < 0:
        raise Refused("%s does not cover the window's start: no sample before utc %d" % (label, w0))
    if hi >= len(recs):
        raise Refused("%s does not cover the window's end: no sample after utc %d" % (label, w1))
    span = recs[lo:hi + 1]
    for a, b in zip(span, span[1:]):
        if b["utc"] <= a["utc"]:
            raise Refused("%s: utc does not increase at %s" % (label, b.get("line", b["utc"])))
    return lo, hi, intervals(span, label)


def p95(xs):
    s = sorted(xs)
    return s[max(0, int(math.ceil(0.95 * len(s))) - 1)]


def worst_ten_seconds(iv, k):
    """the largest integral of rate k over any ten seconds of mono time. A sample's rate holds over the interval that
    ends at it, so ten seconds take from each interval rate x the part of it they overlap. The integral is linear in
    the ten seconds' position between the positions where their start or their end meets a sample, so its largest
    value is at one of those positions. Kept in rate x ns until the end: whole rates times whole ns stay exact in a
    float below 2**53, so whole-rate traces at the limit read exactly the limit."""
    xs = [iv[0][0]["mono"]] + [b["mono"] for a, b, d in iv]
    rate = [b[k] for a, b, d in iv]
    cum = [0.0]
    for j, (a, b, d) in enumerate(iv):
        cum.append(cum[-1] + rate[j] * d)

    def upto(t):
        if t <= xs[0]:
            return 0.0
        if t >= xs[-1]:
            return cum[-1]
        j = bisect.bisect_right(xs, t) - 1
        return cum[j] + rate[j] * (t - xs[j])
    return max(upto(e) - upto(e - PAGING_SPAN_NS) for e in xs + [x + PAGING_SPAN_NS for x in xs]) / 1e9


def guest_rules(ncpu, recs, w0, w1, out):
    lo, hi, _ = cover(recs, w0, w1, "guest trace")
    win = recs[lo + 1:hi]
    if len(win) < 2:
        raise Refused("guest trace: %d samples in the window" % len(win))
    ids = set((r["rpid"], r["rstart"]) for r in win)
    if len(ids) != 1 or not all(p.isdigit() and s.isdigit() for p, s in ids):
        raise Refused("guest trace: the ROUNDS identity changes inside the window: %s" % sorted(ids))
    iv = intervals(win, "guest trace")
    for a, b, d in iv:
        if b["rcpu"] is None:
            raise Refused("guest line %d: no ROUNDS CPU for the interval ending there" % b["line"])
    ok = True
    ng = [b["total"] * ncpu / 100.0 - b["rcpu"] for a, b, d in iv]
    bad = p95(ng) > NONGAME_P95 or max(ng) > NONGAME_MAX
    out.append("QUIET guest non-game cores %s: p95 %.4f (<= %.2f), max %.4f (<= %.2f), %d intervals"
               % ("FAIL" if bad else "PASS", p95(ng), NONGAME_P95, max(ng), NONGAME_MAX, len(ng)))
    ok = ok and not bad
    dq = max(max(b["dq"]) for a, b, d in iv)
    av = min(b["avail"] for a, b, d in iv)
    cm = max(b["commit"] for a, b, d in iv)
    for name, bad, txt in (("disk queue", dq > DISKQ_MAX, "max %.2f (<= %.0f)" % (dq, DISKQ_MAX)),
                           ("available memory", av < AVAIL_MIN, "min %.0f MiB (>= %.0f)" % (av, AVAIL_MIN)),
                           ("committed", cm > COMMIT_MAX, "max %.1f%% (<= %.0f)" % (cm, COMMIT_MAX))):
        out.append("QUIET guest %s %s: %s" % (name, "FAIL" if bad else "PASS", txt))
        ok = ok and not bad
    for k, name in PAGING:
        worst = worst_ten_seconds(iv, k)
        bad = worst > PAGING_MAX
        out.append("QUIET guest %s %s: worst ten-second integral %.2f (<= %.0f)"
                   % (name, "FAIL" if bad else "PASS", worst, PAGING_MAX))
        ok = ok and not bad
    return ok


def host_iv_limits(a, b, d):
    """one host interval: each vCPU's delay and each reserved core's non-VM cores; returns (worst delay, worst
    reserved, the per-vCPU d wait and d run). Both groups come from read_host, so they hold the same vCPUs and cores."""
    worst_d, waits, runs = 0.0, {}, {}
    for tid in b["v"]:
        dw = b["v"][tid]["wait"] - a["v"][tid]["wait"]
        dr = b["v"][tid]["run"] - a["v"][tid]["run"]
        if dw < 0 or dr < 0:
            raise Refused("host trace: a schedstat counter of vCPU %s goes backwards at utc %d" % (tid, b["utc"]))
        waits[tid], runs[tid] = dw, dr
        worst_d = max(worst_d, dw / d)
    worst_r = 0.0
    for cpu, busy in b["c"].items():
        db = busy - a["c"][cpu]
        vm = sum(runs[t] for t in b["v"] if b["v"][t]["cpus"] == cpu)
        if db < 0:
            raise Refused("host trace: the busy counter of reserved core %s goes backwards at utc %d" % (cpu, b["utc"]))
        if db == 0 and vm > RESERVED_MAX * d:
            raise Refused("host trace: the busy counter of reserved core %s does not advance at utc %d while the vCPUs "
                          "pinned to it ran %.3f core (a frozen counter)" % (cpu, b["utc"], vm / d))
        worst_r = max(worst_r, (db - vm) / d)
    return worst_d, worst_r, waits, runs


def host_rules(span, iv, out):
    """span: the host samples from the last one before the window to the first one after it; iv: its intervals"""
    ok = True
    worst_d = worst_r = 0.0
    tw = {}
    for a, b, d in iv:
        dd, rr, waits, runs = host_iv_limits(a, b, d)
        worst_d, worst_r = max(worst_d, dd), max(worst_r, rr)
        for t in waits:
            tw[t] = tw.get(t, 0) + waits[t]
    wall = span[-1]["mono"] - span[0]["mono"]
    overall = max(tw[t] / wall for t in tw)
    for name, bad, txt in (("vCPU delay every interval", worst_d > DELAY_EACH, "max %.4f (<= %.2f)" % (worst_d, DELAY_EACH)),
                           ("vCPU delay overall", overall > DELAY_ALL, "max %.4f (<= %.2f), %d vCPUs" % (overall, DELAY_ALL, len(tw))),
                           ("reserved-core non-VM", worst_r > RESERVED_MAX, "max %.4f cores (<= %.2f)" % (worst_r, RESERVED_MAX))):
        out.append("QUIET host %s %s: %s" % (name, "FAIL" if bad else "PASS", txt))
        ok = ok and not bad
    return ok


def fixture_rule(groups, marks, w0, ha, out):
    """ha: the index of the last host sample before the window (cover)"""
    starts = [u for u, m in marks if m == "start" and u < w0]
    if not starts:
        raise Refused("no contention fixture before the window: no X fixture=start line before utc %d" % w0)
    s0 = starts[-1]
    stops = [u for u, m in marks if m == "stop" and s0 < u < w0]
    if not stops:
        raise Refused("the contention fixture started at utc %d has no X fixture=stop line before the window" % s0)
    s1 = stops[0]
    if s1 - s0 < FIXTURE_MS:
        raise Refused("the contention fixture lasted %.1f s (utc %d to %d): it must last ten seconds"
                      % ((s1 - s0) / 1000.0, s0, s1))
    upto = [i for i, g in enumerate(groups) if g["utc"] <= s0]
    after = [i for i, g in enumerate(groups) if g["utc"] >= s1]
    if not upto:
        raise Refused("host trace does not cover the contention fixture's start: no sample at or before utc %d" % s0)
    if not after:
        raise Refused("host trace does not cover the contention fixture's stop: no sample at or after utc %d" % s1)
    fa, fb = upto[-1], after[0]
    fx = groups[fa:fb + 1]
    iv = intervals(fx, "host trace (fixture)")
    tw, tr = {}, {}
    for a, b, d in iv:
        _, _, waits, runs = host_iv_limits(a, b, d)
        for t in waits:
            tw[t] = tw.get(t, 0) + waits[t]
            tr[t] = tr.get(t, 0) + runs[t]
    wall = fx[-1]["mono"] - fx[0]["mono"]
    best = max(tw, key=lambda t: (tr[t] > 0, tw[t]))
    grown = tr[best] > 0 and tw[best] / wall >= FIXTURE_WAIT
    # from the first sample at or after the stop to the last one before the window: every interval gap-checked, so
    # the host evidence runs unbroken from the fixture's start to the window's end
    rest = groups[fb:ha + 1]
    quiet = 0
    if len(rest) >= 2:
        for a, b, d in intervals(rest, "host trace (after the fixture)"):
            dd, rr, _, _ = host_iv_limits(a, b, d)
            quiet = quiet + 1 if dd <= DELAY_EACH and rr <= RESERVED_MAX else 0
    regained = quiet >= QUIET_AFTER
    ok = grown and regained
    out.append("QUIET contention fixture %s: %.1f s, vCPU %s run %.0f ns, wait %.4f of the wall (>= %.2f, run > 0); "
               "then %d quiet intervals before the window (>= %d)"
               % ("PASS" if ok else "FAIL", (s1 - s0) / 1000.0, best, tr[best], tw[best] / wall, FIXTURE_WAIT, quiet,
                  QUIET_AFTER))
    return ok


def judge(guest, host, window=None, guest_only=False):
    """returns (verdict, lines); guest_only judges the guest half alone (never the sitting's verdict)"""
    out = []
    try:
        ncpu, recs = read_guest(guest)
        if window:
            w0, w1 = window
        else:
            live = [r["utc"] for r in recs if r["rpid"] != "-"]
            if not live:
                raise Refused("guest trace: no sample shows the ROUNDS process")
            # the span's two ends must be observed: a sample without ROUNDS before it and after it (cover then
            # holds each of those within two seconds of the span)
            if recs[0]["rpid"] != "-" or recs[-1]["rpid"] != "-":
                raise Refused("guest trace: it %s while ROUNDS runs (the window's ends are not observed)"
                              % ("starts" if recs[0]["rpid"] != "-" else "ends"))
            w0, w1 = min(live), max(live)
        out.append("QUIET window utc %d to %d (%.1f s)" % (w0, w1, (w1 - w0) / 1000.0))
        if guest_only:
            return ("PASS" if guest_rules(ncpu, recs, w0, w1, out) else "FAIL"), out
        groups, marks = read_host(host)
        ok = guest_rules(ncpu, recs, w0, w1, out)
        ha, hb, hiv = cover(groups, w0, w1, "host trace")
        ok = host_rules(groups[ha:hb + 1], hiv, out) and ok
        ok = fixture_rule(groups, marks, w0, ha, out) and ok
    except Refused as e:
        out.append("QUIET REFUSED: %s" % e)
        return "REFUSED", out
    return ("PASS" if ok else "FAIL"), out


def main(argv):
    guest_only = len(argv) > 1 and argv[1] == "--guest"
    a = [argv[0], argv[2], "-"] + argv[3:] if guest_only and len(argv) > 2 else argv
    usage = __doc__.split(chr(10) * 2)[1]
    if len(a) not in (3, 6) or (len(a) == 6 and a[3] != "--window"):
        print(usage)
        return 2
    try:
        window = (float(a[4]), float(a[5])) if len(a) == 6 else None
    except ValueError:
        print(usage)
        return 2
    v, lines = judge(a[1], a[2], window, guest_only)
    for ln in lines:
        print(ln)
    # the guest half has its own word: it is never the sitting's quiet verdict
    print("QUIET %s %s" % ("GUEST-HALF" if guest_only else "RESULT", v))
    return {"PASS": 0, "FAIL": 1, "REFUSED": 3}[v]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
