"""Tests for ft_parse.py. Golden values were computed with dither_control v5 (md5 894b010c), whose claims C10 to
C21 they stand behind; each port test pins the parser to the control's own function on the same input.
Run: python -I -B -m pytest tools/frametime/test_ft_parse.py -q"""
import os
import sys

import re

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ft_parse as P  # noqa: E402

DW = [(float(10 + 3 * i - (i % 3) * 7), float(20000 + 500 * (i % 5))) for i in range(16)]
KS = [0, 1, 0, 2, 0, 0, 3, 0, 1, 0, 0, 0, 5, 0, 1, 0]
NS = [25000] * 16


# ------------------------------------------------------------------ ports of the control (frame_weight, dispersion, poisson)

def test_frame_weight_port_matches_control():
    est, hw, df = P.fw_interval(DW)
    assert est == pytest.approx(25.98507462686567, abs=1e-9)
    assert hw == pytest.approx(14.622555606607124, abs=1e-9)
    assert df == 7


def test_dispersion_port_matches_control():
    assert P.phi_v4(KS, NS) == pytest.approx(4.38312938875477, abs=1e-9)
    assert P.phi_v4([0] * 16, NS) == pytest.approx(1.7550518086389735, abs=1e-9)


def test_poisson_port_matches_control():
    assert P.rate_ub(KS, NS) == pytest.approx(0.00011218523776561974, rel=1e-9)
    assert P.rate_lb(KS, NS) == pytest.approx(4.342833270026816e-06, rel=1e-9)
    assert P.rate_ub([0] * 16, NS) == pytest.approx(2.1005740105034458e-05, rel=1e-9)
    assert P.pois_ub(0.0, P.A_HITCH) == pytest.approx(4.787491742782047, abs=1e-9)
    assert P.Z_END == pytest.approx(2.2414027276049464, abs=1e-12)


def test_poisson_zero_events_never_zero():
    # V4 3.8: zero events give phi x lambda_U(0) = 1.755 x 4.79 = 8.40 events, never 0 (HIGH 4)
    assert P.phi_v4([0] * 16, NS) * P.pois_ub(0.0, P.A_HITCH) == pytest.approx(8.402, abs=0.001)


def test_mutant_dispersion_dropped_undercovers():
    # mutant control: without the dispersion factor the clustered counts' upper limit is smaller
    plain = P.pois_ub(float(sum(KS)), P.A_HITCH) / sum(NS)
    assert plain < P.rate_ub(KS, NS)


# ------------------------------------------------------------------ lines

def test_integer_lines_refuse_decimals():
    with pytest.raises(P.Refused):
        P.parse_line("[Info   :CompetitiveRounds] [FRAME-TIME] w pt=1.1.1 arm=ON partial=0 n=120 sF=1.5 sS=1 sC=1 maxF=1 gc=0")


def test_window_line_parses_run_bounds():
    r = P.parse_line("[FRAME-TIME] w pt=3.2.4 arm=OFF partial=0 n=120 sF=3180000 sS=900000 sC=7900000 maxF=40100"
                     " medF=26500 e4=0,1 e8=0,0 e16=0,0 gc=0")
    assert (r["game"], r["round"], r["point"]) == (3, 2, 4)
    assert r["e4"] == (0, 1) and r["medF"] == 26500 and r["arm"] == "OFF"


# ------------------------------------------------------------------ frame weighting (F15)

def _p(g, arm, n, sc, pt=1):
    return {"kind": "p", "game": g, "round": 1, "point": pt, "arm": arm, "n": n, "sC": sc}


def test_frame_weight_contrast_is_ratio_of_sums():
    pts = [_p(1, "ON", 100, 30000), _p(1, "ON", 10, 0, 2), _p(1, "OFF", 100, 10000, 3), _p(1, "OFF", 10, 1000, 4)]
    d, n = P.contrast_c(pts)
    assert d == pytest.approx(30000 / 110 - 100.0, abs=1e-9)   # 172.73, not the point-weighted 50
    assert n == 220


def test_mutant_point_weighted_differs():
    pts = [_p(1, "ON", 100, 30000), _p(1, "ON", 10, 0, 2), _p(1, "OFF", 100, 10000, 3), _p(1, "OFF", 10, 1000, 4)]
    point_weighted = (300 + 0) / 2 - (100 + 100) / 2
    assert abs(P.contrast_c(pts)[0] - point_weighted) > 100


# ------------------------------------------------------------------ the hitch test end to end (runs, VR7-like)

def _windows(events_on, events_off, games=16, per_arm=210):
    recs = []
    for g in range(1, games + 1):
        for arm, ev in (("ON", events_on), ("OFF", events_off)):
            for w in range(per_arm):
                k = ev(g, w)
                recs.append({"kind": "w", "game": g, "arm": arm, "partial": 0, "n": 120,
                             "e4": (k, k), "e8": (0, 0), "e16": (0, 0)})
    return recs


def test_runs_no_events_no_fail():
    out = P.hitch(_windows(lambda g, w: 0, lambda g, w: 0))
    assert not any(v["fail"] for v in out.values())
    assert out[4]["ub_per_1000"] > 0      # never zero


def test_runs_stalls_fail():
    out = P.hitch(_windows(lambda g, w: 1 if w % 10 == 0 else 0, lambda g, w: 0))
    assert out[4]["fail"] and not out[8]["fail"]


def test_mutant_runs_kmax_for_fail_does_not_fail_on_uncertain_only():
    # FAIL must use K_ON_min: windows whose only events are uncertain (kmin 0, kmax 1) never FAIL
    recs = _windows(lambda g, w: 0, lambda g, w: 0)
    for r in recs:
        if r["arm"] == "ON":
            r["e4"] = (0, 1)
    assert not P.hitch(recs)[4]["fail"]


# ------------------------------------------------------------------ VR2, VR3, VR5

def test_vr5_flags_an_ungated_entry():
    recs = [{"kind": "census", "g": 1, "entry": "SeatEvidence.Tick", "on": 50, "guarded": 0},
            {"kind": "census", "g": 1, "entry": "CombatEvidence.Tick", "on": 50, "guarded": 40}]
    ok, bad = P.vr5_points(recs)
    assert not ok and bad == ["g=1 SeatEvidence.Tick"]


def test_vr2_flags_missing_end_and_missing_settled():
    recs = [{"kind": "p", "game": 1}, {"kind": "p", "game": 2},
            {"kind": "settled", "g": 1, "missing_end": 3, "cycle_failures": 0}]
    ok, bad = P.vr2(recs)
    assert not ok and "no settled line for game 2" in bad and "settled g=1 missing_end=3" in bad


def test_vr3_lag1():
    assert P.lag1([1, -1] * 8) < -0.9
    assert P.lag1(list(range(16))) > 0.8


# ------------------------------------------------------------------ the plant (M5): e_C, VR7, planted windows kept out

def test_batch_interval_port_matches_control():
    es = [0.95 + 0.01 * ((i * 7) % 5) - 0.004 * (i % 3) for i in range(16)]
    est, hw, df = P.batch_interval(es)
    assert est == pytest.approx(0.965, abs=1e-12)
    assert hw == pytest.approx(0.009371237028935563, abs=1e-12)
    assert df == 15


def _plant_log(ks, c_plant=80, fhat=3000000000):
    recs = [{"kind": "plant", "c_plant": c_plant}]
    for g, k in enumerate(ks, 1):
        recs.append({"kind": "settled", "g": g, "f_hat": fhat})
        unit = c_plant * fhat // 1000000
        for pt in (1, 2):
            recs.append({"kind": "p", "game": g, "round": 1, "point": pt, "arm": "OFF", "n": 900,
                         "sC": 900 * 7000000, "pn": 300, "psC": 300 * (7000000 + int(k * unit))})
        recs.append({"kind": "p", "game": g, "round": 1, "point": 3, "arm": "ON", "n": 900, "sC": 1, "pn": 0, "psC": 0})
    return recs


def test_e_c_reads_the_plant():
    ks = [0.98 + 0.002 * (i % 4) for i in range(16)]
    m, hw, df, lo, ng, miss = P.e_c(_plant_log(ks))
    assert m == pytest.approx(sum(ks) / 16, abs=1e-6)
    assert lo == pytest.approx(m - hw) and hw > 0 and ng == 16 and miss == []


def test_e_c_refuses_without_a_plant_line():
    recs = [r for r in _plant_log([1.0] * 16) if r["kind"] != "plant"]
    with pytest.raises(P.Refused):
        P.e_c(recs)


def _with_planted(recs, events, games=16, per=70):
    for g in range(1, games + 1):
        for w in range(per):
            k = events(g, w)
            recs.append({"kind": "w", "game": g, "arm": "OFF", "plant": 1, "partial": 0, "n": 120,
                         "e4": (k, k), "e8": (0, 0), "e16": (0, 0)})
    return recs


def test_hitch_leaves_planted_windows_out():
    base = P.hitch(_windows(lambda g, w: 0, lambda g, w: 0))
    mixed = P.hitch(_with_planted(_windows(lambda g, w: 0, lambda g, w: 0), lambda g, w: 1))
    assert mixed[4]["ub_per_frame"] == base[4]["ub_per_frame"]


def test_mutant_hitch_counting_planted_windows_differs():
    recs = _with_planted(_windows(lambda g, w: 0, lambda g, w: 0), lambda g, w: 1)
    with_planted = P.hitch(recs, side=lambda r: r["arm"])
    assert with_planted[4]["ub_per_frame"] != P.hitch(recs)[4]["ub_per_frame"]


def test_vr7_constant_plant_passes():
    ok, bad = P.vr7(_with_planted(_windows(lambda g, w: 0, lambda g, w: 0), lambda g, w: 0))
    assert ok and bad == []


def test_vr7_stalls_in_planted_windows_fail():
    ok, bad = P.vr7(_with_planted(_windows(lambda g, w: 0, lambda g, w: 0), lambda g, w: 1 if w % 5 == 0 else 0))
    assert not ok and "H=4 ms FAIL" in bad


# ------------------------------------------------------------------ census and span totals: VR5 per point, K_up

def _pt(gate, **kw):
    r = {"kind": "p", "pt": "1.1.1", "game": 1, "gate": gate, "span_g": 0, "span_gn": 0, "on_calls": 0, "guarded": 0}
    r.update(kw)
    return r


def test_vr5_point_zero_holds():
    ok, bad = P.vr5_points([_pt(1, guarded=40), _pt(0, span_g=900, span_gn=40, on_calls=40)])
    assert ok and bad == []


def test_vr5_flags_gated_span_time_at_a_gated_point():
    ok, bad = P.vr5_points([_pt(1, guarded=40, span_g=3)])
    assert not ok and bad == ["pt=1.1.1 gated: span_g=3 span_gn=0 on_calls=0"]


