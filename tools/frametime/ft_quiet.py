"""ft_quiet.py: the quiet protocol's acceptance of one sitting (ruling R6-A3.11.131 E, ruling R6-A3.11.133 (3) MEDIUM 6;
method-v52.md section 6, method-v54.md:187). A breach invalidates the whole sitting.

Usage: python -I -B ft_quiet.py <guest trace> <host trace|-> [--window <utc ms from> <utc ms to>]
       python -I -B ft_quiet.py --guest <guest trace> [--window <utc ms from> <utc ms to>]
         (the guest half alone, printed "QUIET GUEST-HALF <verdict>": never the sitting's verdict)

Inputs: the guest trace ft_quiet_guest.ps1 writes on the VM (one G line a second) and the host trace
ft_quiet_host.sh writes on the Proxmox host (one group of V and C lines a second, X lines around the contention
fixture). Both carry utc=<epoch ms>; the window is judged on that clock, each trace's own intervals on its mono=<ns>.
The window is the given one, or by default the span of guest samples that show the ROUNDS process (calibration
through terminal drain).

The rules, every interval of the window:
  guest  non-game cores = total% x ncpu / 100 - ROUNDS cores: p95 <= 0.05 and every interval <= 0.20;
         each physical disk's Avg. Disk Queue Length <= 3; Available MBytes >= 3000; % Committed Bytes In Use <= 85;
         Pages Input/sec, Page Reads/sec, Pages Output/sec: every rolling ten-second integral (rate x elapsed) <= 10;
  host   each vCPU's delay (d wait / d wall, schedstat): <= 1% over the window and <= 5% every interval; each reserved
         core's non-VM execution (d busy - d run of the vCPUs pinned to it alone) <= 0.05 core;
  fixture before the window: the X fixture=start..stop span shows run growth and d wait / d wall >= 10% on a vCPU,
         then at least QUIET_AFTER host intervals between its stop and the window's start, each within the host
         interval limits (contention removed, quietness regained). Counters frozen at zero fail.
REFUSED (no verdict): a trace missing or unreadable, no host evidence, a missing or non-numeric field, an interval
longer than two seconds, the ROUNDS identity (pid and start) changing inside the window or not single (rpid=NA),
the default window's start or end not observed (the guest trace starting or ending while ROUNDS runs), the vCPU set
changing, a schedstat counter going backwards.
Prints one line per rule and "QUIET RESULT PASS|FAIL|REFUSED"; exit 0 PASS, 1 FAIL, 3 REFUSED, 2 usage.
"""
import math
import sys

NONGAME_P95 = 0.05
NONGAME_MAX = 0.20
DISKQ_MAX = 3.0
AVAIL_MIN = 3000.0
COMMIT_MAX = 85.0
PAGING_MAX = 10.0          # units in any rolling ten seconds
PAGING_SPAN_MS = 10000
GAP_NS = 2000000000        # an interval longer than this refuses
DELAY_ALL = 0.01
DELAY_EACH = 0.05
RESERVED_MAX = 0.05        # cores of non-VM execution per reserved core
FIXTURE_WAIT = 0.10
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
            continue
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


def read_host(path):
    if path == "-":
        raise Refused("no host evidence (missing host evidence refuses, method-v52.md section 6)")
    lines = read_lines(path)
    if not lines or not lines[0].startswith("QH v1"):
        raise Refused("host trace: no 'QH v1' header")
    groups = {}       # mono -> {"utc", "v": {tid: rec}, "c": {cpu: busy}}
    marks = []
    for i, ln in enumerate(lines[1:], 2):
        kind = ln.split(" ", 1)[0]
        if kind not in ("V", "C", "X"):
            continue
        r = fields(ln)
        what = "host line %d" % i
        utc, mono = num(r, "utc", what), num(r, "mono", what)
        if kind == "X":
            if r.get("fixture") not in ("start", "stop"):
                raise Refused("%s: fixture=%r" % (what, r.get("fixture")))
            marks.append((utc, r["fixture"]))
            continue
        g = groups.setdefault(mono, {"utc": utc, "v": {}, "c": {}})
        if kind == "V":
            tid = r.get("tid")
            if not tid:
                raise Refused("%s lacks tid" % what)
            g["v"][tid] = {"cpus": r.get("cpus", ""), "run": num(r, "run", what), "wait": num(r, "wait", what)}
        else:
            g["c"][r.get("cpu", "")] = num(r, "busy", what)
    out = [dict(mono=m, **groups[m]) for m in sorted(groups)]
    if not out or not any(g["v"] for g in out):
        raise Refused("no host evidence: the host trace holds no vCPU sample")
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


def p95(xs):
    s = sorted(xs)
    return s[max(0, int(math.ceil(0.95 * len(s))) - 1)]


