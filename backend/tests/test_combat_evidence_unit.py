"""Combat evidence, server half: the wire layout and its one record bound (M3),
the budgeter and its exact byte proof (M6, A16, A25), the canonical fixture
set the client reproduces byte for byte, the cycle rebuild from the per-refill
stream (M5, A17, A24), the pair view and its display cases (Q1), measurement
version compatibility (M2), gate calls against emissions (M4, A22), the owner
gate's forced flag (K1, A18), contact keys (M10, A23), frame-bounded block
pairs (L1, A9, A10), the reload stat seam (L2, A19), ramp (L3, A20), the
reference integrator (M7, A7, A8), server-first compatibility (L5), the
statement scan (A15), the no-tunables guard over the combat modules (M9) and
a SYNTHETIC combat revision (A12 and A13 analogues without a database).

Every record and every rule here is synthetic and built inside the tests."""

import ast
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import types

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, HERE)

import combat_evidence as ce  # noqa: E402
import combat_evidence_fixtures as fx  # noqa: E402
import combat_measures as cm  # noqa: E402
import review_guard as guard  # noqa: E402
import review_measures as rm  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402
import seat_evidence as se  # noqa: E402

API = os.path.normpath(os.path.join(HERE, "..", "api"))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
A, B = fx.SEAT_A, fx.SEAT_B


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def _main():
    import main
    return main


def _owner_dir(view, owner=A):
    return next(d for d in view["directions"] if d["owner"] == owner)


# -- M3: one record bound, one place per side ------------------------------------------

def test_m3_the_route_parser_and_budgeter_read_the_one_bound():
    assert cm.RECORD_MAX_BYTES == cm.W["record_max_bytes"] == 16384
    assert ce.RECORD_MAX_BYTES is cm.RECORD_MAX_BYTES
    src = "\n".join(_read(API, m) for m in ("combat_measures.py", "combat_evidence.py"))
    assert len(re.findall(r"\b16384\b", src)) == 1
    main_src = inspect.getsource(_main().submit_combat_evidence)
    assert not re.search(r"\b1\d{4}\b", main_src)


def test_m3_the_envelope_takes_exactly_the_bound_and_refuses_one_byte_over():
    assert cm.RECORD_MAX_BYTES == ce.RECORD_MAX_BYTES == 16384      # the contract's bound
    rec = fx.empty_record()
    at = fx.envelope(rec, text=" " * cm.RECORD_MAX_BYTES)
    env = ce.parse_envelope(at)
    assert len(env["record_bytes"]) == cm.RECORD_MAX_BYTES
    over = fx.envelope(rec, text=" " * (cm.RECORD_MAX_BYTES + 1))
    with pytest.raises(ce.EvidenceRefused) as e:
        ce.parse_envelope(over)
    assert e.value.status == 413


def test_m3_a_budgeted_record_near_the_bound_parses_whole():
    owner, _meas = fx.over_cap_pair()
    text = cm.budget_record(owner)
    proof = cm.byte_proof()
    # removal is whole entries: the budgeter stops at most one removed protected
    # group (with its point) under the bound
    assert cm.RECORD_MAX_BYTES - proof["group_max"] - proof["point_max"] - 2 < len(text)
    assert len(text) <= cm.RECORD_MAX_BYTES
    env = ce.parse_envelope(fx.envelope(None, text=text))
    assert ce.parse_record(env) == json.loads(text)
    assert len(text) > se.RECORD_MAX_BYTES        # beyond the seat contract's own bound


@pytest.mark.parametrize("mutate,field", [
    (lambda r: r.update(consts=0), "consts"),
    (lambda r: r.update(schema=2), "schema"),
    (lambda r: r["tot_s"].__setitem__(0, True), "tot_s"),
    (lambda r: r.update(extra=1), "extra"),
    (lambda r: r.pop("omit"), "omit"),
    (lambda r: r["sh_s"][0][0].__setitem__(cm.HDR["n"], 3), "sh_s"),
    (lambda r: r["sh_s"][0][1].append(fx.own_shot(1, 1, 0, 0, 0)), "sh_s"),
    (lambda r: r["gun_s"].extend([fx.gun()] * 10), "gun_s"),
])
def test_the_layout_refuses_a_record_outside_it(mutate, field):
    owner, _m = fx.a24_pair()
    cm.check_record(owner)                           # the control is accepted
    mutate(owner)
    with pytest.raises(cm.Refusal) as e:
        cm.check_record(owner)
    assert e.value.field == field


def test_the_layout_refuses_a_reordered_key_set():
    owner, _m = fx.a24_pair()
    items = list(owner.items())
    items[2], items[3] = items[3], items[2]
    with pytest.raises(cm.Refusal) as e:
        cm.check_record(dict(items))
    assert e.value.field == "key_order"


def test_the_route_answers_422_naming_the_field_and_400_for_the_envelope():
    owner, _m = fx.a24_pair()
    bad = fx.clone(owner)
    bad["consts"] = 0
    env = ce.parse_envelope(fx.envelope(bad))
    with pytest.raises(ce.EvidenceRefused) as e:
        ce.parse_record(env)
    assert (e.value.status, e.value.field) == (422, "consts")
    env = ce.parse_envelope(fx.envelope(owner, text=cm.dumps(owner).replace("16667", "16667.0")))
    with pytest.raises(ce.EvidenceRefused) as e:
        ce.parse_record(env)
    assert (e.value.status, e.value.field) == (422, "record_number")
    body = fx.envelope(owner)
    body["contract"] = 2
    with pytest.raises(ce.EvidenceRefused) as e:
        ce.parse_envelope(body)
    assert (e.value.status, e.value.field) == (400, "contract")


def test_signing_is_its_own_canonical_and_needs_the_key():
    owner, _m = fx.a24_pair()
    body = fx.envelope(owner)
    env = ce.parse_envelope(body)
    assert ce.verify_sig(fx.KEY, env)
    assert not ce.verify_sig("another-key", env)
    assert not ce.verify_sig("", env)
    assert ce.record_canonical(env).startswith(cm.W["sign_prefix"])
    assert ce.record_canonical(env) != se.record_canonical(env)
    tampered = dict(body, record=body["record"].replace('"consts":1', '"consts":2'))
    assert not ce.verify_sig(fx.KEY, ce.parse_envelope(tampered))


# -- the budgeter, the byte proof and the canonical fixture set (M6, A16, A25) ----------

def test_a25_the_byte_proof_is_exact_for_the_widest_never_trimmed_part():
    proof = cm.byte_proof()
    widest = cm.max_width_record()
    cm.check_record(widest)
    assert len(cm.dumps(widest)) == proof["never_trimmed_max"] <= cm.RECORD_MAX_BYTES
    assert proof["protected_floor"] >= 1
    per = proof["group_max"] + proof["point_max"] + 2
    assert proof["never_trimmed_max"] + proof["protected_floor"] * per <= cm.RECORD_MAX_BYTES


def _kept_protected(out):
    prot = cm.protected(out)
    return sum(len(prot[gk]) for gk, _ck in cm.W["protect"])


def test_a25_a_record_far_over_the_bound_keeps_the_never_trimmed_part_and_the_floor():
    rec = fx.max_width_protected(n_groups=6)
    cm.check_record(rec)
    assert len(cm.dumps(rec)) > 2 * cm.RECORD_MAX_BYTES
    text = cm.budget_record(rec)
    out = json.loads(text)
    cm.check_record(out)
    assert len(text) <= cm.RECORD_MAX_BYTES
    for k, s in cm.W["spec"]:
        if s[0] not in ("list", "groups") or s[2] == 0:
            if k != "omit":
                assert out[k] == rec[k], k
    assert _kept_protected(out) >= cm.byte_proof()["protected_floor"]
    removed = sum(out["omit"][k] - rec["omit"][k] for k in cm.OMIT_KEYS)
    kept = len(out["sh_s"]) + len(out["sh_o"])
    assert removed == len(rec["sh_s"]) + len(rec["sh_o"]) - kept


def test_a16_a_game_over_the_bound_still_covers_the_whole_game():
    owner, meas = fx.over_cap_pair()
    for rec, side in ((owner, "s"), (meas, "o")):
        out = json.loads(cm.budget_record(rec))
        assert len(cm.dumps(out)) <= cm.RECORD_MAX_BYTES
        assert out["omit"]["sh_" + side] > 0
        assert out["tot_" + side] == rec["tot_" + side]
        assert out["tb_tot"] == rec["tb_tot"]
        assert out["b5_tot"] == rec["b5_tot"]
        assert out["cx_" + side] == rec["cx_" + side]
        assert out["tot_" + side][cm.TOT["cycles"]] == len(out["sh_" + side]) + out["omit"]["sh_" + side]
        assert cm.rebuild_faults(out, side) == []


def test_m6_twenty_five_qualifying_cycles_keep_twenty_four_in_full_totals_and_an_omitted_count():
    rec = fx.many_cycles(25)
    assert len(rec["cx_s"]) == 24 and rec["omit"]["cx_s"] == 1
    tot = rec["tot_s"]
    assert tot[cm.TOT["cx_n"]] == 25 and tot[cm.TOT["cycles"]] == 25
    assert tot[cm.TOT["cx_units"]] == 100 and tot[cm.TOT["cx_volleys"]] == 100
    out = json.loads(cm.budget_record(rec))
    assert out["cx_s"] == rec["cx_s"] and out["omit"]["cx_s"] == 1
    assert cm.rebuild_faults(out, "s") == []
    view = cm.pair_view(fx.records(out, None))
    d = _owner_dir(view)
    assert d["cx"]["self_omitted"] == 1 and len(d["cx"]["self"]) == 24
    assert d["totals"]["self"]["cx_n"] == 25


def test_m6_a_measure_that_needs_an_omitted_cycle_reads_not_run():
    owner, meas = fx.over_cap_pair()
    o = json.loads(cm.budget_record(owner))
    m = json.loads(cm.budget_record(meas))
    view = cm.pair_view(fx.records(o, m))
    d = _owner_dir(view)
    rows = d["cycles"]
    # one row per cycle a record still names (24 kept summaries); the 25th is
    # carried only by the totals and the omitted count
    assert len(rows) == 24 and len({r["s0"] for r in rows}) == 24
    assert d["cx"]["meas_omitted"] == 1 and d["totals"]["meas"]["cycles"] == 25
    trimmed = [r for r in rows if r["not_run"] == "trimmed"]
    assert trimmed, "an over-cap pair has cycles one record no longer lists"
    for r in trimmed:
        assert all(s["not_run"] == "trimmed" and s["d_ammo"] is None for s in r["shots"])
    ctx = cm.combat_subjects(view)["combat.shot"]
    values = [cm.m_shot_d_ammo(c, None) for c in ctx]
    assert None in values and 0 in values


def test_the_budgeter_takes_tier_one_then_two_then_three():
    owner, _m = fx.over_cap_pair()
    rec = fx.clone(owner)
    rec["rx_s"] = [[0, 1, 2, 3]] * 48
    rec["b5_r"] = [[0, 1, 0]] * 32
    out = json.loads(cm.budget_record(rec))
    assert out["rx_s"] == [] and out["omit"]["rx_s"] == 48
    assert out["b5_r"] == [] and out["omit"]["b5_r"] == 32
    small = fx.clone(fx.a24_pair()[0])
    small["rx_s"] = [[0, 1, 2, 3]] * 48
    limit = len(cm.dumps(small)) - 10
    out = json.loads(cm.budget_record(small, limit))
    assert len(out["rx_s"]) < 48 and out["sh_s"] == small["sh_s"]


def test_the_budgeter_is_deterministic_and_counts_every_removal():
    owner, _m = fx.over_cap_pair()
    a, b = cm.budget_record(owner), cm.budget_record(fx.clone(owner))
    assert a == b
    out = json.loads(a)
    for k in cm.LISTS:
        assert len(out[k]) + out["omit"][k] == len(owner[k]) + owner["omit"][k], k


def test_the_canonical_fixture_set_is_byte_identical_to_the_files_the_client_reproduces():
    files = fx.canonical_set()
    on_disk = sorted(os.listdir(fx.FIXTURE_DIR))
    assert on_disk == sorted(files)
    for name, data in files.items():
        with open(os.path.join(fx.FIXTURE_DIR, name), "rb") as f:
            assert f.read() == data, name
    for name in files:
        if name.endswith(".in.json"):
            with open(os.path.join(fx.FIXTURE_DIR, name), "rb") as f:
                rec = json.loads(f.read().decode("ascii"))
            with open(os.path.join(fx.FIXTURE_DIR, name[:-len(".in.json")] + ".out.txt"), "rb") as f:
                assert cm.budget_record(rec).encode("ascii") == f.read(), name


def test_the_canonical_comparison_sees_one_changed_byte(tmp_path):
    """L-6: a copy of the canonical directory passes the on-disk validator
    (negative control); the same copy with one changed byte in one file is
    rejected, naming exactly that file."""
    copy = tmp_path / "canon"
    shutil.copytree(fx.FIXTURE_DIR, str(copy))
    assert fx.validate_dir(str(copy)) == []
    name = "a24_owner.out.txt"
    data = (copy / name).read_bytes()
    changed = data.replace(b'"consts":1', b'"consts":2')
    assert changed != data
    (copy / name).write_bytes(changed)
    assert fx.validate_dir(str(copy)) == [name]
    # A file no budget re-check covers is rejected by the byte comparison alone.
    other = tmp_path / "canon_other"
    shutil.copytree(fx.FIXTURE_DIR, str(other))
    steer = (other / "steering.json").read_bytes()
    (other / "steering.json").write_bytes(steer.replace(b"{", b"{ ", 1))
    assert fx.validate_dir(str(other)) == ["steering.json"]
    assert fx.validate_dir(fx.FIXTURE_DIR) == []


# -- the cycle rebuild and the review's case (A17, A24, M5) ------------------------------

def test_a24_the_reviews_case_from_two_records_alone():
    owner, meas = fx.a24_pair()
    view = cm.pair_view(fx.records(owner, meas))
    d = _owner_dir(view)
    assert d["case"] == "both_agree"
    (row,) = d["cycles"]
    own, cp = row["self"], row["meas"]
    for acct in (own, cp):
        assert (acct["units"], acct["mag"], acct["regen"], acct["in_rl"], acct["tail"]) == (4, 3, 0, 1, 0)
        assert acct["gaps"][0] == 200 and acct["exh"] == 400 and acct["excess"] == 1
    assert own["why"] == fx.A24_WHY_OWN and cp["why"] == fx.A24_WHY_COPY
    assert [s["stamp"] for s in row["shots"]] == [10000, 10200, 10400, 10600]
    for s, a0, rl in zip(row["shots"], (3, 2, 1, 0), (0, 0, 0, 1)):
        assert s["self"]["ammo_before"] == s["meas"]["ammo_before"] == a0
        assert s["self"]["reloading"] == s["meas"]["reloading"] == rl
        assert s["d_ammo"] == s["d_reloading"] == s["d_counter"] == 0
    assert row["shots"][3]["self"]["fl"] & cm.FL["reloading"]
    assert not row["shots"][3]["self"]["fl"] & cm.FL["forced"]
    assert row["stat"]["self"]["mag"] == row["stat"]["meas"]["mag"] == 3
    assert row["stat"]["self"]["rexp"] == 1500 and not any(row["stat"]["diff"].values())
    assert row["time"]["self"]["game_real_pm"] == row["time"]["meas"]["game_real_pm"] == 850
    assert row["refill"]["differs"] is False
    assert d["self_label"] == "SELF-STATED" and d["meas_label"] == "OTHER-SEAT-MEASURED"


