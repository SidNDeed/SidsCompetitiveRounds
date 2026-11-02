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
                     (n and the s sums are the unplanted frames, pn and the ps sums the planted ones)
  plant    once:     c_plant (us) ticks from=g.r.p|sentinel
  settled  per game: g seed c_plant W vsync target freq hires f_hat gc_incremental gc_slice_ns f18 ... missing_end
  cal      per run:  i why kind=fhat|disp|span ...
  census   per entry per game: g entry comp shape on guarded outside

The plant gives e_C_lo (V4 3.5) and VR7. Part 3's remainder adds D_up (V4 3.6) and K_up (UPKEEP spans); until
those lines exist, report() states U as not computable rather than computing it without them.

Usage: python -I -B ft_parse.py <LogOutput.log> [<second seat's log>]
"""
import math
import re
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


INT_KEYS = {"n", "sF", "sS", "sC", "maxF", "medF", "gc", "gate", "windows", "live_frames", "missing_end", "partial",
            "g", "seed", "c_plant", "W", "vsync", "target", "freq", "hires", "f_hat", "frames", "cycle_failures",
            "span_depth_violations", "on", "guarded", "outside", "i", "plant", "pn", "psF", "psS", "psC",
            "plant_mixed", "ticks", "span_g", "span_gn", "span_u", "span_un", "on_calls", "zs", "zl"}


def parse_line(line):
    m = _LINE.search(line)
    if not m:
        return None
    kind, rest = m.group(1), m.group(2)
    rec = {"kind": kind}
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
    """D_up (V4 3.6, F14): per calibration j at a game start, D_j = sum over shapes of the shape's guarded calls
    per OFF live frame (census, measured games) x the shape's per-call closed-path cost in calibration j (mean
    over its batches of (patched - unpatched) / n, us by the settled Stopwatch frequency); D_up = max(mean +
    t(z, J - 1) SE, largest D_j). Returns (D_up, [D_j], {shape: rate})."""
    freq = set(r["freq"] for r in recs if r["kind"] == "settled")
    if len(freq) != 1:
        raise Refused("D_up needs one Stopwatch frequency (got %s)" % sorted(freq))
    f = freq.pop()
    off_frames = sum(q["live_frames"] for pts in games_of(recs, first_game).values() for q in pts if q["gate"] == 1)
    if off_frames <= 0:
        raise Refused("no gated live frames")
    calls = {}
    for r in recs:
        if r["kind"] == "census" and r["g"] >= first_game:
            calls[r["shape"]] = calls.get(r["shape"], 0) + r["guarded"]
    rate = {s: c / off_frames for s, c in calls.items() if c > 0}
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
        miss = [s for s in rate if s not in cals[i]]
        if miss:
            raise Refused("calibration %d has no line for shapes %s" % (i, miss))
        ds.append(sum(rate[s] * cals[i][s] for s in rate))
    j = len(ds)
    m = sum(ds) / j
    se = math.sqrt(sum((v - m) ** 2 for v in ds) / (j - 1) / j)
    return max(m + t_q(z, j - 1) * se, max(ds)), ds, rate


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


def vr5(recs):
    """Census: every entry that ran in ON live frames shows guarded returns in OFF live frames, per game; and per
    point, a gated point has no gated span time, no gated span call and no census call with the gate clear, an
    ungated point no guarded return."""
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


def vr2(recs):
    """Instrument: every measured game has a settled line; no frame without FT_End, no cycle-read failure and no
    span open at a frame boundary in any settled line."""
    sett = [r for r in recs if r["kind"] == "settled"]
    games = sorted(set(r["game"] for r in recs if r["kind"] == "p"))
    have = set(r["g"] for r in sett)
    bad = ["no settled line for game %d" % g for g in games if g not in have]
    for r in sett:
        for k in ("missing_end", "cycle_failures", "span_depth_violations"):
            if r.get(k, 0) != 0:
                bad.append("settled g=%d %s=%d" % (r["g"], k, r[k]))
    fh = [r["f_hat"] for r in sett if r["g"] >= 0 and r.get("f_hat", 0) > 0]
    if fh and (max(fh) - min(fh)) > 0.02 * min(fh):
        bad.append("f_hat spread %d..%d exceeds 2 percent" % (min(fh), max(fh)))
    return not bad, bad


def report(text):
    recs = read(text)
    out = []
    ok2, why2 = vr2(recs)
    out.append("VR2 %s %s" % ("PASS" if ok2 else "FAIL", "; ".join(why2)))
    ok5, why5 = vr5(recs)
    out.append("VR5 %s %s" % ("PASS" if ok5 else "FAIL", "; ".join(why5)))
    try:
        est, hw, df, r1 = dC(recs)
        out.append("dC %.1f cycles/frame, one-sided half-width %.1f at z %.4f, df %d" % (est, hw, Z_END, df))
        out.append("VR3 %s lag-1 %.3f (max %.3f)" % ("PASS" if r1 <= VR3_MAX else "FAIL", r1, VR3_MAX))
    except (Refused, ZeroDivisionError, ValueError) as e:
        out.append("dC not computable: %s" % e)
    try:
        for h, v in hitch(recs).items():
            out.append("B2 H=%d ms %s UB %.4f per 1000 frames" % (h, "FAIL" if v["fail"] else "pass", v["ub_per_1000"]))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("B2 not computable: %s" % e)
    try:
        ok7, why7 = vr7(recs)
        out.append("VR7 %s %s" % ("PASS" if ok7 else "FAIL", "; ".join(why7)))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("VR7 not computable: %s" % e)
    try:
        m, hw, df, lo, ng, miss = e_c(recs)
        out.append("e_C %.4f, lower end %.4f at z %.4f, df %d, %d games%s" % (m, lo, Z_END, df, ng,
                   "; no planted OFF point in games %s" % miss if miss else ""))
        out.append("VR2 e_C_lo %s (>= 0.5)" % ("PASS" if lo >= 0.5 else "FAIL"))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("e_C not computable: %s" % e)
    zok, g0v, g0n, meas, empty = zero_state(recs)
    out.append("VR8 zero-state %s: game 0 (mutant) %d of %d rounds void; measured games: %d rounds void%s"
               % ("PASS" if zok else "FAIL", g0v, g0n, len(meas),
                  "; games with no valid round %s" % empty if empty else ""))
    try:
        ke, kh, ku = k_up(recs)
        out.append("K_up %.3f us per live frame (estimate %.3f, half-width %.3f)" % (ku, ke, kh))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("K_up not computable: %s" % e)
    try:
        du, dsj, rate = d_up(recs)
        out.append("D_up %.3f us per OFF live frame over J=%d calibrations" % (du, len(dsj)))
        de, dh, _, _ = dC_us(recs)
        _, _, _, elo, _, _ = e_c(recs)
        _, _, ku = k_up(recs)
        u = max(0.0, de + dh) / min(1.0, max(elo, 1e-9)) + ku + du
        tr = t_ref(recs)
        out.append("U %.2f us = max(0, dC_up %.2f) / min(1, e_C_lo %.4f) + K_up %.3f + D_up %.3f; T_ref %.1f us; bar"
                   " 3 percent = %.1f us -> %s" % (u, de + dh, elo, ku, du, tr, 0.03 * tr,
                                                  "below" if u < 0.03 * tr else "not below"))
        out.append("U against 60/144/240 FPS: %.3f / %.3f / %.3f percent; R3 %.0f FPS, R5 %.0f FPS"
                   % (100 * u / 16667, 100 * u / 6944, 100 * u / 4167, 30000 / u if u > 0 else float("inf"),
                      50000 / u if u > 0 else float("inf")))
    except (Refused, KeyError, ZeroDivisionError, ValueError) as e:
        out.append("U not computable: %s" % e)
    out.append("VERDICT withheld: VR1, VR4, VR6, VR9 and VR8's predecessor check are not yet computed by this parser")
    return "\n".join(out)


if __name__ == "__main__":
    try:
        print(report(open(sys.argv[1], encoding="utf-8", errors="replace").read()))
    except Refused as e:
        print("REFUSED: %s" % e)
        sys.exit(3)
