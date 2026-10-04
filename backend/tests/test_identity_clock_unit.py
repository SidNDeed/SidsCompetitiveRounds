"""Identity, clock and connection evidence, server half, without a database:
the wire (record bounds and cross-field rules), the envelope and its own
signature, the clock header, the reference budgeter (byte proof and the
over-cap record), the descriptive measures, the clock fit, the identity rule
scope of the review evaluator, and the static scans of the match path.

Every rule, parameter and threshold here is SYNTHETIC (visibly arbitrary,
unrelated to any revision a server runs). Rows S5, S6, Q1, Q3, Q5, C2, C12 of
the build bar; report findings L1, L2, L4, L8, L9, L10, L11."""

import ast
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import identity_clock_evidence as ice  # noqa: E402
import identity_clock_fixtures as fx  # noqa: E402
import identity_clock_measures as icm  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import seat_evidence as se  # noqa: E402

W = ice.IC_WIRE
SRC = {n: open(os.path.join(API, n), encoding="utf-8").read()
       for n in ("main.py", "identity_clock_evidence.py", "identity_clock_measures.py",
                 "conn_ranges.py")}


def _check(rec):
    ice.ice_check_record(json.loads(ice.ice_budget_record(rec)))


def _refused(rec, field):
    with pytest.raises(se.EvidenceRefused) as e:
        ice.ice_check_record(rec)
    assert (e.value.status, e.value.field) == (422, field)


# -- the wire ---------------------------------------------------------------------

def test_a_well_formed_record_passes_every_check():
    _check(fx.base_record())
    _check(fx.base_record(points=0))


def test_the_key_set_and_order_are_the_layout():
    rec = fx.base_record()
    _refused({k: rec[k] for k in ice.IC_KEYS if k != "gdig"}, "gdig")
    _refused(dict(rec, extra=1), "extra")
    swapped = {k: rec[k] for k in ("consts", "schema") + ice.IC_KEYS[2:]}
    _refused(swapped, "key_order")


@pytest.mark.parametrize("field,value", [
    ("schema", 2), ("consts", -1), ("t0_src", "x"), ("proc", ["XYZ", 1, 3, 0, 0]),
    ("pt_s", [fx.pt_s(i, i) for i in range(W["pt_max"] + 1)]),
    ("gdig", [[0, "a" * 63, 0, 1]]), ("tdg", [1, 0, [1.5]]),
    ("asm", [["bad name!", "1.0", 0]]), ("gclk", [W["gclk_cppm_max"] + 1, 1, 1]),
])
def test_each_bound_refuses_with_its_key(field, value):
    _refused(fx.base_record(**{field: value}), field)


def test_l1_a_boot_run_names_an_occurrence_below_the_boot_count():
    rec = fx.base_record()
    rec["chk"][0][1] = 1                              # ordinal 1 with boots = 1
    _refused(rec, "chk.ordinal")
    rec["proc"][1] = 2                                # second boot of the process: control
    ice.ice_check_record(rec)


def test_l2_a_throwing_check_is_not_run_and_never_lists_a_plug_in():
    rec = fx.base_record()
    rec["chk"][1] = [1, 0, 90000, icm.ICM_CODES["not_run"], 1, 0, 0]
    _refused(rec, "chk.outcome")                      # a not_run that lists a plug-in
    rec["chk"][1] = [1, 0, 90000, icm.ICM_CODES["finding"], 0, 0, 0]
    _refused(rec, "chk.outcome")                      # a finding that lists none
    rec["chk"][1] = [1, 0, 90000, icm.ICM_CODES["finding"], 1, 0, 1]
    _refused(rec, "plug")                             # a finding with no name sent
    rec["plug"] = ["OtherPlugin"]
    rec["proc"][3] = 1
    ice.ice_check_record(rec)                         # control: the finding, named


def test_l4_an_incomplete_survey_carries_its_state_and_no_list():
    for state in (icm.ICM_CODES["read_failed"], icm.ICM_CODES["not_yet"],
                  icm.ICM_CODES["no_file"]):
        rec = fx.base_record()
        rec["ldir"]["plugins"][0] = state
        _refused(rec, "ldir.plugins")
        rec["ldir"]["plugins"] = [state, 0, 0, []]
        ice.ice_check_record(rec)
    rec = fx.base_record()
    rec["ldir"]["patchers"] = [0, 0, 0, [["X.dll", "e" * 64]]]
    _refused(rec, "ldir.patchers")                    # more entries than files
    rec = fx.base_record(aload=[2, "c" * 32, icm.ICM_CODES["read_failed"], "c" * 32])
    _refused(rec, "aload")
    rec = fx.base_record(gdig=[[0, "", 0, 1]])
    _refused(rec, "gdig")
    rec = fx.base_record(gdig=[[0, "a" * 64, 0, 1], [0, "b" * 64, 0, 1]])
    _refused(rec, "gdig")


