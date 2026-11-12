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
    st = "[FRAME-TIME] settled g=1 vsync=0 target=-1"
    held = FPSCAP_HOLD_LINE + "\n" + st
    assert P.vr1(recs, held, 2650.0)[0]
    assert not P.vr1(recs, held, 1e6 / 144)[0]                     # T_ref sits on 144 FPS
    assert not P.vr1([{"kind": "settled", "g": 1, "vsync": 1, "target": -1}], held, 2650.0)[0]
    # ruling FRAME-TIME-ROUND-R6-A3: the hold line is required, and no other [FPSCAP] line up to the last settled line
    ok, bad = P.vr1(recs, st, 2650.0)
    assert not ok and bad == ["no '[FPSCAP] held by frame-time calibration' line: the hold is not proven reached"], bad
    ok, bad = P.vr1(recs, FPSCAP_HOLD_LINE + "\n[FPSCAP] engaged unfocused cap: target=120\n" + st, 2650.0)
    assert not ok and bad == ["an [FPSCAP] line other than the hold is present: [FPSCAP] engaged unfocused cap:"
                              " target=120"], bad
    # after the sitting's last settled line (the armfile removed) the hold's release and a cap are outside it
    ok, bad = P.vr1(recs, held + "\n[FPSCAP] hold released\n[FPSCAP] engaged unfocused cap: target=120", 2650.0)
    assert ok, bad


def _mp_recs():
    """Four games of two OFF points each: per point six unplanted windows whose means alternate +-100 us of C about a
    base (sample SD 100 x sqrt(1.2) us) and two planted ones; game g's e values 0.1 x g."""
    fh = 3000000000                      # 3000 cycles per us
    recs = [{"kind": "plant", "c_plant": 80}]
    for g in range(1, 5):
        recs.append({"kind": "settled", "g": g, "f_hat": fh})
        for pt in (1, 2):
            n, pn = 720, 240
            base = 2000.0 * 3000           # cycles per frame
            e = 0.1 * g
            recs.append({"kind": "p", "game": g, "round": 1, "point": pt, "arm": "OFF", "n": n, "pn": pn,
                         "sC": base * n, "psC": (base + e * 80 * 3000) * pn})
            for i in range(6):
                m = base + (1 if i % 2 == 0 else -1) * 100.0 * 3000
                recs.append({"kind": "w", "game": g, "round": 1, "point": pt, "arm": "OFF", "plant": 0,
                             "partial": 0, "n": 120, "sC": m * 120})
            for i in range(2):
                recs.append({"kind": "w", "game": g, "round": 1, "point": pt, "arm": "OFF", "plant": 1,
                             "partial": 0, "n": 120, "sC": base * 120})
    return recs


def test_match_power_reports_w_the_model_and_g_needed():
    # ruling FRAME-TIME-ROUND-R6-A3.3 (2a): report only; w measured, the margin against the planning input, the G
    # VR2 needs at the 1.6 margin and at the observed per-game SD
    import math
    import statistics
    out = P.match_power(_mp_recs())
    w = 100.0 * math.sqrt(1.2)
    assert out[0] == "match power: w %.1f us over 8 OFF points (planning 293.2 us, measured margin %.2f)" % (w, w / 293.2), out
    s = 1.6 * w * math.sqrt(1 / 2 + 1 / 6) / math.sqrt(2) / 80

    def need(x):
        return next(k for k in range(4, 100000) if (P.t_q(P.Z_END, k // 2 - 1) + 1.2816) * x / math.sqrt(k) <= 0.5)
    assert out[1] == "match power: model per-game SE %.3f at margin 1.6 over 4 games: G needed %d" % (s, need(s)), out
    so = statistics.stdev([0.1, 0.2, 0.3, 0.4])
    assert out[2] == "match power: observed per-game SD of e_C %.3f over 4 games: G needed %d" % (so, need(so)), out
    assert P.match_power([r for r in _mp_recs() if r["kind"] != "w"]) == [
        "match power: no OFF point with three complete unplanted window lines, w not measured"]


def test_report_carries_the_match_power_lines():
    # every match sitting's report carries match_power beside VR2 (ruling FRAME-TIME-ROUND-R6-A3.3 (2a))
    rep = _report(_log()).splitlines()
    i = [k for k, ln in enumerate(rep) if ln.startswith("VR2 e_C_lo ")]
    assert len(i) == 1 and rep[i[0] + 1].startswith("match power: w "), rep


def test_vr4_bar():
    assert P.vr4(30.0, 2650.0) and not P.vr4(40.0, 2650.0)


FREQ, FHAT = 10000000, 3000000000


ENTRIES = P.expected_entries()
SHAPES = sorted(set(s for e, s in ENTRIES))
A3_DEP = [r[0] for r in P.a3_spec() if r[2] == "dependent"]
# rulings FRAME-TIME-ROUND-R4 and R5: the live rows (calibrated in game); since R5 retired the scratch A3, every
# dependent row is live and no row is calibrated at game start
A3_LIVE = [r[0] for r in P.a3_spec() if r[2] == "dependent" and r[4] == P.LIVE_PROOF]
A3_CAL = [k for k in A3_DEP if k not in A3_LIVE]
# the six rows ruling R4 named first (a sample the per-row controls loop over)
LIVE_SIX = ["CE_Pos", "CE_Recent", "CE_gun_scalars", "CE_capture", "SE_scalars", "IC_game"]
A3_DRAIN = [r[0] for r in P.a3_spec() if r[2] == "drained"]
# the plugin files holding the FtA3 registrations (mut_parse copies each)
A3_SITES = ["CombatEvidence.cs", "SeatEvidence.cs", "IdentityClockEvidence.cs", "HitEvidence.cs", "PoisonSync.cs",
            "CardDrawEvidence.cs", "PeerBuild.cs"]


FPSCAP_HOLD_LINE = "[Info   :Competitive ROUNDS] [FPSCAP] held by frame-time calibration"
# FtE.RegisterAll's census summary, as plugin/FtEntries.cs writes it (registered, expected, missing, duplicates)
CENSUS_SUMMARY = "[FRAME-TIME] census registered=%d expected=%d missing=%d duplicates=%d"


def _log(carry_us=0.0, cost_us=80.0, games=17, seed=7, heavy_live=0, hash_at=(10, 20), f18="A", replay="settled", heavy_edge=0,
         drop_cal=(), drop_disp=(), drop_opened=(), shut_ic=(), drop_census=(), complete=True, routes="",
         drop_a3=(), drop_a3cal=(), a3_peak=None, drop_a3drain=(), a3_dirty=None, drop_heavy=(), drop_offthread=(),
         drop_flushed=(), drop_between=(), drop_w=(), refusals_why=("game", "quit"), a3_starts=None, a3_cal_p=None,
         drop_p=(), drop_replay=(), replay_bad=None, drop_counters=(), counters_bad=None, point_missing_end=None,
         a3_withheld=None, a3zero_lines=None, live_planning=None, live_beside=None, live_drop=(), live_bad=None,
         live_ticks=30, live_peak=None, fhat_fail=(), fhat_extra_fail=(), fhat_zero=(), disp_fail=None,
         live_game=None, live_tail=None, census_summary=None):
    """A synthetic sitting, every line as FtFrames, FtCalib, FtCensus and FtDrive write it. Point costs: ON adds
    cost_us of C per frame; a first-in-round ON point after an ON round end carries carry_us more (the predecessor
    case). The drop_* and shut_ic arguments remove or spoil records for the completeness controls. census_summary
    is the census summary lines FtE.RegisterAll writes (None: the one clean line; a list of lines replaces it)."""
    import random
    rng = random.Random(seed)
    clock = [10 ** 6]
    if census_summary is None:
        census_summary = [CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 0, 0)]
    L = list(census_summary)
    L += ["[FRAME-TIME] settled g=-1 seed=1 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d" % (FREQ, FHAT),
         "%s" % FPSCAP_HOLD_LINE,
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
            per = (live_game or {}).get(g, live_ticks)
            tk = rd * (per * 3 if live_peak == (g, k) else per)
            v = dict(i=g + 1, reads=rd, scopes=rd // 2, ticks=tk, tmax=4 * live_ticks, unscoped=0, depth_err=0)
            v.update((live_bad or {}).get((g, k), {}))
            L.append("[FRAME-TIME] cal i=%d why=game%d kind=a3 k=%s live=1 reads=%d scopes=%d ticks=%d tmax=%d "
                     "unscoped=%d depth_err=%d%s" % (v["i"], g, k, v["reads"], v["scopes"], v["ticks"], v["tmax"],
                                                     v["unscoped"], v["depth_err"], (live_tail or {}).get((g, k), "")))
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
    # the integrator's marker rule (11 Nov): a measurement input carries the FrameTime build marker exactly once
    return "\n".join("[Info   :CompetitiveRounds] " + x for x in ["[FRAME-TIME] " + P.MARK_FT] + L)



_PEER = {}


def _peer_text():
    """The other seat's log (round-5 MEDIUM, ft_parse.py:1643: every verdict needs both seats' logs); a clean sitting
    of its own seed. A test about the peer passes its own."""
    if "t" not in _PEER:
        _PEER["t"] = _log(seed=9)
    return _PEER["t"]


def _report(text, **kw):
    kw.setdefault("peer", _peer_text())
    return P.report(text, **kw)


def _a3(recs, **kw):
    kw.setdefault("peer_recs", P.read(_peer_text()))
    return P.a3(recs, **kw)

def test_report_end_to_end_reaches_a_verdict():
    out = _report(_log())
    assert "not computable" not in out, out
    assert "SITTING complete: games 0 to 16" in out, out
    assert "VR8 zero-state PASS: game 0 (mutant) 7 of 7 rounds void" in out
    assert re.search(r"^VERDICT B1 (PASS|SID|FAIL|WITHHELD): U [0-9.]+ us against T_ref", out, re.M), out
    assert "INVALID" not in out and "withheld" not in out, out
    assert "VERDICT B2 PASS" in out and "VERDICT B3 PASS" in out, out
    assert "F18 reading A PASS" in out, out


def test_report_carries_the_specified_figures():
    # round-1 MEDIUM (ft_parse:793): the classification and the figures V4 section 0 and 3.3 to 3.9 report
    out = _report(_log())
    for want in ("U without D_up", "dF ", "dS ", "dP (process CPU, all threads)", "e_F ", "e_S ", "trend: d_g slope",
                 "last four games' mean", "UPKEEP spans per live frame: ON", "format M's own stamps",
                 "between-point spans after ON points", "conditional: U bounds the NET", "PASS <= 3, SID <= 5"):
        assert want in out, (want, out)
    assert P.classify(2.9, 100, 9, 0) == "PASS" and P.classify(4.0, 100, 1, 3.1) == "SID" \
        and P.classify(5.1, 100, 1, 5.05) == "FAIL"


def test_a3_is_the_largest_per_game_window_rate_times_the_calibrated_difference():
    # ruling FRAME-TIME-ROUND-R1-A1 (route D): A3 = sum over dependent structures of r_k_max x d_k
    recs = P.read(_log())
    v, ds, rate, dk = _a3(recs, last_game=P.LAST_GAME)
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
    v2, ds2, rate2, dk2 = _a3(recs, last_game=P.LAST_GAME)
    games = P.games_of(recs)
    peak = [r for r in recs if r["kind"] == "a3" and r["k"] == k and r["g"] == 3][0]["reads_win"]
    r3 = peak / sum(q["live_frames"] for q in games[3] if q["gate"] == 0)
    assert r3 > 2 and abs(rate2[k] - r3) < 1e-12 and v2 > v, (rate2, r3)


def test_a3_refuses_a_missing_line_or_calibration():
    # ruling A1 part 3: the refill window counted from absent records cannot pass, nor a missing calibration
    k = A3_DEP[0]
    # every dependent row is live since ruling R5, so the executed-reads cross-check meets the missing line first
    with pytest.raises(P.Refused, match="game 5 executed reads [0-9]+, the game's a3 line counts \[\]"):
        _a3(P.read(_log(drop_a3={(5, k)})), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="game 7 has 0 executed calibration lines"):
        _a3(P.read(_log(live_drop={(7, k)})), last_game=P.LAST_GAME)
    out = _report(_log(drop_a3={(5, k)}))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


def test_a3_drained_rows_refuse_a_missing_line_or_a_point_that_started_holding_entries():
    # ruling A1 part 3: a drained row's zero is checked by the build, never assumed
    assert A3_DRAIN, "the inventory names no drained row"
    k = A3_DRAIN[0]
    v, ds, rate, dk = _a3(P.read(_log()), last_game=P.LAST_GAME)
    assert k not in rate and k not in dk
    with pytest.raises(P.Refused, match="a3drain lines"):
        _a3(P.read(_log(drop_a3drain={(4, k)})), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="nonempty"):
        _a3(P.read(_log(a3_dirty=(6, k))), last_game=P.LAST_GAME)
    out = _report(_log(a3_dirty=(6, k)))
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
        _a3(recs, spec=[])
    with pytest.raises(P.Refused, match="needs a reason"):
        _a3(recs, spec=[("X", "S99", "zero", " ", "sweep:no-live-write")])
    assert _a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins", "sweep:no-live-write")])[0] == 0.0


def test_a3_zero_row_without_its_proof_reference_fails_the_parse():
    # ruling FRAME-TIME-ROUND-R2 (1), default-deny: a zero row carries its proof (sweep:... or probe:...), a drained
    # row its probe (probe:a3drain), and a row of the old four-field shape is refused
    recs = P.read(_log())
    for proof in ("", " ", "sweep:", "because", "probe"):
        with pytest.raises(P.Refused, match="proof reference"):
            _a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins", proof)])
    with pytest.raises(P.Refused, match="probe:a3drain"):
        _a3(recs, spec=[("X", "S99", "drained", "emptied between points", "sweep:no-live-write")])
    with pytest.raises(P.Refused, match="name, survivor id, kind, reason, proof"):
        _a3(recs, spec=[("X", "S99", "zero", "a fixed loop over all bins")])
    # round-3 MEDIUM (ft_parse.py:540): a probe token is accepted only with its records
    with pytest.raises(P.Refused, match="probe:a3zero needs one a3zero line"):
        _a3(recs, spec=[("X", "S99", "zero", "r", "probe:a3zero")])
    # the shipped inventory: every zero row names its proof, every drained row its probe
    for r in P.a3_spec():
        assert len(r) == 5, r
        if r[2] == "zero":
            assert re.fullmatch(r"(sweep|probe):\S+", r[4]), r
        if r[2] == "drained":
            assert r[4] == "probe:a3drain", r
    _a3(recs, last_game=P.LAST_GAME)


def test_a3_every_games_calibration_is_required_and_a_dropped_one_never_passes():
    # round-2 HIGH (ft_parse.py:495), Codex's own control, on the executed lines (ruling FRAME-TIME-ROUND-R5): game 8's
    # reads cost most, so game 8 sets every d_k and B1 is FAIL; dropping game 8's executed lines (every row's, or one
    # row's) must withhold the verdict, never fall back to the cheaper games
    big = {8: 2000}
    out = _report(_log(live_game=big))
    # re-pinned (the integrator's ruling on the hand-back (2)): U is in the FAIL band, but A3 is a charge whose lower
    # end is 0, so the lower bound does not clear 5 percent and the band is WITHHELD
    m8 = re.search(r"^VERDICT B1 WITHHELD: U ([0-9.]+) us against T_ref ([0-9.]+) us", out, re.M)
    assert m8 and float(m8.group(1)) > 0.05 * float(m8.group(2)), out
    for drop in ({(8, k) for k in A3_DEP}, {(8, A3_DEP[0])}):
        out2 = _report(_log(live_game=big, live_drop=drop))
        assert "VERDICT B1 withheld" in out2, out2
        assert not re.search(r"^VERDICT B1 (PASS|SID)", out2, re.M), out2
    with pytest.raises(P.Refused, match="game 8"):
        _a3(P.read(_log(live_game=big, live_drop={(8, k) for k in A3_DEP})), last_game=P.LAST_GAME)
    # a row's executed line names game 8's start calibration, which is gone
    with pytest.raises(P.Refused, match="game 8 line i=9 is not the game's start calibration"):
        _a3(P.read(_log(drop_cal={8})), last_game=P.LAST_GAME)
    # the default reads the sitting's games too: no caller can skip the per-game rule by omitting last_game
    with pytest.raises(P.Refused, match="game 8"):
        _a3(P.read(_log(live_game=big, live_drop={(8, k) for k in A3_DEP})))


def test_a3_drained_starts_equal_the_games_point_count():
    # round-2 MEDIUM: a drained row's probe ran at every point start of the game, no fewer and no more
    k = A3_DRAIN[0]
    for st in (13, 15, 1):
        with pytest.raises(P.Refused, match="point starts"):
            _a3(P.read(_log(a3_starts=(4, k, st))), last_game=P.LAST_GAME)
    _a3(P.read(_log(a3_starts=(4, k, 14))), last_game=P.LAST_GAME)


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
    ("census_summary", "sitting", None, INCOMPLETE),
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
    # the integrator's marker rule (11 Nov): a measurement input without its build marker is refused by name
    ("build", "marker", None, "MARKER-ABSENT"),
    # SHARED.md: the mark cost boot line; without it the transition overhead is named not computable
    ("mark", "b11", None, r"^B11 class transitions: not computable: 0 mark cost lines"),
    # ruling R6-A3.11.147 (5): the five V6 boot lines; a missing one counts as its control out of range (sitting V)
    ("alloc", "v6", None, r"^V6 WITHHELD seat a: .*the counter's pin differs or is not read \(0 'alloc' lines"),
    ("scope", "v6", None, r"^V6 WITHHELD seat a: .*control K2 out of range \(0 'scope plant' lines.*R-SCOPE's census "
                          r"line out of range \(0 'scope census' lines"),
    ("nest", "v6", None, r"^V6 WITHHELD seat a: .*control K3 out of range \(0 'nest plant' lines"),
    ("photon", "v6", None, r"^V6 WITHHELD seat a: .*R-SCOPE's patches line out of range \(0 'photon patches' lines"),
    # P1's V6 emitter (via the integrator, 12 Nov): a sitting log without its controls line is refused (K-MUTANT)
    ("controls", "v6", None, "REFUSED:K-MUTANT: the sitting log V:a carries 0 controls lines"),
    # the follow-up to ruling .149, A: a sitting-V log without its ledger line withholds B1, the tap's state not read
    ("ledger", "v6", None, r"^V6 WITHHELD seat a: .*the disk-log tap: 0 'ledger' lines \(needs exactly 1\)"),
    # ruling R6-A3.11.151 (3): a sitting-V log without its attach line withholds B1, naming ATTACH
    ("attach", "v6", None, r"^V6 WITHHELD seat a: .*ATTACH: 0 'attach' lines \(needs exactly 1 per boot\)"),
)
# the kinds whose PRESENCE is the event (their absence is the normal case): test_failure_events_make_the_run_incomplete
# and test_vr6_build_fails_on_a_disarm are their controls; chk_attach_guard is attach_failed's
RECORD_EVENTS = {"disarmed", "game", "start", "clock", "attach_failed"}


def _a3zero_case():
    k = A3_DEP[0]
    spec = [(n, s, ("zero" if n == k else kd), (w or "r"), ("probe:a3zero" if n == k else pr))
            for n, s, kd, w, pr in P.a3_spec()]
    drop = {(g, k) for g in range(17)}
    return _log(drop_a3=drop, live_drop=drop, a3zero_lines={k: 0}), spec


@pytest.mark.parametrize("kind,fixture,where,want", DELETIONS)
def test_deleting_each_record_kind_withholds(kind, fixture, where, want):
    if fixture == "sitting":
        base = _log()
        assert re.search(r"^VERDICT B1 WITHHELD: U", _report(base), re.M)
        log, n = _drop_kind(base, kind, where)
        assert n >= 1, kind
        assert re.search(want, _report(log), re.M), (kind, _report(log))
    elif fixture == "a3zero":
        base, spec = _a3zero_case()
        _a3(P.read(base), spec=spec, peer_recs=P.read(base))
        log, n = _drop_kind(base, kind, where)
        assert n >= 1
        with pytest.raises(P.Refused, match=want):
            _a3(P.read(log), spec=spec, peer_recs=P.read(log))
    elif fixture == "b11":
        base = _b11_text(_one_run_games(), _c2_model)
        assert re.search(r"^B11 class transitions \(in the charge", P.report(base, peer=base), re.M)
        log, n = _drop_kind(base, kind, where)
        assert n == 1
        assert re.search(want, P.report(log, peer=log), re.M), P.report(log, peer=log)
    elif fixture == "v6":
        base = _v_text()
        assert "V6 WITHHELD seat a: none" in _on(P, base, base)[0]
        log, n = _drop_kind(base, kind, where)
        assert n >= 1, kind
        if want.startswith("REFUSED:"):
            with pytest.raises(P.Refused, match=re.escape(want[len("REFUSED:"):])):
                _on(P, log, log)
        else:
            out = "\n".join(_on(P, log, log)[0])
            assert re.search(want, out, re.M), (kind, out)
    elif fixture == "marker":
        base = _log()
        assert re.search(r"^VERDICT B1 WITHHELD: U", _report(base), re.M)
        log, n = _drop_kind(base, kind, where)
        assert n == 1
        with pytest.raises(P.MarkerRefused, match=want):
            _report(log)
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


def _plugin_src():
    """The emitter's source in this tree (plugin/*.cs, its comment lines dropped), each string constant printed after
    '[FRAME-TIME] ' (FtArm.DLL_PROP) put in place: what the build prints."""
    plug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin")
    src = ""
    for fn in sorted(os.listdir(plug)):
        if fn.endswith(".cs"):
            src += open(os.path.join(plug, fn), encoding="utf-8").read() + "\n"
    src = re.sub(r"(?m)^\s*//.*$", "", src)
    consts = dict(re.findall(r'const string (\w+) = "([^"]*)";', src))

    def put(mm):
        assert mm.group(1) in consts, "'[FRAME-TIME] ' + %s: not a string constant" % mm.group(1)
        return '"[FRAME-TIME] ' + consts[mm.group(1)]
    return re.sub(r'"\[FRAME-TIME\] "\s*\+\s*(\w+)\s*\+\s*"', put, src)


# a [FRAME-TIME] line's lead in the source: the literal after '[FRAME-TIME] ' up to its first hole
SOURCE_LEAD = re.compile(r'"\[FRAME-TIME\] ((?:[^"\\{]|\\.)*)')
# ruling R6-A3.11.151 (3): the attach line and its warning are printed by plugin/FtAttach.cs and Plugin.cs's call of it
# (P1b, commit aa6d99e9 on claude/ft-b11-p1), merged after this tree. Until FtAttach.cs is in the plugin folder the
# source prints neither, and the two source tests below hold that, taking the two leads and the kind as printed; once
# it is there, they must be printed and are read like every other form
ATTACH_LEADS = ("attach n=", "attach report failed: ")


def _attach_merged():
    return os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin", "FtAttach.cs"))


def test_every_emitted_kind_is_read_or_named():
    # every "[FRAME-TIME] <kind>" the build writes is a RECORDS kind or named in EMITTED_UNREAD with its reason; no kind
    # the parser reads is called unread; every RECORDS kind but a3zero (no build writes it today) is written (ruling
    # R6-A3.11.149 (6) 9: no kind is excluded, the emitter being merged)
    here = os.path.dirname(os.path.abspath(__file__))
    plug_src = _plugin_src()
    emitted = set(re.findall(r'"\[FRAME-TIME\] (\w+)', plug_src))
    if not _attach_merged():
        assert "attach" not in emitted, "FtAttach.cs is not in the plugin folder, yet the source prints an attach line"
        emitted.add("attach")
    src = open(os.path.join(here, "ft_parse.py"), encoding="utf-8").read()
    # a FAILURE_EVENTS row on a whole kind (head None) reads the kind; one scoped by its head reads only that failure
    # line, so its kind's other lines may be unread (ruling R6-A3.11.92 (3): churn), the reason naming the row
    used = set(re.findall(r'\["kind"\] [!=]= "(\w+)"', src)) | set(k for k, h, _ in P.FAILURE_EVENTS if h is None)
    assert emitted <= set(P.RECORDS) | set(P.EMITTED_UNREAD), sorted(emitted - set(P.RECORDS) - set(P.EMITTED_UNREAD))
    assert not set(P.EMITTED_UNREAD) & used, sorted(set(P.EMITTED_UNREAD) & used)
    for k, h, _ in P.FAILURE_EVENTS:
        assert k in P.RECORDS or (k in P.EMITTED_UNREAD and "FAILURE_EVENTS" in P.EMITTED_UNREAD[k]), (k, h)
    # every RAW_FAILURES text is one the build writes
    for t, _ in P.RAW_FAILURES:
        assert ('"%s' % t) in plug_src, t
    assert not set(P.EMITTED_UNREAD) & set(P.RECORDS)
    assert set(P.EMITTED_UNREAD) <= emitted, sorted(set(P.EMITTED_UNREAD) - emitted)
    # a SUBKINDS record is a line of an emitted kind told apart by its first word: its parent is emitted, it is not
    assert all(parent in emitted for parent, _ in P.SUBKINDS.values()), P.SUBKINDS
    assert set(P.RECORDS) - emitted == {"a3zero"} | set(P.SUBKINDS), sorted(set(P.RECORDS) - emitted)


def test_forms_are_every_line_form_the_emitter_prints():
    # ruling R6-A3.11.149 (6) 9 and 10: the source's leads are exactly FORMS' leads (a form the source prints and the
    # parser does not know, or a FORMS row no source prints, fails here); a row whose fields FORMS fixes carries the
    # keys of its one source statement, in printed order (a key marked '?' is printed by a separate literal, which the
    # source holds); the markers' rows are MARK_FT's and MARK_REF's texts
    src = _plugin_src()
    leads = set(SOURCE_LEAD.findall(src))
    merged = _attach_merged()
    if not merged:
        assert not leads & set(ATTACH_LEADS), sorted(leads & set(ATTACH_LEADS))
        leads |= set(ATTACH_LEADS)
    have = set(lead for lead, _, _ in P.FORMS)
    assert leads == have, (sorted(leads - have), sorted(have - leads))
    for lead, pat, keys in P.FORMS:
        if keys is None or (lead in ATTACH_LEADS and not merged):
            continue
        at = [mm.start() for mm in re.finditer(re.escape('"[FRAME-TIME] ' + lead), src)]
        assert len(at) == 1, (lead, len(at))
        stmt = src[at[0]:src.index(";", at[0])]
        got = [k for lit in re.findall(r'"((?:[^"\\]|\\.)*)"', stmt) for k in re.findall(r"(?:^| )(\w+)=", lit)]
        assert got == [k for k in keys if not k.endswith("?")], (lead, got, keys)
        for k in keys:
            if k.endswith("?"):
                assert ('" %s=' % k[:-1]) in src, (lead, k)
    assert (P.MARK_FT, P.MARK_REF) == ("build variant=FrameTime", "build variant=FrameTimeRef SCR_FT_REF=NOCOLLECTORS")


def test_p_line_sock_p95_may_print_na_and_heap_is_an_integer():
    # ruling R6-A3.11.149 (6) 10: FtUpload prints sock_p95=NA with no sock sample (plugin/FtUpload.cs:333-345), and
    # FtFrames prints heap= as an integer (plugin/FtFrames.cs:279)
    text = _b11_text(_one_run_games(), _flat, p_extra=B11_P_EXTRA.replace("sock_p95=0", "sock_p95=NA"))
    assert [r for r in P.read(text) if r["kind"] == "p"][0]["sock_p95"] is None
    assert [r for r in P.read(_b11_text(_one_run_games(), _flat)) if r["kind"] == "p"][0]["heap"] == 50000000
    with pytest.raises((P.Refused, P.RecordRefused)):
        P.read(_b11_text(_one_run_games(), _flat, p_extra=B11_P_EXTRA.replace("heap=50000000", "heap=NA")))


FAILURE_LINES = ("[Warning:CompetitiveRounds] [FRAME-TIME] game over failed: boom",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] game start failed: boom",
                 # ruling R6-A3.11.100 (3)(b): GameStateWatcher's MatchEnded hooks
                 "[Warning:CompetitiveRounds] [FRAME-TIME] game end failed: boom",
                 # ruling R6-A3.11.101 (2)(e): FtSchedule.GameStart in a menu=1 process
                 "[Warning:CompetitiveRounds] [FRAME-TIME] game start failed: menu=1 process",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] start failed: boom",
                 "[Warning:CompetitiveRounds] [FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate 1)",
                 # ruling R6-A3.11.92 (3)
                 "[Warning:CompetitiveRounds] [FRAME-TIME] churn freeze failed: boom")
# the failure warnings _LINE cannot match, read in the raw lines (RAW_FAILURES); ruling R6-A3.11.92 (3)
RAW_FAILURE_LINES = ("[Warning:CompetitiveRounds] [FRAME-TIME] FT-ROOM read failed: boom",
                     "[Warning:CompetitiveRounds] [FRAME-TIME] FT-GATE report failed: boom")


def test_failure_events_make_the_run_incomplete():
    # round-4 sweep of every kind the build writes: a failure warning is never ignored
    for ln in FAILURE_LINES:
        log = _log()
        i = log.index("[FRAME-TIME] flushed g=9")
        log = log[:i] + ln + "\n" + log[i:]
        assert any("failure event" in m for m in P.complete(P.read(log))), ln
        assert re.search(INCOMPLETE, _report(log), re.M), ln
        ok, _, bad = P.menu_check(P.read(_menu_log() + "\n" + ln))
        assert not ok and any("failure event" in b for b in bad), (ln, bad)
    # the control the other way: the clock's ordinary line is not a failure
    ok_line = "[Info   :CompetitiveRounds] [FRAME-TIME] clock installed freq=10000000 hires=1"
    assert P.complete(P.read(_log() + "\n" + ok_line)) == []
    assert P.menu_check(P.read(_menu_log() + "\n" + ok_line))[0]


def test_f18_failure_guards_b1():
    # round-3 MEDIUM (ft_parse.py:1461): game 8's replay failing makes F18 FAIL, and B1 is INVALID, never PASS or SID
    out = _report(_log(replay_bad=8))
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


def test_menu_check_names_an_entry_patch_that_did_not_attach():
    # ruling FRAME-TIME-ROUND-R6-A1: the entry table's readiness lines (not built before the plugin's own patches, the
    # counts line once built) are no failure; an entry calibration that failed after the signal (a patch that did not
    # attach, lesson #83) fails the menu run, named by its shape
    lines = _menu_log().splitlines()
    ready = ["[FRAME-TIME] cal i=0 why=start kind=entries built=0 own_patches=not-applied",
             "[FRAME-TIME] cal i=-1 why=patches kind=entries built=1 own_owner=com.competitiverounds.mod"
             " own_targets=40 entries=40 errors=0"]
    ok, _, bad = P.menu_check(P.read("\n".join(lines[:1] + ready + lines[1:])))
    assert ok, bad
    fail = ["[FRAME-TIME] cal i=1 why=menu0 kind=disp shape=HE7 failed: InvalidOperationException: HeFooPatch is not"
            " attached: no target patched by com.competitiverounds.mod (lesson #83)"]
    ok, _, bad = P.menu_check(P.read("\n".join(lines[:1] + ready + fail + lines[1:])))
    assert not ok and any("failure warnings" in b and "menu0 disp HE7" in b for b in bad), bad


def test_a3_probe_proofs_need_their_records_and_contrary_ones_fail():
    # round-3 MEDIUM (ft_parse.py:540): probe:a3zero accepted only with consistent a3zero lines; an unknown token, a
    # contrary record, or live writes counted for a zero row are refused
    k = A3_DEP[0]
    spec = [(n, s, ("zero" if n == k else kd), (w or "r"), ("probe:a3zero" if n == k else pr))
            for n, s, kd, w, pr in P.a3_spec()]
    drop = {(g, k) for g in range(17)}
    recs = P.read(_log(drop_a3=drop, live_drop=drop))
    with pytest.raises(P.Refused, match="probe:a3zero needs one a3zero line"):
        _a3(recs, spec=spec, peer_recs=recs)
    good = P.read(_log(drop_a3=drop, live_drop=drop, a3zero_lines={k: 0}))
    _a3(good, spec=spec, peer_recs=good)
    bad = P.read(_log(drop_a3=drop, live_drop=drop, a3zero_lines={k: 1}))
    with pytest.raises(P.Refused, match="written=1"):
        _a3(bad, spec=spec, peer_recs=good)
    spec2 = [(n, s, kd, w, ("sweep:anything" if n == k else pr)) for n, s, kd, w, pr in spec]
    with pytest.raises(P.Refused, match="names no evidence"):
        _a3(good, spec=spec2, peer_recs=good)
    spec3 = [(n, s, kd, w, ("sweep:no-live-write" if n == k else pr)) for n, s, kd, w, pr in spec]
    with pytest.raises(P.Refused, match="contrary evidence"):
        _a3(P.read(_log()), spec=spec3)


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
    out = _report(_log(fhat_fail={5}))
    assert "VR2 instrument FAIL" in out and re.search(r"^VERDICT B1 (INVALID|withheld)", out, re.M), out


def test_live_rows_take_their_executed_in_game_calibration():
    # rulings FRAME-TIME-ROUND-R4 and R5: every dependent row is calibrated by its executed in-game lines (the scratch
    # A3 is retired): d_k is the largest per-game ticks / reads, and A3 is the one sum r_k_max x d_k
    assert sorted(A3_LIVE) == sorted(A3_DEP) and len(A3_DEP) == 32 and not A3_CAL and set(LIVE_SIX) <= set(A3_LIVE)
    recs = P.read(_log())
    d, det = P.a3_live(recs)
    want = 30 * 1e6 / FREQ
    assert sorted(d) == sorted(A3_LIVE) and all(abs(d[k] - want) < 1e-9 for k in A3_LIVE), d
    assert all(len(det[k]) == P.LAST_GAME + 1 for k in A3_LIVE), det
    v, ds, rate, dk = _a3(recs, last_game=P.LAST_GAME)
    assert all(abs(dk[k] - want) < 1e-9 for k in A3_LIVE)
    # the per-game maximum: a game whose reads cost three times as much sets d_k
    k = A3_LIVE[0]
    d2, _ = P.a3_live(P.read(_log(live_peak=(4, k))))
    assert abs(d2[k] - 3 * want) < 1e-9, d2
    v2 = _a3(P.read(_log(live_peak=(4, k))), last_game=P.LAST_GAME)[0]
    assert v2 > v
    out = _report(_log())
    assert "A3 live rows (this seat): " in out and "U not computable" not in out, out


def test_a_dependent_row_is_calibrated_only_by_its_in_game_lines():
    # ruling FRAME-TIME-ROUND-R5 (round 5's HIGH, CombatEvidence.cs:3217, FtCalB5c): the scratch A3 is retired for every
    # dependent row; an inventory that gives a dependent row any proof but live:executed (the scratch path's "") is
    # refused, whichever row it is, and the shipped inventory marks all 32 live
    recs = P.read(_log())
    for k in (A3_DEP[0], "CE_B5c", A3_DEP[-1]):
        for proof in ("", "scratch", "sweep:no-live-write"):
            spec = [(n, s, kd, w, (proof if n == k else pr)) for n, s, kd, w, pr in P.a3_spec()]
            with pytest.raises(P.Refused, match="A3 row %s .*the scratch A3 is retired" % k):
                _a3(recs, spec=spec, last_game=P.LAST_GAME)
    assert len(A3_DEP) == 32 and all(r[4] == P.LIVE_PROOF for r in P.a3_spec() if r[2] == "dependent")
    # the positive control: the shipped inventory with both seats' executed lines
    _a3(recs, last_game=P.LAST_GAME)


def test_live_row_planning_or_withheld_line_never_passes_as_executed():
    # ruling FRAME-TIME-ROUND-R4 (R3-A1 stands): a planning value or a withheld line can never stand in for a live
    # row's executed calibration, in place of it or beside it
    for k in LIVE_SIX:
        with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a planning" % k):
            _a3(P.read(_log(live_planning=k)), last_game=P.LAST_GAME)
    k = A3_LIVE[1]
    with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a planning" % k):
        _a3(P.read(_log(live_beside=k)), last_game=P.LAST_GAME)
    with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a withheld" % k):
        _a3(P.read(_log(a3_withheld=k)), last_game=P.LAST_GAME)
    for kw in (dict(live_planning=k), dict(live_beside=k), dict(a3_withheld=k)):
        out = _report(_log(**kw))
        assert "U not computable" in out and "VERDICT B1 withheld" in out, (kw, out)


def test_live_marked_stand_in_line_is_refused_in_either_seat():
    # round-5 MEDIUM (ft_parse.py:637), the reviewer's probe: a peer CE_Pos line carrying live=1 together with
    # withheld=1, or "failed: control", or the planning fields, passed the live branch as an executed line. One
    # predicate now refuses the failure, withholding and planning fields whatever the live marker says, in this seat's
    # log and in the peer's, and B1 is withheld.
    k = "CE_Pos"
    clean = P.read(_log())
    for tail, what in ((" withheld=1", "withheld"), (" failed: control", "failed"),
                       (" n=1000 u=100000,100000 p=130000,130000", "planning")):
        bad = _log(live_tail={(5, k): tail})
        assert "live=1" in [x for x in bad.splitlines() if "why=game5 kind=a3 k=%s " % k in x][0]
        with pytest.raises(P.Refused, match="live row %s: cal i=6 carries a %s" % (k, what)):
            P.a3_live(P.read(bad))
        with pytest.raises(P.Refused, match="live row %s: cal i=6 carries a %s" % (k, what)):
            P.a3(clean, last_game=P.LAST_GAME, peer_recs=P.read(bad))
        with pytest.raises(P.Refused, match="live row %s: cal i=6 carries a %s" % (k, what)):
            P.a3(P.read(bad), last_game=P.LAST_GAME, peer_recs=clean)
        out = P.report(_log(), peer=bad)
        assert "U not computable" in out and "VERDICT B1 withheld" in out, (tail, out)
    # the positive control: the clean executed lines pass in both seats
    d, _ = P.a3_live(clean)
    assert k in d
    P.a3(clean, last_game=P.LAST_GAME, peer_recs=P.read(_peer_text()))


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
            _a3(P.read(_log(**kw)), last_game=P.LAST_GAME)
    # no read in any measured game: the row's in-game calibration is empty (its a3 lines agree: reads_on 0)
    txt = _log(live_bad={(g, k): {"reads": 0, "scopes": 0, "ticks": 0, "tmax": 0} for g in range(17)})
    txt = re.sub(r"(a3 g=\d+ k=%s cap=32 steady=1 reads_on=)\d+" % k, r"\g<1>0", txt)
    with pytest.raises(P.Refused, match="no measured game executed a read"):
        P.a3_live(P.read(txt))
    # a live line for a row the inventory does not mark live (since R5 no dependent row is calibrated at game start,
    # so the subject is a drained row, which carries no a3 calibration line at all)
    txt = _log() + "\n[FRAME-TIME] cal i=3 why=game2 kind=a3 k=%s live=1 reads=1 scopes=1 ticks=1 tmax=1 unscoped=0 " \
        "depth_err=0" % A3_DRAIN[0]
    with pytest.raises(P.Refused, match="does not mark live:executed"):
        _a3(P.read(txt), last_game=P.LAST_GAME)


def test_peer_seat_live_lines_are_read_and_required():
    # ruling FRAME-TIME-ROUND-R4: the live rows' calibration is read from both seats' logs; each is validated, d_k is
    # the larger of the two. Round-5 MEDIUM (ft_parse.py:1643): no verdict-producing API takes one seat's log, and no
    # parameter bypasses that
    k = A3_LIVE[0]
    v, _, _, dk = _a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_ticks=60, seed=9)))
    assert abs(dk[k] - 60 * 1e6 / FREQ) < 1e-9, dk
    with pytest.raises(P.Refused, match="game 3 has 0 executed calibration lines"):
        _a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_drop={(3, k)})))
    with pytest.raises(P.Refused, match="carries a planning"):
        _a3(P.read(_log()), last_game=P.LAST_GAME, peer_recs=P.read(_log(live_planning=k)))
    out = P.report(_log(), peer=_log(seed=9))
    assert "A3 live rows (peer seat): " in out and "U not computable" not in out, out
    assert re.search(r"^VERDICT B1 (PASS|SID|FAIL|WITHHELD): U", out, re.M), out
    # the reviewer's control: report on one complete seat's log alone is Refused, and so is A3 from one seat's log
    with pytest.raises(P.Refused, match="a verdict needs both seats' logs"):
        P.report(_log())
    with pytest.raises(P.Refused, match="no peer log was given"):
        P.a3(P.read(_log()), last_game=P.LAST_GAME)
    import inspect
    assert "require_peer" not in inspect.signature(P.report).parameters
    with pytest.raises(TypeError):
        P.report(_log(), require_peer=False)
    out = P.report(_log(), peer=_log(live_drop={(3, k)}))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