def test_vr5_flags_guarded_returns_at_an_open_point():
    ok, bad = P.vr5_points([_pt(0, guarded=1)])
    assert not ok and bad == ["pt=1.1.1 open: guarded=1"]


def _kup_log(per_frame_ticks, freq=10000000):
    recs = [{"kind": "settled", "g": 0, "freq": freq}]
    for g, u in enumerate(per_frame_ticks, 1):
        recs.append({"kind": "settled", "g": g, "freq": freq})
        for arm in ("ON", "OFF"):
            recs.append({"kind": "p", "game": g, "round": 1, "arm": arm, "n": 1000, "pn": 0, "live_frames": 1001,
                         "span_u": int(u * 1001)})
    return recs


def test_k_up_reads_upkeep_per_live_frame():
    ticks = [600 + 10 * (i % 3) for i in range(16)]      # 60 to 62 us at 10 MHz
    est, hw, ku = P.k_up(_kup_log(ticks))
    assert est == pytest.approx(sum(ticks) / 16 / 10.0, abs=1e-9)
    assert ku == pytest.approx(est + hw) and hw > 0


def test_k_up_refuses_two_frequencies():
    recs = _kup_log([600] * 16)
    recs.append({"kind": "settled", "g": 17, "freq": 3000000})
    with pytest.raises(P.Refused):
        P.k_up(recs)


# ------------------------------------------------------------------ D_up, dC in us, U

def test_cal_line_keeps_its_line_kind():
    r = P.parse_line("[FRAME-TIME] cal i=3 why=game2 kind=disp shape=S6 n=100000 u=10,12 p=30,34")
    assert r["kind"] == "cal" and r["ckind"] == "disp" and r["shape"] == "S6"


def _dup_log(costs_by_cal, on_calls=(3000,), on_frames=1000, freq=10000000, shape="S6"):
    """One entry E1 of the given shape; per measured game g its ON calls on_calls[g - 1] over on_frames ON live
    frames (one ON point per game), and an OFF point that must not matter."""
    recs = [{"kind": "settled", "g": g, "freq": freq} for g in range(0, len(on_calls) + 1)]
    for g, c in enumerate(on_calls, 1):
        recs.append({"kind": "p", "game": g, "round": 1, "gate": 0, "live_frames": on_frames, "arm": "ON"})
        recs.append({"kind": "p", "game": g, "round": 1, "gate": 1, "live_frames": 50 * on_frames, "arm": "OFF"})
        recs.append({"kind": "census", "g": g, "entry": "E1", "shape": shape, "on": c, "guarded": 7})
    for i, c in enumerate(costs_by_cal):
        # c: closed-path ticks per call at 10 MHz; two batches of n = 1000
        recs.append({"kind": "cal", "i": i, "why": "game%d" % i, "ckind": "disp", "shape": shape, "n": 1000,
                     "u": "1000,1000", "p": "%d,%d" % (1000 + 1000 * c, 1000 + 1000 * c)})
    return recs


def test_d_up_dispatch_is_rate_times_cost_with_the_largest_as_floor():
    du, ds, rate = P.d_up(_dup_log([2, 2, 2, 2]))
    assert rate == {"E1": 3.0}
    assert ds == [pytest.approx(0.6)] * 4         # 3 calls per ON live frame x 0.2 us
    assert du == pytest.approx(0.6)


def test_d_up_dispatch_never_below_its_largest_calibration():
    # sixteen calibrations at 0.3 us and one at 0.9: mean + t SE is about 0.42, so the largest value binds
    du, ds, rate = P.d_up(_dup_log([1] * 16 + [3]))
    assert du == pytest.approx(0.9)


def test_d_up_dispatch_refuses_a_missing_shape():
    recs = _dup_log([2, 2])
    recs.append({"kind": "census", "g": 1, "entry": "E2", "shape": "S1", "on": 5, "guarded": 5})
    with pytest.raises(P.Refused):
        P.d_up(recs)


def test_d_up_uses_the_largest_per_game_on_rate_not_a_pooled_off_rate():
    # round-1 HIGH 3's counterexample: game 1 runs E1 20 times per ON live frame, game 2 0.2 times, at 1 us a call
    # (10 ticks). n_max is 20, so D_j = 20 us; a pooled rate (10.1) or a rate over the 50x larger OFF frames (0.2)
    # understates it.
    du, ds, rate = P.d_up(_dup_log([10, 10, 10], on_calls=(20000, 200)))
    assert rate == {"E1": pytest.approx(20.0)}
    assert du == pytest.approx(20.0) and ds == [pytest.approx(20.0)] * 3


# ------------------------------------------------------------------ zero state (VR8 part 1)

def _zp(g, rnd, pt, arm, zs, n=100, sc=1000):
    return {"kind": "p", "game": g, "round": rnd, "point": pt, "arm": arm, "n": n, "sC": sc, "zs": zs}


def test_zero_state_voids_the_whole_round():
    recs = [_zp(1, 1, 1, "ON", 0, sc=90000), _zp(1, 1, 2, "OFF", 4), _zp(1, 2, 1, "ON", 0, sc=30000),
            _zp(1, 2, 2, "OFF", 0, sc=10000)]
    g = P.games_of(recs)
    assert [(q["round"], q["point"]) for q in g[1]] == [(2, 1), (2, 2)]
    assert P.contrast_c(g[1])[0] == pytest.approx(200.0)


def test_game0_mutant_must_void_every_round():
    ok = P.zero_state([_zp(0, 1, 1, "ON", 4), _zp(0, 2, 1, "OFF", 0), _zp(0, 2, 2, "ON", 4)])
    assert ok[0] and ok[1:3] == (2, 2)
    bad = P.zero_state([_zp(0, 1, 1, "ON", 4), _zp(0, 2, 1, "OFF", 0), _zp(0, 2, 2, "ON", 0)])
    assert not bad[0] and bad[1:3] == (1, 2)


def test_zero_state_reports_a_game_with_no_valid_round():
    out = P.zero_state([_zp(0, 1, 1, "ON", 4), _zp(1, 1, 1, "ON", 1), _zp(2, 1, 1, "ON", 0)])
    assert out[3] == [(1, 1)] and out[4] == [1]


# ------------------------------------------------------------------ VR1, VR4, VR8 predecessor, VR9, and report() end to end

def test_vr1_flags_a_cap():
    recs = [{"kind": "settled", "g": 1, "vsync": 0, "target": -1}]
    assert P.vr1(recs, "", 2650.0)[0]
    assert not P.vr1(recs, "", 1e6 / 144)[0]                       # T_ref sits on 144 FPS
    assert not P.vr1([{"kind": "settled", "g": 1, "vsync": 1, "target": -1}], "", 2650.0)[0]
    assert not P.vr1(recs, "[FPSCAP] on", 2650.0)[0]


def test_vr4_bar():
    assert P.vr4(30.0, 2650.0) and not P.vr4(40.0, 2650.0)


FREQ, FHAT = 10000000, 3000000000


ENTRIES = P.expected_entries()
SHAPES = sorted(set(s for e, s in ENTRIES))
A3_DEP = [r[0] for r in P.a3_spec() if r[2] == "dependent"]
# ruling FRAME-TIME-ROUND-R4: the live rows (calibrated in game) and the rows calibrated at every game start
A3_LIVE = [r[0] for r in P.a3_spec() if r[2] == "dependent" and r[4] == P.LIVE_PROOF]
A3_CAL = [k for k in A3_DEP if k not in A3_LIVE]
# the six rows the ruling names (fixed here, so a row losing its live marker in a3.py fails the controls)
LIVE_SIX = ["CE_Pos", "CE_Recent", "CE_gun_scalars", "CE_capture", "SE_scalars", "IC_game"]
A3_DRAIN = [r[0] for r in P.a3_spec() if r[2] == "drained"]
# the plugin files holding the FtA3 registrations (mut_parse copies each)
A3_SITES = ["CombatEvidence.cs", "SeatEvidence.cs", "IdentityClockEvidence.cs", "HitEvidence.cs", "PoisonSync.cs",
            "CardDrawEvidence.cs", "PeerBuild.cs"]