def test_a24_variant_regeneration_names_the_refill_kind_amount_and_lengths():
    owner, meas = fx.a24_pair("regen")
    view = cm.pair_view(fx.records(owner, meas))
    d = _owner_dir(view)
    assert d["case"] == "both_differ"
    (row,) = d["cycles"]
    assert row["self"]["regen"] == 1 and row["self"]["why"] == cm.WHY["short_gap"]
    assert row["meas"]["regen"] == 0 and row["meas"]["why"] == fx.A24_WHY_COPY
    (only,) = row["refill"]["owner_only"]
    assert only == {"before_shot": 3, "kind": cm.W["regen_kind"], "amt": 1, "st": 10550,
                    "gap_g": 150, "gap_s": 150, "gap_r": 160}
    assert row["refill"]["meas_only"] == [] and row["refill"]["differs"]
    fourth = row["shots"][3]
    assert (fourth["self"]["ammo_before"], fourth["self"]["reloading"]) == (1, 0)
    assert (fourth["d_ammo"], fourth["d_reloading"]) == (1, -1)


def test_a24_variant_a_trimmed_group_gives_not_run_never_a_pass():
    owner, meas = fx.a24_pair("trimmed")
    view = cm.pair_view(fx.records(owner, meas))
    d = _owner_dir(view)
    (row,) = d["cycles"]
    assert row["not_run"] == "trimmed" and row["meas"] is None
    assert all(s["not_run"] == "trimmed" and s["d_ammo"] is None for s in row["shots"])
    assert d["case"] == "not_run"
    assert d["cx"]["meas"][0]["why"] == fx.A24_WHY_COPY       # the summary is kept in full
    owner2, meas2 = fx.a24_pair("short")
    row2 = _owner_dir(cm.pair_view(fx.records(owner2, meas2)))["cycles"][0]
    assert row2["meas"]["not_run"] == "trimmed" and row2["meas"]["why"] is None
    assert [s["not_run"] for s in row2["shots"]] == [None, None, None, "trimmed"]


def test_a17_the_rebuild_equals_the_totals_and_sees_a_missing_shot():
    owner, meas = fx.a24_pair()
    assert cm.rebuild_faults(owner, "s") == [] and cm.rebuild_faults(meas, "o") == []
    lost = fx.clone(meas)
    lost["sh_o"][0][0][cm.HDR["n"]] = 3
    lost["sh_o"][0][1] = lost["sh_o"][0][1][:3]
    assert "units" in cm.rebuild_faults(lost, "o")
    dup = fx.clone(owner)
    dup["tot_s"][cm.TOT["emit"]] = 5
    assert cm.rebuild_faults(dup, "s") == ["emit"]
    gone = fx.clone(owner)
    gone["sh_s"] = []
    assert "cycles" in cm.rebuild_faults(gone, "s")


def _a6_pair(skip=False):
    """Magazine three. Control: three shots on both seats, every decrement
    taken. Skip arm: the owner skips its second decrement, so it fires a
    FOURTH shot the copy counts as over the magazine."""
    n = 4 if skip else 3
    owner, meas = fx.empty_record(), fx.empty_record()
    for r, side in ((owner, "s"), (meas, "o")):
        r["tb"] = [fx.point()]
        r["tb_tot"] = fx.tb_tot_of(r["tb"])
        r["gun_" + side] = [fx.gun()]
        r["sh_" + side] = [fx.cycle_group(fx.S0, fx.PID0, n, side=side, reload_after=False)]
    if skip:
        for e, a0 in zip(owner["sh_s"][0][1], (3, 3, 2, 1)):
            e[cm.SHOT["s"]["ammo_before"]] = a0
    return fx.finish(owner, "s"), fx.finish(meas, "o")


def test_a6_a_skipped_decrement_shows_reason_bit_one_and_a_non_zero_ammo_difference():
    owner, meas = _a6_pair()
    control = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    (crow,) = control["cycles"]
    assert crow["meas"]["why"] == 0 and crow["self"]["why"] == 0         # no bit
    assert [s["d_ammo"] for s in crow["shots"]] == [0, 0, 0]             # no difference
    assert control["case"] == "both_agree" and len(crow["shots"]) == 3
    skip, smeas = _a6_pair(skip=True)
    d = _owner_dir(cm.pair_view(fx.records(skip, smeas)))
    (row,) = d["cycles"]
    assert len(row["shots"]) == 4                                        # the extra shot
    assert row["meas"]["why"] & cm.WHY["over_mag"] == cm.WHY["over_mag"] == 1
    assert [s["d_ammo"] for s in row["shots"]] == [0, 1, 1, 1]
    assert d["case"] == "both_differ" and "shot" in d["differs_by"]


# -- Q1: the display cases --------------------------------------------------------------

def test_q1_the_five_display_cases():
    owner, meas = fx.a24_pair()
    only_meas = ce.q1_display(cm.pair_view(fx.records(None, meas)))
    only_owner = ce.q1_display(cm.pair_view(fx.records(owner, None)))
    agree = ce.q1_display(cm.pair_view(fx.records(owner, meas)))
    differ = ce.q1_display(cm.pair_view(fx.records(*fx.a24_pair("regen"))))
    trimmed = ce.q1_display(cm.pair_view(fx.records(*fx.a24_pair("trimmed"))))

    def gun(disp):
        return next(x for x in disp if x["owner"] == A)
    assert gun(only_meas)["case"] == "only_measuring"
    assert gun(only_meas)["self_label"] is None and gun(only_meas)["meas_label"] == cm.LABEL_MEAS
    assert gun(only_owner)["case"] == "only_owner"
    assert gun(only_owner)["self_label"] == cm.LABEL_SELF and gun(only_owner)["meas_label"] is None
    assert gun(only_owner)["not_run"].get("missing_record", 0) >= 1
    assert gun(agree)["case"] == "both_agree" and gun(agree)["not_run"] == {}
    assert gun(differ)["case"] == "both_differ"
    assert gun(trimmed)["case"] == "not_run" and gun(trimmed)["not_run"]["trimmed"] >= 4
    for disp in (only_meas, only_owner, agree, differ, trimmed):
        assert gun(disp)["case_text"] == cm.CASE_TEXT[gun(disp)["case"]]
    assert ce.q1_display(None) == [{"owner": None, "case": "not_run",
                                    "not_run": {"lists_purged": 1}}]


def test_q1_one_record_alone_never_shows_a_pair_measure():
    owner, meas = fx.a24_pair()
    view = cm.pair_view(fx.records(None, meas))
    d = _owner_dir(view)
    assert d["attacks"]["d_emit_msgs"] is None and d["attacks"]["not_run"] == "missing_record"
    for s in d["cycles"][0]["shots"]:
        assert s["d_ammo"] is None and s["not_run"] == "missing_record"
    assert all(st["diff"] is None and st["not_run"] == "missing_record" for st in d["stat"])


# -- M2: measurement version compatibility ----------------------------------------------

def test_m2_every_combat_measure_declares_its_version_dependence():
    entries = [e for e in rm.REGISTRY.values()
               if e.kind == "measure" and e.subject in rm.COMBAT_SUBJECTS]
    assert len(entries) >= 40
    for e in entries:
        assert isinstance(e.data, dict) and isinstance(e.data.get("consts"), bool), e.name
    assert {e.name for e in entries if e.data["consts"]} == {
        "b1.hist.compatible", "b1.hist.meas_volleys", "b1.hist.self_volleys", "b3.top.d_perp",
        "b2.shot.owner_gate_flags", "b2.shot.owner_since", "b1.react.err", "b3.tb.gap",
        "b3.tb.ang_to_me", "b3.hm.ratio_pm", "b3.top.d_along", "b3.top.ang", "rec.a1sum",
        "b3.tb.min_gap", "b3.hm.max_ratio_pm", "b3.hm.hist", "b3.bounce.meas_gap"}


def test_m2_a_mixed_version_pair_is_stored_but_every_cross_record_measure_is_not_run():
    owner, meas = fx.a24_pair("mixed")
    cm.check_record(meas)
    view = cm.pair_view(fx.records(owner, meas))
    d = _owner_dir(view)
    assert d["case"] == "not_run"
    (row,) = d["cycles"]
    assert row["not_run"] == "incompatible" and row["refill"] is None
    assert row["self"]["units"] == 4 and row["meas"]["units"] == 4   # each account stays shown
    assert all(s["d_ammo"] is None and s["not_run"] == "incompatible" for s in row["shots"])
    assert d["attacks"]["d_emit_msgs"] is None
    b1 = {r["subject"]: r for r in view["b1"]}
    assert b1[A]["not_run"] == "incompatible" and b1[A]["meas"] is None
    subs = cm.combat_subjects(view)
    assert [cm.m_aim_meas_volleys(c, None) for c in subs["combat.aim"]
            if c.row["subject"] == A] == [None]
    control = cm.pair_view(fx.records(*fx.a24_pair()))
    assert _owner_dir(control)["cycles"][0]["not_run"] is None


def test_m2_a_mixed_version_pair_with_no_cycles_is_not_run_never_agreed():
    view = cm.pair_view(fx.records(fx.empty_record(), fx.empty_record(2)))
    assert _owner_dir(view)["cycles"] == [] and _owner_dir(view)["case"] == "not_run"
    control = cm.pair_view(fx.records(fx.empty_record(), fx.empty_record()))
    assert _owner_dir(control)["case"] == "both_agree"


def test_m2_contributions_carry_the_contributing_records_version():
    owner, meas = fx.a24_pair("mixed")
    contrib = cm.contributions(fx.records(owner, meas))
    by = {(c["subject"], c["source"]): c["consts"] for c in contrib}
    assert by[(A, "self")] == 1 and by[(A, "meas")] == 2
    assert by[(B, "self")] == 2 and by[(B, "meas")] == 1


# -- M4 and K1: gate calls, emissions, the forced flag -----------------------------------

def _charged_pair():
    owner, meas = fx.empty_record(), fx.empty_record()
    for r in (owner, meas):
        r["tb"] = [fx.point()]
        r["tb_tot"] = fx.tb_tot_of(r["tb"])
    owner["gun_s"] = [fx.gun(mag=6)]
    meas["gun_o"] = [fx.gun(mag=6)]
    # one accepted gate call, two repeats: two emissions, two attack messages
    owner["sh_s"] = [[fx.hdr(5000, 40, 2, end=cm.END["point"], rl=(-1, -1, -1)),
                      [fx.own_shot(0, 0, 6, 0, 0, rep=0), fx.own_shot(1, 100, 5, 0, 100, rep=1)], []]]
    meas["sh_o"] = [[fx.hdr(5000, 40, 2, end=cm.END["point"], rl=(-1, -1, -1)),
                     [fx.copy_shot(0, 0, 6, 0, 0, am=20), fx.copy_shot(1, 100, 5, 0, 100, am=21)], []]]
    owner["tot_s"] = fx.tot(cycles=1, volleys=2, units=2, gate=1, emit=2)
    meas["tot_o"] = fx.tot(cycles=1, volleys=2, units=2, atk_msg=2)
    return owner, meas


def test_m4_a22_gate_calls_are_kept_apart_from_emissions_and_messages_pair_with_emissions():
    owner, meas = _charged_pair()
    cm.check_record(owner)
    cm.check_record(meas)
    assert cm.rebuild_faults(owner, "s") == [] and cm.rebuild_faults(meas, "o") == []
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    att = d["attacks"]
    assert (att["owner_gate"], att["owner_emit"], att["meas_msgs"], att["d_emit_msgs"]) == (1, 2, 2, 0)
    assert all(s["meas"]["am"] >= 0 for s in d["cycles"][0]["shots"] if s["meas"]["first_of_emission"])
    conflated = fx.clone(owner)
    conflated["tot_s"][cm.TOT["emit"]] = 1
    assert cm.rebuild_faults(conflated, "s") == ["emit"]


def test_k1_a18_the_owner_gate_bit_needs_a_non_forced_attack_while_reloading():
    owner, meas = fx.a24_pair()
    gated = cm.rebuild_side(owner, "s")[0]
    assert gated["why"] & cm.WHY["gate_reloading"]
    forced = fx.clone(owner)
    forced["sh_s"][0][1][3][7] |= cm.FL["forced"]
    assert not cm.rebuild_side(forced, "s")[0]["why"] & cm.WHY["gate_reloading"]
    copy = cm.rebuild_side(meas, "o")[0]
    assert not copy["why"] & cm.WHY["gate_reloading"] and copy["shots"][3]["reloading"] == 1
    subs = cm.combat_subjects(cm.pair_view(fx.records(owner, meas)))
    flags = [cm.m_shot_owner_flags(c, None) for c in subs["combat.shot"]]
    assert flags[3] & cm.FL["reloading"] and not flags[3] & cm.FL["forced"]


# -- M10, L1: contacts and blocks ------------------------------------------------------

def _contact_pair(victim_rows, shooter_rows):
    victim, shooter = fx.empty_record(), fx.empty_record()
    victim["b5_c"] = [fx.named_row("b5_c", pid=p, s_init=si, cord=c, tc=tc, since_c=40, own_since=-2)
                      for p, si, c, tc in victim_rows]
    shooter["b5_h"] = [fx.named_row("b5_h", path=0, stamp=st, pid=p, s_init=si, cord=c, ord=0,
                                    since_ms=30, pred_since=10)
                       for p, si, c, st in shooter_rows]
    return victim, shooter


def test_m10_a23_contacts_pair_by_init_identity_and_ordinal_even_when_reordered():
    victim, shooter = _contact_pair([(9, 100, 1, 2000), (9, 100, 0, 1500)],
                                    [(9, 100, 0, 1530), (9, 100, 1, 2040)])
    rows = cm.contacts(victim, shooter)
    assert [(r["cord"], r["contact_to_decision"], r["not_run"]) for r in rows] == \
        [(1, 40, None), (0, 30, None)]
    assert rows[0]["since_c"] == 40 and rows[0]["since_ms"] == 30
    assert rows[0]["own_since"] == -2                         # the wire's "no own window"


def test_l4_a23_the_victims_own_since_is_read_and_its_absence_is_none():
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [(9, 100, 0, 1530)])
    victim["b5_c"][0][cm.IX["b5_c"]["own_since"]] = 25
    view = cm.pair_view(fx.records(victim, shooter))
    (c,) = cm.combat_subjects(view)["combat.contact"]
    assert c.row["own_since"] == 25 and cm.m_contact_own_since(c, None) == 25
    victim["b5_c"][0][cm.IX["b5_c"]["own_since"]] = cm.W["own_since_none"]   # negative mutant
    (c,) = cm.combat_subjects(cm.pair_view(fx.records(victim, shooter)))["combat.contact"]
    assert cm.m_contact_own_since(c, None) is None


def test_m10_a_duplicated_or_gapped_contact_key_is_ambiguous_and_not_run():
    victim, shooter = _contact_pair([(9, 100, 0, 1500), (9, 100, 0, 1600)],
                                    [(9, 100, 0, 1530)])
    rows = cm.contacts(victim, shooter)
    assert [r["not_run"] for r in rows] == ["ambiguous", "ambiguous"]
    assert all(r["since_ms"] is None and r["since_c"] is None for r in rows)
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [(9, 100, 1, 1530)])
    assert cm.contacts(victim, shooter)[0]["not_run"] in ("ambiguous", "uncounted")
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [])
    assert cm.contacts(victim, shooter)[0]["not_run"] == "uncounted"     # no counter (M-8)
    shooter["omit"]["b5_h"] = 1
    assert cm.contacts(victim, shooter)[0]["not_run"] == "trimmed"


