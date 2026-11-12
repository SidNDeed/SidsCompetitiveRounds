#!/usr/bin/env python3
"""ft_parse.py: the FrameTime (B11 format M) log parser and its verdicts. Stdlib only.

It reads the [FRAME-TIME] lines of a BepInEx log and applies METHOD-V4.md's statistics, ported from
dither_control v5 (md5 894b010c), whose claims C10 to C21 they reproduce. test_ft_parse.py checks the
port against values computed with the control.

Lines read (all values integers; a value with a decimal point is refused, HIGH 5):
  w        window:   pt=g.r.p arm=ON|OFF plant=0|1 partial=0|1 n sF sS sC maxF [medF e4=kmin,kmax e8=.. e16=..] gc
  p        point:    pt arm gate pred n sF sS sC maxF pn psF psS psC plant_mixed windows live_frames missing_end
                     span_g span_gn span_u span_un on_calls guarded (census and span totals, live moment)
                     zs zl (zero-state failing rows, late rows read; ZERO-STATE.md)
                     t0 t1 (Stopwatch ticks at the first live frame boundary and at the end; B3)
                     (n and the s sums are the unplanted frames, pn and the ps sums the planted ones)
  plant    once:     c_plant (us) ticks from=g.r.p|sentinel
  settled  per game: g seed c_plant W vsync target freq hires f_hat gc_incremental gc_slice_ns f18 ... missing_end
  cal      per run:  i why kind=fhat|disp|span ...
  census   per entry per game: g entry comp shape on guarded outside
  heavy    per operation per game: g op live between pick over menu at_call edge off (B3)
  offthread per game: g span_off hash_t0 hash_t1 (B3)
  refusals at game over and quit: why pairs what:route=count ... (VR6's build half)
  disarmed once, if FtArm's predicate fails after arming: input pt (the sitting is INVALID)
  answer_replay per game under f18=A: g ticks result (F18; settled and point lines carry answer=replay|unmeasured)

The plant gives e_C_lo (V4 3.5) and VR7. Part 3's remainder adds D_up (V4 3.6) and K_up (UPKEEP spans); until
those lines exist, report() states U as not computable rather than computing it without them.

  census registered expected missing duplicates: once per process, the census summary (kind census_summary)

  alloc pin= planted= empty=; scope plant asked= got=; nest plant asked= x= e= p=; photon patches n= names=; scope census
  entries= wrapped=: the five V6 boot lines, once per process (boot_controls); controls k_mutant=<none|k1|k2|k3>: a
  sitting log prints none (refuse_k_mutant), a control run's boot names the control it breaks (controls_proof)
  counters, in a V6 log: also span_leave_mismatch (0, VR2's class) and photon_offmain (reported only), both printed

Usage: python -I -B ft_parse.py <sitting-C log> --peer <the other seat's sitting-C log> [--ref <reference log>]
                                   (sitting C, as built: its validity set, the cross-check and the two-arm guards)
       python -I -B ft_parse.py --on <seat>=<sitting-V log> <seat>=<sitting-V log>
                                   (report_on: U, its terms and the validity set per seat, seats named)
       python -I -B ft_parse.py --combine V:<seat>=<log> V:<seat>=<log> C:<seat>=<log> C:<seat>=<log>
                                   [R:<seat>=<reference log> ...]
                                   (VERDICT B1 and B3 per seat and the worse seat; a seat's logs paired by its name)
       python -I -B ft_parse.py --controls <a control run's boot log>
                                   (controls_proof: K1 to K3 under k_mutant, the unknown line forms, Failed to patch)
Exit: 0 the report printed; 3 REFUSED (a check refused the input); 4 FT-PARSE REFUSED (a record lacks a key
REQUIRED_KEYS names: one line names its kind, file, line and keys; or an input holds a line "withheld <class> <n>",
n >= 1, of a class in READ_CLASSES: the laptop seat script's export rule held back n lines of a class this parse
reads, so the record is not whole, and the one line names the class, the count, the file and the line).
"""
import math
import os
import re
import runpy
import statistics
import sys

M_ENDS = 4
A_END = 0.05 / M_ENDS
_ND = statistics.NormalDist()
Z_END = _ND.inv_cdf(1.0 - A_END)
H_MS = (4, 8, 16)
A_HITCH = 0.05 / (2 * len(H_MS))      # alpha' = 0.05/6: three H, two ends
CHI_Q = 0.10
VR3_MAX = 0.349
LAST_GAME = 16                        # the sitting: game 0 (the washout mutant), then games 1 to 16 (V4 3.3)
# decision 21'' (ruling FRAME-TIME-ROUND-R6-A3.2, superseding R1-A1's decision 21': the band 0.5..1.5 and the
# nearness 0.10, which the per-segment spread made unreachable at any level, spread-r6a3.md): at each menu level the
# e_C interval contains 1 and excludes 0, and at MENU_EC_LO_LEVEL its lower end is at least MENU_EC_LO_MIN, VR2's
# own criterion (METHOD-V4 VR2: e_C_lo >= 0.5) rehearsed at the menu
MENU_EC_LO_MIN = 0.5
MENU_EC_LO_LEVEL = "3"
# the planning model the menu's length comes from (plugin/FtMenu.cs summary), reported against each run's own w
MENU_PLAN_W_US = 146.6                # window-to-window SD of a 120-frame window's mean C, the 17:35 sitting
MENU_PLAN_MARGIN = 1.6                # on the model's per-segment SE
MENU_PLAN_ZPOW = 1.2816               # probability 0.9 of e_C_lo >= 0.5 at a true e_C of 1

_LINE = re.compile(r"\[FRAME-TIME\] (\w+) (.*)$")
_KV = re.compile(r"(\w+)=(\S+)")


class Refused(Exception):
    pass


class RecordRefused(Exception):
    """A record of a known kind lacks a key the checks index (REQUIRED_KEYS): the input is refused as it is read,
    never a traceback inside a verdict. Deliberately not a Refused (nor a KeyError): report() turns those into a
    'not computable' line, and a malformed input must stop the whole parse. The script exits REFUSED_RECORD_EXIT."""

    def __init__(self, kind, src, line, lacks):
        self.kind, self.src, self.line, self.lacks = kind, src, line, list(lacks)
        Exception.__init__(self, "FT-PARSE REFUSED: kind=%s file=%s line=%d lacks %s"
                           % (kind, src, line, ",".join(self.lacks)))


REFUSED_RECORD_EXIT = 4     # the exit code of a RecordRefused; no other path of the script uses it (Refused exits 3)

# ruling R6-A3.11.113 (2)(a): the slice classes (frame_time_seat.ps1's $SliceClasses) whose lines this parse reads. The
# laptop seat script exports a selected line only when the whole line matches one of its forms, and counts the rest
# as one "withheld <class> <n>" line per class; a withheld line of a class read here would otherwise read as absence.
# A test holds every bracketed class word of $SliceClasses that occurs in this source to this tuple.
READ_CLASSES = ("FRAME-TIME", "FPSCAP")
_WITHHELD = re.compile(r"withheld (%s) ([0-9]+)" % "|".join(re.escape(c) for c in READ_CLASSES))


class WithheldRefused(RecordRefused):
    """An input holds a line that is exactly "withheld <class> <n>", n >= 1, <class> in READ_CLASSES: the record is
    refused as a whole, before any record of it is read (exit REFUSED_RECORD_EXIT), never read as absence."""

    def __init__(self, cls, count, src, line):
        self.kind, self.src, self.line, self.lacks = "withheld", src, line, []
        self.cls, self.count = cls, count
        Exception.__init__(self, "FT-PARSE REFUSED: withheld class=%s count=%d file=%s line=%d" % (cls, count, src, line))


def refuse_withheld(text, src="input"):
    """Raise WithheldRefused at the first line of text that is exactly "withheld <class> <n>" with <class> in
    READ_CLASSES and n >= 1; a count of 0, another class, or any other text on the line is not this refusal."""
    for n, ln in enumerate(text.splitlines(), 1):
        m = _WITHHELD.fullmatch(ln)
        if m and int(m.group(2)) >= 1:
            raise WithheldRefused(m.group(1), int(m.group(2)), src, n)


# ----------------------------------------------------------------------------- statistics (ported from the control)