def test_a3_row_withheld_by_the_build_withholds_b1():
    # ruling FRAME-TIME-ROUND-R3-A1: a row whose real reader cannot run is withheld; U is not computable, B1 withheld
    k = A3_DEP[1]
    with pytest.raises(P.Refused, match="live row %s: cal i=\\d+ carries a withheld" % k):
        _a3(P.read(_log(a3_withheld=k)), last_game=P.LAST_GAME)
    out = _report(_log(a3_withheld=k))
    assert "U not computable" in out and "VERDICT B1 withheld" in out, out


@pytest.mark.parametrize("what,kw", ABSENT)
def test_each_absent_record_fails_the_run(what, kw):
    recs = P.read(_log(**kw))
    miss = P.complete(recs)
    assert any(what in m for m in miss), (what, miss)
    out = _report(_log(**kw))
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
    out = _report(_log())
    tr = P.t_ref(recs)
    b2 = P.hitch(recs)
    for h, v in b2.items():
        assert ("B2 H=%d ms" % h) in out and ("%.4f per minute of live combat at T_ref" % (v["ub_per_frame"] * 60e6 / tr)) in out, out
    assert "longest live frame: ON %.2f ms, OFF %.2f ms" % (lf["ON"], lf["OFF"]) in out, out
    assert "dC minus dS %.2f us per live frame" % P.dc_minus_ds(recs) in out, out


def test_report_adds_a3_to_u():
    out = _report(_log())
    assert re.search(r"^A3 [0-9.]+ us per live frame", out, re.M), out
    assert re.search(r"\+ D_up [0-9.]+ \+ A3 [0-9.]+;", out) and "U without A3" in out, out
    m = re.search(r"^U ([0-9.]+) us = max\(0, dC_up ([-0-9.]+)\) / min\(1, e_C_lo ([0-9.]+)\) \+ K_up ([0-9.]+) "
                  r"\+ D_up ([0-9.]+) \+ A3 ([0-9.]+);", out, re.M)
    u, dc, e, k, d, a = (float(x) for x in m.groups())
    assert a > 0 and abs(u - (max(0.0, dc) / min(1.0, e) + k + d + a)) < 0.02, (u, dc, e, k, d, a)


def test_verdicts_need_the_complete_sitting():
    # round-1 HIGH 4: four measured games, or a sitting without its completion line, gets no verdict at all
    for log in (_log(games=5, complete=False), _log(games=5), _log(complete=False)):
        out = _report(log)
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
    out = _report(_log(drop_census=[(3, ENTRIES[5][0])]))
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
    out = _report(_log(routes=" route:GET_h/api/v1/x=1 sent:GET_h/api/v1/x=1"))
    assert "VERDICT B1 INVALID: VR6 failed" in out and "VERDICT B3 INVALID: VR6 failed" in out, out
    assert "VERDICT B2 PASS" in out, out
    out = _report(_log() + "\n[FRAME-TIME] disarmed input=fighters pt=3.2.1")
    assert "VERDICT B1 INVALID: VR6 failed" in out and "VERDICT B3 INVALID: VR6 failed" in out, out
    log = P.read(_log())
    for r in log:
        if r["kind"] == "w" and r["arm"] == "OFF" and r.get("plant") == 1:
            r["e4"] = (3, 3)
    assert not P.vr7(log)[0]
    # VR7 failing invalidates B2 in the report, and B2 alone
    text = re.sub(r"(arm=OFF plant=1 partial=0 .*?e4=)\d+,\d+", r"\g<1>3,3", _log())
    out = _report(text)
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


@pytest.mark.parametrize("result", ["skipped_quit", "skipped_live", "skipped_absent"])
def test_f18_fails_a_skipped_replay_that_records_missing_counts(result):
    # ruling R6-A3.11.100 (3)(a)1: the quit flush (or the settle cap in a live frame) writes FtReplay.Skip's line, one
    # answer_replay line for the game: records_missing() is satisfied by it and f18() fails it
    good = _log(games=4)
    old = re.search(r"\[FRAME-TIME\] answer_replay g=2 ticks=\d+ result=settled", good).group(0)
    log = good.replace(old, "[FRAME-TIME] answer_replay g=2 ticks=0 result=" + result)
    assert log != good and log.count("answer_replay g=2 ") == 1
    ok, _, why, _ = P.f18(P.read(log))
    assert not ok and "game 2 replay result %s" % result in why, why
    assert not [m for m in P.records_missing(P.read(log), last_game=3) if "answer_replay" in m]
    assert not [m for m in P.records_missing(P.read(good), last_game=3) if "answer_replay" in m]
    dropped = good.replace(old + "\n", "")
    assert [m for m in P.records_missing(P.read(dropped), last_game=3) if "answer_replay" in m]
    assert P.f18(P.read(good))[0]


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
              drop_startup=False, startup_bad=False, menu_fhat_fail=False, armfile=True, hold=True,
              hold_after_seg=None, cap_lines=(), closing_target=-1, slow_from=None, unplanted_seg=None,
              levels=("3", "3", "5"), ec_noise=None):
    """A menu run as FtMenu writes it: pair 0 unplanted, then the levels in turn (the pattern 3, 3, 5 by default),
    base 2500 us per frame.
    The frame-rate state (ruling FRAME-TIME-ROUND-R6-A3): the startup snapshot carries armfile=1 and the hold line
    follows it (hold_after_seg moves it after that segment's lines); cap_lines are (segment, [FPSCAP] text) pairs
    written after that segment; closing_target is the terminal snapshot's target; slow_from divides every later
    segment's frames by 24 (the deep-idle collapse); unplanted_seg gives that OFF segment no planted frame."""
    caps = {}
    for s_, t_ in cap_lines:
        caps.setdefault(s_, []).append("[Info   :Competitive ROUNDS] " + t_)
    if hold and hold_after_seg is not None:
        caps.setdefault(hold_after_seg, []).append(FPSCAP_HOLD_LINE)
    ec = ec or {}
    # round-4 MEDIUM (ft_parse.py:1219): a menu run carries two snapshots, as the build writes them: the startup one
    # (Plugin.cs FtCalib.Run("start"); FtCalib.Settled(-1, -1), before FtMenu arms) and the terminal one (FtMenu's
    # FtCalib.Settled after menu_done); extra_settled adds one inside the run, which the build never writes
    out = [] if drop_startup else [
        "[FRAME-TIME] cal i=0 why=start kind=fhat f_hat=%d spins=1/1" % FHAT,
        "[Info   :CompetitiveRounds] [FRAME-TIME] settled g=-1 seed=7 c_plant=%d W=120 vsync=0 target=-1 freq=%d"
        " hires=1 f_hat=%d%s force=%s clock=1 frames=0 missing_end=0 cycle_failures=0 span_depth_violations=0"
        % (80 if startup_bad else -1, FREQ, FHAT, " armfile=1" if armfile else "", force)]
    if hold and hold_after_seg is None:
        out.append(FPSCAP_HOLD_LINE)
    out.append("[FRAME-TIME] menu_armed segments=%d seg_s=10 settle_s=20 force=%s seed=7" % (segs, force))
    if extra_settled:
        out.append("[FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d"
                   " force=%s clock=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0"
                   % (FREQ, FHAT, force))
    if menu_fhat_fail:
        out.append("[FRAME-TIME] cal i=9 kind=fhat failed: overflow")
    base, level, cp, cycles = 2500, "0", 0, 0
    for s in range(1, segs + 1):
        pair = (s - 1) // 2
        if (s - 1) % 2 == 0:
            arm = "ON" if pair % 2 == 0 else "OFF"
            if pair == 0:
                level, cp = "0", 0
            else:
                li = (pair - 1) % len(levels)
                level = levels[li]
                cp = int(round(float(level) / 100 * base))
            if s == 1 or (pair >= 1 and (pair - 1) % len(levels) == 0):
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
        if unplanted_seg == s:
            n, pn = 4000, 0
        if slow_from is not None and s >= slow_from:
            n, pn = n // 24, pn // 24
        if empty_seg == s:
            n, pn = 0, 0
        e = ec.get(level, 1.0) * (1 + ((s * 13) % 5 - 2) * (ec_noise or {}).get(level, 0.01))
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
        out += caps.get(s, [])
    done = "[FRAME-TIME] menu_done why=%s segs=%d of=%d base_us=%d cycles=%d" % (why, segs, segs, base, cycles)
    if not terminal_misplaced:
        out.append(done)
    if not drop_terminal:
        out.append("[FRAME-TIME] settled g=-1 seed=7 c_plant=-1 W=120 vsync=0 target=%d freq=%d hires=1 f_hat=%d"
                   " force=%s clock=1 frames=99999 missing_end=%d cycle_failures=0 span_depth_violations=0"
                   % (closing_target, FREQ, FHAT, force, 1 if terminal_bad else 0))
    if terminal_misplaced:
        out.append(done)
    return "\n".join([LOG_PREFIX + "[FRAME-TIME] " + P.MARK_FT] + out)


def test_menu_check_passes_a_clean_run():
    ok, lines, bad = P.menu_check(P.read(_menu_log()))
    assert ok, bad
    assert any("contains 0" in ln for ln in lines), lines
    ecs = [ln for ln in lines if "menu e_C level" in ln]
    assert len(ecs) == 2 and all("e_F 1.0000, e_S 1.0000" in ln for ln in ecs), ecs
    # the planning model is reported, never judged; a log without window lines says w was not measured
    assert "menu power: no complete unplanted window lines, w not measured" in lines, lines
    rep = _report(_menu_log())
    assert rep.startswith("MENU self-check") and "\nMENU PASS\n" in rep and rep.endswith("MENU FRAMERATE PASS"), rep


def test_menu_check_names_an_off_segment_with_no_planted_window():
    # ruling FRAME-TIME-ROUND-R6-A3 (2): an OFF segment with a planted level and no planted window is a named MENU
    # FAIL reason by number, never a silent drop from its level's count; every such segment's windows are reported
    ok, lines, bad = P.menu_check(P.read(_menu_log(unplanted_seg=3)))
    assert not ok and "OFF segments with a planted level and no planted window: 3 (level 3, 34 windows, n 4000)" \
        in bad, bad
    assert any(ln.startswith("menu e_C level 3 percent:") and ln.endswith("10 segments; e_F 1.0000, e_S 1.0000")
               for ln in lines), lines
    w = [ln for ln in lines if ln.startswith("menu OFF segments with a planted level")]
    assert len(w) == 1 and " 3:3:34:0 " in w[0] and " 6:3:34:1000 " in w[0] and " 7:5:34:1000 " in w[0], w
    ok, lines, bad = P.menu_check(P.read(_menu_log()))
    assert ok and not any("no planted window" in b for b in bad), bad


def test_menu_framerate_passes_the_held_run():
    ok, lines, bad = P.menu_framerate(_menu_log())
    assert ok, bad
    assert "menu frame rate: opening settled target=-1 vsync=0, closing target=-1 vsync=0" in lines, lines
    # the release of a cap the mod owned on the hold's first tick is admitted
    ok, _, bad = P.menu_framerate(_menu_log(cap_lines=[(1, "[FPSCAP] released (restored target=-1 vsync=0, "
                                                           "focused=False)")]))
    assert ok, bad


def test_menu_framerate_c5_shape_fails_on_each_named_reason():
    # the 16:53 sitting's shape (ruling FRAME-TIME-ROUND-R6-A3 C5): no hold, the unfocused cap then deep idle, the
    # closing target 15, the segments collapsed; each reason named, the missing hold stopping none of the others
    log = _menu_log(hold=False, closing_target=15, slow_from=10,
                    cap_lines=[(5, "[FPSCAP] engaged unfocused cap: target=120 (baseline target=-1 vsync=0)"),
                               (8, "[FPSCAP] deep idle (60s+ unfocused, out of room): target=15")])
    ok, _, bad = P.menu_framerate(log)
    assert not ok
    assert "no '[FPSCAP] held by frame-time calibration' line: the hold is not proven reached" in bad, bad
    assert any(b.startswith("an [FPSCAP] line between the arm and menu_done") and "deep idle (60s+" in b
               for b in bad), bad
    assert any(b.startswith("an [FPSCAP] line between the arm and menu_done") and "engaged unfocused cap" in b
               for b in bad), bad
    assert "the closing settled line's target=15 vsync=0 differs from the opening one's target=-1 vsync=0" in bad, bad
    assert any(b.startswith("segments below one tenth of the first segment's 4000 frames: 10 (166)") for b in bad), bad
    # each reason alone
    ok, _, bad = P.menu_framerate(_menu_log(cap_lines=[(8, "[FPSCAP] deep idle (60s+ unfocused, out of room): target=15")]))
    assert not ok and len(bad) == 1 and bad[0].startswith("an [FPSCAP] line between the hold and menu_done"), bad
    ok, _, bad = P.menu_framerate(_menu_log(cap_lines=[(8, "[FPSCAP] hold released")]))
    assert not ok and len(bad) == 1 and "hold released" in bad[0], bad
    ok, _, bad = P.menu_framerate(_menu_log(closing_target=15))
    assert not ok and len(bad) == 1 and bad[0].startswith("the closing settled line's target=15"), bad
    ok, _, bad = P.menu_framerate(_menu_log(slow_from=30))
    assert not ok and len(bad) == 1 and bad[0].startswith("segments below one tenth"), bad
    ok, _, bad = P.menu_framerate(_menu_log(hold=False))
    assert not ok and len(bad) == 1 and "the hold is not proven reached" in bad[0], bad
    ok, _, bad = P.menu_framerate(_menu_log(armfile=False))
    assert not ok and bad == ["no startup settled line with armfile=1 (the arm)"], bad
    # a cap line before the hold, and a hold after menu_done
    ok, _, bad = P.menu_framerate(_menu_log(hold_after_seg=4, cap_lines=[(2, "[FPSCAP] engaged unfocused cap: "
                                                                             "target=120")]))
    assert not ok and any(b.startswith("an [FPSCAP] line between the arm and the hold") for b in bad), bad
    ok, _, bad = P.menu_framerate(_menu_log(hold=False) + "\n" + FPSCAP_HOLD_LINE)
    assert not ok and len(bad) == 1 and bad[0].startswith("the hold line (log line ") and "is not between" in bad[0], bad


def test_menu_check_fails_an_aa_shift_either_way():
    for shift in (8.0, -8.0):
        ok, lines, bad = P.menu_check(P.read(_menu_log(aa_us=shift)))
        assert not ok and any("excludes 0" in b for b in bad), (shift, bad)


def test_menu_check_fails_a_level_with_low_exposure():
    # decision 21'' (ruling FRAME-TIME-ROUND-R6-A3.2): an interval that does not contain 1 fails at either level
    ok, lines, bad = P.menu_check(P.read(_menu_log(ec={"5": 0.3})))
    assert not ok and bad == [b for b in bad if b.startswith("level 5 percent: e_C interval 0.")] and \
        any(b.endswith("does not contain 1") for b in bad), bad
    ok, lines, bad = P.menu_check(P.read(_menu_log(ec={"3": 0.3})))
    assert not ok and any(b.startswith("level 3 percent: e_C interval 0.") and b.endswith("does not contain 1")
                          for b in bad), bad
    assert any(b.startswith("level 3 percent: e_C_lo 0.") and b.endswith("below 0.5") for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"5": 1.0})))
    assert ok, bad


def test_menu_check_e_c_lo_bar_at_3_percent_only():
    # decision 21'': e_C_lo >= 0.5 is judged at 3 percent (VR2's criterion rehearsed); a wide interval that contains 1
    # and excludes 0 passes at 5 percent with its lower end below 0.5, and fails at 3 percent on the lower end alone
    ok, lines, bad = P.menu_check(P.read(_menu_log(ec_noise={"3": 0.5})))
    assert not ok and len(bad) == 1 and bad[0].startswith("level 3 percent: e_C_lo 0.") and \
        bad[0].endswith("below 0.5"), (bad, lines)
    ok, lines, bad = P.menu_check(P.read(_menu_log(segs=58, ec_noise={"5": 0.5})))
    lo5 = [ln for ln in lines if ln.startswith("menu e_C level 5 percent:")]
    assert ok and lo5 and float(lo5[0].split("lower end ")[1].split(",")[0]) < 0.5, (bad, lo5)
    # an interval that contains 0 fails on the exclusion, named
    ok, lines, bad = P.menu_check(P.read(_menu_log(ec={"5": 0.2}, ec_noise={"5": 4.0})))
    assert not ok and any(b.startswith("level 5 percent: e_C interval") and b.endswith("does not exclude 0")
                          for b in bad), (bad, lines)


def test_menu_check_names_a_level_outside_the_pattern():
    # a log from a build that still plants 0.5 and 1.5 percent is not this check's
    ok, _, bad = P.menu_check(P.read(_menu_log(levels=("0.5", "1.5", "3", "5"))))
    assert not ok and "segments planted at levels outside 3, 5: 0.5, 1.5" in bad, bad


def test_menu_check_fails_a_tenfold_exposure():
    # round-1 MEDIUM (ft_parse:771): e_C about 10 passed a lower-only bar; the declared band is two-sided
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"3": 10.0})))
    assert not ok and any(b.startswith("level 3 percent: e_C interval 9.") and b.endswith("does not contain 1")
                          for b in bad), bad
    ok, _, bad = P.menu_check(P.read(_menu_log(ec={"3": 1.3})))
    assert not ok and any(b.startswith("level 3 percent: e_C interval 1.2") and b.endswith("does not contain 1")
                          for b in bad), bad


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
    rep = _report("\n".join(ln for ln in log.splitlines() if "kind=fhat" not in ln))
    assert "MENU not computable: no menu calibration line" in rep.splitlines(), rep


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


# ------------------------------------------------------------------ the census summary and the required-keys table

FT_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ft_parse.py")
LOG_PREFIX = "[Info   :CompetitiveRounds] "
# a token that makes each REQUIRED_KEYS condition hold (a new conditional row needs its token here)
WHEN_TOKENS = {"span_g present": "span_g=1", "t0 present": "t0=1", "partial=0": "partial=0",
               "kind=disp|span, not failed": "kind=disp", "kind=fhat, not failed": "kind=fhat",
               "result=settled": "result=settled", "after=ON": "after=ON", "c_plant>0": "c_plant=5",
               "live present": "live=1", "not ref=NA": None,
               # the row's own keys make its condition hold, so dropping any one of them leaves it holding
               "a B11 field present": None}
SAMPLE_VALUES = {"pt": "1.1.1", "e4": "0,0", "e8": "0,0", "e16": "0,0", "u": "1,1", "p": "1,1", "partial": "0",
                 "q": ",".join(["1"] * 10), "r": ",".join(["1"] * 10), "qn": ",".join(["12"] * 10),
                 "tok": "log:0,0,0,0,0,0,0", "unit": "P13", "pred": "none", "wu": "log:0:0"}


def _summary_log(lines):
    return "\n".join(LOG_PREFIX + x for x in lines)


def test_census_summary_is_its_own_kind_and_passes_beside_census_lines():
    # the bug: the summary line was read as a census record without g, and complete() stopped with KeyError 'g'
    r = P.parse_line(LOG_PREFIX + CENSUS_SUMMARY % (44, 44, 0, 0))
    assert r["kind"] == "census_summary" and r["head"] == "registered=44", r
    assert P.parse_line(LOG_PREFIX + "[FRAME-TIME] census g=3 entry=E comp=X shape=S on=1 guarded=0 outside=0")["kind"] \
        == "census"
    recs = P.read(_log())
    assert sum(1 for q in recs if q["kind"] == "census_summary") == 1
    assert all("g" in q for q in recs if q["kind"] == "census")
    assert sum(1 for q in recs if q["kind"] == "census") == 17 * len(ENTRIES)
    ok, reading, bad = P.census_summary(recs)
    assert ok and not bad, bad
    assert reading == "1 line [registered=%d expected=%d missing=0 duplicates=0]; entries.py derives %d" % (
        len(ENTRIES), len(ENTRIES), len(ENTRIES)), reading
    assert P.complete(recs) == []


N_E = len(ENTRIES)
SUMMARY_FAILS = [
    ("registered not expected", [CENSUS_SUMMARY % (N_E - 1, N_E, 0, 0)], "differs from expected"),
    ("expected not derived", [CENSUS_SUMMARY % (N_E + 1, N_E + 1, 0, 0)], "entries gate_specs/entries.py derives"),
    ("missing 1", [CENSUS_SUMMARY % (N_E, N_E, 1, 0)], "missing=1 (needs 0)"),
    ("duplicates 1", [CENSUS_SUMMARY % (N_E, N_E, 0, 1)], "duplicates=1 (needs 0)"),
    ("two lines", [CENSUS_SUMMARY % (N_E, N_E, 0, 0)] * 2, "2 census summary lines (needs exactly 1)"),
    ("absent", [], "0 census summary lines (needs exactly 1)"),
]


@pytest.mark.parametrize("name,lines,why", SUMMARY_FAILS, ids=[x[0].replace(" ", "_") for x in SUMMARY_FAILS])
def test_census_summary_failing_forms_fail_the_check(name, lines, why):
    ok, _, bad = P.census_summary(P.read(_summary_log(lines)))
    assert not ok and [b for b in bad if why in b] and len(bad) == 1, bad
    # complete() carries the miss, so the verdicts are withheld as for every completeness miss
    assert [m for m in P.complete(P.read(_log(census_summary=lines))) if why in m], name


def test_census_summary_failure_withholds_the_verdicts_on_either_seat():
    bad_lines = [CENSUS_SUMMARY % (N_E, N_E, 1, 0)]
    out = _report(_log(census_summary=bad_lines))
    assert "CENSUS summary this seat FAIL" in out and "SITTING INCOMPLETE: " in out, out
    assert "VERDICT B1 withheld: sitting incomplete" in out, out
    out = _report(_log(), peer=_log(seed=9, census_summary=bad_lines))
    assert "CENSUS summary this seat PASS" in out and "CENSUS summary peer seat FAIL" in out, out
    assert "peer seat: census summary missing=1 (needs 0)" in out, out
    assert "VERDICT B1 withheld: sitting incomplete" in out, out


def _keyed_line(row, drop):
    """A line of row's kind making its condition hold and carrying every required key of the kind but drop."""
    kind, when = row[0], row[1]
    keys = []
    for k2, _, _, ks, _ in P.REQUIRED_KEYS:
        if k2 == kind:
            keys += [k for k in ks if k not in keys]
    word = P.SUBKINDS[kind][0] if kind in P.SUBKINDS else kind
    toks = ["%s=%s" % (k, SAMPLE_VALUES.get(k, "1")) for k in keys if k != drop]
    if when is not None and WHEN_TOKENS[when] is not None:
        toks.append(WHEN_TOKENS[when])
    return "[FRAME-TIME] %s %s" % (word, " ".join(toks))


def _refusal_cases():
    out = []
    for row in P.REQUIRED_KEYS:
        for k in row[3]:
            out.append((row, k))
    return out


def _expect(row, drop):
    """The refusal the line lacking drop must give: (kind, lacks). A SUBKINDS line without its first word is a line
    of the parent kind, refused for the parent's keys."""
    kind = row[0]
    if kind in P.SUBKINDS and drop == P.REQUIRED_KEYS[[r[0] for r in P.REQUIRED_KEYS].index(kind)][3][0]:
        parent = P.SUBKINDS[kind][0]
        return parent, P.lacks_keys(dict(P.parse_line(_keyed_line(row, drop)), kind=parent))
    return kind, [drop]


def test_required_keys_table_is_complete_and_known():
    # every row names a known record kind, every condition has its sample token, a kind's rows hold disjoint keys,
    # and every required key is indexed in ft_parse.py as ["key"] (the table is derived from the code)
    src = open(FT_SCRIPT, encoding="utf-8").read()
    seen = {}
    for kind, when, cond, keys, users in P.REQUIRED_KEYS:
        assert kind in P.RECORDS, kind
        assert (when is None) == (cond is None) and (when is None or when in WHEN_TOKENS), (kind, when)
        assert not set(keys) & seen.get(kind, set()), (kind, keys)
        seen.setdefault(kind, set()).update(keys)
        for k in keys:
            # hitch indexes the three e<H> keys as r["e%d" % h]
            assert '["%s"]' % k in src or (re.fullmatch(r"e\d+", k) and 'r["e%d" % h]' in src), (kind, k)


@pytest.mark.parametrize("row,drop", _refusal_cases(),
                         ids=[re.sub(r"\W", "_", "%s_%s_%s" % (r[0], r[1], k)) for r, k in _refusal_cases()])
def test_record_lacking_a_required_key_is_a_named_refusal(row, drop):
    good = _summary_log(["[FRAME-TIME] sitting complete g=16", _keyed_line(row, None)])
    recs = P.read(good, "good.log")
    assert recs[1]["kind"] == row[0] and P.lacks_keys(recs[1]) == []      # the negative control: nothing lacking
    text = _summary_log(["[FRAME-TIME] sitting complete g=16", _keyed_line(row, drop)])
    kind, lacks = _expect(row, drop)
    with pytest.raises(P.RecordRefused) as ei:
        P.read(text, "seat.log")
    e = ei.value
    assert (e.kind, e.src, e.line, e.lacks) == (kind, "seat.log", 2, lacks), str(e)
    assert str(e) == "FT-PARSE REFUSED: kind=%s file=seat.log line=2 lacks %s" % (kind, ",".join(lacks))
    with pytest.raises(P.RecordRefused):
        P.report(text, peer=_peer_text())