def _block_pair(open_s, open_c, fr_s=17, fr_o=16, o_pred=None):
    victim, shooter = fx.empty_record(), fx.empty_record()
    victim["b5_s"] = [fx.named_row("b5_s", tb=7000, kind=1, ord=0, press=open_s - 5, open=open_s,
                                   len=300, len_g=300, cd=1000, gap_prev=-1, fr=fr_s)]
    shooter["b5_o"] = [fx.named_row("b5_o", tb=7000, kind=1, ord=0, ta=60, open_c=open_c, started=1,
                                    len_c=300, len_cg=300, o_pred=open_s if o_pred is None else o_pred,
                                    cd_c=1000, gap_prev_s=-1, fr=fr_o)]
    return victim, shooter


def test_l1_a9_a_paired_block_carries_its_frame_bound():
    (row,) = cm.blocks(*_block_pair(7200, 7260, o_pred=7190))
    assert (row["d_open"], row["d_len"], row["d_pred"]) == (60, 0, 10)
    assert row["frame_bound"] == 33 and (row["d_pred_lo"], row["d_pred_hi"]) == (-23, 43)
    assert row["d_pred_lo"] <= 0 <= row["d_pred_hi"]          # one frame late is inside the bound


def test_l1_a10_a_delay_is_measured_against_its_control():
    """L-2: the injected delay lies inside the control-relative interval the
    two records' frame bounds give (each seat may see the open up to one of
    its frames late), never asserted as an exact difference; a zero delay
    lies outside the delayed interval and inside the control's own."""
    delay = 125
    (control,) = cm.blocks(*_block_pair(7200, 7260, fr_s=17, fr_o=16))
    for jitter, fr_s, fr_o in ((0, 17, 16), (14, 17, 16), (-9, 20, 12)):
        (delayed,) = cm.blocks(*_block_pair(7200, 7260 + delay + jitter, fr_s=fr_s, fr_o=fr_o))
        bound = control["frame_bound"] + delayed["frame_bound"]
        rel = delayed["d_open"] - control["d_open"]
        assert rel - bound <= delay <= rel + bound
        assert not rel - bound <= 0 <= rel + bound                       # negative control
    assert -control["frame_bound"] <= 0 <= control["frame_bound"]


# -- L2, L3: stat seam and ramp ------------------------------------------------------

def test_l2_a19_a_reload_card_on_one_seat_differs_in_rtm_and_rexp_only():
    owner, meas = fx.a24_pair()
    meas["gun_o"] = [fx.gun(rtm=1300, rexp=1950)]
    st = _owner_dir(cm.pair_view(fx.records(owner, meas)))["stat"][0]
    assert sorted(k for k, v in st["diff"].items() if v) == ["d_rexp", "d_rtm"]
    seam = fx.clone(meas)
    seam["gun_o"] = [fx.gun(rexp=1950)]
    st = _owner_dir(cm.pair_view(fx.records(owner, seam)))["stat"][0]
    assert sorted(k for k, v in st["diff"].items() if v) == ["d_rexp"]


def test_l3_a20_a_ramped_point_and_a_point_without_ramp():
    rec = fx.empty_record()
    rec["tb"] = [fx.point(0, ramp=180), fx.point(1, ramp=0, ps=60000)]
    rec["tb_tot"] = fx.tb_tot_of(rec["tb"])
    view = cm.pair_view(fx.records(rec, None))
    pts = {p["pt"]: p for p in view["points"][0]["rows"]}
    assert pts[0]["ramp"] == 180 and pts[1]["ramp"] == 0
    assert pts[1]["game_real_pm"] == pts[1]["base"] == 850
    subs = cm.combat_subjects(view)["combat.point"]
    assert sorted(cm.m_point_base(c, None) for c in subs) == [850, 850]
    m = _measure_fn
    assert sorted(m("tb.point.ramp")(c, None) for c in subs) == [0, 180]


def _point_subjects(**over):
    rec = fx.empty_record()
    rec["tb"] = [fx.point(0, **over)]
    rec["tb_tot"] = fx.tb_tot_of(rec["tb"])
    (sub,) = cm.combat_subjects(cm.pair_view(fx.records(rec, None)))["combat.point"]
    return sub


def _measure_fn(name):
    return rm.REGISTRY[name].impl[0]


def test_m4_slow_slowed_reload_and_frame_clamp_each_against_its_control():
    m = _measure_fn
    control = _point_subjects()
    slow = _point_subjects(slow=9000, game=42000)
    assert m("tb.point.slow")(control, None) == 0 and m("tb.point.slow")(slow, None) == 9000
    assert m("tb.point.game_real")(slow, None) < m("tb.point.game_real")(control, None)
    clamp = _point_subjects(clamp=250, dt_max_us=50000)
    assert m("tb.point.clamp")(control, None) == 0 and m("tb.point.clamp")(clamp, None) == 250
    assert m("tb.point.dt_max_us")(clamp, None) == 50000 > m("tb.point.dt_max_us")(control, None)
    ramp = _point_subjects(ramp=180)
    assert m("tb.point.ramp")(ramp, None) == 180 and m("tb.point.ramp")(control, None) == 0
    # A reload slowed with the game: on the game clock it lasts its stated
    # length, on the real clock longer. Its control lasts the same on both.
    owner, meas = fx.a24_pair()
    slowed_o, slowed_m = fx.clone(owner), fx.clone(meas)
    for r, gk in ((slowed_o, "sh_s"), (slowed_m, "sh_o")):
        r[gk][0][0][cm.HDR["rl_r"]] = 2400
        r["tb"] = [fx.point(slow=9000, game=42000)]
        r["tb_tot"] = fx.tb_tot_of(r["tb"])
    for o, me, real in ((owner, meas, 1600), (slowed_o, slowed_m, 2400)):
        (ref,) = cm.combat_subjects(cm.pair_view(fx.records(o, me)))["combat.refill"]
        assert m("b2.refill.self_rl_g")(ref, None) == m("b2.refill.meas_rl_g")(ref, None) == 1500
        assert m("b2.refill.self_rl_r")(ref, None) == m("b2.refill.meas_rl_r")(ref, None) == real
        assert m("b2.refill.d_rl_r")(ref, None) == 0


def test_a21_a_timer_refill_carries_three_clocks_and_a_card_reload_ends_external():
    owner, meas = fx.a24_pair()
    row = _owner_dir(cm.pair_view(fx.records(owner, meas)))["cycles"][0]
    assert list(row["refill"]["end"]["rl_g"]) == [1500, 1500]
    assert list(row["refill"]["end"]["rl_s"]) == [1500, 1500]
    assert list(row["refill"]["end"]["rl_r"]) == [1600, 1600]
    assert row["clock"]["d_rl_s"] == 0 and not row["refill"]["differs"]
    shared = fx.clone(meas)                                   # negative mutant: the shared clock moves
    shared["sh_o"][0][0][cm.HDR["rl_s"]] = 1450
    srow = _owner_dir(cm.pair_view(fx.records(owner, shared)))["cycles"][0]
    assert list(srow["refill"]["end"]["rl_s"]) == [1500, 1450]
    assert srow["clock"]["d_rl_s"] == 50 and "clock" in srow["differs_by"]
    (ref,) = cm.combat_subjects(cm.pair_view(fx.records(owner, shared)))["combat.refill"]
    assert _measure_fn("b2.refill.meas_rl_s")(ref, None) == 1450
    ext = fx.clone(owner)
    ext["sh_s"][0][0][cm.HDR["end"]] = cm.END["external"]
    ext["cx_s"][0][cm.CX["end"]] = cm.END["external"]
    ext["cx_s"][0][cm.CX["why"]] &= ~cm.WHY["short_gap"]
    ext["tot_s"][cm.TOT["why_short_gap"]] = 0
    c = cm.rebuild_side(ext, "s")[0]
    assert c["end"] == cm.END["external"] and not c["why"] & cm.WHY["short_gap"]
    assert cm.rebuild_faults(ext, "s") == []


# -- M7: the reference integrator (A7, A8) ---------------------------------------------

def _f32_straight(state, frames):
    x, y = cm.f32(state["x"]), cm.f32(state["y"])
    vx, vy = cm.f32(state["vx"]), cm.f32(state["vy"])
    for dt in frames:
        d = cm.f32(cm.f32(dt) * cm.f32(1.0))
        x = cm.f32(x + cm.f32(cm.f32(vx * d) * cm.f32(1.0)))
        y = cm.f32(y + cm.f32(cm.f32(vy * d) * cm.f32(1.0)))
    return x, y


def test_m7_the_straight_case_equals_a_single_precision_hand_loop_and_not_double():
    name, state, frames, prm = fx.INTEGRATOR_CASES[0]
    out = cm.integrate(state, frames, prm)
    assert (out["x"], out["y"]) == _f32_straight(state, frames)
    x64 = state["x"] + sum(state["vx"] * dt for dt in frames)
    assert out["x"] != x64


def test_m7_the_pinned_integrator_set_and_the_turn_mutant_against_its_control():
    pinned = json.loads(_read(fx.FIXTURE_DIR, "integrator.json"))
    for case, (name, state, frames, prm) in zip(pinned, fx.INTEGRATOR_CASES):
        assert case["name"] == name
        pred = cm.integrate(state, frames, prm)
        assert {k: float.hex(v) for k, v in pred.items()} == case["pred"]
        control = cm.residual(pred, cm.trace(state, frames, prm))
        mutant = cm.residual(pred, cm.trace(state, frames, prm, fx.TURN_PER_FRAME))
        assert control == {"d_perp": 0, "d_along": 0, "ang": 0} == case["control_residual"]
        assert mutant == case["mutant_residual"]
        assert mutant["ang"] > 0 and mutant["d_perp"] > 0


def test_m7_a8_the_turned_bullets_entry_keeps_mask_zero_and_shows_the_residual():
    name, state, frames, prm = fx.INTEGRATOR_CASES[1]
    pred = cm.integrate(state, frames, prm)
    res = cm.residual(pred, cm.trace(state, frames, prm, fx.TURN_PER_FRAME))
    rec = fx.empty_record()
    rec["p3top"] = [fx.named_row("p3top", pid=3, s_rel=0, d_perp=res["d_perp"],
                                 d_along=res["d_along"], ang=res["ang"], dt=117, speed=8000, mask=0)]
    view = cm.pair_view(fx.records(None, rec))
    (top,) = cm.combat_subjects(view)["combat.top"]
    assert cm.m_top_mask(top, None) == 0 and cm.m_top_d_perp(top, None) == res["d_perp"] > 0


def test_m7_the_residual_rounds_half_to_even():
    assert cm.residual({"x": 0.0, "y": 0.0, "vx": 1.0, "vy": 0.0},
                       {"x": 0.0, "y": 0.025, "vx": 1.0, "vy": 0.0})["d_perp"] == round(2.5)


# -- L5: server first ----------------------------------------------------------------

def _git(*args):
    return subprocess.run(["git", "-C", REPO, *args], check=True, capture_output=True).stdout.decode()


def _consts_at(rev):
    src = _git("show", "%s:backend/api/main.py" % rev)
    out = {}
    for name in ("LATEST_MOD_VERSION", "MIN_MOD_VERSION"):
        out[name] = re.search(r"^%s = \"([^\"]+)\"" % name, src, re.M).group(1)
    return out


def test_l5_the_advertised_version_and_the_floor_are_unchanged():
    main = _main()
    base = _git("merge-base", "HEAD", "main").strip()
    assert _consts_at(base) == {"LATEST_MOD_VERSION": main.LATEST_MOD_VERSION,
                                "MIN_MOD_VERSION": main.MIN_MOD_VERSION}


def _gate(main, path, sent):
    from starlette.requests import Request
    req = Request({"type": "http", "method": "POST", "path": path, "query_string": b"",
                   "headers": [(b"x-mod-version", sent.encode())]})
    passed = []

    async def call_next(r):
        passed.append(r.url.path)
        return "passed"
    import asyncio
    out = asyncio.new_event_loop().run_until_complete(main.version_gate(req, call_next))
    return out, passed


def test_l5_before_the_release_the_gate_passes_and_after_it_the_426_is_byte_identical(monkeypatch):
    main = _main()
    for path in ("/api/v1/matches/combat-evidence", "/api/v1/matches"):
        out, passed = _gate(main, path, main.LATEST_MOD_VERSION)
        assert out == "passed" and passed == [path]
    monkeypatch.setattr(main, "MIN_MOD_VERSION_EFFECTIVE", "1.41.0")
    combat, _p = _gate(main, "/api/v1/matches/combat-evidence", "1.40.3")
    match, _p = _gate(main, "/api/v1/matches", "1.40.3")
    assert combat.status_code == match.status_code == 426
    assert combat.body == match.body == json.dumps(
        {"error": "outdated", "required": "1.41.0", "current": "1.40.3"},
        separators=(",", ":")).encode()


# -- A15: the statement scan, the match path, the worker role, the health word ----------

_WRITE = re.compile(r"\b(?:INSERT\s+INTO|(?<!KEY )(?<!FOR )UPDATE|DELETE\s+FROM)\s+([a-z_]+)")


def _writes(fn_or_src):
    src = fn_or_src if isinstance(fn_or_src, str) else textwrap.dedent(inspect.getsource(fn_or_src))
    lits = " ".join(n.value for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.Constant) and isinstance(n.value, str))
    return set(_WRITE.findall(lits))


def test_a15_the_route_writes_only_combat_evidence_and_the_worker_only_its_tables_and_findings():
    main = _main()
    assert _writes(ce.store_record) == {"combat_evidence"}
    assert _writes(main.submit_combat_evidence) == set()
    worker = _writes(_read(API, "combat_evidence.py"))
    assert worker <= {"combat_evidence", "combat_games", "combat_contrib", "combat_player_daily",
                      "seat_evidence_findings"}, worker
    assert _writes(se.post_finding) == {"flagged_matches", "seat_evidence_findings"}
    assert _writes(_read(API, "combat_measures.py")) == set()


def test_a15_the_scan_sees_a_write_when_there_is_one():
    assert _writes('q = "UPDATE players SET gold = gold + 1"\n') == {"players"}


def test_a15_the_match_report_path_names_nothing_of_the_combat_lane():
    main = _main()
    for fn in (main.submit_match, main.submit_macro_evidence):
        src = inspect.getsource(fn)
        for word in ("_cev", "combat_evidence", "combat_measures"):
            assert word not in src, (fn.__name__, word)


def _lifespan_branches(source):
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if (isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                and node.test.id == "IS_REPLICA"):
            return (" ".join(ast.unparse(n) for n in node.body),
                    " ".join(ast.unparse(n) for n in node.orelse))
    raise AssertionError("lifespan has no IS_REPLICA branch")


def test_the_combat_pass_runs_on_the_primary_only_and_the_standby_says_so():
    main = _main()
    replica, primary = _lifespan_branches(inspect.getsource(main.lifespan))
    assert "[COMBAT] worker=standby-disabled" in replica
    assert "[COMBAT] worker=primary" in primary and "[COMBAT] worker=standby-disabled" not in primary
    loop = inspect.getsource(main.review_worker_loop)
    assert "_cev.games_pass(async_session, state)" in loop and "_cev.purge_pass" in loop
    assert "review_worker_loop" in primary and "review_worker_loop" not in replica


def test_the_health_word_is_derived_from_the_routes(monkeypatch):
    main = _main()
    assert main._combat_evidence_health_word() == 1
    kept = [r for r in main.app.router.routes
            if getattr(r, "endpoint", None) is not main.admin_combat_evidence]
    monkeypatch.setattr(main.app.router, "routes", kept)
    assert main._combat_evidence_health_word() == 0


def test_the_health_answer_carries_the_word_on_both_arms():
    main = _main()
    src = inspect.getsource(main.health_check)
    assert src.count("combat_evidence=_combat_evidence_health_word()") == 2
    import schemas
    assert schemas.HealthResponse.model_fields["combat_evidence"].is_required()