def _log(carry_us=0.0, cost_us=80.0, games=17, seed=7, heavy_live=0, hash_at=(10, 20), f18="A", replay="settled", heavy_edge=0,
         drop_cal=(), drop_disp=(), drop_opened=(), shut_ic=(), drop_census=(), complete=True, routes="",
         drop_a3=(), drop_a3cal=(), a3_peak=None, drop_a3drain=(), a3_dirty=None, drop_heavy=(), drop_offthread=(),
         drop_flushed=(), drop_between=(), drop_w=(), refusals_why=("game", "quit"), a3_starts=None, a3_cal_p=None,
         drop_p=(), drop_replay=(), replay_bad=None, drop_counters=(), counters_bad=None, point_missing_end=None,
         a3_withheld=None, a3zero_lines=None, live_planning=None, live_beside=None, live_drop=(), live_bad=None,
         live_ticks=30, live_peak=None, fhat_fail=(), fhat_extra_fail=(), fhat_zero=(), disp_fail=None):
    """A synthetic sitting, every line as FtFrames, FtCalib, FtCensus and FtDrive write it. Point costs: ON adds
    cost_us of C per frame; a first-in-round ON point after an ON round end carries carry_us more (the predecessor
    case). The drop_* and shut_ic arguments remove or spoil records for the completeness controls."""
    import random
    rng = random.Random(seed)
    clock = [10 ** 6]
    L = ["[FRAME-TIME] settled g=-1 seed=1 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d" % (FREQ, FHAT),
         "[FRAME-TIME] plant c_plant=80 ticks=800 from=0.1.2"]
    for g in range(games):
        L.append("[FRAME-TIME] settled g=%d seed=1 c_plant=80 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                 " f18=%s answer=%s" % (g, FREQ, FHAT, f18, "replay" if f18 == "A" else "unmeasured"))
        if f18 == "A" and replay:
            if g not in drop_replay:
                L.append("[FRAME-TIME] answer_replay g=%d ticks=%d result=%s"
                         % (g, 4000, "timeout" if replay_bad == g else replay))
        if g not in drop_cal:
            # round-4 MEDIUM (ft_parse.py:1132): a failed f_hat calibration is a warning that still names its kind
            if g in fhat_fail:
                L.append("[FRAME-TIME] cal i=%d kind=fhat failed: overflow" % (g + 1))
            else:
                L.append("[FRAME-TIME] cal i=%d why=game%d kind=fhat f_hat=%d spins=1/1"
                         % (g + 1, g, 0 if g in fhat_zero else FHAT))
            if g in fhat_extra_fail:
                L.append("[FRAME-TIME] cal i=%d kind=fhat failed: overflow" % (g + 1))
            for s in SHAPES:
                if (g, s) in drop_disp:
                    continue
                if disp_fail == (g, s):
                    L.append("[FRAME-TIME] cal i=%d why=game%d kind=disp shape=%s failed: no calls" % (g + 1, g, s))
                    continue
                L.append("[FRAME-TIME] cal i=%d why=game%d kind=disp shape=%s n=100000 u=1000000,1000000"
                         " p=1030000,1030000" % (g + 1, g, s))
            L.append("[FRAME-TIME] cal i=%d why=game%d kind=span shape=span.empty n=100000 u=100000,100000"
                     " p=150000,150000" % (g + 1, g))
            for k in A3_DEP:
                if (g, k) not in drop_a3cal:
                    ap = (a3_cal_p or {}).get(g, 130000)
                    if a3_withheld == k:
                        L.append("[FRAME-TIME] cal i=%d why=game%d kind=a3 k=%s withheld=1" % (g + 1, g, k))
                        continue
                    # a live row has no game-start calibration (FtA3.Calibrate skips it); live_planning gives it
                    # the planning (u/p) line a stand-in would write, in place of its executed line
                    if k in A3_LIVE and k not in (live_planning, live_beside):
                        continue
                    L.append("[FRAME-TIME] cal i=%d why=game%d kind=a3 k=%s n=1000 u=100000,100000 p=%d,%d"
                             % (g + 1, g, k, ap, ap))
        if g not in drop_opened:
            L.append("[FRAME-TIME] opened g=%d se=1 ce=1 %s" % (g, "ic=0" if g in shut_ic else "ic=1"))
        base = 2600.0 * (1 + 0.05 * rng.random())
        pred = "none"
        guarded = 0
        offl = 0
        onlf = 0
        for rnd in range(1, 8):
            first_on = rng.random() < 0.5
            for pt in (1, 2):
                on = first_on if pt == 1 else not first_on
                n = 2000 + rng.randrange(800)
                c_us = base + rng.gauss(0, 8) + (cost_us if on else 0.0)
                if on and pt == 1 and pred == "ON":
                    c_us += carry_us
                sc = int(n * c_us * FHAT / 1e6)
                f_us = c_us
                sf = int(n * f_us * FREQ / 1e6)
                pn = n // 4 if not on else 0
                psc = int(pn * (c_us + 80.0) * FHAT / 1e6) if pn else 0
                lf = n + pn + 1
                spg = int(lf * 20.0 * FREQ / 1e6) if on else 0
                spu = int(lf * 1.0 * FREQ / 1e6)
                zs = 4 if g == 0 and on else 0
                gq = 0 if on else 3 * lf
                guarded += gq
                offl += 0 if on else lf
                t0 = clock[0]
                t1 = t0 + int(lf * c_us * FREQ / 1e6)
                clock[0] = t1 + FREQ // 2
                onlf += lf if on else 0
                if (g, rnd, pt) not in drop_p:
                    L.append("[FRAME-TIME] p pt=%d.%d.%d arm=%s gate=%d pred=%s n=%d sF=%d sS=%d sC=%d maxF=%d pn=%d psF=%d "
                         "psS=%d psC=%d sP=%d psP=%d excl=1 plant_mixed=0 windows=%d live_frames=%d missing_end=0 "
                         "span_g=%d span_gn=%d span_u=%d span_un=%d on_calls=%d guarded=%d zs=%d zl=1 t0=%d t1=%d "
                         "answer=%s"
                         % (g, rnd, pt, "ON" if on else "OFF", 0 if on else 1, pred, n, sf, sf // 2, sc, sf // n * 3,
                            pn, int(pn * f_us * FREQ / 1e6), int(pn * (f_us / 2 + 80.0) * FREQ / 1e6), psc,
                            int(sc * 1.1), int(psc * 1.1), (n + pn) // 120, lf, spg, lf if on else 0, spu, lf,
                            3 * lf if on else 0, gq, zs, t0, t1, "replay" if f18 == "A" else "unmeasured"))
                # FtFrames writes a between line at every point start after the game's first point
                if not (rnd == 1 and pt == 1) and (g, rnd, pt) not in drop_between:
                    L.append("[FRAME-TIME] between g=%d after=%s ticks=%d calls=4" % (g, pred, 2000))
                for w in range((n + pn) // 120):
                    if w == 0 and (g, rnd, pt) in drop_w:
                        continue
                    plant = 1 if (not on and w % 4 == 0) else 0
                    k = 1 if rng.random() < 0.01 else 0
                    L.append("[FRAME-TIME] w pt=%d.%d.%d arm=%s plant=%d partial=0 n=120 sF=1 sS=1 sC=1 maxF=1 medF=1 "
                             "e4=%d,%d e8=0,0 e16=0,0 gc=0" % (g, rnd, pt, "ON" if on else "OFF", plant, k, k))
                pred = "ON" if on else "OFF"
        for k, (e, s) in enumerate(ENTRIES):
            if (g, e) in drop_census or (g, "*") in drop_census:
                continue
            on_n = 3 * onlf if k == 0 else 0
            L.append("[FRAME-TIME] census g=%d entry=%s comp=X shape=%s on=%d guarded=%d outside=0"
                     % (g, e, s, on_n, guarded if k == 0 else 0))
        for op in P.HEAVY_OPS:
            if (g, op) in drop_heavy:
                continue
            k = heavy_live if op == "pump" else 0
            ke = heavy_edge if op == "enqueue" else 0
            L.append("[FRAME-TIME] heavy g=%d op=%s live=%d between=7 pick=1 over=1 menu=0 at_call=%d edge=%d off=0"
                     % (g, op, k + ke, k, ke))
        if g not in drop_offthread:
            L.append("[FRAME-TIME] offthread g=%d span_off=0 hash_t0=%d hash_t1=%d" % (g, hash_at[0], hash_at[1]))
        for k in A3_DEP:
            if (g, k) not in drop_a3:
                L.append("[FRAME-TIME] a3 g=%d k=%s cap=32 steady=1 reads_on=%d reads_win=%d writes_on=%d"
                         % (g, k, 2 * onlf, (3 * onlf if a3_peak == (g, k) else onlf // 4), 3 * onlf))
        # ruling FRAME-TIME-ROUND-R4: each live row's executed line, written by FtA3.LogGame with the a3 lines
        for k in A3_LIVE:
            if (g, k) in live_drop or k in (live_planning, a3_withheld):
                continue
            rd = 2 * onlf
            tk = rd * (live_ticks * 3 if live_peak == (g, k) else live_ticks)
            v = dict(i=g + 1, reads=rd, scopes=rd // 2, ticks=tk, tmax=4 * live_ticks, unscoped=0, depth_err=0)
            v.update((live_bad or {}).get((g, k), {}))
            L.append("[FRAME-TIME] cal i=%d why=game%d kind=a3 k=%s live=1 reads=%d scopes=%d ticks=%d tmax=%d "
                     "unscoped=%d depth_err=%d" % (v["i"], g, k, v["reads"], v["scopes"], v["ticks"], v["tmax"],
                                                   v["unscoped"], v["depth_err"]))
        for k in A3_DRAIN:
            if (g, k) not in drop_a3drain:
                st = a3_starts[2] if a3_starts and a3_starts[:2] == (g, k) else 14     # 7 rounds of 2 points
                L.append("[FRAME-TIME] a3drain g=%d k=%s starts=%d nonempty=%d faults=0"
                         % (g, k, st, 1 if a3_dirty == (g, k) else 0))
        if "game" in refusals_why:
            L.append("[FRAME-TIME] refusals why=%s pairs=3 queue:e=3 sent:GET_h/api/v1/mod-version=1 "
             "dispatched:GET_h/api/v1/mod-version=1" % ("game%d" % g) + routes)
        if g not in drop_flushed:
            L.append("[FRAME-TIME] flushed g=%d why=%s" % (g, "next_game" if g < games - 1 else "settle"))
        if g not in drop_counters:
            cb = counters_bad if counters_bad and counters_bad[0] == g else (g, None)
            L.append("[FRAME-TIME] counters g=%d frames=%d missing_end=%d cycle_failures=%d span_depth_violations=%d"
                     % (g, 1000 * (g + 1), cb[1] == "missing_end", cb[1] == "cycle_failures",
                        cb[1] == "span_depth_violations"))
        for (zk, zw) in (a3zero_lines or {}).items():
            if g >= 1:
                L.append("[FRAME-TIME] a3zero g=%d k=%s starts=14 written=%d faults=0" % (g, zk, zw))
    if point_missing_end:
        head = "[FRAME-TIME] p pt=%d.%d.%d " % point_missing_end
        hit = [i for i, x in enumerate(L) if x.startswith(head)]
        assert len(hit) == 1
        L[hit[0]] = L[hit[0]].replace(" missing_end=0 ", " missing_end=1 ")
    if complete:
        L.append("[FRAME-TIME] sitting complete g=%d" % (games - 1))
    if "quit" in refusals_why:
        L.append("[FRAME-TIME] refusals why=%s pairs=3 queue:e=3 sent:GET_h/api/v1/mod-version=1 "
             "dispatched:GET_h/api/v1/mod-version=1" % "quit" + routes)
    return "\n".join("[Info   :CompetitiveRounds] " + x for x in L)


def test_report_end_to_end_reaches_a_verdict():
    out = P.report(_log())
    assert "not computable" not in out, out
    assert "SITTING complete: games 0 to 16" in out, out
    assert "VR8 zero-state PASS: game 0 (mutant) 7 of 7 rounds void" in out
    assert re.search(r"^VERDICT B1 (PASS|SID|FAIL): U [0-9.]+ us against T_ref", out, re.M), out
    assert "INVALID" not in out and "withheld" not in out, out
    assert "VERDICT B2 PASS" in out and "VERDICT B3 PASS" in out, out
    assert "F18 reading A PASS" in out, out


def test_report_carries_the_specified_figures():
    # round-1 MEDIUM (ft_parse:793): the classification and the figures V4 section 0 and 3.3 to 3.9 report
    out = P.report(_log())
    for want in ("U without D_up", "dF ", "dS ", "dP (process CPU, all threads)", "e_F ", "e_S ", "trend: d_g slope",
                 "last four games' mean", "UPKEEP spans per live frame: ON", "format M's own stamps",
                 "between-point spans after ON points", "conditional: U bounds the NET", "PASS <= 3, SID <= 5"):
        assert want in out, (want, out)
    assert P.classify(2.9, 100) == "PASS" and P.classify(4.0, 100) == "SID" and P.classify(5.1, 100) == "FAIL"


def test_a3_is_the_largest_per_game_window_rate_times_the_calibrated_difference():
    # ruling FRAME-TIME-ROUND-R1-A1 (route D): A3 = sum over dependent structures of r_k_max x d_k
    recs = P.read(_log())
    v, ds, rate, dk = P.a3(recs, last_game=P.LAST_GAME)
    d = 30000 / 1000 * 1e6 / FREQ                     # (p - u) / n ticks per read, in us
    assert set(rate) == set(A3_DEP) and all(abs(dk[k] - d) < 1e-9 for k in A3_DEP)
    games = P.games_of(recs)
    want = 0.0
    for k in A3_DEP:
        rk = max(r["reads_win"] / sum(q["live_frames"] for q in games[r["g"]] if q["gate"] == 0)
                 for r in recs if r["kind"] == "a3" and r["k"] == k and r["g"] in games)
        assert abs(rate[k] - rk) < 1e-12
        want += rk * d
    assert abs(v - want) < 1e-9 and v > 0
    # the per-game maximum, not the last game's rate: a peak planted in an early game sets r_k_max
    k = A3_DEP[0]
    recs = P.read(_log(a3_peak=(3, k)))
    v2, ds2, rate2, dk2 = P.a3(recs, last_game=P.LAST_GAME)
    games = P.games_of(recs)
    peak = [r for r in recs if r["kind"] == "a3" and r["k"] == k and r["g"] == 3][0]["reads_win"]
    r3 = peak / sum(q["live_frames"] for q in games[3] if q["gate"] == 0)
    assert r3 > 2 and abs(rate2[k] - r3) < 1e-12 and v2 > v, (rate2, r3)


def test_a3_refuses_a_missing_line_or_calibration():
    # ruling A1 part 3: the refill window counted from absent records cannot pass, nor a missing calibration
    k = A3_DEP[0]
    with pytest.raises(P.Refused, match="a3 lines"):
        P.a3(P.read(_log(drop_a3={(5, k)})), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="no a3 line"):
        P.a3(P.read(_log(drop_a3cal={(7, k)})), last_game=P.LAST_GAME)
    out = P.report(_log(drop_a3={(5, k)}))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


def test_a3_drained_rows_refuse_a_missing_line_or_a_point_that_started_holding_entries():
    # ruling A1 part 3: a drained row's zero is checked by the build, never assumed
    assert A3_DRAIN, "the inventory names no drained row"
    k = A3_DRAIN[0]
    v, ds, rate, dk = P.a3(P.read(_log()), last_game=P.LAST_GAME)
    assert k not in rate and k not in dk
    with pytest.raises(P.Refused, match="a3drain lines"):
        P.a3(P.read(_log(drop_a3drain={(4, k)})), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="nonempty"):
        P.a3(P.read(_log(a3_dirty=(6, k))), last_game=P.LAST_GAME)
    out = P.report(_log(a3_dirty=(6, k)))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


def _survivor_ids():
    here = os.path.dirname(os.path.abspath(__file__))
    ids, dep = [], []
    sec = None
    for ln in open(os.path.join(here, "SURVIVORS.md"), encoding="utf-8"):
        if ln.startswith("## "):
            sec = ln.strip()
            continue
        m = re.match(r"\| (S\d\d) ", ln)
        if not m:
            continue
        if sec == "## Survivors read live":
            ids.append(m.group(1))
        elif sec == "## Content-dependent rows and their steady state":
            dep.append(m.group(1))
    return ids, dep


def test_a3_inventory_names_every_survivor_once_and_the_build_registers_each_row():
    # ruling A1 part 2: the inventory is SURVIVORS.md's; part 3: removing a structure fails, a row the build does not
    # register fails, a capacity typed instead of taken from the code constant fails
    spec = P.a3_spec()
    ids, dep = _survivor_ids()
    sids = [r[1] for r in spec]
    assert len(ids) >= 36 and sorted(sids) == sorted(ids) and len(set(sids)) == len(sids), (sids, ids)
    kinds = dict((r[1], r[2]) for r in spec)
    for sid in dep:
        assert kinds[sid] in ("dependent", "drained"), (sid, kinds[sid])
    # default-deny (ruling FRAME-TIME-ROUND-R2 (1)): a zero row only with its proof; S18 is dependent since round 3
    for r in spec:
        assert r[2] != "zero" or r[4].startswith(("sweep:", "probe:")), r
    plug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin")
    ft = open(os.path.join(plug, "FtA3.cs"), encoding="utf-8-sig").read()
    src = "".join(open(os.path.join(plug, f), encoding="utf-8-sig").read() for f in A3_SITES)
    live = [(r[0], r[2]) for r in spec if r[2] != "zero"]
    m = re.search(r"internal const int Rows = (\d+);", ft)
    assert m and int(m.group(1)) == len(live), "FtA3.Rows differs from the inventory's registered rows"
    for n, kind in live:
        assert re.search(r"\b%s = \d+" % n, ft), "FtA3 has no constant for %s" % n
        call = "SetDrained" if kind == "drained" else "Set"
        hits = re.findall(r"FtA3\.%s\(FtA3\.%s, \"%s\", ([^,)]+)" % (call, n, n), src)
        assert len(hits) == 1, "%s: %d FtA3.%s registrations" % (n, len(hits), call)
        if kind == "dependent":
            assert not re.fullmatch(r"\s*\d+\s*", hits[0]) or hits[0].strip() == "1", \
                "%s: refill typed as %s, not a code constant" % (n, hits[0])


def test_a3_rows_need_a_kind_and_a_zero_row_its_reason():
    recs = P.read(_log())
    with pytest.raises(P.Refused, match="names no structure"):
        P.a3(recs, spec=[])
    with pytest.raises(P.Refused, match="needs a reason"):
        P.a3(recs, spec=[("X", "S99", "zero", " ", "sweep:no-live-write")])
    assert P.a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins", "sweep:no-live-write")])[0] == 0.0


def test_a3_zero_row_without_its_proof_reference_fails_the_parse():
    # ruling FRAME-TIME-ROUND-R2 (1), default-deny: a zero row carries its proof (sweep:... or probe:...), a drained
    # row its probe (probe:a3drain), and a row of the old four-field shape is refused
    recs = P.read(_log())
    for proof in ("", " ", "sweep:", "because", "probe"):
        with pytest.raises(P.Refused, match="proof reference"):
            P.a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins", proof)])
    with pytest.raises(P.Refused, match="probe:a3drain"):
        P.a3(recs, spec=[("X", "S99", "drained", "emptied between points", "sweep:no-live-write")])
    with pytest.raises(P.Refused, match="name, survivor id, kind, reason, proof"):
        P.a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins")])
    # round-3 MEDIUM (ft_parse.py:540): a probe token is accepted only with its records
    with pytest.raises(P.Refused, match="probe:a3zero needs one a3zero line"):
        P.a3(recs, spec=[("X", "S99", "zero", "r", "probe:a3zero")])
    # the shipped inventory: every zero row names its proof, every drained row its probe
    for r in P.a3_spec():
        assert len(r) == 5, r
        if r[2] == "zero":
            assert re.fullmatch(r"(sweep|probe):\S+", r[4]), r
        if r[2] == "drained":
            assert r[4] == "probe:a3drain", r
    P.a3(recs, last_game=P.LAST_GAME)


def test_a3_every_games_calibration_is_required_and_a_dropped_one_never_passes():
    # round-2 HIGH (ft_parse.py:495), Codex's own control: game 8's A3 calibration costs most, so A_8 decides A3 and
    # B1 is FAIL; dropping game 8's family used to shrink J and turn FAIL into PASS. Now it withholds the verdict.
    big = {8: 100000 + 2000000}
    out = P.report(_log(a3_cal_p=big))
    assert "VERDICT B1 FAIL" in out, out
    for drop in ({(8, k) for k in A3_DEP}, {(8, A3_DEP[0])}):
        out2 = P.report(_log(a3_cal_p=big, drop_a3cal=drop))
        assert "VERDICT B1 withheld" in out2, out2
        assert not re.search(r"^VERDICT B1 (PASS|SID)", out2, re.M), out2
    with pytest.raises(P.Refused, match="game 8"):
        P.a3(P.read(_log(a3_cal_p=big, drop_a3cal={(8, k) for k in A3_DEP})), last_game=P.LAST_GAME)
    # a live row's executed line names game 8's start calibration, which is gone: either refusal names it
    with pytest.raises(P.Refused, match="game 8 (has 0 start calibrations|line i=9 is not the game's start calibration)"):
        P.a3(P.read(_log(drop_cal={8})), last_game=P.LAST_GAME)
    # the default reads the sitting's games too: no caller can skip the per-game rule by omitting last_game
    with pytest.raises(P.Refused, match="game 8"):
        P.a3(P.read(_log(a3_cal_p=big, drop_a3cal={(8, k) for k in A3_DEP})))


def test_a3_drained_starts_equal_the_games_point_count():
    # round-2 MEDIUM: a drained row's probe ran at every point start of the game, no fewer and no more
    k = A3_DRAIN[0]
    for st in (13, 15, 1):
        with pytest.raises(P.Refused, match="point starts"):
            P.a3(P.read(_log(a3_starts=(4, k, st))), last_game=P.LAST_GAME)
    P.a3(P.read(_log(a3_starts=(4, k, 14))), last_game=P.LAST_GAME)


# the absent-record sweep (ruling FRAME-TIME-ROUND-R2): each record's absence fails the run
ABSENT = (
    ("flushed", dict(drop_flushed={16})),
    ("flushed", dict(drop_flushed={3})),
    ("between", dict(drop_between={(5, 3, 2)})),
    ("between", dict(drop_between={(0, 1, 2)})),
    ("heavy", dict(drop_heavy={(7, "spool")})),
    ("heavy", dict(drop_heavy={(0, "hash_now")})),
    ("offthread", dict(drop_offthread={9})),
    ("window", dict(drop_w={(2, 4, 1)})),
    ("refusals", dict(refusals_why=())),
    ("between", dict(drop_p={(6, 2, 1)})),
    ("answer_replay", dict(drop_replay={8})),
    ("answer_replay", dict(drop_replay={0})),
    ("counters", dict(drop_counters={16})),
    ("counters", dict(drop_counters={4})),
)


def _g16(r):
    return r.get("g") == 16 or r.get("game") == 16 or r.get("why") == "game16"


def _drop_kind(log, kind, where=None):
    """The log with every line of `kind` (as parse_line reads it) removed, where `where(rec)` holds; and the count."""
    keep, n = [], 0
    for ln in log.splitlines():
        r = P.parse_line(ln)
        if r is not None and r["kind"] == kind and (where is None or where(r)):
            n += 1
            continue
        keep.append(ln)
    return "\n".join(keep), n


INCOMPLETE = r"^VERDICT B1 withheld: sitting incomplete"
# One deletion control per kind the parser reads (round-3 MEDIUMs ft_parse.py:1461, ft_parse.py:1077, FtSchedule.cs:140,
# ruling FRAME-TIME-ROUND-R3-A1): (kind, fixture, which lines go, what the run must then say). Every RECORDS kind is
# here or in RECORD_EVENTS; test_every_record_kind_has_a_deletion_control fails on a kind in neither.
DELETIONS = (
    ("settled", "sitting", _g16, INCOMPLETE),
    ("p", "sitting", _g16, INCOMPLETE),
    ("w", "sitting", _g16, INCOMPLETE),
    ("cal", "sitting", _g16, INCOMPLETE),
    ("census", "sitting", _g16, INCOMPLETE),
    ("opened", "sitting", _g16, r"^VERDICT B1 INVALID: VR5 failed"),
    ("heavy", "sitting", _g16, INCOMPLETE),
    ("offthread", "sitting", _g16, INCOMPLETE),
    ("a3", "sitting", _g16, r"^VERDICT B1 withheld: U not computable"),
    ("a3drain", "sitting", _g16, r"^VERDICT B1 withheld: U not computable"),
    ("answer_replay", "sitting", _g16, INCOMPLETE),
    ("between", "sitting", _g16, INCOMPLETE),
    ("flushed", "sitting", _g16, INCOMPLETE),
    ("counters", "sitting", _g16, INCOMPLETE),
    ("plant", "sitting", None, r"^VERDICT B1 withheld: VR1"),
    ("refusals", "sitting", None, INCOMPLETE),
    ("sitting", "sitting", None, INCOMPLETE),
    ("a3zero", "a3zero", _g16, "probe:a3zero needs one a3zero line in game 16"),
    ("menu", "menu", lambda r: r.get("seg") == 9, "menu"),
    ("p", "menu", lambda r: r.get("pt") == "-1.9.1", "menu"),
    ("cal", "menu", lambda r: r.get("why") == "menu2", "menu"),
    ("menu_done", "menu", None, "menu"),
    ("menu_armed", "menu", None, "menu"),
    ("settled", "menu", None, "menu"),
)
# the kinds whose PRESENCE is the event (their absence is the normal case): test_failure_events_make_the_run_incomplete
# and test_vr6_build_fails_on_a_disarm are their controls
RECORD_EVENTS = {"disarmed", "game", "start", "clock"}


def _a3zero_case():
    k = A3_DEP[0]
    spec = [(n, s, ("zero" if n == k else kd), (w or "r"), ("probe:a3zero" if n == k else pr))
            for n, s, kd, w, pr in P.a3_spec()]
    drop = {(g, k) for g in range(17)}
    return _log(drop_a3=drop, drop_a3cal=drop, a3zero_lines={k: 0}), spec


@pytest.mark.parametrize("kind,fixture,where,want", DELETIONS)
def test_deleting_each_record_kind_withholds(kind, fixture, where, want):
    if fixture == "sitting":
        base = _log()
        assert re.search(r"^VERDICT B1 SID", P.report(base), re.M)
        log, n = _drop_kind(base, kind, where)
        assert n >= 1, kind
        assert re.search(want, P.report(log), re.M), (kind, P.report(log))
    elif fixture == "a3zero":
        base, spec = _a3zero_case()
        P.a3(P.read(base), spec=spec)
        log, n = _drop_kind(base, kind, where)
        assert n >= 1
        with pytest.raises(P.Refused, match=want):
            P.a3(P.read(log), spec=spec)
    else:
        base = _menu_log()
        assert P.menu_check(P.read(base))[0]
        log, n = _drop_kind(base, kind, where)
        assert n >= 1, kind
        bad = "refused"
        try:
            ok, _, bad = P.menu_check(P.read(log))
        except P.Refused:
            ok = False
        assert not ok, (kind, bad)


def test_every_record_kind_has_a_deletion_control():
    covered = set(k for k, _, _, _ in DELETIONS)
    assert covered | RECORD_EVENTS == set(P.RECORDS), (sorted(set(P.RECORDS) - covered - RECORD_EVENTS),
                                                       sorted((covered | RECORD_EVENTS) - set(P.RECORDS)))
    assert not covered & RECORD_EVENTS


def test_every_emitted_kind_is_read_or_named():
    # every "[FRAME-TIME] <kind>" the build writes is a RECORDS kind or named in EMITTED_UNREAD with its reason; no kind
    # the parser reads is called unread; every RECORDS kind but a3zero (no build writes it today) is written
    here = os.path.dirname(os.path.abspath(__file__))
    plug = os.path.join(here, "..", "..", "plugin")
    emitted = set()
    for fn in sorted(os.listdir(plug)):
        if fn.endswith(".cs"):
            emitted |= set(re.findall(r'"\[FRAME-TIME\] (\w+)', open(os.path.join(plug, fn), encoding="utf-8").read()))
    src = open(os.path.join(here, "ft_parse.py"), encoding="utf-8").read()
    used = set(re.findall(r'\["kind"\] [!=]= "(\w+)"', src)) | set(k for k, _, _ in P.FAILURE_EVENTS)
    assert emitted <= set(P.RECORDS) | set(P.EMITTED_UNREAD), sorted(emitted - set(P.RECORDS) - set(P.EMITTED_UNREAD))
    assert not set(P.EMITTED_UNREAD) & used, sorted(set(P.EMITTED_UNREAD) & used)
    assert not set(P.EMITTED_UNREAD) & set(P.RECORDS)
    assert set(P.EMITTED_UNREAD) <= emitted, sorted(set(P.EMITTED_UNREAD) - emitted)
    assert set(P.RECORDS) - emitted == {"a3zero"}, sorted(set(P.RECORDS) - emitted)


FAILURE_LINES = ("[Warning:CompetitiveRounds] [FRAME-TIME] game over failed: boom",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] game start failed: boom",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] start failed: boom",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate 1)")


def test_failure_events_make_the_run_incomplete():
    # round-4 sweep of every kind the build writes: a failure warning is never ignored
    for ln in FAILURE_LINES:
        log = _log()
        i = log.index("[FRAME-TIME] flushed g=9")
        log = log[:i] + ln + "\n" + log[i:]
        assert any("failure event" in m for m in P.complete(P.read(log))), ln
        assert re.search(INCOMPLETE, P.report(log), re.M), ln
        ok, _, bad = P.menu_check(P.read(_menu_log() + "\n" + ln))
        assert not ok and any("failure event" in b for b in bad), (ln, bad)
    # the control the other way: the clock's ordinary line is not a failure
    ok_line = "[Info   :CompetitiveRounds] [FRAME-TIME] clock installed freq=10000000 hires=1"
    assert P.complete(P.read(_log() + "\n" + ok_line)) == []
    assert P.menu_check(P.read(_menu_log() + "\n" + ok_line))[0]


def test_f18_failure_guards_b1():
    # round-3 MEDIUM (ft_parse.py:1461): game 8's replay failing makes F18 FAIL, and B1 is INVALID, never PASS or SID
    out = P.report(_log(replay_bad=8))
    assert re.search(r"^F18 reading A FAIL", out, re.M), out
    assert re.search(r"^VERDICT B1 INVALID: .*F18", out, re.M), out


def test_vr2_judges_the_last_games_counters_and_every_point_stamp():
    # round-3 MEDIUM (FtSchedule.cs:140): the last game's play is judged by its flush-time counters line, and a point
    # line with a missed FT_End stamp fails VR2
    ok, why = P.vr2(P.read(_log()), P.LAST_GAME)
    assert ok, why
    for kw, want in ((dict(counters_bad=(16, "missing_end")), "counters g=16 missing_end=1"),
                     (dict(counters_bad=(16, "cycle_failures")), "counters g=16 cycle_failures=1"),
                     (dict(counters_bad=(9, "span_depth_violations")), "counters g=9 span_depth_violations=1"),
                     (dict(drop_counters={16}), "game 16: 0 counters lines"),
                     (dict(point_missing_end=(16, 7, 2)), "point 16.7.2: missing_end=1")):
        ok, why = P.vr2(P.read(_log(**kw)), P.LAST_GAME)
        assert not ok and any(want in w for w in why), (kw, why)


def test_menu_check_needs_every_cycle_calibration_and_the_terminal_snapshot():
    # round-3 MEDIUM (ft_parse.py:1077): a failing menu calibration (cycle 4 off by 5 percent) deleted must not pass,
    # nor a deleted or failing terminal snapshot
    ok, _, bad = P.menu_check(P.read(_menu_log(fhat_last=int(FHAT * 1.05))))
    assert not ok, bad
    ok, _, bad = P.menu_check(P.read(_menu_log(fhat_last=int(FHAT * 1.05), drop_menu_cal=4)))
    assert not ok and any("menu calibrations" in b for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(drop_menu_cal=0)))
    assert not ok and any("menu calibrations" in b for b in bad), bad
    with pytest.raises(P.Refused, match="settled line after menu_done"):
        P.menu_check(P.read(_menu_log(drop_terminal=True)))
    # the snapshot written before menu_done is not the terminal one
    with pytest.raises(P.Refused, match="settled line after menu_done"):
        P.menu_check(P.read(_menu_log(terminal_misplaced=True)))
    ok, _, bad = P.menu_check(P.read(_menu_log(terminal_bad=True)))
    assert not ok and any("terminal settled line missing_end=1" in b for b in bad), bad
    # a settled line the build never writes in a menu run fails it (its counters are not this run's)
    ok, _, bad = P.menu_check(P.read(_menu_log(extra_settled=True)))
    assert not ok and any("settled lines inside the menu run" in b for b in bad), bad


def test_menu_check_validates_the_startup_and_the_terminal_snapshot():
    # round-4 MEDIUM (ft_parse.py:1219): Codex's counterexample, the real menu shape with its startup snapshot,
    # passes; the startup snapshot is required at its position and shape, the terminal one after menu_done
    ok, _, bad = P.menu_check(P.read(_menu_log()))
    assert ok, bad
    ok, _, bad = P.menu_check(P.read(_menu_log(drop_startup=True)))
    assert not ok and any("startup snapshot" in b for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(startup_bad=True)))
    assert not ok and any("startup snapshot" in b for b in bad), bad
    with pytest.raises(P.Refused, match="settled line after menu_done"):
        P.menu_check(P.read(_menu_log(drop_terminal=True)))
    # a calibration failure warning in a menu run fails it
    ok, _, bad = P.menu_check(P.read(_menu_log(menu_fhat_fail=True)))
    assert not ok and any("failure warnings" in b for b in bad), bad


def test_a3_probe_proofs_need_their_records_and_contrary_ones_fail():
    # round-3 MEDIUM (ft_parse.py:540): probe:a3zero accepted only with consistent a3zero lines; an unknown token, a
    # contrary record, or live writes counted for a zero row are refused
    k = A3_DEP[0]
    spec = [(n, s, ("zero" if n == k else kd), (w or "r"), ("probe:a3zero" if n == k else pr))
            for n, s, kd, w, pr in P.a3_spec()]
    recs = P.read(_log(drop_a3={(g, k) for g in range(17)}, drop_a3cal={(g, k) for g in range(17)}))
    with pytest.raises(P.Refused, match="probe:a3zero needs one a3zero line"):
        P.a3(recs, spec=spec)
    good = P.read(_log(drop_a3={(g, k) for g in range(17)}, drop_a3cal={(g, k) for g in range(17)}, a3zero_lines={k: 0}))
    P.a3(good, spec=spec)
    bad = P.read(_log(drop_a3={(g, k) for g in range(17)}, drop_a3cal={(g, k) for g in range(17)}, a3zero_lines={k: 1}))
    with pytest.raises(P.Refused, match="written=1"):
        P.a3(bad, spec=spec)
    spec2 = [(n, s, kd, w, ("sweep:anything" if n == k else pr)) for n, s, kd, w, pr in spec]
    with pytest.raises(P.Refused, match="names no evidence"):
        P.a3(good, spec=spec2)
    spec3 = [(n, s, kd, w, ("sweep:no-live-write" if n == k else pr)) for n, s, kd, w, pr in spec]
    with pytest.raises(P.Refused, match="contrary evidence"):
        P.a3(P.read(_log()), spec=spec3)


def test_vr2_needs_a_successful_fhat_and_rejects_calibration_failures():
    # round-4 MEDIUM (ft_parse.py:1132): Codex's counterexample, a failure warning in place of game 5's fhat line, kept
    # VR2 PASS; it now fails, as does a failure beside a success, an f_hat of 0 and a failed disp shape
    ok, why = P.vr2(P.read(_log()), P.LAST_GAME)
    assert ok, why
    ok, why = P.vr2(P.read(_log(fhat_fail={5})), P.LAST_GAME)
    assert not ok and any("game 5: calibration 6 has no successful fhat line" in w for w in why), why
    assert any("game 5: calibration 6 carries failure warnings for fhat" in w for w in why), why
    ok, why = P.vr2(P.read(_log(fhat_extra_fail={5})), P.LAST_GAME)
    assert not ok and any("carries failure warnings for fhat" in w for w in why), why
    ok, why = P.vr2(P.read(_log(fhat_zero={5})), P.LAST_GAME)
    assert not ok and any("game 5: calibration 6 has no successful fhat line" in w for w in why), why
    s = sorted(SHAPES)[0]
    ok, why = P.vr2(P.read(_log(disp_fail=(5, s))), P.LAST_GAME)
    assert not ok and any("no disp line for shapes" in w for w in why), why
    out = P.report(_log(fhat_fail={5}))
    assert "VR2 instrument FAIL" in out and re.search(r"^VERDICT B1 (INVALID|withheld)", out, re.M), out


def test_live_rows_take_their_executed_in_game_calibration():
    # ruling FRAME-TIME-ROUND-R4: the six live rows are calibrated by their executed in-game lines: d_k is the
    # largest per-game ticks / reads, and enters every A_j
    assert sorted(A3_LIVE) == sorted(LIVE_SIX)
    recs = P.read(_log())
    d, det = P.a3_live(recs)
    want = 30 * 1e6 / FREQ
    assert sorted(d) == sorted(A3_LIVE) and all(abs(d[k] - want) < 1e-9 for k in A3_LIVE), d
    assert all(len(det[k]) == P.LAST_GAME + 1 for k in A3_LIVE), det
    v, ds, rate, dk = P.a3(recs, last_game=P.LAST_GAME)
    assert all(abs(dk[k] - want) < 1e-9 for k in A3_LIVE)
    # the per-game maximum: a game whose reads cost three times as much sets d_k
    k = A3_LIVE[0]
    d2, _ = P.a3_live(P.read(_log(live_peak=(4, k))))
    assert abs(d2[k] - 3 * want) < 1e-9, d2
    v2 = P.a3(P.read(_log(live_peak=(4, k))), last_game=P.LAST_GAME)[0]
    assert v2 > v
    out = P.report(_log())
    assert "A3 live rows (this seat): " in out and "U not computable" not in out, out


def test_live_row_planning_or_withheld_line_never_passes_as_executed():
    # ruling FRAME-TIME-ROUND-R4 (R3-A1 stands): a planning value or a withheld line can never stand in for a live
    # row's executed calibration, in place of it or beside it
    for k in LIVE_SIX:
        with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a planning" % k):
            P.a3(P.read(_log(live_planning=k)), last_game=P.LAST_GAME)
    k = A3_LIVE[1]
    with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a planning" % k):
        P.a3(P.read(_log(live_beside=k)), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a withheld" % k):
        P.a3(P.read(_log(a3_withheld=k)), last_game=P.LAST_GAME)
    for kw in (dict(live_planning=k), dict(live_beside=k), dict(a3_withheld=k)):
        out = P.report(_log(**kw))
        assert "U not computable" in out and "VERDICT B1 withheld" in out, (kw, out)


def test_live_row_lines_are_complete_and_consistent():
    # every game 0..16 carries exactly one executed line per live row, under that game's start calibration, its
    # reads equal to the game's a3 line, every read scoped and every scope balanced; a live line for a row the
    # inventory does not mark live is refused; a row never read in any measured game is withheld
    k = A3_LIVE[2]
    cases = [
        (dict(live_drop={(5, k)}), "game 5 has 0 executed calibration lines"),
        (dict(live_drop={(0, k)}), "game 0 has 0 executed calibration lines"),
        (dict(live_bad={(5, k): {"reads": 7, "scopes": 3, "ticks": 210, "tmax": 120}}), "game 5 executed reads 7"),
        (dict(live_bad={(5, k): {"unscoped": 1}}), "game 5 unscoped=1"),
        (dict(live_bad={(5, k): {"depth_err": 2}}), "depth_err=2"),
        (dict(live_bad={(5, k): {"i": 3}}), "game 5 line i=3 is not the game's start calibration"),
        (dict(live_bad={(5, k): {"tmax": 10 ** 12}}), "are inconsistent"),
    ]
    for kw, msg in cases:
        with pytest.raises(P.Refused, match=re.escape(msg)):
            P.a3(P.read(_log(**kw)), last_game=P.LAST_GAME)
    # no read in any measured game: the row's in-game calibration is empty (its a3 lines agree: reads_on 0)
    txt = _log(live_bad={(g, k): {"reads": 0, "scopes": 0, "ticks": 0, "tmax": 0} for g in range(17)})
    txt = re.sub(r"(a3 g=\d+ k=%s cap=32 steady=1 reads_on=)\d+" % k, r"\g<1>0", txt)
    with pytest.raises(P.Refused, match="no measured game executed a read"):
        P.a3_live(P.read(txt))
    # a live line for a row calibrated at game start
    txt = _log() + "\n[FRAME-TIME] cal i=3 why=game2 kind=a3 k=%s live=1 reads=1 scopes=1 ticks=1 tmax=1 unscoped=0 " \
        "depth_err=0" % A3_CAL[0]
    with pytest.raises(P.Refused, match="does not mark live:executed"):
        P.a3(P.read(txt), last_game=P.LAST_GAME)


def test_peer_seat_live_lines_are_read_and_required():
    # ruling FRAME-TIME-ROUND-R4: the live rows' calibration is read from both seats' logs; each is validated, d_k is
    # the larger of the two, and the command line's form withholds U without the peer's log
    k = A3_LIVE[0]
    v, _, _, dk = P.a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_ticks=60, seed=9)))
    assert abs(dk[k] - 60 * 1e6 / FREQ) < 1e-9, dk
    with pytest.raises(P.Refused, match="game 3 has 0 executed calibration lines"):
        P.a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_drop={(3, k)})))
    with pytest.raises(P.Refused, match="carries a planning"):
        P.a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_planning=k)))
    out = P.report(_log(), peer=_log(seed=9), require_peer=True)
    assert "A3 live rows (peer seat): " in out and "U not computable" not in out, out
    out = P.report(_log(), require_peer=True)
    assert "U not computable: the live rows' in-game calibration is read from both seats' logs" in out, out
    assert "VERDICT B1 withheld" in out, out
    out = P.report(_log(), peer=_log(live_drop={(3, k)}), require_peer=True)
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