def t_q(z, df):
    return (z + (z ** 3 + z) / (4.0 * df) + (5 * z ** 5 + 16 * z ** 3 + 3 * z) / (96.0 * df * df)
            + (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / (384.0 * df ** 3))


def _gser(a, x):
    ap, d = a, 1.0 / a
    s = d
    for _ in range(100000):
        ap += 1.0
        d *= x / ap
        s += d
        if abs(d) < abs(s) * 1e-15:
            break
    return s * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _gcf(a, x):
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 100000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        de = d * c
        h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def gammp(a, x):
    if x <= 0.0:
        return 0.0
    return _gser(a, x) if x < a + 1.0 else 1.0 - _gcf(a, x)


def gammq(a, x):
    if x <= 0.0:
        return 1.0
    return 1.0 - _gser(a, x) if x < a + 1.0 else _gcf(a, x)


def pois_cdf(k, lam):
    if k < 0:
        return 0.0
    return gammq(k + 1.0, lam) if lam > 0.0 else 1.0


def chi2_quantile(q, nu):
    lo, hi = 0.0, nu + 10.0 * math.sqrt(2.0 * nu) + 10.0
    while gammp(0.5 * nu, 0.5 * hi) < q:
        hi *= 2.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if gammp(0.5 * nu, 0.5 * mid) < q:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def pois_ub(k, a):
    """Exact upper limit for a (real, dispersion-scaled) count k: P(X <= k; lam) = a, 60 bisection steps."""
    lo, hi = 0.0, k + 10.0 + 10.0 * math.sqrt(k + 1.0)
    while pois_cdf(k, hi) > a:
        hi *= 2.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if pois_cdf(k, mid) > a:
            lo = mid
        else:
            hi = mid
    return hi


def pois_lb(k, a):
    if k <= 0.0:
        return 0.0
    lo, hi = 0.0, float(k)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gammp(float(k), mid) < a:
            lo = mid
        else:
            hi = mid
    return lo


def phi_hat(ks, ns):
    tot_k, tot_n = sum(ks), sum(ns)
    if tot_k <= 0:
        return 1.0
    lam = tot_k / tot_n
    return sum((k - n * lam) ** 2 / (n * lam) for k, n in zip(ks, ns)) / (len(ks) - 1)


def phi_v4(ks, ns):
    nu = len(ks) - 1
    return max(1.0, nu * phi_hat(ks, ns) / chi2_quantile(CHI_Q, nu))


def rate_ub(ks, ns, a=A_HITCH):
    f = phi_v4(ks, ns)
    return f * pois_ub(sum(ks) / f, a) / sum(ns)


def rate_lb(ks, ns, a=A_HITCH):
    f = phi_v4(ks, ns)
    return f * pois_lb(sum(ks) / f, a) / sum(ns)


def fw_interval(dw, z=Z_END):
    """Frame-weighted estimate over games and its one-sided half-width (V4 3.4, F15): the linearised ratio
    variance over one-game and two-game batches, the wider wins. dw: [(d_g, N_g)]. Returns (est, hw, df)."""
    tot = sum(w for d, w in dw)
    est = sum(d * w for d, w in dw) / tot
    best = None
    for b in (1, 2):
        bs = []
        for i in range(0, len(dw) - len(dw) % b, b):
            ww = sum(w for d, w in dw[i:i + b])
            bs.append((sum(d * w for d, w in dw[i:i + b]) / ww, ww))
        kb = len(bs)
        wbar = sum(w for d, w in bs) / kb
        se = math.sqrt(sum((w * (d - est) / wbar) ** 2 for d, w in bs) / (kb * (kb - 1)))
        hw = t_q(z, kb - 1) * se
        if best is None or hw > best[1]:
            best = (est, hw, kb - 1)
    return best


def batch_interval(ds, z=Z_END):
    """The control's interval over games for a per-game mean (e_C): one-game and two-game batch means, the wider
    one-sided half-width wins. Returns (est, hw, df)."""
    k = len(ds)
    est = sum(ds) / k
    best = None
    for b in (1, 2):
        bm = [sum(ds[i:i + b]) / b for i in range(0, k - k % b, b)]
        kb = len(bm)
        mb = sum(bm) / kb
        se = math.sqrt(sum((v - mb) ** 2 for v in bm) / (kb - 1) / kb)
        hw = t_q(z, kb - 1) * se
        if best is None or hw > best[1]:
            best = (est, hw, kb - 1)
    return best


def lag1(xs):
    m = sum(xs) / len(xs)
    den = sum((x - m) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return sum((xs[i] - m) * (xs[i + 1] - m) for i in range(len(xs) - 1)) / den


# ----------------------------------------------------------------------------- lines

def _int(key, v):
    if not re.fullmatch(r"-?\d+", v):
        raise Refused("non-integer value %s=%s" % (key, v))
    return int(v)


INT_KEYS = {"written", "withheld", "seg", "pair", "base_us", "segs", "of", "cycles", "n", "sF", "sS", "sC", "maxF", "medF", "gc", "gate", "windows", "live_frames", "missing_end", "partial",
            "g", "seed", "c_plant", "W", "vsync", "target", "freq", "hires", "f_hat", "frames", "cycle_failures",
            "span_depth_violations", "on", "guarded", "outside", "i", "plant", "pn", "psF", "psS", "psC",
            "plant_mixed", "ticks", "span_g", "span_gn", "span_u", "span_un", "on_calls", "zs", "zl",
            "t0", "t1", "live", "between", "pick", "over", "menu", "at_call", "edge", "off", "span_off",
            "hash_t0", "hash_t1", "sP", "psP", "excl", "se", "ce", "ic", "calls", "dispatched",
            "cap", "steady", "reads_on", "reads_win", "writes_on", "starts", "nonempty", "faults",
            "reads", "scopes", "tmax", "unscoped", "depth_err",
            "run", "pos", "coin", "wi", "f0", "res", "gcn", "cW", "cR", "cS", "cE", "prun", "nm", "cyc", "p90",
            "own_split", "recv_offmain", "ledger_cycle_miss", "sock_n", "heap",
            "sock_thr", "sock_main", "cP", "cX", "ab_back", "ab_retry", "span_leave_mismatch", "photon_offmain",
            # ruling R6-A3.11.151 (2) class B: the p line's fault counters the parser now judges
            "off_g", "off_gn", "off_on", "on_guarded", "span_class_overflow", "gc_read_failures"}
# the B11 window line (ruling R6-A3.11.138, SHARED.md's line contract): the fields it appends to the w line, in order.
# q = C° by tenth, r = the retained direct execution R by tenth, qn = frames by tenth, prun = the window is in a plant
# run (spun or not; the w line's own plant= marks a window actually planted, its own partial= is the only partial
# flag), wu = typed writer units (type:units:cycles;..., cycles NA where unread), tok = each writer type's token ledger
# (type:open0,enqON,enqOFF,doneON,doneOFF,disc,open1;...), nm = the window's class transitions (FtSpan marks)
# V6 (SHARED.md "V6: the direct bound", rulings R6-A3.11.146 and .147) appends after nm: cP (the recv scopes, class P),
# cX (Photon's own main-thread work, class X), aC (the bytes allocated in the window's live frames), aW to aX (the bytes
# allocated while that class ran on the main thread; NA when the counter is unavailable) and wa (the bytes allocated in
# the off-thread scopes of log, hash and sock: wa=log:<b>;hash:<b>;sock:<b>, each NA when unavailable)
V6_FIELDS = ("cP", "cX", "aC", "aW", "aR", "aS", "aP", "aX", "wa")
A_FIELDS = ("aC", "aW", "aR", "aS", "aP", "aX")
B11_FIELDS = ("run", "pos", "unit", "coin", "wi", "f0", "pred", "prun", "res", "gcn", "cG", "cW", "cR", "cS", "cE", "q",
              "r", "qn", "wu", "tok", "nm") + V6_FIELDS
W_LIST_KEYS = ("q", "r", "qn")
# keys that print NA when unread, read as None: a w line's a* bytes (the allocation counter) and cG (the GC hook), a p
# line's sock_p95 (FtUpload.SockStats prints NA when the point had no datagram, or when the percentile falls in the open
# last bucket). A p line's heap= is always a number (GC.GetTotalMemory, plugin/FtFrames.cs:279; ruling R6-A3.11.149 (6)
# 9 and 10): it is an INT_KEYS key, and NA there is a non-integer value
NA_KEYS = {"w": ("cG",) + A_FIELDS, "p": ("sock_p95",)}


# a line the build writes under an emitted kind that is not that kind's record, told apart by its first word (as
# failure events are, FAILURE_EVENTS): record kind -> (the emitted kind, the first word's prefix). FtE.RegisterAll
# writes the one census summary ("census registered=N expected=N missing=N duplicates=N") beside the per-game
# census lines, so every consumer of kind "census" sees per-game lines only (bug: the summary read as a census
# record without g stopped complete() with KeyError 'g')
SUBKINDS = {"census_summary": ("census", "registered="),
            # ruling R6-A3.11.151 (3): Plugin's warning when the attach report itself throws, beside the attach line
            "attach_failed": ("attach", "report")}


def parse_line(line):
    m = _LINE.search(line)
    if not m:
        return None
    kind, rest = m.group(1), m.group(2)
    rec = {"kind": kind}
    # the first word after the kind: a failure event (FAILURE_EVENTS) is told apart from its kind's ordinary line by it
    words = rest.split()
    rec["head"] = words[0] if words else ""
    for sub, (parent, prefix) in SUBKINDS.items():
        if kind == parent and rec["head"].startswith(prefix):
            kind = rec["kind"] = sub
    if kind == "refusals":
        # what:route=count tokens; route names hold ':' and '/', so split each token at its last '='
        kv = {}
        for tok in rest.split():
            k, _, v = tok.rpartition("=")
            if k in ("why", "pairs"):
                rec[k] = v if k == "why" else _int(k, v)
            elif k:
                kv[k] = _int(k, v)
        rec["pairs_kv"] = kv
        return rec
    seen = {}
    for k, v in _KV.findall(rest):
        if k == "kind":
            k = "ckind"      # a cal line's kind=fhat|disp|span must not overwrite the line kind
        if kind == "w":
            # a key printed twice on one w line is read once, and only when both copies agree
            if k in seen and seen[k] != v:
                raise Refused("w line: %s printed twice with different values (%s, %s)" % (k, seen[k], v))
            seen[k] = v
            if k in W_LIST_KEYS:
                rec[k] = [_int(k, x) for x in v.split(",")]
                continue
        if k in NA_KEYS.get(kind, ()):
            # NA: cG, the native GC hook is not built (SHARED.md V6); a*, the allocation counter is unavailable (the
            # pin differs); heap, the same counter's heap figure unread
            rec[k] = None if v == "NA" else _int(k, v)
            continue
        if k in INT_KEYS:
            rec[k] = _int(k, v)
        elif re.fullmatch(r"e\d+", k):
            # the integrator's point I: a value of another form is the parser's refusal, never a ValueError
            if v.count(",") != 1:
                raise Refused("%s=%s is not <count>,<count>" % (k, v))
            a, b = v.split(",")
            rec[k] = (_int(k, a), _int(k, b))
        else:
            rec[k] = v
    # round-4 MEDIUM (ft_parse.py:1132): FtCalib and FtA3 write a failed calibration as a warning that still carries
    # kind=<fhat|disp|a3|span>; it is marked here, and every check counting a calibration kind counts only unmarked lines
    if kind == "cal" and re.search(r"(^|\s)failed:", rest):
        rec["failed"] = 1
    if "pt" in rec:
        if not re.fullmatch(r"-?\d+\.\d+\.\d+", rec["pt"]):
            raise Refused("%s line: pt=%s is not <game>.<round>.<point>" % (kind, rec["pt"]))
        g, r, p = rec["pt"].split(".")
        rec["game"], rec["round"], rec["point"] = int(g), int(r), int(p)
    return rec


# The required-keys table: for every record kind, the keys the parser's checks index as r["key"] (not r.get),
# derived from each kind's consumers, with the condition under which they index them. read() tests every record
# against it, so a record of a known kind that lacks one is a named refusal (RecordRefused), never a KeyError
# traceback (complete()) or a KeyError swallowed into a "not computable" line (report()). Rows of one kind hold
# disjoint keys. (kind, condition shown, condition or None for every line of the kind, keys, consumers)
REQUIRED_KEYS = (
    ("p", None, None,
     ("pt", "arm", "gate", "n", "sF", "sS", "sC", "maxF", "pn", "psF", "psS", "psC", "live_frames", "span_u", "pred",
      "span_g"),
     "games_of, void_rounds, zero_state, contrast_c, d_up, a3, t_ref, predecessor, vr9, longest_frames, e_c, "
     "match_power, k_up, vr2, menu_check, menu_framerate, contrast_key, e_key, upkeep_per_arm, stamps_estimate"),
    ("p", "span_g present", lambda r: "span_g" in r, ("span_gn", "on_calls", "guarded"), "vr5_points"),
    ("p", "t0 present", lambda r: "t0" in r, ("t1",), "b3"),
    ("w", None, None, ("pt", "arm", "n", "sC"), "hitch, _side_plain, _side_vr7, match_power, menu_power"),
    ("w", "partial=0", lambda r: r.get("partial", 1) == 0, ("e4", "e8", "e16"), "hitch"),
    # ruling R6-A3.11.138: a line carrying any field of the B11 contract carries all of them (and the totals the
    # per-point reconciliation sums); a line with none is the pre-B11 window line
    ("w", "a B11 field present", lambda r: any(k in r for k in B11_FIELDS),
     B11_FIELDS + ("plant", "partial", "sF", "sS", "sP"),
     "window_reconcile, window_faults, b11_terms, vr5_points, t_ref_windows"),
    # SHARED.md: the boot line giving one class transition's cost, which nm multiplies
    ("mark", None, None, ("cyc", "p90", "n"), "b11_transitions"),
    # FtLedger.Install's one boot line (plugin/FtUpload.cs:368)
    ("ledger", None, None, ("log", "why", "types"), "ledger_state"),
    # ruling R6-A3.11.151 (3): the attach line (FtAttach.Report), the ATTACH guard's
    ("attach", None, None, ("n", "of", "missing", "names"), "attach_faults"),
    ("settled", None, None, ("g", "freq", "f_hat"),
     "complete, _fhat, d_up, t_ref, vr1, vr9, f18, e_c, match_power, vr2, menu_check, _freq1"),
    ("census", None, None, ("g", "entry", "shape", "on", "guarded"), "complete, d_up, vr5_records, vr5_points, vr2"),
    ("census_summary", None, None, ("registered", "expected", "missing", "duplicates"), "census_summary"),
    ("cal", None, None, ("i",), "a3_live, vr2"),
    ("cal", "kind=disp|span, not failed", lambda r: r.get("ckind") in ("disp", "span") and not r.get("failed"),
     ("shape", "n", "u", "p"), "d_up, stamps_estimate"),
    ("cal", "kind=fhat, not failed", lambda r: r.get("ckind") == "fhat" and not r.get("failed"), ("f_hat",),
     "menu_check"),
    # Codex PARSER-FIX-R1 HIGH 1: a live row's executed line (a3_live indexes these after its own presence check)
    ("cal", "live present", lambda r: "live" in r, ("reads", "scopes", "ticks", "tmax", "unscoped", "depth_err"),
     "a3_live"),
    ("heavy", None, None, ("op", "at_call", "edge", "off", "live"), "b3"),
    ("offthread", None, None, ("span_off", "hash_t0", "hash_t1"), "b3, report"),
    ("plant", None, None, ("c_plant",), "e_c, match_power, e_key"),
    # the reference build prints 'a3 g=<g> ref=NA rows=0' (no row is measured there) and no reads_win; read() admits
    # that form in a reference-marked log only (the integrator's point J), and refuses it in any other log as lacking
    # reads_win, as before
    ("a3", None, None, ("g",), "proof_records, a3"),
    ("a3", "not ref=NA", lambda r: r.get("ref") != "NA", ("reads_win",), "proof_records, a3"),
    ("answer_replay", None, None, ("g",), "f18"),       # Codex PARSER-FIX-R1 HIGH 1: f18 keys every replay by g
    ("answer_replay", "result=settled", lambda r: r.get("result") == "settled", ("ticks",), "f18"),
    ("between", "after=ON", lambda r: r.get("after") == "ON", ("ticks",), "between_after"),
    ("menu", None, None, ("seg", "pair", "arm", "gate"), "menu_check"),
    ("menu", "c_plant>0", lambda r: r.get("c_plant", 0) > 0, ("level",), "menu_check"),
)


def lacks_keys(r):
    """The required keys (REQUIRED_KEYS) record r lacks, in table order (empty when it carries them all)."""
    out = []
    for kind, _, cond, keys, _ in REQUIRED_KEYS:
        if r["kind"] == kind and (cond is None or cond(r)):
            out += [k for k in keys if k not in r]
    return out


def read(text, src="input"):
    """The [FRAME-TIME] records of a log, each tested against REQUIRED_KEYS as it is read; src names the input in a
    RecordRefused (its 1-based line number is the line's in text). A withheld line of a read class refuses the whole
    input first (refuse_withheld). The reference build's a3 form ('a3 g=<g> ref=NA ...', no reads_win) is admitted only
    in a log that build_marker reads as a reference (exactly one FrameTimeRef marker and no FrameTime one); in any other
    log it is refused as lacking reads_win (the integrator's point J). A line whose form cannot be read is refused by
    parse_line (Refused), never a traceback (point I)."""
    refuse_withheld(text, src)
    recs, ref_log = [], None
    for n, ln in enumerate(text.splitlines(), 1):
        r = parse_line(ln)
        if r is not None:
            gone = lacks_keys(r)
            if not gone and r["kind"] == "a3" and r.get("ref") == "NA":
                if ref_log is None:
                    ref_log = reference_marked(text)
                gone = [] if ref_log else ["reads_win"]
            if gone:
                raise RecordRefused(r["kind"], src, n, gone)
            recs.append(r)
    return recs


def reference_marked(text):
    """True when build_marker reads text as a reference input (one FrameTimeRef marker, no FrameTime one)."""
    try:
        build_marker(text, "reference", "text")
    except MarkerRefused:
        return False
    return True


# ----------------------------------------------------------------------------- verdicts

def void_rounds(recs):
    """V4 3.3: the rounds (game, round) holding a point whose zero-state check failed (zs != 0)."""
    return set((r["game"], r["round"]) for r in recs if r["kind"] == "p" and r.get("zs", 0) != 0)


def games_of(recs, first_game=1):
    """Measured games (game 0 is the washout test and counts toward nothing), void rounds left out:
    {game: [point records]}. A game with no valid round is absent (reported by zero_state)."""
    void = void_rounds(recs)
    out = {}
    for r in recs:
        if r["kind"] == "p" and r["game"] >= first_game and (r["game"], r["round"]) not in void:
            out.setdefault(r["game"], []).append(r)
    return out


def expected_entries():
    """The census table the build registers (gate_specs/entries.py, the same source gen_entries.py writes
    plugin/FtEntries.cs from): [(census name, shape)], names as the census line spells them."""
    here = os.path.dirname(os.path.abspath(__file__))
    rows = runpy.run_path(os.path.join(here, "gate_specs", "entries.py"))["ENTRIES"]
    return [(n.replace(" ", ":"), s) for c, n, k, s in rows]


OPENED = ("se", "ce", "ic")
# FtHeavy.Names, in order (plugin/FtHeavy.cs): B3 requires one heavy line per operation per game
HEAVY_OPS = ("ce_build", "se_build", "cd_build", "ic_build", "enqueue", "spool", "pump", "answer", "hash_start",
             "hash_now")     # V4 3.7 VR5: SeatEvidence, CombatEvidence and IdentityClockEvidence's BeginGame


def complete(recs, last_game=LAST_GAME):
    """The complete sitting (round-1 HIGH 4, the complete-slice law): before any verdict, games 0 to last_game
    each present with a settled line, point lines, a calibration run and their census, and the sitting's own
    completion line (FtDrive: sitting complete g=last_game). Returns the list of what is missing (empty when
    complete)."""
    miss = []
    want = set(range(0, last_game + 1))
    sett = set(r["g"] for r in recs if r["kind"] == "settled")
    pts = set(r["game"] for r in recs if r["kind"] == "p")
    cen = set(r["g"] for r in recs if r["kind"] == "census")
    # a failed calibration line is no calibration (round-4 rule; ruling R6-A3.11.92 (4))
    cal = set(int(r["why"][4:]) for r in recs if r["kind"] == "cal" and re.fullmatch(r"game\d+", str(r.get("why", "")))
              and not r.get("failed"))
    for name, have in (("settled line", sett), ("point lines", pts), ("census", cen), ("calibration", cal)):
        gone = sorted(want - have)
        if gone:
            miss.append("no %s for games %s" % (name, gone))
        extra = sorted(g for g in have if g > last_game)
        if extra:
            miss.append("%s for games beyond %d: %s" % (name, last_game, extra))
    done = [r for r in recs if r["kind"] == "sitting" and r.get("g") == last_game]
    if len(done) != 1:
        miss.append("%d 'sitting complete g=%d' lines (needs exactly 1)" % (len(done), last_game))
    miss += census_summary(recs)[2]
    miss += records_missing(recs, last_game)
    return miss


CENSUS_SUMMARY_KEYS = ("registered", "expected", "missing", "duplicates")


def census_summary(recs):
    """The build's census summary (FtE.RegisterAll, once per process at clock install, before any game): exactly one
    line per seat's log, and on it registered equals expected, expected equals the entries the parser derives itself
    (expected_entries(), gate_specs/entries.py), missing is 0 and duplicates is 0. Required: FtClock.Install writes it
    unconditionally once the clock installs, and no game line is written without the clock, so a log without it (or
    with two, a second process) is not one sitting's. Returns (ok, reading, misses)."""
    want = len(expected_entries())
    lines = [r for r in recs if r["kind"] == "census_summary"]
    bad = []
    if len(lines) != 1:
        bad.append("%d census summary lines (needs exactly 1)" % len(lines))
    for r in lines:
        v = {}
        for k in CENSUS_SUMMARY_KEYS:
            if re.fullmatch(r"-?\d+", str(r[k])):
                v[k] = int(r[k])
            else:
                bad.append("census summary %s=%s is not an integer" % (k, r[k]))
        if len(v) != len(CENSUS_SUMMARY_KEYS):
            continue
        if v["registered"] != v["expected"]:
            bad.append("census summary registered=%d differs from expected=%d" % (v["registered"], v["expected"]))
        if v["expected"] != want:
            bad.append("census summary expected=%d differs from the %d entries gate_specs/entries.py derives"
                       % (v["expected"], want))
        if v["missing"] != 0:
            bad.append("census summary missing=%d (needs 0)" % v["missing"])
        if v["duplicates"] != 0:
            bad.append("census summary duplicates=%d (needs 0)" % v["duplicates"])
    reading = "%d line%s%s; entries.py derives %d" % (
        len(lines), "" if len(lines) == 1 else "s",
        "".join(" [%s]" % " ".join("%s=%s" % (k, r[k]) for k in CENSUS_SUMMARY_KEYS) for r in lines), want)
    return not bad, reading, bad


def records_missing(recs, last_game=LAST_GAME):
    """The absent-record sweep (ruling FRAME-TIME-ROUND-R2, round-2 HIGH ft_parse.py:495 and its class): every
    per-game and per-point record the parser reads, required where the build always writes it, so a missing line
    withholds the verdict instead of shrinking what is judged. RECORDS below lists each kind with its rule; the
    kinds required elsewhere (settled, census, opened, cal, a3, a3drain, answer_replay, plant, refusals, sitting)
    are named there with the function that requires them. Returns the list of what is missing."""
    miss = failure_events(recs)
    for g in range(0, last_game + 1):
        pts = [r for r in recs if r["kind"] == "p" and r["game"] == g]
        # flushed: FtSchedule.FlushGame writes one per game (next_game, settle or quit)
        n = sum(1 for r in recs if r["kind"] == "flushed" and r.get("g") == g)
        if n != 1:
            miss.append("game %d: %d flushed lines (needs 1)" % (g, n))
        # between: FtFrames writes one at every point start after the game's first point
        n = sum(1 for r in recs if r["kind"] == "between" and r.get("g") == g)
        if pts and n != len(pts) - 1:
            miss.append("game %d: %d between lines for %d points (needs %d)" % (g, n, len(pts), len(pts) - 1))
        # heavy and offthread: one per operation per game, one per game (B3 also refuses on them)
        for op in HEAVY_OPS:
            n = sum(1 for r in recs if r["kind"] == "heavy" and r.get("g") == g and r.get("op") == op)
            if n != 1:
                miss.append("game %d: %d heavy lines for %s (needs 1)" % (g, n, op))
        n = sum(1 for r in recs if r["kind"] == "offthread" and r.get("g") == g)
        if n != 1:
            miss.append("game %d: %d offthread lines (needs 1)" % (g, n))
    # w: window ownership and the B11 reconciliation (ruling R6-A3.11.138, SHARED.md), every point and every window
    # visited, no early stop
    miss += window_reconcile(recs)
    # answer_replay (round-3 MEDIUM ft_parse.py:1461): under reading A, FtSchedule writes one replay line per game
    # over: a replay call (FtReplay.Run) at the next boundary that reads not live or at the next game start, or a skip
    # line (FtReplay.Skip, result=skipped_live, skipped_quit or skipped_absent) where no call may run, decided owed at
    # the game over (reading A with the sentinel present there). Each game 0..last needs exactly
    # one; f18() fails a skip only for a game it reads (g >= first_game), so game 0's counts here only. Under reading
    # B there is none
    readings = set(r.get("f18") for r in recs if r["kind"] == "settled" and r.get("g", -1) >= 0)
    for g in range(0, last_game + 1):
        n = sum(1 for r in recs if r["kind"] == "answer_replay" and r.get("g") == g)
        want = 1 if readings == {"A"} else 0
        if n != want:
            miss.append("game %d: %d answer_replay lines (reading %s needs %d)" % (g, n, "/".join(sorted(map(str, readings))), want))
    # counters: FtSchedule.FlushGame writes one per game (VR2 judges its values)
    for g in range(0, last_game + 1):
        n = sum(1 for r in recs if r["kind"] == "counters" and r.get("g") == g)
        if n != 1:
            miss.append("game %d: %d counters lines (needs 1)" % (g, n))
    # refusals: VR6 reads the cumulative counts of the line written after the last game (its flush or the quit)
    if not any(r["kind"] == "refusals" and r.get("why") in ("quit", "game%d" % last_game) for r in recs):
        miss.append("no refusals line after game %d (why=game%d or why=quit)" % (last_game, last_game))
    return miss


# The absent-record table (ruling FRAME-TIME-ROUND-R2): kind -> where its absence fails. "event" kinds are lines
# whose absence is the normal case, judged only on a complete log (complete() above), with the reason stated.
RECORDS = {
    "settled": "complete() and vr2: one per game",
    "p": "complete(): point lines per game; a3(): a drained row's probe count equals the game's point lines",
    "w": "records_missing() via window_reconcile(): exactly one owner point per window line, per point as many as the "
         "point line's windows; B11 lines: contiguous ordinals and the point's planted and unplanted totals",
    "mark": "b11_transitions(): the boot line '[FRAME-TIME] mark cost cyc= p90= n=', exactly once (SHARED.md)",
    # ruling R6-A3.11.147 (5): the five V6 boot lines, each exactly once; a missing one is its control out of range
    "alloc": "boot_controls(): 'alloc pin= planted=/ empty=' exactly once, K1 and the pin (sitting_v withholds)",
    "scope": "boot_controls(): 'scope plant asked= got=' (K2) and 'scope census entries= wrapped=' (R-SCOPE), each "
             "exactly once (sitting_v withholds)",
    "nest": "boot_controls(): 'nest plant asked= x= e= p=' exactly once, K3 (sitting_v withholds)",
    "photon": "boot_controls(): 'photon patches n= names=' exactly once, R-SCOPE's patch line (sitting_v withholds)",
    "build": "report(): exactly one FrameTime marker in a measurement input, exactly one FrameTimeRef marker in a "
             "reference input (build_marker())",
    "menu_armed": "menu_check(): one per menu run, the startup snapshot before it and none between it and menu_done",
    "cal": "complete() and vr2: one game-start run per game with a successful fhat, span and every disp shape and no "
           "failure warning; a3_live(): every dependent row's executed line per game (no game-start a3 family since "
           "ruling FRAME-TIME-ROUND-R5)",
    "census": "complete() and vr5_records: one per registered entry per game",
    "census_summary": "complete() via census_summary() (a SUBKINDS line of the emitted kind census): exactly one per "
                      "seat's log, registered = expected = the derived entries, missing 0, duplicates 0",
    "opened": "vr5_records: one per game",
    "heavy": "records_missing() and b3(): one per operation per game",
    "offthread": "records_missing() and b3(): one per game",
    "a3": "a3(): one per dependent row per measured game",
    "a3drain": "a3(): one per drained row per measured game, starts equal to the game's points",
    "answer_replay": "records_missing(): one per game 0..16 under reading A, none under B; f18() judges it, F18 guards B1",
    "between": "records_missing(): one per point after the game's first",
    "flushed": "records_missing(): one per game",
    "counters": "records_missing() and vr2(): one per game, written at its flush, the three counters 0",
    # P1's V6 emitter (via the integrator, 12 Nov): the boot's control-mutant line
    "controls": "refuse_k_mutant(): a V6 sitting log carries exactly one 'controls k_mutant=none' (else K-MUTANT); "
                "controls_proof() reads a control run's boot",
    # the integrator's follow-up to ruling .149, A: the writer ledger's disk-log tap (FtLedger.Install)
    "ledger": "ledger_state(): exactly one 'ledger log= why= types=' per log, log=1 and types= the parser's writer "
              "types (sitting_v withholds; sitting C reports it beside R-WORK)",
    # ruling R6-A3.11.151 (3): the patch classes' attachment, read from Harmony's patch table (FtAttach.Report)
    "attach": "attach_faults() via the validity set's ATTACH: exactly one 'attach n= of= missing= names=' per boot, n "
              "= of, missing=none, every entry got = want > 0, the names the parser's list in ordinal order (sitting V "
              "withholds; sitting C has no cross-check; --controls and read_reference refuse)",
    "attach_failed": "event: 'attach report failed: <message>' (a SUBKINDS line of the emitted kind attach) fails "
                     "ATTACH by its presence",
    "a3zero": "proof_records(): one per measured game for a zero row proved by probe:a3zero (none today)",
    "plant": "e_c(): exactly one",
    "refusals": "records_missing(): one after the last game; vr6_build reads it",
    "sitting": "complete(): exactly one for the last game",
    "menu": "menu_check(): one per segment 1..of, and no menu point line without one (menu runs only)",
    "menu_done": "menu_check(): exactly one, its cycles each with a menu fhat calibration, one settled line after it",
    "disarmed": "event: its presence fails VR6; its absence is normal and is judged on a complete log",
    "game": "event (FAILURE_EVENTS): a game start, game over or game end failure; its presence makes the sitting incomplete",
    "start": "event (FAILURE_EVENTS): the FrameTime start failed; its presence makes the run incomplete",
    "clock": "event (FAILURE_EVENTS) when refused: the clock never installed; 'clock installed' is informational",
}

# the failure warnings the build writes (round-4 sweep of every kind the build emits): any one makes the sitting
# incomplete (records_missing) and fails the menu check, so a run whose game start or game over threw midway is never
# judged on what it happened to write. (kind, head or None for every line of the kind, the writer)
FAILURE_EVENTS = (
    ("game", None, "GameStateWatcher: FtSchedule.GameStart, GameOver or MatchEnded threw ('game start failed', "
                   "'game over failed', 'game end failed')"),
    ("start", None, "Plugin: the FrameTime start threw ('start failed')"),
    ("clock", "refused:", "FtClock: a player-loop phase was missing, so the clock never installed ('clock refused')"),
    # ruling R6-A3.11.92 (3): the room gate's churn-timer step threw, so the sitting's isolation is not proven
    ("churn", "freeze", "FtRoomGate: the churn-timer freeze threw ('churn freeze failed')"),
)


def failure_events(recs):
    return ["failure event: %s %s (%s)" % (r["kind"], r.get("head", ""), why) for r in recs
            for k, h, why in FAILURE_EVENTS if r["kind"] == k and (h is None or r.get("head") == h)]


# ruling R6-A3.11.92 (3): failure warnings whose words _LINE cannot match (the hyphen in FT-ROOM and FT-GATE), read
# as fixed texts in the raw lines so _LINE and every record stay as they were; any one makes the sitting incomplete
# (report) and fails the menu check (menu_report), as a FAILURE_EVENTS line does. (fixed text, the writer)
RAW_FAILURES = (
    ("[FRAME-TIME] FT-ROOM read failed", "FtRoomGate's join postfix: the room identity read threw ('FT-ROOM read failed')"),
    ("[FRAME-TIME] FT-GATE report failed", "Plugin: FtRoomGate.ReportPatched threw ('FT-GATE report failed')"),
)


def raw_failure_events(text):
    return ["failure event: %s (%s)" % (t[len("[FRAME-TIME] "):], why) for ln in text.splitlines()
            for t, why in RAW_FAILURES if t in ln]


# every other kind the build writes (each "[FRAME-TIME] <kind>" in plugin/*.cs), with why no verdict reads it: the
# test test_every_emitted_kind_is_read_or_named fails on a written kind in neither table, and on a kind named here
# that the parser reads
EMITTED_UNREAD = {
    "a3rows": "FtA3.RegisterAll's count; a row that failed to register writes no a3 or a3drain line, which a3() requires",
    "armed": "FtArm's arming record; an unarmed run writes no settled line, which complete() requires per game",
    "not": "FtArm's 'not armed' record; as for armed",
    "room": "FtArm's room record; as for armed",
    "ended": "FtArm's end record; complete() requires the sitting complete line instead",
    "menu_base": "FtMenu's base sample; menu_done's base_us and the menu point lines carry what menu_check judges",
    "menu_wait": "FtMenu waiting for its input; a run that never completes has menu_done why= the failed input",
    "ranked": "the ranked-check guard trace ('ranked-check ...'); _LINE does not even match it (the hyphen)",
    "self": "FtDrive's self-drive trace ('self-drive ...'); _LINE does not match it; sitting complete proves the drive",
    "refused": "FtUpload's per-refusal line; the cumulative refusals line (required) carries the counts VR6 reads",
    "rematch": "FtRematch's answer trace; the next game's settled and point lines (required) prove the rematch",
    "spans": "FtCensus's per-component span breakdown (diagnostic); the point lines' sS carries the span cost judged",
    # ruling R6-A3.11.92 (3): the room gate's and the arming's trace lines
    "staged": "FtArm's staged-property trace ('staged <prop>=<v> in-room|pre-join'); the settled lines carry the arming",
    "peer": "FtArm's peer trace ('peer known|unknown actor=...'); a peer without the build is refused by the arming",
    "churn": "FtRoomGate's 'churn timer frozen' trace; its failure line 'churn freeze failed' is a FAILURE_EVENTS row",
    "ft": "the 'ft room options' trace (Plugin's room options for a frame-time room); no verdict reads it",
    "steam": "SteamAuth's 'steam ticket withheld' trace; FtRoute's refusals reach VR6 through the refusals line",
    "FT": "the FT-GATE and FT-ROOM traces; _LINE does not match them (the hyphen); their two failure lines are "
          "RAW_FAILURES, read as fixed texts in the raw lines, and the FT-GATE patched line is read from the raw text "
          "by the validity set's ATTACH guard (its room gate part, attach_gate_faults; ruling R6-A3.11.151 (3), F17)",
    # ruling R6-A3.11.149 (6) 9 and 10: the merged tip's other boot traces. Each form is known to unknown_forms (FORMS)
    "alloc_init": "FtAlloc.Init's outcome (why=ok, sha, code or failed:<type>); the alloc boot line's pin= prints ok "
                  "exactly when it is ok, and boot_controls judges that line",
    "reference": "the FrameTimeRef build's 'reference collectors not installed' trace; a reference input is known by "
                 "its marker alone (build_marker)",
    "ft_dll": "FtArm's 'ft_dll staging failed' warning (the kind is FtArm.DLL_PROP); the arming reads the peer's "
              "ft_dll, and a seat that never arms writes no settled line, which complete() requires",
}


# ruling R6-A3.11.149 (6) 9 and 10, (8): every [FRAME-TIME] line form the emitter's source prints (plugin/*.cs at the
# merged tip), as (lead, payload pattern, keys). lead is the literal the source prints first after "[FRAME-TIME] "
# (the test holds the set of the source's leads to this table's); the pattern fullmatches the line's payload (the text
# after "[FRAME-TIME] "); keys, for a line whose fields this table fixes, are its keys in printed order ("?" marks one
# printed only sometimes), which the test reads from the source statement. unknown_forms() lists every [FRAME-TIME]
# line whose payload no pattern matches; controls_proof needs 0 of them.
_FV = r"\S+"


def _kv(words, keys, vals=None):
    """A line of fixed keys: the words, then each key=value in order (a key ending '?' optional)."""
    p = re.escape(words)
    for k in keys:
        name = k.rstrip("?")
        one = r" %s=(?:%s)" % (name, (vals or {}).get(name, _FV))
        p += "(?:%s)?" % one if k.endswith("?") else one
    return p


def _star(words):
    """A line of key=value fields the parser reads by key (REQUIRED_KEYS guards the keys it indexes)."""
    return re.escape(words) + r"(?: [^\s=]+=\S*)*"


def _msg(words):
    """A trace or failure line: the words, then any text."""
    return re.escape(words) + r"(?: .*)?"


_I, _N, _INA = r"-?\d+", r"\d+", r"-?\d+|NA"
# ruling R6-A3.11.151 (3): the attach line's printed names are letters, digits and the underscore (FtAttach.NameOf)
ATTACH_NAME = r"[A-Za-z0-9_]+"
ATTACH_MISSING = r"none|%s(?:,%s)*" % (ATTACH_NAME, ATTACH_NAME)
ATTACH_ENTRY = r"%s:\d+/\d+" % ATTACH_NAME
ATTACH_NAMES = r"%s(?:,%s)*" % (ATTACH_ENTRY, ATTACH_ENTRY)
COUNTER_LINE_KEYS = ("g", "frames", "missing_end", "cycle_failures", "span_depth_violations", "photon_offmain",
                     "span_leave_mismatch")
_CAL_FAILED = r"cal i=-?\d+(?: [^\s=]+=\S*)* failed: .*"
FORMS = (
    # the lines whose fields this table fixes (the five boot lines, the controls line, the counters line, the census
    # summary, the mark cost and the other boot traces)
    ("alloc pin=", _kv("alloc", ("pin", "planted", "empty"),
                       {"pin": "ok|differs", "planted": r"(?:\d+|NA)/\d+", "empty": r"\d+|NA"}),
     ("pin", "planted", "empty")),
    ("alloc_init why=", _kv("alloc_init", ("why",)), ("why",)),
    ("scope plant asked=", _kv("scope plant", ("asked", "got"), {"asked": _I, "got": _INA}), ("asked", "got")),
    ("scope census entries=", _kv("scope census", ("entries", "wrapped", "failed?"), {"entries": _N, "wrapped": _N}),
     ("entries", "wrapped", "failed?")),
    ("nest plant asked=", _kv("nest plant", ("asked", "x", "e", "p"), {"asked": _I, "x": _INA, "e": _INA, "p": _INA}),
     ("asked", "x", "e", "p")),
    ("photon patches n=", _kv("photon patches", ("n", "names"), {"n": _N, "names": r"[\w.,]*"}), ("n", "names")),
    ("controls k_mutant=", _kv("controls", ("k_mutant",), {"k_mutant": "none|k1|k2|k3"}), ("k_mutant",)),
    ("counters g=", _kv("counters", COUNTER_LINE_KEYS, dict((k, _I) for k in COUNTER_LINE_KEYS)), COUNTER_LINE_KEYS),
    ("census registered=", _kv("census", CENSUS_SUMMARY_KEYS, dict((k, _I) for k in CENSUS_SUMMARY_KEYS)),
     CENSUS_SUMMARY_KEYS),
    ("mark cost cyc=", _kv("mark cost", ("cyc", "p90", "n"), {"cyc": _I, "p90": _I, "n": _I}), ("cyc", "p90", "n")),
    ("ledger log=", _kv("ledger", ("log", "why", "types"), {"log": "0|1", "types": r"[\w,]*"}), ("log", "why", "types")),
    ("attach n=", _kv("attach", ("n", "of", "missing", "names"),
                      {"n": _N, "of": _N, "missing": ATTACH_MISSING, "names": ATTACH_NAMES}),
     ("n", "of", "missing", "names")),
    ("attach report failed: ", _msg("attach report failed:"), None),
    ("clock installed freq=", _kv("clock installed", ("freq", "hires", "cycles"), {"freq": _N, "hires": "0|1",
                                                                                   "cycles": "0|1"}),
     ("freq", "hires", "cycles")),
    ("sitting complete g=", _kv("sitting complete", ("g",), {"g": _I}), ("g",)),
    # the two build markers (MARK_FT and MARK_REF below; the test holds them equal)
    ("build variant=FrameTime", re.escape("build variant=FrameTime"), None),
    ("build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS", re.escape("build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS"),
     None),
    # the records the parser reads by key
    ("a3 g=", _star("a3"), None), ("a3drain g=", _star("a3drain"), None),
    ("a3rows registered=", _star("a3rows"), None), ("a3rows registered=0 expected=", _star("a3rows"), None),
    ("answer_replay g=", _star("answer_replay"), None), ("between g=", _star("between"), None),
    ("cal i=", _star("cal"), None), ("cal i=", _CAL_FAILED, None),
    ("cal i=-1 why=patches kind=entries built=1 own_owner=", _star("cal"), None),
    ("cal i=-1 why=patches kind=entries reference=1 built=0", _star("cal"), None),
    ("cal i=-1 why=patches kind=entries failed: ", _CAL_FAILED, None),
    # FtCalib.Run's entries step failing (plugin/FtCalib.cs:126): the word 'entries' carries no '=', so _CAL_FAILED does
    # not hold it (the integrator's point H). parse_line marks it failed with kind=disp, so VR2 already fails the
    # game's calibration run that prints it ('carries failure warnings for disp') and B1 is WITHHELD
    ("cal i=", r"cal i=-?\d+ kind=disp entries failed: .*", None),
    ("census g=", _star("census"), None), ("disarmed input=", _star("disarmed"), None),
    ("flushed g=", _star("flushed"), None), ("heavy g=", _star("heavy"), None),
    ("menu seg=", _star("menu"), None), ("menu_armed segments=", _star("menu_armed"), None),
    ("menu_base base_us=", _star("menu_base"), None), ("menu_done why=", _star("menu_done"), None),
    ("offthread g=", _star("offthread"), None), ("opened g=", _star("opened"), None),
    ("p pt=", _star("p"), None), ("plant c_plant=", _star("plant"), None), ("refusals why=", _star("refusals"), None),
    ("settled g=", _star("settled"), None), ("spans g=", _star("spans"), None), ("w pt=", _star("w"), None),
    # failure lines (FAILURE_EVENTS, RAW_FAILURES and the other warnings) and traces, read by their words
    ("FT-GATE patched ", _msg("FT-GATE patched"), None), ("FT-GATE report failed: ", _msg("FT-GATE report failed:"), None),
    ("FT-ROOM joined offline=", _msg("FT-ROOM joined"), None), ("FT-ROOM read failed: ", _msg("FT-ROOM read failed:"), None),
    ("armed room=", _msg("armed"), None), ("churn freeze failed: ", _msg("churn freeze failed:"), None),
    ("churn timer frozen room=", _msg("churn timer frozen"), None),
    ("clock refused: player-loop phase missing (EarlyUpdate ", _msg("clock refused:"), None),
    ("ended why=complete pt=", _msg("ended"), None),
    ("ft room options max=2 visible=0 room=", _msg("ft room options"), None),
    ("ft_dll staging failed: ", _msg("ft_dll staging failed:"), None),
    ("game end failed: ", _msg("game end failed:"), None), ("game over failed: ", _msg("game over failed:"), None),
    ("game start failed: ", _msg("game start failed:"), None),
    ("game start failed: menu=1 process", _msg("game start failed:"), None),
    ("menu_wait input=", _msg("menu_wait"), None), ("not armed input=", _msg("not armed"), None),
    ("opened line failed: ", _msg("opened line failed:"), None), ("peer ", _msg("peer"), None),
    ("photon patches report failed: ", _msg("photon patches report failed:"), None),
    ("ranked-check skipped", _msg("ranked-check skipped"), None),
    ("ranked-check test hook answered true", _msg("ranked-check test hook answered true"), None),
    ("reference collectors not installed: patch classes skipped=", _msg("reference collectors not installed:"), None),
    ("refused what=", _msg("refused"), None),
    ("rematch answer failed: ", _msg("rematch answer failed:"), None),
    ("rematch held: published ", _msg("rematch held:"), None),
    ("rematch mutant: answered Yes at once", _msg("rematch mutant: answered Yes at once"), None),
    ("rematch not answered (sitting over)", _msg("rematch not answered (sitting over)"), None),
    ("rematch publish failed: ", _msg("rematch publish failed:"), None),
    ("rematch timeout g=", _msg("rematch timeout"), None), ("rematch yes g=", _msg("rematch yes"), None),
    ("room call refused op=", _msg("room call refused"), None), ("room name=", _msg("room"), None),
    ("self-drive ", _msg("self-drive"), None), ("self-drive join failed: ", _msg("self-drive join failed:"), None),
    ("self-drive join room=", _msg("self-drive join"), None), ("self-drive pick index=", _msg("self-drive pick"), None),
    ("self-drive spawn threw: ", _msg("self-drive spawn threw:"), None),
    ("self-drive spawn tick failed: ", _msg("self-drive spawn tick failed:"), None),
    ("staged ", _msg("staged"), None), ("start failed: ", _msg("start failed:"), None),
    ("steam ticket withheld route=", _msg("steam ticket withheld"), None),
)
_FORMS_RE = [re.compile(p) for _, p, _ in FORMS]


def unknown_forms(text):
    """Every [FRAME-TIME] line of text whose payload (the text after '[FRAME-TIME] ', trailing space dropped) no FORMS
    pattern matches: [(1-based line number, payload)]."""
    out = []
    for n, ln in enumerate(text.splitlines(), 1):
        i = ln.find("[FRAME-TIME] ")
        if i < 0:
            continue
        pay = ln[i + len("[FRAME-TIME] "):].rstrip()
        if not any(r.fullmatch(pay) for r in _FORMS_RE):
            out.append((n, pay))
    return out


def zero_state(recs):
    """VR8, part 1: game 0 (the mutant) must have every round void; reports the void rounds of the measured
    games and the games left with no valid round. Returns (ok, game-0 void, game-0 rounds, measured void, empty)."""
    void = void_rounds(recs)
    rounds = set((r["game"], r["round"]) for r in recs if r["kind"] == "p")
    g0 = [x for x in rounds if x[0] == 0]
    g0v = [x for x in g0 if x in void]
    meas = sorted(x for x in void if x[0] >= 1)
    games = set(x[0] for x in rounds if x[0] >= 1)
    empty = sorted(g for g in games if all((g, r) in void for (gg, r) in rounds if gg == g))
    return bool(g0) and len(g0v) == len(g0), len(g0v), len(g0), meas, empty


def contrast_c(points):
    """One game's frame-weighted ON-minus-OFF C per frame (cycles; ratio of sums), and its frames N_g."""
    son = sum(p["sC"] for p in points if p["arm"] == "ON")
    non = sum(p["n"] for p in points if p["arm"] == "ON")
    soff = sum(p["sC"] for p in points if p["arm"] == "OFF")
    noff = sum(p["n"] for p in points if p["arm"] == "OFF")
    if non == 0 or noff == 0:
        raise Refused("a game without both arms")
    return son / non - soff / noff, non + noff


def dC(recs, z=Z_END):
    """dC in cycles per frame: (est, one-sided half-width, df, lag-1 of the per-game contrasts)."""
    g = games_of(recs)
    dw = [contrast_c(g[k]) for k in sorted(g)]
    est, hw, df = fw_interval(dw, z)
    return est, hw, df, lag1([d for d, w in dw])


def _fhat(recs):
    return {r["g"]: r["f_hat"] for r in recs if r["kind"] == "settled"}


def dC_us(recs, z=Z_END, first_game=1):
    """dC in microseconds per frame: each game's frame-weighted contrast in cycles over that game's f_hat (V4 3.2:
    C in us is cycles / f_hat), then fw_interval at z. Returns (est, hw, df, lag-1)."""
    fh = _fhat(recs)
    g = games_of(recs, first_game)
    dw = []
    for k in sorted(g):
        if fh.get(k, 0) <= 0:
            raise Refused("no f_hat for game %d" % k)
        d, n = contrast_c(g[k])
        dw.append((d * 1e6 / fh[k], n))
    est, hw, df = fw_interval(dw, z)
    return est, hw, df, lag1([d for d, w in dw])


def d_up(recs, z=Z_END, first_game=1):
    """D_up (V4 3.6, F14; round-1 HIGH 3): n_k_max is entry k's largest per-game mean of calls per ON live frame
    (the census's on count over the game's ON live frames, the live frames of its gate-clear points, measured
    games); per calibration j at a game start, D_j = sum over entries of n_k_max x d_kj, d_kj the per-call
    closed-path cost of entry k's shape in calibration j (mean over its batches of (patched - unpatched) / n, us by
    the settled Stopwatch frequency); D_up = max(mean + t(z, J - 1) SE, largest D_j).
    Returns (D_up, [D_j], {entry: n_k_max})."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("D_up needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    on_frames = {}
    for g, pts in games_of(recs, first_game).items():
        on_frames[g] = sum(q["live_frames"] for q in pts if q["gate"] == 0)
    rate, shape = {}, {}
    for r in recs:
        if r["kind"] != "census" or r["g"] < first_game or r["g"] not in on_frames:
            continue
        if on_frames[r["g"]] <= 0:
            raise Refused("game %d has no ON live frames" % r["g"])
        k = r["entry"]
        if shape.setdefault(k, r["shape"]) != r["shape"]:
            raise Refused("entry %s has two shapes (%s, %s)" % (k, shape[k], r["shape"]))
        rate[k] = max(rate.get(k, 0.0), r["on"] / on_frames[r["g"]])
    rate = {k: v for k, v in rate.items() if v > 0}
    if not rate:
        raise Refused("no entry ran in ON live frames")
    cals = {}
    for r in recs:
        if r["kind"] == "cal" and r.get("why", "").startswith("game") and r.get("ckind") == "disp" and not r.get("failed"):
            u = [int(x) for x in r["u"].split(",")]
            pp = [int(x) for x in r["p"].split(",")]
            if len(u) != len(pp) or not u:
                raise Refused("cal i=%d shape=%s: batch lists differ" % (r["i"], r["shape"]))
            cost = sum(b - a for a, b in zip(u, pp)) / len(u) / r["n"] * 1e6 / f
            cals.setdefault(r["i"], {})[r["shape"]] = cost
    if len(cals) < 2:
        raise Refused("D_up needs at least two game-start calibrations (got %d)" % len(cals))
    ds = []
    for i in sorted(cals):
        miss = sorted(set(shape[k] for k in rate if shape[k] not in cals[i]))
        if miss:
            raise Refused("calibration %d has no line for shapes %s" % (i, miss))
        ds.append(sum(rate[k] * cals[i][shape[k]] for k in rate))
    j = len(ds)
    m = sum(ds) / j
    se = math.sqrt(sum((v - m) ** 2 for v in ds) / (j - 1) / j)
    return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate


# the zero proofs the parser can check (ruling FRAME-TIME-ROUND-R3-A1, round-3 MEDIUM ft_parse.py:540):
# sweep:no-live-write, which survivor_sweep.py verifies per row against the sources (the parser requires that no a3
# line counts a write for the row), and probe:a3zero, which needs one a3zero line per measured game for the row with
# starts equal to the game's point lines, written 0 and faults 0 (no build writes a3zero lines today, so a row
# claiming it cannot pass)
ZERO_PROOFS = ("sweep:no-live-write", "probe:a3zero")


def proof_records(recs, spec, last_game=None):
    """Every proof token's evidence (round-3 MEDIUM): present and consistent, contrary evidence refused."""
    games = sorted(set(q["game"] for q in recs if q["kind"] == "p" and q["game"] >= 1
                       and (last_game is None or q["game"] <= last_game)))
    for n, sid, kind, why, proof in spec:
        a3l = [r for r in recs if r["kind"] == "a3" and r.get("k") == n]
        if kind == "zero":
            wr = [r for r in a3l if r.get("writes_on", 0) != 0]
            if wr:
                raise Refused("A3 row %s (%s): zero by %s, but game %d counts %d live writes (contrary evidence)"
                              % (n, sid, proof, wr[0]["g"], wr[0]["writes_on"]))
            if proof == "probe:a3zero":
                for g in games:
                    rows = [r for r in recs if r["kind"] == "a3zero" and r.get("g") == g and r.get("k") == n]
                    npts = sum(1 for q in recs if q["kind"] == "p" and q["game"] == g)
                    if len(rows) != 1:
                        raise Refused("A3 row %s (%s): probe:a3zero needs one a3zero line in game %d (got %d)"
                                      % (n, sid, g, len(rows)))
                    r = rows[0]
                    if r.get("starts", -1) != npts or r.get("written", -1) != 0 or r.get("faults", -1) != 0:
                        raise Refused("A3 row %s (%s): game %d a3zero starts=%s written=%s faults=%s (needs starts %d, "
                                      "written 0, faults 0)" % (n, sid, g, r.get("starts"), r.get("written"),
                                                                r.get("faults"), npts))
        elif kind == "drained":
            if any(r["kind"] == "a3zero" and r.get("k") == n for r in recs):
                raise Refused("A3 row %s (%s): drained, but a3zero lines name it (contrary proof)" % (n, sid))


def a3_spec():
    """The A3 inventory (gate_specs/a3.py, from SURVIVORS.md): [(name, survivor id, "dependent" | "drained" | "zero",
    reason, proof)]. Kinds are default-deny (ruling FRAME-TIME-ROUND-R2 (1)): "zero" only with a proof reference,
    sweep:... (survivor_sweep.py proves no write site reachable in the measured span) or probe:... (an executed
    probe); "drained" only by its executed probe (probe:a3drain, FtA3.PointStart at every point's first live frame);
    every other row is "dependent", counted and calibrated."""
    here = os.path.dirname(os.path.abspath(__file__))
    return runpy.run_path(os.path.join(here, "gate_specs", "a3.py"))["A3"]


LIVE_PROOF = "live:executed"

# round-5 MEDIUM (ft_parse.py:637), ruling FRAME-TIME-ROUND-R5: the fields a stand-in line carries (a failure, a
# withholding, a planning value). ONE predicate refuses any of them on a live row's a3 calibration line, whether or not
# the line carries the live marker: a live=1 line with withheld=1, failed: or u/p/n is not an executed line.
STAND_IN = ("withheld", "failed", "u", "p", "n")


def stand_in(r):
    """The stand-in fields an a3 calibration line carries ([] for a clean executed line)."""
    return [x for x in STAND_IN if x in r]


def fhat_ok(fh, why):
    """One successful f_hat calibration line for the run: why as named, f_hat above 0, its spins dk/dt list."""
    return (len(fh) == 1 and fh[0].get("why") == why and isinstance(fh[0].get("f_hat"), int) and fh[0]["f_hat"] > 0
            and re.fullmatch(r"\d+/\d+(,\d+/\d+)*", str(fh[0].get("spins", ""))) is not None)


def a3_live(recs, spec=None, first_game=1, last_game=LAST_GAME):
    """Ruling FRAME-TIME-ROUND-R4: the in-game executed calibration of the live rows (a3.py proof live:executed),
    whose real readers run only in live combat. The build times every live reader method of such a row in its own
    body (FtA3.TEnter/TExit, exclusive of nested reader scopes) and writes per game one line
    cal i=<the game's start calibration> why=game<g> kind=a3 k=<row> live=1 reads= scopes= ticks= tmax= unscoped=
    depth_err=. d_k is the largest, over the measured games with reads, of ticks / reads (us by the Stopwatch
    frequency): the executed exclusive cost of the row's reader bodies per live read, so r_k_max x d_k bounds the
    row's per-frame read cost from above (its reads_win are a subset of its scoped reads). Refuses when a live row
    carries a planning (u/p), withheld or failed calibration line, when a non-live row carries a live line, when a
    game 0 to last_game lacks exactly one live line for a live row or that line is not under the game's start
    calibration, when its reads differ from the game's a3 line reads_on or any read ran outside a scope (unscoped)
    or a scope was unbalanced (depth_err), and when no measured game executed a read of the row (that row is
    WITHHELD, ruling FRAME-TIME-ROUND-R5: never planned from scratch). Every a3 calibration line naming an inventory
    row is judged by one predicate (round-5 MEDIUM, ft_parse.py:637): the row must be live, and the line must carry the
    live marker and none of the stand-in fields (STAND_IN), so a live=1 line with withheld=1, failed: or a planning
    value is refused like one without the marker. Returns ({k: d_k us}, {k: [(g, reads, scopes, ticks, tmax)]})."""
    spec = a3_spec() if spec is None else spec
    live = [n for n, sid, kind, why, proof in spec if kind == "dependent" and proof == LIVE_PROOF]
    names = set(row[0] for row in spec)
    a3c = [r for r in recs if r["kind"] == "cal" and r.get("ckind") == "a3"]
    for r in a3c:
        k = r.get("k")
        # a name outside the inventory is ignored, as every other a3 line of one is (the inventory's own coverage is
        # test_a3_inventory_names_every_survivor_once); every inventory row's a3 calibration line meets ONE predicate
        if k not in names:
            continue
        if k not in live:
            # a drained or zero row carries no a3 calibration line at all (ruling FRAME-TIME-ROUND-R5)
            raise Refused("cal i=%s a3 k=%s: an a3 calibration line for a row the inventory does not mark %s"
                          % (r.get("i"), k, LIVE_PROOF))
        bad = stand_in(r)
        if bad or "live" not in r:
            raise Refused("A3 live row %s: cal i=%s carries a %s line; a live row is calibrated only by its in-game "
                          "executed line (rulings FRAME-TIME-ROUND-R4 and R5)"
                          % (k, r.get("i"), "withheld" if "withheld" in bad else "failed" if "failed" in bad
                             else "planning (u/p)" if bad else "unmarked"))
    if not live:
        return {}, {}
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("A3 live rows need one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    starts = {}
    for r in recs:
        if (r["kind"] == "cal" and re.fullmatch(r"game\d+", str(r.get("why", ""))) and "live" not in r
                and not r.get("failed")):
            starts.setdefault(int(r["why"][4:]), set()).add(r["i"])
    d, det = {}, {}
    for k in live:
        best = None
        for g in range(0, last_game + 1):
            rows = [r for r in a3c if r.get("k") == k and "live" in r and r.get("why") == "game%d" % g]
            if len(rows) != 1:
                raise Refused("A3 live row %s: game %d has %d executed calibration lines (needs 1)" % (k, g, len(rows)))
            r = rows[0]
            gone = [x for x in ("i", "reads", "scopes", "ticks", "tmax", "unscoped", "depth_err") if x not in r]
            if gone or r["live"] != 1:
                raise Refused("A3 live row %s: game %d line lacks %s or live=%s" % (k, g, gone, r.get("live")))
            run = starts.get(g, set())
            if len(run) != 1 or r["i"] not in run:
                raise Refused("A3 live row %s: game %d line i=%d is not the game's start calibration %s"
                              % (k, g, r["i"], sorted(run)))
            if r["unscoped"] != 0 or r["depth_err"] != 0:
                raise Refused("A3 live row %s: game %d unscoped=%d depth_err=%d (needs 0 and 0: every read timed in "
                              "a balanced scope)" % (k, g, r["unscoped"], r["depth_err"]))
            if min(r["reads"], r["scopes"], r["ticks"], r["tmax"]) < 0 or r["scopes"] > r["reads"] or \
                    (r["reads"] == 0) != (r["scopes"] == 0) or r["tmax"] > r["ticks"]:
                raise Refused("A3 live row %s: game %d reads=%d scopes=%d ticks=%d tmax=%d are inconsistent"
                              % (k, g, r["reads"], r["scopes"], r["ticks"], r["tmax"]))
            a3l = [q for q in recs if q["kind"] == "a3" and q.get("g") == g and q.get("k") == k]
            if len(a3l) != 1 or a3l[0].get("reads_on") != r["reads"]:
                raise Refused("A3 live row %s: game %d executed reads %d, the game's a3 line counts %s"
                              % (k, g, r["reads"], [q.get("reads_on") for q in a3l]))
            det.setdefault(k, []).append((g, r["reads"], r["scopes"], r["ticks"], r["tmax"]))
            if g >= first_game and r["reads"] > 0:
                v = r["ticks"] / r["reads"] * 1e6 / f
                best = v if best is None else max(best, v)
        if best is None:
            raise Refused("A3 live row %s: no measured game executed a read of it (its in-game calibration is empty; "
                          "the row is WITHHELD, ruling FRAME-TIME-ROUND-R5)" % k)
        d[k] = best
    return d, det


def a3(recs, z=Z_END, first_game=1, last_game=LAST_GAME, spec=None, peer_recs=None):
    """A3 (ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0), the fifth term of U: a deterministic
    bound on the class (iii) carryover the whole-entry gate leaves. Per content-dependent survivor k, the build
    counts, in every ON point's live frames, the live reads of k whose work can differ from an always-ON game's:
    those made before k reaches its steady state (writes since the point's first live frame below k's capacity,
    the code constant), or every read when k has no steady state (it accumulates over the game). r_k_max is the
    largest per-game count of such reads over the game's ON live frames (frame-weighted, as D_up's n_k_max).
    Ruling FRAME-TIME-ROUND-R5 retires the scratch (game-start) calibration for every dependent row: each is
    calibrated only by its in-game executed lines (proof live:executed, a3_live), read from BOTH seats' logs, d_k the
    larger of the two seats' largest per-game executed cost per read, and A3 = sum_k r_k_max x d_k (one value, the
    same for every game; returned as the single A_j). A dependent row without the live proof is refused, a row with no
    executed read in any measured game is withheld (a3_live), and a log without the peer's is refused whenever a
    dependent row exists (round-5 MEDIUM, ft_parse.py:1643). Zero rows add nothing and are listed. A drained row adds nothing only because the build saw
    it empty at the first live frame of every point of the game: its a3drain line must say so (starts above 0,
    nonempty 0, faults 0). Refuses when the spec names no structure, when a row's kind is unknown or a zero or
    drained row has no reason, when a dependent structure lacks its a3 line in a measured game (or carries two) or
    its calibration line in a game-start calibration, or when a drained row lacks its a3drain line (or carries two)
    or reports a point that started with it holding entries. A live row (proof live:executed, ruling
    FRAME-TIME-ROUND-R4) takes its d_k from its in-game executed lines (a3_live), the same in every A_j; with
    peer_recs (the other seat's log) its executed lines are required and validated too, and d_k is the larger of the
    two seats'. Returns (A3, [A_j], {k: r_k_max}, {k: mean d_k us})."""
    spec = a3_spec() if spec is None else spec
    if not spec:
        raise Refused("the A3 inventory names no structure")
    for row in spec:
        if len(row) != 5:
            raise Refused("A3 row %r: needs (name, survivor id, kind, reason, proof)" % (row,))
    dep = [n for n, sid, kind, why, proof in spec if kind == "dependent"]
    drained = [n for n, sid, kind, why, proof in spec if kind == "drained"]
    for n, sid, kind, why, proof in spec:
        if kind not in ("dependent", "drained", "zero") or (kind != "dependent" and not why.strip()):
            raise Refused("A3 row %s (%s): kind %r needs a reason when zero or drained" % (n, sid, kind))
        # ruling FRAME-TIME-ROUND-R2 (1), default-deny: zero only with a proof the sweep checks (sweep:...) or an
        # executed probe (probe:...); drained only by its executed probe (FtA3.PointStart's a3drain lines)
        if kind == "zero" and not re.fullmatch(r"(sweep|probe):\S+", proof):
            raise Refused("A3 row %s (%s): a zero row needs its proof reference (sweep:... or probe:...), got %r"
                          % (n, sid, proof))
        # round-3 MEDIUM (ft_parse.py:540): a proof token is a claim about records; it is accepted only when the
        # records it names are present and consistent (proof_records), and a token naming no known evidence is refused
        if kind == "zero" and proof not in ZERO_PROOFS:
            raise Refused("A3 row %s (%s): zero proof %r names no evidence the parser can check (known: %s)"
                          % (n, sid, proof, ", ".join(sorted(ZERO_PROOFS))))
        if kind == "drained" and proof != "probe:a3drain":
            raise Refused("A3 row %s (%s): a drained row's proof is its probe (probe:a3drain), got %r" % (n, sid, proof))
        if kind == "dependent" and proof != LIVE_PROOF:
            raise Refused("A3 row %s (%s): a dependent row is calibrated only by its in-game executed lines, proof %s "
                          "(ruling FRAME-TIME-ROUND-R5: the scratch A3 is retired), got %r" % (n, sid, LIVE_PROOF, proof))
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("A3 needs one Stopwatch frequency (got %s)" % sorted(freq))
    proof_records(recs, spec, last_game)
    # round-5 MEDIUM (ft_parse.py:1643): the dependent rows' in-game calibration is read from both seats' logs; no
    # caller computes A3 from one seat's log
    if dep and peer_recs is None:
        raise Refused("A3: the dependent rows' in-game calibration is read from both seats' logs; no peer log was given")
    # rulings FRAME-TIME-ROUND-R4 and R5: every dependent row's in-game executed calibration, from both logs; a withheld,
    # failed or planning line of any row is refused by a3_live's one predicate (it replaces round 4's separate
    # withheld-row refusal, which only ever saw this seat's log)
    ld, _ = a3_live(recs, spec, first_game, last_game)
    pd, _ = a3_live(peer_recs, spec, first_game, last_game) if peer_recs is not None else ({}, {})
    ld = {k: max(v, pd[k]) for k, v in ld.items()}
    on_frames = {}
    for g, pts in games_of(recs, first_game).items():
        if last_game is None or g <= last_game:
            on_frames[g] = sum(q["live_frames"] for q in pts if q["gate"] == 0)
    if not on_frames:
        raise Refused("A3 needs measured games")
    rate = {}
    for k in dep:
        for g in sorted(on_frames):
            rows = [r for r in recs if r["kind"] == "a3" and r.get("g") == g and r.get("k") == k]
            if len(rows) != 1:
                raise Refused("A3 structure %s: game %d has %d a3 lines (needs 1)" % (k, g, len(rows)))
            if on_frames[g] <= 0:
                raise Refused("game %d has no ON live frames" % g)
            rate[k] = max(rate.get(k, 0.0), rows[0]["reads_win"] / on_frames[g])
    for k in drained:
        for g in sorted(on_frames):
            rows = [r for r in recs if r["kind"] == "a3drain" and r.get("g") == g and r.get("k") == k]
            if len(rows) != 1:
                raise Refused("A3 drained structure %s: game %d has %d a3drain lines (needs 1)" % (k, g, len(rows)))
            r = rows[0]
            npts = sum(1 for q in recs if q["kind"] == "p" and q["game"] == g)
            if r.get("starts", -1) != npts:
                raise Refused("A3 drained structure %s: game %d probed at %s point starts, the game has %d points"
                              % (k, g, r.get("starts"), npts))
            if r.get("starts", 0) <= 0 or r.get("nonempty", -1) != 0 or r.get("faults", -1) != 0:
                raise Refused("A3 drained structure %s: game %d starts=%s nonempty=%s faults=%s (needs starts > 0, "
                              "nonempty 0, faults 0)" % (k, g, r.get("starts"), r.get("nonempty"), r.get("faults")))
    if not dep:
        return 0.0, [], {}, {}
    # ruling FRAME-TIME-ROUND-R5: d_k is the executed in-game cost per read (the larger seat's largest game), the same
    # in every game, so A3 is the one sum; there is no scratch A_j left to spread over calibrations
    a3v = sum(rate[k] * ld[k] for k in dep)
    return a3v, [a3v], rate, {k: ld[k] for k in dep}


def t_ref(recs, first_game=1):
    """T_ref (V4 section 0): the mean F of the OFF points' unplanted frames, us."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("T_ref needs one Stopwatch frequency (got %s)" % sorted(freq))
    pts = [q for v in games_of(recs, first_game).values() for q in v if q["arm"] == "OFF"]
    n = sum(q["n"] for q in pts)
    if n <= 0:
        raise Refused("no OFF frames")
    return sum(q["sF"] for q in pts) * 1e6 / freq.pop() / n


FPSCAP_HOLD = "[FPSCAP] held by frame-time calibration"
FPSCAP_RELEASED = "[FPSCAP] released ("


def _until_last_settled(text):
    """The log's lines up to and including its last [FRAME-TIME] settled line (the sitting's end): an armfile removed
    after the sitting releases the hold, and the cap may then engage, outside every measured frame."""
    ls = text.splitlines()
    last = max([i for i, ln in enumerate(ls) if "[FRAME-TIME] settled " in ln], default=len(ls) - 1)
    return ls[:last + 1]


def vr1(recs, text, tref, name="T_ref"):
    """VR1, no cap (ruling FRAME-TIME-ROUND-R6-A3): up to the last settled line the log carries the frame-time
    calibration hold's line ("[FPSCAP] held by frame-time calibration": the mod's frame-rate cap held off while the
    armfile is present, proven reached by its own line, lesson #83) and no other [FPSCAP] line; every settled line
    vsync 0 and target -1 or above 1000; the frame time tref (named name: T_ref, or T_on in sitting V, ruling
    R6-A3.11.149 (6) 3) not within 2 percent of 1e6 / k for k in 60, 75, 120, 144, 165, 240."""
    bad = []
    caps = [ln.strip() for ln in _until_last_settled(text) if "[FPSCAP]" in ln]
    if not any(FPSCAP_HOLD in ln for ln in caps):
        bad.append("no '%s' line: the hold is not proven reached" % FPSCAP_HOLD)
    other = [ln for ln in caps if FPSCAP_HOLD not in ln]
    if other:
        bad.append("an [FPSCAP] line other than the hold is present: %s" % other[0][other[0].find("[FPSCAP]"):])
    for r in recs:
        if r["kind"] == "settled" and r["g"] >= 0:
            if r.get("vsync", 0) != 0:
                bad.append("settled g=%d vsync=%d" % (r["g"], r["vsync"]))
            tg = r.get("target", -1)
            if not (tg == -1 or tg > 1000):
                bad.append("settled g=%d target=%d" % (r["g"], tg))
    for k in (60, 75, 120, 144, 165, 240):
        if abs(tref - 1e6 / k) <= 0.02 * (1e6 / k):
            bad.append("%s %.1f us within 2 percent of 1e6/%d" % (name, tref, k))
    return not bad, bad


def vr4(hw_us, tref):
    """VR4, resolution: dC's one-sided half-width at 0.9875 at most 1.5 percent of T_ref."""
    return hw_us <= 0.015 * tref


def predecessor(recs, first_game=1):
    """VR8's predecessor check (V4 3.3): each first-in-round ON point's mean C (us, by its game's f_hat) minus its
    round's OFF mean, grouped by the arm of the previous round's last point (the point line's pred; first rounds
    have pred none and drop out); FLAG when (after-ON mean - after-OFF mean) - 1.96 x Welch SE > 0.
    Returns (flag, after-ON values, after-OFF values)."""
    fh = _fhat(recs)
    g = games_of(recs, first_game)
    groups = {"ON": [], "OFF": []}
    for k in sorted(g):
        rounds = {}
        for q in g[k]:
            rounds.setdefault(q["round"], []).append(q)
        for pts in rounds.values():
            first = [q for q in pts if q["point"] == 1 and q["arm"] == "ON" and q.get("pred") in ("ON", "OFF")]
            off = [q for q in pts if q["arm"] == "OFF" and q["n"] > 0]
            if not first or not off or first[0]["n"] <= 0:
                continue
            x = first[0]["sC"] / first[0]["n"] - sum(q["sC"] for q in off) / sum(q["n"] for q in off)
            groups[first[0]["pred"]].append(x * 1e6 / fh[k])
    a, b = groups["ON"], groups["OFF"]
    if len(a) < 2 or len(b) < 2:
        raise Refused("predecessor check needs two rounds in each group (got %d and %d)" % (len(a), len(b)))
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((v - ma) ** 2 for v in a) / (len(a) - 1)
    vb = sum((v - mb) ** 2 for v in b) / (len(b) - 1)
    return (ma - mb) - 1.96 * math.sqrt(va / len(a) + vb / len(b)) > 0, a, b


def vr9(recs, bound_us, first_game=1):
    """VR9, absorption: the gated spans' ON live time per live frame (span_g over live_frames at ON points, us by
    the settled frequency), frame-weighted over games, at its lower 97.5 percent end, at most the bound
    max(0, dC_up) / min(1, e_C_lo). Returns (ok, lower end)."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("VR9 needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    g = games_of(recs, first_game)
    sw = []
    for k in sorted(g):
        on = [q for q in g[k] if q["arm"] == "ON"]
        lf = sum(q["live_frames"] for q in on)
        if lf > 0:
            sw.append((sum(q["span_g"] for q in on) * 1e6 / f / lf, sum(q["n"] for q in on)))
    est, hw, _ = fw_interval(sw, _ND.inv_cdf(0.975))
    return est - hw <= bound_us, est - hw


def b3(recs):
    """B3 (V4 3.9), placement: no heavy operation (record builds, queue writes, the pump, answers, the hashing
    thread's start, a hash completed on the main thread) ran in a live-combat frame: neither with CombatLive true
    at its call, in any moment (at_call), nor in a frame that started live whose combat ended before the call
    (edge; round-1 MEDIUM, FtHeavy.cs:39); and the hashing job's interval [hash_t0, hash_t1] lies clear of every
    point's live interval [t0, t1]. Off-thread calls are reported, not judged.
    Returns (ok, reasons, {op: (at_call, edge, off, live-moment calls)})."""
    hv = [r for r in recs if r["kind"] == "heavy"]
    if not hv:
        raise Refused("B3 needs heavy lines (one per operation per game)")
    # round-2 MEDIUM (ft_parse.py:611): complete records, never a pass by absence: every game with point lines
    # has exactly one heavy line per operation of FtHeavy.Names and exactly one offthread line
    for g in sorted(set(q["game"] for q in recs if q["kind"] == "p" and q["game"] >= 0)):
        for op in HEAVY_OPS:
            n = sum(1 for r in hv if r.get("g") == g and r.get("op") == op)
            if n != 1:
                raise Refused("B3: game %d has %d heavy lines for %s (needs 1)" % (g, n, op))
        alien = sorted(set(r.get("op") for r in hv if r.get("g") == g) - set(HEAVY_OPS))
        if alien:
            raise Refused("B3: game %d has heavy lines for unknown operations %s" % (g, alien))
        n = sum(1 for r in recs if r["kind"] == "offthread" and r.get("g") == g)
        if n != 1:
            raise Refused("B3: game %d has %d offthread lines (needs 1)" % (g, n))
    ops = {}
    for r in hv:
        a, e, o, lv = ops.get(r["op"], (0, 0, 0, 0))
        ops[r["op"]] = (a + r["at_call"], e + r["edge"], o + r["off"], lv + r["live"])
    bad = ["%s ran %d times with combat live" % (op, v[0]) for op, v in sorted(ops.items()) if v[0] > 0]
    bad += ["%s ran %d times in a live frame after combat ended (edge)" % (op, v[1])
            for op, v in sorted(ops.items()) if v[1] > 0]
    pts = [(q["t0"], q["t1"], q["pt"]) for q in recs if q["kind"] == "p" and "t0" in q]
    if not pts:
        raise Refused("B3 needs point lines carrying t0 and t1")
    jobs = set((r["hash_t0"], r["hash_t1"]) for r in recs if r["kind"] == "offthread" and r["hash_t0"] > 0)
    for a, b in sorted(jobs):
        if b < a:
            bad.append("the hashing job started at %d had not ended at a game over" % a)
            b = max(q[1] for q in pts)
        hit = [q[2] for q in pts if a < q[1] and q[0] < b]
        if hit:
            bad.append("the hashing job [%d, %d] overlaps live points %s" % (a, b, ", ".join(hit[:5])))
    return not bad, bad, ops


def disarms(recs):
    """FtArm's disarm lines (the predicate failed after arming): ['<input> at <pt>']."""
    return ["%s at %s" % (r.get("input", "?"), r.get("pt", "?")) for r in recs if r["kind"] == "disarmed"]


def vr6_build(recs):
    """VR6's build half (FORMAT-M-PLAN.md V2 part b): the latest refusals line (why=quit when present, else the
    last game over) gives every refused what:route pair's count and every allowed route's send count; a route that
    was both refused and sent fails, and any disarmed line makes the sitting INVALID. The file listings before and
    after are the runner's half. The dispatched and sent counts come from one patch class, FtRoute_SendPatch: when it
    never attached both stay at zero and agree, so this comparison rests on the validity set's ATTACH guard, which
    requires that class's entry fully attached (ruling R6-A3.11.151 (2) class A, F2). Returns (ok, reasons, {pair:
    count}, [disarm inputs])."""
    lines = [r for r in recs if r["kind"] == "refusals"]
    dis = disarms(recs)
    if not lines:
        raise Refused("VR6 needs a refusals line (game over or quit)")
    quit_ = [r for r in lines if r.get("why") == "quit"]
    last = (quit_ or lines)[-1]
    pairs = last["pairs_kv"]
    bad = []
    refused_routes = set(k.split(":", 1)[1] for k in pairs if k.startswith("route:"))
    sent_routes = set(k.split(":", 1)[1] for k in pairs if k.startswith("sent:"))
    for r in sorted(refused_routes & sent_routes):
        bad.append("route %s both refused and sent" % r)
    # round-1 MEDIUM (FtRoute.cs:97): the dispatch counter is independent of the classifier (a postfix that sees
    # the original actually run); every dispatched route must be an allowed one, as often as it was counted sent
    disp = dict((k.split(":", 1)[1], v) for k, v in pairs.items() if k.startswith("dispatched:"))
    sent = dict((k.split(":", 1)[1], v) for k, v in pairs.items() if k.startswith("sent:"))
    for r in sorted(set(disp) | set(sent)):
        if disp.get(r, 0) != sent.get(r, 0):
            bad.append("route %s dispatched %d times, sent %d" % (r, disp.get(r, 0), sent.get(r, 0)))
    if dis:
        bad.append("disarmed: " + "; ".join(dis))
    return not bad, bad, pairs, dis


def f18(recs, first_game=1):
    """F18 (build brief section 5): the reading the settled lines name (one for the sitting). Under A each
    measured game has an answer_replay line with result=settled, and the replay's time (us by the settled
    frequency) is reported apart from the between-point figure; under B there is no answer_replay line and every
    settled and point line carries answer=unmeasured. Returns (ok, reading, reasons, [replay us per game])."""
    st = [r for r in recs if r["kind"] == "settled" and r["g"] >= first_game]
    readings = set(r.get("f18") for r in st)
    if len(readings) != 1 or None in readings:
        raise Refused("F18 needs one reading named on every measured settled line (got %s)" % sorted(map(str, readings)))
    reading = readings.pop()
    rep = [r for r in recs if r["kind"] == "answer_replay"]
    bad = []
    us = []
    if reading == "A":
        freq = set(r["freq"] for r in recs if r["kind"] == "settled")
        f = freq.pop() if len(freq) == 1 else None
        games = sorted(set(r["g"] for r in st))
        byg = dict((r["g"], r) for r in rep)
        for g in games:
            r = byg.get(g)
            if r is None:
                bad.append("game %d has no answer_replay line" % g)
            elif r.get("result") != "settled":
                bad.append("game %d replay result %s" % (g, r.get("result")))
            elif f:
                us.append(r["ticks"] * 1e6 / f)
    elif reading == "B":
        if rep:
            bad.append("%d answer_replay lines under reading B" % len(rep))
        for r in recs:
            if r["kind"] in ("settled", "p") and r.get("g", r.get("game", 0)) >= first_game \
                    and r.get("answer") != "unmeasured":
                bad.append("%s line without answer=unmeasured" % r["kind"])
                break
    else:
        bad.append("unknown reading %s" % reading)
    return not bad, reading, bad, us


def _side_plain(r):
    """B2's sides: the window's arm; planted windows take no side (M5: exposure and VR7 only)."""
    return r["arm"] if r.get("plant", 0) == 0 else None


def _side_vr7(r):
    """VR7's sides, OFF windows only: planted windows stand in the ON place, unplanted in the OFF place."""
    if r["arm"] != "OFF":
        return None
    return "ON" if r.get("plant", 0) else "OFF"


def b2_per_minute(ub_per_frame, tr):
    """B2's bound per minute of live combat at T_ref (METHOD-V4.md section 3.8's report; round-1 MEDIUM 16):
    the per-frame bound times the frames a minute holds at T_ref microseconds per frame."""
    if tr <= 0:
        raise Refused("T_ref must be positive (got %r)" % tr)
    return ub_per_frame * 60e6 / tr


def longest_frames(recs, first_game=1):
    """The longest ON and the longest OFF live frame of the measured games, in ms by the settled Stopwatch
    frequency (the point lines' maxF; reported, round-1 MEDIUM 16)."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("longest frames need one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    out = {}
    for r in recs:
        if r["kind"] == "p" and r["game"] >= first_game:
            out[r["arm"]] = max(out.get(r["arm"], 0), r["maxF"])
    if "ON" not in out or "OFF" not in out:
        raise Refused("longest frames need point lines of both arms (got %s)" % sorted(out))
    return {a: v * 1000.0 / f for a, v in out.items()}


def dc_minus_ds(recs):
    """dC minus dS, us per live frame (reported, round-1 MEDIUM 16): the cycle estimate in us less the
    wall-clock-on-thread estimate, both the point-level contrasts the report prints."""
    return dC_us(recs)[0] - d_key_us(recs, "sS", "ticks")[0]


def hitch(recs, first_game=1, side=_side_plain):
    """B2 (V4 3.8): per H, the FAIL test on K_ON_min against K_OFF_max and the upper bound UB on K_ON_max against
    K_OFF_min, per frame, with each arm's dispersion bound over its per-game counts. Full windows only; games
    with full windows on both sides only."""
    per = {}
    for r in recs:
        if r["kind"] != "w" or r.get("partial", 1) != 0 or r["game"] < first_game:
            continue
        arm = side(r)
        if arm is None:
            continue
        key = (arm, r["game"])
        a = per.setdefault(key, {"n": 0, "k": {h: [0, 0] for h in H_MS}})
        a["n"] += r["n"] - 2
        for h in H_MS:
            kmin, kmax = r["e%d" % h]
            a["k"][h][0] += kmin
            a["k"][h][1] += kmax
    games = sorted(g for g in set(g for arm, g in per) if ("ON", g) in per and ("OFF", g) in per)
    if len(games) < 2:
        raise Refused("fewer than two games with full windows on both sides")
    out = {}
    for h in H_MS:
        n_on = [per[("ON", g)]["n"] for g in games]
        n_off = [per[("OFF", g)]["n"] for g in games]
        on_min = [per[("ON", g)]["k"][h][0] for g in games]
        on_max = [per[("ON", g)]["k"][h][1] for g in games]
        off_min = [per[("OFF", g)]["k"][h][0] for g in games]
        off_max = [per[("OFF", g)]["k"][h][1] for g in games]
        fail = rate_lb(on_min, n_on) - rate_ub(off_max, n_off) > 0
        ub = rate_ub(on_max, n_on) - rate_lb(off_min, n_off)
        out[h] = {"fail": fail, "ub_per_frame": ub, "ub_per_1000": ub * 1000.0}
    return out


def vr7(recs, first_game=1):
    """VR7, the hitch control: B2's test on planted against unplanted OFF windows (a constant planted cost, no
    stall) must not FAIL at any H."""
    out = hitch(recs, first_game, _side_vr7)
    bad = ["H=%d ms FAIL" % h for h in H_MS if out[h]["fail"]]
    return not bad, bad


def e_c(recs, z=Z_END, first_game=1):
    """V4 3.5: C's response to the plant at OFF points, as the control's v4_reading reads it. Per OFF point with
    planted and unplanted frames, (planted mean C - unplanted mean C) / c_plant in cycles (c_plant us x the game's
    f_hat / 10^6); per game the mean over those points; over games batch_interval at z. Returns (mean, hw, df,
    e_lo, games used, games without a planted OFF point)."""
    cp = [r["c_plant"] for r in recs if r["kind"] == "plant"]
    if len(cp) != 1 or cp[0] <= 0:
        raise Refused("e_C needs exactly one plant line with c_plant > 0 (got %s)" % cp)
    fh = {r["g"]: r["f_hat"] for r in recs if r["kind"] == "settled"}
    games = games_of(recs, first_game)
    es, missing = [], []
    for g in sorted(games):
        if g not in fh or fh[g] <= 0:
            raise Refused("no f_hat for game %d" % g)
        unit = cp[0] * fh[g] / 1e6
        v = [(q["psC"] / q["pn"] - q["sC"] / q["n"]) / unit for q in games[g]
             if q["arm"] == "OFF" and q.get("pn", 0) > 0 and q["n"] > 0]
        if v:
            es.append(sum(v) / len(v))
        else:
            missing.append(g)
    if len(es) < 3:
        raise Refused("e_C needs planted OFF points in at least three games (got %d)" % len(es))
    m, hw, df = batch_interval(es, z)
    return m, hw, df, m - hw, len(es), missing


MATCH_PLAN_W_US = 293.2               # R6-A3.2 (2): the menu's w x 2, the planning input until the match measures its own


def match_power(recs, z=Z_END, first_game=1, margin=MENU_PLAN_MARGIN):
    """Report only, never judged (ruling FRAME-TIME-ROUND-R6-A3.3 (2a)): the match scene's own window noise and the
    game count VR2's e_C_lo >= 0.5 needs from it. w: the median over OFF points (at least three complete unplanted
    windows) of the SD of the point's unplanted 120-frame window means of C, in us by the game's f_hat. Per game,
    e_C is the mean of its OFF points' e values (e_c), so the model's per-game SE is
    margin x w x sqrt(mean over the game's planted OFF points of (1/n_p + 1/n_u)) / sqrt(points) / c_plant, its
    median over games used; the observed per-game SD is that of e_c's per-game values. G needed is the least G with
    (t_q(z, floor(G/2) - 1) + MENU_PLAN_ZPOW) x s / sqrt(G) <= 0.5, at the model SE (the margin applied) and at the
    observed SD. Returns report lines."""
    cp = [r["c_plant"] for r in recs if r["kind"] == "plant"]
    if len(cp) != 1 or cp[0] <= 0:
        return ["match power: not computable (needs exactly one plant line with c_plant > 0, got %s)" % cp]
    cpu = cp[0]
    fh = {r["g"]: r["f_hat"] for r in recs if r["kind"] == "settled"}
    games = games_of(recs, first_game)
    wins = {}
    for r in recs:
        if r["kind"] == "w" and r.get("game", -1) >= first_game and r.get("arm") == "OFF" and not r.get("partial") \
                and r.get("n", 0) > 0:
            wins.setdefault((r["game"], r["round"], r["point"]), []).append(r)
    sds = []
    for (g, rd, pt), ws in wins.items():
        u = [w["sC"] / w["n"] for w in ws if not w.get("plant")]
        if len(u) >= 3 and fh.get(g, 0) > 0:
            sds.append(statistics.stdev(u) / (fh[g] / 1e6))
    if not sds:
        return ["match power: no OFF point with three complete unplanted window lines, w not measured"]
    w = statistics.median(sds)
    per_game_se, per_game_e = [], []
    for g in sorted(games):
        if fh.get(g, 0) <= 0:
            continue
        unit = cpu * fh[g] / 1e6
        inv, ev = [], []
        for q in games[g]:
            if q["arm"] != "OFF" or q.get("pn", 0) <= 0 or q["n"] <= 0:
                continue
            ws = wins.get((g, q["round"], q["point"]), [])
            npl = sum(1 for x in ws if x.get("plant"))
            nun = sum(1 for x in ws if not x.get("plant"))
            if npl > 0 and nun > 0:
                inv.append(1.0 / npl + 1.0 / nun)
            ev.append((q["psC"] / q["pn"] - q["sC"] / q["n"]) / unit)
        if inv:
            per_game_se.append(margin * w * math.sqrt(sum(inv) / len(inv)) / math.sqrt(len(inv)) / cpu)
        if ev:
            per_game_e.append(sum(ev) / len(ev))

    def g_need(s):
        for k in range(4, 100000):
            if (t_q(z, k // 2 - 1) + MENU_PLAN_ZPOW) * s / math.sqrt(k) <= 0.5:
                return k
        return -1
    out = ["match power: w %.1f us over %d OFF points (planning %.1f us, measured margin %.2f)"
           % (w, len(sds), MATCH_PLAN_W_US, w / MATCH_PLAN_W_US)]
    if per_game_se:
        s_model = statistics.median(per_game_se)
        out.append("match power: model per-game SE %.3f at margin %.1f over %d games: G needed %d"
                   % (s_model, margin, len(per_game_se), g_need(s_model)))
    if len(per_game_e) >= 2:
        s_obs = statistics.stdev(per_game_e)
        out.append("match power: observed per-game SD of e_C %.3f over %d games: G needed %d"
                   % (s_obs, len(per_game_e), g_need(s_obs)))
    return out


def vr5(recs, first_game=0, last_game=None):
    """VR5 (V4 3.7): the expected records present (vr5_records) and the census rules hold (vr5_points)."""
    ok1, bad1 = vr5_records(recs, first_game, last_game)
    ok2, bad2 = vr5_points(recs)
    return ok1 and ok2, bad1 + bad2


def vr5_records(recs, first_game=0, last_game=None):
    """VR5's records (round-1 HIGH 5, a positive completeness requirement): in every game present (or every game
    first_game..last_game when last_game is given), one opened line showing all three collectors opened (se, ce,
    ic = 1), and exactly one census line for every registered entry (gate_specs/entries.py) with its registered
    shape. Missing, duplicated or unregistered records fail; nothing passes by absence."""
    bad = []
    exp = dict(expected_entries())
    games = set(r["game"] for r in recs if r["kind"] == "p" and r["game"] >= first_game)
    if last_game is not None:
        games |= set(range(first_game, last_game + 1))
    if not games:
        bad.append("no game to check")
    for g in sorted(games):
        op = [r for r in recs if r["kind"] == "opened" and r.get("g") == g]
        if len(op) != 1:
            bad.append("g=%d: %d opened lines (needs 1)" % (g, len(op)))
        else:
            shut = [c for c in OPENED if op[0].get(c) != 1]
            if shut:
                bad.append("g=%d: collection not opened: %s" % (g, ",".join(shut)))
        seen = {}
        for r in recs:
            if r["kind"] == "census" and r["g"] == g:
                seen[r["entry"]] = seen.get(r["entry"], 0) + 1
                if r["entry"] in exp and r.get("shape") != exp[r["entry"]]:
                    bad.append("g=%d %s shape %s, registered %s" % (g, r["entry"], r.get("shape"), exp[r["entry"]]))
        gone = sorted(e for e in exp if e not in seen)
        if gone:
            bad.append("g=%d: %d census records missing (%s)" % (g, len(gone), ", ".join(gone[:4])))
        dup = sorted(e for e, n in seen.items() if n > 1)
        if dup:
            bad.append("g=%d: census records duplicated (%s)" % (g, ", ".join(dup[:4])))
        alien = sorted(e for e in seen if e not in exp)
        if alien:
            bad.append("g=%d: census records not registered (%s)" % (g, ", ".join(alien[:4])))
    return not bad, bad


# ruling R6-A3.11.151 (2) class B: the point line's VR5 counters at window granularity (plugin/FtFrames.cs:214-215,
# printed at :274; attributed under the gate of the frame that closed, FtClock.OnStart calling OnFrameClosed before the
# boundary moves the gate): off_g and off_gn, gated span ticks and calls while the window's gate was off; off_on,
# census calls that ran their body while it was off; on_guarded, guarded returns while it was open. Each is 0 when the
# gate does what it says.
GATE_COUNTERS = ("off_g", "off_gn", "off_on", "on_guarded")


def gate_counter_faults(recs, valid):
    """The point lines (of valid, a set of pt, or every point line when None) whose GATE_COUNTERS are not printed or
    not 0, as reasons naming each counter and its points."""
    why = []
    for k in GATE_COUNTERS:
        bad = [q["pt"] for q in recs if q["kind"] == "p" and (valid is None or q["pt"] in valid) and q.get(k, 1) != 0]
        if bad:
            why.append("%s above 0 or not printed at %s%s" % (k, ", ".join(bad[:4]),
                                                               " and %d more" % (len(bad) - 4) if len(bad) > 4 else ""))
    return why


def vr5_points(recs):
    """VR5's rules: every entry that ran in ON live frames shows guarded returns in OFF live frames, per game; and
    per point, a gated point has no gated span time, no gated span call and no census call with the gate clear,
    an ungated point no guarded return. In a V6 log (one carrying B11 window lines) every point line also carries
    the same rules at window granularity (gate_counter_faults)."""
    bad = gate_counter_faults(recs, None) if any(b11_line(r) for r in recs) else []
    for r in recs:
        if r["kind"] == "census" and r["on"] > 0 and r["guarded"] == 0:
            bad.append("g=%d %s" % (r["g"], r["entry"]))
        if r["kind"] == "p" and "span_g" in r:
            if r["gate"] == 1 and (r["span_g"] or r["span_gn"] or r["on_calls"]):
                bad.append("pt=%s gated: span_g=%d span_gn=%d on_calls=%d" % (r["pt"], r["span_g"], r["span_gn"],
                                                                          r["on_calls"]))
            if r["gate"] == 0 and r["guarded"]:
                bad.append("pt=%s open: guarded=%d" % (r["pt"], r["guarded"]))
        # B11 (method-v52.md:87, kept by method-v54.md:183): arms switch per window, so the zero is per window: an
        # OFF window executes no switched scope
        if b11_line(r) and r["arm"] == "OFF" and r["cS"] != 0:
            bad.append("window %s.%d OFF: cS=%d" % (r["pt"], r["wi"], r["cS"]))
    return not bad, bad


def k_up(recs, z=Z_END, first_game=1):
    """K_up (V4 3.3, F13): per game, the upkeep spans' elapsed time per live frame over both arms (sum of span_u
    over sum of live_frames, in microseconds by the settled line's Stopwatch frequency); over games fw_interval at
    z, weighted by the game's measured frames. Returns (est, hw, k_up)."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("K_up needs one Stopwatch frequency across settled lines (got %s)" % sorted(freq))
    f = freq.pop()
    g = games_of(recs, first_game)
    kw = []
    for k in sorted(g):
        pts = g[k]
        if any("span_u" not in q for q in pts):
            raise Refused("game %d has a point line without span totals" % k)
        lf = sum(q["live_frames"] for q in pts)
        nn = sum(q["n"] + q.get("pn", 0) for q in pts)
        kw.append((sum(q["span_u"] for q in pts) * 1e6 / f / lf, nn))
    est, hw, _ = fw_interval(kw, z)
    return est, hw, est + hw


COUNTER_KEYS = ("missing_end", "cycle_failures", "span_depth_violations")
# P1's V6 emitter (via the integrator, 12 Nov): a V6 log's counters line adds span_leave_mismatch (a Photon scope's
# finalizer found the class stack at another depth than its prefix left: it must be 0, in VR2's class with
# span_depth_violations) and photon_offmain (X and listener scopes entered off the main thread: reported only, no rule
# reads its value). A V6 log's line without either is faulted as one without span_depth_violations is
COUNTER_KEYS_V6 = ("span_leave_mismatch",)
COUNTER_REPORTED_V6 = ("photon_offmain",)


def counters_faults(recs, games):
    """VR2's counters half: exactly one counters line per game of games (g >= 0), its three counters printed and 0;
    in a V6 log (one carrying B11 window lines) also span_leave_mismatch printed and 0 and photon_offmain printed. A key
    the line carries beyond these is read and left unjudged. Returns the reasons."""
    v6 = any(b11_line(r) for r in recs)
    bad = []
    for g in games:
        if g < 0:
            continue
        cs = [r for r in recs if r["kind"] == "counters" and r.get("g") == g]
        if len(cs) != 1:
            bad.append("game %d: %d counters lines (needs 1, written at its flush)" % (g, len(cs)))
            continue
        for k in COUNTER_KEYS:
            if cs[0].get(k, -1) != 0:
                bad.append("counters g=%d %s=%s" % (g, k, cs[0].get(k)))
        if v6:
            for k in COUNTER_KEYS_V6 + COUNTER_REPORTED_V6:
                if k not in cs[0]:
                    bad.append("counters g=%d %s not printed (a V6 counters line carries it)" % (g, k))
            if cs[0].get("span_leave_mismatch", 0) != 0:
                bad.append("counters g=%d span_leave_mismatch=%s" % (g, cs[0]["span_leave_mismatch"]))
    return bad


def vr2(recs, last_game=None):
    """Instrument (V4 3.7 VR2): every game has a settled line; no frame without FT_End, no cycle-read failure
    and no span open at a frame boundary in any settled line; f_hat within 2 percent; and (round-1 MEDIUM,
    calibration coverage) each game's start calibration complete: one run per game (why=game<g>) with its fhat
    line, its span line and a disp line for every shape the census maps an entry to (the registered table's
    shapes and every shape a census line names). e_C_lo >= 0.5 is judged in report()."""
    sett = [r for r in recs if r["kind"] == "settled"]
    games = set(r["game"] for r in recs if r["kind"] == "p")
    if last_game is not None:
        games |= set(range(0, last_game + 1))
    games = sorted(games)
    have = set(r["g"] for r in sett)
    bad = ["no settled line for game %d" % g for g in games if g not in have]
    shapes = set(s for e, s in expected_entries()) | set(r["shape"] for r in recs if r["kind"] == "census")
    for g in games:
        if g < 0:
            continue
        # a live row's executed line (ruling FRAME-TIME-ROUND-R4) is written at the game's end under the start run's i;
        # it is no start calibration, so it never stands for a missing run
        runs = sorted(set(r["i"] for r in recs if r["kind"] == "cal" and r.get("why") == "game%d" % g
                          and "live" not in r))
        if len(runs) != 1:
            bad.append("game %d: %d calibration runs (needs 1)" % (g, len(runs)))
            continue
        allc = [r for r in recs if r["kind"] == "cal" and r.get("i") == runs[0]]
        # round-4 MEDIUM (ft_parse.py:1132): a failure warning names its kind but is no calibration; any one in the
        # game's run fails VR2, and the coverage below counts successful lines only
        fails = sorted(set(str(r.get("ckind")) for r in allc if r.get("failed")))
        if fails:
            bad.append("game %d: calibration %d carries failure warnings for %s" % (g, runs[0], ", ".join(fails)))
        cl = [r for r in allc if not r.get("failed")]
        if not fhat_ok([r for r in cl if r.get("ckind") == "fhat"], "game%d" % g):
            bad.append("game %d: calibration %d has no successful fhat line (one, why=game%d, f_hat > 0, its spins)"
                       % (g, runs[0], g))
        if not any(r.get("ckind") == "span" for r in cl):
            bad.append("game %d: calibration %d has no span line" % (g, runs[0]))
        got = set(r.get("shape") for r in cl if r.get("ckind") == "disp")
        gone = sorted(shapes - got)
        if gone:
            bad.append("game %d: calibration %d has no disp line for shapes %s" % (g, runs[0], gone))
    for r in sett:
        for k in ("missing_end", "cycle_failures", "span_depth_violations"):
            if r.get(k, 0) != 0:
                bad.append("settled g=%d %s=%d" % (r["g"], k, r[k]))
    # round-3 MEDIUM (FtSchedule.cs:140): a game's settled line is written at its start, before its play, so the last
    # game's play had no health snapshot. FtSchedule.FlushGame writes a counters line after every game's work: one
    # per game is required, each with the three counters at 0 (and a V6 log's two more, counters_faults), and no point
    # line may carry a missed FT_End stamp
    bad += counters_faults(recs, games)
    for r in recs:
        if r["kind"] == "p" and r["game"] >= 0 and r.get("missing_end", 0) != 0:
            bad.append("point %s: missing_end=%d" % (r["pt"], r["missing_end"]))
    fh = [r["f_hat"] for r in sett if r["g"] >= 0 and r.get("f_hat", 0) > 0]
    if fh and (max(fh) - min(fh)) > 0.02 * min(fh):
        bad.append("f_hat spread %d..%d exceeds 2 percent" % (min(fh), max(fh)))
    return not bad, bad


MENU_LEVELS = ("3", "5")              # ruling FRAME-TIME-ROUND-R6-A3.2 (1): 0.5 and 1.5 percent dropped


def menu_power(recs, seg, lv, z=Z_END):
    """Report only (ruling FRAME-TIME-ROUND-R6-A3.2 (1) and (3)): the menu length's planning model re-run on this run's
    own noise. w is the median over segments of the SD of the unplanted 120-frame window means of C (complete
    windows; us by the segment's f_hat); per level, the model's per-segment SE (MENU_PLAN_MARGIN x w x
    sqrt(1/n_p + 1/n_u) / c_plant, with this run's mean planted and unplanted windows per segment) against the
    observed SD of the segments' e_C, and the k the formula needs at each:
    (t_q(z, floor(k/2) - 1) + MENU_PLAN_ZPOW) x s / sqrt(k) <= MENU_EC_LO_MIN."""
    out = []
    win = {}
    for r in recs:
        if r["kind"] == "w" and r.get("game") == -1 and not r.get("plant") and not r.get("partial") and r.get("n", 0) > 0:
            win.setdefault(r["round"], []).append(r["sC"] / r["n"])
    sds = []
    for s, ms in win.items():
        if len(ms) >= 3 and s in seg and (seg[s].get("f_hat") or 0) > 0:
            sds.append(statistics.stdev(ms) / (seg[s]["f_hat"] / 1e6))
    if not sds:
        return ["menu power: no complete unplanted window lines, w not measured"]
    w = statistics.median(sds)

    def k_need(s):
        for k in range(4, 100000):
            if (t_q(z, k // 2 - 1) + MENU_PLAN_ZPOW) * s / math.sqrt(k) <= MENU_EC_LO_MIN:
                return k
        return -1
    out.append("menu power: w %.1f us over %d segments (planning %.1f us, measured margin %.2f)"
               % (w, len(sds), MENU_PLAN_W_US, w / MENU_PLAN_W_US))
    for L in MENU_LEVELS:
        ks = sorted(s for s in seg if seg[s].get("level") == L and seg[s].get("arm") == "OFF"
                    and seg[s].get("p") and seg[s]["p"].get("pn", 0) > 0 and seg[s].get("c_plant", 0) > 0)
        v = [x[0] for x in lv.get(L, [])]
        if len(ks) < 2 or len(v) < 2:
            out.append("menu power level %s percent: fewer than two planted OFF segments" % L)
            continue
        wp = [sum(1 for r in recs if r["kind"] == "w" and r.get("game") == -1 and r["round"] == s and r.get("plant"))
              for s in ks]
        wu = [sum(1 for r in recs if r["kind"] == "w" and r.get("game") == -1 and r["round"] == s and not r.get("plant"))
              for s in ks]
        np_, nu_ = sum(wp) / len(wp), sum(wu) / len(wu)
        cp = sum(seg[s]["c_plant"] for s in ks) / len(ks)
        if np_ <= 0 or nu_ <= 0:
            out.append("menu power level %s percent: no planted or no unplanted windows" % L)
            continue
        s_model = MENU_PLAN_MARGIN * w * math.sqrt(1 / np_ + 1 / nu_) / cp
        s_obs = statistics.stdev(v)
        out.append("menu power level %s percent: %d segments, c_plant %.0f us, windows %.1f/%.1f; model SE %.3f"
                   " (k needed %d), observed SD %.3f (k needed %d)"
                   % (L, len(v), cp, np_, nu_, s_model, k_need(s_model), s_obs, k_need(s_obs)))
    return out


def menu_check(recs, z=Z_END):
    """The menu self-check (METHOD-V4.md section 6 step 2; plugin/FtMenu.cs). Segments are FtMenu's menu lines with
    their point lines (pt=-1.<seg>.1), in log order. Judged: (1) the run completed (one menu_done line,
    why=complete, segs equal to of); (2) every segment has its point line, the gate the sentinel's force implies
    (none: OFF segments gated) on both lines, and missing_end 0; (3) the A/A: per pair with both arms, the
    unplanted mean F of ON minus OFF in us (by the settled lines' Stopwatch freq), batch_interval at z, and the
    two-sided interval must contain 0; (4) e_C at each of the two levels (3 and 5 percent): per OFF segment with
    planted and unplanted frames, (psC/pn - sC/n) / (c_plant x f_hat / 10^6) with the menu calibration in force at
    that segment, batch_interval over the level's segments (at least four); decision 21'' (ruling
    FRAME-TIME-ROUND-R6-A3.2, superseding R1-A1's decision 21'): the two-sided interval contains 1 and excludes 0,
    and at MENU_EC_LO_LEVEL its lower end e_C_lo is at least MENU_EC_LO_MIN; an OFF segment with a planted level and
    no planted window is a named failure; e_F and e_S (by freq) reported; the planning model's power figures are
    reported against the run's own window noise (menu_power), never judged; (5) f_hat over the menu calibrations
    within 2 percent; (6) the last settled line shows no frame without FT_End, no cycle failure and no span depth
    violation. Returns (ok, report lines, failures)."""
    sett = [r for r in recs if r["kind"] == "settled"]
    freq = set(r["freq"] for r in sett)
    if len(freq) != 1:
        raise Refused("the menu check needs one Stopwatch frequency across settled lines (got %s)" % sorted(freq))
    f = freq.pop()
    done = [r for r in recs if r["kind"] == "menu_done"]
    if len(done) != 1:
        raise Refused("the menu check needs exactly one menu_done line (got %d)" % len(done))
    bad, lines = [], []
    d = done[0]
    if d.get("why") != "complete" or d.get("segs") != d.get("of"):
        bad.append("run not complete: why=%s, %s of %s segments" % (d.get("why"), d.get("segs"), d.get("of")))
    force = sett[-1].get("force", "none")
    seg, fh, fhs = {}, None, []
    for r in recs:
        if (r["kind"] == "cal" and r.get("ckind") == "fhat" and str(r.get("why", "")).startswith("menu")
                and not r.get("failed")):
            fh = r["f_hat"]
            fhs.append(fh)
        elif r["kind"] == "menu":
            seg[r["seg"]] = dict(r, f_hat=fh)
        elif r["kind"] == "p" and r["game"] == -1 and r["round"] in seg:
            seg[r["round"]]["p"] = r
    if not fhs:
        raise Refused("no menu calibration line")
    # round-3 MEDIUM (ft_parse.py:1077): every menu calibration cycle menu_done counts has its fhat line, once, and a
    # settled line follows menu_done (the terminal snapshot (6) judges); a deleted failing record must not pass
    cyc = d.get("cycles")
    whys = [str(r.get("why")) for r in recs if r["kind"] == "cal" and r.get("ckind") == "fhat"
            and str(r.get("why", "")).startswith("menu") and not r.get("failed")]
    if cyc is None or sorted(whys) != sorted("menu%d" % c for c in range(cyc)):
        bad.append("menu calibrations %s, menu_done counts %s cycles" % (sorted(whys), cyc))
    idone = max(i for i, r in enumerate(recs) if r["kind"] == "menu_done")
    post = [r for r in recs[idone + 1:] if r["kind"] == "settled"]
    if len(post) != 1:
        raise Refused("the menu check needs exactly one settled line after menu_done (got %d)" % len(post))
    terminal = post[0]
    # round-4 MEDIUM (ft_parse.py:1219): a menu run carries two snapshots, at their own positions: the startup one
    # (Plugin's FtCalib.Settled(-1, -1) before FtMenu arms, so before menu_armed, c_plant -1) and the terminal one
    # (FtMenu's FtCalib.Settled after menu_done, judged above and required); no game starts in a menu run, so
    # FtSchedule writes none, and a settled line anywhere else is not this run's
    iarm = [i for i, r in enumerate(recs) if r["kind"] == "menu_armed"]
    if len(iarm) != 1:
        bad.append("%d menu_armed lines (needs 1)" % len(iarm))
    else:
        pre = [r for r in recs[:iarm[0]] if r["kind"] == "settled"]
        if len(pre) != 1 or pre[0].get("g") != -1 or pre[0].get("c_plant") != -1:
            bad.append("startup snapshot: %d settled lines before menu_armed (needs 1, g=-1 c_plant=-1)" % len(pre))
        mid = [r for r in recs[iarm[0]:idone] if r["kind"] == "settled"]
        if mid:
            bad.append("%d settled lines inside the menu run (only the startup and the terminal snapshot belong to it)"
                       % len(mid))
    # ruling FRAME-TIME-ROUND-R6-A1: a failed entry calibration is named by its shape (a patch that did not attach)
    mfail = sorted(set(("%s %s %s" % (r.get("why", "-"), r.get("ckind"), r["shape"])) if r.get("shape") else
                       ("%s %s" % (r.get("why", "-"), r.get("ckind")))
                       for r in recs if r["kind"] == "cal" and r.get("failed")))
    if mfail:
        bad.append("menu run carries calibration failure warnings: %s" % ", ".join(mfail))
    bad += failure_events(recs)
    # the absent-record sweep (ruling FRAME-TIME-ROUND-R2): every segment FtMenu counted has its menu line, and every
    # menu point line its segment; a dropped menu line must not leave its segment out of the judgement
    want_segs = list(range(1, (d.get("of") or 0) + 1))
    if sorted(seg) != want_segs:
        bad.append("menu lines for segments %s, menu_done counts %s" % (sorted(seg), d.get("of")))
    orphan = sorted(r["round"] for r in recs if r["kind"] == "p" and r["game"] == -1 and r["round"] not in seg)
    if orphan:
        bad.append("menu point lines with no menu line: segments %s" % orphan)
    pairs, lv, unplanted, offw = {}, {}, [], []
    for s in sorted(seg):
        m = seg[s]
        p = m.get("p")
        if p is None:
            bad.append("segment %d has no point line" % s)
            continue
        want = 1 if force == "OFF" or (force == "none" and m["arm"] == "OFF") else 0
        if m["gate"] != want or p["gate"] != want or p["arm"] != m["arm"]:
            bad.append("segment %d: arm %s gate %d/%d, force=%s wants %d" % (s, m["arm"], m["gate"], p["gate"], force,
                                                                              want))
        if p.get("missing_end", 0):
            bad.append("segment %d: missing_end=%d" % (s, p["missing_end"]))
        # round-2 MEDIUM (FtClock.cs:144): menu frames are never a combat point's closing frame; a segment with an
        # excluded frame or no measured frame is a defect, not a smaller sample
        if p.get("excl", 0) != 0 or p["n"] <= 0:
            bad.append("segment %d: excl=%d n=%d (a menu segment measures every frame)" % (s, p.get("excl", 0), p["n"]))
        if p["n"] > 0:
            pairs.setdefault(m["pair"], {})[m["arm"]] = p
        # ruling FRAME-TIME-ROUND-R6-A3 (2): an OFF segment with a planted level and no planted window is named, never
        # a silent drop from its level's count; every such segment's window count is reported
        if m["arm"] == "OFF" and m.get("c_plant", 0) > 0:
            offw.append("%d:%s:%d:%d" % (s, m["level"], p.get("windows", -1), p.get("pn", 0)))
            if p.get("pn", 0) <= 0:
                unplanted.append("%d (level %s, %d windows, n %d)" % (s, m["level"], p.get("windows", -1), p["n"]))
        if m["arm"] == "OFF" and m.get("c_plant", 0) > 0 and p.get("pn", 0) > 0 and p["n"] > 0:
            cp = m["c_plant"]
            ec = (p["psC"] / p["pn"] - p["sC"] / p["n"]) / (cp * m["f_hat"] / 1e6)
            ef = (p["psF"] / p["pn"] - p["sF"] / p["n"]) * 1e6 / f / cp
            es = (p["psS"] / p["pn"] - p["sS"] / p["n"]) * 1e6 / f / cp
            lv.setdefault(m["level"], []).append((ec, ef, es))
    lines.append("menu OFF segments with a planted level (segment:level:windows:planted frames): %s"
                 % (" ".join(offw) or "none"))
    # ruling FRAME-TIME-ROUND-R6-A3.2: a planted level outside MENU_LEVELS is a build that is not this check's
    outside = sorted(set(seg[s]["level"] for s in seg if seg[s].get("c_plant", 0) > 0) - set(MENU_LEVELS))
    if outside:
        bad.append("segments planted at levels outside %s: %s" % (", ".join(MENU_LEVELS), ", ".join(outside)))
    if unplanted:
        bad.append("OFF segments with a planted level and no planted window: %s" % ", ".join(unplanted))
    ds = [(q["ON"]["sF"] / q["ON"]["n"] - q["OFF"]["sF"] / q["OFF"]["n"]) * 1e6 / f
          for k, q in sorted(pairs.items()) if "ON" in q and "OFF" in q]
    if len(ds) < 4:
        raise Refused("the A/A needs at least four complete pairs (got %d)" % len(ds))
    est, hw, df = batch_interval(ds, z)
    aa_ok = est - hw <= 0 <= est + hw
    lines.append("menu A/A ON-OFF %.2f us per frame, interval %.2f..%.2f at z %.4f, df %d, %d pairs: %s"
                 % (est, est - hw, est + hw, z, df, len(ds), "contains 0" if aa_ok else "EXCLUDES 0"))
    if not aa_ok:
        bad.append("A/A interval %.2f..%.2f us excludes 0" % (est - hw, est + hw))
    for L in MENU_LEVELS:
        v = lv.get(L, [])
        if len(v) < 4:
            bad.append("level %s percent: %d planted OFF segments (needs 4)" % (L, len(v)))
            continue
        m_, h_, df_ = batch_interval([x[0] for x in v], z)
        lines.append("menu e_C level %s percent: %.4f, lower end %.4f, df %d, %d segments; e_F %.4f, e_S %.4f"
                     % (L, m_, m_ - h_, df_, len(v), sum(x[1] for x in v) / len(v), sum(x[2] for x in v) / len(v)))
        # decision 21'' (ruling FRAME-TIME-ROUND-R6-A3.2): the interval contains 1 and excludes 0 at each level;
        # e_C_lo at least MENU_EC_LO_MIN at MENU_EC_LO_LEVEL
        if not (m_ - h_ <= 1.0 <= m_ + h_):
            bad.append("level %s percent: e_C interval %.4f..%.4f does not contain 1" % (L, m_ - h_, m_ + h_))
        if m_ - h_ <= 0.0 <= m_ + h_:
            bad.append("level %s percent: e_C interval %.4f..%.4f does not exclude 0" % (L, m_ - h_, m_ + h_))
        if L == MENU_EC_LO_LEVEL and m_ - h_ < MENU_EC_LO_MIN:
            bad.append("level %s percent: e_C_lo %.4f below %.1f" % (L, m_ - h_, MENU_EC_LO_MIN))
    lines += menu_power(recs, seg, lv, z)
    lines.append("menu f_hat %d..%d over %d calibrations" % (min(fhs), max(fhs), len(fhs)))
    if max(fhs) - min(fhs) > 0.02 * min(fhs):
        bad.append("f_hat spread %d..%d exceeds 2 percent" % (min(fhs), max(fhs)))
    for k in ("missing_end", "cycle_failures", "span_depth_violations"):
        if terminal.get(k, -1) != 0:
            bad.append("terminal settled line %s=%s" % (k, terminal.get(k)))
    return not bad, lines, bad


MENU_SEG_FLOOR = 10


def menu_framerate(text):
    """The menu sitting's frame-rate state (ruling FRAME-TIME-ROUND-R6-A3 (3)), read from the log in line order. The
    arm is the startup settled line (g=-1, armfile=1). The hold line ("[FPSCAP] held by frame-time calibration")
    follows the arm and precedes menu_done, with no [FPSCAP] line between the arm and the hold. From the hold (or,
    when it is missing, from the arm) to menu_done the only [FPSCAP] line admitted is the release of a cap the mod
    owned ("[FPSCAP] released ("): no engaged, deep idle, stage change, re-assert or hold-released line. The closing
    settled line's target and vsync equal the opening one's. Every menu segment's frames (n + pn: a planted OFF
    segment's n leaves its planted frames out) are at least one tenth of the first segment's. Every failure is
    named; a missing hold line does not stop the other checks. Returns (ok, lines, bad)."""
    bad, lines = [], []
    arm = hold = done = None
    settled, segs, caps = [], {}, []
    for i, ln in enumerate(text.splitlines()):
        if "[FPSCAP]" in ln:
            caps.append((i, ln.strip()[ln.strip().find("[FPSCAP]"):]))
            if hold is None and FPSCAP_HOLD in ln:
                hold = i
            continue
        r = parse_line(ln)
        if r is None:
            continue
        if r["kind"] == "settled" and r.get("g") == -1:
            settled.append(r)
            if arm is None and str(r.get("armfile")) == "1":
                arm = i
        elif r["kind"] == "menu_done" and done is None:
            done = i
        elif r["kind"] == "p" and r.get("game") == -1 and r["round"] not in segs:
            segs[r["round"]] = r
    if arm is None:
        bad.append("no startup settled line with armfile=1 (the arm)")
    if done is None:
        bad.append("no menu_done line")
    if hold is None:
        bad.append("no '%s' line: the hold is not proven reached" % FPSCAP_HOLD)
    elif arm is not None and done is not None and not (arm < hold < done):
        bad.append("the hold line (log line %d) is not between the arm (line %d) and menu_done (line %d)"
                   % (hold + 1, arm + 1, done + 1))
    if arm is not None and hold is not None:
        pre = [c for c in caps if arm < c[0] < hold]
        if pre:
            bad.append("an [FPSCAP] line between the arm and the hold: line %d %s" % (pre[0][0] + 1, pre[0][1]))
    start = hold if hold is not None else arm
    if start is not None and done is not None:
        mid = [c for c in caps if start < c[0] < done and FPSCAP_RELEASED not in c[1]]
        for c in mid[:3]:
            bad.append("an [FPSCAP] line between the %s and menu_done: line %d %s"
                       % ("hold" if hold is not None else "arm", c[0] + 1, c[1]))
        if len(mid) > 3:
            bad.append("%d more [FPSCAP] lines between the %s and menu_done" % (len(mid) - 3, "hold" if hold is not None else "arm"))
    if len(settled) < 2:
        bad.append("%d settled g=-1 lines (needs the opening and the closing one)" % len(settled))
    else:
        o, c = settled[0], settled[-1]
        lines.append("menu frame rate: opening settled target=%s vsync=%s, closing target=%s vsync=%s"
                     % (o.get("target"), o.get("vsync"), c.get("target"), c.get("vsync")))
        if (o.get("target"), o.get("vsync")) != (c.get("target"), c.get("vsync")):
            bad.append("the closing settled line's target=%s vsync=%s differs from the opening one's target=%s vsync=%s"
                       % (c.get("target"), c.get("vsync"), o.get("target"), o.get("vsync")))
    if not segs:
        bad.append("no menu segment point lines")
    else:
        fr = {s: segs[s]["n"] + segs[s].get("pn", 0) for s in sorted(segs)}
        s0 = min(fr)
        low = [s for s in fr if fr[s] * MENU_SEG_FLOOR < fr[s0]]
        lines.append("menu segment frames (n + pn): first %d (segment %d), least %d (segment %d), %d segments"
                     % (fr[s0], s0, min(fr.values()), min(fr, key=fr.get), len(fr)))
        if low:
            bad.append("segments below one tenth of the first segment's %d frames: %s"
                       % (fr[s0], ", ".join("%d (%d)" % (s, fr[s]) for s in low)))
    return not bad, lines, bad


def menu_report(recs, text=None):
    out = ["MENU self-check (one launch, no room)"]
    try:
        ok, lines, bad = menu_check(recs)
        rawf = raw_failure_events(text) if text is not None else []
        ok, bad = ok and not rawf, bad + rawf
        out += lines
        out.append("MENU %s%s" % ("PASS" if ok else "FAIL: ", "; ".join(bad)))
    except Refused as e:
        out.append("MENU not computable: %s" % e)
    if text is not None:
        fok, flines, fbad = menu_framerate(text)
        out += flines
        out.append("MENU FRAMERATE %s%s" % ("PASS" if fok else "FAIL: ", "; ".join(fbad)))
    return "\n".join(out)


def _freq1(recs, what):
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("%s needs one Stopwatch frequency (got %s)" % (what, sorted(freq)))
    return freq.pop()


def contrast_key(points, key):
    """One game's frame-weighted ON-minus-OFF mean of a per-frame sum (unplanted frames), and its frames."""
    son = sum(p.get(key, 0) for p in points if p["arm"] == "ON")
    non = sum(p["n"] for p in points if p["arm"] == "ON")
    soff = sum(p.get(key, 0) for p in points if p["arm"] == "OFF")
    noff = sum(p["n"] for p in points if p["arm"] == "OFF")
    if non == 0 or noff == 0:
        raise Refused("a game without both arms")
    return son / non - soff / noff, non + noff


def d_key_us(recs, key, unit, z=Z_END, first_game=1):
    """V4 section 0's reported differences: dF and dS (ticks, unit "ticks": us by the settled frequency) and dP,
    the process's CPU over all threads (cycles, unit "cycles": us by each game's f_hat), frame-weighted ON minus OFF
    over games with fw_interval at z. Returns (est, hw, df)."""
    g = games_of(recs, first_game)
    fh = _fhat(recs)
    f = _freq1(recs, "d" + key) if unit == "ticks" else None
    dw = []
    for k in sorted(g):
        if any(key not in q for q in g[k]):
            raise Refused("game %d has a point line without %s" % (k, key))
        d, n = contrast_key(g[k], key)
        if unit == "ticks":
            dw.append((d * 1e6 / f, n))
        else:
            if fh.get(k, 0) <= 0:
                raise Refused("no f_hat for game %d" % k)
            dw.append((d * 1e6 / fh[k], n))
    return fw_interval(dw, z)


def e_key(recs, key, z=Z_END, first_game=1):
    """e_F or e_S (V4 3.5, reported, never judged): per OFF point with planted and unplanted frames, (planted mean -
    unplanted mean) in us by the settled frequency over c_plant us; per game the mean; batch_interval at z."""
    cp = [r["c_plant"] for r in recs if r["kind"] == "plant"]
    if len(cp) != 1 or cp[0] <= 0:
        raise Refused("needs exactly one plant line with c_plant > 0")
    f = _freq1(recs, "e_" + key)
    pk = "p" + key
    es = []
    for g, pts in sorted(games_of(recs, first_game).items()):
        v = [(q[pk] / q["pn"] - q[key] / q["n"]) * 1e6 / f / cp[0] for q in pts
             if q["arm"] == "OFF" and q.get("pn", 0) > 0 and q["n"] > 0]
        if v:
            es.append(sum(v) / len(v))
    if len(es) < 3:
        raise Refused("needs planted OFF points in at least three games")
    return batch_interval(es, z)


def trend(recs, first_game=1):
    """V4 3.4: the slope of the per-game contrast d_g (us) over the game index, with its two-sided 95 percent
    interval (t on G - 2 df), and the last four games' mean d_g. Returns (slope, half-width, last-four mean)."""
    fh = _fhat(recs)
    g = games_of(recs, first_game)
    xs, ys = [], []
    for k in sorted(g):
        if fh.get(k, 0) <= 0:
            raise Refused("no f_hat for game %d" % k)
        d, n = contrast_c(g[k])
        xs.append(float(k))
        ys.append(d * 1e6 / fh[k])
    if len(xs) < 4:
        raise Refused("the trend needs at least four games")
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    s2 = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys)) / (len(xs) - 2)
    hw = t_q(_ND.inv_cdf(0.975), len(xs) - 2) * math.sqrt(s2 / sxx)
    return b, hw, sum(ys[-4:]) / 4.0


def upkeep_per_arm(recs, first_game=1):
    """V4 3.3 (2): the UPKEEP spans' elapsed time per live frame, per arm (us by the settled frequency)."""
    f = _freq1(recs, "the upkeep per arm")
    out = {}
    for arm in ("ON", "OFF"):
        pts = [q for v in games_of(recs, first_game).values() for q in v if q["arm"] == arm]
        lf = sum(q["live_frames"] for q in pts)
        out[arm] = sum(q.get("span_u", 0) for q in pts) * 1e6 / f / lf if lf else float("nan")
    return out


def stamps_estimate(recs, first_game=1):
    """V4 3.6: format M's own span stamps and census counters at ON points, census calls per ON live frame x the
    calibrated span cost (the span.empty shape, mean over the game-start runs), us; reported, never subtracted."""
    f = _freq1(recs, "the stamp estimate")
    g = games_of(recs, first_game)
    lf = sum(q["live_frames"] for v in g.values() for q in v if q["gate"] == 0)
    calls = sum(q.get("on_calls", 0) for v in g.values() for q in v if q["gate"] == 0)
    cost = []
    for r in recs:
        if (r["kind"] == "cal" and r.get("ckind") == "span" and str(r.get("why", "")).startswith("game")
                and not r.get("failed")):
            u = [int(x) for x in r["u"].split(",")]
            p = [int(x) for x in r["p"].split(",")]
            cost.append(sum(b - a for a, b in zip(u, p)) / len(u) / r["n"] * 1e6 / f)
    if not lf or not cost:
        raise Refused("needs ON live frames and span calibrations")
    return calls / lf * (sum(cost) / len(cost))


def between_after(recs, first_game=1):
    """V4 3.9: between-point span time from transitions that follow ON points only (the between lines), us per
    transition; the transitions after OFF points are counted, not used."""
    f = _freq1(recs, "the between-point figure")
    on = [r for r in recs if r["kind"] == "between" and r.get("g", -1) >= first_game and r.get("after") == "ON"]
    off = [r for r in recs if r["kind"] == "between" and r.get("g", -1) >= first_game and r.get("after") == "OFF"]
    if not on:
        raise Refused("no between line after an ON point")
    return sum(r["ticks"] for r in on) * 1e6 / f / len(on), len(on), len(off)


# ============================================================================ B11: the interleaved window design
# Ruling R6-A3.11.138 as .139 amends it, with .137, .136, method-v53.md:32-48 and method-v54.md. Inside a point each
# run of four windows takes (A, B, 1-A, 1-B): positions 1 and 3 are pair P13, 2 and 4 pair P24, one fresh coin per
# pair, committed by position, kept by a window that ends partial; the parser finds singletons (a pair whose mate never
# ran). The contrast is V5.3's HT estimator on Y_ON = C° and Y_OFF = C° - R_OFF with exact probabilities (1/2 for one
# window; 0 or 1/2 for mates; 1/4 for windows of different pairs), actual frame counts as weights, the earlier-block
# baseline (method-v54.md:131), and the conservative bound for zero-probability exposures (method-v53.md:44-45).
# Every term is an exposure: an assignment of the coins it depends on. Terms on one exposure are one indicator and are
# summed, so a pair is one variance unit (.138 (4)) and the contrast, both arms' carryover in both strata and the
# restoration enter one covariance (.137 (4), .138 (3), .139 (3)).

TENTHS = 10
BIN_FRAMES = 12
WINDOW_FRAMES = TENTHS * BIN_FRAMES       # SHARED.md: bin j = floor(i / 12) + 1 for i = 0..119
UNIT_OF_POS = {1: "P13", 2: "P24", 3: "P13", 4: "P24"}
A_UP = 0.0025                             # method-v52.md:154: within the corrected contrast .0025 upper, .001 lower
A_LO = 0.001
Z_UP = _ND.inv_cdf(1.0 - A_UP)
Z_LO = _ND.inv_cdf(1.0 - A_LO)
BETA_US = 6000.0                          # method-v54.md:131: the VM's frozen baseline when no earlier block exists
# the build markers (the integrator's strings, 11 Nov): each input names its build by exactly one whole payload
MARK_FT = "build variant=FrameTime"
MARK_REF = "build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS"
R_CARRY = ("R-CARRY (accepted risk, rulings R6-A3.11.136 (5), .137 (8)): once GC and the writers are separated, a "
           "predecessor's effect has decayed to zero by a full window's last tenth (d_a10 = 0 in both arms); its "
           "falsifiers are the between-window estimate of d_a10 and the point-level contrast, each at its own precision")
R_COMMON = ("R-COMMON (accepted risk, rulings R6-A3.11.136 (5), .137 (5)): the common scopes' external work is at most "
            "r_U times their direct execution; its falsifier is a no-collector reference whose total common cost "
            "exceeds (1 + r_U) D_common")
# ruling R6-A3.11.141 (3), stated beside the cross-check's interval since .146 (6): their falsifiers (paired reference
# replays) belong to the second build wave, which .146 (7) leaves unbuilt, so they are stated, not checked
R_PATH = ("R-PATH (ruling R6-A3.11.141 (3), cross-check only): from the same start state and inputs, any arm schedule "
          "gives the same ordered gameplay events and the same point-ending wall time, within declared tolerances; "
          "its falsifier (paired reference replays) is not built")
R_PREFIX = ("R-PREFIX (ruling R6-A3.11.141 (3), cross-check only): the cumulative clock displacement over any frame "
            "prefix k is at most k delta + rho(k), and every frame lasts at least f_min > 0; its falsifier is not built")
R_REST = ("R-REST (SHARED.md V6): outside every scope the collectors cost the game's code nothing the contrast would "
          "not show; its check is this interval and its half-width against the band. The contrast cannot see a cost "
          "that stays in OFF windows")
RISKS_NOTE = ("these risks bear on the cross-check only: it can refute U (a lower end above U_hi withholds B1), and it "
              "never confirms it")
CROSS_RISKS = (R_CARRY, R_COMMON, R_PATH, R_PREFIX, R_REST, RISKS_NOTE)


class MarkerRefused(Refused):
    """An input without its role's build marker, with it twice, with the other role's, or with an unknown one."""

    def __init__(self, word, role, src, detail):
        self.word = word
        Refused.__init__(self, "%s: the %s input %s %s" % (word, role, src, detail))


def build_marker(text, role, src):
    """The build marker rule (the integrator, 11 Nov): a measurement input carries exactly one '[FRAME-TIME] build
    variant=FrameTime' line and no reference line; a reference input exactly one FrameTimeRef line and no FrameTime
    line. Each line is matched as a whole payload. Zero, two, the other role's or an unknown build line each refuse
    with their own word: MARKER-ABSENT, MARKER-REPEATED, MARKER-WRONG-ROLE, MARKER-UNKNOWN."""
    want, other = (MARK_FT, MARK_REF) if role == "measurement" else (MARK_REF, MARK_FT)
    got = {MARK_FT: 0, MARK_REF: 0}
    for ln in text.splitlines():
        if "[FRAME-TIME] build" not in ln:
            continue
        # the whole line: one BepInEx prefix, then the payload, which must equal a marker exactly (the FrameTime
        # marker is a prefix of the FrameTimeRef one, so no prefix match may count)
        m = re.fullmatch(r"\[[^\[\]]*\] \[FRAME-TIME\] (.*?)\s*", ln)
        pay = m.group(1) if m else ln
        if pay not in got:
            raise MarkerRefused("MARKER-UNKNOWN", role, src, "carries a build line that is no marker: '%s'" % pay)
        got[pay] += 1
    if got[other]:
        raise MarkerRefused("MARKER-WRONG-ROLE", role, src, "carries %d '%s' line(s)" % (got[other], other))
    if got[want] == 0:
        raise MarkerRefused("MARKER-ABSENT", role, src, "carries no '%s' line" % want)
    if got[want] != 1:
        raise MarkerRefused("MARKER-REPEATED", role, src, "carries %d '%s' lines (needs exactly 1)" % (got[want], want))


def b11_line(r):
    """A B11 window record: a w line carrying the contract's appended fields (read() refuses one carrying only some)."""
    return r["kind"] == "w" and any(k in r for k in B11_FIELDS)


def coin_of(w):
    """The coin that sets window w's arm (ruling .138 (4)): one per committed pair of its point's run, so mates share
    it whether a member ends full or partial; a pair whose mate never ran is a singleton by having one window."""
    return (w["game"], w["round"], w["point"], w["run"], w["unit"])


def coin_value(w):
    """The value of w's coin read off w's arm: positions 1 and 2 take the coin, 3 and 4 its complement."""
    return (1 if w["arm"] == "ON" else 0) ^ (1 if w["pos"] in (3, 4) else 0)


def event(*pairs):
    """The exposure fixing each (coin, value): a sorted tuple, or None when two pairs give one coin two values."""
    d = {}
    for c, v in pairs:
        if d.setdefault(c, v) != v:
            return None
    return tuple(sorted(d.items()))


def event_prob(e):
    return 0.5 ** len(e)


def joint_prob(e, f):
    """method-v53.md:39: compatible exposures have probability 2^-|K_e u K_f|, conflicting ones 0."""
    u = event(*(e + f))
    return 0.0 if u is None else event_prob(u)


def arm_prob(*was):
    """P(every window w takes arm a), (w, a) pairs, under the positional schedule: 1/2 for one window, 0 or 1/2 for
    mates, 1/4 for windows of different pairs."""
    e = event(*((coin_of(w), (1 if a == "ON" else 0) ^ (1 if w["pos"] in (3, 4) else 0)) for w, a in was))
    return 0.0 if e is None else event_prob(e)


def _bins(n):
    """A window's frames by tenth: fixed 12-frame bins from its first live frame (SHARED.md); unreached bins 0."""
    return [max(0, min(BIN_FRAMES, n - BIN_FRAMES * j)) for j in range(TENTHS)]


# SHARED.md (md5 2119eb2e): the writer types in order (FtLedger.TypeNames). log, hash and sock run off the main thread
# and add to the writer cost; recv runs on the main thread, its cycles already inside C: never added a second time
WRITER_TYPES = ("log", "hash", "recv", "sock")
WRITER_ADDED = ("log", "hash", "sock")


def _typed(v, width, na=False):
    """wu (width 2: units, cycles) or tok (width 7) as {type: [ints]}: items type:a:b or type:a,b,...; ';' between
    types. With na=True units and cycles may print NA (a FrameTimeRef log prints sock:NA:NA), read as None. None when
    the text is not of that form or names a type twice."""
    if v == "":
        return {}
    out = {}
    for item in v.split(";"):
        t, _, rest = item.partition(":")
        xs = rest.split(":") if width == 2 else rest.split(",")
        ok = len(xs) == width and all(re.fullmatch(r"-?\d+" if width == 7 else r"\d+", x)
                                      or (na and x == "NA") for i, x in enumerate(xs))
        if not t or not ok or t in out:
            return None
        out[t] = [None if x == "NA" else int(x) for x in xs]
    return out


WA_TYPES = ("log", "hash", "sock")


def _wa(v):
    """wa as {type: bytes or None (NA)}: exactly log, hash and sock in that order, each type:<bytes|NA>; None when the
    text is not of that form."""
    out = {}
    for item in v.split(";"):
        t, _, b = item.partition(":")
        if t in out or not (b == "NA" or re.fullmatch(r"\d+", b)):
            return None
        out[t] = None if b == "NA" else int(b)
    return out if tuple(out) == WA_TYPES else None


def window_faults(w):
    """One B11 window's own invariants (SHARED.md): the partition, C° and R by tenth, the binning, the unit of its
    position, its ordinal, the token ledger (method-v54.md:43), and V6's fields. A window with G unavailable (cG=NA)
    is checked with cG left out: its GC execution sits inside cE and its q is C - W - P. A record lacking a required
    key (read() refuses one as it is read; a caller that hands parse_line's record here directly) gives its one fault,
    naming the keys, never a KeyError (the integrator's point I)."""
    gone = lacks_keys(w) if b11_line(w) else ["the B11 fields"]
    if gone:
        return ["window %s.%s: lacks %s" % (w.get("pt"), w.get("wi"), ", ".join(gone))]
    tag = "window %s.%s" % (w["pt"], w["wi"])
    f = []
    if w["unit"] != UNIT_OF_POS.get(w["pos"]):
        f.append("%s: unit %s at position %s" % (tag, w["unit"], w["pos"]))
    if w["run"] < 1 or w["wi"] != 4 * (w["run"] - 1) + w["pos"]:
        f.append("%s: run %d position %d is not ordinal %d" % (tag, w["run"], w["pos"], w["wi"]))
    for k in ("coin", "plant", "prun", "res", "partial"):
        if w[k] not in (0, 1):
            f.append("%s: %s=%s" % (tag, k, w[k]))
    if w["arm"] not in ("ON", "OFF") or w["pred"] not in ("ON", "OFF", "none"):
        f.append("%s: arm=%s pred=%s" % (tag, w["arm"], w["pred"]))
    if w["f0"] < 0 or w["gcn"] < 0 or min(w["sF"], w["sS"], w["sP"]) < 0:
        f.append("%s: f0=%d gcn=%d sF=%d sS=%d sP=%d" % (tag, w["f0"], w["gcn"], w["sF"], w["sS"], w["sP"]))
    if (w["partial"] == 0 and w["n"] != WINDOW_FRAMES) or (w["partial"] == 1 and not 0 < w["n"] < WINDOW_FRAMES):
        f.append("%s: partial=%d with n=%d" % (tag, w["partial"], w["n"]))
    if any(len(w[k]) != TENTHS for k in ("q", "r", "qn")):
        f.append("%s: q, r, qn hold %d, %d, %d tenths (needs 10)" % (tag, len(w["q"]), len(w["r"]), len(w["qn"])))
        return f
    if sum(w["qn"]) != w["n"]:
        f.append("%s: sum(qn)=%d, n=%d" % (tag, sum(w["qn"]), w["n"]))
    elif w["qn"] != _bins(w["n"]):
        f.append("%s: qn %s is not n=%d in 12-frame bins" % (tag, w["qn"], w["n"]))
    if any(w["qn"][j] == 0 and (w["q"][j] or w["r"][j]) for j in range(TENTHS)):
        f.append("%s: an unreached tenth holds q or r" % tag)
    if sum(w["r"]) != w["cR"]:
        f.append("%s: sum(r)=%d, cR=%d" % (tag, sum(w["r"]), w["cR"]))
    # SHARED.md V6, the two changed invariants: the partition holds the classes P and X, and C° leaves P (charged whole
    # in U, ruling R6-A3.11.146 (7)) exactly once while X stays in it; an NA cG counts 0
    if w["cP"] < 0 or w["cX"] < 0:
        f.append("%s: cP=%d cX=%d" % (tag, w["cP"], w["cX"]))
    rest = w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cX"] + w["cE"]
    g = 0 if w["cG"] is None else w["cG"]
    if w["sC"] != g + rest:
        f.append("%s: sC=%d is not %scW+cR+cS+cP+cX+cE=%d" % (tag, w["sC"], "" if w["cG"] is None else "cG+",
                                                            g + rest))
    if sum(w["q"]) != w["sC"] - g - w["cW"] - w["cP"]:
        f.append("%s: sum(q)=%d is not sC-%scW-cP=%d" % (tag, sum(w["q"]), "" if w["cG"] is None else "cG-",
                                                         w["sC"] - g - w["cW"] - w["cP"]))
    neg = [k for k in A_FIELDS if w[k] is not None and w[k] < 0]
    if neg:
        f.append("%s: %s below 0" % (tag, ", ".join("%s=%d" % (k, w[k]) for k in neg)))
    if _wa(w["wa"]) is None:
        f.append("%s: wa=%s is not log:<bytes|NA>;hash:<bytes|NA>;sock:<bytes|NA>" % (tag, w["wa"]))
    if w["plant"] == 1 and (w["prun"] != 1 or w["arm"] != "OFF"):
        f.append("%s: planted (plant=1) with prun=%d arm=%s (FtPlant spins a plant run's OFF windows)"
                 % (tag, w["prun"], w["arm"]))
    wu, tok = _typed(w["wu"], 2, na=True), _typed(w["tok"], 7)
    if wu is None:
        f.append("%s: wu=%s is not type:units:cycles;..." % (tag, w["wu"]))
    if tok is None:
        f.append("%s: tok=%s is not type:open0,enqON,enqOFF,doneON,doneOFF,disc,open1;..." % (tag, w["tok"]))
    else:
        # SHARED.md (md5 2119eb2e): the conservation sum is an identity of the emitter (open is computed from the
        # same counters), so the checks are open1 >= 0 here and open0 = the previous window's open1 (window_reconcile)
        for t, x in sorted(tok.items()):
            if x[6] < 0:
                f.append("%s: %s open1=%d is below 0 (a service counted on the wrong type)" % (tag, t, x[6]))
    if wu is not None and tuple(wu) != WRITER_TYPES:
        f.append("%s: wu types %s are not %s" % (tag, ",".join(wu), ",".join(WRITER_TYPES)))
    if tok is not None and tuple(tok) != WRITER_TYPES:
        f.append("%s: tok types %s are not %s" % (tag, ",".join(tok), ",".join(WRITER_TYPES)))
    return f


def window_reconcile(recs):
    """Window ownership and the B11 reconciliation (ruling .138, SHARED.md), visiting every window and every point
    with no early stop: every w line has exactly one owner point line; every point has as many w lines as its line
    counts; B11 lines: one format per log, ordinals 1..k per point, the point's unplanted and planted totals of n,
    sF, sS, sC and sP equal to its line's, each window's own invariants (window_faults), the predecessor and res=1
    marks against the game's window order, plant constant per run, and mates on one coin (opposite arms, one coin
    field). Returns the misses."""
    miss = []
    owners, wins = {}, {}
    for r in recs:
        if r["kind"] == "p":
            owners.setdefault(r["pt"], []).append(r)
        elif r["kind"] == "w":
            wins.setdefault(r["pt"], []).append(r)
    for pt in sorted(wins):
        k = len(owners.get(pt, []))
        if k != 1:
            miss.append("window lines of point %s: %d owner point lines (needs exactly 1)" % (pt, k))
    for pt in sorted(owners):
        for q in owners[pt]:
            n = len(wins.get(pt, []))
            if n != q.get("windows", -1):
                miss.append("point %s: %d window lines, the point line counts %s" % (q["pt"], n, q.get("windows")))
    b11 = [r for r in recs if b11_line(r)]
    if not b11:
        return miss
    old = sum(1 for r in recs if r["kind"] == "w" and not b11_line(r))
    if old:
        miss.append("%d window lines lack the B11 fields beside %d that carry them" % (old, len(b11)))
    for pt in sorted(wins):
        bw = [w for w in wins[pt] if b11_line(w)]
        if not bw:
            continue
        wis = sorted(w["wi"] for w in bw)
        if wis != list(range(1, len(bw) + 1)):
            miss.append("point %s: window ordinals %s are not 1..%d" % (pt, ",".join(map(str, wis)), len(bw)))
        own = owners.get(pt, [])
        if len(own) != 1:
            continue
        p = own[0]
        for planted, pairs in ((0, (("n", "n"), ("sF", "sF"), ("sS", "sS"), ("sC", "sC"), ("sP", "sP"))),
                               (1, (("n", "pn"), ("sF", "psF"), ("sS", "psS"), ("sC", "psC"), ("sP", "psP")))):
            for wk, pk in pairs:
                tot = sum(w[wk] for w in bw if w["plant"] == planted)
                if tot != p.get(pk):
                    miss.append("point %s: the %s windows' %s total %d, the point line's %s %s"
                                % (pt, "planted" if planted else "unplanted", wk, tot, pk, p.get(pk)))
    for w in b11:
        miss += window_faults(w)
    games = {}
    for w in b11:
        games.setdefault(w["game"], []).append(w)
    # SHARED.md V6: arm= is the gate's real state, so under force=ON (or OFF) a window's arm no longer carries its
    # coin; mates are then held to one coin field only
    forced = set(r["g"] for r in recs if r["kind"] == "settled" and r.get("force") in ("ON", "OFF"))
    for g in sorted(games):
        prev = None
        runs, coins = {}, {}
        for w in games[g]:
            want = "none" if prev is None else prev["arm"]
            if w["pred"] != want:
                miss.append("window %s.%d: pred=%s, the game's previous window is %s" % (w["pt"], w["wi"], w["pred"], want))
            if prev is not None:
                t0, t1 = _typed(w["tok"], 7), _typed(prev["tok"], 7)
                for t in (sorted(set(t0) & set(t1)) if t0 and t1 else ()):
                    if t0[t][0] != t1[t][6]:
                        miss.append("window %s.%d: %s open0=%d, the game's previous window's open1=%d"
                                    % (w["pt"], w["wi"], t, t0[t][0], t1[t][6]))
            res = 1 if prev is not None and prev["prun"] == 1 and w["prun"] == 0 else 0
            if w["res"] != res:
                miss.append("window %s.%d: res=%d, needs %d (the first window after a plant run)" % (w["pt"], w["wi"],
                                                                                                   w["res"], res))
            prev = w
            runs.setdefault((w["pt"], w["run"]), set()).add(w["prun"])
            coins.setdefault(coin_of(w), []).append(w)
        for (pt, run), pl in sorted(runs.items()):
            if len(pl) != 1:
                miss.append("point %s run %d: plant-run and ordinary windows in one run (prun)" % (pt, run))
        for c, ws in sorted(coins.items()):
            if len(ws) > 2 or len(set(w["pos"] for w in ws)) != len(ws):
                miss.append("point %s run %d %s: %d windows on one pair" % (ws[0]["pt"], c[3], c[4], len(ws)))
            elif ((g not in forced and len(set(coin_value(w) for w in ws)) != 1)
                  or len(set(w["coin"] for w in ws)) != 1):
                miss.append("point %s run %d %s: mates %s do not carry one committed coin (arms %s, coin %s)"
                            % (ws[0]["pt"], c[3], c[4], ",".join(str(w["wi"]) for w in ws),
                               ",".join(w["arm"] for w in ws), ",".join(str(w["coin"]) for w in ws)))
    return miss


def _add(stat, g, e, x):
    if x != 0:
        d = stat.setdefault(g, {})
        d[e] = d.get(e, 0.0) + x


def _comb(*parts):
    """The linear combination sum of coef x stat, term by term on each exposure."""
    out = {}
    for c, st in parts:
        for g, evs in st.items():
            for e, x in evs.items():
                _add(out, g, e, c * x)
    return out


def b11_terms(recs, first_game=1, beta_us=BETA_US):
    """The B11 statistics' HT terms, per game per exposure (stat[g][exposure] = x; the estimate is the sum of
    x / P(exposure) over the realised exposures). The population: B11 windows of the measured games' valid rounds,
    plant runs and res=1 windows left out (the integrator's D4) and counted as the exposure loss.
    - B, the contrast: sign(arm) x (Y - n b) / N, Y_ON = C°, Y_OFF = C° - R_OFF, b the unit's baseline
      (method-v54.md:131 under the frozen rule of ruling R6-A3.11.140 (4)): the C° per frame of the latest full
      ordinary window (not a plant run, not res=1) of the game's runs q-2 and earlier, q the unit's run counted
      through the game, so it is independent of the current coin and the predecessor's coin and of their influence
      through its own history; it enters with its own coin; with none, beta_us.
    - c[a], arm a's carryover share in the corrected estimate (ruling .139 (1)): c_a = F_F c_a,F + F_P c_a,P.
      Full stratum: c_a,F = sum over j < 10 of (1/10)(d_aj - d_a10), d_aj the per-frame difference in tenth j's Y
      between predecessor ON and OFF over full windows, HT with the joint current and predecessor probabilities.
      Partial stratum: c_a,P the same difference over a partial window's occupied frames, estimated directly and
      centred on the unit's baseline (ruling .140 (5): its widths are the centred ones). A
      window with no predecessor (pred=none) is in its stratum's frames with no difference: nothing precedes it
      (refutation-c3.md:23 counts C3's cold first window so).
    - d10[a]: the between-window d_a10 over full windows, R-CARRY's falsifier.
    - D: the direct branch, sign(arm) x (cR + cS) in ON and cS in OFF (R_OFF restored), per frame, for r_U.
    - hp: the uncentred partial part of the charge, (1/2)(F_P c_ON,P + F_P c_OFF,P) without the centring, whose
      realised value under fixed A/A outcomes is H_P = (2/N) sum over ordinary partial windows of S_(i-1) C_i
      (c5.out:51-55; ruling .140 cross-check), kept for that check.
    All in us per frame (cycles / f_hat)."""
    fh = _fhat(recs)
    valid = set(q["pt"] for pts in games_of(recs, first_game).values() for q in pts)
    byg = {}
    for r in recs:
        if b11_line(r) and r["game"] >= first_game:
            byg.setdefault(r["game"], []).append(r)
    if not byg:
        raise Refused("no B11 window records in a measured game")
    loss = {"plant": 0, "res": 0, "all": 0}
    pop, pred_of, idx = [], {}, {}
    for g in sorted(byg):
        if fh.get(g, 0) <= 0:
            raise Refused("no f_hat for game %d" % g)
        prev = None
        for i, w in enumerate(byg[g]):
            pred_of[id(w)], idx[id(w)] = prev, i
            prev = w
            if w["pt"] not in valid:
                continue
            loss["all"] += w["n"]
            if w["prun"]:
                loss["plant"] += w["n"]
            elif w["res"]:
                loss["res"] += w["n"]
            else:
                pop.append(w)
    N = sum(w["n"] for w in pop)
    if N <= 0:
        raise Refused("no B11 window frames outside plant runs and res=1 windows")
    Ng = {}
    for w in pop:
        Ng[w["game"]] = Ng.get(w["game"], 0) + w["n"]
    full = [w for w in pop if w["partial"] == 0]
    nfull = sum(w["n"] for w in full)
    npart = N - nfull
    # ruling .139 (1): each stratum's share of the estimate's frames
    share_f, share_p = nfull / N, npart / N
    ff = BIN_FRAMES * len(full)                  # a full window's frames in each tenth, summed
    # each window's run counted through its game (a new (point, run) starts the next): ruling .140 (4) centres a
    # window of run q only on ordinary windows of runs q-2 and earlier
    grun = {}
    for g, ws in byg.items():
        k, key = 0, None
        for w in ws:
            if (w["pt"], w["run"]) != key:
                k, key = k + 1, (w["pt"], w["run"])
            grun[id(w)] = k
    base = {}
    for w in pop:
        c = coin_of(w)
        if c in base:
            continue
        ws = byg[w["game"]]
        hit = None
        for i in range(idx[id(w)] - 1, -1, -1):
            v = ws[i]
            if (grun[id(v)] <= grun[id(w)] - 2 and v["partial"] == 0 and v["prun"] == 0 and v["res"] == 0
                    and v["pt"] in valid):
                hit = v
                break
        base[c] = hit
    B, D, d10, hp = {}, {}, {"ON": {}, "OFF": {}}, {}
    cs = {"ON": {}, "OFF": {}}
    rows = []
    for w in pop:
        g = w["game"]
        k = 1e6 / fh[g]
        on = w["arm"] == "ON"
        s = 1.0 if on else -1.0
        c, v = coin_of(w), coin_value(w)
        ev = event((c, v))
        y = [(w["q"][j] - (0 if on else w["r"][j])) * k for j in range(TENTHS)]
        bw = base[c]
        if bw is None:
            b = beta_us
            _add(B, g, ev, s * (sum(y) - w["n"] * b) / N)
        else:
            b = sum(bw["q"]) * k / bw["n"]
            _add(B, g, ev, s * sum(y) / N)
            # the expanded baseline term (method-v53.md:46): its exposure carries the baseline window's coin
            _add(B, g, event((c, v), (coin_of(bw), coin_value(bw))), -s * w["n"] * b / (2 * N))
        _add(D, g, ev, s * (w["cR"] + w["cS"] if on else w["cS"]) * k / N)
        rows.append((w, sum(y) / w["n"], b))
        pw = pred_of[id(w)]
        if pw is None:
            continue
        sp = 1.0 if pw["arm"] == "ON" else -1.0
        e2 = event((coin_of(pw), coin_value(pw)), (c, v))
        a = w["arm"]
        if w["partial"] == 0:
            prof = (sum(y[:TENTHS - 1]) / TENTHS - (TENTHS - 1) / TENTHS * y[TENTHS - 1]) / ff
            _add(cs[a], g, e2, share_f * sp * prof)
            _add(d10[a], g, e2, sp * y[TENTHS - 1] / ff)
        elif share_p:
            # the partial stratum, centred like the contrast: the baseline term's exposure adds the baseline's coin
            if bw is None:
                _add(cs[a], g, e2, share_p * sp * (sum(y) - w["n"] * b) / npart)
            else:
                _add(cs[a], g, e2, share_p * sp * sum(y) / npart)
                _add(cs[a], g, event((coin_of(pw), coin_value(pw)), (c, v), (coin_of(bw), coin_value(bw))),
                     -share_p * sp * w["n"] * b / (2 * npart))
            _add(hp, g, e2, 0.5 * share_p * sp * sum(y) / npart)
    gna = [w for w in pop if w["cG"] is None]
    # D_common (the integrator's ruling on the hand-back (4), RUL:3452, 3511-3512): the direct execution of every
    # scope that runs while the arm is OFF, (cR + cW) per frame, over the ordinary full OFF windows
    ofw = [w for w in pop if w["arm"] == "OFF" and w["partial"] == 0]
    dcommon = (sum((w["cR"] + w["cW"]) * 1e6 / fh[w["game"]] for w in ofw) / sum(w["n"] for w in ofw)
               if ofw else None)
    # plant runs (P1's notes): every prun=1 window is out of the estimate; a run fixed before c_plant is unspun
    # (prun=1, no window planted); the plant control (method-v53.md:162) takes the spun ones only
    pr = {}
    for g in sorted(byg):
        for w in byg[g]:
            if w["prun"] and w["pt"] in valid:
                pr.setdefault((g, w["pt"], w["run"]), []).append(w)
    unspun = sorted(k for k, ws in pr.items() if not any(w["plant"] for w in ws))
    # writer types whose cycles print NA in any window of a measured game withhold B1 for the seat (P1's notes). A
    # FrameTimeRef log prints sock:NA:NA, but a Ref log is known only by its build marker (build_marker), never by the
    # NA: a measurement log printing NA:NA still withholds (to-p2-r4.md (4))
    wu_na = sorted(set(t for g in byg for w in byg[g] if w["pt"] in valid
                       for t, x in (_typed(w["wu"], 2, na=True) or {}).items() if x[1] is None))
    pairs = {}
    for w in pop:
        pairs.setdefault(coin_of(w), []).append(w)
    return {"B": B, "c": cs, "d10": d10, "D": D, "hp": hp, "N": N, "Ng": Ng, "nfull": nfull, "npart": npart, "loss": loss,
            "gna": gna, "rows": rows, "pop": pop, "valid": valid, "byg": byg, "plant_runs": len(pr), "fh": fh,
            "unspun": unspun, "wu_na": wu_na,
            "units": (sum(1 for x in pairs.values() if len(x) == 2), sum(1 for x in pairs.values() if len(x) == 1)),
            "dcommon": dcommon}


def _design_sets(*stats):
    """The coin sets of the design's exposures, per game: every coin set a nonzero realised term uses, each with all
    its value combinations (an unrealised combination's term is unknown, so it is counted)."""
    sets = {}
    for st in stats:
        for g, evs in st.items():
            for e, x in evs.items():
                if x != 0:
                    sets.setdefault(g, set()).add(tuple(c for c, _ in e))
    return sets


def ht_var(stat, sets=None):
    """method-v53.md:39-46: (estimate, conservative design variance, per-game estimate). Pairs of realised exposures
    sharing a coin contribute (p_ef - p_e p_f) / (p_e p_f p_ef) x_e x_f; each design exposure conflicting with a
    realised e (p_ef = 0) adds e's half of the bound, x_e^2 / p_e; exposures on disjoint coins have p_ef = p_e p_f.
    Games share no coin, so the variance aggregates within games."""
    if sets is None:
        sets = _design_sets(stat)
    est = var = 0.0
    pg = {}
    for g, evs in stat.items():
        evs = {e: x for e, x in evs.items() if x != 0}
        by_coin, sets_by_coin = {}, {}
        for e in evs:
            for c, _ in e:
                by_coin.setdefault(c, []).append(e)
        for s in sets.get(g, ()):
            for c in s:
                sets_by_coin.setdefault(c, []).append(s)
        tot = 0.0
        for e, x in evs.items():
            pe = event_prob(e)
            tot += x / pe
            seen = set()
            for c, _ in e:
                for f in by_coin[c]:
                    if f in seen:
                        continue
                    seen.add(f)
                    pef = joint_prob(e, f)
                    if pef == 0:
                        raise Refused("two realised exposures conflict (%s, %s): the records are not one assignment"
                                      % (e, f))
                    pf = event_prob(f)
                    var += (pef - pe * pf) / (pe * pf * pef) * x * evs[f]
            ke = dict(e)
            conf, seen = 0, set()
            for c, _ in e:
                for s in sets_by_coin.get(c, ()):
                    if s in seen:
                        continue
                    seen.add(s)
                    shared = sum(1 for cc in s if cc in ke)
                    conf += 2 ** len(s) - 2 ** (len(s) - shared)
            var += conf * x * x / pe
        pg[g] = tot
        est += tot
    return est, var, pg


def _cluster_hw(pg, Ng, N, z):
    """The game and adjacent-game interval (method-v53.md:48, as fw_interval): one-game and two-game batches of the
    per-game contributions, the wider wins; 0 when fewer than two batches exist."""
    dw = [(pg.get(g, 0.0) * N / Ng[g], Ng[g]) for g in sorted(Ng) if Ng[g] > 0]
    est = sum(d * w for d, w in dw) / N
    best = 0.0
    for b in (1, 2):
        bs = []
        for i in range(0, len(dw) - len(dw) % b, b):
            ww = sum(w for d, w in dw[i:i + b])
            bs.append((sum(d * w for d, w in dw[i:i + b]) / ww, ww))
        kb = len(bs)
        if kb < 2:
            continue
        wbar = sum(w for d, w in bs) / kb
        se = math.sqrt(sum((w * (d - est) / wbar) ** 2 for d, w in bs) / (kb * (kb - 1)))
        best = max(best, t_q(z, kb - 1) * se)
    return best


def stat_interval(stat, z, Ng, N, sets=None):
    """(estimate, half-width at z): the wider of the conservative design half-width and the game/adjacent-game one."""
    est, var, pg = ht_var(stat, sets)
    return est, max(z * math.sqrt(max(var, 0.0)), _cluster_hw(pg, Ng, N, z))


def _ratio_ub(B, D, Ng, N):
    """r_U (ruling .136 (5), the integrator's ruling on the hand-back (4)): the upper bound of the switched scopes'
    external-to-direct ratio, (B - D) / D with B the carryover-corrected contrast, by Fieller's construction: the largest r whose B - (1 + r) D keeps its upper bound at or above 0,
    under the joint covariance. Infinite when D is not bounded away from 0."""
    sets = _design_sets(B, D)
    b, vb, pgb = ht_var(B, sets)
    d, vd, pgd = ht_var(D, sets)
    _, vbd, _ = ht_var(_comb((1.0, B), (1.0, D)), sets)
    cov = (vbd - vb - vd) / 2

    def ub(r):
        a = 1.0 + r
        pg = dict((g, pgb.get(g, 0.0) - a * pgd.get(g, 0.0)) for g in Ng)
        var = vb + a * a * vd - 2 * a * cov
        return b - a * d + max(Z_UP * math.sqrt(max(var, 0.0)), _cluster_hw(pg, Ng, N, Z_UP))

    lo = -1.0
    if ub(lo) < 0:
        return (b - d) / d if d else float("inf"), lo
    hi = 1.0
    while ub(hi) >= 0:
        hi *= 2
        if hi > 1e6:
            return (b - d) / d if d else float("inf"), float("inf")
    for _ in range(60):
        mid = (lo + hi) / 2
        if ub(mid) >= 0:
            lo = mid
        else:
            hi = mid
    return (b - d) / d if d else float("inf"), lo


def exposure_diagnostics(T, freq):
    """Per point (ruling R6-A3.11.140 (3), which withdraws .139 (4)'s count/share bound: it bounds nothing,
    c5.out:30-36): its frames, wall duration (sum of sF over freq), terminal window length, ON-frame share and mean
    frame time by arm, us (None for an arm with no frames). Diagnostics only: none enters U."""
    pts = {}
    for g, ws in T["byg"].items():
        for w in ws:
            if w["pt"] in T["valid"]:
                pts.setdefault(w["pt"], []).append(w)
    rows = []
    for pt in sorted(pts, key=lambda x: tuple(int(v) for v in x.split("."))):
        ws = sorted(pts[pt], key=lambda w: w["wi"])
        n = sum(w["n"] for w in ws)
        mean = {}
        for arm in ("ON", "OFF"):
            k = sum(w["n"] for w in ws if w["arm"] == arm)
            mean[arm] = sum(w["sF"] for w in ws if w["arm"] == arm) * 1e6 / freq / k if k else None
        on = sum(w["n"] for w in ws if w["arm"] == "ON")
        rows.append((pt, n, sum(w["sF"] for w in ws) / freq, ws[-1]["n"], on / n if n else 0.0, mean["ON"],
                     mean["OFF"]))
    return rows


def b11_estimate(recs, first_game=1, beta_us=BETA_US, exposure=None):
    """The corrected contrast's bound and its parts (rulings .138 (3), .139 (1)): the contrast B, both arms' carryover
    c_ON and c_OFF over both strata, the charge max(0, the upper bound of (c_ON + c_OFF)/2) under the joint covariance
    with the contrast, R-CARRY's falsifier d_a10, r_U and D_common for R-COMMON, the per-point exposure diagnostics.
    exposure is an exposure envelope, (upper bound in us per frame, its source), checked for its form and returned as
    ex and ex_src, or None (the default: the parser constructs no envelope). Under V6 (SHARED.md:235, ruling
    R6-A3.11.151 (2) class D, F15) the exposure obligation left the verdict with B_U's terms: the envelope enters no
    figure of U or of the cross-check, and its absence withholds nothing."""
    T = b11_terms(recs, first_game, beta_us)
    N, Ng = T["N"], T["Ng"]

    def iv(st, z):
        return stat_interval(st, z, Ng, N)

    B = T["B"]
    charge = _comb((0.5, T["c"]["ON"]), (0.5, T["c"]["OFF"]))
    J = _comb((1.0, B), (1.0, charge))
    b, hb = iv(B, Z_UP)
    hbl = iv(B, Z_LO)[1]
    c, hc = iv(charge, Z_UP)
    j, hj = iv(J, Z_UP)
    hjl = iv(J, Z_LO)[1]
    con, hcon = iv(T["c"]["ON"], Z_UP)
    coff, hcoff = iv(T["c"]["OFF"], Z_UP)
    cub = c + hc
    ub_b, ub_j = b + hb, j + hj
    # max(0, .) (ruling .137 (4)): a charge whose upper bound is not above 0 charges nothing and the contrast's own
    # bound stands; a positive one gives the joint bound, never under the contrast's own
    bu = max(ub_b, ub_j) if cub > 0 else ub_b
    joint = cub > 0 and ub_j >= ub_b
    hw = hj if joint else hb
    # the lower bound for SID and FAIL (the integrator's ruling on the hand-back (2), RUL:3452-3454): every component at
    # its lower end, the carryover term without its max(0, .) floor; the GC, writer and R-COMMON charges have no lower
    # end measured, so they enter it as 0
    lb = j - hjl
    d10 = dict((a, iv(T["d10"][a], Z_LO)) for a in ("ON", "OFF"))
    # r_U (ruling (4)): on the carryover-corrected external contrast, the charge at its upper end (none when that end
    # is not above 0, as in bu)
    xr = J if cub > 0 else B
    r_hat, r_u = _ratio_ub(xr, T["D"], Ng, N)
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("the exposure diagnostics need one Stopwatch frequency (got %s)" % sorted(freq))
    prow = exposure_diagnostics(T, freq.pop())
    if exposure is not None and not (isinstance(exposure[0], (int, float)) and exposure[0] >= 0 and exposure[1]):
        raise Refused("an exposure envelope is an upper bound >= 0 us per frame with its source (got %r)"
                      % (exposure,))
    ex = None if exposure is None else float(exposure[0])
    return {"T": T, "B": (b, hb, hbl), "c_on": (con, hcon), "c_off": (coff, hcoff), "charge": (c, hc, max(0.0, cub)),
            "J": (j, hj, hjl), "bu": bu, "hw": hw, "lb": lb, "joint": joint, "d10": d10, "r_hat": r_hat,
            "r_u": max(0.0, r_u), "dcommon": T["dcommon"], "ex": ex, "ex_src": None if exposure is None
            else exposure[1], "points": prow, "center": j if joint else b}


def t_ref_windows(recs, first_game=1):
    """T_ref for the window design: the mean F per frame of the OFF unplanted B11 windows in the population, us."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("T_ref needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    valid = set(q["pt"] for pts in games_of(recs, first_game).values() for q in pts)
    ws = [w for w in recs if b11_line(w) and w["game"] >= first_game and w["pt"] in valid and w["arm"] == "OFF"
          and w["prun"] == 0 and w["res"] == 0]
    n = sum(w["n"] for w in ws)
    if n <= 0:
        raise Refused("no OFF window frames")
    return sum(w["sF"] for w in ws) * 1e6 / f / n


def read_reference(text, src="reference"):
    """R-COMMON's reference record set (the integrator, 11 Nov): a FrameTimeRef build's log (no census, no disp lines,
    A3 rows in a reference form), recognised by its marker only. Only the kinds the comparator reads (w, settled) are
    taken, each tested against REQUIRED_KEYS. ATTACH (ruling R6-A3.11.151 (3)) holds for it against the reference
    build's list (ATTACH_CLASSES_REF), or the input is refused by name: a reference whose patches did not attach is no
    reference."""
    refuse_withheld(text, src)
    build_marker(text, "reference", src)
    bad = attach_guard(text, ATTACH_CLASSES_REF)
    if bad:
        raise Refused("ATTACH: the reference log %s: %s" % (src, _reasons(bad)))
    recs = []
    for n, ln in enumerate(text.splitlines(), 1):
        r = parse_line(ln)
        if r is None or r["kind"] not in ("w", "settled"):
            continue
        gone = lacks_keys(r)
        if gone:
            raise RecordRefused(r["kind"], src, n, gone)
        recs.append(r)
    return recs


def _mean_hw(ds, z):
    k = len(ds)
    if k < 2:
        raise Refused("needs two games (got %d)" % k)
    m = sum(ds) / k
    return m, t_q(z, k - 1) * math.sqrt(sum((v - m) ** 2 for v in ds) / (k - 1) / k)


def reference_common_cost(recs, ref_recs, first_game=1):
    """The total common cost the reference isolates (R-COMMON's falsifier, ruling .137 (5)): the measured log's OFF
    windows' whole C less the restored R_OFF, per frame, against the reference's whole C per frame, game means at
    point-level precision. Returns (total, its lower end at Z_LO)."""
    fh, fr = _fhat(recs), _fhat(ref_recs)
    valid = set(q["pt"] for pts in games_of(recs, first_game).values() for q in pts)
    meas, ref = {}, {}
    for w in recs:
        if b11_line(w) and w["game"] >= first_game and w["pt"] in valid and w["arm"] == "OFF" and not w["prun"]:
            a = meas.setdefault(w["game"], [0.0, 0])
            a[0] += (w["sC"] - w["cR"]) * 1e6 / fh[w["game"]]
            a[1] += w["n"]
    for w in ref_recs:
        if w["kind"] == "w" and w["game"] >= first_game and not w.get("prun", w.get("plant", 0)):
            if fr.get(w["game"], 0) <= 0:
                raise Refused("reference: no f_hat for game %d" % w["game"])
            a = ref.setdefault(w["game"], [0.0, 0])
            a[0] += w["sC"] * 1e6 / fr[w["game"]]
            a[1] += w["n"]
    mm, hm = _mean_hw([s / n for s, n in meas.values() if n], Z_LO)
    mr, hr = _mean_hw([s / n for s, n in ref.values() if n], Z_LO)
    return mm - mr, mm - mr - math.sqrt(hm * hm + hr * hr)


def r_common_check(total_lo, r_u, d_common):
    """R-COMMON's comparator (ruling .137 (5)): the reference's total common cost against (1 + r_U) D_common; True
    when it falsifies R-COMMON."""
    return total_lo > (1.0 + r_u) * d_common


def _wu_cyc(w, types):
    """The window's wu cycles summed over types (NA as 0; NA withholds elsewhere) and its units, cycles."""
    d = _typed(w["wu"], 2, na=True) or {}
    return sum(d[t][1] or 0 for t in types if t in d)


def writer_added(T):
    """The off-main writer cycles per frame by arm, us (SHARED.md md5 2119eb2e): log, hash and sock add to the writer
    cost; recv's cycles are already inside C and are never added again. The input W_U's construction reads."""
    out = {}
    for arm in ("ON", "OFF"):
        ws = [w for w in T["pop"] if w["arm"] == arm]
        n = sum(w["n"] for w in ws)
        out[arm] = (sum(_wu_cyc(w, WRITER_ADDED) * 1e6 / T["fh"][w["game"]] for w in ws) / n) if n else None
    return out


def own_split_faults(recs, T):
    """own_split per point (the integrator's ruling on the hand-back (3)): an ownership fault, not a quantity; every
    point of a measured game whose line counts one or more, or prints none, as (pt, count or None)."""
    return [(q["pt"], q.get("own_split")) for q in recs
            if q["kind"] == "p" and q["pt"] in T["valid"] and q.get("own_split", 1) != 0]


# SHARED.md (md5 3ab20794): recv_offmain, ledger_cycle_miss and sock_main; ruling R6-A3.11.151 (2) class B, F3:
# span_class_overflow (FtFrames.cs:275, counted at FtSpan.cs:228: a scope past the class stack's depth, whose cycles and
# bytes land on the class below it); .152 (2)(h): plant_mixed (FtFrames.cs:144: a frame unlike its window's plant)
P_LINE_FAULTS = ("recv_offmain", "ledger_cycle_miss", "sock_main", "span_class_overflow", "plant_mixed")


def p_line_faults(recs, valid):
    """P_LINE_FAULTS must be printed and 0 in every point of valid (a set of pt): recv_offmain, ledger_cycle_miss and
    sock_main (cycles both in C and in sock; SHARED.md md5 3ab20794), span_class_overflow (ruling R6-A3.11.151, F3) and
    plant_mixed (ruling .152 (2)(h)); sock_thr is reported only. The socket counters are zero also when the socket hook
    never attached; they rest on the validity set's ATTACH guard (its FtSockPatch entry; .151 (2) class A, F1)."""
    why = []
    for k in P_LINE_FAULTS:
        bad = [q["pt"] for q in recs if q["kind"] == "p" and q["pt"] in valid and q.get(k, 1) != 0]
        if bad:
            why.append("%s nonzero or not printed at %s" % (k, ", ".join(bad)))
    return why


def b11_transitions(recs, T):
    """The class-transition overhead per arm (SHARED.md, P1's notes): nm times the boot line's median cost, as a share
    of the arm's C. It stays in the charge (method-v53.md:13-48): reported, never subtracted. None, with the reason,
    when the boot line is not there exactly once."""
    mk = [r for r in recs if r["kind"] == "mark" and r["head"] == "cost"]
    if len(mk) != 1:
        return None, "%d mark cost lines (needs exactly 1)" % len(mk)
    out = {}
    for arm in ("ON", "OFF"):
        ws = [w for w in T["pop"] if w["arm"] == arm]
        nm, c = sum(w["nm"] for w in ws), sum(w["sC"] for w in ws)
        out[arm] = (nm, nm * mk[0]["cyc"] / c if c else None)
    return out, "median %d cycles (p90 %d, n %d)" % (mk[0]["cyc"], mk[0]["p90"], mk[0]["n"])


def b11_report(recs, ref_recs=None, first_game=1):
    """The window design's report lines and its figures, as built: under V6 (rulings R6-A3.11.146 (6), .147) the
    contrast is a cross-check that can only refute U, so nothing here is a term of the verdict (B_U's terms, the
    exposure obligation and the peer-driven charge, left it). A forced log is no contrast input (contrast_input)."""
    contrast_input(recs)
    e = b11_estimate(recs, first_game)
    T = e["T"]
    out = []
    tr = t_ref_windows(recs, first_game)
    lo = T["loss"]
    out.append("B11 windows: %d in the estimate (%d pairs, %d singletons; %d partial), %d frames (%d in partial "
               "windows); exposure loss: plant runs %d frames, res=1 windows %d frames, %.2f percent of %d left out of "
               "the contrast and the carryover statistic" % (len(T["pop"]), T["units"][0], T["units"][1],
                                                             sum(1 for w in T["pop"] if w["partial"]), T["N"],
                                                             T["npart"], lo["plant"], lo["res"],
                                                             100.0 * (lo["plant"] + lo["res"]) / max(1, lo["all"]),
                                                             lo["all"]))
    out.append("B11 plant runs: %d, %d unspun (fixed before c_plant: prun=1, nothing planted; out of the estimate, "
               "and the plant control takes the spun runs only)%s" % (T["plant_runs"], len(T["unspun"]), "".join(
                   "; %s run %d" % (pt, run) for g, pt, run in T["unspun"])))
    osp = own_split_faults(recs, T)
    out.append("B11 own_split (windows written partial by an owner split, an ownership fault): %s"
               % ("; ".join("%s %s" % (pt, "not printed" if k is None else k) for pt, k in osp) if osp
                  else "0 in every point"))
    tx, why = b11_transitions(recs, T)
    if tx is None:
        out.append("B11 class transitions: not computable: %s" % why)
    else:
        out.append("B11 class transitions (in the charge, reported only): %s; ON %d marks, %s of C; OFF %d marks, %s "
                   "of C" % (why, tx["ON"][0], "%.4f percent" % (100 * tx["ON"][1]) if tx["ON"][1] is not None
                             else "no C", tx["OFF"][0], "%.4f percent" % (100 * tx["OFF"][1])
                             if tx["OFF"][1] is not None else "no C"))
    if T["wu_na"]:
        out.append("B11 writers: cycles print NA for %s (reported: the writers left the contrast's verdict with B_U; "
                   "in sitting V an NA withholds B1)" % ", ".join(T["wu_na"]))
    if T["gna"]:
        # ruling R6-A3.11.151 (2) class D, F15: V6 retired G_U (SHARED.md:235, B_U's terms leave the verdict)
        out.append("B11 GC: cG prints NA in %d windows (%s): their identity is checked without cG and their C° keeps "
                   "their GC, which the contrast then carries; V6 has no G_U (B_U's terms left the verdict, SHARED.md "
                   "V6), and the bound's GC term is sitting V's G_cap" % (len(T["gna"]), ", ".join(
                       "%s.%d" % (w["pt"], w["wi"]) for w in T["gna"])))
    else:
        out.append("B11 GC: G available in every window")
    b, hb, hbl = e["B"]
    c, hc, ch = e["charge"]
    j, hj, hjl = e["J"]
    out.append("B11 contrast %.3f us per frame, upper half-width %.3f, lower %.3f; T_ref %.1f us" % (b, hb, hbl, tr))
    out.append("B11 carryover c_ON %.3f (+%.3f) us, c_OFF %.3f (+%.3f) us (full and partial strata); (c_ON + c_OFF)/2 "
               "%.3f, upper bound %.3f, charge max(0, .) %.3f us" % (e["c_on"][0], e["c_on"][1], e["c_off"][0],
                                                                    e["c_off"][1], c, c + hc, ch))
    out.append("B11 corrected bound %.3f us (%s; centre %.3f, half-width %.3f, lower bound %.3f) = %.3f percent of "
               "T_ref" % (e["bu"], "joint with the charge" if e["joint"] else "the contrast's own, no charge",
                          e["center"], e["hw"], e["lb"], 100 * e["bu"] / tr))
    fals = [a for a in ("ON", "OFF") if e["d10"][a][0] - e["d10"][a][1] > 0]
    out.append("R-CARRY falsifier: between-window d_ON,10 %.3f +- %.3f us, d_OFF,10 %.3f +- %.3f us: %s"
               % (e["d10"]["ON"][0], e["d10"]["ON"][1], e["d10"]["OFF"][0], e["d10"]["OFF"][1],
                  "FALSIFIED in %s (lower end above 0)" % "/".join(fals) if fals else "not falsified at this precision"))
    eu = (e["r_u"] * e["dcommon"] if e["r_u"] != float("inf") and e["dcommon"] is not None else None)
    out.append("R-COMMON charge: r_U %s (estimate %.4f), D_common %s per frame, r_U D_common %s"
               % ("%.4f" % e["r_u"], e["r_hat"], "%.3f us" % e["dcommon"] if e["dcommon"] is not None
                  else "not computable (no ordinary full OFF window)", "%.3f us" % eu if eu is not None
                  else "not bounded"))
    wa = writer_added(T)
    out.append("B11 writers off the main thread (log, hash, sock; recv is inside C): ON %s, OFF %s per frame"
               % tuple("%.3f us" % wa[a] if wa[a] is not None else "no frames" for a in ("ON", "OFF")))
    if ref_recs is None:
        out.append("R-COMMON UNTESTED: no reference record set")
    elif e["dcommon"] is None:
        out.append("R-COMMON comparator not computable: no ordinary full OFF window for D_common")
    else:
        tot, tlo = reference_common_cost(recs, ref_recs, first_game)
        bar = (1.0 + e["r_u"]) * e["dcommon"]
        out.append("R-COMMON comparator: the reference's total common cost %.3f us per frame (lower end %.3f) against "
                   "(1 + r_U) D_common %.3f us: %s" % (tot, tlo, bar, "FALSIFIED" if r_common_check(
                       tlo, e["r_u"], e["dcommon"]) else "holds"))
    for pt, n, wall, last, sh, mon, moff in e["points"]:
        out.append("B11 point %s: %d frames, wall %.3f s, terminal window %d frames, ON-frame share %.4f, mean frame "
                   "time ON %s, OFF %s (diagnostic)" % (pt, n, wall, last, sh, "%.1f us" % mon if mon is not None
                                                        else "none", "%.1f us" % moff if moff is not None else "none"))
    e["tref"], e["eu"] = tr, eu
    return out, e


def classify(u, tref, hw, lb):
    """The decision (method-v54.md:189, method-v51.md D, ruling R6-A3.11.131 D): the candidate band comes from U
    (PASS <= 3, SID <= 5, FAIL > 5 percent of T_ref); PASS needs nothing more; SID or FAIL also need the total
    statistical half-width at most 1.5 percent of T_ref and the corresponding lower bound above 3 or 5 percent;
    otherwise WITHHELD (band unresolved)."""
    if u <= 0.03 * tref:
        return "PASS"
    if hw > 0.015 * tref:
        return "WITHHELD"
    if u <= 0.05 * tref:
        return "SID" if lb > 0.03 * tref else "WITHHELD"
    return "FAIL" if lb > 0.05 * tref else "WITHHELD"


# ----------------------------------------------------------------------------- V6: the direct bound and the combine
# SHARED.md "V6: the direct bound" (rulings R6-A3.11.146 and .147). Sitting V: both seats forced ON; U, its five terms,
# U_hi, L, T_ref and the class come from it alone (sitting_v, report_on). Sitting C: both seats alternate as built; its
# contrast is the cross-check (cross_check). combine() reads both and prints VERDICT B1 per seat and the worse seat.

FORCE_C = "none"                          # sitting C: force=none on every settled line
FORCE_V = "ON"                            # sitting V: force=ON on every settled line of both seats
MIN_GAMES_V = 6                           # "fewer than 6 games remain" withholds B1
K_TOL = 0.05                              # K2 and K3: each spin reads within 5 percent in its own class
K1_ABOVE = 4096                           # K1: the planted median from the bytes asked to 4096 above
# K2 (SHARED.md:223, ruling R6-A3.11.151 (2) class C): a spin of 2000 us read within 5 percent, 1900 to 2100 us; K3
# spins the same constant (FtSpan.PlantUs = 2000, plugin/FtSpan.cs:324, spun at FtPhoton.cs:111-121)
K_PLANT_US = 2000
_K_BAND = "%d to %d" % (K_PLANT_US * (1 - K_TOL), K_PLANT_US * (1 + K_TOL))
# the four PhotonPeer entries P1 scopes as class X (Photon3Unity3D 4.1.7.0); the patch line names each attached patch
#: ruling R6-A3.11.149 (1) and (6) 4: the patch line names ten methods, each as FtPhoton.ReportPatched prints it
# (DeclaringType.Name + "." + Name, plugin/FtPhoton.cs:93): PhotonPeer's four (class X) and LoadBalancingClient's six
# listener callbacks (class E)
PHOTON_ENTRIES = ("PhotonPeer.DispatchIncomingCommands", "PhotonPeer.SendOutgoingCommands", "PhotonPeer.SendAcksOnly",
                  "PhotonPeer.Service", "LoadBalancingClient.OnOperationResponse", "LoadBalancingClient.OnEvent",
                  "LoadBalancingClient.OnStatusChanged", "LoadBalancingClient.DebugReturn",
                  "LoadBalancingClient.OnMessage", "LoadBalancingClient.OnDisconnectMessageReceived")
RANK = {"PASS": 0, "SID": 1, "WITHHELD": 2, "FAIL": 3}     # the worse seat: a FAIL is worse than an unresolved seat
V_RISKS = (
    "R-GC (SHARED.md V6): the collectors add to collection work at most in proportion to the bytes they allocate, and "
    "what they keep alive does not lengthen collections; checks: K1, collections per MB in sitting C's ON and OFF "
    "windows, the collectors' bytes over sitting V against heap= at its end",
    "R-SCOPE (ruling R6-A3.11.147 (3)(f)): every collector entry point runs inside a scope, on the main thread and off "
    "it, and Photon moves messages on the main thread only inside the patched entries; checks: the scope census line, "
    "the photon patch line, the contrast",
    "R-WORK (SHARED.md V6): sitting V is ordinary play; checks: the census on both seats, and each game's u_g beside U",
    "R-REST: see the cross-check (its interval and half-width against the band, per seat)")


def contrast_input(recs):
    """SHARED.md V6, The two sittings (m7): the contrast's input is sitting C's, alternating as built, so every settled
    line prints force=none. A forced log (force=ON or OFF), or one that does not print force=, is refused by name."""
    bad = [(r["g"], r.get("force")) for r in recs if r["kind"] == "settled" and r.get("force") != FORCE_C]
    if bad:
        raise Refused("FORCED-INPUT: a contrast input alternates as built (force=none on every settled line): %s"
                      % ", ".join("g=%s force=%s" % x for x in bad))


def cross_check_line(e, sc):
    """The as-built report's B1 line for a window log (sitting C): the corrected contrast and its interval, T_ref as
    built, and the cross-check as built (ruling R6-A3.11.149 (5)(c), (d)): unavailable while a guard of the validity
    set fails, else available and weakened by any two-arm guard that did not pass. It gives no verdict (SHARED.md V6:
    the contrast is a cross-check; the combining step tests it against U_hi)."""
    weak = _weak(sc["two"])
    st = ("unavailable (%s)" % ", ".join(sc["unavail"]) if sc["unavail"]
          else "available%s" % (", weakened by %s" % _weak_text(weak) if weak else ""))
    if e is None:
        return ("B1 CROSS-CHECK not computable (the B11 window estimator above); no B1 verdict here: the combining "
                "step (--combine) gives it; guards as built: the cross-check is %s" % st)
    return ("B1 CROSS-CHECK (sitting C; no B1 verdict here: the combining step, --combine, gives it from sitting V's "
            "U_hi): contrast %.3f us per frame, interval %.3f to %.3f (lower end at z %.4f, upper at z %.4f), T_ref as "
            "built %.1f us; guards as built: the cross-check is %s" % (e["center"], e["lb"], e["bu"], Z_LO, Z_UP,
                                                                      e["tref"], st))


def _num(v):
    """A boot line's integer value (parse_line keeps keys outside INT_KEYS as text), or None."""
    return v if isinstance(v, int) else (int(v) if re.fullmatch(r"-?\d+", str(v)) else None)


def _within(got, asked):
    return got is not None and asked is not None and asked > 0 and abs(got - asked) <= K_TOL * asked


def boot_controls(recs):
    """The five V6 boot lines (ruling R6-A3.11.147 (5), SHARED.md V6 What P1 builds), each read exactly once; a
    missing, repeated or malformed line counts as its control out of range. Returns {name: (ok, reading)} for pin
    (alloc pin=ok), K1 (the planted median from the bytes asked to 4096 above, the empty median 0), K2 (the scope
    plant within 5 percent), K3 (each of x, e and p within 5 percent), patches (n equals the names counted, and the
    names are exactly PHOTON_ENTRIES' ten, typed, each once; the warning 'photon patches report failed' is its own
    failure) and census (every census entry point wrapped by a scope, and no failed= printed: the census threw)."""
    def one(kind, head):
        ls = [r for r in recs if r["kind"] == kind and (head is None or r["head"] == head)]
        return (ls[0], None) if len(ls) == 1 else (None, "%d '%s%s' lines (needs exactly 1)"
                                                  % (len(ls), kind, "" if head is None else " " + head))
    out = {}
    a, why = one("alloc", None)
    out["pin"] = (False, why) if a is None else (a.get("pin") == "ok", "pin=%s" % a.get("pin"))
    if a is None:
        out["K1"] = (False, why)
    else:
        m = re.fullmatch(r"(\d+)/(\d+)", str(a.get("planted", "")))
        emp = _num(a.get("empty", ""))
        if m is None or emp is None:
            out["K1"] = (False, "planted=%s empty=%s is not <median>/<bytes asked> and <median>"
                         % (a.get("planted"), a.get("empty")))
        else:
            med, ask = int(m.group(1)), int(m.group(2))
            out["K1"] = (ask > 0 and ask <= med <= ask + K1_ABOVE and emp == 0,
                         "planted median %d for %d asked (needs %d to %d), empty median %d (needs 0)"
                         % (med, ask, ask, ask + K1_ABOVE, emp))
    s, why = one("scope", "plant")
    if s is None:
        out["K2"] = (False, why)
    else:
        ask, got = _num(s.get("asked", "")), _num(s.get("got", ""))
        # ruling R6-A3.11.151 (2) class C, F5: the spin is SHARED.md's 2000 us, never the log's own asked=
        out["K2"] = (ask == K_PLANT_US and _within(got, K_PLANT_US),
                     "asked %s us (needs %d), class S read %s us (needs %s)" % (ask, K_PLANT_US, got, _K_BAND))
    t, why = one("nest", "plant")
    if t is None:
        out["K3"] = (False, why)
    else:
        ask = _num(t.get("asked", ""))
        rd = dict((c, _num(t.get(c, ""))) for c in ("x", "e", "p"))
        # F5's sibling: K3 spins the same constant (FtSpan.PlantUs, plugin/FtPhoton.cs:111-121)
        out["K3"] = (ask == K_PLANT_US and all(_within(v, K_PLANT_US) for v in rd.values()),
                     "asked %s us (needs %d), read x %s, e %s, p %s us (each needs %s)"
                     % (ask, K_PLANT_US, rd["x"], rd["e"], rd["p"], _K_BAND))
    ph, why = one("photon", "patches")
    if ph is None:
        out["patches"] = (False, why)
    elif "n" not in ph:
        out["patches"] = (False, "the patch report failed (the line prints no n=)")
    else:
        # the names as written (ruling R6-A3.11.152, G1's class: no entry dropped) are PHOTON_ENTRIES exactly, each
        # once and in the emitter's order (FtPhoton.ReportPatched, plugin/FtPhoton.cs:66-69: the X targets in XNames'
        # order, then the E targets in ENames'), and n= counts them; the reading names what differs
        names = str(ph.get("names", "")).split(",")
        gone = [x for x in PHOTON_ENTRIES if x not in names]
        alien = [x or "(an empty entry)" for x in names if x not in PHOTON_ENTRIES]
        dup = sorted(set(x for x in names if x and names.count(x) > 1))
        order = not gone and not alien and not dup and tuple(names) != PHOTON_ENTRIES
        out["patches"] = (_num(ph.get("n", "")) == len(names) and tuple(names) == PHOTON_ENTRIES,
                          "n=%s for %d names%s%s%s%s" % (ph.get("n"), len(names),
                                                        "; not attached: %s" % ", ".join(gone) if gone else "",
                                                        "; not of the ten: %s" % ", ".join(alien) if alien else "",
                                                        "; named twice: %s" % ", ".join(dup) if dup else "",
                                                        "; not in the emitter's order" if order else ""))
    c, why = one("scope", "census")
    if c is None:
        out["census"] = (False, why)
    else:
        ent, wr = _num(c.get("entries", "")), _num(c.get("wrapped", ""))
        out["census"] = (ent is not None and ent > 0 and wr == ent and "failed" not in c,
                         "entries %s, wrapped %s%s" % (ent, wr, "; the census threw (failed=%s)" % c["failed"]
                                                       if "failed" in c else ""))
    return out


K_MUTANTS = {"k1": "K1", "k2": "K2", "k3": "K3"}       # P1's control mutants: the control each one breaks


def k_mutant(recs):
    """The boot's '[FRAME-TIME] controls k_mutant=<none|k1|k2|k3>' value, or None with the line's count when the log
    does not carry exactly one: (value, count)."""
    ls = [r for r in recs if r["kind"] == "controls"]
    return (str(ls[0].get("k_mutant")) if len(ls) == 1 else None), len(ls)


def refuse_k_mutant(recs, src):
    """A V6 sitting log (one carrying B11 window lines, either sitting) is no control run: its boot carries exactly
    one 'controls k_mutant=none'. Any other value, or the line absent or repeated, refuses the input by name
    (K-MUTANT) before any figure is read from it."""
    if not any(b11_line(r) for r in recs):
        return
    km, n = k_mutant(recs)
    if km != "none":
        raise Refused("K-MUTANT: the sitting log %s %s; a sitting log's boot prints exactly one 'controls "
                      "k_mutant=none' (a control run's boot is read by --controls)"
                      % (src, "prints k_mutant=%s" % km if km is not None else "carries %d controls lines" % n))


# ruling R6-A3.11.151 (2) class C: --controls names the boot's profile, in ft_arm_text.sh's words, and the k_mutant
# that profile arms
CONTROL_PROFILES = {"boot": "none", "boot-k1": "k1", "boot-k2": "k2", "boot-k3": "k3"}
CONTROLS_USAGE = ("usage: ft_parse.py --controls <profile>=<boot log>, the profile one of %s (ft_arm_text.sh's words)"
                  % ", ".join(CONTROL_PROFILES))
# every ruled line of a control boot (ruling R6-A3.11.147 (5)'s five boot lines; the controls line; the census summary;
# the attach line of .151 (3)), as (the FORMS lead whose pattern it must fullmatch, its kind, its head or None). Each
# must be present exactly once and in its form before any number is judged
CONTROL_LINES = (("alloc pin=", "alloc", None), ("scope plant asked=", "scope", "plant"),
                 ("nest plant asked=", "nest", "plant"), ("photon patches n=", "photon", "patches"),
                 ("scope census entries=", "scope", "census"), ("controls k_mutant=", "controls", None),
                 ("census registered=", "census_summary", None), ("attach n=", "attach", None))


def control_records(text):
    """CONTROL_LINES over a boot's text: the reasons a ruled line is absent, repeated or not in its form."""
    pat = dict((lead, re.compile(p)) for lead, p, _ in FORMS)
    seen = dict((lead, []) for lead, _, _ in CONTROL_LINES)
    for ln in text.splitlines():
        r = parse_line(ln)
        if r is None:
            continue
        for lead, kind, head in CONTROL_LINES:
            if r["kind"] == kind and (head is None or r["head"] == head):
                seen[lead].append(ln[ln.find("[FRAME-TIME] ") + len("[FRAME-TIME] "):].rstrip())
    bad = []
    for lead, kind, head in CONTROL_LINES:
        ls = seen[lead]
        if len(ls) != 1:
            bad.append("%d '%s' lines (needs exactly 1)" % (len(ls), lead))
        elif pat[lead].fullmatch(ls[0]) is None:
            bad.append("the '%s' line is not in its form: %s" % (lead, ls[0]))
    return bad


def controls_proof(text, profile, src="boot"):
    """A control run's boot read as the named profile (ruling R6-A3.11.151 (2) class C; P1's k_mutant). Refused
    (Refused, 'CONTROLS-REFUSED: ...') before any number is judged when: the profile is not one of CONTROL_PROFILES; the
    boot's k_mutant is not the profile's (boot reads none); a ruled line (CONTROL_LINES) is absent, repeated or not in
    its form; the scope plant or the nest plant asked another spin than K_PLANT_US; ATTACH fails (.151 (3)); the census
    summary fails; or a settled line prints problems= (the arm file not read as written). Then K1 to K3 are read from
    the numbers the boot prints (boot_controls), never from k_mutant's name: the proof holds when the controls read out
    of range are exactly the one the profile's k_mutant names (none for boot), R-SCOPE's patches and census lines are
    in range, and (ruling R6-A3.11.149 (8)) every [FRAME-TIME] line of the boot is a form the parser knows
    (unknown_forms: each is listed, and the count must be 0). Returns (ok, lines)."""
    if profile not in CONTROL_PROFILES:
        raise Refused("CONTROLS-REFUSED: '%s' is not a profile; %s" % (profile, CONTROLS_USAGE))
    refuse_withheld(text, src)
    recs = read(text, src)
    km, n = k_mutant(recs)
    want_km = CONTROL_PROFILES[profile]
    if km != want_km:
        raise Refused("CONTROLS-REFUSED: the boot log %s %s; the profile %s's boot prints k_mutant=%s"
                      % (src, "prints k_mutant=%s" % km if km is not None else "carries %d controls lines" % n,
                         profile, want_km))
    bad = control_records(text)
    for kind, head, name in (("scope", "plant", "the scope plant"), ("nest", "plant", "the nest plant")):
        asked = [_num(r.get("asked", "")) for r in recs if r["kind"] == kind and r["head"] == head]
        if len(asked) == 1 and asked[0] != K_PLANT_US:
            bad.append("%s asked=%s (the control spins %d us)" % (name, asked[0], K_PLANT_US))
    bad += ["ATTACH: " + w for w in attach_guard(text)]
    bad += ["census summary: " + w for w in census_summary(recs)[2]]
    bad += arm_problems(recs)
    if bad:
        raise Refused("CONTROLS-REFUSED: the boot log %s (profile %s): %s" % (src, profile, "; ".join(bad)))
    bc = boot_controls(recs)
    at = [r for r in recs if r["kind"] == "attach"][0]
    out = ["CONTROLS profile %s: k_mutant=%s, the profile's; every ruled line once and in its form (%s)"
           % (profile, km, ", ".join(lead.rstrip("=") for lead, _, _ in CONTROL_LINES)),
           "CONTROLS ATTACH: n=%s of=%s missing=none, no 'Failed to patch' line, the room gate attached"
           % (at["n"], at["of"])]
    out += ["CONTROLS %s %s: %s" % (k, "in range" if bc[k][0] else "OUT OF RANGE", bc[k][1]) for k in ("K1", "K2", "K3")]
    out += ["CONTROLS R-SCOPE %s %s: %s" % (k, "in range" if bc[k][0] else "OUT OF RANGE", bc[k][1])
            for k in ("patches", "census")]
    unk = unknown_forms(text)
    out += ["CONTROLS UNKNOWN FORM line %d: %s" % (i, pay) for i, pay in unk]
    out.append("CONTROLS unknown [FRAME-TIME] line forms: %d (needs 0)" % len(unk))
    want = set() if km == "none" else {K_MUTANTS[km]}
    got = set(k for k in ("K1", "K2", "K3") if not bc[k][0])
    scope = [k for k in ("patches", "census") if not bc[k][0]]
    ok = got == want and not scope and not unk
    out.append("CONTROLS PROOF %s: profile %s, k_mutant=%s; out of range %s (needs exactly %s); R-SCOPE's patches and "
               "census %s; %d unknown line forms" % ("PASS" if ok else "FAIL", profile, km, ", ".join(sorted(got)) or "none",
                                                    ", ".join(sorted(want)) or "none",
                                                    "out of range: %s" % ", ".join(scope) if scope else "in range",
                                                    len(unk)))
    return ok, out


def _bytes_k(w):
    """bK's bytes of one window: the class bytes aW to aX and wa's log, hash and sock (None while any is NA)."""
    wa = _wa(w["wa"]) or {}
    xs = [w["aW"], w["aR"], w["aS"], w["aP"], w["aX"]] + [wa.get(t) for t in WA_TYPES]
    return None if any(x is None for x in xs) else sum(xs)


def _p_cyc(w):
    """P of one window (SHARED.md V6, ruling R6-A3.11.147 (3)(g)): the larger of cP and wu's recv cycles (NA cycles
    count 0 here; they withhold the seat)."""
    return max(w["cP"], _wu_cyc(w, ("recv",)))


def u_games(recs, first_game=1, arm=None):
    """Per game, over its windows with plant=0 and res=0 (SHARED.md V6, The bound), and arm=ON only when arm is given
    (sitting C's u_g): {g: dict(n, D, P, S, X, G, u, l, T, sF, bK, bE)}. In us per live frame: D = cS + cR + cW; P the
    windows' P; S the off-thread wu cycles by type (log, hash, sock), charged whole; X = cX; G = G_cap = (bK / bE) x T
    with bK = aW + aR + aS + aP + aX + wa and bE = aC - bK; u = u_g = D + P + S + X + G; l = cS + cR + cW + cP (L's
    terms); T the game's mean live frame time. G and u are None while a byte count is NA or bE <= 0. Returns
    (games, the Stopwatch frequency)."""
    fh = _fhat(recs)
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("V6 needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    byg = {}
    for w in recs:
        if (b11_line(w) and w["game"] >= first_game and w["plant"] == 0 and w["res"] == 0
                and (arm is None or w["arm"] == arm)):
            byg.setdefault(w["game"], []).append(w)
    out = {}
    for g, ws in sorted(byg.items()):
        n = sum(w["n"] for w in ws)
        if n <= 0:
            continue
        if fh.get(g, 0) <= 0:
            raise Refused("no f_hat for game %d" % g)
        k = 1e6 / fh[g] / n
        d = sum(w["cS"] + w["cR"] + w["cW"] for w in ws) * k
        p = sum(_p_cyc(w) for w in ws) * k
        s = dict((t, sum(_wu_cyc(w, (t,)) for w in ws) * k) for t in WRITER_ADDED)
        x = sum(w["cX"] for w in ws) * k
        lo = sum(w["cS"] + w["cR"] + w["cW"] + w["cP"] for w in ws) * k
        sf = sum(w["sF"] for w in ws)
        tg = sf * 1e6 / f / n
        bs, ac = [_bytes_k(w) for w in ws], [w["aC"] for w in ws]
        bk = None if None in bs else sum(bs)
        be = None if bk is None or None in ac else sum(ac) - bk
        gc = bk / be * tg if be is not None and be > 0 else None
        u = None if gc is None else d + p + sum(s.values()) + x + gc
        out[g] = dict(n=n, D=d, P=p, S=s, X=x, G=gc, u=u, l=lo, T=tg, sF=sf, bK=bk, bE=be)
    return out, f


def _weighted(ug, key, sub=None):
    """A term's frame-weighted mean over games (the five terms then sum to U)."""
    n = sum(d["n"] for d in ug.values())
    return sum((d[key][sub] if sub else d[key]) * d["n"] for d in ug.values()) / n


def _wins(ws):
    return ", ".join("%s.%d" % (w["pt"], w["wi"]) for w in ws[:4]) + (" and %d more" % (len(ws) - 4) if len(ws) > 4
                                                                       else "")


FHAT_PAIR = 0.01            # ruling R6-A3.11.149 (6) 6: a seat's sitting-V and sitting-C logs agree in f_hat within 1 percent
# ruling R6-A3.11.149 (5)(a) and (d): the validity set (the guards that need no second arm) and the two-arm guards
VALIDITY = ("complete sitting", "census summary", "VR1", "VR2 instrument", "VR5 records", "VR6 build", "F18",
            "counters line", "line invariants", "p-line faults", "own_split", "build marker",
            # ruling R6-A3.11.151 (3): every patch class of the measuring build attached (the attach line), no 'Failed
            # to patch' line and the room gate attached; it folds the follow-up to .149, B's two rows
            "ATTACH")
TWO_ARM = ("VR2 e_C_lo", "VR3", "VR4", "VR5 OFF-window rule", "VR7", "VR8 predecessor", "VR9", "R-CARRY", "R-COMMON")
# the follow-up to ruling .149, C: a two-arm guard's word. NOT TESTED: its input is absent (R-COMMON without a
# reference log); a guard that cannot be computed although its input is present is FAIL with its reason. FAIL and
# NOT TESTED both weaken the cross-check.
TWO_WORDS = ("PASS", "FAIL", "NOT TESTED")
NOT_COMPUTABLE = (Refused, KeyError, ZeroDivisionError, ValueError)
FAILED_PATCH = "Failed to patch"
# FtRoomGate.ReportPatched's line (plugin/FtRoomGate.cs:109), counted from Harmony's own patch table
GATE_LINE = re.compile(r"\[FRAME-TIME\] FT-GATE patched (\d+) entry points expected=(\d+) excluded=(\S*)"
                       r"(?: missing=(.*))?$")
# ruling R6-A3.11.151 (3): the patch classes of the measuring build, one attach entry each, in ordinal order of the
# name: every class with a class-level [HarmonyPatch] compiled only when SCR_FRAMETIME is defined (the test holds this
# list equal to the source's set). ATTACH_CLASSES_REF is the reference build's, from P1b's hand-back (commit aa6d99e9,
# via the integrator, 12 Nov): the same without FtSockPatch, which is compiled only without SCR_FT_NOCOLLECTORS
# (plugin/FtUpload.cs:420); its line prints n=9 of=9
ATTACH_CLASSES = ("FtChurnFreezePatch", "FtDrive_InputPatch", "FtDrive_PickPatch", "FtPhotonEPatch", "FtPhotonXPatch",
                  "FtRoomGateNchRoutinePatch", "FtRoomGateNchVoidPatch", "FtRoomGatePunPatch", "FtRoute_SendPatch",
                  "FtSockPatch")
ATTACH_CLASSES_REF = tuple(c for c in ATTACH_CLASSES if c != "FtSockPatch")
_ATTACH_PAYLOAD = re.compile(r"attach n=(\d+) of=(\d+) missing=(%s) names=(%s)" % (ATTACH_MISSING, ATTACH_NAMES))


def attach_faults(text, classes=ATTACH_CLASSES):
    """The attach line's part of ATTACH (ruling R6-A3.11.151 (3)) over one boot's log text, against classes (the
    build's list): exactly one '[FRAME-TIME] attach n= of= missing= names=' line in its form, each entry Name:got/want
    with got equal to want and want above 0, the entries' names exactly classes in ordinal order, each once, of the
    entries' count, n the count of attached entries and equal to of, missing=none; and no 'attach report failed'
    line. Returns the reasons, each naming the part and the class."""
    bad, lines = [], []
    for i, ln in enumerate(text.splitlines(), 1):
        r = parse_line(ln)
        if r is None:
            continue
        if r["kind"] == "attach_failed":
            bad.append("attach report failed (line %d): %s" % (i, ln[ln.find("[FRAME-TIME]") + len("[FRAME-TIME] "):]
                                                                .rstrip()))
        elif r["kind"] == "attach":
            lines.append((i, ln[ln.find("[FRAME-TIME]") + len("[FRAME-TIME] "):].rstrip(), r))
    if len(lines) != 1:
        return ["%d 'attach' lines (needs exactly 1 per boot): the patch classes' attachment is not read"
                % len(lines)] + bad
    i, pay, r = lines[0]
    if _ATTACH_PAYLOAD.fullmatch(pay) is None:
        return ["the attach line is not in its form (line %d): %s" % (i, pay)] + bad
    n, of, missing = int(r["n"]), int(r["of"]), str(r["missing"])
    ents = [re.fullmatch(r"(%s):(\d+)/(\d+)" % ATTACH_NAME, x).groups() for x in str(r["names"]).split(",")]
    names = [x for x, _, _ in ents]
    for x, got, want in ents:
        if int(want) == 0:
            bad.append("attach %s %s/%s: want 0, no patch of the class counted" % (x, got, want))
        elif int(got) != int(want):
            bad.append("attach %s %s/%s: not every patch of the class attached" % (x, got, want))
    gone = [x for x in classes if x not in names]
    alien = [x for x in names if x not in classes]
    dup = sorted(set(x for x in names if names.count(x) > 1))
    if gone:
        bad.append("attach names lack %s (a patch class of the build)" % ",".join(gone))
    if alien:
        bad.append("attach names %s, not a patch class of the build" % ",".join(alien))
    if dup:
        bad.append("attach names %s twice" % ",".join(dup))
    if names != sorted(names):
        bad.append("attach entries not in ordinal order of the name")
    if of != len(ents):
        bad.append("attach of=%d for %d entries" % (of, len(ents)))
    ok = sum(1 for _, got, want in ents if int(want) > 0 and int(got) == int(want))
    if n != ok:
        bad.append("attach n=%d for %d entries attached" % (n, ok))
    if n != of:
        bad.append("attach n=%d of=%d: not every patch class attached" % (n, of))
    if missing != "none":
        bad.append("attach missing=%s" % missing)
    return bad


def attach_guard(text, classes=ATTACH_CLASSES):
    """ATTACH over one boot's log text (ruling R6-A3.11.151 (3)): the attach line's part (attach_faults, against
    classes), the 'Failed to patch' part (attach_patch_faults) and the room gate's part (attach_gate_faults, F17).
    Returns the reasons."""
    return attach_faults(text, classes) + attach_patch_faults(text) + attach_gate_faults(text)


def _attach_row(text, peer_text):
    """The validity set's ATTACH row: this seat's log and the peer seat's (its reasons marked 'peer seat: '), each a
    measuring build's boot (ATTACH_CLASSES)."""
    bad = attach_guard(text)
    if peer_text is not None:
        bad += ["peer seat: " + w for w in attach_guard(peer_text)]
    return _ok(bad)


def ledger_state(recs):
    """The writer ledger's disk-log tap as its one boot line prints it (FtLedger.Install, plugin/FtUpload.cs:368:
    '[FRAME-TIME] ledger log=<0|1> why=<ok|already|no_disk_listener|failed:<type>> types=<list>'; the follow-up to
    ruling .149, A): (ok, reasons, state). ok needs exactly one ledger line, log=1 (the tap installed: without it the
    log type's writes reach no term of U) and types= the parser's writer types (WRITER_TYPES: the types
    window_reconcile reads in wu and tok; u_games sums log, hash and sock and P reads recv). The list is judged as
    written (ruling R6-A3.11.152, G1; SHARED.md:245-246): its comma-split entries, none dropped, must be WRITER_TYPES
    exactly, each once and in that order, the order the emitter joins them in (FtUpload.cs:104, joined at :368); a
    repeated name, an empty entry, another order, a name missing or a name more is not the list. The log=0 reason
    names why=; state is the line's state as one phrase, its list as written."""
    ls = [r for r in recs if r["kind"] == "ledger"]
    if len(ls) != 1:
        return False, ["%d 'ledger' lines (needs exactly 1): the disk-log tap's state is not read" % len(ls)], (
            "not read (%d ledger lines)" % len(ls))
    r = ls[0]
    log, why = str(r["log"]), str(r["why"])               # REQUIRED_KEYS: read() refuses a line without them
    types = str(r["types"])
    listed = tuple(types.split(","))
    bad = []
    if log != "1":
        bad.append("ledger log=%s why=%s: the disk log is not tapped, so the log type's writes reach no term of U"
                   % (log, why))
    if listed != WRITER_TYPES:
        bad.append("ledger types=%s is not the parser's writer types %s (each once, in that order)"
                   % (types, ",".join(WRITER_TYPES)))
    return not bad, bad, "log=%s why=%s types=%s" % (log, why, types)


def attach_patch_faults(text):
    """ATTACH's 'Failed to patch' part over one boot's log text (ruling R6-A3.11.151 (3); first the follow-up to
    ruling .149, B), for every patch class of the plugin, the measuring build's and the product's: no line holds
    'Failed to patch'. Plugin's patch loop prints '[HARMONY] Failed to patch <class>: <message>' (plugin/Plugin.cs:
    1483) for a class that did not attach; the laptop's slice exports that line as 'withheld Failed to patch <n>' (its
    message is free text), which holds the same words (lesson #83: attached, or never attached). Returns the reasons,
    each naming its line and the class."""
    bad = []
    for i, ln in enumerate(text.splitlines(), 1):
        if FAILED_PATCH in ln:
            ln = ln.strip()
            bad.append("line %d: %s" % (i, ln[ln.find("[HARMONY]"):] if "[HARMONY]" in ln else ln))
    return bad


def attach_gate_faults(text):
    """ATTACH's room gate part over one boot's log text (ruling R6-A3.11.151 (3), F17; first the follow-up to ruling
    .149, B): exactly one FT-GATE patched line (GATE_LINE, FtRoomGate.ReportPatched, plugin/FtRoomGate.cs:109-111), its
    count equal to its expected count, which is above 0, and no missing= list; else the sitting's isolation is not
    proven. Returns the reasons."""
    ls = [ln.rstrip() for ln in text.splitlines() if "[FRAME-TIME] FT-GATE patched " in ln]
    if len(ls) != 1:
        return ["%d 'FT-GATE patched' lines (needs exactly 1): the room gate's attachment is not read" % len(ls)]
    m = GATE_LINE.search(ls[0])
    if m is None:
        return ["the FT-GATE patched line is not in its form: %s" % ls[0][ls[0].find("FT-GATE"):]]
    if m.group(1) != m.group(2) or int(m.group(2)) == 0 or m.group(4) is not None:
        return ["FT-GATE patched %s entry points of %s expected%s: the room gate is not attached on every entry point"
                % (m.group(1), m.group(2), "; missing=%s" % m.group(4) if m.group(4) is not None else "")]
    return []


def _ok(bad):
    return not bad, bad


def _guard(fn):
    """One validity guard's (ok, reasons). A guard that cannot be computed fails with its reason: it passes nothing."""
    try:
        ok, why = fn()
    except NOT_COMPUTABLE as x:
        return False, ["not computable: %s" % x]
    return bool(ok), list(why)


def _reasons(why, k=3):
    return "; ".join(why[:k]) + (" and %d more" % (len(why) - k) if len(why) > k else "")


def _complete_row(recs, text, peer_recs, peer_text):
    """The complete sitting and the absent-record sweep (complete(), records_missing()), with this seat's failure
    events and fixed failure texts and the peer seat's, parsed and raw (as report() sweeps them since Codex
    PARSER-FIX-R1 HIGH 2: a failure event's meaning holds for both seats)."""
    bad = complete(recs) + raw_failure_events(text) + arm_problems(recs)
    if peer_recs is None:
        bad.append("peer seat: its records were not read, so its failure events were not swept")
    else:
        bad += ["peer seat: " + w for w in failure_events(peer_recs) + raw_failure_events(peer_text or "")
                + arm_problems(peer_recs)]
    return _ok(bad)


def arm_problems(recs):
    """Ruling R6-A3.11.151 (2) class B: a settled line printing problems= (FtConfig.Load's list, plugin/FtConfig.cs:
    49-76, printed at FtCalib.cs:409: the file's stat failed, a line has no '=', or a key's value is not valid and its
    default was taken) means the boot did not read the arm file as written. Returns one reason per such line."""
    return ["settled g=%s problems=%s: the arm file was not read as written" % (r["g"], r["problems"])
            for r in recs if r["kind"] == "settled" and "problems" in r]


def _census_row(recs, peer_recs):
    bad = census_summary(recs)[2]
    if peer_recs is not None:
        bad += ["peer seat: " + w for w in census_summary(peer_recs)[2]]
    return _ok(bad)


def _vr1_row(recs, text, t, name):
    if t is None:
        return False, ["%s not computable, so the cap band is not checked" % name]
    return vr1(recs, text, t, name)


def _vr6_row(recs, peer_recs):
    ok, why, pairs, dis = vr6_build(recs)
    pdis = disarms(peer_recs) if peer_recs is not None else []
    return ok and not pdis, why + (["peer seat disarmed: " + "; ".join(pdis)] if pdis else [])


def _f18_row(recs, first_game):
    ok, reading, why, us = f18(recs, first_game)
    return ok, ["reading %s: %s" % (reading, w) for w in why]


def _own_split_row(recs, pts):
    osp = [q["pt"] for q in recs if q["kind"] == "p" and q["pt"] in pts and q.get("own_split", 1) != 0]
    return _ok(["ownership faults at %s%s" % (", ".join(osp[:4]), " and %d more" % (len(osp) - 4) if len(osp) > 4
                                              else "")] if osp else [])


def _marker_row(text, src):
    try:
        build_marker(text, "measurement", src)
    except MarkerRefused as x:
        return False, [str(x)]
    return True, []


def validity_set(recs, text, peer_recs, peer_text, t_vr1, src, first_game=1, t_name="T_ref"):
    """Ruling R6-A3.11.149 (5)(a): the guards that need no second arm, each a row (name, ok, reasons) in VALIDITY's
    order: the complete sitting and the absent-record sweep with the failure events and the fixed failure texts (both
    seats'); the census summary (both seats'); VR1 at t_vr1, named t_name (sitting V: T_on, ruling (6) 3; sitting C: T_ref
    as built); VR2's instrument half; VR5's records half; VR6's build half with both seats' disarm lines; F18; the
    counters line of every game 0 to 16 (span_leave_mismatch 0); every line invariant; the p-line faults and own_split
    over the points of the measured games, void rounds kept; the build marker (a failed one withholds here, naming its
    word; report() still refuses it); and ATTACH (ruling R6-A3.11.151 (3)): every patch class of the measuring build
    attached by the attach line, no 'Failed to patch' line and the room gate attached, both seats' (_attach_row).
    Sitting V withholds B1 on any failed row (sitting_v); sitting C has no cross-check
    while any row fails (sitting_c). (5)(b)'s exception is empty: the one record the emitter writes only after OFF
    windows, the plant line (FtPlant.Fix, plugin/FtPlant.cs:35, called at plugin/FtFrames.cs:285-287 once a game's OFF
    frames reach a window), is not in the sweep (records_missing, complete); e_c, a two-arm guard, reads it. So sitting
    V's sweep leaves nothing out."""
    pts = set(q["pt"] for q in recs if q["kind"] == "p" and q["game"] >= first_game)
    rows = []
    rows.append(("complete sitting",) + _guard(lambda: _complete_row(recs, text, peer_recs, peer_text)))
    rows.append(("census summary",) + _guard(lambda: _census_row(recs, peer_recs)))
    rows.append(("VR1",) + _guard(lambda: _vr1_row(recs, text, t_vr1, t_name)))
    rows.append(("VR2 instrument",) + _guard(lambda: vr2(recs, LAST_GAME)))
    rows.append(("VR5 records",) + _guard(lambda: vr5_records(recs, 0, LAST_GAME)))
    rows.append(("VR6 build",) + _guard(lambda: _vr6_row(recs, peer_recs)))
    rows.append(("F18",) + _guard(lambda: _f18_row(recs, first_game)))
    rows.append(("counters line",) + _guard(lambda: _ok(counters_faults(recs, range(0, LAST_GAME + 1)))))
    rows.append(("line invariants",) + _guard(lambda: _ok(window_reconcile(recs))))
    rows.append(("p-line faults",) + _guard(lambda: _ok(p_line_faults(recs, pts))))
    rows.append(("own_split",) + _guard(lambda: _own_split_row(recs, pts)))
    rows.append(("build marker",) + _guard(lambda: _marker_row(text, src)))
    rows.append(("ATTACH",) + _guard(lambda: _attach_row(text, peer_text)))
    return rows


def _two(name, fn):
    """One two-arm guard's row (name, word, detail), its word one of TWO_WORDS: fn returns (True, detail) PASS,
    (False, detail) FAIL or (None, detail) NOT TESTED (its input is absent); a guard that cannot be computed although
    its input is present is FAIL with its reason."""
    try:
        ok, det = fn()
    except NOT_COMPUTABLE as x:
        return name, "FAIL", "not computable: %s" % x
    return name, "NOT TESTED" if ok is None else ("PASS" if ok else "FAIL"), det


def _weak(two):
    """The two-arm rows that weaken the cross-check: each one not PASS (FAIL or NOT TESTED)."""
    return [(nm, w, d) for nm, w, d in two if w != "PASS"]


def _weak_text(weak):
    """The weakening guards as the verdict line names them, each with its word: 'R-COMMON (not tested: no reference
    log)', 'VR7 (fail)'; a FAIL's reason stands on its TWO-ARM line."""
    return ", ".join("%s (%s)" % (nm, "not tested: %s" % d if w == "NOT TESTED" else "fail") for nm, w, d in weak)


def _need_e(e):
    if e is None:
        raise Refused("no contrast")
    return e


def _two_ec(recs, first_game):
    m, hw, df, elo, ng, miss = e_c(recs, first_game=first_game)
    return elo >= 0.5, "e_C %.4f, lower end %.4f (needs at least 0.5)" % (m, elo)


def _two_vr3(recs):
    est, hw, df, r1 = dC(recs)
    return r1 <= VR3_MAX, "lag-1 %.3f (max %.3f)" % (r1, VR3_MAX)


def _two_vr4(e):
    e = _need_e(e)
    return vr4(e["hw"], e["tref"]), ("the contrast's half-width %.3f us against 1.5 percent of T_ref as built, %.2f us"
                                     % (e["hw"], 0.015 * e["tref"]))


def _two_vr5(recs):
    ok, bad = vr5_points(recs)
    return ok, _reasons(bad) if bad else "holds"


def _two_vr7(recs, first_game):
    ok, bad = vr7(recs, first_game)
    return ok, _reasons(bad) if bad else "no H fails"


def _two_vr8(recs, first_game):
    flag, a, b = predecessor(recs, first_game)
    return not flag, "%s (after ON %d rounds, after OFF %d)" % ("FLAG" if flag else "no flag", len(a), len(b))


def _two_vr9(recs, e, first_game):
    e = _need_e(e)
    elo = e_c(recs, first_game=first_game)[3]
    bound = max(0.0, e["bu"]) / min(1.0, max(elo, 1e-9))
    ok, lo = vr9(recs, bound, first_game)
    return ok, "gated span time per ON live frame, lower end %.2f us, against %.2f us" % (lo, bound)


def _two_carry(e):
    e = _need_e(e)
    fals = [a for a in ("ON", "OFF") if e["d10"][a][0] - e["d10"][a][1] > 0]
    return not fals, "d_ON,10 %.3f +- %.3f us, d_OFF,10 %.3f +- %.3f us%s" % (
        e["d10"]["ON"][0], e["d10"]["ON"][1], e["d10"]["OFF"][0], e["d10"]["OFF"][1],
        ": FALSIFIED in %s" % "/".join(fals) if fals else "")


def _two_common(recs, e, ref_recs, first_game):
    if ref_recs is None:
        return None, "no reference log"            # the follow-up to ruling .149, C: its input is absent
    e = _need_e(e)
    if e["dcommon"] is None:
        raise Refused("no ordinary full OFF window for D_common")
    tot, tlo = reference_common_cost(recs, ref_recs, first_game)
    bar = (1.0 + e["r_u"]) * e["dcommon"]
    return not r_common_check(tlo, e["r_u"], e["dcommon"]), (
        "the reference's total common cost %.3f us (lower end %.3f) against (1 + r_U) D_common %.3f us" % (tot, tlo, bar))


def two_arm(recs, e, ref_recs, first_game=1):
    """Ruling R6-A3.11.149 (5)(d): the guards that need both arms, judged on sitting C as built and printed beside the
    contrast, each a row (name, word, detail) in TWO_ARM's order (_two). A guard that cannot be computed is FAIL,
    R-COMMON without a reference NOT TESTED; either weakens the cross-check as a failed one does (the follow-up to
    ruling .149, C); none decides the refutation test
    (cross_state). In the window design VR4 reads the cross-check's own half-width against T_ref as built, and VR9's
    bound is the cross-check's corrected upper bound over min(1, e_C_lo); e is the cross-check (None when it did not
    run: the rows that read it are then not computable)."""
    rows = []
    rows.append(_two("VR2 e_C_lo", lambda: _two_ec(recs, first_game)))
    rows.append(_two("VR3", lambda: _two_vr3(recs)))
    rows.append(_two("VR4", lambda: _two_vr4(e)))
    rows.append(_two("VR5 OFF-window rule", lambda: _two_vr5(recs)))
    rows.append(_two("VR7", lambda: _two_vr7(recs, first_game)))
    rows.append(_two("VR8 predecessor", lambda: _two_vr8(recs, first_game)))
    rows.append(_two("VR9", lambda: _two_vr9(recs, e, first_game)))
    rows.append(_two("R-CARRY", lambda: _two_carry(e)))
    rows.append(_two("R-COMMON", lambda: _two_common(recs, e, ref_recs, first_game)))
    return rows


def cross_state(unavail, e, u_hi, weak):
    """Ruling R6-A3.11.149 (5)(e): the cross-check's state on the seat's B1 verdict line, and whether it withholds B1.
    'unavailable (<guards>)' when sitting C's validity set failed or its contrast did not run (a log that is not a
    valid measurement refutes nothing); 'REFUTED' when the contrast's lower end is above U_hi; else 'not refuted', or
    'not refuted, weakened by <guard> (<word>), ...' when a two-arm guard did not pass (weak: _weak's rows; the
    follow-up to ruling .149, C). Unavailable and REFUTED withhold."""
    if unavail:
        return "unavailable (%s)" % ", ".join(unavail), True
    if u_hi is None:
        return "unavailable (no U_hi to test: U not computable)", True
    if e["lb"] > u_hi:
        return "REFUTED", True
    if weak:
        return "not refuted, weakened by %s" % _weak_text(weak), False
    return "not refuted", False


def _b3(recs):
    """B3 on one sitting's log: (True, []) holds, (False, reasons) violated, (None, [reason]) not computable."""
    try:
        ok, why, ops = b3(recs)
    except NOT_COMPUTABLE as x:
        return None, ["not computable: %s" % x]
    return ok, why


def _b3_word(b):
    return "holds" if b[0] else ("VIOLATED: %s" % _reasons(b[1]) if b[0] is False else _reasons(b[1]))


def seat_fhat(recs, first_game=1):
    """The seat's f_hat (ruling R6-A3.11.149 (6) 6, the pairing check): the median over the measured games' settled
    lines, or None when none prints one."""
    fs = [r["f_hat"] for r in recs if r["kind"] == "settled" and r["g"] >= first_game and r.get("f_hat", 0) > 0]
    return statistics.median(fs) if fs else None


def sitting_c(recs, text, peer_recs, peer_text, ref_recs, src, first_game=1):
    """One seat's sitting C (ruling R6-A3.11.149 (5)(c), (d), (g)): the validity set at T_ref as built (any failure
    makes the cross-check unavailable for this seat), the cross-check (the as-built contrast with T_ref as built; a
    forced input or an estimator refusal also makes it unavailable), the two-arm guards, B3 and VR8's zero-state half
    (reported). peer_recs and peer_text are the other seat's sitting-C log, ref_recs this seat's reference record set or
    None. Returns a dict."""
    try:
        t_c = t_ref_windows(recs, first_game)
    except NOT_COMPUTABLE:
        t_c = None
    rows = validity_set(recs, text, peer_recs, peer_text, t_c, src, first_game, "T_ref as built")
    unavail = [n for n, ok, _ in rows if not ok]
    e = ewhy = None
    try:
        contrast_input(recs)
        e = b11_estimate(recs, first_game)
        if t_c is None:
            raise Refused("T_ref as built not computable")
        e["tref"] = t_c
    except NOT_COMPUTABLE as x:
        e, ewhy = None, str(x)
        unavail.append("contrast: %s" % x)
    return dict(rows=rows, unavail=unavail, e=e, ewhy=ewhy, two=two_arm(recs, e, ref_recs, first_game), b3=_b3(recs),
                zero=_zero(recs), fhat=seat_fhat(recs, first_game))


def _zero(recs):
    """VR8's zero-state half, reported only: zero_state's tuple, or its reason (a string) when it cannot be computed
    (the follow-up to ruling .149, D: a reported value never ends the report)."""
    try:
        return zero_state(recs)
    except NOT_COMPUTABLE as x:
        return "not computable: %s" % x


def _pct(u, t):
    """U_hi as a percent of T_ref, reported: 'not computable' when T_ref is not above 0 (the class reads T_ref
    itself)."""
    return "%.3f percent" % (100 * u / t) if t > 0 else "not computable: T_ref %.1f us is not above 0" % t


def sitting_v(recs, text, peer_recs, peer_text, src, first_game=1):
    """One seat's sitting V (SHARED.md V6, The bound; ruling R6-A3.11.149 (5)(b), (f), (g) and (6) 3): U and its five
    terms, hw, df, U_hi = U + hw, L, T_on, T_ref = T_on - U_hi, the class classify(U_hi, T_ref, hw, L), the games' u_g,
    R-GC's sitting-V figures, the validity set (validity_set; VR1 reads T_on), VR8's zero-state half (reported, not
    judged: void rounds stay in the population, game 0 stays out), B3 on this sitting, the seat's f_hat for the pairing
    check, and the WITHHELD list: V6's own conditions and each failed validity guard by name. peer_recs and peer_text
    are the other seat's sitting-V log: the arm and force conditions hold on either seat, and its failure events,
    census summary and disarm lines join this seat's guards. Returns a dict."""
    why = []
    for who, rr in (("this seat", recs), ("the peer seat", peer_recs)):
        off = [w for w in rr if b11_line(w) and w["arm"] != "ON"]
        if off:
            why.append("sitting V: %s prints arm=OFF in %d windows (%s)" % (who, len(off), _wins(off)))
        nf = [(r["g"], r.get("force")) for r in rr if r["kind"] == "settled" and r.get("force") != FORCE_V]
        if nf:
            why.append("sitting V: %s's settled lines print another force= than ON (%s)"
                       % (who, ", ".join("g=%s force=%s" % x for x in nf)))
    meas = [w for w in recs if b11_line(w) and w["game"] >= first_game]
    na = [w for w in meas if any(w[a] is None for a in A_FIELDS) or None in (_wa(w["wa"]) or {}).values()]
    if na:
        why.append("an a* or wa value prints NA in %d windows (%s): the allocation counter is unavailable"
                   % (len(na), _wins(na)))
    bc = boot_controls(recs)
    if not bc["pin"][0]:
        why.append("the counter's pin differs or is not read (%s)" % bc["pin"][1])
    for k in ("K1", "K2", "K3"):
        if not bc[k][0]:
            why.append("control %s out of range (%s)" % (k, bc[k][1]))
    for k in ("patches", "census"):
        if not bc[k][0]:
            why.append("R-SCOPE's %s line out of range (%s)" % (k, bc[k][1]))
    # the follow-up to ruling .149, A: this seat's disk-log tap installed, its types the parser's
    lok, lwhy, _ = ledger_state(recs)
    why += ["the disk-log tap: %s" % w for w in lwhy]
    pts = [q for q in recs if q["kind"] == "p" and q["game"] >= first_game]
    back = [q["pt"] for q in pts if q.get("ab_back", 1) != 0]
    if back:
        why.append("ab_back above 0 or not printed at %s" % ", ".join(back[:4]))
    # ruling R6-A3.11.151 (2) class B: ab_retry counts a read of the allocation counter whose two takes never agreed
    # (plugin/FtAlloc.cs:102; SHARED.md:57-58), whose bytes may be torn, so it withholds as ab_back does
    retry = [q["pt"] for q in pts if q.get("ab_retry", 1) != 0]
    if retry:
        why.append("ab_retry above 0 or not printed at %s" % ", ".join(retry[:4]))
    # ruling R6-A3.11.151 (2) class B: sitting V runs every window ON, so the gate is never off (FtSchedule.cs:215-219):
    # a guarded return in it is a collector that did not run, which no term of U would hold
    why += ["VR5's window counters: %s" % w for w in gate_counter_faults(recs, set(q["pt"] for q in pts))]
    wna =sorted(set(t for w in meas for t, x in sorted((_typed(w["wu"], 2, na=True) or {}).items())
                     if x[1] is None))
    if wna:
        why.append("a wu type prints NA cycles (%s)" % ", ".join(wna))
    v = dict(games={}, why=why, U=None, hw=None, df=None, U_hi=None, L=None, T_on=None, T_ref=None, cls=None,
             terms=None, bK=None, heap=None, N=None)
    pl = [q for q in recs if q["kind"] == "p"]
    v["heap"] = pl[-1].get("heap") if pl else None
    # R-GC's sitting-V total (SHARED.md:250-253; ruling R6-A3.11.151 (2) class D, F9): the collectors' bytes over every
    # measured window of the sitting, planted or not, res or not; the estimator's own filter (u_games) stays its own
    bs = [_bytes_k(w) for w in meas]
    v["bK_all"] = None if None in bs else sum(bs)
    v["bK_windows"] = len(meas)
    # reported only (no rule reads it): X and listener scopes entered off the main thread, over the measured games
    v["photon_offmain"] = sum(r.get("photon_offmain") or 0 for r in recs
                              if r["kind"] == "counters" and r.get("g", -1) >= first_game)
    try:
        ug, f = u_games(recs, first_game)
    except NOT_COMPUTABLE as x:
        ug, f = {}, None
        why.append("U not computable: %s" % x)
    v["games"] = ug
    if ug:
        N = sum(d["n"] for d in ug.values())
        v.update(N=N, T_on=sum(d["sF"] for d in ug.values()) * 1e6 / f / N)
    be = sorted(g for g, d in ug.items() if d["bE"] is not None and d["bE"] <= 0)
    if be:
        why.append("bE is 0 or below in games %s" % ", ".join(map(str, be)))
    if len(ug) < MIN_GAMES_V:
        why.append("%d games remain (needs at least %d)" % (len(ug), MIN_GAMES_V))
    pairs = [(d["u"], d["n"]) for g, d in sorted(ug.items())]
    if not pairs or any(u is None for u, n in pairs):
        why.append("U not computable: a game's G_cap has an NA byte count or bE <= 0" if pairs
                   else "U not computable: no window with plant=0 and res=0 in a measured game")
    else:
        try:
            U, hw, df = fw_interval(pairs, Z_END)
            le, lh, _ = fw_interval([(d["l"], d["n"]) for g, d in sorted(ug.items())], Z_END)
        except NOT_COMPUTABLE as x:
            why.append("U not computable: fw_interval over %d games (%s)" % (len(pairs), x))
        else:
            u_hi = U + hw
            t_ref = v["T_on"] - u_hi
            v.update(U=U, hw=hw, df=df, U_hi=u_hi, L=le - lh, T_ref=t_ref,
                     cls=classify(u_hi, t_ref, hw, le - lh), bK=sum(d["bK"] for d in ug.values()),
                     terms=dict(D=_weighted(ug, "D"), P=_weighted(ug, "P"), X=_weighted(ug, "X"), G=_weighted(ug, "G"),
                                S=dict((t, _weighted(ug, "S", t)) for t in WRITER_ADDED)))
    t_vr1 = v["T_on"]                   # ruling R6-A3.11.149 (6) 3: VR1 reads T_on, the frames' observed mean
    rows = validity_set(recs, text, peer_recs, peer_text, t_vr1, src, first_game, "T_on")
    for name, ok, w in rows:
        if not ok:
            why.append("%s: %s" % (name, _reasons(w)))
    v.update(validity=rows, zero=_zero(recs), b3=_b3(recs), fhat=seat_fhat(recs, first_game))
    return v


def _validity_lines(head, rows):
    return ["%s %s %s%s" % (head, n, "PASS" if ok else "FAIL", ": " + _reasons(w) if not ok else "") for n, ok, w in rows]


def _zero_line(head, z):
    if isinstance(z, str):
        return "%s (reported, not judged; ruling R6-A3.11.149 (5)(f)): %s" % (head, z)
    zok, g0v, g0n, meas, empty = z
    return ("%s (reported, not judged; ruling R6-A3.11.149 (5)(f)): game 0 (the mutant) %d of %d rounds void; the "
            "measured games %d rounds void, kept in the population%s" % (head, g0v, g0n, len(meas),
                                                                      "; games with no valid round %s" % empty
                                                                      if empty else ""))


def rgc_v_line(label, v):
    """R-GC's sitting-V line (SHARED.md:250-253; ruling R6-A3.11.151 (2) class D, F9): the collectors' bytes over every
    measured window against heap= at the sitting's end, reported whether or not U is computable; a total or a share
    that cannot be computed prints 'not computable' with its reason."""
    if v["bK_all"] is None:
        tot = "not computable: an a* or wa value prints NA in a measured window"
    else:
        tot = "%d over the sitting's %d measured windows" % (v["bK_all"], v["bK_windows"])
    if v["heap"] is None:
        share = "heap= not read"
    elif v["bK_all"] is None:
        share = "heap=%d at its end" % v["heap"]
    elif v["heap"] <= 0:
        share = "heap=%d at its end; its share not computable: heap= is not above 0" % v["heap"]
    else:
        share = "heap=%d at its end (%.4f of it)" % (v["heap"], v["bK_all"] / v["heap"])
    return "R-GC (sitting V) seat %s: the collectors' bytes %s against %s" % (label, tot, share)


def v_lines(label, v):
    """sitting_v's figures as report lines: U and its five terms whenever U is computable, whatever the class (ruling
    R6-A3.11.149 (8)), each validity guard's result, VR8's zero-state half, B3, and the WITHHELD list last."""
    out = []
    ug = v["games"]
    if v["U"] is None:
        out.append("V6 SITTING V seat %s: U not computable (%d games)" % (label, len(ug)))
    else:
        t = v["terms"]
        out.append("V6 SITTING V seat %s: %d games, %d live frames (windows with plant=0 and res=0)"
                   % (label, len(ug), v["N"]))
        out.append("V6 U %.3f us per live frame = D %.3f + P %.3f + S %.3f (log %.3f, hash %.3f, sock %.3f) + X %.3f + "
                   "G_cap %.3f; half-width %.3f at z %.4f, df %d; U_hi %.3f us"
                   % (v["U"], t["D"], t["P"], sum(t["S"].values()), t["S"]["log"], t["S"]["hash"], t["S"]["sock"],
                      t["X"], t["G"], v["hw"], Z_END, v["df"], v["U_hi"]))
        out.append("V6 L %.3f us (cS + cR + cW + cP alone, the interval's lower end); T_on %.1f us; T_ref = T_on - U_hi "
                   "%.1f us; U_hi as a percent of T_ref: %s" % (v["L"], v["T_on"], v["T_ref"],
                                                                _pct(v["U_hi"], v["T_ref"])))
        out.append("V6 class %s (classify(U_hi, T_ref, hw, L): PASS <= 3, SID <= 5, FAIL > 5 percent, WITHHELD when "
                   "the band is unresolved)%s" % (v["cls"], "; B1 is WITHHELD for this seat by the list below"
                                                  if v["why"] else ""))
    out.append(rgc_v_line(label, v))
    out.append("V6 u_g seat %s: %s" % (label, "; ".join("g%d %s (n %d)" % (g, "%.3f" % d["u"] if d["u"] is not None
                                                                         else "NA", d["n"]) for g, d in sorted(ug.items()))
                                      or "none"))
    out.append("V6 photon_offmain seat %s: %d over the measured games (X and listener scopes entered off the main "
               "thread; reported only)" % (label, v["photon_offmain"]))
    out.append("V6 f_hat seat %s: %s (the median over the measured games' settled lines; the pairing check reads it)"
               % (label, "%.0f" % v["fhat"] if v["fhat"] is not None else "not read"))
    out += _validity_lines("V6 VALIDITY seat %s" % label, v["validity"])
    out.append(_zero_line("V6 VR8 zero-state seat %s" % label, v["zero"]))
    out.append("V6 B3 sitting V seat %s: %s" % (label, _b3_word(v["b3"])))
    out.append("V6 WITHHELD seat %s: %s" % (label, "; ".join(v["why"]) if v["why"] else "none"))
    return out


def read_sitting(text, src):
    """A measurement input of either sitting: the withheld-line refusal, the records, and the control-mutant refusal.
    Its build marker is a guard of the validity set (ruling R6-A3.11.149 (5)(a)): a failed one withholds, by name."""
    refuse_withheld(text, src)
    recs = read(text, src)
    refuse_k_mutant(recs, src)                  # a sitting input of either sitting
    return recs


def _two_seats(seats, what):
    names = list(seats)
    if len(names) != 2 or any(not re.fullmatch(r"[A-Za-z0-9][\w.-]*", n) for n in names):
        raise Refused("PAIRING: %s takes exactly two seats, each by its name (got %s)" % (what, names))
    return names


def report_on(seats, first_game=1):
    """Sitting V's report (SHARED.md V6, What P2 builds; ruling R6-A3.11.149 (8)): seats is {seat name: its sitting-V
    log}, two seats. For each seat, U and its five terms, U_hi, L, T_ref and the class (also when B1 is WITHHELD), each
    validity guard's result, VR8's zero-state half, B3 and the WITHHELD list. Returns (lines, [sitting_v per seat, in
    the order named])."""
    a, b = _two_seats(seats, "report_on")
    ra, rb = read_sitting(seats[a], "V:" + a), read_sitting(seats[b], "V:" + b)
    va = sitting_v(ra, seats[a], rb, seats[b], "V:" + a, first_game)
    vb = sitting_v(rb, seats[b], ra, seats[a], "V:" + b, first_game)
    return v_lines(a, va) + v_lines(b, vb), [va, vb]


def gc_per_mb(ws):
    """R-GC: collections per MB (1e6 bytes) of aC by arm, over windows ws; None for an arm with no bytes or an NA."""
    out = {}
    for arm in ("ON", "OFF"):
        xs = [w for w in ws if w["arm"] == arm]
        b = None if any(w["aC"] is None for w in xs) else sum(w["aC"] for w in xs)
        out[arm] = sum(w["gcn"] for w in xs) * 1e6 / b if b else None
    return out


def _fh(x):
    return "%.0f" % x if x is not None else "not read"


def combine(v_logs, c_logs, refs=None, first_game=1):
    """The combining step (SHARED.md V6, What P2 builds; ruling R6-A3.11.149 (5), (6) 6 and 7): v_logs and c_logs are
    {seat name: its sitting-V log} and {seat name: its sitting-C log} for the same two seats, refs {seat name: its
    reference log} for any of them. A seat's logs are paired by its NAME, never by position, and the pairing is checked:
    the seat's two logs agree in f_hat within 1 percent (when the two seats' own values are that close, the check says
    it cannot tell them apart). Per seat it prints sitting C's validity set, the cross-check, the two-arm guards beside
    it, R-GC's and R-WORK's numbers, then VERDICT B1 (PASS, SID, FAIL or WITHHELD with its reason) with the cross-check's
    state, and VERDICT B3 (judged on both sittings, holding only when it holds in both); then the worse seat. Returns
    the report text."""
    names = _two_seats(v_logs, "the combining step")
    if sorted(c_logs) != sorted(names) or any(n not in names for n in (refs or {})):
        raise Refused("PAIRING: sitting C's seats %s (and the references' %s) are not sitting V's %s"
                      % (sorted(c_logs), sorted(refs or {}), sorted(names)))
    out, vl = report_on(v_logs, first_game)
    vs = dict(zip(names, vl))
    pair = dict((n, c_logs[n]) for n in names)          # ruling .149 (6) 6: by name, never by position
    crecs = dict((n, read_sitting(pair[n], "C:" + n)) for n in names)
    refr = dict((n, read_reference(t, "R:" + n)) for n, t in (refs or {}).items())
    fc = dict((n, seat_fhat(crecs[n], first_game)) for n in names)
    paired = {}
    for n in names:
        fv = vs[n]["fhat"]
        paired[n] = fv is not None and fc[n] is not None and abs(fc[n] - fv) <= FHAT_PAIR * fv
        out.append("PAIRING seat %s: f_hat sitting V %s, sitting C %s: %s" % (
            n, _fh(fv), _fh(fc[n]), "agree within 1 percent" if paired[n] else "NOT within 1 percent (or not read)"))
    a, b = names
    fa, fb = vs[a]["fhat"], vs[b]["fhat"]
    if fa is not None and fb is not None and abs(fa - fb) <= FHAT_PAIR * max(fa, fb):
        out.append("PAIRING: the two seats' own f_hat (%s %s, %s %s) are within 1 percent of each other, so the check "
                   "cannot tell the seats apart; the pairing rests on the names" % (a, _fh(fa), b, _fh(fb)))
    seats = []
    for n in names:
        o = b if n == a else a
        v = vs[n]
        sc = sitting_c(crecs[n], pair[n], crecs[o], pair[o], refr.get(n), "C:" + n, first_game)
        e = sc["e"]
        out += _validity_lines("V6 VALIDITY sitting C seat %s" % n, sc["rows"])
        if e is None:
            out.append("V6 CROSS-CHECK seat %s: no contrast (%s)" % (n, sc["ewhy"]))
        else:
            out.append("V6 CROSS-CHECK seat %s: contrast %.3f us per frame, interval %.3f to %.3f; half-width %.3f "
                       "against the band's 3 percent of T_ref as built %.1f us (%.1f us)"
                       % (n, e["center"], e["lb"], e["bu"], e["hw"], e["tref"], 0.03 * e["tref"]))
        out += ["V6 TWO-ARM seat %s %s %s: %s" % (n, nm, w, d) for nm, w, d in sc["two"]]
        # ruling R6-A3.11.151 (2) class D, F16 (SHARED.md:254-261): the cross-check's residual statements beside its
        # interval, as the as-built report prints them
        out += ["  " + x for x in CROSS_RISKS]
        # the follow-up to ruling .149, D: R-GC's and R-WORK's numbers are reported only, so each is computed inside
        # its own guard and a value that cannot be computed is printed as such; the verdict lines still follow
        if e is not None:
            try:
                gm = gc_per_mb(e["T"]["pop"])
                gt = "ON %s, OFF %s" % tuple("%.4f" % gm[x] if gm[x] is not None else "not computable"
                                             for x in ("ON", "OFF"))
            except NOT_COMPUTABLE as x:
                gt = "not computable: %s" % x
            out.append("R-GC (sitting C) seat %s: collections per MB of aC, %s" % (n, gt))
        try:
            ugc, _ = u_games(crecs[n], first_game, arm="ON")
            ct = "; ".join("g%d %s" % (g, "%.3f" % d["u"] if d["u"] is not None else "NA")
                           for g, d in sorted(ugc.items())) or "none"
        except NOT_COMPUTABLE as x:
            ct = "not computable: %s" % x
        # the follow-up to ruling .149, A: sitting C's disk-log tap beside its ON windows' u_g (reported only)
        lok, lwhy, lst = ledger_state(crecs[n])
        out.append("R-WORK seat %s: u_g sitting V %s; sitting C's ON windows %s; sitting C's disk-log tap %s%s "
                   "(reported)" % (n, "; ".join("g%d %s" % (g, "%.3f" % d["u"] if d["u"] is not None else "NA")
                                                for g, d in sorted(v["games"].items())) or "none", ct, lst,
                                   "" if lok else ": " + "; ".join(lwhy)))
        out.append(_zero_line("V6 VR8 zero-state sitting C seat %s" % n, sc["zero"]))
        weak = _weak(sc["two"])
        state, wh = cross_state(sc["unavail"], e, v["U_hi"], weak)
        if not paired[n]:
            cls, txt = "WITHHELD", ("WITHHELD: the pairing check fails: the seat's sitting-V and sitting-C logs do not "
                                    "agree in f_hat within 1 percent")
        elif v["why"]:
            cls, txt = "WITHHELD", "WITHHELD: %s" % "; ".join(v["why"])
        elif v["U_hi"] is None:
            cls, txt = "WITHHELD", "WITHHELD: U not computable"
        elif state == "REFUTED":
            cls, txt = "WITHHELD", ("WITHHELD: the contrast's lower end %.3f us is above U_hi %.3f us (U is refuted)"
                                    % (e["lb"], v["U_hi"]))
        elif wh:
            cls, txt = "WITHHELD", "WITHHELD: sitting C gives no cross-check until it has run again"
        else:
            cls = v["cls"]
            txt = "%s: %sU_hi %.2f us against T_ref %.1f us (%s); the contrast's lower end %.3f us" % (
                cls, "the band is unresolved (half-width %.3f us, L %.3f us); " % (v["hw"], v["L"])
                if cls == "WITHHELD" else "", v["U_hi"], v["T_ref"], _pct(v["U_hi"], v["T_ref"]), e["lb"])
        seats.append((n, cls))
        out.append("VERDICT B1 seat %s %s; cross-check %s" % (n, txt, state))
        b3s = (("V", v["b3"]), ("C", sc["b3"]))         # ruling .149 (5)(g): judged on both sittings
        inval = (["sitting V's " + nm for nm, ok, _ in v["validity"] if not ok]
                 + ["sitting C's " + nm for nm, ok, _ in sc["rows"] if not ok])
        if inval:
            c3 = "WITHHELD: the validity set fails (%s)" % ", ".join(inval)
        elif any(x[0] is None for _, x in b3s):
            c3 = "WITHHELD: %s" % "; ".join("sitting %s %s" % (s, _reasons(x[1])) for s, x in b3s if x[0] is None)
        elif all(x[0] for _, x in b3s):
            c3 = "PASS"
        else:
            c3 = "FAIL: %s" % "; ".join("sitting %s %s" % (s, _b3_word(x)) for s, x in b3s if not x[0])
        out.append("VERDICT B3 seat %s %s (holds only when it holds in both sittings: %s); conditional on VR6's "
                   "file-listing half from frame_time_seat.ps1's report"
                   % (n, c3, ", ".join("sitting %s %s" % (s, _b3_word(x)) for s, x in b3s)))
    worst = max(range(len(seats)), key=lambda j: RANK[seats[j][1]])
    out.append("VERDICT B1 worse seat: seat %s %s" % seats[worst])
    out += ["  " + x for x in V_RISKS]
    return "\n".join(out)


QUALIFY = ("conditional: U bounds the NET main-thread CPU the seven components add per live-combat frame on this "
           "seat at the recorded load (their work minus the CPU it displaces); the gross cost only under the "
           "absorption premise, which VR9 tests inside the spans only; confidence at least 95 percent for "
           "persistence up to rho = 0.9 per point; dispatch in play assumed no dearer per call than in its "
           "calibration (R1); the upkeep's own GC and cache effects outside its spans are not in K_up (R10); "
           "VR6's file-listing half is frame_time_seat.ps1's report")


def report(text, peer=None, src="log", peer_src="peer", ref=None, ref_src="reference"):
    """The verdict report of a two-seat sitting: text is this seat's log, peer the other seat's (rulings
    FRAME-TIME-ROUND-R4 and R5: every dependent row is calibrated by its in-game executed lines, read from both logs).
    Round-5 MEDIUM (ft_parse.py:1643): no verdict is produced from one seat's log; without the peer's, while the
    inventory has a dependent row, the report is Refused (no bypass parameter). A menu run's check is a one-seat
    report and produces no verdict. ref is R-COMMON's reference record set (a FrameTimeRef build's log), read only
    by R-COMMON's comparator; every measurement input carries the FrameTime marker and the reference its own
    (build_marker). A window log's report is sitting C's cross-check and gives no B1 verdict (SHARED.md V6)."""
    # ruling R6-A3.11.113 (2)(a): both inputs are checked for a withheld line of a read class before any record of
    # either is read
    refuse_withheld(text, src)
    if peer is not None:
        refuse_withheld(peer, peer_src)
    recs = read(text, src)
    build_marker(text, "measurement", src)
    if any(r["kind"] in ("menu", "menu_done") for r in recs):
        return menu_report(recs, text)
    if peer is None and any(r[2] == "dependent" for r in a3_spec()):
        raise Refused("a verdict needs both seats' logs: the dependent rows' in-game calibration is read from each "
                      "(rulings FRAME-TIME-ROUND-R4 and R5); no peer log was given")
    # the peer's records are read here, so a RecordRefused names the peer before any verdict; a Refused from its
    # read keeps its old place (the U block below reports it as not computable)
    peer_recs = peer_err = None
    if peer is not None:
        try:
            peer_recs = read(peer, peer_src)
        except Refused as e:
            peer_err = e
        build_marker(peer, "measurement", peer_src)
    # P1's V6 emitter (via the integrator, 12 Nov): a window log of either seat whose boot is a control run's is no
    # sitting log
    refuse_k_mutant(recs, src)
    if peer_recs is not None:
        refuse_k_mutant(peer_recs, peer_src)
    ref_recs = read_reference(ref, ref_src) if ref is not None else None
    out = []
    vr = {}
    miss = complete(recs)
    miss += raw_failure_events(text)
    # Codex PARSER-FIX-R1 HIGH 2: a failure event's meaning (a step of the sitting threw, or the room gate's isolation
    # is not proven) holds for both seats, so the peer's log is swept for them too, parsed and raw; a peer log that
    # could not be read cannot be swept, which withholds the verdicts as well
    if peer is not None:
        miss += ["peer seat: " + w for w in raw_failure_events(peer)]
        if peer_recs is not None:
            miss += ["peer seat: " + w for w in failure_events(peer_recs)]
        else:
            miss.append("peer seat: its failure events not read (%s)" % peer_err)
    # the census summary of each seat's log (this seat's misses are complete()'s); a failed check withholds the
    # verdicts as every completeness miss does
    oks, rds, _ = census_summary(recs)
    lines_cs = ["CENSUS summary this seat %s: %s" % ("PASS" if oks else "FAIL", rds)]
    if peer_recs is not None:
        okp, rdp, whyp = census_summary(peer_recs)
        miss += ["peer seat: " + w for w in whyp]
        lines_cs.append("CENSUS summary peer seat %s: %s" % ("PASS" if okp else "FAIL", rdp))
    out.append("SITTING %s" % ("complete: games 0 to %d" % LAST_GAME if not miss else "INCOMPLETE: " + "; ".join(miss)))
    out += lines_cs
    ok2, why2 = vr2(recs, LAST_GAME)
    out.append("VR2 instrument %s %s" % ("PASS" if ok2 else "FAIL", "; ".join(why2)))
    ok5, why5 = vr5(recs, 0, LAST_GAME)
    vr["VR5"] = ok5
    out.append("VR5 %s %s" % ("PASS" if ok5 else "FAIL", "; ".join(why5)))
    try:
        est, hw, df, r1 = dC(recs)
        out.append("dC %.1f cycles/frame, one-sided half-width %.1f at z %.4f, df %d" % (est, hw, Z_END, df))
        vr["VR3"] = r1 <= VR3_MAX
        out.append("VR3 %s lag-1 %.3f (max %.3f)" % ("PASS" if vr["VR3"] else "FAIL", r1, VR3_MAX))
    except (Refused, ZeroDivisionError, ValueError) as e:
        out.append("dC not computable: %s" % e)
    b2 = None
    try:
        b2 = hitch(recs)
        try:
            trb = t_ref(recs)
        except (Refused, KeyError, ZeroDivisionError, ValueError):
            trb = None
        for h, v in b2.items():
            out.append("B2 H=%d ms %s UB %.4f per 1000 frames, %s per minute of live combat at T_ref"
                       % (h, "FAIL" if v["fail"] else "pass", v["ub_per_1000"],
                          "%.4f" % b2_per_minute(v["ub_per_frame"], trb) if trb else "not computable"))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("B2 not computable: %s" % e)
    try:
        ok7, why7 = vr7(recs)
        vr["VR7"] = ok7
        out.append("VR7 %s %s" % ("PASS" if ok7 else "FAIL", "; ".join(why7)))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("VR7 not computable: %s" % e)
    elo = None
    try:
        m, hw, df, elo, ng, miss_g = e_c(recs)
        out.append("e_C %.4f, lower end %.4f at z %.4f, df %d, %d games%s" % (m, elo, Z_END, df, ng,
                   "; no planted OFF point in games %s" % miss_g if miss_g else ""))
        out.append("VR2 e_C_lo %s (>= 0.5)" % ("PASS" if elo >= 0.5 else "FAIL"))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("e_C not computable: %s" % e)
    # ruling FRAME-TIME-ROUND-R6-A3.3 (2a): the measured w and the G VR2 needs, beside VR2, reported either way
    try:
        out += match_power(recs)
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("match power not computable: %s" % e)
    if elo is not None:
        vr["VR2"] = ok2 and elo >= 0.5
    zok, g0v, g0n, meas, empty = zero_state(recs)
    out.append("VR8 zero-state %s: game 0 (mutant) %d of %d rounds void; measured games: %d rounds void%s"
               % ("PASS" if zok else "FAIL", g0v, g0n, len(meas),
                  "; games with no valid round %s" % empty if empty else ""))
    try:
        ke, kh, ku = k_up(recs)
        out.append("K_up %.3f us per live frame (estimate %.3f, half-width %.3f)" % (ku, ke, kh))
        ua = upkeep_per_arm(recs)
        out.append("UPKEEP spans per live frame: ON %.3f us, OFF %.3f us (reported)" % (ua["ON"], ua["OFF"]))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("K_up not computable: %s" % e)
    u = tr = hw4 = u_lo = None
    try:
        du, dsj, rate = d_up(recs)
        out.append("D_up %.3f us per live frame over J=%d calibrations, %d entries" % (du, len(dsj), len(rate)))
        de, dh, _, _ = dC_us(recs)
        _, _, _, elo2, _, _ = e_c(recs)
        _, _, ku = k_up(recs)
        tr = t_ref(recs)
        if peer_err is not None:
            raise peer_err
        for who, rr in (("this seat", recs), ("peer seat", peer_recs)):
            if rr is not None:
                lv, ldet = a3_live(rr, last_game=LAST_GAME)
                out.append("A3 live rows (%s): %s" % (who, "; ".join(
                    "%s d %.4f us over %d games, reads %d, tmax %d ticks" % (k, lv[k], len(ldet[k]),
                                                                           sum(x[1] for x in ldet[k]),
                                                                           max(x[4] for x in ldet[k]))
                    for k in sorted(lv)) or "none"))
        a3v, a3j, a3r, a3d = a3(recs, last_game=LAST_GAME, peer_recs=peer_recs)
        out.append("A3 %.3f us per live frame from both seats' in-game executed lines, %d content-dependent "
                   "structures%s" % (a3v, len(a3r), "".join("; %s r_max %.4f d %.4f us" % (k, a3r[k], a3d[k]) for k in sorted(a3r))))
        lead = max(0.0, de + dh) / min(1.0, max(elo2, 1e-9))
        u = lead + ku + du + a3v
        # the decision's half-width and lower bound for the point design (the integrator's ruling on the hand-back
        # (2), RUL:3452-3454): dC's half-width, and every component at its lower end: dC's, unfloored and unscaled
        # (e_C <= 1); K_up, D_up and A3 are charges with no lower end measured, so 0
        hw4, u_lo = dh, de - dh
        out.append("U %.2f us = max(0, dC_up %.2f) / min(1, e_C_lo %.4f) + K_up %.3f + D_up %.3f + A3 %.3f; T_ref %.1f us"
                   % (u, de + dh, elo2, ku, du, a3v, tr))
        out.append("U without D_up %.2f us (reported)" % (lead + ku + a3v))
        out.append("U without A3 %.2f us (reported)" % (lead + ku + du))
        out.append("U against T_ref: %.3f percent; against 60/144/240 FPS: %.3f / %.3f / %.3f percent; R3 %.0f FPS, "
                   "R5 %.0f FPS" % (100 * u / tr, 100 * u / 16667, 100 * u / 6944, 100 * u / 4167,
                                    30000 / u if u > 0 else float("inf"), 50000 / u if u > 0 else float("inf")))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("U not computable: %s" % e)
    for name, fn in (("dF", lambda: d_key_us(recs, "sF", "ticks")), ("dS", lambda: d_key_us(recs, "sS", "ticks")),
                     ("dP (process CPU, all threads)", lambda: d_key_us(recs, "sP", "cycles"))):
        try:
            e_, h_, df_ = fn()
            out.append("%s %.2f us per live frame, one-sided half-width %.2f, df %d (reported)" % (name, e_, h_, df_))
        except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
            out.append("%s not computable: %s" % (name, e))
    try:
        out.append("dC minus dS %.2f us per live frame (reported)" % dc_minus_ds(recs))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("dC minus dS not computable: %s" % e)
    try:
        lf = longest_frames(recs)
        out.append("longest live frame: ON %.2f ms, OFF %.2f ms (reported)" % (lf["ON"], lf["OFF"]))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("longest frames not computable: %s" % e)
    for name, key in (("e_F", "sF"), ("e_S", "sS")):
        try:
            e_, h_, df_ = e_key(recs, key)
            out.append("%s %.4f, lower end %.4f (reported)" % (name, e_, e_ - h_))
        except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
            out.append("%s not computable: %s" % (name, e))
    try:
        b_, bh, l4 = trend(recs)
        out.append("trend: d_g slope %.3f us per game (95 percent %.3f..%.3f), last four games' mean %.2f us (reported)"
                   % (b_, b_ - bh, b_ + bh, l4))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("trend not computable: %s" % e)
    try:
        out.append("format M's own stamps about %.3f us per ON live frame (inside dC, not subtracted)" % stamps_estimate(recs))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("stamp estimate not computable: %s" % e)
    try:
        bu, bn, bo = between_after(recs)
        out.append("between-point spans after ON points %.1f us per transition over %d (after OFF: %d, not used)"
                   % (bu, bn, bo))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("between-point figure not computable: %s" % e)
    try:
        tr1 = t_ref(recs)
        de, dh, _, _ = dC_us(recs)
        _, _, _, elo3, _, _ = e_c(recs)
        ok1, why1 = vr1(recs, text, tr1)
        vr["VR1"] = ok1
        out.append("VR1 %s %s" % ("PASS" if ok1 else "FAIL", "; ".join(why1)))
        vr["VR4"] = vr4(dh, tr1)
        out.append("VR4 %s half-width %.2f us against 1.5 percent of T_ref = %.2f us"
                   % ("PASS" if vr["VR4"] else "FAIL", dh, 0.015 * tr1))
        nr = len(set((q["game"], q["round"]) for q in recs if q["kind"] == "p" and q["game"] >= 1))
        vfrac = len(meas) / nr if nr else 1.0
        flag, a, b = predecessor(recs)
        vr["VR8"] = vfrac <= 0.10 and not flag and zok
        out.append("VR8 %s: %.1f percent of measured rounds void (max 10); predecessor %s (after ON %d, after OFF %d)"
                   % ("PASS" if vr["VR8"] else "FAIL", 100 * vfrac, "FLAG" if flag else "no flag", len(a), len(b)))
        ok9, lo9 = vr9(recs, max(0.0, de + dh) / min(1.0, max(elo3, 1e-9)))
        vr["VR9"] = ok9
        out.append("VR9 %s: gated span time per ON live frame, lower end %.2f us" % ("PASS" if ok9 else "FAIL", lo9))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("VR1/VR4/VR8/VR9 not computable: %s" % e)
    try:
        ok6, why6, pairs, dis = vr6_build(recs)
        # Codex PARSER-FIX-R1 HIGH 2's sweep: a disarm on either seat makes the sitting INVALID (FtArm's predicate
        # failed after arming, so that seat's lines are not the armed sitting's)
        pdis = disarms(peer_recs) if peer_recs is not None else []
        if pdis:
            ok6, why6 = False, why6 + ["peer seat disarmed: " + "; ".join(pdis)]
        vr["VR6"] = ok6
        out.append("VR6 build half %s%s; %d refused or sent pairs (file listings: the runner's report)"
                   % ("PASS" if ok6 else "FAIL: ", "; ".join(why6), len(pairs)))
    except Refused as e:
        out.append("VR6 build half not computable: %s" % e)
    okb3 = None
    try:
        okb3, whyb3, ops = b3(recs)
        edge = sum(v[1] for v in ops.values())
        off = sum(v[2] for v in ops.values())
        so = max([r["span_off"] for r in recs if r["kind"] == "offthread"] or [0])
        out.append("B3 placement %s%s; edge calls %d (judged), off-thread heavy calls %d, off-thread span calls %d (reported)"
                   % ("holds" if okb3 else "VIOLATED: ", "; ".join(whyb3), edge, off, so))
    except (Refused, KeyError) as e:
        out.append("B3 not computable: %s" % e)
    try:
        ok18, rd, why18, us18 = f18(recs)
        vr["F18"] = ok18
        out.append("F18 reading %s %s%s%s" % (rd, "PASS" if ok18 else "FAIL: ", "; ".join(why18),
                   ("; answer replay %.1f us mean over %d games (reported apart)" % (sum(us18) / len(us18), len(us18))
                    if us18 else "")))
    except Refused as e:
        out.append("F18 not computable: %s" % e)
    # the verdicts (V4 3.7: a failed rule makes the run INVALID for the claim it guards; round-1 MEDIUM,
    # ft_parse:894: VR7 guards B2; VR1 to VR6, VR8 and VR9 guard B1; VR5 and VR6 guard B3 as well)
    # round-3 MEDIUM (ft_parse.py:1461): F18's reading guards B1 (U's answer cost is measured or excluded by it)
    guards = {"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR6", "VR8", "VR9", "F18"), "B2": ("VR7",),
              "B3": ("VR5", "VR6")}

    def gate(claim):
        if miss:
            return "withheld: sitting incomplete"
        gone = [k for k in guards[claim] if k not in vr]
        if gone:
            return "withheld: %s not computable" % ", ".join(gone)
        bad = [k for k in guards[claim] if not vr[k]]
        if bad:
            return "INVALID: %s failed" % ", ".join(bad)
        return None

    g1 = gate("B1")
    if any(b11_line(r) for r in recs):
        # V6 (rulings R6-A3.11.146 (6), .147 (3)(a), .149 (5)): a window log read here is sitting C's, and its contrast
        # is the cross-check with its interval and T_ref as built; the validity set decides whether it is available,
        # the two-arm guards stand beside it, and R-CARRY, R-COMMON, R-PATH and R-PREFIX follow. No B1 verdict is given
        # here: U comes from sitting V only, and the combining step (--combine) gives VERDICT B1 from both sittings
        e11 = None
        try:
            lines11, e11 = b11_report(recs, ref_recs)
            out += lines11
        except (Refused, ZeroDivisionError, ValueError) as e:
            out.append("B11 window estimator not computable: %s" % e)
        sc = sitting_c(recs, text, peer_recs, peer, ref_recs, src)
        out += _validity_lines("VALIDITY", sc["rows"])
        out.append(cross_check_line(e11, sc))
        out += ["TWO-ARM %s %s: %s" % (nm, w, d) for nm, w, d in sc["two"]]
        out += ["  " + x for x in CROSS_RISKS]
    else:
        if ref_recs is not None:
            out.append("R-COMMON reference not read: this log has no B11 window records")
        if g1 is None and (u is None or tr is None):
            g1 = "withheld: U not computable"
        out.append("VERDICT B1 %s" % (g1 if g1 else "%s: U %.2f us against T_ref %.1f us (PASS <= 3, SID <= 5, FAIL > 5 "
                                                   "percent; SID and FAIL need a half-width at most 1.5 percent and "
                                                   "the lower bound past the band, else WITHHELD); %s"
                                                   % (classify(u, tr, hw4, u_lo), u, tr, QUALIFY)))
    g2 = gate("B2")
    if g2 is None and b2 is None:
        g2 = "withheld: B2 not computable"
    out.append("VERDICT B2 %s" % (g2 if g2 else ("FAIL" if any(v["fail"] for v in b2.values()) else "PASS")
                                   + " at the stated resolution"))
    g3 = gate("B3")
    if g3 is None and okb3 is None:
        g3 = "withheld: B3 not computable"
    out.append("VERDICT B3 %s" % (g3 if g3 else ("PASS" if okb3 else "FAIL")
                                   + "; conditional on VR6's file-listing half from frame_time_seat.ps1's report"))
    return "\n".join(out)


def _read_file(path):
    return open(path, encoding="utf-8", errors="replace").read()


_NAMED = re.compile(r"(?:([VCR]):)?([A-Za-z0-9][\w.-]*)=(.+)")


def _named_args(args, kinds):
    """The command line's named logs (ruling R6-A3.11.149 (6) 6: seats by name, never by position): each argument is
    <kind>:<seat>=<path> for kind in kinds (V, C or R), or <seat>=<path> when kinds is (None,). Returns {kind: {seat:
    path}} in the order given; a malformed argument, an unknown kind or a seat named twice for one kind refuses."""
    out = dict((k, {}) for k in kinds)
    for a in args:
        m = _NAMED.fullmatch(a)
        if m is None or m.group(1) not in kinds:
            raise Refused("PAIRING: '%s' is not of the form %s" % (a, " or ".join(
                ("%s:<seat>=<log>" % k) if k else "<seat>=<log>" for k in kinds)))
        if m.group(2) in out[m.group(1)]:
            raise Refused("PAIRING: seat %s is named twice%s" % (m.group(2), " for %s" % m.group(1) if m.group(1)
                                                                  else ""))
        out[m.group(1)][m.group(2)] = m.group(3)
    return out


if __name__ == "__main__":
    try:
        _args = sys.argv[1:]
        # SHARED.md V6 and ruling R6-A3.11.149 (6) 6: --on <seat>=<V log> <seat>=<V log>: report_on; --combine
        # V:<seat>=<log> V:<seat>=<log> C:<seat>=<log> C:<seat>=<log> [R:<seat>=<log> ...]: each seat's logs paired by
        # its name; --controls <profile>=<boot log>: controls_proof (ruling R6-A3.11.151 (2) class C)
        _mode = _args[0] if _args and _args[0] in ("--on", "--combine", "--controls") else None
        if _mode == "--controls":
            _m = re.fullmatch(r"(%s)=(.+)" % "|".join(sorted(map(re.escape, CONTROL_PROFILES), key=len, reverse=True)),
                              _args[1]) if len(_args) == 2 else None
            if _m is None:
                raise Refused("CONTROLS-REFUSED: --controls takes one <profile>=<boot log> (got %s); %s"
                              % (" ".join("'%s'" % a for a in _args[1:]) or "nothing", CONTROLS_USAGE))
            print("\n".join(controls_proof(_read_file(_m.group(2)), _m.group(1), _m.group(2))[1]))
        elif _mode == "--on":
            _n = _named_args(_args[1:], (None,))[None]
            print("\n".join(report_on(dict((s, _read_file(p)) for s, p in _n.items()))[0]))
        elif _mode == "--combine":
            _n = _named_args(_args[1:], ("V", "C", "R"))
            print(combine(*(dict((s, _read_file(p)) for s, p in _n[k].items()) for k in ("V", "C")),
                          refs=dict((s, _read_file(p)) for s, p in _n["R"].items()) or None))
        _ref = _ref_src = None
        if _mode is None and "--ref" in _args:
            _i = _args.index("--ref")
            _ref_src = _args[_i + 1] if _i + 1 < len(_args) else None
            if _ref_src is None:
                raise Refused("--ref needs a reference log")
            _ref = open(_ref_src, encoding="utf-8", errors="replace").read()
            _args = _args[:_i] + _args[_i + 2:]
        if _mode is None and "--peer" in _args:
            # the peer seat's log of the same sitting, named; the second positional form stays
            _i = _args.index("--peer")
            if _i + 1 >= len(_args) or len(_args) > 3:
                raise Refused("--peer needs the peer seat's log (and no second positional log)")
            _args = _args[:_i] + _args[_i + 2:] + [_args[_i + 1]]
        if _mode is None:
            _peer = open(_args[1], encoding="utf-8", errors="replace").read() if len(_args) > 1 else None
            print(report(open(_args[0], encoding="utf-8", errors="replace").read(), peer=_peer, src=_args[0],
                         peer_src=_args[1] if len(_args) > 1 else "peer", ref=_ref, ref_src=_ref_src or "reference"))
    except RecordRefused as e:
        print(e)
        sys.exit(REFUSED_RECORD_EXIT)
    except Refused as e:
        print("REFUSED: %s" % e)
        sys.exit(3)