def test_both_routes_are_registered():
    main = _main()
    paths = {(getattr(r, "path", None), tuple(sorted(getattr(r, "methods", ()) or ())))
             for r in main.app.router.routes}
    assert ("/api/v1/matches/combat-evidence", ("POST",)) in paths
    assert ("/api/v1/admin/combat-evidence", ("GET",)) in paths


def test_the_route_decides_the_session_first():
    src = inspect.getsource(_main().submit_combat_evidence)
    body = src[src.index('"""', src.index('"""') + 3):]
    assert body.index("_strict_steam_session_ok") < body.index("combat_evidence_accept") \
        < body.index("parse_envelope") < body.index("verify_sig") < body.index("parse_record")


# -- M9: the no-tunables guard over the combat modules ---------------------------------

GUARD_MODULES = ("review_measures", "review_rules", "review_module", "review_module_runner",
                 "seat_evidence", "combat_measures", "combat_evidence")


def _guard_copy(tmp):
    dst = os.path.join(str(tmp), "backend", "api")
    os.makedirs(dst)
    for m in GUARD_MODULES:
        shutil.copy(os.path.join(API, m + ".py"), dst)
    return str(tmp), dst


def _guard_edit(dst, mod, old, new):
    p = os.path.join(dst, mod + ".py")
    s = _read(p)
    assert s.count(old) == 1, (mod, old)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(s.replace(old, new))


def test_m9_the_real_tree_is_clean_and_the_combat_modules_are_in_reach():
    findings, _n = guard.tree_mode(REPO)
    assert findings == []
    assert "combat_measures" in guard.JUDGING and "combat_evidence" in guard.ROOTED


GUARD_MUTANTS = [
    ("measure_number", "combat_measures", 'return _get(ctx, "excess")\n',
     'return _get(ctx, "excess") + 7\n', "number"),
    ("measure_text", "combat_measures", 'return _get(ctx, "units")\n',
     'return _get(ctx, "units") if "over 17" else None\n', "text"),
    ("wire_pin", "combat_measures", '"seat_hourly_cap": 40,', '"seat_hourly_cap": 41,', "pinned"),
    ("wire_added", "combat_measures", '"centi": 100,', '"centi": 100, "slack": 0,', "pinned"),
    ("rooted_number", "combat_evidence", "    rev = rs.rev if rs is not None else None\n",
     "    rev = rs.rev if rs is not None else None\n    _floor = 7\n", "number"),
    ("rooted_setting", "combat_evidence", 'if await setting(db, "combat_evidence_worker") != "1":',
     'if await setting(db, "combat_review_post") != "1":', "setting"),
    ("encoded", "combat_measures", 'return _get(ctx, "tail")\n',
     'return _get(ctx, "tail") + int("7")\n', "call"),
]


@pytest.mark.parametrize("name,mod,old,new,cls", GUARD_MUTANTS, ids=[m[0] for m in GUARD_MUTANTS])
def test_m9_the_guard_refuses_a_planted_value_in_the_combat_modules(tmp_path, name, mod, old, new, cls):
    repo, dst = _guard_copy(tmp_path)
    assert guard.tree_mode(repo)[0] == []                     # negative control: the copy is clean
    _guard_edit(dst, mod, old, new)
    classes = {c for _l, _line, c in guard.tree_mode(repo)[0]}
    assert cls in classes, (name, classes)


# -- a synthetic combat revision (bars 12, 13 without a database) ------------------------

ID_COMBAT = "r0000c001"


def combat_doc():
    """synthetic_doc plus one synthetic combat rule: a visibly arbitrary value
    over a public description, chosen only to exercise the machinery."""
    doc = tk.synthetic_doc()
    doc["rules"].append({
        "id": ID_COMBAT, "scope": "combat", "subject": "combat.cycle", "effect": "flag",
        "post": False, "post_since": None,
        "when": tk.cmp(tk.M("b2.cycle.rexp"), "gt", tk.V(777)),
        "show": [["units", "b2.cycle.units"], ["acct", "b2.cycle.account"]],
        "line": "synthetic combat {units} ({acct})"})
    return doc


def combat_cases():
    o, m = fx.a24_pair()
    return tk.quiet_cases() + [{"combat": fx.records(o, m), "fire": [ID_COMBAT]},
                               {"combat": fx.records(fx.empty_record(), None), "fire": []}]


def test_a12_a_synthetic_combat_revision_loads_binds_the_combat_core_and_fires_in_shadow(tmp_path):
    store, rev = tk.build_revision(tmp_path, combat_doc(), combat_cases(), name="combat")
    rs = rr.load_dir(os.path.join(store, "rules-" + rev))
    assert "core.combat" in rs.core and [r.id for r in rs.combat_rules] == [ID_COMBAT]
    findings, fired, errors = rs.evaluate_combat(fx.records(*fx.a24_pair()))
    assert fired == [ID_COMBAT] and errors == 0
    (rule, det), = findings
    assert rule.post is False
    assert sorted(det["items"], key=lambda i: i["acct"]) == [{"units": 4, "acct": "meas"},
                                                            {"units": 4, "acct": "self"}]


def test_a13_a_revision_without_combat_rules_binds_no_combat_core_and_evaluates_nothing(tmp_path):
    store, rev = tk.build_revision(tmp_path)
    rs = rr.load_dir(os.path.join(store, "rules-" + rev))
    assert "core.combat" not in rs.core and rs.combat_rules == []
    assert rs.evaluate_combat(fx.records(*fx.a24_pair())) == ([], [], 0)


def test_a_combat_selftest_that_does_not_fire_as_listed_refuses_the_revision(tmp_path):
    cases = tk.quiet_cases() + [{"combat": fx.records(*fx.a24_pair()), "fire": []}]
    with pytest.raises(rr.Refused):
        tk.build_revision(tmp_path, combat_doc(), cases, name="bad")


def test_combat_selftest_cases_without_a_combat_rule_refuse_the_revision(tmp_path):
    cases = tk.quiet_cases() + [{"combat": fx.records(*fx.a24_pair()), "fire": []}]
    with pytest.raises(rr.Refused):
        tk.build_revision(tmp_path, None, cases, name="nocombat")


def test_a_combat_rule_on_an_unknown_subject_is_refused(tmp_path):
    doc = combat_doc()
    doc["rules"][-1]["subject"] = "combat.unknown"
    with pytest.raises(rr.Refused):
        tk.build_revision(tmp_path, doc, combat_cases(), name="badsubject")


def test_the_combat_core_is_a_fingerprinted_vocabulary_entry():
    names = dict(rm.entry_manifest())
    assert "core.combat" in names
    for n in ("b2.cycle.units", "b2.shot.d_ammo", "b5.contact.since_ms", "b3.top.d_perp",
              "b1.hist.compatible", "tb.point.base"):
        assert n in names, n
    assert "combat_measures" in rm.FINGERPRINT_MODULES


# -- the addendum sections: R1 push, R2 owner velocity changes, R3 hit chain, R5 deaths --

def _r_view(variant="base"):
    victim, shooter = fx.r_sections_pair(variant)
    cm.check_record(victim)
    cm.check_record(shooter)
    return victim, shooter, cm.pair_view(fx.records(victim, shooter))


def _by(view, key, who, field="victim"):
    return next(x for x in view[key] if x[field] == str(who))


def test_r1_a_push_is_data_keyed_by_the_hit_and_set_beside_the_shooters_copy():
    victim, shooter, view = _r_view()
    assert cm.section_faults(victim) == [] and cm.section_faults(shooter) == []
    (row,) = _by(view, "pushes", A)["rows"]
    assert (row["pid"], row["s_init"], row["cord"]) == fx.HIT
    assert row["self"]["fx"] == -120000 and row["self"]["mass"] == 20000
    assert (row["self"]["vax"], row["self"]["pbx"], row["self"]["pax"]) == (-600, 150000, 149990)
    assert (row["d_fx"], row["d_vax"], row["not_run"]) == (0, 0, None)
    (_v, _s, more) = _r_view("pushed_more")
    assert _by(more, "pushes", A)["rows"][0]["d_fx"] == 30000


def test_r1_r3_a_room_without_the_capability_shows_not_collected_never_zero():
    _v, _s, view = _r_view("uncapped")
    (prow,) = _by(view, "pushes", A)["rows"]
    assert prow["not_run"] == "not_collected" and prow["d_fx"] is None
    (crow,) = _by(view, "chains", A)["rows"]
    assert crow["not_run"] == "not_collected" and crow["msg_transit"] is None
    owner, meas = fx.a24_pair()
    plain = cm.pair_view(fx.records(owner, meas))
    assert _by(plain, "pushes", A) == {"victim": A, "rows": [], "not_run": "not_collected"}
    assert _by(plain, "velocity", A, "owner")["not_run"] == "not_collected"


def test_r1_a_listed_entry_the_caps_say_was_not_collected_is_a_fault():
    victim, _s = fx.r_sections_pair()
    victim["caps"] = 0
    assert set(cm.section_faults(victim)) == {"caps_push_s", "caps_ch_s", "caps_bd_s"}
    victim, _s = fx.r_sections_pair()
    victim["r_tot"][cm.IX["r_tot"]["push_own"]] = 2
    assert cm.section_faults(victim) == ["push_s"]


def test_l10_an_omitted_count_with_the_capability_clear_is_a_caps_fault():
    victim, _s = fx.r_sections_pair()
    victim["caps"] = cm.W["caps"]["chain"] | cm.W["caps"]["death"]       # push not collected
    victim["push_s"] = []
    victim["r_tot"][cm.IX["r_tot"]["push_own"]] = 0
    assert cm.section_faults(victim) == []                               # negative control
    victim["omit"]["push_s"] = 2
    assert cm.section_faults(victim) == ["caps_push_s"]


def test_r2_owner_velocity_changes_with_causes_and_the_bounce_targets_candidates():
    _v, _s, view = _r_view()
    vel = _by(view, "velocity", B, "owner")
    assert vel["label"] == cm.LABEL_SELF and vel["not_run"] is None
    (chg,) = vel["changes"]
    assert chg["causes"] == ["surface", "retarget"] and chg["turn_mrad"] == 1571
    assert chg["old"] == [0, -8000] and chg["new"] == [-8000, 0]
    (b,) = vel["bounces"]
    assert (b["target"], b["d_self"], b["d_other"], b["nearer"]) == ("other", 900, 1400, "self")
    assert (b["los_self"], b["los_other"]) == (1, 1)
    assert b["meas"]["gap"] == 110 and b["meas"]["has_retarget"] == 1
    assert (b["meas"]["s_init"], b["meas"]["s_rel"], b["meas_not_run"]) == (fx.HIT[1], 4200, None)
    assert vel["meas_unpaired"] == []
    subs = cm.combat_subjects(view)
    assert [cm.m_bounce_target(c, None) for c in subs["combat.bounce"]] == ["other"]
    assert [cm.m_vchange_cause(c, None) for c in subs["combat.vchange"]] == [18]


def test_r3_the_hit_chain_from_decision_to_screen():
    _v, _s, view = _r_view()
    (row,) = _by(view, "chains", A)["rows"]
    assert (row["dec_to_msg"], row["msg_transit"], row["dmg_transit"]) == (1, 49, 49)
    assert (row["rcv_to_hp"], row["hp_to_frame"], row["decision_to_screen"]) == (18, 17, 85)
    assert row["hp_d"] == -25 and row["not_run"] is None


def test_r5_a_boundary_death_with_its_cause_edge_state_and_recent_hit_identities():
    _v, _s, view = _r_view()
    (row,) = _by(view, "deaths", A, "seat")["rows"]
    assert row["self"]["cause"] == cm.W["death_cause"]["out_of_bounds"]
    assert row["self"]["edge"] == cm.W["edge"]["left"]
    assert (row["self"]["px"], row["self"]["vx"]) == (-4000, -900)
    assert row["hits"] == [{"pid": 9, "s_init": 4100, "cord": 0, "age": 800, "push_listed": True,
                            "push_not_run": None}]
    assert (row["d_px"], row["d_vx"], row["not_run"]) == (-10, 0, None)
    subs = cm.combat_subjects(view)["combat.death"]
    assert [cm.m_death_hits(c, None) for c in subs] == [1]


def test_r_sections_under_mixed_versions_are_not_run():
    victim, shooter = fx.r_sections_pair()
    shooter["consts"] = 2
    view = cm.pair_view(fx.records(victim, shooter))
    assert _by(view, "pushes", A)["rows"][0]["not_run"] == "incompatible"
    assert _by(view, "chains", A)["rows"][0]["msg_transit"] is None
    assert _by(view, "deaths", A, "seat")["rows"][0]["d_px"] is None


# -- FIX PASS 1: the refill-event stream (M-2) ------------------------------------------

def _regen_both():
    """The regeneration case with BOTH seats listing the same one-unit
    regeneration before the fourth shot: every account agrees."""
    owner, meas = fx.a24_pair("regen")
    g = meas["sh_o"][0]
    g[0][cm.HDR["rg"]], g[0][cm.HDR["nrg"]] = 1, 1
    g[1][3] = fx.copy_shot(1, 200, 1, 0, 0)
    g[2] = [fx.regen(3, 1, fx.S0 + 550)]
    return owner, fx.finish(meas, "o")


def test_m2_the_regeneration_total_is_derived_from_the_event_stream():
    owner, meas = fx.a24_pair()
    assert cm.rebuild_faults(owner, "s") == []                           # negative control
    stated = fx.clone(owner)
    stated["sh_s"][0][0][cm.HDR["rg"]] = 999                             # aggregate, no events
    (c,) = cm.rebuild_side(stated, "s")
    assert c["regen"] == 0 and c["regen_stated"] == 999
    assert c["why"] & cm.WHY["over_mag"]                                 # nothing suppressed
    assert "regen_total" in cm.rebuild_faults(stated, "s")


def test_m2_events_compare_as_multisets_on_kind_amount_stamp_and_three_clocks():
    owner, meas = _regen_both()
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    assert d["case"] == "both_agree", d["differs_by"]                    # negative control
    (row,) = d["cycles"]
    assert row["refill"]["owner_only"] == [] == row["refill"]["meas_only"]
    clock_only = fx.clone(meas)                                          # one clock of one event
    clock_only["sh_o"][0][2][0][cm.REGEN["gap_r"]] = 170
    d = _owner_dir(cm.pair_view(fx.records(owner, clock_only)))
    (row,) = d["cycles"]
    assert [r["gap_r"] for r in row["refill"]["owner_only"]] == [160]
    assert [r["gap_r"] for r in row["refill"]["meas_only"]] == [170]
    assert d["case"] == "both_differ" and d["differs_by"] == ["refill"]
    stamp_only = fx.clone(meas)
    stamp_only["sh_o"][0][2][0][cm.REGEN["st"]] = fx.S0 + 560
    (row,) = _owner_dir(cm.pair_view(fx.records(owner, stamp_only)))["cycles"]
    assert row["refill"]["differs"] and len(row["refill"]["meas_only"]) == 1


def test_m2_a_duplicated_event_is_one_unmatched_listing():
    owner, meas = _regen_both()
    dup = fx.clone(owner)
    g = dup["sh_s"][0]
    g[2] = g[2] + [list(g[2][0])]
    g[0][cm.HDR["rg"]], g[0][cm.HDR["nrg"]] = 2, 2
    (row,) = _owner_dir(cm.pair_view(fx.records(dup, meas)))["cycles"]
    assert len(row["refill"]["owner_only"]) == 1 and row["refill"]["meas_only"] == []
    assert row["refill"]["differs"]