def test_the_remaining_cross_field_rules():
    _refused(fx.base_record(tdg=[100, 0, [90, 9]]), "tdg")
    _refused(fx.base_record(cad_b=[[1, 1, 1, 1, 0], [1, 1, 1, 1, 0]]), "cad_b")
    _refused(fx.base_record(gclk=[0, 0, 5]), "gclk")
    rec = fx.base_record()
    rec["pt_o"][1][0] = rec["pt_o"][0][0]
    _refused(rec, "pt_o")
    rec = fx.base_record()
    rec["pt_o"][0][3] = [5]
    _refused(rec, "pt_o.tgt")
    _refused(fx.base_record(proc=[fx.PROC_A, 1, 1, 1, 1]), "proc.counts")
    _refused(fx.base_record(asm_n=[1, 2, 0, 0]), "asm_n")


# -- the envelope and the signature ---------------------------------------------------

def test_the_envelope_answers_like_the_seat_lane_with_its_own_bound():
    body = fx.envelope(fx.base_record())
    env = ice.ice_parse_envelope(body)
    assert ice.ice_verify_sig(fx.KEY, env)
    for bad, code, field in (
            (dict(body, contract=1), 400, "contract"),
            ({k: v for k, v in body.items() if k != "sig"}, 400, "envelope_keys"),
            (dict(body, other_steam_id=body["seat_steam_id"]), 400, "steam_ids"),
            (dict(body, record="x" * (W["record_max_bytes"] + 1)), 413, "record_bytes"),
            (dict(body, record="é"), 422, "record_ascii")):
        with pytest.raises(se.EvidenceRefused) as e:
            ice.ice_parse_envelope(bad)
        assert (e.value.status, e.value.field) == (code, field)
    at_cap = dict(body, record="x" * W["record_max_bytes"])
    assert ice.ice_parse_envelope(at_cap)["record_bytes"] == b"x" * W["record_max_bytes"]


def test_the_signature_has_its_own_prefix_and_never_crosses_lanes():
    body = fx.envelope(fx.base_record())
    env = ice.ice_parse_envelope(body)
    assert ice.ice_canonical(env).startswith(ice.SIGN_PREFIX)
    assert not ice.ice_verify_sig("", env)
    assert not ice.ice_verify_sig(fx.KEY + "x", env)
    # the seat lane's signature over the same bytes does not verify here
    seat_sig = se.record_sign(fx.KEY, env)
    assert not ice.ice_verify_sig(fx.KEY, dict(env, sig=seat_sig))
    flipped = dict(env, record_bytes=env["record_bytes"].replace(b'"consts":1', b'"consts":2'))
    assert not ice.ice_verify_sig(fx.KEY, flipped)


# -- the clock header (L9) -----------------------------------------------------------

def test_l9_the_clock_header_states():
    rec = fx.base_record()
    ok = ice.ice_parse_clock(fx.clock(), rec)
    assert ok == {"state": "ok", "proc": fx.PROC_A, "sw": 5_000_000, "unity": 4_000_000,
                  "photon": 123_456}
    assert ice.ice_parse_clock(None, rec)["state"] == "absent"
    assert ice.ice_parse_clock("", rec)["state"] == "absent"
    for bad in ("x", fx.clock().upper(), fx.clock() + "." * 64, fx.clock(photon=2 ** 31),
                "%s.%d.1.1" % (fx.PROC_A, 10 ** 13), fx.PROC_A + ".1.1"):
        st = ice.ice_parse_clock(bad, rec)
        assert st["state"] == "malformed" and st["sw"] is None, bad
    other = ice.ice_parse_clock(fx.clock(proc=fx.PROC_B), rec)
    assert other == {"state": "other_proc", "proc": None, "sw": None, "unity": None,
                     "photon": None}
    assert ice.ice_parse_clock(fx.clock(photon=-(2 ** 31)), rec)["state"] == "ok"