def test_a3_row_withheld_by_the_build_withholds_b1():
    # ruling FRAME-TIME-ROUND-R3-A1: a row whose real reader cannot run is withheld; U is not computable, B1 withheld
    k = A3_DEP[1]
    with pytest.raises(P.Refused, match="withheld by the build.*%s" % k):
        P.a3(P.read(_log(a3_withheld=k)), last_game=P.LAST_GAME)
    out = P.report(_log(a3_withheld=k))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


@pytest.mark.parametrize("what,kw", ABSENT)
def test_each_absent_record_fails_the_run(what, kw):
    recs = P.read(_log(**kw))
    miss = P.complete(recs)
    assert any(what in m for m in miss), (what, miss)
    out = P.report(_log(**kw))
    for c in ("B1", "B2", "B3"):
        assert "VERDICT %s withheld: sitting incomplete" % c in out, (what, out)


def test_records_table_names_every_kind_the_parser_reads():
    # the sweep's own control: a line kind the parser consumes without a row in RECORDS fails here
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, "ft_parse.py"), encoding="utf-8").read()
    used = set(re.findall(r'\["kind"\] [!=]= "(\w+)"', src))
    assert {"heavy", "flushed", "between", "a3drain", "refusals", "w"} <= used, used
    assert used <= set(P.RECORDS), sorted(used - set(P.RECORDS))
    assert P.complete(P.read(_log())) == []
    assert P.complete(P.read(_log(refusals_why=("game",)))) == []
    assert P.complete(P.read(_log(refusals_why=("quit",)))) == []