def test_census_line_without_g_is_a_named_refusal():
    text = _summary_log(["[FRAME-TIME] census entry=E comp=X shape=S on=1 guarded=0 outside=0"])
    with pytest.raises(P.RecordRefused) as ei:
        P.read(text, "seat.log")
    assert str(ei.value) == "FT-PARSE REFUSED: kind=census file=seat.log line=1 lacks g"


def _run_script(*paths):
    import subprocess
    r = subprocess.run([sys.executable, "-I", "-B", FT_SCRIPT] + [str(p) for p in paths],
                       capture_output=True, text=True, timeout=600)
    return r.returncode, r.stdout, r.stderr


def test_refusal_exit_code_is_its_own():
    src = open(FT_SCRIPT, encoding="utf-8").read()
    codes = re.findall(r"sys\.exit\(([^)]*)\)", src)
    assert sorted(codes) == ["3", "REFUSED_RECORD_EXIT"], codes
    assert P.REFUSED_RECORD_EXIT not in (0, 1, 2, 3)


def test_refusals_through_the_script_main_path(tmp_path):
    # the census line without g, and one line per REQUIRED_KEYS row (its first key dropped), through the script
    cases = [("census-no-g", "[FRAME-TIME] census entry=E comp=X shape=S on=1 guarded=0 outside=0", "census", ["g"])]
    for i, row in enumerate(P.REQUIRED_KEYS):
        kind, lacks = _expect(row, row[3][0])
        cases.append(("row%d" % i, _keyed_line(row, row[3][0]), kind, lacks))
    for name, line, kind, lacks in cases:
        f = tmp_path / ("%s.log" % name)
        f.write_text(_summary_log(["[FRAME-TIME] sitting complete g=16", line]) + "\n", encoding="utf-8")
        rc, out, err = _run_script(f)
        assert rc == P.REFUSED_RECORD_EXIT and not err.strip(), (name, rc, out, err)
        assert out.strip() == "FT-PARSE REFUSED: kind=%s file=%s line=2 lacks %s" % (kind, f, ",".join(lacks)), (name, out)
    # the peer's input is named as the peer's
    good = tmp_path / "good.log"
    good.write_text(_log() + "\n", encoding="utf-8")
    bad = tmp_path / "census-no-g.log"
    rc, out, err = _run_script(good, bad)
    assert rc == P.REFUSED_RECORD_EXIT and out.strip() == \
        "FT-PARSE REFUSED: kind=census file=%s line=2 lacks g" % bad, (rc, out, err)


# ------------------------------------------------------------------ ruling R6-A3.11.92: room-gate lines, failed cal lines

def _insert_before(log, anchor, line):
    i = log.index(anchor)
    return log[:i] + line + "\n" + log[i:]


def test_churn_freeze_failed_withholds_the_verdicts_and_its_trace_does_not():
    trace = _insert_before(_log(), "[FRAME-TIME] flushed g=9", LOG_PREFIX + "[FRAME-TIME] churn timer frozen room=R")
    assert P.complete(P.read(trace)) == []
    log = _insert_before(_log(), "[FRAME-TIME] flushed g=9", FAILURE_LINES[-1])
    assert [m for m in P.complete(P.read(log)) if m.startswith("failure event: churn freeze")], log
    assert re.search(r"^VERDICT B1 withheld: sitting incomplete", _report(log), re.M)


def test_raw_failure_lines_withhold_the_verdicts_and_their_traces_do_not():
    traces = (LOG_PREFIX + "[FRAME-TIME] FT-ROOM joined offline=0 name=R",
              LOG_PREFIX + "[FRAME-TIME] FT-GATE patched 5 entry points expected=5 excluded=")
    assert all(P.raw_failure_events(t) == [] for t in traces)
    base = _log()
    for ln in RAW_FAILURE_LINES:
        assert P.parse_line(ln) is None                     # _LINE unchanged: the line is no record
        log = _insert_before(base, "[FRAME-TIME] flushed g=9", ln)
        assert len(P.read(log)) == len(P.read(base))
        want = "failure event: " + ln[ln.index("FT-"):ln.index(" failed") + len(" failed")]
        assert [m for m in P.raw_failure_events(log) if m.startswith(want)], (want, P.raw_failure_events(log))
        out = _report(log)
        assert re.search(r"^SITTING INCOMPLETE: .*" + re.escape(want), out, re.M), out
        assert re.search(r"^VERDICT B1 withheld: sitting incomplete", out, re.M), out
        menu = _menu_log() + "\n" + ln
        assert "MENU PASS" in P.report(_menu_log()) and re.search(r"^MENU FAIL: .*" + re.escape(want), P.report(menu),
                                                                  re.M), P.report(menu)


def test_census_summary_non_integer_value_fails_the_check():
    # Codex PARSER-FIX-R1 MEDIUM: the non-integer route names the value and no comparison passes it
    for k in P.CENSUS_SUMMARY_KEYS:
        v = dict(registered=N_E, expected=N_E, missing=0, duplicates=0)
        v[k] = "bogus"
        line = "[FRAME-TIME] census registered=%(registered)s expected=%(expected)s missing=%(missing)s " \
               "duplicates=%(duplicates)s" % v
        ok, _, bad = P.census_summary(P.read(_summary_log([line])))
        assert not ok and bad == ["census summary %s=bogus is not an integer" % k], (k, bad)


PEER_FAILURE_LINES = (FAILURE_LINES[-1],) + RAW_FAILURE_LINES     # churn freeze failed, FT-ROOM, FT-GATE


@pytest.mark.parametrize("line", PEER_FAILURE_LINES, ids=["churn", "ft_room", "ft_gate"])
def test_a_failure_line_in_the_peer_log_alone_withholds_the_verdicts(line):
    # Codex PARSER-FIX-R1 HIGH 2: failure events are collected from the peer's log too, parsed and raw
    peer = _insert_before(_peer_text(), "[FRAME-TIME] flushed g=9", line)
    out = _report(_log(), peer=peer)
    want = "peer seat: failure event: " + line[line.index("[FRAME-TIME] ") + 13:line.index(" failed")]
    assert re.search(r"^SITTING INCOMPLETE: .*" + re.escape(want), out, re.M), (want, out)
    for v in ("B1", "B2", "B3"):
        assert re.search(r"^VERDICT %s withheld: sitting incomplete" % v, out, re.M), out


def test_a_disarm_in_the_peer_log_alone_fails_vr6():
    # Codex PARSER-FIX-R1 HIGH 2's sweep: a disarm on either seat makes the sitting INVALID
    peer = _insert_before(_peer_text(), "[FRAME-TIME] flushed g=9",
                          LOG_PREFIX + "[FRAME-TIME] disarmed input=room pt=9.3.1")
    out = _report(_log(), peer=peer)
    assert "VR6 build half FAIL: peer seat disarmed: room at 9.3.1" in out, out
    assert re.search(r"^VERDICT B1 INVALID: VR6 failed", out, re.M), out


def test_an_unreadable_peer_log_withholds_the_verdicts():
    # Codex PARSER-FIX-R1 HIGH 2's sweep: a peer log whose records cannot be read cannot be swept for failure events
    peer = _peer_text().replace("[FRAME-TIME] flushed g=9 why=next_game", "[FRAME-TIME] flushed g=9.5 why=next_game")
    assert peer != _peer_text()
    out = _report(_log(), peer=peer)
    assert "peer seat: its failure events not read (non-integer value g=9.5)" in out, out
    assert re.search(r"^VERDICT B2 withheld: sitting incomplete", out, re.M), out


LIVE_FIELDS = ("reads", "scopes", "ticks", "tmax", "unscoped", "depth_err")     # FtA3.LogGame's executed line


@pytest.mark.parametrize("field", LIVE_FIELDS)
def test_a_live_calibration_line_lacking_a_field_is_refused_when_read(field):
    # Codex PARSER-FIX-R1 HIGH 1: a live row's executed line is refused by name as it is read (before this, a3_live's
    # own check refused it later, inside the U block); the fields are FtA3.cs's writer's, not REQUIRED_KEYS'
    base = _sweep_base("log")
    i = base.index(" live=1 ")
    s = base.rindex("\n", 0, i) + 1
    e = base.index("\n", i)
    line = base[s:e]
    toks = line.split(" ")
    cut = " ".join(t for t in toks if not t.startswith(field + "="))
    assert cut != line
    n = base[:s].count("\n") + 1
    with pytest.raises(P.RecordRefused) as ei:
        P.read(base[:s] + cut + base[e:], "seat.log")
    assert (ei.value.kind, ei.value.line, ei.value.lacks) == ("cal", n, [field]), str(ei.value)


def _record_keys(text):
    """{kind: sorted keys} over every record line of text, each key as its raw token spells it (the part before the
    token's last '=' for a refusals line, before its first '=' otherwise); taken from the log, never from REQUIRED_KEYS."""
    out = {}
    for ln in text.splitlines():
        r = P.parse_line(ln)
        if r is not None:
            out.setdefault(r["kind"], set()).update(_tok_key(r["kind"], t) for t in ln.split() if "=" in t)
    out = {k: sorted(v - {""}) for k, v in out.items()}
    return out


def _tok_key(kind, tok):
    return tok.rpartition("=")[0] if kind == "refusals" else tok.partition("=")[0]


def _drop_key(text, kind, key):
    """text with the token of key removed from every line of kind (the whole report then reads that kind without it)."""
    out = []
    for ln in text.splitlines():
        r = P.parse_line(ln)
        if r is not None and r["kind"] == kind:
            i = ln.index("[FRAME-TIME] ")
            ln = ln[:i] + " ".join(t for t in ln[i:].split(" ") if not ("=" in t and _tok_key(kind, t) == key))
        out.append(ln)
    return "\n".join(out)


_SWEEP = {}


def _sweep_base(name):
    """The clean fixture a sweep case drops a key from, built once: this seat's log, the peer's, a menu run's."""
    if name not in _SWEEP:
        _SWEEP[name] = {"log": _log, "peer": _peer_text, "menu": _menu_log}[name]()
    return _SWEEP[name]


def _sitting_cases():
    return [(k, key) for k, keys in sorted(_record_keys(_sweep_base("log")).items()) for key in keys]


def _menu_cases():
    return [(k, key) for k, keys in sorted(_record_keys(_sweep_base("menu")).items()) for key in keys]


def _ends_named(fn):
    """'report' when fn returns, the refusal's class name when it raises RecordRefused or Refused; any other exception
    propagates (a traceback, the defect this sweep looks for). A report holding a KeyError's text in a 'not
    computable' line (report() catches KeyError there) is the same defect swallowed, and fails here by name."""
    try:
        out = fn()
        swallowed = re.findall(r"^.*not computable: '\w+'$", out, re.M)
        assert not swallowed, swallowed
        return "report"
    except P.RecordRefused:
        return "RecordRefused"
    except P.Refused:
        return "Refused"


@pytest.mark.parametrize("kind,key", _sitting_cases(), ids=["%s-%s" % c for c in _sitting_cases()])
def test_every_fixture_key_dropped_ends_in_the_report_or_a_named_refusal(kind, key):
    # Codex PARSER-FIX-R1 HIGH 1: the cases come from the fixture's own records (every kind, every key it carries),
    # not from REQUIRED_KEYS; each key is dropped from every line of its kind, in both seats' logs, and the whole
    # report runs. It ends in the report or in a named refusal (the script exits 0, 4 or 3), never a traceback.
    text = _drop_key(_sweep_base("log"), kind, key)
    peer = _drop_key(_sweep_base("peer"), kind, key)
    assert text != _sweep_base("log")
    assert _ends_named(lambda: P.report(text, peer=peer)) in ("report", "RecordRefused", "Refused")


@pytest.mark.parametrize("kind,key", _menu_cases(), ids=["%s-%s" % c for c in _menu_cases()])
def test_every_menu_fixture_key_dropped_ends_in_the_report_or_a_named_refusal(kind, key):
    # the same sweep over the menu run's fixture (menu_report's path)
    text = _drop_key(_sweep_base("menu"), kind, key)
    assert text != _sweep_base("menu")
    assert _ends_named(lambda: P.report(text)) in ("report", "RecordRefused", "Refused")


def test_failed_cal_lines_are_skipped_by_the_calibration_consumers():
    # ruling R6-A3.11.92 (4): a failed disp or span line beside good ones is read without a KeyError and moves nothing
    base = _log()
    s = sorted(SHAPES)[0]
    bad = _insert_before(base, "[FRAME-TIME] cal i=6 why=game5 kind=span",
                         LOG_PREFIX + "[FRAME-TIME] cal i=6 why=game5 kind=disp shape=%s failed: no calls" % s)
    bad = _insert_before(bad, "[FRAME-TIME] cal i=6 why=game5 kind=span",
                         LOG_PREFIX + "[FRAME-TIME] cal i=6 why=game5 kind=span shape=span.empty failed: boom")
    assert P.d_up(P.read(bad)) == P.d_up(P.read(base))
    assert P.stamps_estimate(P.read(bad)) == P.stamps_estimate(P.read(base))
    # complete(): a game whose only calibration line failed has no calibration
    # (the game's live a3 executed lines carry why=game5 too, so they go with its start run)
    gone = _insert_before(_log(drop_cal={5}, live_drop={(5, k) for k in A3_LIVE}), "[FRAME-TIME] opened g=5",
                          LOG_PREFIX + "[FRAME-TIME] cal i=6 why=game5 kind=disp shape=%s failed: no calls" % s)
    assert "no calibration for games [5]" in P.complete(P.read(gone)), P.complete(P.read(gone))
    # menu_check: a failed menu fhat line counts as no calibration cycle (its failure warning is named apart)
    m = _menu_log()
    i = m.index("[FRAME-TIME] cal i=1 why=menu1 kind=fhat f_hat=")
    j = m.index("\n", i)
    m = m[:j] + "\n" + LOG_PREFIX + "[FRAME-TIME] cal i=1 why=menu1 kind=fhat failed: overflow" + m[j:]
    ok, _, why = P.menu_check(P.read(m))
    assert not ok and any("failure warnings" in w for w in why), why
    assert not any(w.startswith("menu calibrations") for w in why), why


# ------------------------------------------------------------------ ruling R6-A3.11.113 (2)(a)(b): withheld read classes

SEAT_PS1 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frame_time_seat.ps1")


def _slice_class_words():
    """the bracketed class words of the laptop seat script's $SliceClasses, its list of selected classes"""
    t = open(SEAT_PS1, encoding="utf-8").read()
    m = re.search(r"^\$SliceClasses = @\((.*?)\)$", t, re.M | re.S)
    assert m, "no $SliceClasses in the seat script"
    return re.findall(r"'\[([A-Z0-9-]+)\]'", m.group(1))


def _check_read_classes(path):
    """every bracketed class word of $SliceClasses that occurs in the parse source at path is in that source's own
    READ_CLASSES"""
    import ast
    src = open(path, encoding="utf-8").read()
    m = re.search(r"^READ_CLASSES = (\(.*\))$", src, re.M)
    assert m, "no READ_CLASSES in %s" % path
    read = ast.literal_eval(m.group(1))
    words = _slice_class_words()
    assert "FRAME-TIME" in words and "COMBAT-PERF" in words and len(words) >= 12, words
    gaps = [w for w in words if "[%s]" % w in src and w not in read]
    assert gaps == [], "slice classes this parse reads but READ_CLASSES lacks: %s" % gaps


def test_every_slice_class_the_parse_reads_is_a_read_class():
    _check_read_classes(FT_SCRIPT)
    assert P.READ_CLASSES == ("FRAME-TIME", "FPSCAP")


def test_read_class_check_turns_red_on_a_planted_class_literal(tmp_path):
    # the control: a copy of the parse with a planted [COMBAT-PERF] literal fails the check above
    src = open(FT_SCRIPT, encoding="utf-8").read()
    planted = tmp_path / "ft_parse.py"
    planted.write_text(src + '\n_PLANTED = "[COMBAT-PERF] mode="\n', encoding="utf-8")
    with pytest.raises(AssertionError) as ei:
        _check_read_classes(str(planted))
    assert "COMBAT-PERF" in str(ei.value), ei.value


@pytest.mark.parametrize("cls", ["FRAME-TIME", "FPSCAP"])
@pytest.mark.parametrize("where", ["log", "peer"])
def test_a_withheld_read_class_line_is_the_record_refusal(tmp_path, cls, where):
    good = _log()
    bad = good + "\n=== component slice\nwithheld %s 3\n" % cls
    g = tmp_path / "good.log"
    b = tmp_path / "bad.log"
    g.write_text(good + "\n", encoding="utf-8")
    b.write_text(bad, encoding="utf-8")
    rc, out, err = _run_script(b, g) if where == "log" else _run_script(g, b)
    n = bad.splitlines().index("withheld %s 3" % cls) + 1
    assert rc == P.REFUSED_RECORD_EXIT and not err.strip(), (rc, out, err)
    assert out.strip() == "FT-PARSE REFUSED: withheld class=%s count=3 file=%s line=%d" % (cls, b, n), out
    with pytest.raises(P.RecordRefused):
        P.read(bad)


@pytest.mark.parametrize("line", ["withheld FRAME-TIME 0", "withheld COMBAT-PERF 3", "withheld refused 2",
                                  " withheld FRAME-TIME 3", "withheld FRAME-TIME 3 ", "withheld [FRAME-TIME] 3",
                                  LOG_PREFIX + "withheld FRAME-TIME 3"])
def test_other_withheld_lines_are_not_the_refusal(line):
    P.refuse_withheld(_log() + "\n" + line + "\n")


# ------------------------------------------------------------------ B11: the interleaved window design (ruling .138/.139)
# A synthetic record generator with a known truth. Clock unit: f_hat 1e6, so a window's cycles are microseconds; T_ref
# is B11_T us per frame and one percent of it B11_PC. A game is a list of points; a point is a dict: n, the windows'
# frame counts in order; coins, one (A, B) per run of four (1 = ON at positions 1 and 2, the complement at 3 and 4);
# plant, the runs that are plant runs; zs (a void round when nonzero); rnd, its round. model(arm, pred, pos, partial,
# j) gives the per-frame (S, E, R) cycles of tenth j (0-based), pred the predecessor's arm or "none".

B11_T = 180000
B11_PC = B11_T // 100
B11_BASE = 100000
B11_TICKS = 10                       # Stopwatch ticks per us at FREQ


def _b11_arm(coins, wi):
    run, pos = (wi - 1) // 4 + 1, (wi - 1) % 4 + 1
    a = coins[run - 1][0 if pos in (1, 3) else 1]
    return run, pos, ("ON" if a ^ (1 if pos in (3, 4) else 0) else "OFF")


B11_TOK0 = "log:0,0,0,0,0,0,0;hash:0,0,0,0,0,0,0;recv:0,0,0,0,0,0,0;sock:0,0,0,0,0,0,0"
B11_WU0 = "log:0:0;hash:0:0;recv:0:0;sock:0:0"
B11_P_EXTRA = (" sock_p95=0 sock_n=0 sock_thr=0 sock_main=0 ab_back=0 ab_retry=0 heap=50000000"
               # ruling R6-A3.11.151 (2) class B: the p line's other fault fields as the emitter prints them
               # (plugin/FtFrames.cs:265, 274-276), each 0
               " excl=0 plant_mixed=0 off_g=0 off_gn=0 off_on=0 on_guarded=0 span_class_overflow=0 gc_read_failures=0")
# ruling R6-A3.11.151 (3): the attach line of a healthy FrameTime boot, as FtAttach.Report builds it (P1b's hand-back,
# commit aa6d99e9, via the integrator), and of a healthy FrameTimeRef boot (the nine without FtSockPatch)
ATTACH_OK = ("attach n=10 of=10 missing=none names=FtChurnFreezePatch:1/1,FtDrive_InputPatch:1/1,FtDrive_PickPatch:1/1,"
             "FtPhotonEPatch:12/12,FtPhotonXPatch:8/8,FtRoomGateNchRoutinePatch:2/2,FtRoomGateNchVoidPatch:2/2,"
             "FtRoomGatePunPatch:9/9,FtRoute_SendPatch:2/2,FtSockPatch:2/2")
ATTACH_REF = ATTACH_OK.replace("n=10 of=10", "n=9 of=9").replace(",FtSockPatch:2/2", "")


def _as_ref(text):
    """A measurement fixture as a FrameTimeRef boot's log: its marker and its attach line (the reference build's)."""
    assert text.count(P.MARK_FT) == 1 and text.count(ATTACH_OK) == 1
    return text.replace(P.MARK_FT, P.MARK_REF).replace(ATTACH_OK, ATTACH_REF)
# ruling R6-A3.11.147 (5): the V6 boot lines, each in range; _b11_text's boot= replaces (or, with None, drops) one
V6_BOOT = (("alloc", "alloc pin=ok planted=1048600/1048576 empty=0"),
           ("scope plant", "scope plant asked=2000 got=2010"),
           ("nest", "nest plant asked=2000 x=2020 e=1990 p=2005"),
           # ruling R6-A3.11.149 (1): the patch line names ten methods, typed as FtPhoton.ReportPatched prints them
           ("photon", "photon patches n=10 names=" + ",".join(P.PHOTON_ENTRIES)),
           ("scope census", "scope census entries=40 wrapped=40"),
           # P1's V6 emitter (via the integrator, 12 Nov): a sitting log's control-mutant line
           ("controls", "controls k_mutant=none"),
           # the follow-up to ruling .149, A and B: the writer ledger's disk-log tap (FtLedger.Install) and the room
           # gate's patch-time line (FtRoomGate.ReportPatched: 9 PUN overloads, 2 void and 2 coroutine entry points)
           ("ledger", "ledger log=1 why=ok types=log,hash,recv,sock"),
           ("gate", "FT-GATE patched 13 entry points expected=13 excluded=JoinLobby,LoadOrCreateSettings"),
           # ruling R6-A3.11.151 (3): the attach line, after the patch loop and the two patch reports
           ("attach", ATTACH_OK))
# the two keys a V6 counters line carries after span_depth_violations (P1's emitter, via the integrator, 12 Nov)
B11_CTR_V6 = " photon_offmain=0 span_leave_mismatch=0"


def _b11_text(games, model, marker=True, settled=True, first_game=1, edit=None, cg=None, cw=0, mark=True,
              wu=B11_WU0, p_extra=B11_P_EXTRA, force="none", force_arms=True, v6=None, boot=None, fpscap=True,
              ctr=None, sitting=False, fhat=1000000, t_us=B11_T, heavy=None):
    """The [FRAME-TIME] lines of B11 games: the marker, the mark cost boot line, the five V6 boot lines (boot: name ->
    replacement line, or None to drop it), the FPSCAP hold, settled (f_hat 1e6, force=), the point lines and their
    window lines in SHARED.md's format. A point's "plant" runs are plant runs (prun=1), "unspun" those of them fixed
    before c_plant (no window planted); a spun run's OFF windows are planted (plant=1). edit(window dict) may spoil a
    window's fields before it is written; cg(window) may return None (cG=NA: G stays inside cE and q) or a GC cycle
    count; cw is common-writer cycles per frame; ON windows mark 4 class transitions, OFF windows 1. force: the
    settled lines' force= (None prints none); under force=ON every window is ON (sitting V) unless force_arms is
    False. v6(window) may return V6 values: cP_pf and cX_pf (cycles per frame; P leaves q, X stays in it), aC to aX
    (bytes or None for NA), wa (text) and wu (text); by default no P or X, aC 100000 bytes per frame, no class bytes.
    Each game ends with its counters line, the three counters 0 and then ctr(g) (B11_CTR_V6 by default; None drops
    the line). sitting=True makes it a complete sitting (ruling R6-A3.11.149 (5)(a): the validity set needs one): game 0,
    the mutant, every point of the first game again with zs=4 (every round void), before games first_game on; the
    census summary; per game the settled line under F18 reading A, its replay, its calibration run (fhat, a disp line
    per shape, span), its opened, census, heavy, offthread, between and flushed lines, and t0 and t1 on every point
    line; the refusals line at the quit and 'sitting complete'. fhat is every settled and calibration f_hat, t_us every
    frame's time, heavy(g, op) an optional (live, at_call, edge) for a heavy line."""
    L = ["[FRAME-TIME] " + P.MARK_FT] if marker else []
    if mark:
        L.append("[FRAME-TIME] mark cost cyc=50 p90=70 n=1000")
    if sitting:
        L.append(CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 0, 0))
        games = [[dict(pt, zs=4) for pt in games[0]]] + list(games)
        first_game -= 1
    bt = dict(V6_BOOT)
    bt.update(boot or {})
    L += ["[FRAME-TIME] " + x for x in bt.values() if x is not None]
    if fpscap:
        L.append("[FPSCAP] held by frame-time calibration")
    clock = [10 ** 6]
    for gi, pts in enumerate(games):
        g = first_game + gi
        if settled:
            L.append("[FRAME-TIME] settled g=%d seed=1 c_plant=80 W=120 vsync=0 target=-1 freq=%d hires=1 f_hat=%d%s%s"
                     % (g, FREQ, fhat, " f18=A answer=replay" if sitting else "",
                        "" if force is None else " force=%s" % force))
        if sitting:
            L.append("[FRAME-TIME] answer_replay g=%d ticks=4000 result=settled" % g)
            L.append("[FRAME-TIME] cal i=%d why=game%d kind=fhat f_hat=%d spins=1/1" % (g + 1, g, fhat))
            L += ["[FRAME-TIME] cal i=%d why=game%d kind=disp shape=%s n=100000 u=1000000,1000000 p=1030000,1030000"
                  % (g + 1, g, s) for s in SHAPES]
            L.append("[FRAME-TIME] cal i=%d why=game%d kind=span shape=span.empty n=100000 u=100000,100000 "
                     "p=150000,150000" % (g + 1, g))
            L.append("[FRAME-TIME] opened g=%d se=1 ce=1 ic=1" % g)
        prev = None
        f0 = 0
        for pi, pt in enumerate(pts):
            label = "%d.%d.%d" % (g, pt.get("rnd", 1), pt.get("pnum", pi + 1))
            ws = []
            for wi, n in enumerate(pt["n"], 1):
                run, pos, arm = _b11_arm(pt["coins"], wi)
                if force == "ON" and force_arms:
                    arm = "ON"                  # SHARED.md V6: arm= is the gate's real state
                prun = 1 if run in pt.get("plant", ()) else 0
                plant = 1 if prun and arm == "OFF" and run not in pt.get("unspun", ()) else 0
                pred = "none" if prev is None else prev["arm"]
                res = 1 if prev is not None and prev["prun"] == 1 and prun == 0 else 0
                qn = P._bins(n)
                partial = 1 if n < P.WINDOW_FRAMES else 0
                S = E = R = 0
                q, r = [], []
                for j in range(P.TENTHS):
                    s_, e_, r_ = model(arm, pred, pos, partial, j)
                    S += s_ * qn[j]
                    E += (e_ + B11_BASE) * qn[j]
                    R += r_ * qn[j]
                    q.append((s_ + e_ + B11_BASE + r_) * qn[j])
                    r.append(r_ * qn[j])
                w = dict(pt=label, arm=arm, plant=plant, prun=prun, partial=partial, n=n, run=run, pos=pos,
                         unit="P13" if pos in (1, 3) else "P24", coin=pt["coins"][run - 1][0 if pos in (1, 3) else 1],
                         wi=wi, f0=f0, pred=pred, res=res, gcn=0, cG=0, cW=cw * n, cR=R, cS=S, cE=E, q=q, r=r, qn=qn,
                         wu=wu, tok=B11_TOK0, nm=4 if arm == "ON" else 1, cP=0, cX=0, aC=100000 * n, aW=0, aR=0,
                         aS=0, aP=0, aX=0, wa="log:0;hash:0;sock:0")
                ex = v6(w) if v6 else {}
                w["cP"], w["cX"] = ex.get("cP_pf", 0) * n, ex.get("cX_pf", 0) * n
                w["q"] = [qq + ex.get("cX_pf", 0) * qn[j] for j, qq in enumerate(q)]     # X stays in C°, P leaves it
                for k in ("aC", "aW", "aR", "aS", "aP", "aX", "wa", "wu", "gcn"):
                    if k in ex:
                        w[k] = ex[k]
                gv = cg(w) if cg else 0
                if gv is None:
                    w["cG"] = None
                else:
                    w["cG"] = gv
                    w["cE"] = E - gv                    # GC executes inside the frame: the partition keeps C
                    w["q"] = list(w["q"])
                    w["q"][0] -= gv                     # C° = C - G - W - P
                w["sC"] = (w["cG"] or 0) + w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cX"] + w["cE"]
                w["sF"] = n * t_us * B11_TICKS
                w["sS"] = 0
                w["sP"] = w["sC"]
                if edit:
                    edit(w)
                ws.append(w)
                prev = w
                f0 += n
            un = [w for w in ws if not w["plant"]]
            pl = [w for w in ws if w["plant"]]
            t0 = clock[0]
            clock[0] += sum(w["sF"] for w in ws) + FREQ
            L.append("[FRAME-TIME] p pt=%s arm=%s gate=0 pred=%s n=%d sF=%d sS=%d sC=%d maxF=1 pn=%d psF=%d psS=%d "
                     "psC=%d sP=%d psP=%d windows=%d live_frames=%d missing_end=0 span_g=0 span_gn=0 span_u=0 "
                     "on_calls=0 guarded=0 zs=%d zl=1 own_split=%d recv_offmain=0 ledger_cycle_miss=0%s%s"
                     % (label, ws[0]["arm"], ws[0]["pred"], sum(w["n"] for w in un), sum(w["sF"] for w in un),
                        sum(w["sS"] for w in un), sum(w["sC"] for w in un), sum(w["n"] for w in pl),
                        sum(w["sF"] for w in pl), sum(w["sS"] for w in pl), sum(w["sC"] for w in pl),
                        sum(w["sP"] for w in un), sum(w["sP"] for w in pl), len(ws), sum(w["n"] for w in ws),
                        pt.get("zs", 0), pt.get("own_split", 0), p_extra,
                        " t0=%d t1=%d answer=replay" % (t0, t0 + sum(w["sF"] for w in ws)) if sitting else ""))
            if sitting and pi > 0:
                L.append("[FRAME-TIME] between g=%d after=%s ticks=2000 calls=4" % (g, ws[0]["pred"]))
            for w in ws:
                L.append(_b11_wline(w))
        if sitting:
            L += ["[FRAME-TIME] census g=%d entry=%s comp=X shape=%s on=0 guarded=0 outside=0" % (g, e, s)
                  for e, s in ENTRIES]
            for op in P.HEAVY_OPS:
                lv, ac, ed = (heavy and heavy(g, op)) or (0, 0, 0)
                L.append("[FRAME-TIME] heavy g=%d op=%s live=%d between=7 pick=1 over=1 menu=0 at_call=%d edge=%d off=0"
                         % (g, op, lv, ac, ed))
            L.append("[FRAME-TIME] offthread g=%d span_off=0 hash_t0=0 hash_t1=0" % g)
            L.append("[FRAME-TIME] flushed g=%d why=%s" % (g, "next_game" if gi < len(games) - 1 else "settle"))
        tail = B11_CTR_V6 if ctr is None else ctr(g)
        if tail is not None:
            L.append("[FRAME-TIME] counters g=%d frames=%d missing_end=0 cycle_failures=0 span_depth_violations=0%s"
                     % (g, sum(sum(pt["n"]) for pt in pts), tail))
    if sitting:
        L.append("[FRAME-TIME] refusals why=quit pairs=0")
        L.append("[FRAME-TIME] sitting complete g=%d" % (first_game + len(games) - 1))
    return "\n".join(LOG_PREFIX + x for x in L)


def _na(x):
    return "NA" if x is None else str(x)


def _b11_wline(w):
    # FtFrames.cs's line: medF and the excess counts only on a full window; then SHARED.md's appended fields, and V6's
    # after nm
    full = "" if w["partial"] else "medF=1 e4=0,0 e8=0,0 e16=0,0 "
    return ("[FRAME-TIME] w pt=%s arm=%s plant=%d partial=%d n=%d sF=%d sS=%d sC=%d sP=%d maxF=1 %sgc=0 run=%d pos=%d "
            "unit=%s coin=%d wi=%d f0=%d pred=%s prun=%d res=%d gcn=%d cG=%s cW=%d cR=%d cS=%d cE=%d q=%s r=%s qn=%s "
            "wu=%s tok=%s nm=%d cP=%d cX=%d aC=%s aW=%s aR=%s aS=%s aP=%s aX=%s wa=%s"
            % (w["pt"], w["arm"], w["plant"], w["partial"], w["n"], w["sF"], w["sS"], w["sC"], w["sP"], full, w["run"],
               w["pos"], w["unit"], w["coin"], w["wi"], w["f0"], w["pred"], w["prun"], w["res"], w["gcn"], _na(w["cG"]),
               w["cW"], w["cR"], w["cS"], w["cE"], ",".join(map(str, w["q"])), ",".join(map(str, w["r"])),
               ",".join(map(str, w["qn"])), w["wu"], w["tok"], w["nm"], w["cP"], w["cX"], _na(w["aC"]), _na(w["aW"]),
               _na(w["aR"]), _na(w["aS"]), _na(w["aP"]), _na(w["aX"]), w["wa"]))