# -- the budgeter (S6, L11) ------------------------------------------------------------

def test_l11_the_point_cap_holds_the_legal_ranked_maximum():
    """Nine rounds at most (best of 5 rounds to win) and at most three point
    starts per round (two points to win a round: a round ends 2-0 or 2-1)."""
    rounds, starts_per_round = 2 * 5 - 1, 2 * 2 - 1
    assert W["pt_max"] >= rounds * starts_per_round


def test_s6_byte_proof_every_protected_list_full_at_maximum_width_fits():
    rec = fx.max_protected_record()
    rec["omit"] = {k: W["count_max"] for k in ice.IC_TRIM}     # widest omit counts too
    rec["asm_n"] = [W["small_max"]] * 4
    text = ice.ice_budget_record(rec)
    assert len(text) <= W["record_max_bytes"]
    out = json.loads(text)
    for k in ("pt_s", "pt_o", "gdig", "chk", "cost", "plug"):
        assert out[k] == rec[k], k
    assert out["asm_n"] == rec["asm_n"]


def test_s6_the_over_cap_record_keeps_the_protected_lists_and_counts_every_cut():
    rec = fx.over_cap_record()
    text = ice.ice_budget_record(rec)
    assert len(text) <= W["record_max_bytes"]
    out = json.loads(text)
    ice.ice_check_record(out)
    for k in ("pt_s", "pt_o", "gdig", "chk", "asm_n", "cost", "plug", "hp_all", "aload"):
        assert out[k] == rec[k], k
    assert sum(out["omit"].values()) > 0
    for k in ("asm", "cad_b", "rpc_o", "hp"):
        assert len(out[k]) + out["omit"][k] == len(rec[k]), k
    kept = sum(len(out["ldir"][p][3]) for p in ice.IC_LDIR_PARTS)
    assert kept + out["omit"]["ldir"] == sum(len(rec["ldir"][p][3]) for p in ice.IC_LDIR_PARTS)
    assert ice.ice_budget_record(rec) == text                  # deterministic


def test_s6_the_budgeter_trims_the_longest_list_first_and_never_a_protected_one():
    rec = fx.base_record()
    rec["asm"] = [["A%d" % i, "1", 0] for i in range(30)]
    rec["asm_n"] = [30, 0, 0, 0]
    rec["rpc_o"] = [["R%d" % i, 1] for i in range(10)]
    full = len(ice.ice_budget_record(rec, limit=10 ** 6))
    out = json.loads(ice.ice_budget_record(rec, limit=full - 40))
    assert len(out["asm"]) < 30 and len(out["rpc_o"]) == 10
    assert out["omit"]["asm"] == 30 - len(out["asm"])
    with pytest.raises(ValueError):
        ice.ice_budget_record(fx.base_record(pt_s=[fx.pt_s(i, i) for i in range(W["pt_max"] + 1)]))
    with pytest.raises(ValueError):
        ice.ice_budget_record(fx.max_protected_record(), limit=1000)


def test_s6_ldir_trims_the_longer_part_plugins_on_a_tie():
    rec = fx.base_record()
    rec["ldir"] = {"plugins": [0, 3, 0, [["P%d" % i, "e" * 64] for i in range(3)]],
                   "patchers": [0, 3, 0, [["Q%d" % i, "e" * 64] for i in range(3)]]}
    full = len(ice.ice_budget_record(rec, limit=10 ** 6))
    out = json.loads(ice.ice_budget_record(rec, limit=full - 10))
    assert len(out["ldir"]["plugins"][3]) == 2 and len(out["ldir"]["patchers"][3]) == 3


# -- canonical fixtures the client reproduces --------------------------------------------

FIXDIR = os.path.join(HERE, "fixtures", "identity_clock")


@pytest.mark.parametrize("name,maker", [("base", fx.base_record),
                                        ("over_cap", fx.over_cap_record)])
def test_the_canonical_fixtures_are_reproduced_byte_for_byte(name, maker):
    """input.json -> record.txt is the budgeter's exact output, and envelope.json
    carries the signature over it with the fixture key; the client half
    reproduces both."""
    d = os.path.join(FIXDIR, name)
    with open(os.path.join(d, "input.json"), encoding="ascii") as f:
        assert json.load(f) == json.loads(json.dumps(maker()))
    with open(os.path.join(d, "record.txt"), encoding="ascii", newline="") as f:
        want = f.read()
    assert ice.ice_budget_record(maker()) == want
    with open(os.path.join(d, "envelope.json"), encoding="ascii") as f:
        assert json.load(f) == fx.envelope(maker())
    with open(os.path.join(FIXDIR, "clock_headers.json"), encoding="ascii") as f:
        cases = json.load(f)
    for case in cases:
        assert ice.ice_parse_clock(case["header"], fx.base_record())["state"] == case["state"]