def test_b3_requires_complete_records():
    # round-2 MEDIUM (ft_parse.py:611): B3 never passes on absent heavy or offthread lines
    with pytest.raises(P.Refused, match="heavy lines for spool"):
        P.b3(P.read(_log(drop_heavy={(5, "spool")})))
    with pytest.raises(P.Refused, match="offthread"):
        P.b3(P.read(_log(drop_offthread={5})))
    ok, why, ops = P.b3(P.read(_log()))
    assert ok and set(ops) == set(P.HEAVY_OPS), (why, ops)


def test_menu_check_fails_a_segment_whose_menu_line_is_absent():
    # the absent-record sweep: a dropped menu line fails the check instead of leaving its segment unjudged
    for s in (1, 9, 34):
        ok, lines, bad = P.menu_check(P.read(_menu_log(drop_menu_seg=s)))
        assert not ok and any("menu_done counts 34" in b for b in bad) and any("no menu line" in b for b in bad), (s, bad)


def test_menu_check_fails_an_excluded_or_empty_segment():
    # round-2 MEDIUM (FtClock.cs:144): menu frames are measured, never excluded as a combat point's closing frame
    for kw in (dict(excl_seg=5), dict(empty_seg=6)):
        ok, lines, bad = P.menu_check(P.read(_menu_log(**kw)))
        assert not ok and any("a menu segment measures every frame" in b for b in bad), (kw, bad)