def _enum(k):
    """Every assignment of k fair coins, so an HT estimate's realised average over the games is its expectation."""
    return [[(i >> b) & 1 for b in range(k)] for i in range(2 ** k)]


def _one_run_games(reps=1):
    """C2 and C3's design: one point of four full windows per game, every (A, B) once (times reps); cold starts."""
    return [[{"n": [120] * 4, "coins": [(a, b)]}] for a, b in _enum(2)] * reps


def _c2_model(arm, pred, pos, partial, j):
    # refutation-c2.md:1: ON costs 2.5 percent (1 direct, 1.5 external); second positions after predecessor ON cost
    # 5/3 percent more in tenths 1 to 9, nothing in tenth 10
    s, e = (B11_PC, B11_PC * 3 // 2) if arm == "ON" else (0, 0)
    if pos in (2, 4) and pred == "ON" and j < 9:
        e += B11_PC * 5 // 3
    return s, e, 0


def _c3_model(arm, pred, pos, partial, j):
    # refutation-c3.md:16-23: ON switched direct 2.65 percent; retained R 7/18 percent in tenths 1 to 9 after a
    # predecessor OFF (and cold), none after ON; after ON, 4/9 percent switched-origin external in tenths 1 to 9;
    # either current arm
    s = B11_PC * 265 // 100 if arm == "ON" else 0
    r = B11_PC * 7 // 18 if pred != "ON" and j < 9 else 0
    e = B11_PC * 4 // 9 if pred == "ON" and j < 9 else 0
    return s, e, r


def _c4_games():
    """refutation-c4.md (ruling .139 (2)): groups of four points, three of 120 + 60 frames and one of 120 + 120 + 120;
    each game is one group, every assignment of its eight coins once."""
    out = []
    for c in _enum(8):
        out.append([{"n": [120, 60], "coins": [(c[0], c[1])]}, {"n": [120, 60], "coins": [(c[2], c[3])]},
                    {"n": [120, 60], "coins": [(c[4], c[5])]}, {"n": [120, 120, 120], "coins": [(c[6], c[7])]}])
    return out


def _c4_model(arm, pred, pos, partial, j):
    # S 2.5 percent everywhere ON; a terminal partial window costs 5 percent external after a predecessor ON
    return (B11_PC * 5 // 2 if arm == "ON" else 0), (B11_PC * 5 if partial and pred == "ON" else 0), 0


def _pct(x):
    return x / B11_PC


def _est(text, **kw):
    return P.b11_estimate(P.read(text), **kw)


def chk_c2_recovers_3_25(m):
    # ruling .137 (3)-(4), .138 (2): the interleaved contrast 2.5, both carryover terms 0.75, the corrected 3.25
    e = m.b11_estimate(m.read(_b11_text(_one_run_games(), _c2_model)))
    assert _pct(e["B"][0]) == pytest.approx(2.5, abs=1e-9), e["B"]
    assert _pct(e["c_on"][0]) == pytest.approx(0.75, abs=1e-9) and _pct(e["c_off"][0]) == pytest.approx(0.75, abs=1e-9)
    assert _pct(e["J"][0]) == pytest.approx(3.25, abs=1e-9), e["J"]
    assert e["joint"] and e["bu"] >= e["J"][0]


def chk_c3_recovers_3_0375(m):
    # ruling .138 (3): c_ON 0.0375 on C°, c_OFF 0.3 on C° - R_OFF, the charge 0.16875, the corrected 3.0375
    e = m.b11_estimate(m.read(_b11_text(_one_run_games(), _c3_model)))
    assert _pct(e["B"][0]) == pytest.approx(2.86875, abs=1e-9), e["B"]
    assert _pct(e["c_on"][0]) == pytest.approx(0.0375, abs=1e-9), e["c_on"]
    assert _pct(e["c_off"][0]) == pytest.approx(0.3, abs=1e-9), e["c_off"]
    assert _pct(e["charge"][0]) == pytest.approx(0.16875, abs=1e-9)
    assert _pct(e["J"][0]) == pytest.approx(3.0375, abs=1e-9), e["J"]


def chk_c4_recovers_3_5(m):
    # ruling .139 (2): the partial stratum's direct estimate: c_a,P 5 percent, F_P 0.2, the charge 1, corrected 3.5
    e = m.b11_estimate(m.read(_b11_text(_c4_games(), _c4_model)))
    T = e["T"]
    assert T["N"] == 256 * 900 and T["npart"] == 256 * 180
    assert _pct(e["B"][0]) == pytest.approx(2.5, abs=1e-9), e["B"]
    assert _pct(e["charge"][0]) == pytest.approx(1.0, abs=1e-9), e["charge"]
    assert _pct(e["J"][0]) == pytest.approx(3.5, abs=1e-9), e["J"]


def _neg_model(arm, pred, pos, partial, j):
    # a predecessor ON makes every window cheaper by 20 percent in tenths 1 to 9: the carryover is far below 0
    return (B11_PC * 3 if arm == "ON" else 0), (-B11_PC * 20 if pred == "ON" and j < 9 else 0), 0


def chk_charge_never_negative(m):
    # max(0, .) (ruling .137 (4)): a charge whose upper bound is below 0 charges nothing; the bound is the contrast's
    e = m.b11_estimate(m.read(_b11_text(_one_run_games(reps=8), _neg_model)))
    assert e["charge"][0] + e["charge"][1] < 0 and e["charge"][2] == 0.0, e["charge"]
    # the lower bound keeps the negative carryover term (the integrator's ruling on the hand-back (2))
    assert e["lb"] == pytest.approx(e["J"][0] - e["J"][2], rel=1e-12) and e["lb"] < e["B"][0] - e["B"][2]
    assert e["bu"] == pytest.approx(e["B"][0] + e["B"][1], abs=1e-9) and not e["joint"], (e["bu"], e["B"], e["J"])
    assert e["J"][0] + e["J"][1] < e["bu"]


def _flat(arm, pred, pos, partial, j):
    return (B11_PC * 3 if arm == "ON" else 0), (B11_PC * (pos + j % 3) if arm == "ON" else B11_PC * (j % 2)), 0


def _ys(m, text):
    """Per window: (record, Y in us): C° in ON, C° - R in OFF."""
    out = []
    for w in m.read(text):
        if m.b11_line(w):
            out.append((w, sum(w["q"]) - (0 if w["arm"] == "ON" else w["cR"])))
    return out


def chk_mates_have_joint_probability_0_or_half(m):
    # ruling .138 (4), the integrator's D1: mates P(ON, ON) = 0 and P(ON, OFF) = 1/2; other windows 1/4; one 1/2
    ws = [w for w in m.read(_b11_text([[{"n": [120] * 4, "coins": [(1, 0)]}]], _flat)) if m.b11_line(w)]
    w1, w2, w3, w4 = ws
    assert m.arm_prob((w1, "ON")) == 0.5 and m.arm_prob((w3, "OFF")) == 0.5
    assert m.arm_prob((w1, "ON"), (w3, "ON")) == 0.0 and m.arm_prob((w1, "ON"), (w3, "OFF")) == 0.5
    assert m.arm_prob((w2, "OFF"), (w4, "OFF")) == 0.0 and m.arm_prob((w2, "ON"), (w4, "OFF")) == 0.5
    for a in ("ON", "OFF"):
        for b in ("ON", "OFF"):
            assert m.arm_prob((w1, a), (w2, b)) == 0.25 and m.arm_prob((w3, a), (w4, b)) == 0.25


def chk_a_pair_is_one_variance_unit(m):
    # ruling .138 (4); refutation-c4.md's V_g = 4 sum over pairs of (X_i - X_j)^2: equal mates' baselines cancel
    text = _b11_text([[{"n": [120] * 4, "coins": [(1, 0)]}]], _flat)
    T = m.b11_terms(m.read(text))
    y = dict((w["wi"], (w["arm"], v)) for w, v in _ys(m, text))
    N = 480.0
    want = 0.0
    for a, b in ((1, 3), (2, 4)):
        on, off = (a, b) if y[a][0] == "ON" else (b, a)
        want += (2 * (y[on][1] - y[off][1]) / N) ** 2
    est, var, _ = m.ht_var(T["B"])
    assert var == pytest.approx(want, rel=1e-12), (var, want)


def chk_a_partial_mate_stays_in_its_pair(m):
    # ruling .138 (4): a partial window keeps its committed arm, its pair is one variance unit with actual frame
    # counts and probability 1/2 (the baseline enters as n_i b for each member); a mate that never ran leaves a
    # singleton; an emitter that gave the partial window its own coin fails the mates' check
    text = _b11_text([[{"n": [120, 120, 60], "coins": [(1, 1)]}]], _flat)
    recs = m.read(text)
    ws = [w for w in recs if m.b11_line(w)]
    assert m.arm_prob((ws[0], "ON"), (ws[2], "ON")) == 0.0 and m.arm_prob((ws[0], "ON"), (ws[2], "OFF")) == 0.5
    T = m.b11_terms(recs)
    assert T["units"] == (1, 1)
    y = dict((w["wi"], (w["arm"], v, w["n"])) for w, v in _ys(m, text))
    N, beta = 300.0, m.BETA_US
    t13 = 2 * ((y[1][1] - y[1][2] * beta) - (y[3][1] - y[3][2] * beta)) / N      # w1 ON, w3 OFF (1 - A)
    t24 = 2 * (y[2][1] - y[2][2] * beta) / N                                       # w2 ON, its mate never ran
    est, var, _ = m.ht_var(T["B"])
    assert est == pytest.approx(t13 + t24, rel=1e-12) and var == pytest.approx(t13 ** 2 + t24 ** 2, rel=1e-12)
    same = _b11_text([[{"n": [120, 120, 60], "coins": [(1, 1)]}]], _flat,
                     edit=lambda w: w.update(arm="ON") if w["wi"] == 3 else None)
    miss = m.window_reconcile(m.read(same))
    assert [x for x in miss if "do not carry one committed coin" in x], miss


def _two_points(**kw):
    return _b11_text([[{"n": [120, 120, 120, 120, 60], "coins": [(1, 0), (0, 1)]},
                       {"n": [120, 120, 120], "coins": [(0, 0)]}]], _flat, **kw)


def chk_reconcile_reports_every_point(m):
    # ruling .138, SHARED.md: no early stop; every point's totals and counts are compared, every mismatch named
    text = _two_points()
    assert m.window_reconcile(m.read(text)) == []
    bad = text.replace(" n=540 sF=", " n=541 sF=").replace(" windows=3 ", " windows=4 ")
    bad = re.sub(r"(p pt=1\.1\.1 .*? sC=)(\d+)", lambda mm: mm.group(1) + str(int(mm.group(2)) + 1), bad)
    bad = re.sub(r"(p pt=1\.1\.2 .*? sC=)(\d+)", lambda mm: mm.group(1) + str(int(mm.group(2)) + 1), bad)
    bad = bad.replace(" windows=5 ", " windows=6 ")
    miss = m.window_reconcile(m.read(bad))
    tot = [x for x in miss if "unplanted windows'" in x]
    cnt = [x for x in miss if "window lines, the point line counts" in x]
    assert len([x for x in tot if x.startswith("point 1.1.1:")]) == 2, miss          # n and sC
    assert len([x for x in tot if x.startswith("point 1.1.2:")]) == 1, miss          # sC
    assert len(cnt) == 2, miss                                                         # both points


def chk_vr5_window_zero(m):
    # method-v52.md:87: an OFF window executes no switched scope
    text = _b11_text(_one_run_games(), _c2_model, edit=lambda w: w.update(cS=7, cE=w["cE"] - 7)
                     if w["arm"] == "OFF" and w["wi"] == 1 else None)
    ok, bad = m.vr5_points(m.read(text))
    assert not ok and len([b for b in bad if " OFF: cS=7" in b]) == 2, bad


def chk_classify_half_width_rule(m):
    # method-v54.md:189: SID and FAIL need half-width <= 1.5 percent and the lower bound past 3 or 5 percent
    assert m.classify(3.0, 100, 50, 0) == "PASS"
    assert m.classify(4.0, 100, 1.5, 3.1) == "SID" and m.classify(4.0, 100, 1.6, 3.9) == "WITHHELD"
    assert m.classify(6.0, 100, 1.4, 5.1) == "FAIL" and m.classify(6.0, 100, 1.6, 5.9) == "WITHHELD"


def chk_classify_lower_bound_rule(m):
    assert m.classify(4.0, 100, 1.0, 3.0) == "WITHHELD" and m.classify(6.0, 100, 1.0, 4.5) == "WITHHELD"
    assert m.classify(6.0, 100, 1.0, 5.0) == "WITHHELD"


def chk_r_common_comparator(m):
    # ruling .137 (5): total common cost against (1 + r_U) D_common
    assert m.r_common_check(1.2, 0.3, 1.0) is False and m.r_common_check(1.31, 0.3, 1.0) is True


def chk_full_profile_not_applied_to_partials(m):
    # ruling .139 (1): the partial stratum is estimated directly; the old .138 (5) profile reads 2.5 on C4's case
    chk_c4_recovers_3_5(m)


def _aa(arm, pred, pos, partial, j):
    # fixed A/A outcomes: nothing depends on either arm
    return 0, B11_PC * (pos + j % 3), 0


def chk_h_p_cross_check(m):
    # c5.out:51-55, ruling .140: under fixed A/A outcomes the uncentred partial charge is H_P = (2/N) sum over the
    # ordinary partial windows of S_(i-1) C_i; the general HT (terms aggregated on their signed coins) must give it
    games = [[{"n": [120, 60], "coins": [(1, 0)]}, {"n": [120] * 5 + [30], "coins": [(0, 1), (1, 1)]},
              {"n": [120, 120, 90], "coins": [(1, 1)]}],
             [{"n": [120, 120, 120, 100], "coins": [(0, 0)]}, {"n": [60], "coins": [(1, 0)]}]]
    recs = m.read(_b11_text(games, _aa))
    T = m.b11_terms(recs)
    want = 0.0
    for w in recs:
        if m.b11_line(w) and w["partial"] and w["pred"] != "none":
            want += (1 if w["pred"] == "ON" else -1) * (sum(w["q"]) - (0 if w["arm"] == "ON" else w["cR"]))
    want *= 2.0 / T["N"]
    assert want != 0
    assert m.ht_var(T["hp"])[0] == pytest.approx(want, rel=1e-12), (m.ht_var(T["hp"])[0], want)
    assert all(len(e) == 2 for evs in T["hp"].values() for e in evs)


def _arm_only(arm, pred, pos, partial, j):
    return (B11_PC * 3 if arm == "ON" else 0), 0, 0


def chk_baseline_frozen_q_minus_2(m):
    # ruling .140 (4): a window of run q is centred only on ordinary windows of runs q-2 and earlier. Here run 2's
    # partial first window has run 1's last window as predecessor; centred on run q-1 its baseline would be that
    # predecessor, whose coin moves it, and both carryover estimates would leave their true 0
    games = [[{"n": [120] * 4 + [60], "coins": [(x[0], x[1]), (x[2], 0)]}] for x in _enum(3)]
    e = m.b11_estimate(m.read(_b11_text(games, _arm_only)))
    assert _pct(e["B"][0]) == pytest.approx(3.0, abs=1e-6), e["B"]
    assert _pct(e["c_on"][0]) == pytest.approx(0.0, abs=1e-6), e["c_on"]
    assert _pct(e["c_off"][0]) == pytest.approx(0.0, abs=1e-6), e["c_off"]


def _raises(fn, word):
    """True when fn() raises MarkerRefused with that word (a check, not pytest.raises, so a mutant's miss is an
    AssertionError the mutant battery reads)."""
    try:
        fn()
    except Exception as x:          # noqa: BLE001
        return getattr(x, "word", None) == word
    return False


def chk_marker_whole_line(m):
    # P3 via the integrator: the FrameTime marker is a prefix of the FrameTimeRef one; each counts only as the whole
    # line, so a Ref line is never a FrameTime marker
    text = _b11_text(_one_run_games(), _c2_model)
    ft = LOG_PREFIX + "[FRAME-TIME] " + m.MARK_FT
    ref = LOG_PREFIX + "[FRAME-TIME] " + m.MARK_REF
    only_ref = text.replace(ft, ref)
    assert _raises(lambda: m.build_marker(only_ref, "measurement", "a"), "MARKER-WRONG-ROLE")
    assert _raises(lambda: m.build_marker(text + "\n" + ref, "measurement", "a"), "MARKER-WRONG-ROLE")
    assert _raises(lambda: m.build_marker(text.replace(ft, ft + " SCR_FT_REF=NOCOLLECTORS"), "measurement", "a"),
                   "MARKER-UNKNOWN")
    assert _raises(lambda: m.build_marker(text.replace(ft, ft + "Ref"), "measurement", "a"), "MARKER-UNKNOWN")
    assert _raises(lambda: m.build_marker(text.replace(ft, ft + "Ref"), "reference", "a"), "MARKER-UNKNOWN")
    assert _raises(lambda: m.build_marker(text.replace(ft, "[FRAME-TIME] " + m.MARK_FT), "measurement", "a"),
                   "MARKER-UNKNOWN")
    m.build_marker(text, "measurement", "a")
    m.build_marker(only_ref, "reference", "a")
    m.build_marker(text.replace(ft, ft + "  "), "measurement", "a")


def chk_token_open1_and_continuity(m):
    # SHARED.md (md5 2119eb2e): per type open1 >= 0, and each window's open0 = the game's previous window's open1. The
    # fixture is P1's mutant (hash's service counted on log): every type's conservation sum still holds
    def moved(w):
        if w["pt"] == "1.1.1" and w["wi"] == 2:
            w["tok"] = "log:0,1,0,2,0,0,-1;hash:0,1,0,0,0,0,1;recv:0,0,0,0,0,0,0;sock:0,0,0,0,0,0,0"
    recs = m.read(_two_points(edit=moved))
    w = [r for r in recs if m.b11_line(r) and r["pt"] == "1.1.1" and r["wi"] == 2][0]
    assert all(x[0] + x[1] + x[2] == x[3] + x[4] + x[5] + x[6] for x in m._typed(w["tok"], 7).values())
    miss = m.window_reconcile(recs)
    assert [x for x in miss if "window 1.1.1.2: log open1=-1 is below 0" in x], miss
    assert [x for x in miss if "window 1.1.1.3: log open0=0, the game's previous window's open1=-1" in x], miss
    assert [x for x in miss if "window 1.1.1.3: hash open0=0, the game's previous window's open1=1" in x], miss
    assert m.window_reconcile(m.read(_two_points())) == []


def _recv_wu(w):
    # recv 2 units and 600 cycles a window, log 100, hash 50, sock 30 (all us at f_hat 1e6)
    w["wu"] = "log:1:100;hash:1:50;recv:2:600;sock:2:30"


def chk_writers_recv_never_added(m):
    # SHARED.md (md5 2119eb2e): log, hash and sock add; recv is inside C and is never added a second time
    recs = m.read(_b11_text(_one_run_games(), _c2_model, edit=_recv_wu))
    wa = m.writer_added(m.b11_terms(recs))
    assert wa["ON"] == pytest.approx(180.0 / 120, rel=1e-12) and wa["OFF"] == pytest.approx(180.0 / 120, rel=1e-12), wa


def _rows(m, text, t=None, peer=None, first_game=1):
    """validity_set of one log (its peer the same log unless given) as {guard: (ok, reasons)}; VR1 at t."""
    peer = text if peer is None else peer
    return dict((n, (ok, w)) for n, ok, w in m.validity_set(m.read(text), text, m.read(peer), peer, t, "a",
                                                            first_game))


def chk_p_line_faults_withhold(m):
    # SHARED.md (md5 2119eb2e) and ruling R6-A3.11.149 (5)(a): recv_offmain, ledger_cycle_miss and sock_main nonzero
    # fail the validity set's p-line faults row (which withholds B1 for the seat); printed 0, the row holds
    assert _rows(m, _b11_text(_one_run_games(), _flat))["p-line faults"] == (True, [])
    for k in ("recv_offmain", "ledger_cycle_miss", "sock_main"):
        ok, why = _rows(m, _b11_text(_one_run_games(), _flat).replace(" %s=0" % k, " %s=3" % k, 1))["p-line faults"]
        assert not ok and why == ["%s nonzero or not printed at 1.1.1" % k], (k, why)


def chk_ref_known_by_marker_not_by_na(m):
    # to-p2-r4.md (4): a FrameTimeRef log prints sock:NA:NA but is known only by its marker; a measurement log printing
    # sock:NA:NA is read (not refused as a format fault) and withholds B1 for the seat
    text = _b11_text(_one_run_games(), _flat, wu="log:0:0;hash:0:0;recv:0:0;sock:NA:NA")
    recs = m.read(text)
    m.build_marker(text, "measurement", "a")
    assert m.window_reconcile(recs) == []
    e = m.b11_estimate(recs)
    assert e["T"]["wu_na"] == ["sock"], e["T"]["wu_na"]
    # in sitting V (SHARED.md V6) NA writer cycles withhold B1 for the seat
    v = _v(m, _v_text(edit=lambda w: w.update(wu="log:1:0;hash:1:0;recv:2:0;sock:NA:NA")))
    assert "a wu type prints NA cycles (sock)" in v["why"], v["why"]
    assert _v(m, _v_text())["why"] == []


def chk_v4_lower_bound_at_lower_ends(m):
    # the integrator's ruling on the hand-back (2): the point design's SID/FAIL lower bound takes dC at its lower end
    # and the charges at 0; the base fixture's U is in the SID band but its lower bound is not above 3 percent
    out = m.report(_log(), peer=_peer_text())
    assert re.search(r"^VERDICT B1 WITHHELD: U [0-9.]+ us", out, re.M), [x for x in out.splitlines() if "VERDICT" in x]


def chk_r_common_d_common_and_corrected_r_u(m):
    # the integrator's ruling on the hand-back (4): D_common = (cR + cW) per frame over ordinary full OFF windows; r_U
    # from the carryover-corrected external contrast (C2: B 2.5, J 3.25, D 1 percent, so 2.25 and not 1.5)
    recs = m.read(_b11_text(_one_run_games(), _c2_model, cw=B11_PC // 4))
    e = m.b11_estimate(recs)
    assert _pct(m.ht_var(e["T"]["D"])[0]) == pytest.approx(1.0, abs=1e-9)
    assert e["r_hat"] == pytest.approx(2.25, abs=1e-9), e["r_hat"]
    assert e["r_u"] >= e["r_hat"]
    recs = m.read(_b11_text(_one_run_games(), _c3_model, cw=B11_PC // 4))
    ofw = [w for w in recs if m.b11_line(w) and w["arm"] == "OFF" and w["partial"] == 0]
    want = sum(w["cR"] + w["cW"] for w in ofw) / sum(w["n"] for w in ofw)
    assert sum(w["cR"] for w in ofw) > 0
    assert m.b11_estimate(recs)["dcommon"] == pytest.approx(want, rel=1e-12)


def chk_own_split_withholds(m):
    # the integrator's ruling on the hand-back (3) and ruling R6-A3.11.149 (5)(a): any nonzero own_split fails the
    # validity set's own_split row (which withholds B1 for the seat)
    games = [[{"n": [120] * 4, "coins": [(1, 0)]}, {"n": [120, 60], "coins": [(0, 0)], "own_split": 1}]]
    assert _rows(m, _b11_text(games, _flat))["own_split"] == (False, ["ownership faults at 1.1.2"])
    assert _rows(m, _b11_text([[{"n": [120] * 4, "coins": [(1, 0)]}]], _flat))["own_split"] == (True, [])


# ----------------------------------------------------------------------------- V6 (SHARED.md "V6: the direct bound")
# Sitting-V fixtures are forced ON in every window. Cycles are us (f_hat 1e6); every frame lasts B11_T us.

V6_BYTES = dict(aC=12000000, aW=1000, aR=2000, aS=3000, aP=500, aX=1500, wa="log:400;hash:300;sock:300")


def _v_model(s=30, r=20):
    def model(arm, pred, pos, partial, j):
        return s, 0, r
    return model


def _v_cls(cp=5, recv=1, wlog=2, whash=3, wsock=4, cx=7, bytes_=None):
    """V6 values per window, per frame: P's scopes cp, wu's recv cycles recv, the off-thread log, hash and sock cycles,
    X cx + (the game mod 3); the window's bytes bytes_ (V6_BYTES)."""
    def v6(w):
        g, n = int(w["pt"].split(".")[0]), w["n"]
        d = dict(bytes_ or V6_BYTES)
        d.update(cP_pf=cp, cX_pf=cx + g % 3,
                 wu="log:1:%d;hash:1:%d;recv:2:%d;sock:3:%d" % (wlog * n, whash * n, recv * n, wsock * n))
        return d
    return v6


def _v_text(games=P.LAST_GAME, s=30, cls=None, pts=None, **kw):
    """A complete sitting-V log (ruling R6-A3.11.149 (5)(b): the validity set applies): game 0 and the measured games,
    each one point of four full windows, force=ON on every settled line and every window ON, S s and R 20 per frame,
    W 10 per frame, the V6 values of cls (_v_cls()). pts(g) may give a measured game's points instead."""
    gs = [(pts and pts(g + 1)) or [{"n": [120] * 4, "coins": [(1, 0)]}] for g in range(games)]
    return _b11_text(gs, _v_model(s), force="ON", cw=10, v6=cls or _v_cls(), sitting=True, **kw)


def _c_text(model=None, reps=P.LAST_GAME // 4, **kw):
    """A complete sitting-C log: game 0 and the measured games of _one_run_games (every (A, B) once per four games),
    alternating as built; model as _b11_text's (_c_cost(0) by default)."""
    return _b11_text(_one_run_games(reps=reps), model or _c_cost(0), sitting=True, **kw)


def _on(m, v1, v2):
    """report_on of two seats named a and b."""
    return m.report_on({"a": v1, "b": v2})


def _comb(m, v1, v2, c1, c2, **kw):
    """The combining step for seats a (v1, c1) and b (v2, c2), each paired by its name."""
    return m.combine({"a": v1, "b": v2}, {"a": c1, "b": c2}, **kw)


def _v_hand(games=P.LAST_GAME, s=30, cp=5, recv=1, cx=7):
    """U by hand for _v_text's fixture: per game u_g = D + P + S + X + G_cap with D = S + R + W, P = max(cP, recv), S =
    log + hash + sock, X = cx + g mod 3, G_cap = bK / (aC - bK) x T; and G_cap."""
    wa = 400 + 300 + 300
    bk = 4 * (1000 + 2000 + 3000 + 500 + 1500 + wa)
    gc = bk / (4 * 12000000 - bk) * B11_T
    return [(s + 20 + 10) + max(cp, recv) + (2 + 3 + 4) + (cx + g % 3) + gc for g in range(1, games + 1)], gc


def _p_sub(text, pt, old, new):
    """text with old replaced by new on point pt's p line alone (that line must hold old)."""
    key = "[FRAME-TIME] p pt=%s " % pt
    lines = text.split("\n")
    hit = [i for i, x in enumerate(lines) if key in x and old in x]
    assert len(hit) == 1, (pt, old, hit)
    lines[hit[0]] = lines[hit[0]].replace(old, new, 1)
    return "\n".join(lines)


def _sub1(text, old, new):
    """text with its one occurrence of old replaced by new (old must occur exactly once)."""
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new)


def _v(m, text, peer=None):
    """sitting_v of one seat's log (seat a), its peer the same log unless given."""
    peer = text if peer is None else peer
    return m.sitting_v(m.read(text), text, m.read(peer), peer, "V:a")


def _c_cost(on=0):
    """A sitting-C model: ON costs `on` cycles per frame of class S, and every window's C° per frame is otherwise the
    frozen baseline, so a window's centred value is its own cost alone."""
    def model(arm, pred, pos, partial, j):
        return (on if arm == "ON" else 0), int(P.BETA_US) - B11_BASE, 0
    return model


def _p_only(edit=None):
    # E4's H6: a sitting-C fixture whose arms differ only in P. recv is gated by the seat's own arm, so class P runs
    # in ON windows only; with C° = C - G - W - P the windows' C° is the same in both arms
    return _c_text(v6=lambda w: {"cP_pf": 50 if w["arm"] == "ON" else 0}, edit=edit)


def _classes(out):
    seats = dict(re.findall(r"^VERDICT B1 seat (\S+) (\w+)", out, re.M))
    return seats, re.findall(r"^VERDICT B1 worse seat: seat (\S+) (\w+)$", out, re.M)


def _verdict(out, seat):
    """The seat's VERDICT B1 line."""
    ln = [x for x in out.splitlines() if x.startswith("VERDICT B1 seat %s " % seat)]
    assert len(ln) == 1, (seat, out)
    return ln[0]


def _word_refused(fn, word):
    """True when fn() raises an exception whose text holds word (a check, so a mutant's miss is an AssertionError)."""
    try:
        fn()
    except Exception as x:          # noqa: BLE001
        return word in str(x)
    return False


def chk_q_leaves_p_once(m):
    # m1, the fixture of E4's H6 (n2e4.out:22 against changes.md:146): it asserts the corrected q = C - G - W - P itself
    # and the contrast end to end, with P removed exactly once. A q keeping P, or losing it twice, is named by the
    # invariant, so such a line never reaches a contrast; the end-to-end contrast of the P-only fixture is 0
    good = m.read(_p_only())
    on = [w for w in good if m.b11_line(w) and w["arm"] == "ON"]
    assert on and all(w["cP"] == 50 * w["n"] and sum(w["q"]) == w["sC"] - w["cG"] - w["cW"] - w["cP"] for w in on)
    assert m.window_reconcile(good) == []
    e = m.b11_estimate(good)
    assert abs(e["B"][0]) < 1e-9 and abs(e["J"][0]) < 1e-9, (e["B"], e["J"])
    for sign in (1, -1):
        bad = m.read(_p_only(edit=lambda w, s=sign: w.update(q=[w["q"][0] + s * w["cP"]] + w["q"][1:])
                             if w["cP"] else None))
        miss = m.window_reconcile(bad)
        assert len([x for x in miss if "is not sC-cG-cW-cP" in x]) == len(on), (sign, miss)
        # what the invariant keeps out: such a q would move the contrast by the whole P
        assert m.b11_estimate(bad)["B"][0] == pytest.approx(sign * 50, abs=1e-6)
    v = _v_text()
    out = _comb(m, v, v, _p_only(), _p_only())
    assert re.search(r"^V6 CROSS-CHECK seat a: contrast -?0\.000 us per frame", out, re.M), out
    assert _classes(out) == ({"a": "PASS", "b": "PASS"}, [("a", "PASS")]), out
    # end to end: a sitting-C log whose q keeps P fails the line invariants, so the seat has no cross-check (ruling
    # R6-A3.11.149 (5)(c)): its contrast refutes nothing and B1 is WITHHELD
    keep = _p_only(edit=lambda w: w.update(q=[w["q"][0] + w["cP"]] + w["q"][1:]) if w["cP"] else None)
    out = _comb(m, v, v, keep, _p_only())
    assert re.search(r"^V6 VALIDITY sitting C seat a line invariants FAIL: window \d+\.1\.1\.\d: sum\(q\)=\d+ is not "
                     r"sC-cG-cW-cP=", out, re.M), out
    assert re.search(r"^VERDICT B1 seat a WITHHELD: sitting C gives no cross-check until it has run again; cross-check "
                     r"unavailable \([^)]*line invariants", _verdict(out, "a")), out
    assert _classes(out)[0] == {"a": "WITHHELD", "b": "PASS"}, out


def chk_class_sum_holds_cp_and_cx(m):
    # m2: sC = cG + cW + cR + cS + cP + cX + cE, an NA cG counting 0; X stays in C°
    for cg in (None, lambda w: None):
        recs = m.read(_b11_text(_one_run_games(), _c2_model, cg=cg, v6=lambda w: {"cP_pf": 3, "cX_pf": 4}))
        assert m.window_reconcile(recs) == []
        w = [r for r in recs if m.b11_line(r)][0]
        assert w["cP"] == 360 and w["cX"] == 480
        assert w["sC"] == (w["cG"] or 0) + w["cW"] + w["cR"] + w["cS"] + w["cP"] + w["cX"] + w["cE"]


def chk_report_on_hand_computed_u(m):
    # m3, m5, m6 and ruling R6-A3.11.147 (7): report_on gives the hand-computed U on a both-ON fixture; U = D + P + S +
    # X + G_cap per game, through fw_interval at Z_END as built; each term and each S type is nonzero and distinct
    text = _v_text()
    lines, (va, vb) = _on(m, text, text)
    ug, gc = _v_hand()
    U, hw, df = P.fw_interval([(u, 480) for u in ug], P.Z_END)
    assert va["why"] == [] and vb["why"] == [], (va["why"], vb["why"])
    assert hw > 0 and va["U"] == pytest.approx(U, abs=1e-6) and va["hw"] == pytest.approx(hw, abs=1e-6)
    assert va["df"] == df and va["U_hi"] == pytest.approx(U + hw, abs=1e-6)
    t = va["terms"]
    assert t["D"] == pytest.approx(60) and t["P"] == pytest.approx(5) and t["X"] == pytest.approx(8)
    assert t["S"] == pytest.approx({"log": 2, "hash": 3, "sock": 4}) and t["G"] == pytest.approx(gc, rel=1e-12)
    assert t["D"] + t["P"] + sum(t["S"].values()) + t["X"] + t["G"] == pytest.approx(va["U"], abs=1e-6)
    assert va["L"] == pytest.approx(65, abs=1e-6)
    assert va["T_on"] == pytest.approx(B11_T) and va["T_ref"] == pytest.approx(B11_T - va["U_hi"], abs=1e-6)
    assert va["cls"] == "PASS"
    want = "V6 U %.3f us per live frame = D 60.000 + P 5.000 + S 9.000 (log 2.000, hash 3.000, sock 4.000) + X 8.000" \
           % va["U"]
    assert [x for x in lines if x.startswith(want)], lines


def chk_p_is_the_larger_of_cp_and_recv(m):
    # m4, ruling R6-A3.11.147 (3)(g): P is the larger of cP and wu's recv cycles; L takes cP alone
    v = _v(m, _v_text(cls=_v_cls(cp=2, recv=9)))
    ug, _ = _v_hand(cp=2, recv=9)
    assert v["terms"]["P"] == pytest.approx(9, abs=1e-9) and v["U"] == pytest.approx(sum(ug) / len(ug), abs=1e-6)
    assert v["L"] == pytest.approx(62, abs=1e-6)


def chk_forced_log_is_no_contrast_input(m):
    # m7: sitting C alternates as built; a log forced ON or OFF, or one not printing force=, is refused as a contrast
    # input by the as-built report and by the combining step (the arms still alternate here: only force= tells)
    m.contrast_input(m.read(_b11_text(_one_run_games(), _c2_model)))
    for f in ("ON", "OFF", None):
        recs = m.read(_b11_text(_one_run_games(), _c2_model, force=f, force_arms=False))
        assert _word_refused(lambda: m.contrast_input(recs), "FORCED-INPUT"), f
        assert _word_refused(lambda: m.b11_report(recs), "FORCED-INPUT"), f
    v = _v_text()
    forced = _c_text(force="ON", force_arms=False)
    out = _comb(m, v, v, forced, _c_text())
    assert re.search(r"WITHHELD: sitting C gives no cross-check until it has run again; cross-check unavailable "
                     r"\(contrast: FORCED-INPUT", _verdict(out, "a")), out
    assert _classes(out)[0] == {"a": "WITHHELD", "b": "PASS"}, out


def _off_last(w):
    if w["pt"] == "3.1.1" and w["wi"] == 4:
        w["arm"] = "OFF"


def chk_sitting_v_is_forced_on(m):
    # m8: B1 is withheld for a seat when a sitting-V window prints arm=OFF, or a game's settled line another force=
    # than ON, on either seat; under force=ON mates carry one coin field and not one arm
    clean = _v_text()
    assert _v(m, clean)["why"] == []
    off = _v_text(edit=_off_last)
    assert "sitting V: this seat prints arm=OFF in 1 windows (3.1.1.4)" in _v(m, off, clean)["why"]
    assert "sitting V: the peer seat prints arm=OFF in 1 windows (3.1.1.4)" in _v(m, clean, off)["why"]
    nf = re.sub(r"(settled g=3 [^\n]*) force=ON", r"\1 force=none", clean)
    assert "sitting V: this seat's settled lines print another force= than ON (g=3 force=none)" in _v(m, nf, clean)["why"]
    assert ("sitting V: the peer seat's settled lines print another force= than ON (g=3 force=none)"
            in _v(m, clean, nf)["why"])


# (what, the sitting-V log, the reason sitting_v must give): m9's NA, pin, ab_back and controls, each boot line
# missing, R-SCOPE's two lines, bE, the as-built p line and wu faults, own_split, the line invariants and VR1
V_SPOILS = (
    ("aC NA", lambda: _v_text(edit=lambda w: w.update(aC=None) if (w["pt"], w["wi"]) == ("2.1.1", 1) else None),
     "an a* or wa value prints NA in 1 windows (2.1.1.1)"),
    ("aX NA", lambda: _v_text(edit=lambda w: w.update(aX=None) if (w["pt"], w["wi"]) == ("2.1.1", 3) else None),
     "an a* or wa value prints NA in 1 windows (2.1.1.3)"),
    ("wa NA", lambda: _v_text(edit=lambda w: w.update(wa="log:400;hash:300;sock:NA") if (w["pt"], w["wi"]) ==
                              ("4.1.1", 2) else None), "an a* or wa value prints NA in 1 windows (4.1.1.2)"),
    ("pin", lambda: _v_text(boot={"alloc": "alloc pin=differs planted=1048600/1048576 empty=0"}),
     "the counter's pin differs or is not read (pin=differs)"),
    ("ab_back", lambda: _p_sub(_v_text(), "1.1.1", " ab_back=0 ", " ab_back=2 "),
     "ab_back above 0 or not printed at 1.1.1"),
    ("K1 planted", lambda: _v_text(boot={"alloc": "alloc pin=ok planted=1052673/1048576 empty=0"}),
     "control K1 out of range (planted median 1052673 for 1048576 asked"),
    ("K1 empty", lambda: _v_text(boot={"alloc": "alloc pin=ok planted=1048600/1048576 empty=8"}),
     "control K1 out of range (planted median 1048600 for 1048576 asked (needs 1048576 to 1052672), empty median 8"),
    ("K2", lambda: _v_text(boot={"scope plant": "scope plant asked=2000 got=2101"}), "control K2 out of range (asked 2000"),
    ("K3", lambda: _v_text(boot={"nest": "nest plant asked=2000 x=2020 e=1899 p=2005"}),
     "control K3 out of range (asked 2000 us (needs 2000), read x 2020, e 1899"),
    # ruling R6-A3.11.151 (2) class C, F5: the plants are judged at 2000 us, never at the log's own asked=
    ("K2 own asked", lambda: _v_text(boot={"scope plant": "scope plant asked=4000 got=4000"}),
     "control K2 out of range (asked 4000 us (needs 2000), class S read 4000 us (needs 1900 to 2100))"),
    ("K2 below", lambda: _v_text(boot={"scope plant": "scope plant asked=2000 got=1899"}),
     "control K2 out of range (asked 2000 us (needs 2000), class S read 1899 us (needs 1900 to 2100))"),
    ("K3 own asked", lambda: _v_text(boot={"nest": "nest plant asked=4000 x=4000 e=4000 p=4000"}),
     "control K3 out of range (asked 4000 us (needs 2000), read x 4000, e 4000, p 4000 us (each needs 1900 to 2100))"),
    # and any other asked= is out of range, its reading in the band or not
    ("K2 asked another", lambda: _v_text(boot={"scope plant": "scope plant asked=4000 got=2010"}),
     "control K2 out of range (asked 4000 us (needs 2000), class S read 2010 us (needs 1900 to 2100))"),
    ("K3 asked another", lambda: _v_text(boot={"nest": "nest plant asked=4000 x=2020 e=1990 p=2005"}),
     "control K3 out of range (asked 4000 us (needs 2000), read x 2020, e 1990, p 2005 us (each needs 1900 to 2100))"),
    # ruling R6-A3.11.151 (2) class B: the fault fields given a rule
    ("ab_retry", lambda: _p_sub(_v_text(), "1.1.1", " ab_retry=0 ", " ab_retry=3 "),
     "ab_retry above 0 or not printed at 1.1.1"),
    ("span_class_overflow", lambda: _p_sub(_v_text(), "2.1.1", " span_class_overflow=0 ", " span_class_overflow=1 "),
     "p-line faults: span_class_overflow nonzero or not printed at 2.1.1"),
    # ruling R6-A3.11.152 (2)(h): a frame whose plant state is not its window's first frame's
    ("plant_mixed", lambda: _p_sub(_v_text(), "3.1.1", " plant_mixed=0 ", " plant_mixed=1 "),
     "p-line faults: plant_mixed nonzero or not printed at 3.1.1"),
    ("off_g", lambda: _p_sub(_v_text(), "1.1.1", " off_g=0 ", " off_g=5 "),
     "VR5's window counters: off_g above 0 or not printed at 1.1.1"),
    ("off_gn", lambda: _p_sub(_v_text(), "1.1.1", " off_gn=0 ", " off_gn=1 "),
     "VR5's window counters: off_gn above 0 or not printed at 1.1.1"),
    ("off_on", lambda: _p_sub(_v_text(), "3.1.1", " off_on=0 ", " off_on=1 "),
     "VR5's window counters: off_on above 0 or not printed at 3.1.1"),
    ("on_guarded", lambda: _p_sub(_v_text(), "1.1.1", " on_guarded=0 ", " on_guarded=2 "),
     "VR5's window counters: on_guarded above 0 or not printed at 1.1.1"),
    ("arm file", lambda: _settled_add(_v_text(), 3, " problems=bad-seed"),
     "complete sitting: settled g=3 problems=bad-seed: the arm file was not read as written"),
    ("alloc gone, pin", lambda: _v_text(boot={"alloc": None}),
     "the counter's pin differs or is not read (0 'alloc' lines (needs exactly 1))"),
    ("alloc gone, K1", lambda: _v_text(boot={"alloc": None}), "control K1 out of range (0 'alloc' lines (needs exactly 1))"),
    ("scope plant gone", lambda: _v_text(boot={"scope plant": None}),
     "control K2 out of range (0 'scope plant' lines (needs exactly 1))"),
    ("nest gone", lambda: _v_text(boot={"nest": None}), "control K3 out of range (0 'nest plant' lines (needs exactly 1))"),
    ("photon gone", lambda: _v_text(boot={"photon": None}),
     "R-SCOPE's patches line out of range (0 'photon patches' lines (needs exactly 1))"),
    ("census gone", lambda: _v_text(boot={"scope census": None}),
     "R-SCOPE's census line out of range (0 'scope census' lines (needs exactly 1))"),
    # ruling R6-A3.11.149 (1), (6) 4: the ten typed names, each once, and n their count
    ("photon entry", lambda: _v_text(boot={"photon": "photon patches n=9 names=" + ",".join(
        x for x in P.PHOTON_ENTRIES if x != "LoadBalancingClient.OnMessage")}),
     "R-SCOPE's patches line out of range (n=9 for 9 names; not attached: LoadBalancingClient.OnMessage)"),
    ("photon count", lambda: _v_text(boot={"photon": dict(V6_BOOT)["photon"].replace("n=10", "n=11")}),
     "R-SCOPE's patches line out of range (n=11 for 10 names)"),
    ("photon alien", lambda: _v_text(boot={"photon": "photon patches n=11 names=" + ",".join(P.PHOTON_ENTRIES)
                                            + ",PhotonPeer.EstablishEncryption"}),
     "R-SCOPE's patches line out of range (n=11 for 11 names; not of the ten: PhotonPeer.EstablishEncryption)"),
    ("photon twice", lambda: _v_text(boot={"photon": "photon patches n=11 names=" + ",".join(
        P.PHOTON_ENTRIES + P.PHOTON_ENTRIES[:1])}),
     "R-SCOPE's patches line out of range (n=11 for 11 names; named twice: PhotonPeer.DispatchIncomingCommands)"),
    # ruling R6-A3.11.152, G1's class: the names as written, in the emitter's order, no entry dropped
    ("photon reordered", lambda: _v_text(boot={"photon": "photon patches n=10 names=" + ",".join(
        P.PHOTON_ENTRIES[1:2] + P.PHOTON_ENTRIES[:1] + P.PHOTON_ENTRIES[2:])}),
     "R-SCOPE's patches line out of range (n=10 for 10 names; not in the emitter's order)"),
    ("photon empty entry", lambda: _v_text(boot={"photon": "photon patches n=10 names=" + ",".join(
        P.PHOTON_ENTRIES[:4] + ("",) + P.PHOTON_ENTRIES[4:])}),
     "R-SCOPE's patches line out of range (n=10 for 11 names; not of the ten: (an empty entry))"),
    ("photon untyped", lambda: _v_text(boot={"photon": "photon patches n=10 names=" + ",".join(
        x.split(".")[1] for x in P.PHOTON_ENTRIES)}),
     "R-SCOPE's patches line out of range (n=10 for 10 names; not attached: PhotonPeer.DispatchIncomingCommands"),
    ("photon failed", lambda: _v_text(boot={"photon": "photon patches report failed: boom"}),
     "R-SCOPE's patches line out of range (the patch report failed (the line prints no n=))"),
    ("census wrapped", lambda: _v_text(boot={"scope census": "scope census entries=40 wrapped=39"}),
     "R-SCOPE's census line out of range (entries 40, wrapped 39)"),
    ("census threw", lambda: _v_text(boot={"scope census": "scope census entries=40 wrapped=40 "
                                                           "failed=NullReferenceException"}),
     "R-SCOPE's census line out of range (entries 40, wrapped 40; the census threw (failed=NullReferenceException))"),
    ("bE", lambda: _v_text(cls=_v_cls(bytes_=dict(V6_BYTES, aC=9000))), "bE is 0 or below in games 1, 2, 3, 4, 5, 6"),
    ("recv_offmain", lambda: _p_sub(_v_text(), "1.1.1", " recv_offmain=0 ", " recv_offmain=1 "),
     "p-line faults: recv_offmain nonzero or not printed at 1.1.1"),
    ("sock_main", lambda: _p_sub(_v_text(), "4.1.1", " sock_main=0 ", " sock_main=2 "),
     "p-line faults: sock_main nonzero or not printed at 4.1.1"),
    ("wu NA", lambda: _v_text(edit=lambda w: w.update(wu="log:1:240;hash:1:360;recv:2:120;sock:3:NA")
                              if (w["pt"], w["wi"]) == ("5.1.1", 1) else None), "a wu type prints NA cycles (sock)"),
    ("own_split", lambda: _p_sub(_v_text(), "1.1.1", " own_split=0 ", " own_split=1 "),
     "own_split: ownership faults at 1.1.1"),
    ("line invariant", lambda: _v_text(edit=lambda w: w.update(sC=w["sC"] + 1) if (w["pt"], w["wi"]) == ("2.1.1", 3)
                                       else None), "line invariants: window 2.1.1.3: sC="),
    ("VR1", lambda: _v_text(fpscap=False), "VR1: no '[FPSCAP] held by frame-time calibration' line"),
)


def chk_sitting_v_withholds_the_counter_and_controls(m):
    # m9 and the rest of SHARED.md V6's list (B1 is WITHHELD for a seat when), each by its own reason; the clean log
    # and the controls' edges in range withhold nothing
    for text in (_v_text(), _v_text(boot={"alloc": "alloc pin=ok planted=1052672/1048576 empty=0",
                                          "scope plant": "scope plant asked=2000 got=2100",
                                          "nest": "nest plant asked=2000 x=1900 e=2100 p=2000"})):
        assert _v(m, text)["why"] == [], _v(m, text)["why"]
    for what, fn, want in V_SPOILS:
        why = _v(m, fn())["why"]
        assert [x for x in why if x.startswith(want)], (what, want, why)


def chk_t_ref_is_t_on_minus_u_hi(m):
    # m10, ruling R6-A3.11.147 (3)(e): T_ref = T_on - U_hi, and the class reads it: U_hi within 3 percent of T_on but
    # above 3 percent of T_ref is no PASS (its L is below 3 percent, so the band is unresolved)
    v = _v(m, _v_text())
    assert v["U_hi"] > 0 and v["T_ref"] == pytest.approx(v["T_on"] - v["U_hi"], abs=1e-9)
    v = _v(m, _v_text(s=5103))
    assert 0.03 * v["T_ref"] < v["U_hi"] <= 0.03 * v["T_on"] and v["cls"] == "WITHHELD", (v["U_hi"], v["T_ref"], v["cls"])


def chk_six_games_at_least(m):
    # m12: fewer than 6 games withholds B1
    assert not [x for x in _v(m, _v_text(games=6))["why"] if "games remain" in x]
    assert "5 games remain (needs at least 6)" in _v(m, _v_text(games=5))["why"]


def chk_combine_four_classes(m):
    # m11 and ruling R6-A3.11.147 (7): the combining step's class on four fixtures (PASS, SID, WITHHELD by a contrast
    # whose lower end is above U_hi, WITHHELD by a missing counter), per seat, and the worse seat; ruling R6-A3.11.149
    # (5)(e): the cross-check's state on each verdict line
    c0 = _c_text()
    v = _v_text()
    out = _comb(m, v, v, c0, c0)
    assert _classes(out) == ({"a": "PASS", "b": "PASS"}, [("a", "PASS")]), out
    assert re.search(r"; cross-check not refuted(, weakened by [^;]+)?$", _verdict(out, "a")), out
    out = _comb(m, _v_text(s=6000), v, c0, c0)
    assert _classes(out) == ({"a": "SID", "b": "PASS"}, [("a", "SID")]), out
    out = _comb(m, v, v, c0, _c_text(_c_cost(20000)))
    assert _classes(out) == ({"a": "PASS", "b": "WITHHELD"}, [("b", "WITHHELD")]), out
    assert re.search(r"^VERDICT B1 seat b WITHHELD: the contrast's lower end [0-9.]+ us is above U_hi [0-9.]+ us \(U is "
                     r"refuted\); cross-check REFUTED$", _verdict(out, "b")), out
    out = _comb(m, _v_text(boot={"alloc": None}), v, c0, c0)
    assert _classes(out) == ({"a": "WITHHELD", "b": "PASS"}, [("a", "WITHHELD")]), out
    assert "the counter's pin differs or is not read (0 'alloc' lines" in _verdict(out, "a")
    out = _comb(m, v, _v_text(edit=lambda w: w.update(aC=None)), c0, c0)
    assert _classes(out) == ({"a": "PASS", "b": "WITHHELD"}, [("b", "WITHHELD")]), out


def chk_r_gc_numbers(m):
    # R-GC's numbers (SHARED.md V6): collections per MB of aC in sitting C's ON and OFF windows; the collectors' bytes
    # over sitting V against heap= at its end; and sitting C's u_g from its ON windows beside sitting V's (R-WORK)
    # sitting C: ON costs 30 us per frame of class S, so its ON windows' u_g is 30 and both arms' would be 15
    c = _c_text(_c_cost(30), v6=lambda w: {"gcn": 3 if w["arm"] == "ON" else 1, "aC": 1000000})
    v = _v_text()
    out = _comb(m, v, v, c, c)
    assert "R-GC (sitting C) seat a: collections per MB of aC, ON 3.0000, OFF 1.0000" in out, out
    va = _v(m, v)
    assert va["bK"] == P.LAST_GAME * 4 * 9000 and va["heap"] == 50000000
    assert ("R-GC (sitting V) seat a: the collectors' bytes 576000 over the sitting's 64 measured windows against "
            "heap=50000000 at its end (0.0115 of it)") in out.splitlines(), "R-GC line"
    assert re.search(r"^R-WORK seat a: u_g sitting V g1 [0-9.]+; .*; sitting C's ON windows g1 30\.000; g2 30\.000; ",
                     out, re.M), out


def _ctr_at(g0, tail):
    """ctr for _b11_text: game g0's counters line ends with tail (None drops the line), every other game's as built."""
    return lambda g: tail if g == g0 else B11_CTR_V6


def chk_counters_line_v6_keys(m):
    # P1's V6 emitter (via the integrator, 12 Nov): a V6 counters line carries span_leave_mismatch, which must be 0 (a
    # nonzero one is VR2's class, as span_depth_violations), and photon_offmain, reported only; a V6 line without
    # either is faulted as one without span_depth_violations; a key the line carries beyond these is left unjudged
    games = list(range(1, 7))
    for text in (_v_text(), _v_text(ctr=_ctr_at(2, " photon_offmain=7 span_leave_mismatch=0")),
                 _v_text(ctr=_ctr_at(2, B11_CTR_V6 + " zz_unknown=5"))):
        recs = m.read(text)
        assert m.counters_faults(recs, games) == [] and _v(m, text)["why"] == [], _v(m, text)["why"]
    v = _v(m, _v_text(ctr=_ctr_at(2, " photon_offmain=7 span_leave_mismatch=0")))
    assert v["photon_offmain"] == 7, v["photon_offmain"]
    for tail, want in ((" photon_offmain=0 span_leave_mismatch=1", "counters g=2 span_leave_mismatch=1"),
                       (" photon_offmain=0", "counters g=2 span_leave_mismatch not printed"),
                       (" span_leave_mismatch=0", "counters g=2 photon_offmain not printed"),
                       (None, "game 2: 0 counters lines (needs 1, written at its flush)")):
        text = _v_text(ctr=_ctr_at(2, tail))
        recs = m.read(text)
        assert [x for x in m.counters_faults(recs, games) if x.startswith(want)], (tail, want)
        assert [x for x in m.vr2(recs)[1] if x.startswith(want)], (tail, want)
        # ruling R6-A3.11.149 (5)(a): the validity set's counters line row withholds B1 in sitting V
        assert [x for x in _v(m, text)["why"] if x.startswith("counters line: " + want)], (tail, _v(m, text)["why"])
    # the same class as span_depth_violations
    text = re.sub(r"(counters g=1 [^\n]*)span_depth_violations=0", r"\g<1>span_depth_violations=2", _v_text(), count=1)
    assert "counters line: counters g=1 span_depth_violations=2" in _v(m, text)["why"], _v(m, text)["why"]
    # a log without B11 window lines is no V6 log: its counters line carries the three counters only
    old = LOG_PREFIX + "[FRAME-TIME] counters g=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0"
    assert m.counters_faults(m.read(old), [1]) == []


def _boot(census=True, **kw):
    """A control run's boot: the census summary (census=False drops it) and V6_BOOT with the named lines replaced
    (keys as V6_BOOT's, spaces as underscores; None drops one)."""
    bt = dict(V6_BOOT)
    bt.update((k.replace("_", " "), v) for k, v in kw.items())
    head = [CENSUS_CLEAN] if census else []
    return "\n".join(LOG_PREFIX + x for x in head + ["[FRAME-TIME] " + x for x in bt.values() if x is not None])


K1_OUT = "alloc pin=ok planted=1052673/1048576 empty=0"
K2_OUT = "scope plant asked=2000 got=2101"
K3_OUT = "nest plant asked=2000 x=2020 e=1899 p=2005"


def chk_k_mutant_sitting_refused_and_controls_proof(m):
    # P1's V6 emitter (via the integrator, 12 Nov): a sitting log of either sitting whose boot prints another k_mutant
    # than none (or no controls line, or two) is refused by name; a control run's boot is read by controls_proof, which
    # reads K1 to K3 from the numbers printed and holds only when exactly the control k_mutant names reads out of range
    v, c = _v_text(), _b11_text(_one_run_games(), _c_cost(0))
    _on(m, v, v)
    rc = m.read_sitting(c, "C:a")
    m.sitting_c(rc, c, rc, c, None, "C:a")
    for line in ("controls k_mutant=k1", "controls k_mutant=k2", "controls k_mutant=k3", "controls k_mutant=x", None):
        bv, bc = _v_text(boot={"controls": line}), _b11_text(_one_run_games(), _c_cost(0), boot={"controls": line})
        assert _word_refused(lambda: _on(m, bv, v), "K-MUTANT"), line
        assert _word_refused(lambda: _on(m, v, bv), "K-MUTANT"), line
        assert _word_refused(lambda: _comb(m, v, v, bc, c), "K-MUTANT"), line
        assert _word_refused(lambda: m.report(bc, peer=c), "K-MUTANT"), line
        assert _word_refused(lambda: m.report(c, peer=bc), "K-MUTANT"), line
    two = _v_text().replace("[FRAME-TIME] controls k_mutant=none", "[FRAME-TIME] controls k_mutant=none\n" + LOG_PREFIX
                            + "[FRAME-TIME] controls k_mutant=none", 1)
    assert _word_refused(lambda: _on(m, two, v), "carries 2 controls lines")
    # controls_proof, read as the named profile (ruling R6-A3.11.151 (2) class C): each mutant's boot breaks its own
    # control alone (PASS); a mutant boot whose numbers read in range, or that breaks another control too, FAILs; boot
    # needs all three in range. A boot whose k_mutant is not the profile's is refused before any number is read
    for kw, prof, ok in ((dict(), "boot", True), (dict(controls="controls k_mutant=k1", alloc=K1_OUT), "boot-k1", True),
                         (dict(controls="controls k_mutant=k2", scope_plant=K2_OUT), "boot-k2", True),
                         (dict(controls="controls k_mutant=k3", nest=K3_OUT), "boot-k3", True),
                         (dict(controls="controls k_mutant=k1"), "boot-k1", False),
                         (dict(controls="controls k_mutant=k1", alloc=K1_OUT, nest=K3_OUT), "boot-k1", False),
                         (dict(controls="controls k_mutant=k2", alloc=K1_OUT), "boot-k2", False),
                         (dict(nest=K3_OUT), "boot", False)):
        got, lines = m.controls_proof(_boot(**kw), prof)
        assert got is ok and lines[-1].startswith("CONTROLS PROOF %s: profile %s" % ("PASS" if ok else "FAIL", prof)), \
            (kw, lines)
    for kw, prof, want in ((dict(controls="controls k_mutant=k4", nest=K3_OUT), "boot-k3",
                            "the boot log boot prints k_mutant=k4; the profile boot-k3's boot prints k_mutant=k3"),
                           (dict(controls=None), "boot", "the boot log boot carries 0 controls lines; the profile boot's "
                                                         "boot prints k_mutant=none"),
                           (dict(controls="controls k_mutant=k1", alloc=K1_OUT), "boot",
                            "prints k_mutant=k1; the profile boot's boot prints k_mutant=none"),
                           (dict(), "boot-k2", "prints k_mutant=none; the profile boot-k2's boot prints k_mutant=k2"),
                           (dict(), "boot-k4", "'boot-k4' is not a profile; usage: ft_parse.py --controls")):
        assert _word_refused(lambda: m.controls_proof(_boot(**kw), prof), "CONTROLS-REFUSED: "), (kw, prof)
        assert _word_refused(lambda: m.controls_proof(_boot(**kw), prof), want), (kw, prof)


def _settled_add(text, g, extra):
    """text with extra appended to game g's settled line."""
    return re.sub(r"(settled g=%d [^\n]*)" % g, lambda mm: mm.group(1) + extra, text, count=1)


def _drop_complete(text):
    return _sub1(text, "\n" + LOG_PREFIX + "[FRAME-TIME] sitting complete g=%d" % P.LAST_GAME, "")


CENSUS_CLEAN = CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 0, 0)
# ruling R6-A3.11.149 (5)(a): one spoil per validity guard, as (guard, a function of a complete sitting log)
VALIDITY_SPOILS = (
    ("complete sitting", _drop_complete),
    ("census summary", lambda t: _sub1(t, CENSUS_CLEAN, CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 1, 0))),
    ("VR1", lambda t: t.replace(LOG_PREFIX + "[FPSCAP] held by frame-time calibration\n", "", 1)),
    ("VR2 instrument", lambda t: _settled_add(t, 3, " missing_end=1")),
    ("VR5 records", lambda t: _sub1(t, "opened g=3 se=1 ce=1 ic=1", "opened g=3 se=1 ce=1 ic=0")),
    ("VR6 build", lambda t: t + "\n" + LOG_PREFIX + "[FRAME-TIME] disarmed input=fighters pt=3.1.1"),
    ("F18", lambda t: _sub1(t, "answer_replay g=3 ticks=4000 result=settled",
                            "answer_replay g=3 ticks=0 result=skipped_quit")),
    ("counters line", lambda t: re.sub(r"(counters g=2 [^\n]*)span_leave_mismatch=0", r"\g<1>span_leave_mismatch=1", t,
                                       count=1)),
    ("line invariants", lambda t: re.sub(r"(w pt=2\.1\.1 arm=\w+ plant=0 partial=0 n=120 sF=\d+ sS=0 sC=)(\d+)",
                                         lambda mm: mm.group(1) + str(int(mm.group(2)) + 1), t, count=1)),
    ("p-line faults", lambda t: _p_sub(t, "1.1.1", " recv_offmain=0 ", " recv_offmain=1 ")),
    ("own_split", lambda t: _p_sub(t, "1.1.1", " own_split=0 ", " own_split=1 ")),
    ("build marker", lambda t: _sub1(t, LOG_PREFIX + "[FRAME-TIME] " + P.MARK_FT + "\n", "")),
    # ruling R6-A3.11.151 (3): a patch class of the build not fully attached (chk_attach_guard spoils each part)
    ("ATTACH", lambda t: _sub1(t, "FtSockPatch:2/2", "FtSockPatch:1/2")),
)


def chk_validity_set_withholds_sitting_v(m):
    # ruling R6-A3.11.149 (5)(a), (b) and (7): sitting V applies the whole validity set: each guard's spoil fails its
    # own row, withholds B1 for the seat and names the guard on the WITHHELD list; the clean sitting fails none
    clean = _v_text()
    v = _v(m, clean)
    assert [n for n, _, _ in v["validity"]] == list(P.VALIDITY) and all(ok for _, ok, _ in v["validity"]), v["validity"]
    assert v["why"] == [] and v["cls"] == "PASS", v["why"]
    for name, spoil in VALIDITY_SPOILS:
        bad = spoil(clean)
        assert bad != clean, name
        v = _v(m, bad, clean)
        rows = dict((n, ok) for n, ok, _ in v["validity"])
        assert rows[name] is False, (name, v["validity"])
        assert [x for x in v["why"] if x.startswith(name + ": ")], (name, v["why"])
        lines = v_lines_of(m, bad, clean)
        assert [x for x in lines if x.startswith("V6 VALIDITY seat a %s FAIL: " % name)], (name, lines)
        assert [x for x in lines if x.startswith("V6 WITHHELD seat a: ") and (name + ": ") in x], (name, lines)


def v_lines_of(m, text, peer):
    """report_on's lines for seat a (text) beside seat b (peer)."""
    return [x for x in m.report_on({"a": text, "b": peer})[0] if " seat a" in x]


def chk_vr1_reads_t_on(m):
    # ruling R6-A3.11.149 (6) 3 and (7): sitting V's VR1 reads T_on, the frames' observed mean. Frames on the 60-FPS cap
    # (t_us 16667) with U_hi near 465 us: T_on is within 2 percent of 1e6/60 and T_on - U_hi (about 16200 us) is not,
    # so only a VR1 reading T_on finds the cap; frames of B11_T are on no cap
    v = _v(m, _v_text(s=400, t_us=16667))
    assert 400 < v["U_hi"] < 600 and abs(v["T_on"] - 1e6 / 60) <= 0.02 * 1e6 / 60, (v["U_hi"], v["T_on"])
    assert abs(v["T_on"] - v["U_hi"] - 1e6 / 60) > 0.02 * 1e6 / 60
    row = [(ok, w) for n, ok, w in v["validity"] if n == "VR1"]
    assert row == [(False, ["T_on 16667.0 us within 2 percent of 1e6/60"])], row
    assert "VR1: T_on 16667.0 us within 2 percent of 1e6/60" in v["why"], v["why"]
    assert [ok for n, ok, w in _v(m, _v_text())["validity"] if n == "VR1"] == [True]


def chk_validity_set_decides_sitting_c(m):
    # ruling R6-A3.11.149 (5)(c) and (7): the same validity set decides whether sitting C gives a cross-check: a
    # sitting-C log that fails a guard is never "not refuted"; its cross-check is unavailable, naming the guard, and
    # B1 is WITHHELD for that seat; the clean log gives one
    v, c = _v_text(), _c_text()
    sc = m.sitting_c(m.read(c), c, m.read(c), c, None, "C:a")
    assert [n for n, _, _ in sc["rows"]] == list(P.VALIDITY) and sc["unavail"] == [] and sc["e"] is not None, sc["unavail"]
    assert re.search(r"; cross-check not refuted", _verdict(_comb(m, v, v, c, c), "a")), _comb(m, v, v, c, c)
    for name in ("complete sitting", "line invariants", "own_split", "build marker", "F18"):
        bad = dict(VALIDITY_SPOILS)[name](c)
        sc = m.sitting_c(m.read(bad), bad, m.read(c), c, None, "C:a")
        assert name in sc["unavail"], (name, sc["unavail"])
        out = _comb(m, v, v, bad, c)
        ln = _verdict(out, "a")
        assert ln.startswith("VERDICT B1 seat a WITHHELD: sitting C gives no cross-check until it has run again; "
                             "cross-check unavailable (") and name in ln.split("cross-check unavailable (", 1)[1], (name, ln)
        assert [x for x in out.splitlines() if x.startswith("V6 VALIDITY sitting C seat a %s FAIL: " % name)], (name, out)
        assert _classes(out)[0] == {"a": "WITHHELD", "b": "PASS"}, (name, out)


def chk_two_arm_guards_named_on_the_verdict_line(m):
    # ruling R6-A3.11.149 (5)(d), (e) and (7): the two-arm guards are printed beside the contrast, one line each in
    # TWO_ARM's order, and the verdict line names every one that does not pass ("not refuted, weakened by ..."), none
    # other; the follow-up to ruling .149, C: each with its word, without a reference R-COMMON NOT TESTED; a guard
    # that does not pass leaves the class as it is
    v, c = _v_text(), _c_text()
    for refs in (None, {"a": _as_ref(c)}):
        out = _comb(m, v, v, c, c, refs=refs)
        two = re.findall(r"^V6 TWO-ARM seat a (.+?) (PASS|FAIL|NOT TESTED): (.*)$", out, re.M)
        assert [n for n, _, _ in two] == list(P.TWO_ARM), two
        weak = [(n, s, d) for n, s, d in two if s != "PASS"]
        common = [(s, d) for n, s, d in two if n == "R-COMMON"][0]
        assert common == ("NOT TESTED", "no reference log") if refs is None else common[0] != "NOT TESTED", (refs, common)
        ln = _verdict(out, "a")
        want = ", ".join("%s (%s)" % (n, "not tested: " + d if s == "NOT TESTED" else "fail") for n, s, d in weak)
        assert ln.endswith("; cross-check not refuted" + (", weakened by %s" % want if weak else "")), (ln, weak)
        assert _classes(out)[0] == {"a": "PASS", "b": "PASS"}, out


def chk_two_arm_three_words(m):
    # the follow-up to ruling .149, C: a two-arm guard's word is PASS, FAIL or NOT TESTED. NOT TESTED when its input is
    # absent (R-COMMON without a reference log, also when the contrast is missing too); FAIL with its reason when it
    # cannot be computed although its input is present (no contrast for VR4, VR9, R-CARRY, and R-COMMON with a
    # reference); FAIL and NOT TESTED both weaken, the verdict line naming each with its word
    assert tuple(m.TWO_WORDS) == ("PASS", "FAIL", "NOT TESTED")
    c = _c_text()
    rc = m.read(c)
    ref = m.read_reference(_as_ref(c), "R:a")
    rows = dict((n, (w, d)) for n, w, d in m.sitting_c(rc, c, rc, c, None, "C:a")["two"])
    assert rows["R-COMMON"] == ("NOT TESTED", "no reference log"), rows["R-COMMON"]
    assert all(w in m.TWO_WORDS for w, d in rows.values()), rows
    rows = dict((n, (w, d)) for n, w, d in m.sitting_c(rc, c, rc, c, ref, "C:a")["two"])
    assert rows["R-COMMON"][0] in ("PASS", "FAIL") and rows["R-COMMON"][1] != "no reference log", rows
    rows = dict((n, (w, d)) for n, w, d in m.two_arm(rc, None, ref))
    for n in ("VR4", "VR9", "R-CARRY", "R-COMMON"):
        assert rows[n] == ("FAIL", "not computable: no contrast"), (n, rows[n])
    assert dict((n, (w, d)) for n, w, d in m.two_arm(rc, None, None))["R-COMMON"] == ("NOT TESTED", "no reference log")
    two = [("VR3", "PASS", "lag-1"), ("VR7", "FAIL", "H fails"), ("R-COMMON", "NOT TESTED", "no reference log")]
    weak = m._weak(two)
    assert weak == two[1:], weak
    assert m._weak_text(weak) == "VR7 (fail), R-COMMON (not tested: no reference log)", m._weak_text(weak)
    assert m.cross_state([], {"lb": 0.0}, 1.0, weak) == (
        "not refuted, weakened by VR7 (fail), R-COMMON (not tested: no reference log)", False)
    assert m.cross_state([], {"lb": 0.0}, 1.0, m._weak(two[:1])) == ("not refuted", False)
    out = _comb(m, _v_text(), _v_text(), c, c)
    assert "V6 TWO-ARM seat a R-COMMON NOT TESTED: no reference log" in out.splitlines(), out
    assert "R-COMMON (not tested: no reference log)" in _verdict(out, "a"), _verdict(out, "a")


def chk_reported_lines_never_end_the_verdict(m):
    # the follow-up to ruling .149, D: a reported-only value that cannot be computed prints 'not computable: <reason>'
    # on its own line and the verdict lines still follow: sitting C's ON-window u_g on the R-WORK line, over a sitting-C
    # log whose settled lines print two Stopwatch frequencies; the clean log prints the numbers (the control)
    v, c = _v_text(), _c_text()
    bad = re.sub(r"(settled g=3 [^\n]*?)freq=\d+", r"\g<1>freq=20000000", c, count=1)
    assert bad != c
    try:
        out = _comb(m, v, v, bad, c)
    except Exception as x:          # noqa: BLE001
        raise AssertionError("the combining step ended on a reported value: %s" % x)
    ln = [x for x in out.splitlines() if x.startswith("R-WORK seat a: ")]
    assert len(ln) == 1 and "; sitting C's ON windows not computable: V6 needs one Stopwatch frequency (got " in ln[0], ln
    assert _verdict(out, "a").startswith("VERDICT B1 seat a ") and _verdict(out, "b").startswith("VERDICT B1 seat b ")
    assert re.search(r"^VERDICT B1 worse seat: seat ", out, re.M), out
    ln = [x for x in _comb(m, v, v, c, c).splitlines() if x.startswith("R-WORK seat a: ")]
    assert len(ln) == 1 and "not computable" not in ln[0] and "; sitting C's ON windows g1 " in ln[0], ln


def _comb_ok(m, v1, v2, c1, c2):
    try:
        return _comb(m, v1, v2, c1, c2)
    except Exception as x:          # noqa: BLE001
        raise AssertionError("the combining step ended on a reported value: %s" % x)


def chk_reported_values_not_computable(m):
    # ruling R6-A3.11.151 (2) class D, F8: a reported value whose divisor can be 0 prints 'not computable: <reason>' and
    # the verdict lines follow: U_hi as a percent of T_ref when T_ref = T_on - U_hi is not above 0 (bE of one byte per
    # window puts G_cap far above T_on), on the V6 L line and the B1 line; R-GC's sitting-V share when heap= prints 0,
    # and its total when a byte count prints NA. The clean logs print the numbers (the control)
    v, c = _v_text(), _c_text()
    out = _comb_ok(m, v, v, c, c)
    for seat in ("a", "b"):
        ln = [x for x in out.splitlines() if x.startswith("V6 L ")]
        assert len(ln) == 2 and all(re.search(r"; U_hi as a percent of T_ref: [0-9.]+ percent$", x) for x in ln), ln
        assert re.search(r"T_ref [0-9.]+ us \([0-9.]+ percent\); the contrast", _verdict(out, seat)), out
    big = _v_text(cls=_v_cls(bytes_=dict(V6_BYTES, aC=9001)))
    vb = _v(m, big)
    assert vb["T_ref"] is not None and vb["T_ref"] <= 0 and vb["U_hi"] > vb["T_on"], (vb["T_ref"], vb["U_hi"])
    out = _comb_ok(m, big, v, c, c)
    want = "not computable: T_ref %.1f us is not above 0" % vb["T_ref"]
    ln = [x for x in out.splitlines() if x.startswith("V6 L ")]
    assert ln[0].endswith("; U_hi as a percent of T_ref: " + want), ln
    assert ("against T_ref %.1f us (%s); the contrast's lower end" % (vb["T_ref"], want)) in _verdict(out, "a"), out
    assert _verdict(out, "b").startswith("VERDICT B1 seat b ") and re.search(r"^VERDICT B1 worse seat: ", out, re.M)
    for text, want in ((_v_text(p_extra=B11_P_EXTRA.replace("heap=50000000", "heap=0")),
                        "R-GC (sitting V) seat a: the collectors' bytes %d over the sitting's %d measured windows "
                        "against heap=0 at its end; its share not computable: heap= is not above 0"
                        % (P.LAST_GAME * 4 * 9000, P.LAST_GAME * 4)),
                       (_v_text(edit=lambda w: w.update(aW=None)),
                        "R-GC (sitting V) seat a: the collectors' bytes not computable: an a* or wa value prints NA in "
                        "a measured window against heap=50000000 at its end")):
        out = _comb_ok(m, text, v, c, c)
        assert want in out.splitlines(), (want, [x for x in out.splitlines() if x.startswith("R-GC (sitting V)")])
        assert _verdict(out, "a").startswith("VERDICT B1 seat a ")


def chk_r_gc_total_reads_every_measured_window(m):
    # ruling R6-A3.11.151 (2) class D, F9 (SHARED.md:250-253): R-GC's sitting-V total is the collectors' bytes over
    # every measured window, a res=1 window among them, while the estimator's own filter (plant=0 and res=0) keeps the
    # window out of bK and U; the clean log's two sums agree (the control)
    v = _v(m, _v_text())
    assert v["bK_all"] == v["bK"] == P.LAST_GAME * 4 * 9000 and v["bK_windows"] == P.LAST_GAME * 4, v
    text = _v_text(edit=lambda w: w.update(res=1) if (w["pt"], w["wi"]) == ("3.1.1", 2) else None)
    v = _v(m, text)
    assert v["bK"] == (P.LAST_GAME * 4 - 1) * 9000, v["bK"]
    assert v["bK_all"] == P.LAST_GAME * 4 * 9000 and v["bK_windows"] == P.LAST_GAME * 4, (v["bK_all"], v["bK_windows"])
    assert m.rgc_v_line("a", v) == ("R-GC (sitting V) seat a: the collectors' bytes %d over the sitting's %d measured "
                                    "windows against heap=50000000 at its end (%.4f of it)"
                                    % (P.LAST_GAME * 4 * 9000, P.LAST_GAME * 4, P.LAST_GAME * 4 * 9000 / 50000000.0))


def chk_cross_risks_beside_the_interval(m):
    # ruling R6-A3.11.151 (2) class D, F16 (SHARED.md:254-261): the combined report prints the cross-check's residual
    # statements (CROSS_RISKS: R-CARRY, R-COMMON, R-PATH, R-PREFIX, R-REST and the note) right after each seat's
    # TWO-ARM rows, beside the interval, and V_RISKS after the worse seat
    v, c = _v_text(), _c_text()
    lines = _comb(m, v, v, c, c).splitlines()
    for seat in ("a", "b"):
        at = max(i for i, x in enumerate(lines) if x.startswith("V6 TWO-ARM seat %s " % seat))
        assert lines[at + 1:at + 1 + len(P.CROSS_RISKS)] == ["  " + x for x in P.CROSS_RISKS], lines[at:at + 8]
        cc = [i for i, x in enumerate(lines) if x.startswith("V6 CROSS-CHECK seat %s:" % seat)]
        assert len(cc) == 1 and cc[0] < at, cc
    assert all(x.startswith("R-") or x for x in P.CROSS_RISKS) and len(P.CROSS_RISKS) == 6
    at = [i for i, x in enumerate(lines) if x.startswith("VERDICT B1 worse seat: ")][0]
    assert lines[at + 1:] == ["  " + x for x in P.V_RISKS], lines[at:]


def chk_b3_on_both_sittings(m):
    # ruling R6-A3.11.149 (5)(g) and (7): B3 holds only when it holds in both sittings; heavy work with combat live in
    # either sitting's log is a FAIL naming that sitting, and both clean is a PASS
    hv = lambda g, op: (1, 1, 0) if (g, op) == (3, P.HEAVY_OPS[0]) else None     # noqa: E731
    v, c = _v_text(), _c_text()
    out = _comb(m, v, v, c, c)
    assert re.search(r"^VERDICT B3 seat a PASS \(", out, re.M), out
    for vv, cc, which in ((_v_text(heavy=hv), c, "V"), (v, _c_text(heavy=hv), "C")):
        out = _comb(m, vv, v, cc, c)
        ln = [x for x in out.splitlines() if x.startswith("VERDICT B3 seat a ")]
        assert len(ln) == 1 and ln[0].startswith("VERDICT B3 seat a FAIL: sitting %s VIOLATED: %s ran 1 times with "
                                                 "combat live" % (which, P.HEAVY_OPS[0])), (which, ln)
        assert re.search(r"^VERDICT B3 seat b PASS \(", out, re.M), out


def chk_seats_paired_by_name(m):
    # ruling R6-A3.11.149 (6) 6 and (7): each seat's two logs are paired by its name, never by position, and checked:
    # they agree in f_hat within 1 percent, or B1 is WITHHELD for the seat; when the two seats' own f_hat are that close,
    # the report says the check cannot tell them apart
    va, vb, ca, cb = _v_text(), _v_text(fhat=1050000), _c_text(), _c_text(fhat=1050000)
    out = m.combine({"a": va, "b": vb}, {"b": cb, "a": ca})         # sitting C named in the other order
    assert "PAIRING seat a: f_hat sitting V 1000000, sitting C 1000000: agree within 1 percent" in out, out
    assert "PAIRING seat b: f_hat sitting V 1050000, sitting C 1050000: agree within 1 percent" in out, out
    assert "cannot tell the seats apart" not in out and _classes(out)[0] == {"a": "PASS", "b": "PASS"}, out
    out = m.combine({"a": va, "b": vb}, {"a": cb, "b": ca})         # each seat named with the other's sitting-C log
    assert "PAIRING seat a: f_hat sitting V 1000000, sitting C 1050000: NOT within 1 percent" in out, out
    assert _verdict(out, "a").startswith("VERDICT B1 seat a WITHHELD: the pairing check fails"), out
    assert _classes(out)[0] == {"a": "WITHHELD", "b": "WITHHELD"}, out
    out = m.combine({"a": va, "b": va}, {"a": ca, "b": ca})
    assert ("PAIRING: the two seats' own f_hat (a 1000000, b 1000000) are within 1 percent of each other, so the check "
            "cannot tell the seats apart") in out, out


def chk_void_rounds_stay_in_sitting_v(m):
    # ruling R6-A3.11.149 (5)(f) and (7): VR8's zero-state half is reported in sitting V and its void rounds stay in
    # the population (game 0 stays out): a measured game whose one round is void still counts its frames in U, and
    # withholds nothing
    clean = _v(m, _v_text())
    text = _v_text(pts=lambda g: [{"n": [120] * 4, "coins": [(1, 0)], "zs": 4}] if g == 2 else None)
    void = _v(m, text)
    assert 0 not in void["games"] and void["N"] == clean["N"] == P.LAST_GAME * 480, (void["N"], clean["N"])
    assert void["games"][2]["n"] == 480 and void["why"] == [], void["why"]
    assert void["zero"][1:4] == (1, 1, [(2, 1)]), void["zero"]
    lines = v_lines_of(m, text, _v_text())
    assert [x for x in lines if x.startswith("V6 VR8 zero-state seat a (reported, not judged; ruling R6-A3.11.149 "
                                             "(5)(f)): game 0 (the mutant) 1 of 1 rounds void; the measured games 1 "
                                             "rounds void, kept in the population")], lines


def _boot_full(**kw):
    """A control run's whole boot: the marker, the clock, alloc_init, the mark cost and the census summary before
    V6_BOOT's lines (_boot: the ledger and the room gate among them)."""
    head = ["[FRAME-TIME] " + P.MARK_FT, "[FRAME-TIME] clock installed freq=10000000 hires=1 cycles=1",
            "[FRAME-TIME] alloc_init why=ok", "[FRAME-TIME] mark cost cyc=50 p90=70 n=1000"]
    return "\n".join(LOG_PREFIX + x for x in head) + "\n" + _boot(**kw)


def chk_controls_forms_and_failed_to_patch(m):
    # ruling R6-A3.11.149 (8): --controls lists every [FRAME-TIME] line whose form the parser does not know (0 for a
    # pass: a new kind, or a known lead in an unknown form, fails); ruling R6-A3.11.151 (3): a line holding "Failed to
    # patch" fails ATTACH, and a control boot whose ATTACH fails is refused, naming the line and the class
    boot = _boot_full()
    ok, lines = m.controls_proof(boot, "boot")
    assert ok and "CONTROLS unknown [FRAME-TIME] line forms: 0 (needs 0)" in lines, lines
    assert lines[:2] == [
        "CONTROLS profile boot: k_mutant=none, the profile's; every ruled line once and in its form (alloc pin, scope "
        "plant asked, nest plant asked, photon patches n, scope census entries, controls k_mutant, census registered, "
        "attach n)",
        "CONTROLS ATTACH: n=10 of=10 missing=none, no 'Failed to patch' line, the room gate attached"], lines[:2]
    n = len(boot.splitlines()) + 1
    for extra, pay in (("[FRAME-TIME] zz frame-time line", "zz frame-time line"),
                       ("[FRAME-TIME] counters g=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0",
                        "counters g=1 frames=10 missing_end=0 cycle_failures=0 span_depth_violations=0"),
                       ("[FRAME-TIME] ledger log=2 why=ok types=log,hash", "ledger log=2 why=ok types=log,hash")):
        ok, lines = m.controls_proof(boot + "\n" + LOG_PREFIX + extra, "boot")
        assert not ok and "CONTROLS UNKNOWN FORM line %d: %s" % (n, pay) in lines, (extra, lines)
        assert "CONTROLS unknown [FRAME-TIME] line forms: 1 (needs 0)" in lines and lines[-1].startswith(
            "CONTROLS PROOF FAIL: "), (extra, lines)
    bad = boot + "\n[Error  :  HarmonyX] Failed to patch void FtSpan::Open(): boom"
    assert _word_refused(lambda: m.controls_proof(bad, "boot"), "CONTROLS-REFUSED: the boot log boot (profile boot): "
                         "ATTACH: line %d: [Error  :  HarmonyX] Failed to patch void FtSpan::Open(): boom" % n)


# ruling R6-A3.11.151 (2) class C: (what, the profile, _boot_full's replaced lines, the refusal's words); every ruled
# line of the profile once and in its form before any number is judged, the plants at 2000 us, ATTACH, the census
# summary and the arm file
CONTROL_REFUSALS = (
    ("k2 boot without its scope plant", "boot-k2", dict(controls="controls k_mutant=k2", scope_plant=None),
     "0 'scope plant asked=' lines (needs exactly 1)"),
    ("no alloc line", "boot", dict(alloc=None), "0 'alloc pin=' lines (needs exactly 1)"),
    ("no nest line", "boot-k3", dict(controls="controls k_mutant=k3", nest=None), "0 'nest plant asked=' lines"),
    ("no photon line", "boot", dict(photon=None), "0 'photon patches n=' lines (needs exactly 1)"),
    ("the photon report failed", "boot", dict(photon="photon patches report failed: boom"),
     "the 'photon patches n=' line is not in its form: photon patches report failed: boom"),
    ("no scope census", "boot", dict(scope_census=None), "0 'scope census entries=' lines (needs exactly 1)"),
    ("no attach line", "boot", dict(attach=None), "0 'attach n=' lines (needs exactly 1)"),
    ("an attach line out of form", "boot", dict(attach=ATTACH_OK.replace("missing=none", "missing=-")),
     "the 'attach n=' line is not in its form"),
    ("an alloc line out of form", "boot-k1", dict(controls="controls k_mutant=k1", alloc="alloc pin=ok planted=x empty=0"),
     "the 'alloc pin=' line is not in its form: alloc pin=ok planted=x empty=0"),
    ("K2 at its own asked", "boot", dict(scope_plant="scope plant asked=4000 got=4000"),
     "the scope plant asked=4000 (the control spins 2000 us)"),
    ("K3 at its own asked", "boot", dict(nest="nest plant asked=4000 x=4000 e=4000 p=4000"),
     "the nest plant asked=4000 (the control spins 2000 us)"),
    ("ATTACH", "boot", dict(attach=ATTACH_OK.replace("FtSockPatch:2/2", "FtSockPatch:0/2")),
     "ATTACH: attach FtSockPatch 0/2: not every patch of the class attached"),
    ("the room gate", "boot", dict(gate="FT-GATE patched 12 entry points expected=13 excluded="),
     "ATTACH: FT-GATE patched 12 entry points of 13 expected"),
)


def chk_controls_ruled_lines_refused(m):
    # ruling R6-A3.11.151 (2) class C (F4, F5): a control boot is refused, naming what, when a ruled line is absent,
    # repeated or out of form (a k2 boot without its scope plant is refused, not "the expected failure"), when a plant
    # asked another spin than 2000 us, or when ATTACH, the census summary or the arm file fails; R-SCOPE's patch and
    # census lines out of range fail the proof. The clean boot of each profile is the control
    for what, prof, kw, want in CONTROL_REFUSALS:
        assert _word_refused(lambda: m.controls_proof(_boot_full(**kw), prof), "CONTROLS-REFUSED: "), what
        assert _word_refused(lambda: m.controls_proof(_boot_full(**kw), prof), want), (what, want)
    twice = _boot_full() + "\n" + LOG_PREFIX + "[FRAME-TIME] " + dict(V6_BOOT)["nest"]
    assert _word_refused(lambda: m.controls_proof(twice, "boot"), "2 'nest plant asked=' lines (needs exactly 1)")
    nocensus = _boot_full().replace(LOG_PREFIX + CENSUS_CLEAN + "\n", "")
    assert nocensus != _boot_full()
    assert _word_refused(lambda: m.controls_proof(nocensus, "boot"), "0 'census registered=' lines (needs exactly 1)")
    assert _word_refused(lambda: m.controls_proof(nocensus, "boot"), "census summary: 0 census summary lines")
    spoilt = _boot_full().replace(CENSUS_CLEAN, CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 1, 0))
    assert _word_refused(lambda: m.controls_proof(spoilt, "boot"), "census summary: census summary missing=1 (needs 0)")
    arm = _boot_full() + "\n" + LOG_PREFIX + ("[FRAME-TIME] settled g=-1 seed=0 c_plant=0 W=120 vsync=0 target=-1 "
                                              "freq=10000000 hires=1 f_hat=0 force=none problems=bad-seed clock=1")
    assert _word_refused(lambda: m.controls_proof(arm, "boot"),
                         "settled g=-1 problems=bad-seed: the arm file was not read as written")
    for prof, kw in (("boot", {}), ("boot-k2", dict(controls="controls k_mutant=k2", scope_plant=K2_OUT))):
        assert m.controls_proof(_boot_full(**kw), prof)[0], prof
    for kw, want in ((dict(photon="photon patches n=9 names=" + ",".join(P.PHOTON_ENTRIES[:9])),
                      "CONTROLS R-SCOPE patches OUT OF RANGE: n=9 for 9 names; not attached: "),
                     (dict(scope_census="scope census entries=40 wrapped=39"),
                      "CONTROLS R-SCOPE census OUT OF RANGE: entries 40, wrapped 39")):
        ok, lines = m.controls_proof(_boot_full(**kw), "boot")
        assert not ok and [x for x in lines if x.startswith(want)], (kw, lines)
        assert lines[-1].startswith("CONTROLS PROOF FAIL: profile boot, k_mutant=none; out of range none (needs "
                                    "exactly none); R-SCOPE's patches and census out of range: "), lines[-1]


LEDGER_OK = dict(V6_BOOT)["ledger"]
# the follow-up to ruling .149, A: (what, the boot's ledger line or None, the reason sitting V gives for this seat)
LEDGER_SPOILS = (
    ("absent", None, "the disk-log tap: 0 'ledger' lines (needs exactly 1): the disk-log tap's state is not read"),
    ("no listener", "ledger log=0 why=no_disk_listener types=log,hash,recv,sock",
     "the disk-log tap: ledger log=0 why=no_disk_listener: the disk log is not tapped, so the log type's writes reach "
     "no term of U"),
    ("failed", "ledger log=0 why=failed:TargetInvocationException types=log,hash,recv,sock",
     "the disk-log tap: ledger log=0 why=failed:TargetInvocationException: the disk log is not tapped"),
    ("type gone", "ledger log=1 why=ok types=log,hash,sock",
     "the disk-log tap: ledger types=log,hash,sock is not the parser's writer types log,hash,recv,sock (each once, in "
     "that order)"),
    ("type extra", "ledger log=1 why=ok types=log,hash,recv,sock,gc",
     "the disk-log tap: ledger types=log,hash,recv,sock,gc is not the parser's writer types log,hash,recv,sock (each "
     "once, in that order)"),
)
# ruling R6-A3.11.152, G1: ledger_state's reason for a types= list that is not WRITER_TYPES as written
LEDGER_TYPES_BAD = "ledger types=%s is not the parser's writer types log,hash,recv,sock (each once, in that order)"
# (what, the types= list as the line prints it): each is not the emitter's list (FtUpload.cs:104, joined at :368)
LEDGER_LISTS = (
    ("a name repeated", "log,log,hash,recv,sock"),
    ("an empty entry leading", ",log,hash,recv,sock"),
    ("an empty entry in the middle", "log,hash,,recv,sock"),
    ("an empty entry trailing", "log,hash,recv,sock,"),
    ("reordered", "log,recv,hash,sock"),
    ("a name missing", "log,hash,sock"),
    ("a name more", "log,hash,recv,sock,gc"),
)


def chk_ledger_types_judged_as_written(m):
    # ruling R6-A3.11.152, G1 (SHARED.md:245-246): the ledger's types= list is WRITER_TYPES exactly, as written: each
    # name once, in the emitter's order, no entry empty; anything else fails ledger_state with one reason naming the
    # list as written and the list required, and the state prints the list as written. On the combining path a
    # sitting-V log whose ledger repeats a name ends B1 WITHHELD for that seat, naming the list. The exact list passes
    # and the clean pair ends B1 PASS (the controls)
    clean, c = _v_text(), _c_text()
    assert m.ledger_state(m.read(clean)) == (True, [], "log=1 why=ok types=log,hash,recv,sock")
    for what, ts in LEDGER_LISTS:
        t = _v_text(boot={"ledger": "ledger log=1 why=ok types=" + ts})
        assert t != clean, what
        got = m.ledger_state(m.read(t))
        assert got == (False, [LEDGER_TYPES_BAD % ts], "log=1 why=ok types=" + ts), (what, got)
    assert _verdict(_comb(m, clean, clean, c, c), "a").startswith("VERDICT B1 seat a PASS: ")
    rep = _v_text(boot={"ledger": "ledger log=1 why=ok types=log,log,hash,recv,sock"})
    ln = _verdict(_comb(m, rep, clean, c, c), "a")
    assert ln.startswith("VERDICT B1 seat a WITHHELD: ") and (LEDGER_TYPES_BAD % "log,log,hash,recv,sock") in ln, ln


def _two_ledgers(text):
    full = LOG_PREFIX + "[FRAME-TIME] " + LEDGER_OK
    return _sub1(text, full, full + "\n" + full)


def chk_ledger_tap_withholds_sitting_v(m):
    # the follow-up to ruling .149, A: sitting V withholds B1 for a seat whose own log has no ledger line, two, one
    # with log=0 (the reason naming why=), or one whose types= differs from the parser's writer types either way; the
    # peer's tap is the peer's. Sitting C prints the same state beside R-WORK's u_g for the ON windows, and it decides
    # nothing there. The clean log (log=1 why=ok, the four types) is the control
    clean = _v_text()
    assert not [x for x in _v(m, clean)["why"] if "disk-log tap" in x], _v(m, clean)["why"]
    assert m.ledger_state(m.read(clean)) == (True, [], "log=1 why=ok types=log,hash,recv,sock")
    cases = [(w, _v_text(boot={"ledger": ln}), want) for w, ln, want in LEDGER_SPOILS]
    cases.append(("twice", _two_ledgers(clean),
                  "the disk-log tap: 2 'ledger' lines (needs exactly 1): the disk-log tap's state is not read"))
    for what, bad, want in cases:
        why = _v(m, bad, clean)["why"]
        assert [x for x in why if x.startswith(want)], (what, want, why)
        lines = v_lines_of(m, bad, clean)
        assert [x for x in lines if x.startswith("V6 WITHHELD seat a: ") and want in x], (what, lines)
        assert not [x for x in _v(m, clean, bad)["why"] if "disk-log tap" in x], what
    c = _c_text()
    out = _comb(m, clean, clean, c, c)
    ln = [x for x in out.splitlines() if x.startswith("R-WORK seat a: ")]
    assert len(ln) == 1 and ln[0].endswith("; sitting C's disk-log tap log=1 why=ok types=log,hash,recv,sock "
                                           "(reported)"), ln
    for what, line, want in LEDGER_SPOILS:
        out2 = _comb(m, clean, clean, _c_text(boot={"ledger": line}), c)
        ln = [x for x in out2.splitlines() if x.startswith("R-WORK seat a: ")]
        assert len(ln) == 1 and "; sitting C's disk-log tap " in ln[0] and want[len("the disk-log tap: "):] in ln[0] \
            and ln[0].endswith(" (reported)"), (what, ln)
        assert _verdict(out2, "a") == _verdict(out, "a"), (what, _verdict(out2, "a"), _verdict(out, "a"))


GATE_FULL = LOG_PREFIX + "[FRAME-TIME] " + dict(V6_BOOT)["gate"]
# the follow-up to ruling .149, B: (what, the boot's FT-GATE patched line or None, the room gate row's reason)
GATE_SPOILS = (
    ("absent", None, "0 'FT-GATE patched' lines (needs exactly 1): the room gate's attachment is not read"),
    ("short", "FT-GATE patched 12 entry points expected=13 excluded=JoinLobby,LoadOrCreateSettings",
     "FT-GATE patched 12 entry points of 13 expected: the room gate is not attached on every entry point"),
    ("missing", "FT-GATE patched 12 entry points expected=12 excluded=JoinLobby,LoadOrCreateSettings "
                "missing=QuickMatch,sweep: boom",
     "FT-GATE patched 12 entry points of 12 expected; missing=QuickMatch,sweep: boom: the room gate is not attached "
     "on every entry point"),
    ("none expected", "FT-GATE patched 0 entry points expected=0 excluded=",
     "FT-GATE patched 0 entry points of 0 expected: the room gate is not attached on every entry point"),
    ("form", "FT-GATE patched many entry points",
     "the FT-GATE patched line is not in its form: FT-GATE patched many entry points"),
)
HARMONY_FAIL = "[Error  :CompetitiveRounds] [HARMONY] Failed to patch %s: Patching exception in method null"


def _attach_with(entries, n=None, of=None, missing="none"):
    """An attach line of entries [(name, got, want)], n and of counted from them unless given."""
    ok = sum(1 for _, g, w in entries if w > 0 and g == w)
    return "attach n=%d of=%d missing=%s names=%s" % (ok if n is None else n, len(entries) if of is None else of, missing,
                                                     ",".join("%s:%d/%d" % e for e in entries))


ATTACH_ENTRIES = [(x.split(":")[0], int(x.split(":")[1].split("/")[0]), int(x.split("/")[1]))
                  for x in ATTACH_OK.split("names=")[1].split(",")]
# ruling R6-A3.11.151 (3): (what, the boot's attach line or None, a reason ATTACH must give), one per rule of the line
ATTACH_SPOILS = (
    ("absent", None, "0 'attach' lines (needs exactly 1 per boot): the patch classes' attachment is not read"),
    ("a class short", _attach_with([(x, 1 if x == "FtRoute_SendPatch" else g, w) for x, g, w in ATTACH_ENTRIES],
                                   missing="FtRoute_SendPatch"),
     "attach FtRoute_SendPatch 1/2: not every patch of the class attached"),
    ("a class short, the counts claiming it", ATTACH_OK.replace("FtSockPatch:2/2", "FtSockPatch:1/2"),
     "attach FtSockPatch 1/2: not every patch of the class attached"),
    ("want 0", _attach_with([(x, 0, 0) if x == "FtSockPatch" else (x, g, w) for x, g, w in ATTACH_ENTRIES],
                            missing="FtSockPatch"), "attach FtSockPatch 0/0: want 0, no patch of the class counted"),
    ("n below of", ATTACH_OK.replace("n=10", "n=9"), "attach n=9 of=10: not every patch class attached"),
    ("n beside the entries", ATTACH_OK.replace("n=10", "n=9"), "attach n=9 for 10 entries attached"),
    ("missing named", ATTACH_OK.replace("missing=none", "missing=FtSockPatch"), "attach missing=FtSockPatch"),
    ("of beside the entries", ATTACH_OK.replace("of=10", "of=11"), "attach of=11 for 10 entries"),
    ("a class gone", _attach_with([e for e in ATTACH_ENTRIES if e[0] != "FtSockPatch"]),
     "attach names lack FtSockPatch (a patch class of the build)"),
    ("a class not the build's", _attach_with(ATTACH_ENTRIES + [("FtZzPatch", 1, 1)]),
     "attach names FtZzPatch, not a patch class of the build"),
    ("a class twice", _attach_with(ATTACH_ENTRIES + [("FtSockPatch", 2, 2)]), "attach names FtSockPatch twice"),
    ("out of order", _attach_with(ATTACH_ENTRIES[1:2] + ATTACH_ENTRIES[:1] + ATTACH_ENTRIES[2:]),
     "attach entries not in ordinal order of the name"),
    ("out of form", ATTACH_OK.replace("missing=none", "missing=-"), "the attach line is not in its form (line "),
)


def _attach_of(m, v):
    return dict((n, (ok, w)) for n, ok, w in v["validity"])["ATTACH"]


def chk_attach_guard(m):
    # ruling R6-A3.11.151 (3): the validity set's ATTACH fails, on either seat's log (the peer's marked), when the attach
    # line is absent or twice, out of its form or any rule of its counts and names fails, when 'attach report failed'
    # is printed, when a line holds 'Failed to patch' (Plugin's line, or the laptop slice's 'withheld Failed to patch
    # <n>'), or when the room gate's line is absent, twice, out of form or short; each reason names the part and the
    # class. Sitting V withholds naming ATTACH; sitting C has no cross-check; a reference reads the reference build's
    # list (nine, without FtSockPatch) and is refused on a failure. The clean log of each is the control
    clean = _v_text()
    assert _attach_of(m, _v(m, clean)) == (True, []), _attach_of(m, _v(m, clean))
    assert m.attach_faults(clean) == [] and m.attach_guard(clean) == []
    full = LOG_PREFIX + "[FRAME-TIME] " + ATTACH_OK
    cases = [(w, _v_text(boot={"attach": ln}), want) for w, ln, want in ATTACH_SPOILS]
    cases.append(("twice", _sub1(clean, full, full + "\n" + full),
                  "2 'attach' lines (needs exactly 1 per boot): the patch classes' attachment is not read"))
    cases.append(("the report failed", _sub1(clean, full, full + "\n" + LOG_PREFIX.replace("Info   ", "Warning")
                                             + "[FRAME-TIME] attach report failed: NullReferenceException"),
                  "attach report failed (line "))
    cases += [("room gate " + w, _v_text(boot={"gate": ln}), want) for w, ln, want in GATE_SPOILS]
    cases.append(("room gate twice", _sub1(clean, GATE_FULL, GATE_FULL + "\n" + GATE_FULL),
                  "2 'FT-GATE patched' lines (needs exactly 1): the room gate's attachment is not read"))
    for line, shown in ((HARMONY_FAIL % "FtSockPatch", "[HARMONY] Failed to patch FtSockPatch: Patching exception in "
                                                       "method null"),
                        ("withheld Failed to patch 1", "withheld Failed to patch 1")):
        bad = clean + "\n" + line
        cases.append((line, bad, "line %d: %s" % (len(bad.splitlines()), shown)))
    for what, bad, want in cases:
        assert bad != clean, what
        for t, p, who in ((bad, clean, ""), (clean, bad, "peer seat: ")):
            v = _v(m, t, p)
            ok, w = _attach_of(m, v)
            assert ok is False and [x for x in w if x.startswith(who + want)], (what, who, w)
            assert [x for x in v["why"] if x.startswith("ATTACH: ") and (who + want) in x], (what, who, v["why"])
    # sitting C: no cross-check, the verdict naming ATTACH
    v, c = _v_text(), _c_text()
    bc = _c_text(boot={"attach": ATTACH_OK.replace("FtSockPatch:2/2", "FtSockPatch:0/2")})
    sc = m.sitting_c(m.read(bc), bc, m.read(c), c, None, "C:a")
    assert "ATTACH" in sc["unavail"], sc["unavail"]
    ln = _verdict(_comb(m, v, v, bc, c), "a")
    assert ln.startswith("VERDICT B1 seat a WITHHELD: sitting C gives no cross-check until it has run again; "
                         "cross-check unavailable (ATTACH)"), ln
    # a reference: the reference build's list
    assert not _word_refused(lambda: m.read_reference(_as_ref(c), "R:a"), ""), "the reference log is refused"
    for ref, want in ((c.replace(P.MARK_FT, P.MARK_REF), "attach names FtSockPatch, not a patch class of the build"),
                      (_as_ref(c) + "\n" + HARMONY_FAIL % "FtRoomGatePunPatch", "[HARMONY] Failed to patch "
                                                                                "FtRoomGatePunPatch"),
                      (_as_ref(c).replace(ATTACH_REF, ATTACH_REF.replace("n=9", "n=8")), "attach n=8 of=9")):
        assert _word_refused(lambda: m.read_reference(ref, "R:a"), "ATTACH: the reference log R:a: "), want
        assert _word_refused(lambda: m.read_reference(ref, "R:a"), want), want


def chk_gate_counters_rule_vr5_in_sitting_c(m):
    # ruling R6-A3.11.151 (2) class B: off_g, off_gn, off_on and on_guarded (plugin/FtFrames.cs:274) are printed and 0
    # on every point of a V6 log: in sitting C a point with one above 0, or without it, fails VR5's OFF-window rule,
    # naming the field and the point, which weakens the cross-check on the B1 line; the clean log holds (the control)
    v, c = _v_text(), _c_text()
    rc = m.read(c)

    def vr5(text):
        return dict((n, (w, d)) for n, w, d in m.sitting_c(m.read(text), text, rc, c, None, "C:a")["two"])[
            "VR5 OFF-window rule"]
    assert vr5(c) == ("PASS", "holds"), vr5(c)
    pt = [r["pt"] for r in rc if r["kind"] == "p" and r["game"] == 2][0]
    for k in P.GATE_COUNTERS:
        for new in (" %s=1" % k, ""):
            bad = _p_sub(c, pt, " %s=0" % k, new)
            w, d = vr5(bad)
            assert w == "FAIL" and ("%s above 0 or not printed at %s" % (k, pt)) in d, (k, new, w, d)
        ln = _verdict(_comb(m, v, v, bad, c), "a")
        assert re.search(r"; cross-check not refuted, weakened by [^;]*VR5 OFF-window rule \(fail\)", ln), (k, ln)


def chk_arm_problems_fail_the_complete_sitting(m):
    # ruling R6-A3.11.151 (2) class B: a settled line's problems= (plugin/FtCalib.cs:409, the arm file's words the
    # build could not read) fails the complete sitting row in either sitting, this seat's or the peer's (marked): in
    # sitting V B1 is WITHHELD naming it, in sitting C the cross-check is unavailable (complete sitting); the clean logs
    # carry none (the control)
    v, c = _v_text(), _c_text()
    want = "settled g=3 problems=bad-seed: the arm file was not read as written"
    assert m.arm_problems(m.read(v)) == [] and m.arm_problems(m.read(c)) == []
    for clean, bad in ((v, _settled_add(v, 3, " problems=bad-seed")), (c, _settled_add(c, 3, " problems=bad-seed"))):
        assert m.arm_problems(m.read(bad)) == [want]
        for t, p, who in ((bad, clean, ""), (clean, bad, "peer seat: ")):
            rows = dict((n, (ok, w)) for n, ok, w in m.validity_set(m.read(t), t, m.read(p), p, None, "X:a", 1, "T"))
            ok, w = rows["complete sitting"]
            assert ok is False and who + want in w, (who, w)
    ln = _verdict(_comb(m, v, v, _settled_add(c, 3, " problems=bad-seed"), c), "a")
    assert "cross-check unavailable (complete sitting" in ln, ln
    ln = _verdict(_comb(m, _settled_add(v, 3, " problems=bad-seed"), v, c, c), "a")
    assert ln.startswith("VERDICT B1 seat a WITHHELD: ") and "complete sitting: " + want in ln, ln


def chk_cal_entries_failure_form(m):
    # the integrator's point H: FtCalib.Run's entries step failing prints 'cal i=<i> kind=disp entries failed:
    # <message>' (plugin/FtCalib.cs:126); a FORMS row reads it (no unknown form), and the game's calibration run that
    # carries it fails VR2 ('carries failure warnings for disp'), so sitting V withholds B1. The clean log passes VR2
    # and the other failure forms stay read (the controls)
    assert '" kind=disp entries failed: "' in _plugin_src()
    for pay in ("cal i=4 kind=disp entries failed: NullReferenceException: x", "cal i=-1 kind=disp entries failed: y"):
        assert m.unknown_forms(LOG_PREFIX + "[FRAME-TIME] " + pay) == [], pay
    assert m.unknown_forms(LOG_PREFIX + "[FRAME-TIME] cal i=4 kind=disp entries broke: x") != []
    assert m.unknown_forms(LOG_PREFIX + "[FRAME-TIME] cal i=4 kind=disp failed: x") == []
    v = _v_text()
    assert not [x for x in _v(m, v)["why"] if x.startswith("VR2")]
    i = [r["i"] for r in m.read(v) if r["kind"] == "cal" and r.get("why") == "game3"][0]
    bad = v + "\n" + LOG_PREFIX + "[FRAME-TIME] cal i=%d kind=disp entries failed: boom" % i
    want = "VR2 instrument: game 3: calibration %d carries failure warnings for disp" % i
    assert [x for x in _v(m, bad)["why"] if x.startswith(want)], _v(m, bad)["why"]


def _w_without(line, key):
    toks = line.split(" ")
    kept = [t for t in toks if not t.startswith(key + "=")]
    assert len(kept) == len(toks) - 1, key
    return " ".join(kept)


def chk_malformed_lines_are_refusals(m):
    # the integrator's point I: a B11 window line without any key its form requires is the parser's refusal as it is
    # read (RecordRefused, naming the key), and window_faults handed parse_line's record directly gives one named
    # fault, never a KeyError; a line no B11 field marks gives its fault too; a pt or an e<H> value of another form is
    # a Refused naming it, never a ValueError. The clean line reads, and its window_faults is [] (the control)
    text = _c_text()
    lines = text.split("\n")
    at = [j for j, x in enumerate(lines) if "[FRAME-TIME] w pt=" in x and " partial=0 " in x][0]
    w = m.parse_line(lines[at])
    assert m.window_faults(w) == [], m.window_faults(w)
    keys = sorted(set(k for kind, _, cond, ks, _ in m.REQUIRED_KEYS if kind == "w" for k in ks))
    assert len([k for k in keys if (" %s=" % k) in lines[at]]) >= 30, keys
    for k in [k for k in keys if (" %s=" % k) in lines[at]]:
        cut = _w_without(lines[at], k)
        rec = m.parse_line(cut)
        try:
            f = m.window_faults(rec)
        except Exception as x:          # noqa: BLE001
            raise AssertionError("window_faults raised %s on a line without %s" % (type(x).__name__, k))
        assert len(f) == 1 and f[0].startswith("window ") and (": lacks %s" % k) in f[0], (k, f)
        bad = "\n".join(lines[:at] + [cut] + lines[at + 1:])
        assert _word_refused(lambda: m.read(bad), "line=%d lacks %s" % (at + 1, k)), k
    old = m.parse_line(" ".join(t for t in lines[at].split(" ") if t.split("=")[0] not in m.B11_FIELDS))
    assert not m.b11_line(old) and m.window_faults(old) == ["window %s.None: lacks the B11 fields" % old["pt"]]
    for old_t, new_t, word in ((" pt=", " pt=1.", "is not <game>.<round>.<point>"),
                               (" e4=", " e4=0,", "is not <count>,<count>")):
        ln = re.sub(r"( pt=)(\d+\.\d+)\.\d+", r"\g<1>\2", lines[at], count=1) if old_t == " pt=" else \
            re.sub(r" e4=(\d+),(\d+)", r" e4=\1", lines[at], count=1)
        assert ln != lines[at], old_t
        bad = "\n".join(lines[:at] + [ln] + lines[at + 1:])
        assert _word_refused(lambda: m.read(bad), word), (old_t, word)
        assert _word_refused(lambda: m.parse_line(ln), word), (old_t, word)


def test_malformed_lines_end_as_refusals_through_the_script(tmp_path):
    # point I through the script's main path: a window line without wu or prun exits REFUSED_RECORD_EXIT, a pt or an
    # e<H> of another form exits 3, each printing the parser's refusal and no traceback
    text = _c_text()
    lines = text.split("\n")
    at = [j for j, x in enumerate(lines) if "[FRAME-TIME] w pt=" in x and " partial=0 " in x][0]
    cases = [(_w_without(lines[at], "wu"), P.REFUSED_RECORD_EXIT, "lacks wu"),
             (_w_without(lines[at], "prun"), P.REFUSED_RECORD_EXIT, "lacks prun"),
             (re.sub(r"( pt=\d+\.\d+)\.\d+", r"\1", lines[at], count=1), 3, "is not <game>.<round>.<point>"),
             (re.sub(r" e4=(\d+),(\d+)", r" e4=\1", lines[at], count=1), 3, "e4=")]
    for j, (ln, rc_want, word) in enumerate(cases):
        p = tmp_path / ("bad%d.log" % j)
        p.write_text("\n".join(lines[:at] + [ln] + lines[at + 1:]) + "\n", encoding="utf-8")
        rc, out, err = _run_script(p, p)
        assert rc == rc_want and word in out and "Traceback" not in err, (j, rc, out[-300:], err[-300:])


A3_REF = "a3 g=1 ref=NA rows=0"


def chk_reference_a3_form(m):
    # the integrator's point J: the reference build prints 'a3 g=<g> ref=NA rows=0' (no row measured, no reads_win);
    # read() admits that form in a log build_marker reads as a reference, so a reference log is readable whole, and
    # refuses it as lacking reads_win in a measuring build's log and in a log carrying both markers; the reference
    # form still needs g. The measuring build's a3 lines keep needing reads_win
    c = _c_text()
    ln = "\n" + LOG_PREFIX + "[FRAME-TIME] " + A3_REF
    ref = _as_ref(c) + ln
    try:
        recs = m.read(ref, "R:a")
    except Exception as x:          # noqa: BLE001
        raise AssertionError("the reference log is refused: %s" % x)
    assert [r for r in recs if r["kind"] == "a3" and r.get("ref") == "NA"], "the reference a3 line is not read"
    assert m.read_reference(ref, "R:a")
    n = len((c + ln).splitlines())
    assert _word_refused(lambda: m.read(c + ln, "C:a"), "kind=a3 file=C:a line=%d lacks reads_win" % n)
    both = c + "\n" + LOG_PREFIX + "[FRAME-TIME] " + P.MARK_REF + ln
    assert _word_refused(lambda: m.read(both, "C:a"), "lacks reads_win")
    assert _word_refused(lambda: m.read(_as_ref(c) + ln.replace("g=1 ", ""), "R:a"), "lacks g")
    assert _word_refused(lambda: m.read(_as_ref(c) + "\n" + LOG_PREFIX + "[FRAME-TIME] a3 g=1 k=CE_Top", "R:a"),
                         "lacks reads_win")


def _source_classes():
    """Every class of plugin/*.cs with a class-level [HarmonyPatch], with the defines it compiles under, by its
    #if nesting: {name: (compiled with SCR_FRAMETIME alone, with SCR_FRAMETIME and SCR_FT_NOCOLLECTORS, with neither)}.
    A condition holds symbols, !, &&, || and parentheses; any other symbol is undefined."""
    plug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin")
    sets = ({"SCR_FRAMETIME"}, {"SCR_FRAMETIME", "SCR_FT_NOCOLLECTORS"}, set())

    def holds(cond, d):
        py = re.sub(r"[A-Za-z_]\w*", lambda mm: "True" if mm.group(0) in d else "False", cond)
        py = py.replace("&&", " and ").replace("||", " or ").replace("!", " not ")
        assert re.fullmatch(r"[\sA-Za-z()]*", py), cond
        return eval(py)                     # noqa: S307 (the condition's own symbols, mapped to True and False)

    attr = r"\[(?:[^\[\]]|\[[^\[\]]*\])*\]"
    decl = re.compile(r"\[\s*HarmonyPatch\b(?:[^\[\]]|\[[^\[\]]*\])*\]\s*(?:%s\s*)*(?:\w+\s+)*class\s+(\w+)" % attr)
    out = {}
    for fn in sorted(os.listdir(plug)):
        if not fn.endswith(".cs"):
            continue
        stack, lines, conds = [], [], []
        for raw in open(os.path.join(plug, fn), encoding="utf-8-sig").read().splitlines():
            ln = re.sub(r"//.*$", "", raw).strip()
            mm = re.match(r"#\s*(if|elif|else|endif)\b(.*)$", ln)
            if mm:
                kw, cond = mm.group(1), mm.group(2).strip()
                if kw == "if":
                    stack.append([cond, [cond]])
                elif kw == "elif":
                    stack[-1][0] = "(%s) && !(%s)" % (cond, ") && !(".join(stack[-1][1]))
                    stack[-1][1].append(cond)
                elif kw == "else":
                    stack[-1][0] = "!(%s)" % ") && !(".join(stack[-1][1])
                else:
                    stack.pop()
            lines.append("" if ln.startswith("#") else ln)
            conds.append([c for c, _ in stack])
        assert stack == [], (fn, stack)
        body = "\n".join(lines)
        for mm in decl.finditer(body):
            at = body.count("\n", 0, mm.start(1))
            assert mm.group(1) not in out, (fn, mm.group(1))
            out[mm.group(1)] = tuple(all(holds(c, d) for c in conds[at]) for d in sets)
    return out


def test_attach_lists_are_the_source_sets():
    # ruling R6-A3.11.151 (3) and the integrator's note on P1b's hand-back: every plugin/*.cs read with its #if nesting;
    # the classes with a class-level [HarmonyPatch] compiled only when SCR_FRAMETIME is defined are ATTACH_CLASSES, in
    # ordinal order, each named "Ft..." (FtAttach.Report finds its entries by that prefix, so a measuring patch class
    # named otherwise would be no entry, and only this test sees it); the reference build's are ATTACH_CLASSES_REF,
    # the difference the classes under #if !SCR_FT_NOCOLLECTORS. Holds before and after FtAttach.cs is merged (it
    # carries no [HarmonyPatch])
    cls = _source_classes()
    ft = sorted(n for n, (a, r, none) in cls.items() if a and not none)
    ref = sorted(n for n, (a, r, none) in cls.items() if r and not none)
    assert list(P.ATTACH_CLASSES) == ft, (P.ATTACH_CLASSES, ft)
    assert list(P.ATTACH_CLASSES_REF) == ref, (P.ATTACH_CLASSES_REF, ref)
    assert all(n.startswith("Ft") for n in ft), ft
    assert set(ft) - set(ref) == {"FtSockPatch"} and set(ref) <= set(ft), (ft, ref)
    # the scanner sees the product's classes too (compiled in every build), so the filter is what selects
    assert [n for n, (a, r, none) in cls.items() if a and none], "the scanner found no product patch class"
    assert ATTACH_OK.split("names=")[1].count(",") + 1 == len(P.ATTACH_CLASSES)
    assert [x for x, _, _ in ATTACH_ENTRIES] == list(P.ATTACH_CLASSES)


# ruling R6-A3.11.151 (2) class B: every emitted field that counts a fault, a miss, an overflow, a violation, a failure
# or a refusal, found at the emit sites: (line, key, the plugin file printing it, the ft_parse function whose rule reads
# it and the text in that function naming it, or None and the recorded reason the field decides nothing). The lines
# are in the hand-back and SHARED.md; test_fault_fields_are_every_emitted_fault_field holds the table to both sources
FAULT_FIELDS = (
    ("p", "excl", "FtFrames.cs", "menu_check", '"excl"'),
    ("p", "plant_mixed", "FtFrames.cs", "p_line_faults", "P_LINE_FAULTS"),
    ("p", "missing_end", "FtFrames.cs", "menu_check", '"missing_end"'),
    ("p", "guarded", "FtFrames.cs", "vr5_points", '"guarded"'),
    ("p", "zs", "FtFrames.cs", "void_rounds", '"zs"'),
    ("p", "off_g", "FtFrames.cs", "gate_counter_faults", "GATE_COUNTERS"),
    ("p", "off_gn", "FtFrames.cs", "gate_counter_faults", "GATE_COUNTERS"),
    ("p", "off_on", "FtFrames.cs", "gate_counter_faults", "GATE_COUNTERS"),
    ("p", "on_guarded", "FtFrames.cs", "gate_counter_faults", "GATE_COUNTERS"),
    ("p", "own_split", "FtFrames.cs", "own_split_faults", '"own_split"'),
    ("p", "span_class_overflow", "FtFrames.cs", "p_line_faults", "P_LINE_FAULTS"),
    ("p", "gc_read_failures", "FtFrames.cs", None,
     "a GC count read that threw (counted at FtClock.cs:78); its window's cG prints NA, which b11_report names; V6's "
     "bound takes its GC term from the allocation counter's bytes (G_cap), never from cG"),
    ("p", "recv_offmain", "FtFrames.cs", "p_line_faults", "P_LINE_FAULTS"),
    ("p", "ledger_cycle_miss", "FtFrames.cs", "p_line_faults", "P_LINE_FAULTS"),
    ("p", "sock_main", "FtUpload.cs", "p_line_faults", "P_LINE_FAULTS"),
    ("p", "sock_thr", "FtUpload.cs", None,
     "socket calls on Photon's own thread, outside the frame (FtUpload.cs:345); SHARED.md (md5 3ab20794) reports it "
     "and charges it in no term"),
    ("p", "ab_back", "FtFrames.cs", "sitting_v", '"ab_back"'),
    ("p", "ab_retry", "FtFrames.cs", "sitting_v", '"ab_retry"'),
    ("counters", "missing_end", "FtSchedule.cs", "counters_faults", "COUNTER_KEYS"),
    ("counters", "cycle_failures", "FtSchedule.cs", "counters_faults", "COUNTER_KEYS"),
    ("counters", "span_depth_violations", "FtSchedule.cs", "counters_faults", "COUNTER_KEYS"),
    ("counters", "span_leave_mismatch", "FtSchedule.cs", "counters_faults", '"span_leave_mismatch"'),
    ("counters", "photon_offmain", "FtSchedule.cs", None,
     "X and listener scopes entered off the main thread open nothing (FtSpan.cs:295, 305); printed (counters_faults "
     "needs the key) and reported on the V6 lines (v_lines); ruled (R6-A3.11.152 (2)(h)): such an entry adds no "
     "collector time to a frame of the main thread, which is what U bounds, so it is reported and decides nothing"),
    ("settled", "problems", "FtCalib.cs", "arm_problems", '"problems"'),
    ("settled", "missing_end", "FtCalib.cs", "vr2", '"missing_end"'),
    ("settled", "cycle_failures", "FtCalib.cs", "vr2", '"cycle_failures"'),
    ("settled", "span_depth_violations", "FtCalib.cs", "vr2", '"span_depth_violations"'),
    ("census", "guarded", "FtCensus.cs", "vr5_points", '"guarded"'),
    ("census", "outside", "FtCensus.cs", None,
     "an entry's calls outside the live moment (FtCensus.cs:57): where a call landed, not a fault of the instrument"),
    ("scope census", "failed", "FtCensus.cs", "boot_controls", '"failed"'),
    ("census_summary", "missing", "FtEntries.cs", "census_summary", '"missing"'),
    ("census_summary", "duplicates", "FtEntries.cs", "census_summary", '"duplicates"'),
    ("a3rows", "missing", "FtA3.cs", None,
     "A3's row registry: a row that failed to register writes no a3 or a3drain line, which a3() requires; V6's "
     "verdict reads no A3 term"),
    ("a3rows", "duplicates", "FtA3.cs", None,
     "a row registered twice keeps one name (FtA3.cs:216); as a3rows missing, V6's verdict reads no A3 term"),
    ("cal", "unscoped", "FtA3.cs", "a3_live", '"unscoped"'),
    ("cal", "depth_err", "FtA3.cs", "a3_live", '"depth_err"'),
    ("cal", "errors", "FtCalib.cs", None,
     "each errored entry prints its own 'kind=disp shape=<s> failed:' line (FtCalib.cs:229), which VR2 reads as a "
     "calibration carrying failure warnings"),
    ("FT-GATE", "missing", "FtRoomGate.cs", "attach_gate_faults", "missing="),
    ("FT-GATE", "excluded", "FtRoomGate.cs", None,
     "the entry points the room gate leaves by design (names, not a count)"),
    ("offthread", "span_off", "FtHeavy.cs", None,
     "component scopes opened off the main thread open nothing (FtSpan.cs:241); reported by report(); ruled "
     "(R6-A3.11.152 (2)(h)) as photon_offmain: reported, it decides nothing"),
    ("attach", "missing", "FtAttach.cs", "attach_faults", '"missing"'),
    ("refusals", "pairs", "FtUpload.cs", "vr6_build", '"refusals"'),
    ("refused", "n", "FtUpload.cs", None,
     "the per-refusal trace; its counts reach VR6 through the cumulative refusals line"),
    ("room call refused", "n", "FtRoomGate.cs", None,
     "the room gate refusing a room call while it holds a measured boot is its design (FtRoomGate.cs:87)"),
)
# the field names a scan of the emit sites takes as counting a fault (the explicit rows above add the n= and pairs=
# counts of the refusal lines, which no name tells apart)
FAULT_WORDS = re.compile(r"\w*(?:fail|miss|overflow|violation|mismatch|refus|err|excl|mixed|offmain|_main|retry|_back"
                         r"|split|problems|duplicates|unscoped|guarded|outside|off_g|off_on|span_off|sock_thr)\w*|zs")


def test_fault_fields_are_every_emitted_fault_field():
    # ruling R6-A3.11.151 (2) class B: every field of plugin/Ft*.cs whose name counts a fault is a FAULT_FIELDS row
    # (by file), every row's key is printed by its file (FtAttach.cs's once merged), and each row names either a rule,
    # a function of ft_parse whose source holds the row's text (a constant named there holding the key), or a reason
    import inspect
    plug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin")
    found = set()
    for fn in sorted(os.listdir(plug)):
        if not (fn.startswith("Ft") and fn.endswith(".cs")):
            continue
        s = re.sub(r"(?m)^\s*//.*$", "", open(os.path.join(plug, fn), encoding="utf-8").read())
        for lit in re.findall(r'"((?:[^"\\\n]|\\.)*)"', s):
            for k in re.findall(r"(?:^| )(\w+)=", lit):
                if FAULT_WORDS.fullmatch(k):
                    found.add((fn, k))
    rows = set((f, k) for _, k, f, _, _ in FAULT_FIELDS)
    assert sorted(found - rows) == [], sorted(found - rows)
    for line, k, f, rule, how in FAULT_FIELDS:
        path = os.path.join(plug, f)
        if f == "FtAttach.cs" and not os.path.exists(path):
            continue
        s = open(path, encoding="utf-8").read()
        assert re.search(r'"(?:[^"\n]* )?%s=' % k, s), (line, k, f)
        if rule is None:
            assert how and len(how) > 20, (line, k)
            continue
        src = inspect.getsource(getattr(P, rule))
        assert how in src, (line, k, rule, how)
        if re.fullmatch(r"[A-Z_]+", how):
            assert k in getattr(P, how), (line, k, how)


def _c_planted():
    """A clean sitting-C log with the plant's boot line (FtPlant.Fix), which the fixture otherwise leaves out."""
    mark = "[FRAME-TIME] mark cost cyc=50 p90=70 n=1000"
    return _sub1(_c_text(), mark, mark + "\n" + LOG_PREFIX + "[FRAME-TIME] plant c_plant=80 ticks=800 from=0.1.2")


_DISP0 = "cal i=4 why=game3 kind=disp shape=%s n=100000 u=1000000,1000000 p=1030000,1030000" % sorted(SHAPES)[0]
_HEAVY0 = "\n" + LOG_PREFIX + ("[FRAME-TIME] heavy g=3 op=%s live=0 between=7 pick=1 over=1 menu=0 at_call=0 edge=0 off=0"
                               % P.HEAVY_OPS[0])
# the follow-up to ruling .149, B: every instrument the emitter attaches or arms (plugin/Ft*.cs, and the evidence
# patches whose sites the ledger reads), as (instrument, what attaches or arms it: the Harmony patch classes, the
# Harmony.Patch call, the player-loop systems or the writer it wraps; the source text of the line reporting its attach
# state; the parser rule that withholds or refuses when it is not attached; the sitting the rule is read in, V
# (sitting_v's WITHHELD list), C (sitting C's two-arm rows) or refuse (read_sitting refuses); a spoil of the clean
# log; the reason, or the refusal's words, the rule then gives). chk_instruments_not_attached_withhold runs each row;
# test_every_attached_instrument_has_a_row holds the table to the source
INSTRUMENTS = (
    ("the player-loop clock", ("PlayerLoop:FtStart", "PlayerLoop:FtEnd", "PlayerLoop:FtPlantTick"),
     '"[FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate "',
     "validity 'complete sitting': FAILURE_EVENTS 'clock refused:' (no clock, no game line)", "V",
     lambda t: t + "\n" + LOG_PREFIX + "[FRAME-TIME] clock refused: player-loop phase missing (EarlyUpdate True, "
                                       "PreLateUpdate True, Update False)",
     "complete sitting: failure event: clock refused: "),
    ("the clock's cycle reader", ("FtClock.Cycles",), '"[FRAME-TIME] clock installed freq="',
     "validity 'VR2 instrument': settled cycle_failures=0 (and the counters line's)", "V",
     lambda t: _settled_add(t, 3, " cycle_failures=1"), "VR2 instrument: settled g=3 cycle_failures=1"),
    ("the allocation counter", ("FtAlloc.Init",), '"[FRAME-TIME] alloc pin="',
     "boot_controls: the pin, and K1", "V",
     lambda t: _sub1(t, dict(V6_BOOT)["alloc"], "alloc pin=differs planted=1048600/1048576 empty=0"),
     "the counter's pin differs or is not read (pin=differs)"),
    ("the writer ledger's disk-log tap", ("DiskLogListener.LogWriter",), '"[FRAME-TIME] ledger log="',
     "ledger_state: one line, log=1, types= the parser's writer types", "V",
     lambda t: _sub1(t, LEDGER_OK, "ledger log=0 why=no_disk_listener types=log,hash,recv,sock"),
     "the disk-log tap: ledger log=0 why=no_disk_listener: "),
    ("class X's and E's photon patches", ("FtPhotonXPatch", "FtPhotonEPatch"), '"[FRAME-TIME] photon patches n="',
     "boot_controls: R-SCOPE's patches line (the ten typed names); validity 'ATTACH'", "V",
     lambda t: _sub1(t, dict(V6_BOOT)["photon"], "photon patches n=9 names=" + ",".join(
         x for x in P.PHOTON_ENTRIES if x != "LoadBalancingClient.OnMessage")),
     "R-SCOPE's patches line out of range (n=9 for 9 names; not attached: LoadBalancingClient.OnMessage)"),
    ("the listener scopes", ("FtCensus scope wrap",), '"[FRAME-TIME] scope census entries="',
     "boot_controls: R-SCOPE's census line (wrapped = entries, not failed)", "V",
     lambda t: _sub1(t, "scope census entries=40 wrapped=40", "scope census entries=40 wrapped=39"),
     "R-SCOPE's census line out of range (entries 40, wrapped 39)"),
    ("the census entry registry", ("FtE.RegisterAll",), '"[FRAME-TIME] census registered="',
     "validity 'census summary'", "V",
     lambda t: _sub1(t, CENSUS_CLEAN, CENSUS_SUMMARY % (len(ENTRIES), len(ENTRIES), 1, 0)), "census summary: "),
    ("the census entry patches", ("FtE.PatchType",), '" kind=disp shape=" + c.Name + " failed: " + c.Error',
     "validity 'VR2 instrument': a failed disp line, by its shape; validity 'ATTACH'", "V",
     lambda t: _sub1(t, _DISP0, _DISP0.split(" n=")[0] + " failed: PatchException: no target"),
     "VR2 instrument: game 3: calibration 4 carries failure warnings for disp"),
    ("the calibration dummies", ("harmony.Patch(c.Dummy",), '" kind=disp shape=" + c.Name + " failed: " + failed',
     "validity 'VR2 instrument': a failed disp line, by its shape", "V",
     lambda t: _sub1(t, _DISP0, _DISP0.split(" n=")[0] + " failed: HarmonyException: patch"),
     "VR2 instrument: game 3: calibration 4 carries failure warnings for disp"),
    ("the per-game collectors", ("FtSchedule.Open",), '"[FRAME-TIME] opened g="', "validity 'VR5 records'", "V",
     lambda t: _sub1(t, "opened g=3 se=1 ce=1 ic=1", "opened g=3 se=1 ce=1 ic=0"), "VR5 records: "),
    ("the K2 scope plant", ("FtSpan.Plant",), '"[FRAME-TIME] scope plant asked="', "boot_controls: K2", "V",
     lambda t: _sub1(t, "scope plant asked=2000 got=2010", "scope plant asked=2000 got=2101"),
     "control K2 out of range (asked 2000"),
    ("the K3 nest plant", ("FtPhoton.Nest",), '"[FRAME-TIME] nest plant asked="', "boot_controls: K3", "V",
     lambda t: _sub1(t, "nest plant asked=2000 x=2020 e=1990 p=2005", "nest plant asked=2000 x=2020 e=1899 p=2005"),
     "control K3 out of range (asked 2000 us (needs 2000), read x 2020, e 1899"),
    ("the control mutant", ("FtSpan.SetMutants",), '"[FRAME-TIME] controls k_mutant="',
     "refuse_k_mutant: a sitting log with another k_mutant than none is refused", "refuse",
     lambda t: _sub1(t, "controls k_mutant=none", "controls k_mutant=k1"), "K-MUTANT"),
    ("the room gate", ("FtRoomGatePunPatch", "FtRoomGateNchVoidPatch", "FtRoomGateNchRoutinePatch"),
     '"[FRAME-TIME] FT-GATE patched "', "validity 'ATTACH' (its room gate part, and its line)", "V",
     lambda t: _sub1(t, "FT-GATE patched 13 entry points expected=13", "FT-GATE patched 12 entry points expected=13"),
     "ATTACH: FT-GATE patched 12 entry points of 13 expected"),
    ("the churn-timer freeze", ("FtChurnFreezePatch",), '"[FRAME-TIME] churn freeze failed: "',
     "validity 'complete sitting': FAILURE_EVENTS 'churn freeze'; validity 'ATTACH'", "V",
     lambda t: t + "\n" + LOG_PREFIX + "[FRAME-TIME] churn freeze failed: boom",
     "complete sitting: failure event: churn freeze "),
    ("the socket hook", ("FtSockPatch",), "[HARMONY] Failed to patch {type.Name}", "validity 'ATTACH'", "V",
     lambda t: t + "\n" + HARMONY_FAIL % "FtSockPatch", "ATTACH: line "),
    ("the route hook", ("FtRoute_SendPatch",), "[HARMONY] Failed to patch {type.Name}", "validity 'ATTACH'",
     "V", lambda t: t + "\n" + HARMONY_FAIL % "FtRoute_SendPatch", "ATTACH: line "),
    ("the self-drive", ("FtDrive_InputPatch", "FtDrive_PickPatch"), '"[FRAME-TIME] sitting complete g="',
     "validity 'complete sitting' (its line proves the drive); validity 'ATTACH'", "V",
     lambda t: t + "\n" + HARMONY_FAIL % "FtDrive_InputPatch", "ATTACH: line "),
    ("the recv scopes' sites", ("HitEvidence_ExecuteRpcPatch",), "[HARMONY] Failed to patch {type.Name}",
     "validity 'ATTACH' (its Failed-to-patch part)", "V",
     lambda t: t + "\n" + HARMONY_FAIL % "HitEvidence_ExecuteRpcPatch", "ATTACH: line "),
    ("the frame-rate cap hold", ("Plugin FPSCAP hold",), '"[FPSCAP] held by frame-time calibration"',
     "validity 'VR1': the hold's line", "V",
     lambda t: t.replace(LOG_PREFIX + "[FPSCAP] held by frame-time calibration\n", "", 1),
     "VR1: no '[FPSCAP] held by frame-time calibration' line"),
    ("the arming", ("FtArm.Arm",), '"[FRAME-TIME] armed room="',
     "sitting V's force=ON condition; validity 'complete sitting' (an unarmed game writes no settled line)", "V",
     lambda t: re.sub(r"(settled g=3 [^\n]*) force=ON", r"\1 force=none", t, count=1),
     "sitting V: this seat's settled lines print another force= than ON (g=3 force=none)"),
    ("the plant", ("FtPlant.Fix",), '"[FRAME-TIME] plant c_plant="',
     "sitting C's two-arm 'VR2 e_C_lo': FAIL, not computable (it weakens the cross-check)", "C",
     lambda t: _sub1(t, "\n" + LOG_PREFIX + "[FRAME-TIME] plant c_plant=80 ticks=800 from=0.1.2", ""),
     "VR2 e_C_lo FAIL: not computable: e_C needs exactly one plant line with c_plant > 0 (got [])"),
    ("the heavy and off-thread marks", ("FtHeavy.Mark",), '"[FRAME-TIME] heavy g="',
     "validity 'complete sitting': one heavy line per operation per game", "V",
     lambda t: _sub1(t, _HEAVY0, ""), "complete sitting: game 3: 0 heavy lines for %s (needs 1)" % P.HEAVY_OPS[0]),
)


def chk_instruments_not_attached_withhold(m):
    # the follow-up to ruling .149, B: each INSTRUMENTS row's rule on its spoil: the reason in sitting V's WITHHELD
    # list (and so on the seat's V6 WITHHELD line), the two-arm row in sitting C, or the refusal; the clean log of the
    # same sitting (the control) gives none of them, and each row's attach-state line is in the source
    src = _plugin_src()
    v, c = _v_text(), _c_planted()
    assert _v(m, v)["why"] == [], _v(m, v)["why"]
    rc = m.read(c)
    two_c = ["%s %s: %s" % x for x in m.sitting_c(rc, c, rc, c, None, "C:a")["two"]]
    m.read_sitting(v, "V:a")
    for name, by, emit, rule, where, spoil, want in INSTRUMENTS:
        assert emit in src, (name, emit)
        if where == "V":
            bad = spoil(v)
            assert bad != v, name
            why = _v(m, bad, v)["why"]
            assert [x for x in why if x.startswith(want)], (name, want, why)
        elif where == "C":
            bad = spoil(c)
            rb = m.read(bad)
            two = ["%s %s: %s" % x for x in m.sitting_c(rb, bad, rc, c, None, "C:a")["two"]]
            assert [x for x in two if x.startswith(want)] and not [x for x in two_c if x.startswith(want)], \
                (name, want, two, two_c)
        else:
            assert _word_refused(lambda: m.read_sitting(spoil(v), "V:a"), want), name


def test_every_attached_instrument_has_a_row():
    # the follow-up to ruling .149, B: every Harmony patch class, Harmony.Patch call and player-loop system in
    # plugin/Ft*.cs, and the disk-log writer FtLedger wraps, is named by an INSTRUMENTS row; every name a row gives
    # for a patch class is a class the plugin declares
    plug = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "plugin")
    named = set(x for row in INSTRUMENTS for x in row[1])
    found, every = set(), ""
    for fn in sorted(os.listdir(plug)):
        if not fn.endswith(".cs"):
            continue
        s = re.sub(r"(?m)^\s*//.*$", "", open(os.path.join(plug, fn), encoding="utf-8").read())
        every += s
        if not fn.startswith("Ft"):
            continue
        found |= set(re.findall(r"\[HarmonyPatch\b[^\]]*\]\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*class (\w+)", s))
        found |= set(re.findall(r"\b(\w+\.Patch\(\w+\.\w+)", s))
        found |= set("PlayerLoop:" + x for x in re.findall(r"PlayerLoopSystem \{ type = typeof\((\w+)\)", s))
        if "new Tap(d.LogWriter)" in s:
            found.add("DiskLogListener.LogWriter")
    # 10 patch classes, the dummies' Harmony.Patch call, 3 player-loop systems and the disk-log writer at this tree
    assert len(found) >= 15, sorted(found)
    assert sorted(found - named) == [], sorted(found - named)
    for x in named:
        if x.endswith("Patch") and "." not in x and ":" not in x:
            assert re.search(r"\bclass %s\b" % x, every), x


# the B11 mutants (mut_parse.py's B11_MUTS) are proven here, in process, so a seat's pytest run proves them: each row
# names the check functions it must turn red; mutant 0, the unchanged parser, keeps every check green
B11_CHECKS = ["chk_c2_recovers_3_25", "chk_c3_recovers_3_0375", "chk_c4_recovers_3_5", "chk_charge_never_negative",
              "chk_mates_have_joint_probability_0_or_half", "chk_a_pair_is_one_variance_unit",
              "chk_a_partial_mate_stays_in_its_pair", "chk_reconcile_reports_every_point", "chk_vr5_window_zero",
              "chk_classify_half_width_rule", "chk_classify_lower_bound_rule", "chk_r_common_comparator",
              "chk_full_profile_not_applied_to_partials", "chk_h_p_cross_check", "chk_baseline_frozen_q_minus_2",
              "chk_marker_whole_line", "chk_v4_lower_bound_at_lower_ends",
              "chk_r_common_d_common_and_corrected_r_u", "chk_own_split_withholds", "chk_token_open1_and_continuity",
              "chk_writers_recv_never_added", "chk_p_line_faults_withhold", "chk_ref_known_by_marker_not_by_na",
              # V6 (SHARED.md "V6: the direct bound"; m1 to m12)
              "chk_q_leaves_p_once", "chk_class_sum_holds_cp_and_cx", "chk_report_on_hand_computed_u",
              "chk_p_is_the_larger_of_cp_and_recv", "chk_forced_log_is_no_contrast_input",
              "chk_sitting_v_is_forced_on", "chk_sitting_v_withholds_the_counter_and_controls",
              "chk_t_ref_is_t_on_minus_u_hi", "chk_six_games_at_least", "chk_combine_four_classes",
              "chk_r_gc_numbers",
              # P1's V6 emitter (via the integrator, 12 Nov): the counters line's two keys and the boot's k_mutant
              "chk_counters_line_v6_keys", "chk_k_mutant_sitting_refused_and_controls_proof",
              # ruling R6-A3.11.149 (5) to (8)
              "chk_validity_set_withholds_sitting_v", "chk_vr1_reads_t_on", "chk_validity_set_decides_sitting_c",
              "chk_two_arm_guards_named_on_the_verdict_line", "chk_b3_on_both_sittings", "chk_seats_paired_by_name",
              "chk_void_rounds_stay_in_sitting_v", "chk_controls_forms_and_failed_to_patch",
              # the integrator's follow-up to ruling .149, A to D
              "chk_ledger_tap_withholds_sitting_v", "chk_attach_guard",
              "chk_instruments_not_attached_withhold", "chk_two_arm_three_words",
              "chk_reported_lines_never_end_the_verdict",
              # ruling R6-A3.11.151 (2): A the attach guard, B the fault counters, C the control read, D reported values
              "chk_gate_counters_rule_vr5_in_sitting_c", "chk_arm_problems_fail_the_complete_sitting",
              "chk_controls_ruled_lines_refused", "chk_reported_values_not_computable",
              "chk_r_gc_total_reads_every_measured_window", "chk_cross_risks_beside_the_interval",
              # the integrator's points H, I and J (P3b's end-to-end export test)
              "chk_cal_entries_failure_form", "chk_malformed_lines_are_refusals", "chk_reference_a3_form",
              # the confirming round's G1 (ruling R6-A3.11.152): emitted lists judged as written
              "chk_ledger_types_judged_as_written"]


@pytest.mark.parametrize("name", B11_CHECKS)
def test_b11_check(name):
    globals()[name](P)


def _b11_mut_rows():
    import ast
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mut_parse.py"), encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "B11_MUTS":
            return ast.literal_eval(node.value)
    raise AssertionError("mut_parse.py has no B11_MUTS")


def _mutated(anchor, repl):
    import types
    t = open(FT_SCRIPT, encoding="utf-8").read()
    assert t.count(anchor) == 1, (anchor, t.count(anchor))
    mod = types.ModuleType("ft_parse_mutant")
    mod.__file__ = FT_SCRIPT
    exec(compile(t.replace(anchor, repl), "ft_parse_mutant.py", "exec"), mod.__dict__)
    return mod


def test_b11_mutant_0_keeps_every_check_green():
    m = _mutated("def classify(u, tref, hw, lb):", "def classify(u, tref, hw, lb):")
    for name in B11_CHECKS:
        globals()[name](m)


@pytest.mark.parametrize("row", _b11_mut_rows(), ids=[r[0] for r in _b11_mut_rows()])
def test_b11_mutant_turns_its_checks_red(row):
    name, anchor, repl, kills = row
    assert kills and all(k in B11_CHECKS for k in kills), row
    m = _mutated(anchor, repl)
    for k in kills:
        with pytest.raises(AssertionError):
            globals()[k](m)


def test_b11_window_line_reads_every_field_and_refuses_disagreeing_repeats():
    text = _b11_text(_one_run_games(), _c2_model)
    w = [r for r in P.read(text) if r["kind"] == "w"][1]
    assert P.b11_line(w) and P.lacks_keys(w) == [] and w["unit"] == "P24" and w["pred"] in ("ON", "OFF")
    assert len(w["q"]) == len(w["r"]) == len(w["qn"]) == 10 and w["tok"] == B11_TOK0 and w["cG"] == 0
    assert w["prun"] == 0 and w["nm"] in (1, 4) and list(P._typed(w["wu"], 2, na=True)) == list(P.WRITER_TYPES)
    ln = [x for x in text.splitlines() if " w pt=" in x][0]
    with pytest.raises(P.Refused, match="plant printed twice"):
        P.parse_line(ln.replace("gcn=", "plant=1 gcn=", 1))
    assert P.parse_line(ln.replace("gcn=", "plant=0 gcn=", 1))["plant"] == 0
    with pytest.raises(P.RecordRefused):
        P.read(LOG_PREFIX + ln.replace(" tok=" + B11_TOK0, ""))
    with pytest.raises(P.RecordRefused):
        P.read(LOG_PREFIX + ln.replace(" prun=0", ""))


def test_b11_reconcile_clean_and_each_invariant_named():
    text = _two_points()
    assert P.window_reconcile(P.read(text)) == []
    cases = [
        # SHARED.md V6: the partition holds the classes P and X, and C° leaves P exactly once
        (lambda w: w.update(cS=w["cS"] + 1), "is not cG+cW+cR+cS+cP+cX+cE"),
        (lambda w: w.update(cP=w["cP"] + 1), "is not cG+cW+cR+cS+cP+cX+cE"),
        (lambda w: w.update(cX=w["cX"] + 1), "is not cG+cW+cR+cS+cP+cX+cE"),
        (lambda w: w.update(cP=w["cP"] + 1, cE=w["cE"] - 1), "is not sC-cG-cW-cP="),     # P moved out of E, kept in q
        (lambda w: w.update(q=[w["q"][0] + 1] + w["q"][1:]), "sum(q)="),
        (lambda w: w.update(r=[w["r"][0] + 1] + w["r"][1:], q=[w["q"][0] + 1] + w["q"][1:]), "sum(r)="),
        (lambda w: w.update(qn=[11, 13] + w["qn"][2:]), "is not n=120 in 12-frame bins"),
        (lambda w: w.update(unit="P13"), "unit P13 at position 2"),
        (lambda w: w.update(tok=B11_TOK0.replace("log:0,0,0,0,0,0,0", "log:0,0,0,0,0,0")), "is not type:open0,enqON"),
        (lambda w: w.update(wu="log:0:0"), "wu types log are not log,hash,recv,sock"),
        (lambda w: w.update(wu="hash:0:0;log:0:0;recv:0:0;sock:0:0"), "wu types hash,log,recv,sock are not"),
        (lambda w: w.update(tok=B11_TOK0.replace("sock:", "up:")), "tok types log,hash,recv,up are not"),
        (lambda w: w.update(wu="log:0:NA;hash:0:0;recv:0:0;sock:0:0"), None),
        (lambda w: w.update(prun=1), "plant-run and ordinary windows in one run (prun)"),
        (lambda w: w.update(plant=1, psF=0), "planted (plant=1) with prun=0"),
        (lambda w: w.update(pred="none"), "the game's previous window is"),
        (lambda w: w.update(res=1), "res=1, needs 0"),
        (lambda w: w.update(coin=1 - w["coin"]), "do not carry one committed coin"),
        (lambda w: w.update(wu="x:1"), "is not type:units:cycles"),
    ]
    for fn, want in cases:
        bad = _two_points(edit=lambda w, fn=fn: fn(w) if w["pt"] == "1.1.1" and w["wi"] == 2 else None)
        miss = P.window_reconcile(P.read(bad))
        if want is None:
            assert miss == [], miss                      # NA cycles are a well-formed wu: they withhold, not fault
        else:
            assert [x for x in miss if want in x], (want, miss)


def test_b11_ownership_and_ordinals():
    text = _two_points()
    lines = text.splitlines()
    orphan = [x for x in lines if " w pt=1.1.2 " in x][0].replace("pt=1.1.2", "pt=1.1.9")
    miss = P.window_reconcile(P.read(text + "\n" + orphan))
    assert "window lines of point 1.1.9: 0 owner point lines (needs exactly 1)" in miss, miss
    twice = [x for x in lines if " p pt=1.1.2 " in x][0]
    miss = P.window_reconcile(P.read(text + "\n" + twice))
    assert "window lines of point 1.1.2: 2 owner point lines (needs exactly 1)" in miss, miss
    gap = "\n".join(x for x in lines if not (" w pt=1.1.1 " in x and " wi=3 " in x))
    miss = P.window_reconcile(P.read(gap))
    assert [x for x in miss if "window ordinals 1,2,4,5 are not 1..4" in x], miss
    assert [x for x in miss if x.startswith("point 1.1.1: 4 window lines, the point line counts 5")], miss


def test_b11_plant_runs_and_res_windows_leave_the_estimate_and_are_counted():
    games = [[{"n": [120] * 8, "coins": [(1, 0), (0, 1)], "plant": (1,)}]]
    text = _b11_text(games, _flat)
    assert P.window_reconcile(P.read(text)) == []
    T = P.b11_terms(P.read(text))
    assert T["loss"] == {"plant": 480, "res": 120, "all": 960} and T["N"] == 360
    lines, e = P.b11_report(P.read(text))
    assert [x for x in lines if "plant runs 480 frames, res=1 windows 120 frames, 62.50 percent of 960" in x], lines
    assert "B11 plant runs: 1, 0 unspun" in "\n".join(lines), lines
    # P1's notes: a plant run fixed before c_plant is unspun (prun=1, nothing planted) and still leaves the estimate
    un = _b11_text([[{"n": [120] * 8, "coins": [(1, 0), (0, 1)], "plant": (1,), "unspun": (1,)}]], _flat)
    assert P.window_reconcile(P.read(un)) == []
    assert not [w for w in P.read(un) if w["kind"] == "w" and w["plant"]]
    T2 = P.b11_terms(P.read(un))
    assert T2["N"] == 360 and T2["loss"]["plant"] == 480 and T2["unspun"] == [(1, "1.1.1", 1)]
    assert [x for x in P.b11_report(P.read(un))[0] if x.startswith("B11 plant runs: 1, 1 unspun") and
            x.endswith("; 1.1.1 run 1")]


def test_b11_transitions_own_split_and_na_writers():
    # SHARED.md (md5 18fdafea), P1's notes: the class-transition overhead per arm (nm x the boot line's median, as a
    # share of C; reported, never subtracted), own_split by arm, and NA writer cycles withholding B1 for the seat
    games = [[{"n": [120] * 4, "coins": [(1, 0)], "own_split": 2}, {"n": [120, 60], "coins": [(0, 0)]}]]
    recs = P.read(_b11_text(games, _flat))
    lines, e = P.b11_report(recs)
    T = e["T"]
    on = [w for w in T["pop"] if w["arm"] == "ON"]
    off = [w for w in T["pop"] if w["arm"] == "OFF"]
    tx, why = P.b11_transitions(recs, T)
    assert tx["ON"] == (4 * len(on), pytest.approx(4 * len(on) * 50 / sum(w["sC"] for w in on), rel=1e-12))
    assert tx["OFF"] == (len(off), pytest.approx(len(off) * 50 / sum(w["sC"] for w in off), rel=1e-12))
    assert [x for x in lines if x.startswith("B11 class transitions (in the charge, reported only): median 50 cycles "
                                             "(p90 70, n 1000); ON %d marks" % (4 * len(on)))], lines
    assert "B11 own_split (windows written partial by an owner split, an ownership fault): 1.1.1 2" in lines
    lines0, e0 = P.b11_report(P.read(_b11_text(games, _flat, mark=False)))
    assert "B11 class transitions: not computable: 0 mark cost lines (needs exactly 1)" in lines0
    assert e0["bu"] == e["bu"]                       # reported only: the bound does not move with the overhead
    two = _b11_text(games, _flat).replace("[FRAME-TIME] mark cost", "[FRAME-TIME] mark cost cyc=50 p90=70 n=1000\n"
                                          + LOG_PREFIX + "[FRAME-TIME] mark cost", 1)
    assert "B11 class transitions: not computable: 2 mark cost lines (needs exactly 1)" in P.b11_report(P.read(two))[0]
    na = _b11_text(games, _flat, edit=lambda w: w.update(wu="log:0:0;hash:0:0;recv:0:0;sock:3:NA")
                   if w["wi"] == 2 else None)
    assert P.window_reconcile(P.read(na)) == []
    lines, e = P.b11_report(P.read(na))
    assert e["T"]["wu_na"] == ["sock"] and ("B11 writers: cycles print NA for sock (reported: the writers left the "
                                            "contrast's verdict with B_U; in sitting V an NA withholds B1)") in lines


def test_b11_gc_na_windows_are_checked_without_cg_and_named():
    # the integrator (11 Nov): cG=NA when the native hook's completeness check fails; the identity drops cG, the
    # window is flagged, and the GC charge takes the all-GC fallback for the estimate
    text = _b11_text(_one_run_games(), _c2_model, cg=lambda w: None if w["wi"] == 2 else 30)
    recs = P.read(text)
    assert P.window_reconcile(recs) == []
    lines, e = P.b11_report(recs)
    gl = [x for x in lines if x.startswith("B11 GC:")]
    # ruling R6-A3.11.151 (2) class D, F15: the text says what V6 does (SHARED.md:235 retired G_U and its fallback)
    assert gl and gl[0].startswith("B11 GC: cG prints NA in 4 windows (") and "fallback" not in gl[0], gl
    assert ("their identity is checked without cG and their C° keeps their GC, which the contrast then carries; V6 has "
            "no G_U (B_U's terms left the verdict, SHARED.md V6), and the bound's GC term is sitting V's G_cap") in gl[0]
    doc = " ".join(P.b11_estimate.__doc__.split())
    assert "fallback" not in doc and "withhold" not in doc.replace("withholds nothing", ""), doc
    assert "the envelope enters no figure" in doc, doc
    assert "1.1.1.2" in gl[0] and "2.1.1.2" in gl[0]
    bad = _b11_text(_one_run_games(), _c2_model, cg=lambda w: None if w["wi"] == 2 else 30,
                    edit=lambda w: w.update(sC=w["sC"] + 30) if w["cG"] is None else None)
    assert [x for x in P.window_reconcile(P.read(bad)) if "is not cW+cR+cS+cP+cX+cE" in x]
    ok = _b11_text(_one_run_games(), _c2_model)
    assert "B11 GC: G available in every window" in P.b11_report(P.read(ok))[0]


def test_b11_report_withholds_b1_and_prints_both_risks():
    # SHARED.md V6, What P2 builds (5): the as-built report prints the contrast as a cross-check with its interval,
    # T_ref and the guards as built, and gives no B1 verdict of its own; ruling R6-A3.11.149 (5)(c), (d): the validity
    # set before it, the two-arm guards beside it (one line each); its risks follow them
    text = _b11_text(_one_run_games(), _c2_model)
    out = P.report(text, peer=text)
    assert not re.search(r"^VERDICT B1", out, re.M), out
    ln = [x for x in out.splitlines() if x.startswith("B1 CROSS-CHECK")]
    assert len(ln) == 1 and re.search(r"contrast [0-9.]+ us per frame, interval -?[0-9.]+ to [0-9.]+ .*T_ref as built "
                                      r"[0-9.]+ us; guards as built: the cross-check is (available|unavailable)", ln[0]), ln
    i = out.splitlines().index(ln[0])
    assert [x.split(" ")[0] for x in out.splitlines()[i - len(P.VALIDITY):i]] == ["VALIDITY"] * len(P.VALIDITY)
    two = out.splitlines()[i + 1:i + 1 + len(P.TWO_ARM)]
    assert [re.match(r"TWO-ARM (.+?) (PASS|FAIL|NOT TESTED): ", x).group(1) for x in two] == list(P.TWO_ARM), two
    # the follow-up to ruling .149, C: without a reference R-COMMON's word is NOT TESTED, its input named
    assert two[-1] == "TWO-ARM R-COMMON NOT TESTED: no reference log", two
    tail = out.splitlines()[i + 1 + len(P.TWO_ARM):i + 7 + len(P.TWO_ARM)]
    assert [x.strip().split(" ")[0] for x in tail] == ["R-CARRY", "R-COMMON", "R-PATH", "R-PREFIX", "R-REST", "these"], tail
    assert "R-COMMON UNTESTED: no reference record set" in out
    for want in ("B11 contrast", "B11 carryover c_ON", "B11 corrected bound", "R-CARRY falsifier: between-window",
                 "B11 point 1.1.1: 480 frames, wall 86.400 s, terminal window 120 frames, ON-frame share 0.5000, "
                 "mean frame time ON 180000.0 us, OFF 180000.0 us (diagnostic)"):
        assert want in out, (want, out)


def test_b11_exposure_diagnostics_per_point():
    # ruling .140 (3): frames, wall duration, terminal length, ON-frame share and mean frame time by arm, per point
    e = _est(_b11_text(_one_run_games(), _c2_model))
    pt, n, wall, last, sh, mon, moff = e["points"][0]
    assert (pt, n, last, sh) == ("1.1.1", 480, 120, 0.5) and wall == pytest.approx(86.4)
    assert mon == pytest.approx(B11_T) and moff == pytest.approx(B11_T) and len(e["points"]) == 4
    games = [[{"n": [120, 60], "coins": [(1, 1)]}]]
    pt, n, wall, last, sh, mon, moff = _est(_b11_text(games, _flat))["points"][0]
    assert (n, last, sh, moff) == (180, 60, 1.0, None)
    with pytest.raises(P.Refused, match="exposure envelope"):
        _est(_b11_text(_one_run_games(), _c2_model), exposure=(-1, "x"))
    with pytest.raises(P.Refused, match="exposure envelope"):
        _est(_b11_text(_one_run_games(), _c2_model), exposure=(1, ""))


def test_b11_reference_input_and_markers():
    # the integrator (11 Nov): each input carries its own build marker exactly once; R-COMMON reads the reference
    text = _b11_text(_one_run_games(), _c2_model)
    ref = _as_ref(text)
    refr = P.read_reference(ref, "ref.log")
    assert refr and all(r["kind"] in ("w", "settled") for r in refr)
    out = P.report(text, peer=text, ref=ref)
    assert "R-COMMON comparator: the reference's total common cost" in out, out
    with pytest.raises(P.MarkerRefused, match="MARKER-WRONG-ROLE"):
        P.report(ref, peer=text)
    with pytest.raises(P.MarkerRefused, match="MARKER-WRONG-ROLE"):
        P.read_reference(text)
    with pytest.raises(P.MarkerRefused, match="MARKER-ABSENT"):
        P.report(_b11_text(_one_run_games(), _c2_model, marker=False), peer=text)
    with pytest.raises(P.MarkerRefused, match="MARKER-ABSENT"):
        P.read_reference(_b11_text(_one_run_games(), _c2_model, marker=False))
    two = LOG_PREFIX + "[FRAME-TIME] " + P.MARK_FT + "\n" + text
    with pytest.raises(P.MarkerRefused, match="MARKER-REPEATED"):
        P.report(two, peer=text)
    with pytest.raises(P.MarkerRefused, match="MARKER-REPEATED"):
        P.read_reference(LOG_PREFIX + "[FRAME-TIME] " + P.MARK_REF + "\n" + ref)
    with pytest.raises(P.MarkerRefused, match="MARKER-UNKNOWN"):
        P.report(LOG_PREFIX + "[FRAME-TIME] build variant=Release\n" + text, peer=text)
    with pytest.raises(P.MarkerRefused, match="MARKER-ABSENT: the measurement input peer.log"):
        P.report(text, peer=_b11_text(_one_run_games(), _c2_model, marker=False), peer_src="peer.log")


def test_b11_reference_through_the_script(tmp_path):
    text = _b11_text(_one_run_games(), _c2_model)
    a, r = tmp_path / "a.log", tmp_path / "r.log"
    a.write_text(text + "\n", encoding="utf-8")
    r.write_text(_as_ref(text) + "\n", encoding="utf-8")
    rc, out, err = _run_script(a, a, "--ref", r)
    assert rc == 0 and "R-COMMON comparator" in out, (rc, out, err)
    rc, out, err = _run_script(a, a, "--ref", a)
    assert rc == 3 and "MARKER-WRONG-ROLE" in out, (rc, out, err)
    # SHARED.md D5: the peer seat's log by --peer, the same report as the positional form
    rc2, out2, err2 = _run_script(a, "--peer", a, "--ref", r)
    rc1, out1, _ = _run_script(a, a, "--ref", r)
    assert rc2 == 0 and out2 == out1 and "B1 CROSS-CHECK (sitting C" in out2, (rc2, err2)
    assert "peer-driven" not in out2 and "VERDICT B1" not in out2, out2


def test_v6_report_on_and_combine_through_the_script(tmp_path):
    # SHARED.md V6, What P2 builds, and ruling R6-A3.11.149 (6) 6: --on <seat>=<V log> <seat>=<V log> prints sitting
    # V's figures per seat; --combine V:<seat>=<log> ... C:<seat>=<log> ... prints VERDICT B1 per seat and the worse
    # seat, each seat's logs paired by its name; a log given by position, or a seat without both logs, is a refusal
    # (exit 3)
    v, c = tmp_path / "v.log", tmp_path / "c.log"
    v.write_text(_v_text() + "\n", encoding="utf-8")
    c.write_text(_c_text() + "\n", encoding="utf-8")
    rc, out, err = _run_script("--on", "a=%s" % v, "b=%s" % v)
    assert rc == 0 and len(re.findall(r"^V6 U [0-9.]+ us per live frame = D 60\.000 ", out, re.M)) == 2, (rc, out, err)
    assert "VERDICT B1" not in out and re.search(r"^V6 WITHHELD seat a: none$", out, re.M), out
    rc, out, err = _run_script("--on", v, v)
    assert rc == 3 and "REFUSED: PAIRING: '%s' is not of the form <seat>=<log>" % v in out, (rc, out, err)
    rc, out, err = _run_script("--combine", "V:a=%s" % v, "V:b=%s" % v, "C:b=%s" % c, "C:a=%s" % c)
    assert rc == 0 and _classes(out) == ({"a": "PASS", "b": "PASS"}, [("a", "PASS")]), (rc, out, err)
    rc, out, err = _run_script("--combine", "V:a=%s" % v, "V:b=%s" % v, "C:a=%s" % c)
    assert rc == 3 and "REFUSED: PAIRING: sitting C's seats ['a'] (and the references' []) are not sitting V's" in out, \
        (rc, out, err)
    rc, out, err = _run_script("--combine", "V:a=%s" % v, "V:a=%s" % v, "C:a=%s" % c, "C:b=%s" % c)
    assert rc == 3 and "REFUSED: PAIRING: seat a is named twice for V" in out, (rc, out, err)
    # a control run's boot: refused as a sitting log, read by --controls; a whole sitting log's every line is a
    # known form
    k = tmp_path / "k1.log"
    k.write_text(_v_text(boot={"controls": "controls k_mutant=k1", "alloc": K1_OUT}) + "\n", encoding="utf-8")
    rc, out, err = _run_script("--on", "a=%s" % k, "b=%s" % v)
    assert rc == 3 and "REFUSED: K-MUTANT: the sitting log V:a" in out, (rc, out, err)
    # ruling R6-A3.11.151 (2) class C: --controls <profile>=<boot log>; the bare form, two logs, an unknown profile and
    # a log of another profile's k_mutant are refused with the usage line
    rc, out, err = _run_script("--controls", "boot-k1=%s" % k)
    assert rc == 0 and ("CONTROLS PROOF PASS: profile boot-k1, k_mutant=k1; out of range K1 (needs exactly K1); "
                        "R-SCOPE's patches and census in range; 0 unknown line forms") in out, (rc, out, err)
    assert "CONTROLS profile boot-k1: k_mutant=k1, the profile's; every ruled line once and in its form" in out, out
    use = "; " + P.CONTROLS_USAGE
    for args, want in ((["--controls", k], "REFUSED: CONTROLS-REFUSED: --controls takes one <profile>=<boot log> "
                                          "(got '%s')%s" % (k, use)),
                       (["--controls"], "REFUSED: CONTROLS-REFUSED: --controls takes one <profile>=<boot log> "
                                        "(got nothing)%s" % use),
                       (["--controls", "boot-k1=%s" % k, "boot-k1=%s" % k], "REFUSED: CONTROLS-REFUSED: --controls "
                                                                            "takes one <profile>=<boot log> (got "),
                       (["--controls", "boot-k4=%s" % k], "REFUSED: CONTROLS-REFUSED: --controls takes one "
                                                          "<profile>=<boot log> (got 'boot-k4="),
                       (["--controls", "boot-k2=%s" % k], "REFUSED: CONTROLS-REFUSED: the boot log %s prints "
                                                          "k_mutant=k1; the profile boot-k2's boot prints k_mutant=k2"
                                                          % k)):
        rc, out, err = _run_script(*args)
        assert rc == 3 and want in out, (args, rc, out, err)
    assert P.CONTROLS_USAGE.startswith("usage: ft_parse.py --controls <profile>=<boot log>")