# -- the measures --------------------------------------------------------------------

BUILD = ("1.41.0", "STANDALONE", "abcdef123456", "e" * 64)


def _view(seat="A", other="B", rec=None, **over):
    v = {"seat": seat, "other": other, "rec": rec or fx.base_record(), "header_version": "1.41.0",
         "conflict": False, "conn_class": "none", "conn_ranges": "absent", "post_clock": "ok",
         "seat_build": list(BUILD), "relayed_build": "1.41.0|STANDALONE|abcdef123456",
         "fit": None, "fit_rows": 0}
    v.update(over)
    return v


def _regs(release=None, game_files=()):
    return {"release": {BUILD: "release"} if release is None else release,
            "game_files": set(game_files)}


def _m(name, ctx, params=None):
    entry = rr.rm.REGISTRY[name]
    return entry.impl[0](ctx, (params or {}).get(entry.family) if entry.family else None)


def _seat_ctx(view, regs=None, other=None):
    return icm.IcCtx(("seat", 0), r=view, other=other, regs=regs or _regs(), seat=0)


def test_q1_the_stated_build_against_the_registered_set_and_its_source():
    c = _seat_ctx(_view())
    assert _m("ic.seat.build_registered", c) is True
    assert _m("ic.seat.build_source", c) == "release"
    c = _seat_ctx(_view(), _regs({BUILD: "beta"}))
    assert _m("ic.seat.build_source", c) == "beta"
    c = _seat_ctx(_view(), _regs({}))
    assert _m("ic.seat.build_registered", c) is False and _m("ic.seat.build_source", c) is None
    c = _seat_ctx(_view(seat_build=None))
    assert _m("ic.seat.build_registered", c) is None


def test_c2_header_stated_and_relayed_agreement_each_unknown_without_both():
    assert _m("ic.seat.build_header_match", _seat_ctx(_view())) is True
    assert _m("ic.seat.build_header_match", _seat_ctx(_view(header_version="1.40.0"))) is False
    assert _m("ic.seat.build_header_match", _seat_ctx(_view(header_version=None))) is None
    assert _m("ic.seat.build_relayed_match", _seat_ctx(_view())) is True
    assert _m("ic.seat.build_relayed_match",
              _seat_ctx(_view(relayed_build="1.41.0|STANDALONE|000000000000"))) is False
    assert _m("ic.seat.build_relayed_match", _seat_ctx(_view(relayed_build=None))) is None


def test_l2_not_run_is_counted_and_no_measure_reads_it_as_a_pass():
    rec = fx.base_record()
    for e in rec["chk"]:
        e[3] = icm.ICM_CODES["not_run"]
    rec["proc"] = [fx.PROC_A, 1, 3, 0, 3]
    c = _seat_ctx(_view(rec=rec))
    assert _m("ic.seat.chk_not_run", c) == 3 and _m("ic.seat.chk_findings", c) == 0
    assert _m("ic.seat.proc_not_run_total", c) == 3
    # no public measure name or value states a pass
    assert not [n for n in rr.rm.REGISTRY if n.startswith("ic.") and "pass" in n]
    assert "caps" not in SRC["identity_clock_measures.py"]


def test_l4_survey_counts_are_unknown_unless_the_survey_completed():
    rec = fx.base_record()
    rec["ldir"]["plugins"] = [icm.ICM_CODES["read_failed"], 0, 0, []]
    c = _seat_ctx(_view(rec=rec))
    assert _m("ic.seat.ldir_plugins_files", c) is None
    assert _m("ic.seat.ldir_plugins_state", c) == icm.ICM_CODES["read_failed"]
    assert _m("ic.seat.ldir_patchers_files", c) == 0
    rec = fx.base_record(aload=[2, "c" * 32, icm.ICM_CODES["read_failed"], ""])
    assert _m("ic.seat.aload_mvid_differs", _seat_ctx(_view(rec=rec))) is None
    rec = fx.base_record(aload=[2, "c" * 32, 0, "f" * 32])
    assert _m("ic.seat.aload_mvid_differs", _seat_ctx(_view(rec=rec))) is True