def test_report_items_per_minute_longest_frames_and_dc_minus_ds():
    # round-1 MEDIUM 16 and round 2: B2 per minute at T_ref, the longest ON and OFF frames, dC minus dS
    assert abs(P.b2_per_minute(0.001, 2500.0) - 24.0) < 1e-12
    with pytest.raises(P.Refused):
        P.b2_per_minute(0.001, 0)
    recs = P.read(_log())
    lf = P.longest_frames(recs)
    for arm in ("ON", "OFF"):
        mx = max(q["maxF"] for q in recs if q["kind"] == "p" and q["game"] >= 1 and q["arm"] == arm)
        assert abs(lf[arm] - mx * 1000.0 / FREQ) < 1e-12 and lf[arm] > 0
    assert abs(P.dc_minus_ds(recs) - (P.dC_us(recs)[0] - P.d_key_us(recs, "sS", "ticks")[0])) < 1e-9
    out = P.report(_log())
    tr = P.t_ref(recs)
    b2 = P.hitch(recs)
    for h, v in b2.items():
        assert ("B2 H=%d ms" % h) in out and ("%.4f per minute of live combat at T_ref" % (v["ub_per_frame"] * 60e6 / tr)) in out, out
    assert "longest live frame: ON %.2f ms, OFF %.2f ms" % (lf["ON"], lf["OFF"]) in out, out
    assert "dC minus dS %.2f us per live frame" % P.dc_minus_ds(recs) in out, out


