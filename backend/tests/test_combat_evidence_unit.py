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
    files = fx.canonical_set()
    name = "a24_owner.out.txt"
    changed = files[name].replace(b'"consts":1', b'"consts":2')
    assert changed != files[name]


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


def test_a6_a_skipped_decrement_shows_reason_bit_one_and_a_non_zero_ammo_difference():
    owner, meas = fx.a24_pair()
    skip = fx.clone(owner)
    for e, a0 in zip(skip["sh_s"][0][1], (3, 3, 2, 1)):
        e[2] = a0
    skip["sh_s"][0][1][3][3] = 0
    d = _owner_dir(cm.pair_view(fx.records(skip, meas)))
    assert d["cycles"][0]["meas"]["why"] & cm.WHY["over_mag"]
    assert [s["d_ammo"] for s in d["cycles"][0]["shots"]] == [0, 1, 1, 1]
    assert d["case"] == "both_differ"
    control = _owner_dir(cm.pair_view(fx.records(owner, meas)))
    assert [s["d_ammo"] for s in control["cycles"][0]["shots"]] == [0, 0, 0, 0]


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
        "b2.shot.owner_gate_flags", "b2.shot.owner_since"}


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


def test_m10_a_duplicated_or_gapped_contact_key_is_ambiguous_and_not_run():
    victim, shooter = _contact_pair([(9, 100, 0, 1500), (9, 100, 0, 1600)],
                                    [(9, 100, 0, 1530)])
    rows = cm.contacts(victim, shooter)
    assert [r["not_run"] for r in rows] == ["ambiguous", "ambiguous"]
    assert all(r["since_ms"] is None and r["since_c"] is None for r in rows)
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [(9, 100, 1, 1530)])
    assert cm.contacts(victim, shooter)[0]["not_run"] in ("ambiguous", "absent")
    victim, shooter = _contact_pair([(9, 100, 0, 1500)], [])
    assert cm.contacts(victim, shooter)[0]["not_run"] == "absent"
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
    delay = 125
    (control,) = cm.blocks(*_block_pair(7200, 7260))
    (delayed,) = cm.blocks(*_block_pair(7200, 7260 + delay))
    assert delayed["d_open"] - control["d_open"] == delay
    assert delayed["frame_bound"] == control["frame_bound"]


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


def test_a21_a_timer_refill_carries_three_clocks_and_a_card_reload_ends_external():
    owner, meas = fx.a24_pair()
    row = _owner_dir(cm.pair_view(fx.records(owner, meas)))["cycles"][0]
    assert list(row["refill"]["end"]["rl_g"]) == [1500, 1500]
    assert list(row["refill"]["end"]["rl_r"]) == [1600, 1600]
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
    assert row["hits"] == [{"pid": 9, "s_init": 4100, "cord": 0, "age": 800, "push_listed": True}]
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