def test_game_file_digests_against_the_registry():
    c = _seat_ctx(_view(), _regs(game_files=[(0, "a" * 64)]))
    assert _m("ic.seat.gdig_unregistered", c) == 1
    c = _seat_ctx(_view(), _regs(game_files=[(0, "a" * 64), (1, "b" * 64)]))
    assert _m("ic.seat.gdig_unregistered", c) == 0


# -- the clock fit (C12) -----------------------------------------------------------------

def _samples(n=12, factor=1.0, step=60_000, photon0=2 ** 31 - 200_000):
    out = []
    for i in range(n):
        t = 1_700_000_000_000 + i * step
        sw = int(round(i * step * factor))
        ph = ((photon0 + i * step + 2 ** 31) % 2 ** 32) - 2 ** 31
        out.append((t, 10_000 + sw, 50_000 + i * step, ph))
    return out


def test_c12_a_scaled_stopwatch_moves_the_fit_by_its_factor():
    base = icm.icm_fit_all(_samples())
    assert abs(base["sw"][0]) < 1 and base["sw"][1] < 1
    scaled = icm.icm_fit_all(_samples(factor=1.0005))
    assert abs(scaled["sw"][0] - 500) < 1                  # +0.05 % = 500 ppm
    assert abs(scaled["unity"][0]) < 1                     # the other clocks did not move
    assert base["sw"][2] == 12 and base["sw"][3] == 11 * 60_000


def test_c12_the_photon_clock_is_unwrapped_and_too_few_points_have_no_fit():
    fit = icm.icm_fit_all(_samples())
    assert abs(fit["photon"][0]) < 1                       # crosses the int32 wrap
    assert icm.icm_fit_all(_samples(n=1)) == {"sw": None, "unity": None, "photon": None}
    assert icm.icm_fit([5, 5], [1, 2]) is None             # no span


def test_c12_the_fit_measures_are_gated_by_the_revisions_minimum():
    fit = icm.icm_fit_all(_samples(factor=1.0005))
    c = _seat_ctx(_view(fit=fit))
    small = {"params.ic_fit": {"min_points": 3, "min_span_ms": 1}}
    large = {"params.ic_fit": {"min_points": 99, "min_span_ms": 1}}
    assert abs(_m("ic.seat.fit_sw_ppm", c, small) - 500) < 1
    assert _m("ic.seat.fit_sw_ppm", c, large) is None
    assert _m("ic.seat.fit_sw_points", c) == 12
    assert _m("ic.seat.fit_sw_ppm", _seat_ctx(_view(fit=None)), small) is None


# -- points (L8, L10) -------------------------------------------------------------------

def _pair(a_rec=None, b_rec=None):
    return [_view("A", "B", a_rec or fx.base_record()),
            _view("B", "A", b_rec or fx.base_record(proc=fx.PROC_B))]


def _point_rows(records, regs=None):
    return icm.icm_subjects(records, regs or _regs())["ic.point"]


def test_l10_pair_measures_compare_age_plus_elapsed_with_the_other_seats_observation():
    rows = _point_rows(_pair())
    assert len(rows) == 6 and all(_m("ic.point.paired", r) for r in rows)
    p = {"params.ic_point": {"rung": 1}}
    r = rows[0]
    # seen in position at rung 1 (1000) against own age (40) + release (900)
    assert _m("ic.point.release_seen_minus_stated", r, p) == 1000 - (40 + 900)
    assert _m("ic.point.input_seen_minus_stated", r) == 1340 - (40 + 1300)
    assert _m("ic.point.shot_seen_minus_stated", r) == 1540 - (40 + 1500)
    assert _m("ic.point.release_seen_minus_stated", r, {"params.ic_point": {"rung": 3}}) is None


def test_l8_the_on_time_expectation_needs_a_published_frame_rate():
    a, b = fx.base_record(), fx.base_record(proc=fx.PROC_B)
    rows = _point_rows([_view("A", "B", a), _view("B", "A", b)])
    exp = _m("ic.point.inpos_expected", rows[0])
    frame = 1000 / 60
    assert abs(exp - (40 + max(400, 20 * frame) + 10 * frame)) < 1e-6
    for e in b["pt_o"]:
        e[-1] = -1                                         # no frame rate published
    rows = _point_rows([_view("A", "B", a), _view("B", "A", b)])
    assert _m("ic.point.inpos_expected", rows[0]) is None
    assert _m("ic.point.inpos_late", rows[0], {"params.ic_point": {"rung": 1}}) is None