def guest_rules(ncpu, recs, w0, w1, out):
    win = [r for r in recs if w0 <= r["utc"] <= w1]
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
        # each sample's rate is its interval's average: units = rate x elapsed; the integral over every ten seconds
        # ending at a sample
        units = [(b["utc"], b[k] * d / 1e9) for a, b, d in iv]
        worst = 0.0
        for t, _ in units:
            s = sum(u for tt, u in units if t - PAGING_SPAN_MS < tt <= t)
            worst = max(worst, s)
        bad = worst > PAGING_MAX
        out.append("QUIET guest %s %s: worst ten-second integral %.2f (<= %.0f)"
                   % (name, "FAIL" if bad else "PASS", worst, PAGING_MAX))
        ok = ok and not bad
    return ok


def host_iv_limits(a, b, d):
    """one host interval: each vCPU's delay and each reserved core's non-VM cores; returns (worst delay, worst
    reserved, the per-vCPU d wait and d run)"""
    if set(a["v"]) != set(b["v"]):
        raise Refused("host trace: the vCPU set changes at utc %d" % b["utc"])
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
        if cpu not in a["c"]:
            raise Refused("host trace: reserved core %s appears at utc %d" % (cpu, b["utc"]))
        vm = sum(runs[t] for t in b["v"] if b["v"][t]["cpus"] == cpu)
        worst_r = max(worst_r, (busy - a["c"][cpu] - vm) / d)
    return worst_d, worst_r, waits, runs


def host_rules(groups, marks, w0, w1, out):
    win = [g for g in groups if w0 <= g["utc"] <= w1]
    if len(win) < 2:
        raise Refused("no host evidence in the window (%d host samples)" % len(win))
    iv = intervals(win, "host trace")
    ok = True
    worst_d = worst_r = 0.0
    tw, tr = {}, {}
    for a, b, d in iv:
        dd, rr, waits, runs = host_iv_limits(a, b, d)
        worst_d, worst_r = max(worst_d, dd), max(worst_r, rr)
        for t in waits:
            tw[t] = tw.get(t, 0) + waits[t]
    wall = win[-1]["mono"] - win[0]["mono"]
    overall = max(tw[t] / wall for t in tw)
    for name, bad, txt in (("vCPU delay every interval", worst_d > DELAY_EACH, "max %.4f (<= %.2f)" % (worst_d, DELAY_EACH)),
                           ("vCPU delay overall", overall > DELAY_ALL, "max %.4f (<= %.2f), %d vCPUs" % (overall, DELAY_ALL, len(tw))),
                           ("reserved-core non-VM", worst_r > RESERVED_MAX, "max %.4f cores (<= %.2f)" % (worst_r, RESERVED_MAX))):
        out.append("QUIET host %s %s: %s" % (name, "FAIL" if bad else "PASS", txt))
        ok = ok and not bad
    return ok


def fixture_rule(groups, marks, w0, out):
    starts = [u for u, m in marks if m == "start" and u < w0]
    if not starts:
        out.append("QUIET contention fixture FAIL: no fixture before the window")
        return False
    s0 = starts[-1]
    stops = [u for u, m in marks if m == "stop" and s0 < u < w0]
    if not stops:
        out.append("QUIET contention fixture FAIL: the fixture started at %d has no stop before the window" % s0)
        return False
    s1 = stops[0]
    fx = [g for g in groups if s0 <= g["utc"] <= s1]
    if len(fx) < 2:
        out.append("QUIET contention fixture FAIL: %d host samples inside the fixture" % len(fx))
        return False
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
    after = [g for g in groups if s1 <= g["utc"] < w0]
    quiet = 0
    if len(after) >= 2:
        for a, b, d in intervals(after, "host trace (after the fixture)"):
            dd, rr, _, _ = host_iv_limits(a, b, d)
            quiet = quiet + 1 if dd <= DELAY_EACH and rr <= RESERVED_MAX else 0
    regained = quiet >= QUIET_AFTER
    ok = grown and regained
    out.append("QUIET contention fixture %s: vCPU %s run %.0f ns, wait %.4f of the wall (>= %.2f, run > 0); then %d "
               "quiet intervals before the window (>= %d)"
               % ("PASS" if ok else "FAIL", best, tr[best], tw[best] / wall, FIXTURE_WAIT, quiet, QUIET_AFTER))
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
            # the span's two ends must be observed: a sample without ROUNDS before it and after it
            if recs[0]["rpid"] != "-" or recs[-1]["rpid"] != "-":
                raise Refused("guest trace: it %s while ROUNDS runs (the window's ends are not observed)"
                              % ("starts" if recs[0]["rpid"] != "-" else "ends"))
            w0, w1 = min(live), max(live)
        out.append("QUIET window utc %d to %d (%.1f s)" % (w0, w1, (w1 - w0) / 1000.0))
        if guest_only:
            return ("PASS" if guest_rules(ncpu, recs, w0, w1, out) else "FAIL"), out
        groups, marks = read_host(host)
        ok = guest_rules(ncpu, recs, w0, w1, out)
        ok = host_rules(groups, marks, w0, w1, out) and ok
        ok = fixture_rule(groups, marks, w0, out) and ok
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