def test_report_adds_a3_to_u():
    out = P.report(_log())
    assert re.search(r"^A3 [0-9.]+ us per live frame", out, re.M), out
    assert re.search(r"\+ D_up [0-9.]+ \+ A3 [0-9.]+;", out) and "U without A3" in out, out
    m = re.search(r"^U ([0-9.]+) us = max\(0, dC_up ([-0-9.]+)\) / min\(1, e_C_lo ([0-9.]+)\) \+ K_up ([0-9.]+) "
                  r"\+ D_up ([0-9.]+) \+ A3 ([0-9.]+);", out, re.M)
    u, dc, e, k, d, a = (float(x) for x in m.groups())
    assert a > 0 and abs(u - (max(0.0, dc) / min(1.0, e) + k + d + a)) < 0.02, (u, dc, e, k, d, a)


def test_verdicts_need_the_complete_sitting():
    # round-1 HIGH 4: four measured games, or a sitting without its completion line, gets no verdict at all
    for log in (_log(games=5, complete=False), _log(games=5), _log(complete=False)):
        out = P.report(log)
        assert "SITTING INCOMPLETE" in out, out
        for c in ("B1", "B2", "B3"):
            assert "VERDICT %s withheld: sitting incomplete" % c in out, out
    assert P.complete(P.read(_log())) == []
    assert any("sitting complete" in m for m in P.complete(P.read(_log(complete=False))))
    assert any("games [5, 6" in m for m in P.complete(P.read(_log(games=5))))


def test_vr5_needs_every_expected_record():
    # round-1 HIGH 5: deleting census rows, an opened line, or one collector's opening must fail VR5
    assert P.vr5(P.read(_log()), 0, 16)[0]
    ok, bad = P.vr5(P.read(_log(drop_census=[(3, ENTRIES[5][0])])), 0, 16)
    assert not ok and any("g=3: 1 census records missing" in b for b in bad), bad
    ok, bad = P.vr5(P.read(_log(drop_census=[(g, "*") for g in range(17)])), 0, 16)
    assert not ok and sum("census records missing" in b for b in bad) == 17, bad
    ok, bad = P.vr5(P.read(_log(drop_opened=[4])), 0, 16)
    assert not ok and "g=4: 0 opened lines (needs 1)" in bad, bad
    ok, bad = P.vr5(P.read(_log(shut_ic=[2])), 0, 16)
    assert not ok and "g=2: collection not opened: ic" in bad, bad
    log = _log() + "\n[FRAME-TIME] census g=6 entry=%s comp=X shape=%s on=0 guarded=0 outside=0" % ENTRIES[0]
    ok, bad = P.vr5(P.read(log), 0, 16)
    assert not ok and any("g=6: census records duplicated" in b for b in bad), bad
    out = P.report(_log(drop_census=[(3, ENTRIES[5][0])]))
    assert "VERDICT B1 INVALID: VR5 failed" in out and "VERDICT B3 INVALID: VR5 failed" in out, out


def test_vr2_needs_every_game_start_calibration():
    # round-1 MEDIUM (ft_parse:677): deleting game 8's calibrations, or one shape's line, must fail VR2
    assert P.vr2(P.read(_log()), 16)[0]
    ok, bad = P.vr2(P.read(_log(drop_cal=[8])), 16)
    assert not ok and "game 8: 0 calibration runs (needs 1)" in bad, bad
    ok, bad = P.vr2(P.read(_log(drop_disp=[(8, SHAPES[1])])), 16)
    assert not ok and any(b.startswith("game 8: calibration 9 has no disp line for shapes") for b in bad), bad


def test_a_failed_rule_invalidates_the_claims_it_guards():
    # round-1 MEDIUM (ft_parse:894): VR6 guards B1 and B3, VR7 guards B2
    out = P.report(_log(routes=" route:GET_h/api/v1/x=1 sent:GET_h/api/v1/x=1"))
    assert "VERDICT B1 INVALID: VR6 failed" in out and "VERDICT B3 INVALID: VR6 failed" in out, out
    assert "VERDICT B2 PASS" in out, out
    out = P.report(_log() + "\n[FRAME-TIME] disarmed input=fighters pt=3.2.1")
    assert "VERDICT B1 INVALID: VR6 failed" in out and "VERDICT B3 INVALID: VR6 failed" in out, out
    log = P.read(_log())
    for r in log:
        if r["kind"] == "w" and r["arm"] == "OFF" and r.get("plant") == 1:
            r["e4"] = (3, 3)
    assert not P.vr7(log)[0]
    # VR7 failing invalidates B2 in the report, and B2 alone
    text = re.sub(r"(arm=OFF plant=1 partial=0 .*?e4=)\d+,\d+", r"\g<1>3,3", _log())
    out = P.report(text)
    assert "VERDICT B2 INVALID: VR7 failed" in out, out
    assert "VERDICT B1 INVALID" not in out and "VERDICT B3 INVALID" not in out, out


def test_predecessor_flags_a_carryover():
    recs = P.read(_log(carry_us=200.0, games=33))
    assert P.predecessor(recs)[0]
    assert not P.predecessor(P.read(_log(carry_us=0.0, games=33)))[0]


def test_vr9_bounds_span_time_by_dc():
    recs = P.read(_log())
    assert P.vr9(recs, 80.0)[0]
    assert not P.vr9(recs, 10.0)[0]


def test_b3_passes_with_heavy_work_between_points():
    ok, why, ops = P.b3(P.read(_log()))
    assert ok, why
    assert ops["pump"] == (0, 0, 0, 0)


def test_b3_flags_heavy_work_with_combat_live():
    ok, why, _ = P.b3(P.read(_log(heavy_live=2)))
    assert not ok and any("pump ran" in w for w in why), why


def test_b3_flags_heavy_work_in_a_live_frame_after_combat_ended():
    # round-1 MEDIUM (FtHeavy.cs:39): V4 3.9 forbids heavy work in a live-combat frame, the edge of one included
    ok, why, _ = P.b3(P.read(_log(heavy_edge=1)))
    assert not ok and any("enqueue ran" in w and "(edge)" in w for w in why), why


def test_b3_flags_a_hashing_job_overlapping_a_point():
    ok, why, _ = P.b3(P.read(_log(hash_at=(10 ** 6 + 5, 10 ** 6 + 10))))
    assert not ok and any("overlaps live points 0.1.1" in w for w in why), why


def test_b3_flags_a_hashing_job_never_ended():
    ok, why, _ = P.b3(P.read(_log(hash_at=(10, 0))))
    assert not ok and any("had not ended" in w for w in why), why


def test_b3_refuses_without_heavy_lines():
    recs = [r for r in P.read(_log()) if r["kind"] != "heavy"]
    with pytest.raises(P.Refused):
        P.b3(recs)


def _vr6_log(extra=()):
    base = [
        "[FRAME-TIME] refused what=queue route=e n=1",
        "[FRAME-TIME] refusals why=game1 pairs=3 queue:e=1 route:GET_10.0.0.1/api/v1/queue/poll/{n}=4 "
        "sent:GET_10.0.0.1/api/v1/mod-version=2",
        "[FRAME-TIME] refusals why=quit pairs=5 queue:e=2 closing:x=1 route:GET_10.0.0.1/api/v1/queue/poll/{n}=9 "
        "sent:GET_10.0.0.1/api/v1/mod-version=2 dispatched:GET_10.0.0.1/api/v1/mod-version=2",
    ] + list(extra)
    return "\n".join("[Info   :CompetitiveRounds] " + x for x in base)


def test_vr6_routes_read_the_quit_counts():
    ok, why, pairs, dis = P.vr6_build(P.read(_vr6_log()))
    assert ok, why
    assert pairs["route:GET_10.0.0.1/api/v1/queue/poll/{n}"] == 9 and pairs["closing:x"] == 1 and not dis


def test_vr6_routes_fail_a_route_refused_and_sent():
    log = _vr6_log(["[FRAME-TIME] refusals why=quit pairs=2 route:GET_h/api/v1/x=1 sent:GET_h/api/v1/x=1"])
    ok, why, _, _ = P.vr6_build(P.read(log))
    assert not ok and any("both refused and sent" in w for w in why), why


def test_vr6_counts_dispatches_independently():
    # round-1 MEDIUM (FtRoute.cs:97): a refused route the transport still dispatched, or an allowed route dispatched
    # more often than the classifier counted it sent, fails VR6
    log = _vr6_log(["[FRAME-TIME] refusals why=quit pairs=3 route:GET_h/api/v1/x=2 dispatched:GET_h/api/v1/x=2"])
    ok, why, _, _ = P.vr6_build(P.read(log))
    assert not ok and "route GET_h/api/v1/x dispatched 2 times, sent 0" in why, why
    log = _vr6_log(["[FRAME-TIME] refusals why=quit pairs=2 sent:GET_h/api/v1/y=1 dispatched:GET_h/api/v1/y=3"])
    ok, why, _, _ = P.vr6_build(P.read(log))
    assert not ok and "route GET_h/api/v1/y dispatched 3 times, sent 1" in why, why


def test_vr6_build_fails_on_a_disarm():
    ok, why, _, dis = P.vr6_build(P.read(_vr6_log(["[FRAME-TIME] disarmed input=fighters pt=3.2.1"])))
    assert not ok and dis == ["fighters at 3.2.1"], why