def test_points_pair_by_stamp_and_an_ambiguous_stamp_never_pairs():
    b = fx.base_record(proc=fx.PROC_B)
    b["pt_o"][1][1] = b["pt_o"][0][1]                      # two observations at one stamp
    rows = _point_rows([_view("A", "B", fx.base_record()), _view("B", "A", b)])
    paired = [r for r in rows if r.seat == 0 and _m("ic.point.paired", r)]
    assert len(paired) == 1                                # stamp 0 ambiguous, stamp 1 unseen
    one_sided = _point_rows([_view("A", "B", fx.base_record())])
    kinds = sorted({r.i[0] for r in one_sided})
    assert kinds == ["about_other", "point"]
    assert all(not _m("ic.point.paired", r) for r in one_sided)


def test_the_view_counts_paired_points():
    view = icm.icm_pair_view(_pair(), _regs())
    assert view["paired"] == 6 and view["seats"] == 2


# -- the identity rule scope (Q5) --------------------------------------------------------

ID_BUILD, ID_CLASS, ID_PT = "r0000e001", "r0000e002", "r0000e003"


def identity_doc():
    doc = tk.synthetic_doc()
    doc["measure_params"]["params.ic_point"] = {"rung": 1}
    doc["rules"] += [
        {"id": ID_BUILD, "scope": "identity", "subject": "ic.seat", "effect": "flag",
         "post": False, "post_since": None,
         "when": {"not": {"op": "op.truth", "args": {"a": tk.M("ic.seat.build_registered")}}},
         "show": [["seat", "ic.seat.index"]], "line": "synthetic unregistered seat {seat}"},
        {"id": ID_CLASS, "scope": "identity", "subject": "ic.seat", "effect": "note",
         "post": False, "post_since": None,
         "when": {"op": "op.in_set", "args": {"a": tk.M("ic.seat.conn_class"),
                                              "set": ["hosting"]}},
         "show": [["seat", "ic.seat.index"]], "line": "synthetic class note seat {seat}"},
        {"id": ID_PT, "scope": "identity", "subject": "ic.point", "effect": "flag",
         "post": False, "post_since": None,
         "when": tk.cmp(tk.M("ic.point.release_seen_minus_stated"), "gt", tk.V(77)),
         "show": [["pt", "ic.point.index"], ["d", "ic.point.release_seen_minus_stated"]],
         "line": "synthetic point {pt} {d}"},
    ]
    return doc


def _jsonable(records):
    return json.loads(json.dumps(records))


def identity_cases():
    quiet = _jsonable(_pair())
    late = _pair()
    late[1]["rec"]["pt_o"][0][5] = [980, 1200, -1, -1]      # B saw A in position late
    hosted = _pair()
    hosted[0]["conn_class"] = "hosting"
    reg = {"release": [list(BUILD)], "game_files": []}
    return [{"identity": quiet, "registries": reg, "fire": []},
            {"identity": quiet, "registries": {"release": [], "game_files": []},
             "fire": [ID_BUILD]},
            {"identity": _jsonable(late), "registries": reg, "fire": [ID_PT]},
            {"identity": _jsonable(hosted), "registries": reg, "fire": [ID_CLASS]}]


def _identity_revision(tmp, cases=None, doc=None):
    store, rev = tk.build_revision(tmp, identity_doc() if doc is None else doc,
                                   tk.quiet_cases() + (identity_cases() if cases is None
                                                       else cases))
    return rr.load_dir(os.path.join(store, "rules-" + rev))


def test_q5_identity_rules_load_selftest_and_evaluate_through_the_bound_core(tmp_path):
    rs = _identity_revision(tmp_path)
    assert {r.id for r in rs.identity_rules} == {ID_BUILD, ID_CLASS, ID_PT}
    assert rr.IDENTITY_CORE in rs.core
    late = _pair()
    late[1]["rec"]["pt_o"][0][5] = [980, 1200, -1, -1]
    late[0]["conn_class"] = "hosting"
    findings, fired, errors = rs.evaluate_identity(late, rr._identity_regs(
        {"release": [list(BUILD)], "game_files": []}))
    assert errors == 0 and sorted(fired) == [ID_CLASS, ID_PT]
    (rule, det), = findings
    assert rule.id == ID_PT and det["items"] == [{"pt": 0, "d": 1200 - 940}]
    assert det["notes"] == ["synthetic class note seat 0"]


