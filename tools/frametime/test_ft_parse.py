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


def test_d_up_dispatch_is_rate_times_cost_with_the_largest_as_floor():
    du, ds, rate = P.d_up(_dup_log([2, 2, 2, 2]))
    assert rate == {"S6": 3.0}
    assert ds == [pytest.approx(0.6)] * 4         # 3 calls per frame x 0.2 us
    assert du == pytest.approx(0.6)


def test_d_up_dispatch_never_below_its_largest_calibration():
    # sixteen calibrations at 0.3 us and one at 0.9: mean + t SE is about 0.42, so the largest value binds
    du, ds, rate = P.d_up(_dup_log([1] * 16 + [3]))
    assert du == pytest.approx(0.9)


def test_d_up_dispatch_refuses_a_missing_shape():
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


def _log(carry_us=0.0, cost_us=80.0, games=17, seed=7, heavy_live=0, hash_at=(10, 20), f18="A", replay="settled"):
    """A synthetic sitting, every line as FtFrames, FtCalib and FtCensus write it. Point costs: ON adds cost_us of C
    per frame; a first-in-round ON point after an ON round end carries carry_us more (the predecessor case)."""
    import random
    rng = random.Random(seed)
    clock = [10 ** 6]
    L = ["[FRAME-TIME] settled g=-1 seed=1 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d" % (FREQ, FHAT),
         "[FRAME-TIME] plant c_plant=80 ticks=800 from=0.1.2"]
    for g in range(games):
        L.append("[FRAME-TIME] settled g=%d seed=1 c_plant=80 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                 " f18=%s answer=%s" % (g, FREQ, FHAT, f18, "replay" if f18 == "A" else "unmeasured"))
        if f18 == "A" and replay:
            L.append("[FRAME-TIME] answer_replay g=%d ticks=%d result=%s" % (g, 4000, replay))
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
                t0 = clock[0]
                t1 = t0 + int(lf * c_us * FREQ / 1e6)
                clock[0] = t1 + FREQ // 2
                L.append("[FRAME-TIME] p pt=%d.%d.%d arm=%s gate=%d pred=%s n=%d sF=%d sS=%d sC=%d maxF=%d pn=%d psF=%d "
                         "psS=0 psC=%d plant_mixed=0 windows=%d live_frames=%d missing_end=0 span_g=%d span_gn=%d "
                         "span_u=%d span_un=%d on_calls=%d guarded=%d zs=%d zl=1 t0=%d t1=%d answer=%s"
                         % (g, rnd, pt, "ON" if on else "OFF", 0 if on else 1, pred, n, sf, sf // 2, sc, sf // n * 3,
                            pn, int(pn * f_us * FREQ / 1e6), psc, (n + pn) // 120, lf, spg, lf if on else 0, spu, lf,
                            3 * lf if on else 0, gq, zs, t0, t1, "replay" if f18 == "A" else "unmeasured"))
                for w in range((n + pn) // 120):
                    plant = 1 if (not on and w % 4 == 0) else 0
                    k = 1 if rng.random() < 0.01 else 0
                    L.append("[FRAME-TIME] w pt=%d.%d.%d arm=%s plant=%d partial=0 n=120 sF=1 sS=1 sC=1 maxF=1 medF=1 "
                             "e4=%d,%d e8=0,0 e16=0,0 gc=0" % (g, rnd, pt, "ON" if on else "OFF", plant, k, k))
                pred = "ON" if on else "OFF"
        L.append("[FRAME-TIME] census g=%d entry=CE-p6 comp=CombatEvidence shape=S6 on=%d guarded=%d outside=0"
                 % (g, guarded, guarded))
        for op in ("ce_build", "se_build", "enqueue", "pump"):
            k = heavy_live if op == "pump" else 0
            L.append("[FRAME-TIME] heavy g=%d op=%s live=%d between=7 pick=1 over=1 menu=0 at_call=%d edge=0 off=0"
                     % (g, op, k, k))
        L.append("[FRAME-TIME] offthread g=%d span_off=0 hash_t0=%d hash_t1=%d" % (g, hash_at[0], hash_at[1]))
    L.append("[FRAME-TIME] refusals why=quit pairs=2 queue:e=3 sent:GET_h/api/v1/mod-version=1")
    return "\n".join("[Info   :CompetitiveRounds] " + x for x in L)


def test_report_end_to_end_reaches_a_verdict():
    out = P.report(_log())
    assert "not computable" not in out, out
    assert "VR8 zero-state PASS: game 0 (mutant) 7 of 7 rounds void" in out
    assert "VERDICT B1:" in out and "INVALID" not in out, out
    assert "VERDICT B3 PASS" in out, out
    assert "F18 reading A PASS" in out, out


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
        "[FRAME-TIME] refusals why=quit pairs=4 queue:e=2 closing:x=1 route:GET_10.0.0.1/api/v1/queue/poll/{n}=9 "
        "sent:GET_10.0.0.1/api/v1/mod-version=2",
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
              gate_flip=None):
    """A menu run as FtMenu writes it: pair 0 unplanted, then the four levels in turn, base 2500 us per frame."""
    ec = ec or {}
    out = ["[Info   :CompetitiveRounds] [FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=-1 freq=%d"
           " hires=1 f_hat=%d force=%s clock=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0"
           % (FREQ, FHAT, force),
           "[FRAME-TIME] menu_armed segments=%d seg_s=10 settle_s=20 force=%s seed=7" % (segs, force)]
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
                out.append("[FRAME-TIME] cal i=%d why=menu%d kind=fhat f_hat=%d spins=1/1" % (cycles, cycles, fh))
                cycles += 1
        else:
            arm = "OFF" if arm == "ON" else "ON"
        gate = 1 if force == "OFF" or (force == "none" and arm == "OFF") else 0
        if gate_flip == s:
            gate = 1 - gate
        out.append("[FRAME-TIME] menu seg=%d pair=%d arm=%s gate=%d level=%s c_plant=%d base_us=%d"
                   % (s, pair, arm, gate, level, cp, base if pair > 0 else -1))
        common = ((pair * 3) % 7 - 3) * 0.3        # us per frame, both arms of the pair
        j = ((pair * 7) % 5 - 2) * 0.5             # the pair's own A/A noise, mean 0 over five pairs
        f_us = base + common + (j / 2 + aa_us if arm == "ON" else -j / 2)
        n, pn = 4000, 0
        if arm == "OFF" and cp > 0:
            n, pn = 3000, 1000
        e = ec.get(level, 1.0) * (1 + ((s * 13) % 5 - 2) * 0.01)
        sF = int(round(n * f_us * 10))
        sS = int(round(n * 900 * 10))
        sC = int(round(n * f_us * 3000))
        psF = int(round(pn * (f_us + cp) * 10))
        psS = int(round(pn * (900 + cp) * 10))
        psC = int(round(pn * (f_us + cp * e) * 3000))
        out.append("[FRAME-TIME] p pt=-1.%d.1 arm=%s gate=%d pred=none n=%d sF=%d sS=%d sC=%d maxF=30000 pn=%d psF=%d"
                   " psS=%d psC=%d plant_mixed=0 windows=34 live_frames=4001 missing_end=%d span_g=0 span_gn=0"
                   " span_u=0 span_un=0 on_calls=0 guarded=0 zs=0 zl=0 t0=1 t1=2 answer=none"
                   % (s, arm, gate, n, sF, sS, sC, pn, psF, psS, psC, 1 if missing_seg == s else 0))
    out.append("[FRAME-TIME] menu_done why=%s segs=%d of=%d base_us=%d cycles=%d" % (why, segs, segs, base, cycles))
    out.append("[FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
               " force=%s clock=1 frames=99999 missing_end=0 cycle_failures=0 span_depth_violations=0"
               % (FREQ, FHAT, force))
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
    assert not ok and bad == ["level 1.5 percent: e_C lower end %s below 0.5" % bad[0].split()[-3]], bad
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"1.5": 0.8})))
    assert ok, bad


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
    assert not ok and bad == ["settled g=1 cycle_failures=4", "settled g=1 span_depth_violations=2"], bad


def test_tb_tot_from_retained_point_rows():
    # LOW 1 (METHOD-V4.md 3.10): tb_tot is computed when the record is built, from the rows the record retains
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "CombatEvidence.cs"),
               encoding="utf-8").read()
    i = src.find("var tb = g.Tb.Rows();")
    j = src.find('r["tb_tot"] = E.TbTot(tb, g.BaseChanges, g.Points)')
    assert src.count("var tb = g.Tb.Rows();") == 1 and src.count("E.TbTot(") == 1, "the tb_tot anchors moved"
    assert 0 <= i < j and src[i:j].count("\n") <= 2, "tb_tot is not built from the retained rows"