def test_m2_a_truncated_event_list_is_not_run_never_compared():
    owner, meas = _regen_both()
    cut = fx.clone(owner)
    cut["sh_s"][0][0][cm.HDR["nrg"]] = 2                                 # two counted, one listed
    cut["sh_s"][0][0][cm.HDR["rg"]] = 2
    (c,) = cm.rebuild_side(cut, "s")
    assert c["events_complete"] is False and c["regen"] is None and c["not_run"] == "trimmed"
    view = cm.pair_view(fx.records(cut, meas))
    (row,) = _owner_dir(view)["cycles"]
    assert row["refill"]["not_run"] == "trimmed"
    assert row["refill"]["owner_only"] is None and row["refill"]["meas_only"] is None
    (ref,) = cm.combat_subjects(view)["combat.refill"]
    assert cm.m_refill_owner_only(ref, None) is None
    assert "regen_total" not in cm.rebuild_faults(cut, "s")             # no total to check


# -- FIX PASS 1: Q1 derived from every comparable field (M-6) -----------------------------

def _set_hdr(rec, gk, field, value):
    rec[gk][0][0][cm.HDR[field]] = value


def _one_field(name):
    """(owner, meas, the classes the one changed field must raise)."""
    owner, meas = fx.a24_pair()
    m = fx.clone(meas)
    if name == "shot_ammo":
        m["sh_o"][0][1][1][cm.SHOT["o"]["ammo_before"]] = 5
        return owner, m, ["shot"]
    if name == "shot_counter":
        m["sh_o"][0][1][1][cm.SHOT["o"]["counter"]] = 230
        return owner, m, ["shot"]
    if name == "cycle_src":
        _set_hdr(m, "sh_o", "src", cm.W["src"]["card"])
        return owner, m, ["cycle", "refill"]
    if name == "clock_rl_r":
        _set_hdr(m, "sh_o", "rl_r", 1700)
        return owner, m, ["clock", "refill"]
    if name == "clock_st_end":
        _set_hdr(m, "sh_o", "st_end", fx.S0 + 1950)
        return owner, m, ["clock"]
    if name == "attacks":
        m["tot_o"][cm.TOT["atk_msg"]] = 5
        return owner, m, ["attacks"]
    if name == "totals":
        m["tot_o"][cm.TOT["inits_rl"]] = 2
        return owner, m, ["totals"]
    if name == "stat":
        m["gun_o"] = [fx.gun(spr=40)]
        return owner, m, ["stat"]
    if name == "refill_event":
        o2, m2 = _regen_both()
        m2 = fx.clone(m2)
        m2["sh_o"][0][2][0][cm.REGEN["gap_g"]] = 151
        return o2, m2, ["refill"]
    raise KeyError(name)


ONE_FIELD = ("shot_ammo", "shot_counter", "cycle_src", "clock_rl_r", "clock_st_end", "attacks",
             "totals", "stat", "refill_event")


@pytest.mark.parametrize("name", ONE_FIELD)
def test_m6_one_field_only_differences_each_make_the_case_differ(name):
    owner, meas, classes = _one_field(name)
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    assert d["case"] == "both_differ" and d["differs_by"] == classes, d["differs_by"]
    (sub,) = [c for c in cm.combat_subjects(cm.pair_view(fx.records(owner, meas)))["combat.direction"]
              if c.row["owner"] == A]
    assert cm.m_direction_differs_by(sub, None) == classes


def test_m6_the_controls_agree_and_the_clock_deltas_are_exposed():
    for owner, meas in (fx.a24_pair(), _regen_both()):
        d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
        assert d["case"] == "both_agree" and d["differs_by"] == []
        (row,) = d["cycles"]
        assert row["clock"] == {"d_rl_g": 0, "d_rl_s": 0, "d_rl_r": 0, "d_st_end": 0, "d_exh": 0,
                                "d_gaps": [0, None, None]}
    owner, meas, _c = _one_field("clock_rl_r")
    (row,) = _owner_dir(cm.pair_view(fx.records(owner, meas)))["cycles"]
    assert row["clock"]["d_rl_r"] == -100


def test_m6_a_stat_difference_without_cycles_is_seen_and_unavailable_inputs_stay_not_run():
    owner, meas = fx.empty_record(), fx.empty_record()
    owner["gun_s"], meas["gun_o"] = [fx.gun()], [fx.gun()]
    assert _owner_dir(cm.pair_view(fx.records(owner, meas)))["case"] == "both_agree"
    meas["gun_o"] = [fx.gun(cexp=310)]
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    assert d["cycles"] == [] and d["case"] == "both_differ" and d["differs_by"] == ["stat"]
    assert _owner_dir(cm.pair_view(fx.records(*fx.a24_pair("trimmed"))))["case"] == "not_run"
    mixed = _owner_dir(cm.pair_view(fx.records(*fx.a24_pair("mixed"))))
    assert mixed["case"] == "not_run" and mixed["totals"]["diff"] is None
    assert _owner_dir(cm.pair_view(fx.records(fx.a24_pair()[0], None)))["case"] == "only_owner"


# -- FIX PASS 2: every shared semantic, generated from the field lists (M-6) --------------

def _bump(spec_row, v):
    """One value of a wire field that differs from `v` and stays in range."""
    if spec_row[0] in ("rep", "am"):                                     # the emission marker flips
        return 0 if v == -1 else -1
    return v + 1 if v + 1 <= spec_row[2] else v - 1


def _header_class(field):
    """The class a one-field header difference must raise."""
    cyc = cm.CYCLE_HEADER[field]
    if cyc == "s0" or cyc in cm.CYCLE_STATED:
        return "cycle"
    if cyc in cm.CLOCKS or cyc == "st_end":
        return "clock"
    raise AssertionError("header field %s is compared by nothing" % field)


def _generated_one_field():
    """(side, part, field, expected class) for every wire field of a shot
    group on both accounts, from the layout's own field lists: each header
    field, each entry field of a listed shot, each refill event field."""
    out = []
    for side, gk in (("s", "sh_s"), ("o", "sh_o")):
        for row in cm.SPEC[gk][3]:
            out.append((side, 0, row, _header_class(row[0])))
        for row in cm.SPEC[gk][5]:
            if row[0] not in cm.SHOT_OWNER_ONLY:
                out.append((side, 1, row, "shot"))
        for row in cm.SPEC[gk][7]:
            out.append((side, 2, row, "refill"))
    return out


GENERATED = _generated_one_field()


def test_f2_m6_the_generated_list_covers_every_wire_field_of_a_shot_group():
    for gk, side in (("sh_s", "s"), ("sh_o", "o")):
        assert [r[0] for r in cm.SPEC[gk][3]] == list(cm.CYCLE_HEADER)
        entry = {r[0] for r in cm.SPEC[gk][5]}
        assert entry <= set(cm.SHOT_ENTRY) | set(cm.SHOT_OWNER_ONLY)
        assert set(cm.SHOT_COMPARED) <= {cm.SHOT_ENTRY[f] for f in entry if f in cm.SHOT_ENTRY}
        got = {(r[0]) for sd, part, r, _c in GENERATED if sd == side and part == 1}
        assert got == entry - set(cm.SHOT_OWNER_ONLY)
    assert not set(cm.SHOT_OWNER_ONLY) & {r[0] for r in cm.SPEC["sh_o"][5]}
    assert len(GENERATED) == sum(len(cm.SPEC[gk][3]) + len(cm.SPEC[gk][5]) + len(cm.SPEC[gk][7])
                                 for gk in ("sh_s", "sh_o")) - len(cm.SHOT_OWNER_ONLY)


@pytest.mark.parametrize("side,part,row,cls", GENERATED,
                         ids=["%s.%d.%s" % (g[0], g[1], g[2][0]) for g in GENERATED])
def test_f2_m6_every_one_field_difference_makes_the_case_differ(side, part, row, cls):
    owner, meas = _regen_both()
    rec, gk = (fx.clone(owner), "sh_s") if side == "s" else (fx.clone(meas), "sh_o")
    group = rec[gk][0]
    target = group[0] if part == 0 else group[part][0 if part == 2 else 1]
    i = [r[0] for r in cm.SPEC[gk][(3, 5, 7)[part]]].index(row[0])
    target[i] = _bump(row, target[i])
    pair = (rec, meas) if side == "s" else (owner, rec)
    d = _owner_dir(cm.pair_view(fx.records(*pair)))
    assert d["case"] == "both_differ" and cls in d["differs_by"], (row[0], d["case"], d["differs_by"])


@pytest.mark.parametrize("field", cm.SHOT_OWNER_ONLY)
def test_f2_m6_the_owner_only_gate_state_is_not_compared(field):
    owner, meas = _regen_both()
    rec = fx.clone(owner)
    row = next(r for r in cm.SPEC["sh_s"][5] if r[0] == field)
    e = rec["sh_s"][0][1][1]
    e[cm.SHOT["s"][field]] = _bump(row, e[cm.SHOT["s"][field]])
    assert _owner_dir(cm.pair_view(fx.records(owner, meas)))["case"] == "both_agree"   # control
    d = _owner_dir(cm.pair_view(fx.records(rec, meas)))
    assert "shot" not in d["differs_by"]


def test_f2_m6_first_of_emission_and_the_header_identity_are_exposed_per_row():
    owner, meas = _regen_both()
    m = fx.clone(meas)
    e = m["sh_o"][0][1][1]
    e[cm.SHOT["o"]["am"]] = _bump(("am",), e[cm.SHOT["o"]["am"]])
    (row,) = _owner_dir(cm.pair_view(fx.records(owner, m)))["cycles"]
    assert row["shots"][1]["d_first"] in (1, -1) and "shot" in row["differs_by"]
    assert row["shots"][0]["d_first"] == 0
    (row,) = _owner_dir(cm.pair_view(fx.records(owner, meas)))["cycles"]
    for acct in ("self", "meas"):
        assert {"s0", "pid0", "pt", "regen_stated"} <= set(row[acct])


def test_f2_m6_a_missing_cycle_partner_is_absent_or_not_run_never_agreement():
    owner, meas = fx.a24_pair()
    gone = fx.clone(meas)
    gone["sh_o"] = []
    gone["tot_o"][cm.TOT["cycles"]] = 0                                 # none listed, none counted
    d = _owner_dir(cm.pair_view(fx.records(owner, gone)))
    (row,) = [r for r in d["cycles"] if r["self"] is not None]
    assert row["absent_in"] == "meas" and "cycle" in row["differs_by"]
    assert d["case"] == "both_differ" and "cycle" in d["differs_by"]
    # Fix pass 3 (M-8): the record this control used before, no group listed
    # while its whole-game count says one, contradicts itself: NOT-RUN
    # `inconsistent`, never absent, never a difference, never an agreement.
    contra = fx.clone(meas)
    contra["sh_o"] = []
    d = _owner_dir(cm.pair_view(fx.records(owner, contra)))
    (row,) = [r for r in d["cycles"] if r["self"] is not None]
    assert row["not_run"] == "inconsistent" and row["absent_in"] is None
    assert row["differs_by"] == [] and d["case"] == "not_run", (d["case"], d["differs_by"])
    trimmed = fx.clone(contra)
    trimmed["omit"]["sh_o"] = 1
    d = _owner_dir(cm.pair_view(fx.records(owner, trimmed)))
    (row,) = [r for r in d["cycles"] if r["self"] is not None]
    assert row["not_run"] == "trimmed" and row["absent_in"] is None
    assert "cycle" not in row["differs_by"] and d["case"] != "both_agree"
    (sub,) = [c for c in cm.combat_subjects(cm.pair_view(fx.records(owner, gone)))["combat.cycle"]
              if c.row["owner"] == A]
    assert cm.m_cycle_partner_absent(sub, None) == "meas"
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))                # control: partnered
    assert d["case"] == "both_agree" and all(r["absent_in"] is None for r in d["cycles"])


# -- FIX PASS 1: target bounce pairing and R5 absence (M-8) -------------------------------

def _bounce_pair(meas_rows, own_stamps=(4200,), omit=0, target=None, bsel_count=None):
    victim, shooter = fx.r_sections_pair()
    tmpl = shooter["bsel"][0]
    shooter["bsel"] = []
    for st in own_stamps:
        e = list(tmpl)
        e[cm.IX["bsel"]["stamp"]] = st
        shooter["bsel"].append(e)
    shooter["r_tot"][cm.IX["r_tot"]["bsel"]] = (len(shooter["bsel"]) if bsel_count is None
                                                 else bsel_count)
    victim["p3tb"] = [fx.named_row("p3tb", pid=fx.HIT[0], s_init=si, s_rel=sr, gap=gap,
                                   has_retarget=1, ang_to_me=40) for si, sr, gap in meas_rows]
    victim["omit"]["p3tb"] = omit
    victim["p3n"][cm.IX["p3n"]["target"]] = len(meas_rows) + omit if target is None else target
    view = cm.pair_view(fx.records(victim, shooter))
    return _by(view, "velocity", B, "owner")


def test_m8_bounces_pair_on_the_whole_event_identity_even_reordered():
    vel = _bounce_pair([(fx.HIT[1], 4600, 120), (fx.HIT[1], 4200, 110)], own_stamps=(4200, 4600))
    assert [(b["stamp"], b["meas"]["gap"], b["meas_not_run"]) for b in vel["bounces"]] == [
        (4200, 110, None), (4600, 120, None)]
    pid_only = _bounce_pair([(fx.HIT[1] + 1, 4200, 110)])               # same pid, other event
    (b,) = pid_only["bounces"]
    assert b["meas"] is None and b["meas_not_run"] == "absent"
    assert [u["not_run"] for u in pid_only["meas_unpaired"]] == ["absent"]


def test_m8_a_duplicated_key_on_either_side_is_ambiguous_and_trimmed_is_named():
    dup = _bounce_pair([(fx.HIT[1], 4200, 110), (fx.HIT[1], 4200, 130)])
    (b,) = dup["bounces"]
    assert b["meas"] is None and b["meas_not_run"] == "ambiguous"
    own_dup = _bounce_pair([(fx.HIT[1], 4200, 110)], own_stamps=(4200, 4200))
    assert [b["meas_not_run"] for b in own_dup["bounces"]] == ["ambiguous", "ambiguous"]
    trimmed = _bounce_pair([], omit=1)
    assert trimmed["bounces"][0]["meas_not_run"] == "trimmed"
    absent = _bounce_pair([])
    assert absent["bounces"][0]["meas_not_run"] == "absent"
    (sub,) = cm.combat_subjects(cm.pair_view(fx.records(*fx.r_sections_pair())))["combat.bounce"]
    assert cm.m_bounce_meas_gap(sub, None) == 110


def _death_hits(**edit):
    victim, shooter = fx.r_sections_pair()
    if edit.get("drop_push"):
        victim["push_s"] = []
        victim["r_tot"][cm.IX["r_tot"]["push_own"]] = edit.get("count", edit.get("omit", 0))
        victim["omit"]["push_s"] = edit.get("omit", 0)
    if edit.get("no_push_cap"):
        victim["caps"] &= ~cm.W["caps"]["push"]
        victim["push_s"] = []
        victim["r_tot"][cm.IX["r_tot"]["push_own"]] = 0
    view = cm.pair_view(fx.records(victim, shooter))
    (row,) = _by(view, "deaths", A, "seat")["rows"]
    (sub,) = [c for c in cm.combat_subjects(view)["combat.death"] if c.row["seat"] == A]
    return row["hits"][0], cm.m_death_push_unlisted(sub, None)