def test_vr6_build_refuses_without_a_refusals_line():
    with pytest.raises(P.Refused):
        P.vr6_build(P.read("[Info   :CompetitiveRounds] [FRAME-TIME] refused what=queue route=e n=1"))


def test_f18_reading_a_needs_a_settled_replay_per_game():
    ok, rd, why, us = P.f18(P.read(_log(games=4)))
    assert ok and rd == "A" and len(us) == 3, why
    ok, _, why, _ = P.f18(P.read(_log(games=4, replay="kept")))
    assert not ok and any("result kept" in w for w in why), why
    ok, _, why, _ = P.f18(P.read(_log(games=4, replay=None)))
    assert not ok and any("no answer_replay line" in w for w in why), why


def test_f18_reading_b_has_no_replay_and_says_unmeasured():
    ok, rd, why, us = P.f18(P.read(_log(games=4, f18="B")))
    assert ok and rd == "B" and not us, why
    log = _log(games=4, f18="B").replace("answer=unmeasured", "answer=replay", 1)
    ok, _, why, _ = P.f18(P.read(log))
    assert ok, why   # the first replaced line is game 0's settled line, which counts toward nothing
    log = _log(games=4, f18="B").replace(" answer=unmeasured", "")
    ok, _, why, _ = P.f18(P.read(log))
    assert not ok and any("without answer=unmeasured" in w for w in why), why


# ------------------------------------------------------------------ the menu self-check (FtMenu)

FREQ = 10000000          # Stopwatch ticks per second: 0.1 us per tick
FHAT = 3000000000        # cycles per second: 3000 per us


def _menu_log(segs=34, force="none", aa_us=0.0, ec=None, fhat_last=FHAT, missing_seg=None, why="complete",
              gate_flip=None, excl_seg=None, empty_seg=None, drop_menu_seg=None, drop_menu_cal=None,
              drop_terminal=False, terminal_bad=False, terminal_misplaced=False, extra_settled=False,
              drop_startup=False, startup_bad=False, menu_fhat_fail=False):
    """A menu run as FtMenu writes it: pair 0 unplanted, then the four levels in turn, base 2500 us per frame."""
    ec = ec or {}
    # round-4 MEDIUM (ft_parse.py:1219): a menu run carries two snapshots, as the build writes them: the startup one
    # (Plugin.cs FtCalib.Run("start"); FtCalib.Settled(-1, -1), before FtMenu arms) and the terminal one (FtMenu's
    # FtCalib.Settled after menu_done); extra_settled adds one inside the run, which the build never writes
    out = [] if drop_startup else [
        "[FRAME-TIME] cal i=0 why=start kind=fhat f_hat=%d spins=1/1" % FHAT,
        "[Info   :CompetitiveRounds] [FRAME-TIME] settled g=-1 seed=7 c_plant=%d W=120 vsync=0 target=-1 freq=%d"
        " hires=1 f_hat=%d force=%s clock=1 frames=0 missing_end=0 cycle_failures=0 span_depth_violations=0"
        % (80 if startup_bad else -1, FREQ, FHAT, force)]
    out.append("[FRAME-TIME] menu_armed segments=%d seg_s=10 settle_s=20 force=%s seed=7" % (segs, force))
    if extra_settled:
        out.append("[FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                   " force=%s clock=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0"
                   % (FREQ, FHAT, force))
    if menu_fhat_fail:
        out.append("[FRAME-TIME] cal i=9 kind=fhat failed: overflow")
    levels = ("0.5", "1.5", "3", "5")
    base, level, cp, cycles = 2500, "0", 0, 0
    for s in range(1, segs + 1):
        pair = (s - 1) // 2
        if (s - 1) % 2 == 0:
            arm = "ON" if pair % 2 == 0 else "OFF"
            if pair == 0:
                level, cp = "0", 0
            else:
                li = (pair - 1) % 4
                level = levels[li]
                cp = int(round(float(level) / 100 * base))
            if s == 1 or (pair >= 1 and (pair - 1) % 4 == 0):
                fh = fhat_last if s > 1 and cycles == 4 else FHAT
                if drop_menu_cal != cycles:
                    out.append("[FRAME-TIME] cal i=%d why=menu%d kind=fhat f_hat=%d spins=1/1" % (cycles, cycles, fh))
                cycles += 1
        else:
            arm = "OFF" if arm == "ON" else "ON"
        gate = 1 if force == "OFF" or (force == "none" and arm == "OFF") else 0
        if gate_flip == s:
            gate = 1 - gate
        if drop_menu_seg != s:
            out.append("[FRAME-TIME] menu seg=%d pair=%d arm=%s gate=%d level=%s c_plant=%d base_us=%d"
                       % (s, pair, arm, gate, level, cp, base if pair > 0 else -1))
        common = ((pair * 3) % 7 - 3) * 0.3        # us per frame, both arms of the pair
        j = ((pair * 7) % 5 - 2) * 0.5             # the pair's own A/A noise, mean 0 over five pairs
        f_us = base + common + (j / 2 + aa_us if arm == "ON" else -j / 2)
        n, pn = 4000, 0
        if arm == "OFF" and cp > 0:
            n, pn = 3000, 1000
        if empty_seg == s:
            n, pn = 0, 0
        e = ec.get(level, 1.0) * (1 + ((s * 13) % 5 - 2) * 0.01)
        sF = int(round(n * f_us * 10))
        sS = int(round(n * 900 * 10))
        sC = int(round(n * f_us * 3000))
        psF = int(round(pn * (f_us + cp) * 10))
        psS = int(round(pn * (900 + cp) * 10))
        psC = int(round(pn * (f_us + cp * e) * 3000))
        out.append("[FRAME-TIME] p pt=-1.%d.1 arm=%s gate=%d pred=none n=%d sF=%d sS=%d sC=%d maxF=30000 pn=%d psF=%d"
                   " psS=%d psC=%d excl=%d plant_mixed=0 windows=34 live_frames=4001 missing_end=%d span_g=0"
                   " span_gn=0 span_u=0 span_un=0 on_calls=0 guarded=0 zs=0 zl=0 t0=1 t1=2 answer=none"
                   % (s, arm, gate, n, sF, sS, sC, pn, psF, psS, psC, 1 if excl_seg == s else 0,
                      1 if missing_seg == s else 0))
    done = "[FRAME-TIME] menu_done why=%s segs=%d of=%d base_us=%d cycles=%d" % (why, segs, segs, base, cycles)
    if not terminal_misplaced:
        out.append(done)
    if not drop_terminal:
        out.append("[FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                   " force=%s clock=1 frames=99999 missing_end=%d cycle_failures=0 span_depth_violations=0"
                   % (FREQ, FHAT, force, 1 if terminal_bad else 0))
    if terminal_misplaced:
        out.append(done)
    return "\n".join(out)


def test_menu_check_passes_a_clean_run():
    ok, lines, bad = P.menu_check(P.read(_menu_log()))
    assert ok, bad
    assert any("contains 0" in ln for ln in lines), lines
    ecs = [ln for ln in lines if "menu e_C level" in ln]
    assert len(ecs) == 4 and all("e_F 1.0000, e_S 1.0000" in ln for ln in ecs), ecs
    rep = P.report(_menu_log())
    assert rep.startswith("MENU self-check") and rep.endswith("MENU PASS"), rep


def test_menu_check_fails_an_aa_shift_either_way():
    for shift in (8.0, -8.0):
        ok, lines, bad = P.menu_check(P.read(_menu_log(aa_us=shift)))
        assert not ok and any("excludes 0" in b for b in bad), (shift, bad)


def test_menu_check_fails_a_level_with_low_exposure():
    ok, lines, bad = P.menu_check(P.read(_menu_log(ec={"1.5": 0.3})))
    assert not ok and any(b.startswith("level 1.5 percent: e_C interval") for b in bad), bad
    assert any(b.startswith("level 1.5 percent: e_C 0.") and "not within 0.10 of 1" in b for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"1.5": 0.95})))
    assert ok, bad


def test_menu_check_fails_a_tenfold_exposure():
    # round-1 MEDIUM (ft_parse:771): e_C about 10 passed a lower-only bar; the declared band is two-sided
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"3": 10.0})))
    assert not ok and any(b.startswith("level 3 percent: e_C interval") for b in bad), bad
    assert any(b.startswith("level 3 percent: e_C 10") for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"3": 1.3})))
    assert not ok and "level 3 percent: e_C 1.3000 not within 0.10 of 1" in bad, bad


def test_menu_check_fails_fhat_spread_and_an_unstamped_frame():
    ok, _, bad = P.menu_check(P.read(_menu_log(fhat_last=int(FHAT * 1.05))))
    assert not ok and any("f_hat spread" in b for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(missing_seg=9)))
    assert not ok and bad == ["segment 9: missing_end=1"], bad


def test_menu_check_fails_an_aborted_run_and_a_wrong_gate():
    ok, _, bad = P.menu_check(P.read(_menu_log(why="in_room")))
    assert not ok and any("run not complete: why=in_room" in b for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(gate_flip=6)))
    assert not ok and any(b.startswith("segment 6: arm") for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(force="ON")))
    assert ok, bad


def test_menu_check_refuses_without_its_lines():
    log = _menu_log()
    with pytest.raises(P.Refused):
        P.menu_check(P.read("\n".join(ln for ln in log.splitlines() if "menu_done" not in ln)))
    with pytest.raises(P.Refused):
        P.menu_check(P.read(_menu_log(segs=6)))
    rep = P.report("\n".join(ln for ln in log.splitlines() if "kind=fhat" not in ln))
    assert rep.endswith("MENU not computable: no menu calibration line"), rep


def test_vr2_flags_span_depth_and_cycle_failures():
    # HIGH 1's mutant no_cycle_counter: a frame whose cycle read failed must fail VR2, as must a span left open
    recs = [{"kind": "p", "game": 1},
            {"kind": "settled", "g": 1, "missing_end": 0, "cycle_failures": 4, "span_depth_violations": 2}]
    ok, bad = P.vr2(recs)
    assert not ok, bad
    assert [b for b in bad if b.startswith("settled")] == ["settled g=1 cycle_failures=4",
                                                            "settled g=1 span_depth_violations=2"], bad


def test_tb_tot_from_retained_point_rows():
    # LOW 1 (METHOD-V4.md 3.10): tb_tot is computed when the record is built, from the rows the record retains
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "CombatEvidence.cs"),
               encoding="utf-8").read()
    i = src.find("var tb = g.Tb.Rows();")
    j = src.find('r["tb_tot"] = E.TbTot(tb, g.BaseChanges, g.Points)')
    assert src.count("var tb = g.Tb.Rows();") == 1 and src.count("E.TbTot(") == 1, "the tb_tot anchors moved"
    assert 0 <= i < j and src[i:j].count("\n") <= 2, "tb_tot is not built from the retained rows"