def test_q5_a_selftest_case_that_does_not_fire_as_listed_refuses_the_revision(tmp_path):
    cases = identity_cases()
    cases[2]["fire"] = []
    with pytest.raises(rr.Refused):
        _identity_revision(tmp_path, cases)


def test_q5_identity_cases_without_an_identity_rule_refuse(tmp_path):
    with pytest.raises(rr.Refused):
        _identity_revision(tmp_path, doc=tk.synthetic_doc())


def test_q5_an_identity_rule_with_a_foreign_subject_refuses(tmp_path):
    doc = identity_doc()
    doc["rules"][-1]["subject"] = "seat"
    with pytest.raises(rr.Refused):
        _identity_revision(tmp_path, doc=doc)


def test_q5_a_revision_without_identity_rules_binds_no_identity_core(tmp_path):
    store, rev = tk.build_revision(tmp_path)
    rs = rr.load_dir(os.path.join(store, "rules-" + rev))
    assert rr.IDENTITY_CORE not in rs.core
    assert rs.evaluate_identity(_pair(), _regs()) == ([], [], 0)


def test_q5_the_code_closure_names_the_identity_measures():
    assert "identity_clock_measures.py" in rr.CODE_REQUIRED


# -- static scans (S5, S3, Q3) -----------------------------------------------------------

def _fn_src(src, name):
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    return ast.get_source_segment(src, fn)


_WRITE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([a-z_]+)", re.I)


def _written(src):
    return set(_WRITE.findall(src))


def test_s5_the_route_writes_only_the_identity_table():
    route = _fn_src(SRC["main.py"], "submit_identity_clock_evidence")
    assert not _written(route) and "db.add" not in route
    assert _written(_fn_src(SRC["identity_clock_evidence.py"], "ice_store_record")) == {
        "identity_clock_evidence"}
    assert _written(_fn_src(SRC["identity_clock_evidence.py"], "ice_register_game_file")) == {
        "game_file_digests"}


def test_s5_the_worker_writes_only_its_tables_and_the_shared_findings():
    ev = SRC["identity_clock_evidence.py"]
    worker = _fn_src(ev, "ice_evaluate_one") + _fn_src(ev, "ice_games_pass")
    assert _written(worker) == {"identity_clock_games", "seat_evidence_findings"}
    # posting reuses the seat lane's single writer of flagged_matches
    assert "se.post_finding(" in worker and "se.upsert_finding(" in worker
    assert _written(_fn_src(ev, "ice_purge_pass")) == {"identity_clock_evidence",
                                                        "identity_clock_games"}


def test_s5_the_match_report_canonical_is_untouched():
    main = SRC["main.py"]
    assert main.count('f"{str(report.is_ranked).lower()}:{report.reported_by_steam_id}:"') == 1
    sub = _fn_src(main, "submit_match")
    assert "_ice" not in sub and "_conn_ranges" not in sub


def test_s3_q3_no_address_is_written_logged_or_fetched():
    route = _fn_src(SRC["main.py"], "submit_identity_clock_evidence")
    # the address reaches only the classifier, inline, never a name
    assert route.count("_rl_client_address(request)") == 1
    assert "_conn_ranges.classify_address(_rl_client_address(request))" in route
    assert "print(" not in route and "logger" not in route
    for name in ("identity_clock_evidence.py", "conn_ranges.py", "identity_clock_measures.py"):
        src = SRC[name]
        for mod in ("socket", "urllib", "requests", "httpx", "aiohttp", "http.client"):
            assert not re.search(r"^\s*(?:import|from)\s+%s\b" % re.escape(mod), src, re.M), (
                name, mod)
    assert "client_address" not in SRC["identity_clock_evidence.py"]
    assert "host" not in _fn_src(SRC["identity_clock_evidence.py"], "ice_store_record")


def test_q5_advisory_only_nothing_here_refuses_rates_or_voids():
    ev = SRC["identity_clock_evidence.py"]
    for word in ("auto_invalidated = true", "auto_invalidated=True", "UPDATE matches",
                 "UPDATE players", "DELETE FROM matches", "UPDATE ranked_series"):
        assert word not in ev, word