def test_m8_r5_absence_only_when_the_retained_push_list_proves_it():
    assert _death_hits() == ({"pid": 9, "s_init": 4100, "cord": 0, "age": 800,
                              "push_listed": True, "push_not_run": None}, 0)
    hit, n = _death_hits(drop_push=True)                                 # whole list, entry absent
    assert (hit["push_listed"], hit["push_not_run"], n) == (False, None, 1)
    hit, n = _death_hits(drop_push=True, omit=1)                         # trimmed: unknown
    assert (hit["push_listed"], hit["push_not_run"], n) == (None, "trimmed", None)
    hit, n = _death_hits(no_push_cap=True)
    assert (hit["push_listed"], hit["push_not_run"], n) == (None, "not_collected", None)


# -- FIX PASS 2: absence only from a list whole against its whole-game counter (M-8) ------

def test_f2_m8_every_absence_list_has_a_whole_game_counter():
    """Generated (fix pass 3): every list the absence gate is asked about,
    read from the source's own calls of the gate, has a whole-game counter,
    or is one the layout gives none (`b5_o`, `b5_h`: always `uncounted`).
    The cycle lists the gate is asked about by variable are the two shot
    group lists, counted by each gun's whole-game `cycles` total."""
    sites, _violations = _gate_proof(_CM_SOURCE)
    keys = set()
    for _fn, args in sites:
        arg = ast.parse("f(%s)" % args, mode="eval").body.args[1]
        keys.add(arg.value if isinstance(arg, ast.Constant) else ("var", arg.id))
    named = {k for k in keys if isinstance(k, str)}
    assert named - set(cm.WHOLE_COUNTERS) == {"b5_o", "b5_h"}, sorted(named)
    assert {k for k in keys if not isinstance(k, str)} == {("var", "other_gk"), ("var", "own_gk")}
    assert cm.WHOLE_COUNTERS["sh_s"] == ("tot_s", "cycles", None)
    assert cm.WHOLE_COUNTERS["sh_o"] == ("tot_o", "cycles", None)
    for key, (row, field, _cap) in cm.WHOLE_COUNTERS.items():
        assert field in cm.IX[row], key
    assert not {"b5_o", "b5_h"} & set(cm.WHOLE_COUNTERS)                # the layout names none


def test_f2_m8_a_list_without_a_counter_never_proves_absence():
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [])
    assert cm.contacts(victim, shooter)[0]["not_run"] == "uncounted"
    shooter["omit"]["b5_h"] = 1
    assert cm.contacts(victim, shooter)[0]["not_run"] == "trimmed"
    victim, shooter = _block_pair(7010, 7030)
    assert cm.blocks(victim, shooter)[0]["not_run"] is None              # control: paired
    shooter["b5_o"] = []
    assert cm.blocks(victim, shooter)[0]["not_run"] == "uncounted"
    shooter["omit"]["b5_o"] = 1
    assert cm.blocks(victim, shooter)[0]["not_run"] == "trimmed"


@pytest.mark.parametrize("cap, key, field, measured", [
    ("push", "pushes", "victim", "d_fx"),
    ("chain", "chains", "victim", "msg_transit"),
    ("death", "deaths", "seat", "d_px")])
def test_f2_m8_a_list_under_a_cleared_capability_is_never_compared(cap, key, field, measured):
    """The other seat's list is read only when its capability says the list
    was collected: with the bit clear, an entry the list still holds for the
    same identity is NOT-RUN `not_collected` and nothing is measured."""
    victim, shooter = fx.r_sections_pair()
    (row,) = _by(cm.pair_view(fx.records(victim, shooter)), key, A, field)["rows"]
    assert row["not_run"] is None and row[measured] is not None          # control: compared
    shooter["caps"] &= ~cm.W["caps"][cap]
    (row,) = _by(cm.pair_view(fx.records(victim, shooter)), key, A, field)["rows"]
    assert row["not_run"] == "not_collected" and row[measured] is None


def test_f2_m8_p3tb_against_p3n_target():
    assert _bounce_pair([])["bounces"][0]["meas_not_run"] == "absent"   # control: 0 counted
    assert _bounce_pair([], target=1)["bounces"][0]["meas_not_run"] == "inconsistent"
    assert _bounce_pair([], omit=1, target=1)["bounces"][0]["meas_not_run"] == "trimmed"


def test_f2_m8_bsel_against_r_tot_bsel():
    other = [(fx.HIT[1] + 1, 4200, 110)]
    assert [u["not_run"] for u in _bounce_pair(other)["meas_unpaired"]] == ["absent"]   # control
    assert [u["not_run"] for u in _bounce_pair(other, bsel_count=2)["meas_unpaired"]] == [
        "inconsistent"]


def test_f2_m8_push_s_against_r_tot_push_own():
    hit, n = _death_hits(drop_push=True)                                 # control: 0 counted
    assert (hit["push_listed"], hit["push_not_run"], n) == (False, None, 1)
    hit, n = _death_hits(drop_push=True, count=1)                        # counted one, lists none
    assert (hit["push_listed"], hit["push_not_run"], n) == (None, "inconsistent", None)


@pytest.mark.parametrize("key,view_key,field,count", [
    ("push_o", "pushes", "victim", "push_other"),
    ("ch_o", "chains", "victim", "chain_other"),
    ("bd_o", "deaths", "seat", "death_other")])
def test_f2_m8_the_other_seats_lists_against_their_counters(key, view_key, field, count):
    victim, shooter = fx.r_sections_pair()
    shooter[key] = []
    shooter["r_tot"][cm.IX["r_tot"][count]] = 0
    (row,) = _by(cm.pair_view(fx.records(victim, shooter)), view_key, A, field)["rows"]
    assert row["not_run"] == "absent"                                    # control: 0 counted
    shooter["r_tot"][cm.IX["r_tot"][count]] = 1
    (row,) = _by(cm.pair_view(fx.records(victim, shooter)), view_key, A, field)["rows"]
    assert row["not_run"] == "inconsistent"


# -- FIX PASS 3: every absence through the one gate (M-8) ---------------------------------

_CM_SOURCE = open(cm.__file__, encoding="utf-8").read()


def _gate_proof(source):
    """(sites, violations) for the combat measures source. `sites`: every
    call of the absence gate, as (enclosing function, its arguments as
    written), generated from the source. `violations`: every absence the
    source produces that the gate does not decide -- the name ABSENT read
    anywhere but the gate's own return or a comparison against a gate
    result; the literal "absent" anywhere but the definition of ABSENT; an
    `absent_in` account or a `push_listed` False set anywhere but under a
    branch taken only when a gate result IS ABSENT; and `list_gap` (the
    gate's own input) called anywhere but in the gate."""
    tree = ast.parse(source)
    parent = {}
    for n in ast.walk(tree):
        for ch in ast.iter_child_nodes(n):
            parent[ch] = n

    def fn_of(n):
        while n in parent:
            n = parent[n]
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return n
        return None

    def is_gate_call(e):
        return isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and e.func.id == "absence"

    cache = {}

    def gate_names(fn):
        """Names whose every binding in `fn` is `name = absence(...)`."""
        if fn not in cache:
            good, bad = set(), set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Name) and not isinstance(n.ctx, ast.Load):
                    p = parent[n]
                    if isinstance(p, ast.Assign) and p.targets == [n] and is_gate_call(p.value):
                        good.add(n.id)
                    else:
                        bad.add(n.id)
            cache[fn] = good - bad
        return cache[fn]

    def polarity(test, fn):
        """The branch ("body"/"orelse") a gate comparison takes when the gate
        said ABSENT, or None when `test` is no such comparison."""
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1
                and isinstance(test.ops[0], (ast.Eq, ast.NotEq))):
            return None
        a, b = test.left, test.comparators[0]
        for x, y in ((a, b), (b, a)):
            gated = is_gate_call(y) or (isinstance(y, ast.Name) and fn is not None
                                        and y.id in gate_names(fn))
            if isinstance(x, ast.Name) and x.id == "ABSENT" and gated:
                return "body" if isinstance(test.ops[0], ast.Eq) else "orelse"
        return None

    def dominated(marker, fn):
        child, n = marker, parent.get(marker)
        while n is not None and n is not fn:
            if isinstance(n, (ast.If, ast.IfExp)):
                pol = polarity(n.test, fn)
                body = n.body if isinstance(n, ast.If) else [n.body]
                orelse = n.orelse if isinstance(n, ast.If) else [n.orelse]
                if pol == "body" and any(child is x for x in body):
                    return True
                if pol == "orelse" and any(child is x for x in orelse):
                    return True
            child, n = n, parent.get(n)
        return False

    def keyed(n):
        """(key, value) pairs a node writes: a subscript store (also inside
        a tuple or list target, paired by position when the value is a
        tuple or list of the same length, else with the whole value), a
        dict entry, a keyword argument."""
        if isinstance(n, ast.Assign):
            out = []
            for t in n.targets:
                pairs = [(t, n.value)]
                if isinstance(t, (ast.Tuple, ast.List)):
                    same = (isinstance(n.value, (ast.Tuple, ast.List))
                            and len(n.value.elts) == len(t.elts))
                    pairs = list(zip(t.elts, n.value.elts if same else [n.value] * len(t.elts)))
                out += [(x.slice.value, v) for x, v in pairs
                        if isinstance(x, ast.Subscript) and isinstance(x.slice, ast.Constant)]
            return out
        if isinstance(n, ast.Dict):
            return [(k.value, v) for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)]
        if isinstance(n, ast.keyword) and n.arg:
            return [(n.arg, n.value)]
        return []

    sites, violations = [], []
    for n in ast.walk(tree):
        f = fn_of(n)
        where = "line %d (%s)" % (getattr(n, "lineno", 0), f.name if f else "module")
        if is_gate_call(n):
            sites.append((f.name if f else None, ", ".join(ast.unparse(a) for a in n.args)))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "list_gap" \
                and (f is None or f.name != "absence"):
            violations.append(where + ": list_gap outside the gate")
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value == "absent":
            p = parent.get(n)
            if not (f is None and isinstance(p, ast.Assign) and len(p.targets) == 1
                    and isinstance(p.targets[0], ast.Name) and p.targets[0].id == "ABSENT"):
                violations.append(where + ": the literal absent")
        if isinstance(n, ast.Name) and n.id == "ABSENT" and isinstance(n.ctx, ast.Load):
            p = parent.get(n)
            if not ((f is not None and f.name == "absence" and isinstance(p, ast.BoolOp))
                    or (isinstance(p, ast.Compare) and polarity(p, f))):
                violations.append(where + ": ABSENT read outside a gate comparison")
        for key, value in keyed(n):
            if key == "absent_in" and not (isinstance(value, ast.Constant) and value.value is None):
                if not dominated(n if isinstance(n, ast.Assign) else value, f):
                    violations.append(where + ": absent_in set without the gate")
            if key == "push_listed":
                for c in ast.walk(value):
                    if isinstance(c, ast.Constant) and c.value is False and not dominated(c, f):
                        violations.append(where + ": push_listed False without the gate")
    return sites, violations


# Every call of the gate, generated from the source, and the test whose
# contradictory-count (or uncounted) control covers it.
_GATE_CONTROLS = {
    ("direction", "owner_rec, 'sh_s'"): "test_f3_m6_an_agreement_needs_a_complete_bijection",
    ("direction", "meas_rec, 'sh_o'"): "test_f3_m6_an_agreement_needs_a_complete_bijection",
    ("_cycle_row", "other_rec, other_gk"): "test_f3_m8_cycle_absence_needs_the_counter_pair",
    ("_cycle_row", "other_rec, other_gk, partner"): "test_f3_m8_shot_absence_needs_the_counter_pair",
    ("_cycle_row", "own_rec, own_gk, c"): "test_f3_m8_shot_absence_needs_the_counter_pair",
    ("blocks", "shooter_rec, 'b5_o'"): "test_f2_m8_a_list_without_a_counter_never_proves_absence",
    ("contacts", "shooter_rec, 'b5_h'"): "test_f2_m8_a_list_without_a_counter_never_proves_absence",
    ("pushes", "shooter_rec, 'push_o'"): "test_f2_m8_the_other_seats_lists_against_their_counters",
    ("chains", "shooter_rec, 'ch_o'"): "test_f2_m8_the_other_seats_lists_against_their_counters",
    ("deaths", "other_rec, 'bd_o'"): "test_f2_m8_the_other_seats_lists_against_their_counters",
    ("velocity_changes", "meas_rec, 'p3tb'"): "test_f2_m8_p3tb_against_p3n_target",
    ("velocity_changes", "owner_rec, 'bsel'"): "test_f2_m8_bsel_against_r_tot_bsel",
    ("deaths", "own_rec, 'push_s'"): "test_f2_m8_push_s_against_r_tot_push_own",
}


def test_f3_m8_every_absence_passes_through_the_one_gate():
    """Every absence verdict the module produces (the ABSENT string, an
    `absent_in` account, a `push_listed` False) is decided by `absence`,
    which reads `list_gap` (record, capability, zero omit, the list against
    its whole-game counter). The call sites are GENERATED from the source
    and must equal the controls table, each control a test of this file.
    Negative controls: two planted bypasses are each found."""
    sites, violations = _gate_proof(_CM_SOURCE)
    assert violations == [], violations
    assert len(sites) == len(set(sites)), sites
    assert set(sites) == set(_GATE_CONTROLS), sorted(set(sites) ^ set(_GATE_CONTROLS))
    for name in set(_GATE_CONTROLS.values()):
        assert callable(globals().get(name)), name
    old = "        why = absence(other_rec, other_gk)\n"
    assert _CM_SOURCE.count(old) == 1
    planted = _CM_SOURCE.replace(old, "        why = list_gap(other_rec, other_gk) or \"absent\"\n")
    _s, found = _gate_proof(planted)
    assert {v.split(": ", 1)[1] for v in found} >= {
        "list_gap outside the gate", "the literal absent", "absent_in set without the gate"}, found
    old = "(False if push_why == ABSENT else None)"
    assert _CM_SOURCE.count(old) == 1
    _s, found = _gate_proof(_CM_SOURCE.replace(old, "(False if push_why != \"trimmed\" else None)"))
    assert [v.split(": ", 1)[1] for v in found] == ["push_listed False without the gate"], found


def _cycle_absence(side, counted):
    """The A24 pair with one account's groups gone, its whole-game cycle
    count set to `counted`."""
    owner, meas = fx.a24_pair()
    rec, gk, tk = (meas, "sh_o", "tot_o") if side == "meas" else (owner, "sh_s", "tot_s")
    rec[gk] = []
    rec[tk][cm.TOT["cycles"]] = counted
    view = cm.pair_view(fx.records(owner, meas))
    (row,) = _owner_dir(view)["cycles"]
    subs = [c for c in cm.combat_subjects(view)["combat.cycle"] if c.row["owner"] == A]
    return _owner_dir(view), row, [cm.m_cycle_partner_absent(c, None) for c in subs]


@pytest.mark.parametrize("side", ["meas", "self"])
def test_f3_m8_cycle_absence_needs_the_counter_pair(side):
    """A cycle the other account does not list is absent there only when
    that account's groups are whole against its whole-game cycle count; a
    list that contradicts its count (none listed, one counted) proves
    nothing: NOT-RUN `inconsistent`, no absence, no difference, no
    agreement. Both accounts."""
    d, row, partner_absent = _cycle_absence(side, 0)                   # control: none counted
    assert row["absent_in"] == side and "cycle" in row["differs_by"]
    assert all(s["absent_in"] == side for s in row["shots"]) and row["shots"]
    assert d["case"] == "both_differ" and partner_absent == [side]
    d, row, partner_absent = _cycle_absence(side, 1)                   # one counted, none listed
    assert row["not_run"] == "inconsistent" and row["absent_in"] is None
    assert row["differs_by"] == [] and partner_absent == [None]
    assert all(s["not_run"] == "inconsistent" and s["absent_in"] is None for s in row["shots"])
    assert d["case"] == "not_run" and d["differs_by"] == []


