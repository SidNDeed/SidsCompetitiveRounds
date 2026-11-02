"""Tests for ft_parse.py. Golden values were computed with dither_control v5 (md5 894b010c), whose claims C10 to
C21 they stand behind; each port test pins the parser to the control's own function on the same input.
Run: python -I -B -m pytest tools/frametime/test_ft_parse.py -q"""
import os
import sys

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
    ok, bad = P.vr5(recs)
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
    ok, bad = P.vr5([_pt(1, guarded=40), _pt(0, span_g=900, span_gn=40, on_calls=40)])
    assert ok and bad == []


def test_vr5_flags_gated_span_time_at_a_gated_point():
    ok, bad = P.vr5([_pt(1, guarded=40, span_g=3)])
    assert not ok and bad == ["pt=1.1.1 gated: span_g=3 span_gn=0 on_calls=0"]


def test_vr5_flags_guarded_returns_at_an_open_point():
    ok, bad = P.vr5([_pt(0, guarded=1)])
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


def _dup_log(costs_by_cal, guarded=3000, off_frames=1000, freq=10000000):
    recs = [{"kind": "settled", "g": g, "freq": freq} for g in range(0, 3)]
    recs.append({"kind": "p", "game": 1, "round": 1, "gate": 1, "live_frames": off_frames, "arm": "OFF"})
    recs.append({"kind": "census", "g": 1, "shape": "S6", "guarded": guarded})
    for i, c in enumerate(costs_by_cal):
        # c: closed-path ticks per call at 10 MHz; two batches of n = 1000
        recs.append({"kind": "cal", "i": i, "why": "game%d" % i, "ckind": "disp", "shape": "S6", "n": 1000,
                     "u": "1000,1000", "p": "%d,%d" % (1000 + 1000 * c, 1000 + 1000 * c)})
    return recs


def test_d_up_is_rate_times_cost_with_the_largest_as_floor():
    du, ds, rate = P.d_up(_dup_log([2, 2, 2, 2]))
    assert rate == {"S6": 3.0}
    assert ds == [pytest.approx(0.6)] * 4         # 3 calls per frame x 0.2 us
    assert du == pytest.approx(0.6)


def test_d_up_never_below_its_largest_calibration():
    # sixteen calibrations at 0.3 us and one at 0.9: mean + t SE is about 0.42, so the largest value binds
    du, ds, rate = P.d_up(_dup_log([1] * 16 + [3]))
    assert du == pytest.approx(0.9)


def test_d_up_refuses_a_missing_shape():
    recs = _dup_log([2, 2])
    recs.append({"kind": "census", "g": 1, "shape": "S1", "guarded": 5})
    with pytest.raises(P.Refused):
        P.d_up(recs)


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


def _log(carry_us=0.0, cost_us=80.0, games=17, seed=7):
    """A synthetic sitting, every line as FtFrames, FtCalib and FtCensus write it. Point costs: ON adds cost_us of C
    per frame; a first-in-round ON point after an ON round end carries carry_us more (the predecessor case)."""
    import random
    rng = random.Random(seed)
    L = ["[FRAME-TIME] settled g=-1 seed=1 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d" % (FREQ, FHAT),
         "[FRAME-TIME] plant c_plant=80 ticks=800 from=0.1.2"]
    for g in range(games):
        L.append("[FRAME-TIME] settled g=%d seed=1 c_plant=80 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                 % (g, FREQ, FHAT))
        L.append("[FRAME-TIME] cal i=%d why=game%d kind=disp shape=S6 n=100000 u=1000000,1000000 p=1300000,1300000"
                 % (g + 1, g))
        L.append("[FRAME-TIME] cal i=%d why=game%d kind=disp shape=S1 n=100000 u=1000000,1000000 p=1200000,1200000"
                 % (g + 1, g))
        base = 2600.0 * (1 + 0.05 * rng.random())
        pred = "none"
        guarded = 0
        offl = 0
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
                L.append("[FRAME-TIME] p pt=%d.%d.%d arm=%s gate=%d pred=%s n=%d sF=%d sS=%d sC=%d maxF=%d pn=%d psF=%d "
                         "psS=0 psC=%d plant_mixed=0 windows=%d live_frames=%d missing_end=0 span_g=%d span_gn=%d "
                         "span_u=%d span_un=%d on_calls=%d guarded=%d zs=%d zl=1"
                         % (g, rnd, pt, "ON" if on else "OFF", 0 if on else 1, pred, n, sf, sf // 2, sc, sf // n * 3,
                            pn, int(pn * f_us * FREQ / 1e6), psc, (n + pn) // 120, lf, spg, lf if on else 0, spu, lf,
                            3 * lf if on else 0, gq, zs))
                for w in range((n + pn) // 120):
                    plant = 1 if (not on and w % 4 == 0) else 0
                    k = 1 if rng.random() < 0.01 else 0
                    L.append("[FRAME-TIME] w pt=%d.%d.%d arm=%s plant=%d partial=0 n=120 sF=1 sS=1 sC=1 maxF=1 medF=1 "
                             "e4=%d,%d e8=0,0 e16=0,0 gc=0" % (g, rnd, pt, "ON" if on else "OFF", plant, k, k))
                pred = "ON" if on else "OFF"
        L.append("[FRAME-TIME] census g=%d entry=CE-p6 comp=CombatEvidence shape=S6 on=%d guarded=%d outside=0"
                 % (g, guarded, guarded))
    return "\n".join("[Info   :CompetitiveRounds] " + x for x in L)


def test_report_end_to_end_reaches_a_verdict():
    out = P.report(_log())
    assert "not computable" not in out, out
    assert "VR8 zero-state PASS: game 0 (mutant) 7 of 7 rounds void" in out
    assert "VERDICT B1:" in out and "INVALID" not in out, out


def test_predecessor_flags_a_carryover():
    recs = P.read(_log(carry_us=200.0, games=33))
    assert P.predecessor(recs)[0]
    assert not P.predecessor(P.read(_log(carry_us=0.0, games=33)))[0]


def test_vr9_bounds_span_time_by_dc():
    recs = P.read(_log())
    assert P.vr9(recs, 80.0)[0]
    assert not P.vr9(recs, 10.0)[0]
