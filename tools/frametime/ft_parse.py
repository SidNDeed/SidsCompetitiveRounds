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

Usage: python -I -B ft_parse.py <LogOutput.log> [<second seat's log>]
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
MENU_EC_BAND = (0.5, 1.5)             # the menu check's declared two-sided band for e_C's interval (decision 21')
MENU_EC_NEAR = 0.10                   # and |e_C - 1| at most this (a spin's response is about 1 by construction)

_LINE = re.compile(r"\[FRAME-TIME\] (\w+) (.*)$")
_KV = re.compile(r"(\w+)=(\S+)")


class Refused(Exception):
    pass


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


INT_KEYS = {"seg", "pair", "base_us", "segs", "of", "cycles", "n", "sF", "sS", "sC", "maxF", "medF", "gc", "gate", "windows", "live_frames", "missing_end", "partial",
            "g", "seed", "c_plant", "W", "vsync", "target", "freq", "hires", "f_hat", "frames", "cycle_failures",
            "span_depth_violations", "on", "guarded", "outside", "i", "plant", "pn", "psF", "psS", "psC",
            "plant_mixed", "ticks", "span_g", "span_gn", "span_u", "span_un", "on_calls", "zs", "zl",
            "t0", "t1", "live", "between", "pick", "over", "menu", "at_call", "edge", "off", "span_off",
            "hash_t0", "hash_t1", "sP", "psP", "excl", "se", "ce", "ic", "calls", "dispatched",
            "cap", "steady", "reads_on", "reads_win", "writes_on"}


def parse_line(line):
    m = _LINE.search(line)
    if not m:
        return None
    kind, rest = m.group(1), m.group(2)
    rec = {"kind": kind}
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
    for k, v in _KV.findall(rest):
        if k == "kind":
            k = "ckind"      # a cal line's kind=fhat|disp|span must not overwrite the line kind
        if k in INT_KEYS:
            rec[k] = _int(k, v)
        elif re.fullmatch(r"e\d+", k):
            a, b = v.split(",")
            rec[k] = (_int(k, a), _int(k, b))
        else:
            rec[k] = v
    if "pt" in rec:
        g, r, p = rec["pt"].split(".")
        rec["game"], rec["round"], rec["point"] = int(g), int(r), int(p)
    return rec


def read(text):
    recs = []
    for ln in text.splitlines():
        r = parse_line(ln)
        if r is not None:
            recs.append(r)
    return recs


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


OPENED = ("se", "ce", "ic")     # V4 3.7 VR5: SeatEvidence, CombatEvidence and IdentityClockEvidence's BeginGame


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
    cal = set(int(r["why"][4:]) for r in recs if r["kind"] == "cal" and re.fullmatch(r"game\d+", str(r.get("why", ""))))
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
    return miss


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
        if r["kind"] == "cal" and r.get("why", "").startswith("game") and r.get("ckind") == "disp":
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


def a3_spec():
    """The A3 inventory (gate_specs/a3.py, from SURVIVORS.md): [(name, survivor id, "dependent" | "zero", reason)].
    A "zero" row is a structure whose live reads cost the same whatever its content (its reason says why)."""
    here = os.path.dirname(os.path.abspath(__file__))
    return runpy.run_path(os.path.join(here, "gate_specs", "a3.py"))["A3"]


def a3(recs, z=Z_END, first_game=1, last_game=None, spec=None):
    """A3 (ruling FRAME-TIME-ROUND-R1-A1, route D; METHOD-V4.1 section 0), the fifth term of U: a deterministic
    bound on the class (iii) carryover the whole-entry gate leaves. Per content-dependent survivor k, the build
    counts, in every ON point's live frames, the live reads of k whose work can differ from an always-ON game's:
    those made before k reaches its steady state (writes since the point's first live frame below k's capacity,
    the code constant), or every read when k has no steady state (it accumulates over the game). r_k_max is the
    largest per-game count of such reads over the game's ON live frames (frame-weighted, as D_up's n_k_max).
    Per calibration j at a game start, d_kj is |mean over batches of (full - empty) / n|: the per-read cost
    difference between k at its capacity and k empty, us; A_j = sum_k r_k_max x d_kj; A3 = max(mean + t(z, J - 1)
    SE, largest A_j). Zero rows add nothing and are listed. Refuses when the spec names no structure, or when
    a dependent structure lacks its a3 line in a measured game (or carries two) or its calibration line in a
    game-start calibration. Returns (A3, [A_j], {k: r_k_max}, {k: mean d_k us})."""
    spec = a3_spec() if spec is None else spec
    if not spec:
        raise Refused("the A3 inventory names no structure")
    dep = [n for n, sid, kind, why in spec if kind == "dependent"]
    for n, sid, kind, why in spec:
        if kind not in ("dependent", "zero") or (kind == "zero" and not why.strip()):
            raise Refused("A3 row %s (%s): kind %r needs a reason when zero" % (n, sid, kind))
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("A3 needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
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
    cals = {}
    for r in recs:
        if r["kind"] == "cal" and r.get("why", "").startswith("game") and r.get("ckind") == "a3":
            u = [int(x) for x in r["u"].split(",")]
            pp = [int(x) for x in r["p"].split(",")]
            if len(u) != len(pp) or not u:
                raise Refused("cal i=%d a3 k=%s: batch lists differ" % (r["i"], r["k"]))
            cals.setdefault(r["i"], {})[r["k"]] = abs(sum(b - a for a, b in zip(u, pp)) / len(u)) / r["n"] * 1e6 / f
    if dep and len(cals) < 2:
        raise Refused("A3 needs at least two game-start calibrations (got %d)" % len(cals))
    ds, dk = [], {}
    for i in sorted(cals):
        miss = sorted(k for k in dep if k not in cals[i])
        if miss:
            raise Refused("calibration %d has no a3 line for %s" % (i, miss))
        ds.append(sum(rate[k] * cals[i][k] for k in dep))
        for k in dep:
            dk.setdefault(k, []).append(cals[i][k])
    if not dep:
        return 0.0, [], {}, {}
    j = len(ds)
    m = sum(ds) / j
    se = statistics.stdev(ds) / math.sqrt(j) if j > 1 else 0.0
    return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate, {k: sum(v) / len(v) for k, v in dk.items()}


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


def vr1(recs, text, tref):
    """VR1, no cap: no [FPSCAP] line; every settled line vsync 0 and target -1 or above 1000; T_ref not within 2
    percent of 1e6 / k for k in 60, 75, 120, 144, 165, 240."""
    bad = []
    if "[FPSCAP]" in text:
        bad.append("an [FPSCAP] line is present")
    for r in recs:
        if r["kind"] == "settled" and r["g"] >= 0:
            if r.get("vsync", 0) != 0:
                bad.append("settled g=%d vsync=%d" % (r["g"], r["vsync"]))
            tg = r.get("target", -1)
            if not (tg == -1 or tg > 1000):
                bad.append("settled g=%d target=%d" % (r["g"], tg))
    for k in (60, 75, 120, 144, 165, 240):
        if abs(tref - 1e6 / k) <= 0.02 * (1e6 / k):
            bad.append("T_ref %.1f us within 2 percent of 1e6/%d" % (tref, k))
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


def vr6_build(recs):
    """VR6's build half (FORMAT-M-PLAN.md V2 part b): the latest refusals line (why=quit when present, else the
    last game over) gives every refused what:route pair's count and every allowed route's send count; a route that
    was both refused and sent fails, and any disarmed line makes the sitting INVALID. The file listings before and
    after are the runner's half. Returns (ok, reasons, {pair: count}, [disarm inputs])."""
    lines = [r for r in recs if r["kind"] == "refusals"]
    dis = ["%s at %s" % (r.get("input", "?"), r.get("pt", "?")) for r in recs if r["kind"] == "disarmed"]
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


def vr5_points(recs):
    """VR5's rules: every entry that ran in ON live frames shows guarded returns in OFF live frames, per game; and
    per point, a gated point has no gated span time, no gated span call and no census call with the gate clear,
    an ungated point no guarded return."""
    bad = []
    for r in recs:
        if r["kind"] == "census" and r["on"] > 0 and r["guarded"] == 0:
            bad.append("g=%d %s" % (r["g"], r["entry"]))
        if r["kind"] == "p" and "span_g" in r:
            if r["gate"] == 1 and (r["span_g"] or r["span_gn"] or r["on_calls"]):
                bad.append("pt=%s gated: span_g=%d span_gn=%d on_calls=%d" % (r["pt"], r["span_g"], r["span_gn"],
                                                                          r["on_calls"]))
            if r["gate"] == 0 and r["guarded"]:
                bad.append("pt=%s open: guarded=%d" % (r["pt"], r["guarded"]))
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
        runs = sorted(set(r["i"] for r in recs if r["kind"] == "cal" and r.get("why") == "game%d" % g))
        if len(runs) != 1:
            bad.append("game %d: %d calibration runs (needs 1)" % (g, len(runs)))
            continue
        cl = [r for r in recs if r["kind"] == "cal" and r.get("i") == runs[0]]
        if not any(r.get("ckind") == "fhat" for r in cl):
            bad.append("game %d: calibration %d has no fhat line" % (g, runs[0]))
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
    fh = [r["f_hat"] for r in sett if r["g"] >= 0 and r.get("f_hat", 0) > 0]
    if fh and (max(fh) - min(fh)) > 0.02 * min(fh):
        bad.append("f_hat spread %d..%d exceeds 2 percent" % (min(fh), max(fh)))
    return not bad, bad


MENU_LEVELS = ("0.5", "1.5", "3", "5")


def menu_check(recs, z=Z_END):
    """The menu self-check (METHOD-V4.md section 6 step 2; plugin/FtMenu.cs). Segments are FtMenu's menu lines with
    their point lines (pt=-1.<seg>.1), in log order. Judged: (1) the run completed (one menu_done line,
    why=complete, segs equal to of); (2) every segment has its point line, the gate the sentinel's force implies
    (none: OFF segments gated) on both lines, and missing_end 0; (3) the A/A: per pair with both arms, the
    unplanted mean F of ON minus OFF in us (by the settled lines' Stopwatch freq), batch_interval at z, and the
    two-sided interval must contain 0; (4) e_C at each of the four levels: per OFF segment with planted and
    unplanted frames, (psC/pn - sC/n) / (c_plant x f_hat / 10^6) with the menu calibration in force at that
    segment, batch_interval over the level's segments (at least four), its two-sided interval inside MENU_EC_BAND
    and its estimate within MENU_EC_NEAR of 1 (decision 21', replacing the lower-end-only bar); e_F and e_S
    (by freq) reported; (5) f_hat over the menu calibrations within 2 percent; (6) the last settled line shows no
    frame without FT_End, no cycle failure and no span depth violation. Returns (ok, report lines, failures)."""
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
        if r["kind"] == "cal" and r.get("ckind") == "fhat" and str(r.get("why", "")).startswith("menu"):
            fh = r["f_hat"]
            fhs.append(fh)
        elif r["kind"] == "menu":
            seg[r["seg"]] = dict(r, f_hat=fh)
        elif r["kind"] == "p" and r["game"] == -1 and r["round"] in seg:
            seg[r["round"]]["p"] = r
    if not fhs:
        raise Refused("no menu calibration line")
    pairs, lv = {}, {}
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
        if p["n"] > 0:
            pairs.setdefault(m["pair"], {})[m["arm"]] = p
        if m["arm"] == "OFF" and m.get("c_plant", 0) > 0 and p.get("pn", 0) > 0 and p["n"] > 0:
            cp = m["c_plant"]
            ec = (p["psC"] / p["pn"] - p["sC"] / p["n"]) / (cp * m["f_hat"] / 1e6)
            ef = (p["psF"] / p["pn"] - p["sF"] / p["n"]) * 1e6 / f / cp
            es = (p["psS"] / p["pn"] - p["sS"] / p["n"]) * 1e6 / f / cp
            lv.setdefault(m["level"], []).append((ec, ef, es))
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
        # decision 21' (round-1 MEDIUM, ft_parse:771): "about 1" is a declared two-sided band: the two-sided
        # interval at z lies inside MENU_EC_BAND and the estimate within MENU_EC_NEAR of 1
        lo_b, hi_b = MENU_EC_BAND
        if not (lo_b <= m_ - h_ and m_ + h_ <= hi_b):
            bad.append("level %s percent: e_C interval %.4f..%.4f outside %.1f..%.1f" % (L, m_ - h_, m_ + h_, lo_b, hi_b))
        if abs(m_ - 1.0) > MENU_EC_NEAR:
            bad.append("level %s percent: e_C %.4f not within %.2f of 1" % (L, m_, MENU_EC_NEAR))
    lines.append("menu f_hat %d..%d over %d calibrations" % (min(fhs), max(fhs), len(fhs)))
    if max(fhs) - min(fhs) > 0.02 * min(fhs):
        bad.append("f_hat spread %d..%d exceeds 2 percent" % (min(fhs), max(fhs)))
    for k in ("missing_end", "cycle_failures", "span_depth_violations"):
        if sett[-1].get(k, 0) != 0:
            bad.append("last settled line %s=%d" % (k, sett[-1][k]))
    return not bad, lines, bad


def menu_report(recs):
    out = ["MENU self-check (one launch, no room)"]
    try:
        ok, lines, bad = menu_check(recs)
        out += lines
        out.append("MENU %s%s" % ("PASS" if ok else "FAIL: ", "; ".join(bad)))
    except Refused as e:
        out.append("MENU not computable: %s" % e)
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
        if r["kind"] == "cal" and r.get("ckind") == "span" and str(r.get("why", "")).startswith("game"):
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


def classify(u, tref):
    """V4 section 0's table against T = T_ref."""
    if u <= 0.03 * tref:
        return "PASS"
    if u <= 0.05 * tref:
        return "SID"
    return "FAIL"


QUALIFY = ("conditional: U bounds the NET main-thread CPU the seven components add per live-combat frame on this "
           "seat at the recorded load (their work minus the CPU it displaces); the gross cost only under the "
           "absorption premise, which VR9 tests inside the spans only; confidence at least 95 percent for "
           "persistence up to rho = 0.9 per point; dispatch in play assumed no dearer per call than in its "
           "calibration (R1); the upkeep's own GC and cache effects outside its spans are not in K_up (R10); "
           "VR6's file-listing half is frame_time_seat.ps1's report")


def report(text):
    recs = read(text)
    if any(r["kind"] in ("menu", "menu_done") for r in recs):
        return menu_report(recs)
    out = []
    vr = {}
    miss = complete(recs)
    out.append("SITTING %s" % ("complete: games 0 to %d" % LAST_GAME if not miss else "INCOMPLETE: " + "; ".join(miss)))
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
        for h, v in b2.items():
            out.append("B2 H=%d ms %s UB %.4f per 1000 frames" % (h, "FAIL" if v["fail"] else "pass", v["ub_per_1000"]))
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
    u = tr = None
    try:
        du, dsj, rate = d_up(recs)
        out.append("D_up %.3f us per live frame over J=%d calibrations, %d entries" % (du, len(dsj), len(rate)))
        de, dh, _, _ = dC_us(recs)
        _, _, _, elo2, _, _ = e_c(recs)
        _, _, ku = k_up(recs)
        tr = t_ref(recs)
        a3v, a3j, a3r, a3d = a3(recs, last_game=LAST_GAME)
        out.append("A3 %.3f us per live frame over J=%d calibrations, %d content-dependent structures%s"
                   % (a3v, len(a3j), len(a3r), "".join("; %s r_max %.4f d %.4f us" % (k, a3r[k], a3d[k]) for k in sorted(a3r))))
        lead = max(0.0, de + dh) / min(1.0, max(elo2, 1e-9))
        u = lead + ku + du + a3v
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
        out.append("F18 reading %s %s%s%s" % (rd, "PASS" if ok18 else "FAIL: ", "; ".join(why18),
                   ("; answer replay %.1f us mean over %d games (reported apart)" % (sum(us18) / len(us18), len(us18))
                    if us18 else "")))
    except Refused as e:
        out.append("F18 not computable: %s" % e)
    # the verdicts (V4 3.7: a failed rule makes the run INVALID for the claim it guards; round-1 MEDIUM,
    # ft_parse:894: VR7 guards B2; VR1 to VR6, VR8 and VR9 guard B1; VR5 and VR6 guard B3 as well)
    guards = {"B1": ("VR1", "VR2", "VR3", "VR4", "VR5", "VR6", "VR8", "VR9"), "B2": ("VR7",), "B3": ("VR5", "VR6")}

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
    if g1 is None and (u is None or tr is None):
        g1 = "withheld: U not computable"
    out.append("VERDICT B1 %s" % (g1 if g1 else "%s: U %.2f us against T_ref %.1f us (PASS <= 3, SID <= 5, FAIL > 5 "
                                               "percent); %s" % (classify(u, tr), u, tr, QUALIFY)))
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


if __name__ == "__main__":
    try:
        print(report(open(sys.argv[1], encoding="utf-8", errors="replace").read()))
    except Refused as e:
        print("REFUSED: %s" % e)
        sys.exit(3)