def _shot_pair(variant="base", tot_s_cycles=1, tot_o_cycles=1):
    """The A24 pair with the copy's fourth projectile of another id: each
    account lists one shot of the cycle the other does not. Returns the row
    and those two shots, keyed by the account that lists each."""
    owner, meas = fx.a24_pair(variant)
    if variant == "base":
        meas["sh_o"][0][1][3][cm.SHOT["o"]["dpid"]] = 2
    owner["tot_s"][cm.TOT["cycles"]] = tot_s_cycles
    meas["tot_o"][cm.TOT["cycles"]] = tot_o_cycles
    (row,) = _owner_dir(cm.pair_view(fx.records(owner, meas)))["cycles"]
    only = {("self" if s["self"] is not None else "meas"): s for s in row["shots"]
            if (s["self"] is None) != (s["meas"] is None)}
    return row, only


@pytest.mark.parametrize("contradict", ["self", "meas"])
def test_f3_m8_shot_absence_needs_the_counter_pair(contradict):
    """A shot one account lists and the other's partnered cycle does not is
    absent there only when that account's groups are whole against its
    cycle count AND the partner lists every shot its header counts. The
    account whose list contradicts its count proves nothing about what it
    lacks; the other account's absence stands. Both sides of the gate: the
    primary cycle's own shots and the partner-only shots."""
    row, only = _shot_pair()                                            # control: both whole
    assert only["self"]["absent_in"] == "meas" and only["meas"]["absent_in"] == "self"
    assert "shot" in row["differs_by"]
    other = "meas" if contradict == "self" else "self"
    row, only = (_shot_pair(tot_s_cycles=2) if contradict == "self"
                 else _shot_pair(tot_o_cycles=2))
    assert only[other]["not_run"] == "inconsistent" and only[other]["absent_in"] is None
    assert only[contradict]["absent_in"] == other and only[contradict]["not_run"] is None
    row, only = _shot_pair("short")                 # the copy's cycle lists three of its four
    assert list(only) == ["self"] and only["self"]["not_run"] == "trimmed"
    assert only["self"]["absent_in"] is None


# -- FIX PASS 3: the cycle match is a bijection or NOT-RUN (M-6) --------------------------

def _group(i, side, s0_shift=0, pid_shift=0, pt=0):
    """Cycle `i` of a generated game on one side: three single-projectile
    volleys. Optionally under another `s0` with the SAME shot identities
    (the first entry's offset undoes the shift), other projectile ids, or
    another point."""
    g = fx.cycle_group(fx.S0 + 10000 * i, fx.PID0 + 100 * i + pid_shift, 3, side=side,
                       reload_after=False)
    g[0][cm.HDR["pt"]] = pt
    if s0_shift:
        g[0][cm.HDR["s0"]] += s0_shift
        g[1][0][cm.SHOT[side]["dt"]] = -s0_shift
    return g


def _cycles_rec(side, groups):
    rec = fx.empty_record()
    rec["tb"] = [fx.point()]
    rec["tb_tot"] = fx.tb_tot_of(rec["tb"])
    rec["gun_" + side] = [fx.gun()]
    rec["sh_" + side] = [fx.clone(g) for g in groups]
    return fx.finish(rec, side)


def _cycles_dir(owner_groups, meas_groups):
    owner, meas = _cycles_rec("s", owner_groups), _cycles_rec("o", meas_groups)
    cm.check_record(owner)
    cm.check_record(meas)
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    for acct, rec, side in (("self", owner, "s"), ("meas", meas, "o")):   # no cycle suppressed
        listed = sorted((c["s0"], c["pt"], c["pid0"]) for c in cm.rebuild_side(rec, side))
        shown = sorted((r[acct]["s0"], r[acct]["pt"], r[acct]["pid0"]) for r in d["cycles"]
                       if r[acct] is not None)
        assert shown == listed, (acct, shown, listed)
    return d


def _all_ambiguous(d):
    assert d["pairing"] == "ambiguous"
    for r in d["cycles"]:
        assert r["not_run"] == "ambiguous" and r["absent_in"] is None and r["differs_by"] == []
        assert all(s["not_run"] == "ambiguous" and s["absent_in"] is None for s in r["shots"])
    assert "cycle" not in d["differs_by"] and "shot" not in d["differs_by"]
    assert d["case"] != "both_agree"


def test_f3_m6_reordered_cycles_pair_one_to_one():
    d = _cycles_dir([_group(0, "s"), _group(1, "s")], [_group(1, "o"), _group(0, "o")])
    assert d["pairing"] is None and d["case"] == "both_agree", (d["case"], d["differs_by"])
    assert len(d["cycles"]) == 2
    assert all(r["self"] is not None and r["meas"] is not None for r in d["cycles"])


def test_f3_m6_a_duplicate_s0_is_ambiguous_and_no_cycle_is_dropped():
    """An `s0` listed twice on one side (the two cycles' projectiles are
    different, so only the `s0` repeats), on either side: every cycle of
    both accounts is shown, all NOT-RUN `ambiguous`."""
    for owner_groups, meas_groups in (
            ([_group(0, "s"), _group(1, "s")],
             [_group(0, "o"), _group(1, "o"), _group(1, "o", pid_shift=50)]),
            ([_group(0, "s"), _group(1, "s"), _group(1, "s", pid_shift=50)],
             [_group(0, "o"), _group(1, "o")])):
        d = _cycles_dir(owner_groups, meas_groups)
        _all_ambiguous(d)
        assert len(d["cycles"]) == len(owner_groups) + len(meas_groups)


def test_f3_m6_the_reviewers_multiplicity_case_is_ambiguous_never_agreement():
    """Owner cycles [A, B] against measured [A, A], B with A's `s0` and shot
    identities and another point. Before fix pass 3 the measured A paired
    with the owner's A twice, B was suppressed because its shots were
    covered, and the case was `both_agree`."""
    d = _cycles_dir([_group(0, "s"), _group(0, "s", pt=1)], [_group(0, "o"), _group(0, "o")])
    _all_ambiguous(d)
    assert d["case"] == "not_run" and len(d["cycles"]) == 4
    assert sorted(r["self"]["pt"] for r in d["cycles"] if r["self"] is not None) == [0, 1]


def test_f3_m6_a_shot_identity_in_two_cycles_is_ambiguous():
    """One projectile in two cycles of different `s0`: on one side (the
    other side lists neither), and across the sides (each side lists it
    under its own `s0`)."""
    d = _cycles_dir([_group(0, "s"), _group(1, "s")],
                    [_group(0, "o"), _group(1, "o"), _group(2, "o"),
                     _group(2, "o", s0_shift=5000)])
    _all_ambiguous(d)
    d = _cycles_dir([_group(0, "s"), _group(1, "s")],
                    [_group(0, "o", s0_shift=5000), _group(1, "o")])
    _all_ambiguous(d)
    assert d["case"] == "not_run"


def test_f3_m6_an_agreement_needs_a_complete_bijection():
    """`both_agree` only from a one-to-one pairing of both accounts' WHOLE
    cycle lists (each against its whole-game cycle count). A cycle one side
    trimmed, or the same cycle trimmed on both sides, leaves the compared
    cycles agreeing and the case NOT-RUN. Both sides of the gate."""
    owner = _cycles_rec("s", [_group(0, "s"), _group(1, "s")])
    meas = _cycles_rec("o", [_group(0, "o"), _group(1, "o")])
    assert _owner_dir(cm.pair_view(fx.records(owner, meas)))["case"] == "both_agree"   # control

    def cut(rec, gk):
        out = fx.clone(rec)
        out[gk] = out[gk][:1]
        out["omit"][gk] = 1                                          # the totals stay whole
        return out
    for o, m, nrows in ((owner, cut(meas, "sh_o"), 2), (cut(owner, "sh_s"), meas, 2),
                        (cut(owner, "sh_s"), cut(meas, "sh_o"), 1)):
        d = _owner_dir(cm.pair_view(fx.records(o, m)))
        assert len(d["cycles"]) == nrows and d["cycles"][0]["not_run"] is None
        assert [r["not_run"] for r in d["cycles"][1:]] == ["trimmed"] * (nrows - 1)
        assert d["differs_by"] == [] and d["case"] == "not_run", (d["case"], d["differs_by"])


# -- FIX PASS 2: the purge states the allowlist the constants apply (L-6) -----------------

def test_f2_l6_the_purge_wording_is_the_allowlist_the_constants_apply():
    doc = " ".join(ce.purge_pass.__doc__.split())
    named = re.findall(r"`([a-z0-9_*]+)`", doc)
    kept = [n for n in named if not n.endswith("*")]
    families = [n[:-1] for n in named if n.endswith("*")]
    assert sorted(kept) == sorted(ce.RETAINED_LISTS)                     # every kept list, no other
    assert set(ce.PURGED_LISTS) == set(cm.LISTS) - set(ce.RETAINED_LISTS)
    for fam in families:                                                 # each named family goes whole
        members = [k for k in cm.LISTS if k.startswith(fam)]
        assert members and set(members) <= set(ce.PURGED_LISTS), fam
    assert sorted(families) == ["gun_", "ivl_"]
    stays = [k for k in cm.KEYS if k not in cm.LISTS]                    # scalars, rows, histograms
    assert {cm.SPEC[k][0] for k in stays} == {"int", "enum", "row", "rows", "hist", "omit"}
    assert not set(stays) & set(ce.PURGED_LISTS)
    for name in ("PURGED_LISTS", "RETAINED_LISTS", "LIST_RETENTION_DAYS"):
        assert name in doc
    assert "whole-game rows" in doc and "histograms" in doc
    assert "stat blocks" not in doc                                      # gun_* is purged


# -- FIX PASS 1: the steering references, subjects and measures (M-3) ---------------------

def test_m3_the_pinned_homing_and_target_bounce_cases_and_their_mutants():
    pinned = json.loads(_read(fx.FIXTURE_DIR, "steering.json"))
    assert pinned == json.loads(json.dumps(fx.steering_set()))
    by = {h["name"]: h for h in pinned["homing"]}
    assert by["homing_in_cone"]["entry"][2] > 0                           # the homing term turns it
    assert by["homing_out_of_cone"]["entry"][2] == 0                      # control: outside the cone
    for h in pinned["homing"]:
        assert h["mutant_entry"][2] != h["entry"][2]                      # an added turn is seen
        assert h["entry"][3] == len(h["packages"]) == len(h["frames"]) // h["sync_every"] + 1
    wait_ms = cm.W["bounce"]["wait_s"] * cm.PER_MILLE
    for b in pinned["bounce"]:
        assert b["entry"]["gap"] >= wait_ms > b["mutant_entry"]["gap"]
    hit = {b["name"]: b for b in pinned["bounce"]}
    assert hit["bounce_to_target"]["entry"]["has_retarget"] == 1
    assert hit["bounce_no_target"]["entry"]["has_retarget"] == 0


def test_m3_homing_runs_the_game_steps_in_single_precision():
    name, state, target, frames, prm, every = fx.HOMING_CASES[0]
    st, on = cm.homing_step(state, target, frames[0], prm)
    assert on is True and all(cm.f32(v) == v for v in st.values())
    off, on2 = cm.homing_step(state, fx.HOMING_CASES[1][2], frames[0], prm)
    assert on2 is False and off == cm.integrate(state, [frames[0]], prm)


def _steer_record(consts=1, omit_tb=0, omit_ht=0):
    rec = fx.empty_record(consts)
    pinned = fx.steering_set()
    h = pinned["homing"][0]["entry"]
    rec["p3ht"] = [fx.named_row("p3ht", pid=h[0], s_rel=h[1], ratio_pm=h[2], n=h[3])]
    b = pinned["bounce"][0]["entry"]
    rec["p3tb"] = [fx.named_row("p3tb", pid=5, s_init=100, s_rel=300, gap=b["gap"],
                                has_retarget=b["has_retarget"], ang_to_me=b["ang_to_me"])]
    rec["p3hm"] = [0, 0, 1, 0, 0, 0, 0, 0, 0, 0]
    rec["omit"]["p3tb"], rec["omit"]["p3ht"] = omit_tb, omit_ht
    return rec, pinned


def test_m3_target_bounce_and_homing_are_versioned_subjects_with_not_run():
    m = _measure_fn
    rec, pinned = _steer_record()
    subs = cm.combat_subjects(cm.pair_view(fx.records(None, rec)))
    (tb,), (hm,), (b3,) = subs["combat.tbounce"], subs["combat.homing"], subs["combat.b3"]
    assert m("b3.tb.gap")(tb, None) == pinned["bounce"][0]["entry"]["gap"]
    assert m("b3.tb.ang_to_me")(tb, None) == pinned["bounce"][0]["entry"]["ang_to_me"]
    assert m("b3.hm.ratio_pm")(hm, None) == pinned["homing"][0]["entry"][2]
    assert m("b3.hm.packages")(hm, None) == pinned["homing"][0]["entry"][3]
    assert m("b3.tb.min_gap")(b3, None) == pinned["bounce"][0]["entry"]["gap"]
    assert m("b3.hm.max_ratio_pm")(b3, None) == pinned["homing"][0]["entry"][2]
    for rec2, key in ((_steer_record(omit_tb=1)[0], "b3.tb.min_gap"),
                      (_steer_record(omit_ht=1)[0], "b3.hm.max_ratio_pm")):
        (b3t,) = cm.combat_subjects(cm.pair_view(fx.records(None, rec2)))["combat.b3"]
        assert m(key)(b3t, None) is None                                  # trimmed: NOT-RUN
    other = _steer_record(consts=2)[0]
    subs2 = cm.combat_subjects(cm.pair_view(fx.records(None, other)))
    assert m("b3.tb.gap")(subs2["combat.tbounce"][0], None) is None       # unread version
    assert m("b3.hm.ratio_pm")(subs2["combat.homing"][0], None) is None
    empty = cm.combat_subjects(cm.pair_view(fx.records(None, fx.empty_record())))
    assert empty["combat.tbounce"] == [] and m("b3.tb.min_gap")(empty["combat.b3"][0], None) is None


# -- FIX PASS 1: wire to view to subject to measure (M-4) ---------------------------------

def _sums(*names):
    return ("contrib", names)


def _rec_rows(key):
    return tuple("rec.%s.%s" % (key, f[0]) for f in cm.SPEC[key][1])


GUN_FIELDS = tuple(f[0] for f in cm.SPEC["gun_s"][3] if f[0] != "pt")
COVERAGE = {
    "schema": [("parse", ())],
    "consts": [("combat.aim", ("b1.hist.compatible",)), ("combat.record", ("rec.a1sum",))],
    "caps": [("combat.record", ("rec.caps",))],
    "t0": [("combat.record", ("rec.t0",))],
    "t0_src": [("combat.record", ("rec.t0_src",))],
    "frame_p50_us": [("combat.record", ("rec.frame_p50_us",))],
    "cost": [("combat.record", ("rec.cost.calls", "rec.cost.total_us", "rec.cost.max_us",
                                "rec.cost.faults"))],
    "l_hat": [("combat.record", ("rec.l_hat",))],
    "tb_tot": [("combat.record", _rec_rows("tb_tot"))],
    "tb": [("combat.point", ("tb.point.slow", "tb.point.ramp", "tb.point.clamp", "tb.point.frames",
                             "tb.point.dt_med_us", "tb.point.dt_max_us", "tb.point.real",
                             "tb.point.game", "tb.point.srv", "tb.point.ps", "tb.point.base",
                             "tb.point.game_real", "tb.point.srv_real"))],
    "a1s": [("combat.aim", ("b1.hist.self_volleys",)), _sums("a1s")],
    "a1p": [_sums("a1p")],
    "a1m": [("combat.aim", ("b1.hist.meas_volleys",)), _sums("a1m")],
    "a1n": [_sums("a1n")],
    "a1sum": [("combat.record", ("rec.a1sum",))],
    "rx_s": [("combat.react", ("b1.react.aim_on", "b1.react.first", "b1.react.err",
                               "b1.react.account"))],
    "rx_o": [("combat.react", ("b1.react.aim_on", "b1.react.first", "b1.react.err",
                               "b1.react.account"))],
    "gun_s": [("combat.stat", tuple("b2.stat.self." + f for f in GUN_FIELDS)
               + tuple("b2.stat.d_" + f for f in GUN_FIELDS) + ("b2.stat.fields_differing",)),
              ("combat.cycle", ("b2.cycle.rexp", "b2.cycle.mag_plus_regen"))],
    "gun_o": [("combat.stat", tuple("b2.stat.meas." + f for f in GUN_FIELDS))],
    "tot_s": [("combat.record", _rec_rows("tot_s")),
              ("combat.direction", ("b2.atk.d_count", "b2.totals.d_units"))],
    "tot_o": [("combat.record", _rec_rows("tot_o")),
              ("combat.direction", ("b2.atk.d_count", "b2.totals.d_units"))],
    "ivl_s": [("combat.interval", ("b2.ivl.gmin", "b2.ivl.cexp_min", "b2.ivl.vmax", "b2.ivl.vexp",
                                   "b2.ivl.refreshes", "b2.ivl.account"))],
    "ivl_o": [("combat.interval", ("b2.ivl.gmin", "b2.ivl.cexp_min", "b2.ivl.vmax", "b2.ivl.vexp",
                                   "b2.ivl.refreshes", "b2.ivl.account"))],
    "cx_s": [("combat.record", ("rec.faults", "rec.omitted.cx_s"))],
    "cx_o": [("combat.record", ("rec.faults", "rec.omitted.cx_o"))],
    "sh_s": [("combat.cycle", ("b2.cycle.account", "b2.cycle.units", "b2.cycle.in_rl",
                               "b2.cycle.tail", "b2.cycle.gap_first", "b2.cycle.gap_second",
                               "b2.cycle.gap_third", "b2.cycle.why", "b2.cycle.end",
                               "b2.cycle.excess", "b2.cycle.regen", "b2.cycle.regen_stated")),
             ("combat.shot", ("b2.shot.d_ammo", "b2.shot.d_reloading", "b2.shot.d_counter",
                              "b2.shot.absent", "b2.shot.owner_gate_flags",
                              "b2.shot.owner_since")),
             ("combat.refill", ("b2.refill.self_rl_g", "b2.refill.self_rl_s",
                                "b2.refill.self_rl_r", "b2.refill.d_rl_g", "b2.refill.d_rl_s",
                                "b2.refill.d_rl_r", "b2.refill.d_st_end",
                                "b2.refill.owner_only_units")),
             ("combat.regen", ("b2.regen.amt", "b2.regen.gap_g", "b2.regen.gap_s",
                               "b2.regen.gap_r", "b2.regen.stream_whole")),
             ("combat.direction", ("b2.direction.case", "b2.direction.differs_by"))],
    "sh_o": [("combat.refill", ("b2.refill.meas_rl_g", "b2.refill.meas_rl_s",
                                "b2.refill.meas_rl_r", "b2.refill.meas_only_units")),
             ("combat.shot", ("b2.shot.d_ammo",)), ("combat.cycle", ("b2.cycle.account",)),
             ("combat.regen", ("b2.regen.amt",))],
    "p3n": [("combat.b3", ("b3.counts",)), ("combat.record", _rec_rows("p3n"))],
    "p3dp0": [_sums("p3dp0")],
    "p3an0": [_sums("p3an0")],
    "p3dp1": [_sums("p3dp1")],
    "p3an1": [_sums("p3an1")],
    "p3hm": [("combat.b3", ("b3.hm.hist",))],
    "p3self": [("combat.record", _rec_rows("p3self"))],
    "p3top": [("combat.top", ("b3.top.d_perp", "b3.top.d_along", "b3.top.ang", "b3.top.dt",
                              "b3.top.speed", "b3.top.mask"))],
    "p3tb": [("combat.tbounce", ("b3.tb.gap", "b3.tb.has_retarget", "b3.tb.ang_to_me")),
             ("combat.b3", ("b3.tb.min_gap",)), ("combat.bounce", ("b3.bounce.meas_gap",))],
    "p3ht": [("combat.homing", ("b3.hm.ratio_pm", "b3.hm.packages")),
             ("combat.b3", ("b3.hm.max_ratio_pm",))],
    "b5_tot": [("combat.record", _rec_rows("b5_tot"))],
    "b5_s": [("combat.block", ("b5.pair.d_open", "b5.pair.d_len", "b5.pair.d_len_g",
                               "b5.pair.d_pred_lo", "b5.pair.d_pred_hi", "b5.pair.frame_bound",
                               "b5.ctl.cd", "b5.ctl.gap_prev", "b5.ctl.len_g", "b5.ctl.reopen",
                               "b5.ctl.scale_pm", "b5.ctl.press", "b5.ctl.fr"))],
    "b5_o": [("combat.block", ("b5.ctl.cd_c", "b5.ctl.gap_prev_s", "b5.ctl.len_cg",
                               "b5.ctl.started", "b5.ctl.reopen_c", "b5.ctl.ta", "b5.ctl.o_pred"))],
    "b5_h": [("combat.contact", ("b5.contact.since_ms", "b5.contact.pred_since",
                                 "b5.contact.contact_to_decision"))],
    "b5_c": [("combat.contact", ("b5.contact.since_c", "b5.contact.own_since"))],
    "b5_r": [("combat.refused", ("b5.refused.since_prev", "b5.refused.cd"))],
    "r_tot": [("combat.record", _rec_rows("r_tot") + ("rec.faults",))],
    "push_s": [("combat.push", ("b5.push.mass", "b5.push.d_fx", "b5.push.d_fy", "b5.push.d_vax",
                                "b5.push.d_vay"))],
    "push_o": [("combat.push", ("b5.push.d_fx",))],
    "vchg": [("combat.vchange", ("b3.vchange.cause", "b3.vchange.turn_mrad"))],
    "bsel": [("combat.bounce", ("b3.bounce.target", "b3.bounce.nearer"))],
    "ch_s": [("combat.chain", ("b5.chain.hp_to_frame", "b5.chain.msg_transit"))],
    "ch_o": [("combat.chain", ("b5.chain.dmg_transit", "b5.chain.decision_to_screen"))],
    "bd_s": [("combat.death", ("death.boundary.cause", "death.boundary.edge",
                               "death.boundary.recent_hits", "death.boundary.push_unlisted"))],
    "bd_o": [("combat.death", ("death.boundary.d_px",))],
    "omit": [("combat.record", ("rec.listed",) + tuple("rec.omitted." + k for k in cm.LISTS))],
}


def full_pair():
    """(victim seat A, shooter seat B): every wire key populated at least once."""
    victim, shooter = fx.r_sections_pair()
    owner, meas = fx.a24_pair("regen")                                 # a refill event listed
    for k in ("tb", "tb_tot", "gun_s", "sh_s", "cx_s", "tot_s"):
        victim[k] = owner[k]
    for k in ("tb", "tb_tot", "gun_o", "sh_o", "cx_o", "tot_o"):
        shooter[k] = meas[k]
    rx = fx.named_row("rx_s", onset=3000, aim_on=120, first=260, err=35)
    victim["rx_s"], victim["rx_o"] = [rx], [list(rx)]
    iv = fx.named_row("ivl_s", pt=0, gmin=180, cexp_min=300, vmax=4, vexp=3, refreshes=1)
    victim["ivl_s"], victim["ivl_o"] = [iv], [list(iv)]
    victim["b5_r"] = [fx.named_row("b5_r", rel=7000, since_prev=400, cd=1000)]
    bv, bs = _block_pair(7200, 7260)
    victim["b5_s"], shooter["b5_o"] = bv["b5_s"], bs["b5_o"]
    cv, cs = _contact_pair([(9, 100, 0, 1500)], [(9, 100, 0, 1530)])
    victim["b5_c"], shooter["b5_h"] = cv["b5_c"], cs["b5_h"]
    steer, _p = _steer_record()
    victim["p3ht"], victim["p3hm"] = steer["p3ht"], steer["p3hm"]
    victim["p3top"] = [fx.named_row("p3top", pid=3, s_rel=0, d_perp=5, d_along=2, ang=1, dt=117,
                                    speed=8000, mask=0)]
    return victim, shooter


def test_m4_every_wire_key_reaches_a_registered_measure_on_a_populated_subject():
    assert set(COVERAGE) == set(cm.KEYS)
    victim, shooter = full_pair()
    cm.check_record(victim)
    cm.check_record(shooter)
    records = fx.records(victim, shooter)
    subs = cm.combat_subjects(cm.pair_view(records))
    sums = {k for c in cm.contributions(records) for k in c["sums"]}
    for key, routes in COVERAGE.items():
        for subject, names in routes:
            if subject == "parse":
                continue
            if subject == "contrib":
                assert set(names) <= sums, key
                continue
            assert subs[subject], (key, subject)                          # the view reaches it
            for n in names:
                e = rm.REGISTRY.get(n)
                assert e is not None and e.kind == "measure" and e.subject == subject, (key, n)
                for ctx in subs[subject]:
                    e.impl[0](ctx, None)                                  # and it evaluates


def test_m4_the_clock_inputs_answer_none_never_minus_one():
    m = _measure_fn
    victim, shooter = full_pair()
    victim["rx_s"][0][cm.IX["rx_s"]["first"]] = -1
    victim["ivl_s"][0][cm.IX["ivl_s"]["gmin"]] = -1
    victim["b5_r"][0][cm.IX["b5_r"]["since_prev"]] = -1
    subs = cm.combat_subjects(cm.pair_view(fx.records(victim, shooter)))
    own_rx = [c for c in subs["combat.react"] if c.row["account"] == "self"]
    assert [m("b1.react.first")(c, None) for c in own_rx] == [None]
    own_iv = [c for c in subs["combat.interval"] if c.row["account"] == "self"]
    assert [m("b2.ivl.gmin")(c, None) for c in own_iv] == [None]
    assert [m("b5.refused.since_prev")(c, None) for c in subs["combat.refused"]] == [None]
    copy_rx = [c for c in subs["combat.react"] if c.row["account"] == "meas"]
    assert [m("b1.react.first")(c, None) for c in copy_rx] == [260]       # control


def test_m4_a_trimmed_list_has_no_listed_count():
    victim, shooter = full_pair()
    victim["omit"]["rx_s"] = 3
    (rec,) = [c for c in cm.combat_subjects(cm.pair_view(fx.records(victim, shooter)))["combat.record"]
              if c.row["seat"] == A]
    listed = cm.m_rec_listed(rec, None)
    assert listed["rx_s"] is None and listed["rx_o"] == 1
    assert _measure_fn("rec.omitted.rx_s")(rec, None) == 3


# -- FIX PASS 1: A22 template multiplicity (L-4) ----------------------------------------

def _template_pair(tmpl_o=2):
    """One gate call, two emissions, each emission TWO projectiles (template
    multiplicity two, the gun stat's `tmpl`)."""
    owner, meas = fx.empty_record(), fx.empty_record()
    for r in (owner, meas):
        r["tb"] = [fx.point()]
        r["tb_tot"] = fx.tb_tot_of(r["tb"])
    owner["gun_s"] = [fx.gun(mag=6, tmpl=2)]
    meas["gun_o"] = [fx.gun(mag=6, tmpl=tmpl_o)]
    owner["sh_s"] = [[fx.hdr(5000, 40, 4, end=cm.END["point"], rl=(-1, -1, -1)),
                      [fx.own_shot(0, 0, 6, 0, 0, rep=0), fx.own_shot(1, 0, 5, 0, 0, rep=-1),
                       fx.own_shot(1, 100, 4, 0, 100, rep=1), fx.own_shot(1, 0, 3, 0, 100, rep=-1)],
                      []]]
    meas["sh_o"] = [[fx.hdr(5000, 40, 4, end=cm.END["point"], rl=(-1, -1, -1)),
                     [fx.copy_shot(0, 0, 6, 0, 0, am=20), fx.copy_shot(1, 0, 5, 0, 0, am=-1),
                      fx.copy_shot(1, 100, 4, 0, 100, am=21), fx.copy_shot(1, 0, 3, 0, 100, am=-1)],
                     []]]
    owner["tot_s"] = fx.tot(cycles=1, volleys=2, units=4, gate=1, emit=2)
    meas["tot_o"] = fx.tot(cycles=1, volleys=2, units=4, atk_msg=2)
    return owner, meas


def test_l4_a22_a_template_multiplicity_above_one_is_units_per_emission():
    owner, meas = _template_pair()
    cm.check_record(owner)
    cm.check_record(meas)
    assert cm.rebuild_faults(owner, "s") == [] and cm.rebuild_faults(meas, "o") == []
    d = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    tmpl = d["stat"][0]["self"]["tmpl"]
    assert tmpl == 2 and d["cycles"][0]["self"]["units"] == d["attacks"]["owner_emit"] * tmpl
    assert d["attacks"]["d_emit_msgs"] == 0 and d["case"] == "both_agree"
    o2, m2 = _template_pair(tmpl_o=1)                                    # negative mutant
    d2 = _owner_dir(cm.pair_view(fx.records(o2, m2)))
    assert d2["stat"][0]["diff"]["d_tmpl"] == 1 and d2["case"] == "both_differ"
    assert d2["differs_by"] == ["stat"]


# -- FIX PASS 1: the match report canonical, byte for byte (L-1) ---------------------------

def test_l1_the_match_report_hmac_is_exactly_the_seven_field_canonical(monkeypatch):
    import hashlib
    import hmac as _hmac
    main = _main()
    monkeypatch.setattr(main, "MATCH_HMAC_SECRET", fx.KEY)
    canonical = b"76561190000000001:76561190000000002:5:3:true:76561190000000001:room_cev_l1"
    assert canonical.count(b":") == 6                                     # seven fields

    def report(sig, **over):
        vals = dict(p1="76561190000000001", p2="76561190000000002", r1=5, r2=3, ranked=True,
                    by="76561190000000001", room="room_cev_l1")
        vals.update(over)
        return types.SimpleNamespace(
            player1=types.SimpleNamespace(steam_id=vals["p1"]),
            player2=types.SimpleNamespace(steam_id=vals["p2"]),
            p1_rounds_won=vals["r1"], p2_rounds_won=vals["r2"], is_ranked=vals["ranked"],
            reported_by_steam_id=vals["by"], photon_room_id=vals["room"], hmac_signature=sig)

    def sign(msg):
        return _hmac.new(fx.KEY.encode(), msg, hashlib.sha256).hexdigest()
    assert main.verify_hmac(report(sign(canonical))) is True
    for wrong in (canonical.replace(b":true:", b":True:"),
                  canonical + b":extra",
                  canonical.rsplit(b":", 1)[0],
                  b"76561190000000002:76561190000000001:3:5:true:76561190000000001:room_cev_l1"):
        assert main.verify_hmac(report(sign(wrong))) is False
    unranked = canonical.replace(b":true:", b":false:")
    assert main.verify_hmac(report(sign(unranked), ranked=False)) is True
    no_room = canonical.rsplit(b":", 1)[0] + b":"
    assert main.verify_hmac(report(sign(no_room), room=None)) is True
