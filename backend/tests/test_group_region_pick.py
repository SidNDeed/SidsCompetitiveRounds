"""Pure tests for backend/api/region_pick.py — the multiplayer room-region
rule (v4: baseline B, quorum, majority-or-bounded admission, SUM selection).

Every worked-example row of ai-collab/sept10-batch/02-region-v4.md is a
fixture with its maps built EXACTLY as written. Two of the table's cells do
not follow from its own maps, and the tests pin what the rule as stated
actually produces rather than the cell:

  * EU/RU row: the tie cell says "sums 220/220, worsts 90/80"; the maps as
    written give sum(eu) = 30+30+90+90 = 240 and sum(ru) = 80+80+30+30 = 220,
    so the tie resolves on SUM (ru), not worst. Pick/why are unaffected
    (rue, bounded — and it is the "equal total, strictly lower worst"
    departure). A sibling exercises the equal-total, lower-worst departure.
  * Last row (4x {us 60, ussc 35, usw 70}): the mutation "`>=` -> `>` on the
    majority arm fails this row" cannot — gain is 4 of 4 (2*4 > 4 holds
    under the strict form too) and the bounded arm admits ussc anyway
    (regret -25). The m1 control therefore uses a majority-ONLY fixture with
    gain exactly N/2 (row 2's maps with the west seats 10 ms further from us),
    and a companion assertion documents that the last row does not flip.

Negative controls flip one clause each through the module's test-only knobs
(`_MAJORITY_STRICT`, `_SKIP_QUORUM`, `_SELECT_BY_WORST`) or a parameter
(`regret_ms=0`); each asserts the FLIPPED outcome and its default twin.
"""

import itertools

import pytest

import region_pick
from region_pick import pick_region_for_group

NOW = 1_700_000_000.0
MAX_AGE = 180
LIVE = ("us", "usw", "ussc", "eu", "ru", "rue")
VOLUMES = {"us": 1000, "eu": 800, "usw": 300, "ussc": 200, "ru": 150, "rue": 50}
LEGACY = "legacy-sentinel"   # never a real code: a verdict equal to it came from the fallback


def seat(sid, home, pings, age=0):
    return {"id": sid, "home": home,
            "map": None if pings is None else dict(pings),
            "measured_at": None if age is None else NOW - age}


def run(members, legacy=LEGACY, live=LIVE, volumes=VOLUMES, **kw):
    kw.setdefault("now", NOW)
    kw.setdefault("max_age_s", MAX_AGE)
    return pick_region_for_group(members, live, volumes, legacy, **kw)


def cand(detail, code):
    rows = [c for c in detail["candidates"] if c["region"] == code]
    assert len(rows) == 1, detail["candidates"]
    return rows[0]


# ── Worked-example rows, maps exactly as written ─────────────────────────────

EAST = {"us": 30, "ussc": 50, "usw": 80, "eu": 110}
EU_FAR = {"us": 120, "ussc": 130, "usw": 150, "eu": 30}


def row1():
    return [seat("a", "us", EAST), seat("b", "us", EAST), seat("c", "us", EAST),
            seat("d", "eu", EU_FAR)]


def row2(west_us=90):
    east = {"us": 30, "ussc": 75}
    west = {"usw": 30, "ussc": 50, "us": west_us}
    return [seat("e1", "us", east), seat("e2", "us", east),
            seat("w1", "usw", west), seat("w2", "usw", west)]


def row3():
    west = {"usw": 30, "ussc": 50, "us": 90}
    east = {"us": 30, "ussc": 75, "usw": 90}
    return [seat("w1", "usw", west), seat("w2", "usw", west), seat("w3", "usw", west),
            seat("e", "us", east)]


def row4():
    eu = {"eu": 30, "rue": 70, "ru": 80}
    ru = {"ru": 30, "rue": 40, "eu": 90}
    return [seat("eu1", "eu", eu), seat("eu2", "eu", eu),
            seat("ru1", "ru", ru), seat("ru2", "ru", ru)]


def row5_codex_c1():
    return [seat("A", "us", {"us": 30, "eu": 65}),
            seat("B", "us", {"us": 100, "eu": 140}),
            seat("C", "us", {"us": 100, "eu": 140}),
            seat("D", "eu", {"us": 300, "eu": 20})]


def row6_codex_c2():
    return [seat("A", "eu", {"us": 100, "eu": 80}), seat("B", "eu", {"us": 100, "eu": 80}),
            seat("C", "us", {"us": 10, "eu": 300}), seat("D", "us", {"us": 10, "eu": 300})]


def row7_missing_baseline():
    return [seat("a", "us", {"us": 30, "eu": 150}), seat("b", "us", {"us": 30, "eu": 150}),
            seat("c", "us", {"us": 30, "eu": 150}), seat("d", "eu", {"eu": 30})]


def row8(stale_last=False):
    m = {"us": 60, "ussc": 35, "usw": 70}
    return [seat("a", "us", m), seat("b", "us", m), seat("c", "us", m),
            seat("d", "usw", m, age=200 if stale_last else 0)]


def sister():
    """3 near + 1 far: the compromise region has the lower WORST but the
    higher SUM. The rule must keep us (sum 250 < 305)."""
    return [seat("a", "us", {"us": 40, "ussc": 70}), seat("b", "us", {"us": 40, "ussc": 70}),
            seat("c", "us", {"us": 40, "ussc": 70}), seat("d", "us", {"us": 130, "ussc": 95})]


def test_row1_three_east_one_eu_stays_us():
    pick, why, d = run(row1())
    assert (pick, why) == ("us", "baseline")
    assert d["baseline"] == "us" and d["tie"] is None
    assert (d["sum_b"], d["worst_b"]) == (210, 120)
    ussc = cand(d, "ussc")
    assert (ussc["gain"], ussc["max_regret"], ussc["admitted_by"], ussc["sum"]) == (0, 20, "bounded", 280)
    assert cand(d, "eu")["admitted_by"] is None and cand(d, "eu")["gain"] == 1
    assert cand(d, "usw")["admitted_by"] is None and cand(d, "usw")["max_regret"] == 50
    assert d["seats"][3] == {"id": "d", "state": "fresh", "cost_b": 120, "cost_pick": 120}


def test_row2_two_two_split_lexical_baseline_stands():
    pick, why, d = run(row2())
    assert (pick, why) == ("us", "baseline")
    assert d["tie"] == "measured"      # east maps carry no usw entry -> only us is peer-measured
    assert d["baseline"] == "us"
    ussc = cand(d, "ussc")
    assert (ussc["gain"], ussc["max_regret"], ussc["admitted_by"]) == (2, 45, "majority")
    assert (ussc["sum"], d["sum_b"]) == (250, 240)


def test_row3_three_west_one_east_stays_usw():
    pick, why, d = run(row3())
    assert (pick, why) == ("usw", "baseline")
    ussc = cand(d, "ussc")
    assert (ussc["gain"], ussc["max_regret"], ussc["admitted_by"], ussc["sum"]) == (0, 20, "bounded", 225)
    assert d["sum_b"] == 180
    us = cand(d, "us")
    assert (us["gain"], us["max_regret"], us["admitted_by"]) == (1, 60, None)


def test_row4_eu_ru_tie_anchors_lexically_and_moves_to_rue_by_majority():
    pick, why, d = run(row4())
    # Both tied homes are peer-measured, so the anchor is the lexical eu —
    # never the numbers (ru's lower total used to make it the baseline and
    # skip the gate). From eu, both ru and rue are majority moves (the two
    # RU seats gain 60 / 50); rue wins the selection on the lower worst.
    assert (d["baseline"], d["tie"]) == ("eu", "lexical")
    assert (pick, why) == ("rue", "majority")
    assert (d["sum_b"], d["worst_b"]) == (240, 90)
    rue, ru = cand(d, "rue"), cand(d, "ru")
    assert (rue["gain"], rue["max_regret"], rue["admitted_by"], rue["sum"], rue["worst"]) == (2, 40, "majority", 220, 70)
    assert (ru["gain"], ru["max_regret"], ru["admitted_by"], ru["sum"], ru["worst"]) == (2, 50, "majority", 220, 80)
    assert (d["sum_pick"], d["worst_pick"]) == (220, 70)


def test_row4_sibling_equal_total_candidate_loses_to_a_lower_total():
    eu = {"eu": 30, "rue": 70, "ru": 80}
    ru = {"ru": 40, "rue": 45, "eu": 90}
    members = [seat("eu1", "eu", eu), seat("eu2", "eu", eu),
               seat("ru1", "ru", ru), seat("ru2", "ru", ru)]
    pick, why, d = run(members)
    assert (d["baseline"], d["tie"]) == ("eu", "lexical")
    assert (pick, why) == ("rue", "majority")
    # ru: equal total (240 = 240) with a lower worst (80 < 90) — an admitted
    # departure on its own, but rue's strictly lower total ranks first.
    assert (cand(d, "ru")["sum"], cand(d, "ru")["worst"], d["sum_b"], d["worst_b"]) == (240, 80, 240, 90)
    assert (cand(d, "rue")["sum"], d["sum_pick"]) == (230, 230)


def test_row5_codex_c1_single_huge_gain_cannot_drag_three():
    pick, why, d = run(row5_codex_c1())
    assert (pick, why) == ("us", "baseline")
    eu = cand(d, "eu")
    assert (eu["gain"], eu["max_regret"], eu["admitted_by"]) == (1, 40, None)
    assert (eu["sum"], d["sum_b"]) == (365, 530)   # would have moved it without the gate


def test_row6_codex_c2_lexical_anchor_then_the_sum_moves_it_to_us():
    pick, why, d = run(row6_codex_c2())
    # Tie us/eu, both peer-measured -> the anchor is eu (lexical). From eu
    # the K counterexample reads the other way round: us is a majority move
    # (C/D gain 290 each; A/B pay 20, inside the bound too) with the far
    # lower total, so the room goes to us — and eu is refused as before.
    assert (d["baseline"], d["tie"]) == ("eu", "lexical")
    assert (pick, why) == ("us", "majority")
    us = cand(d, "us")
    assert (us["gain"], us["max_regret"], us["admitted_by"], us["sum"], d["sum_b"]) == (2, 20, "majority", 220, 760)


def test_row7_map_lacking_baseline_fails_quorum():
    pick, why, d = run(row7_missing_baseline(), legacy="us")
    assert (pick, why) == ("us", "quorum")
    assert [s["state"] for s in d["seats"]] == ["fresh", "fresh", "fresh", "missing_baseline"]
    assert d["seats"][3] == {"id": "d", "state": "missing_baseline", "cost_b": None, "cost_pick": None}
    assert d["candidates"] == [] and d["sum_b"] is None


def test_row8_shared_region_nobody_calls_home_wins_by_majority():
    pick, why, d = run(row8())
    assert (pick, why) == ("ussc", "majority")
    assert d["baseline"] == "us" and d["tie"] is None
    assert d["candidates"][0] == {"region": "ussc", "sum": 140, "worst": 35, "gain": 4,
                                  "max_regret": -25, "admitted_by": "majority"}
    assert cand(d, "usw")["admitted_by"] == "bounded"
    assert (d["sum_b"], d["sum_pick"], d["gain"], d["max_regret"]) == (240, 140, 4, -25)
    assert [s["cost_pick"] for s in d["seats"]] == [35, 35, 35, 35]


def test_sister_fixture_lower_worst_higher_sum_keeps_us():
    pick, why, d = run(sister())
    assert (pick, why) == ("us", "baseline")
    ussc = cand(d, "ussc")
    assert (ussc["gain"], ussc["max_regret"], ussc["admitted_by"]) == (1, 30, "bounded")
    assert (d["sum_b"], ussc["sum"]) == (250, 305)
    assert (d["worst_b"], ussc["worst"]) == (130, 95)


# ── Quorum ───────────────────────────────────────────────────────────────────

def test_stale_seat_fails_quorum():
    pick, why, d = run(row8(stale_last=True), legacy="us")
    assert (pick, why) == ("us", "quorum")
    assert [s["state"] for s in d["seats"]] == ["fresh", "fresh", "fresh", "stale"]
    assert d["seats"][3]["cost_b"] == 60          # the stale number is shown, not used


def test_exactly_max_age_is_still_fresh():
    members = row8()
    members[3]["measured_at"] = NOW - MAX_AGE
    assert run(members)[1] == "majority"
    members[3]["measured_at"] = NOW - MAX_AGE - 1
    assert run(members)[1] == "quorum"


def test_absent_seat_fails_quorum():
    members = row8()
    members[1] = seat("b", "us", None, age=None)
    pick, why, d = run(members, legacy="us")
    assert (pick, why) == ("us", "quorum")
    assert [s["state"] for s in d["seats"]] == ["fresh", "absent", "fresh", "fresh"]
    assert d["seats"][1] == {"id": "b", "state": "absent", "cost_b": None, "cost_pick": None}


def test_map_without_timestamp_is_stale_not_absent():
    members = row8()
    members[2]["measured_at"] = None
    _, why, d = run(members)
    assert why == "quorum" and d["seats"][2]["state"] == "stale"


def test_quorum_returns_the_baseline_not_the_legacy_pick():
    # Design v3 §8 / v4 step 2: a quorum failure yields B (mode of homes);
    # legacy_pick is only the answer when nobody has a home.
    pick, why, d = run(row8(stale_last=True), legacy="eu")
    assert (pick, why, d["baseline"]) == ("us", "quorum", "us")


def test_no_homes_falls_back_to_legacy_pick_as_the_baseline():
    m = {"us": 60, "ussc": 35}
    pick, why, d = run([seat("a", None, m), seat("b", "", m)], legacy="us")
    assert (d["baseline"], d["tie"]) == ("us", None)
    assert (pick, why) == ("ussc", "majority")     # the legacy baseline is measured, so the rule runs


def test_no_homes_legacy_baseline_must_still_be_measured():
    # With B = legacy_pick = "eu" and no map holding eu, quorum fails on
    # missing_baseline — the legacy answer stands, unmoved.
    m = {"us": 60, "ussc": 35}
    pick, why, d = run([seat("a", None, m), seat("b", None, m)], legacy="eu")
    assert (pick, why) == ("eu", "quorum")
    assert {s["state"] for s in d["seats"]} == {"missing_baseline"}


def test_empty_members_returns_legacy_pick_with_quorum():
    pick, why, d = run([], legacy="eu")
    assert (pick, why) == ("eu", "quorum")
    assert d["n"] == 0 and d["seats"] == [] and d["baseline"] == "eu"


# ── Robustness: never raises ─────────────────────────────────────────────────

def test_garbage_map_entries_are_dropped_not_fatal():
    garbage = {"us": "60", 5: 30, "eu": 99999, "ussc": True, "usw": 40.0, "ru": -1,
               "": 50, "rue": 0, "ok": 5000}
    members = [seat("a", "ok", garbage), seat("b", "ok", {"ok": 4999})]
    pick, why, d = run(members, live=("ok",))
    assert (pick, why) == ("ok", "baseline")
    assert d["seats"][0]["cost_b"] == 5000 and d["candidates"] == []


def test_garbage_map_leaving_nothing_is_absent():
    members = row8()
    members[0]["map"] = {"us": "60", "ussc": None}
    _, why, d = run(members)
    assert why == "quorum" and d["seats"][0]["state"] == "absent"
    members[0]["map"] = "us=60"
    _, why, d = run(members)
    assert why == "quorum" and d["seats"][0]["state"] == "absent"


def test_garbage_timestamp_makes_the_seat_stale():
    members = row8()
    members[0]["measured_at"] = "yesterday"
    _, why, d = run(members)
    assert why == "quorum" and d["seats"][0]["state"] == "stale"


def test_garbage_members_volumes_and_live_never_raise():
    members = row8() + ["not a seat", None]
    pick, why, d = run(members, volumes=None, live=None)
    assert why == "quorum" and [s["state"] for s in d["seats"]][-2:] == ["absent", "absent"]
    pick, why, d = run(row8(), volumes={"ussc": "lots"}, live=LIVE)
    assert (pick, why) == ("ussc", "majority")


def test_exception_inside_the_body_returns_legacy_with_error():
    pick, why, d = pick_region_for_group(object(), LIVE, VOLUMES, "lp")
    assert (pick, why) == ("lp", "error") and "error" in d
    pick, why, d = run(row8(), legacy="lp", margin_ms="twenty")
    assert (pick, why) == ("lp", "error") and "TypeError" in d["error"]


def test_default_now_is_wall_clock(monkeypatch):
    monkeypatch.setattr(region_pick.time, "time", lambda: NOW)
    assert pick_region_for_group(row8(), LIVE, VOLUMES, LEGACY)[0] == "ussc"
    monkeypatch.setattr(region_pick.time, "time", lambda: NOW + 1000)
    assert pick_region_for_group(row8(), LIVE, VOLUMES, LEGACY)[1] == "quorum"


# ── Determinism and invariance ───────────────────────────────────────────────

@pytest.mark.parametrize("fixture", [row2, row4, row8, sister, row6_codex_c2])
def test_verdict_is_invariant_under_member_order(fixture):
    base = run(fixture())
    for perm in itertools.permutations(fixture()):
        pick, why, d = run(list(perm))
        assert (pick, why, d["baseline"], d["tie"]) == (base[0], base[1], base[2]["baseline"], base[2]["tie"])
        assert [s["id"] for s in d["seats"]] == [m["id"] for m in perm]   # seats stay seat-ordered


def test_three_way_home_tie_is_lexical_when_a_map_lacks_a_candidate():
    m = {"us": 50, "eu": 50}                      # no "ru" measured anywhere
    members = [seat("a", "us", m), seat("b", "eu", m), seat("c", "ru", m)]
    pick, why, d = run(members)
    assert (d["baseline"], d["tie"]) == ("eu", "lexical")
    assert (pick, why) == ("eu", "baseline")


def test_tie_anchor_is_never_numeric_codex_c2_h1():
    # Three tied homes. usw has by far the lowest TOTAL (2001 vs 5020/5035)
    # because one seat is 1 ms from it and 5000 ms from everything else; the
    # old numeric tie-break made usw the baseline and the gate never judged
    # the 980/985 ms the other two would pay. The anchor is lexical (eu);
    # usw is then a departure a lone gainer cannot carry, and us — which
    # costs nobody anything — takes the room.
    members = [seat("A", "us", {"us": 10, "eu": 20, "usw": 1000}),
               seat("B", "eu", {"us": 10, "eu": 15, "usw": 1000}),
               seat("C", "usw", {"us": 5000, "eu": 5000, "usw": 1})]
    pick, why, d = run(members)
    assert (d["baseline"], d["tie"]) == ("eu", "lexical")
    assert (pick, why) == ("us", "bounded")
    usw, us = cand(d, "usw"), cand(d, "us")
    assert (usw["sum"], usw["gain"], usw["max_regret"], usw["admitted_by"]) == (2001, 1, 985, None)
    assert (us["sum"], us["gain"], us["max_regret"], us["admitted_by"]) == (5020, 0, 0, "bounded")


def test_tie_prefers_a_home_some_other_member_measured():
    # A names a home nobody else can reach; a tie with it falls to the home
    # the other seat's map corroborates, whatever the letters say.
    members = [seat("A", "aa", {"aa": 1, "us": 500}), seat("B", "us", {"us": 20, "eu": 100})]
    pick, why, d = run(members)
    assert (d["baseline"], d["tie"]) == ("us", "measured")
    assert (pick, why) == ("us", "baseline")
    # nobody measured anything: the filter has no evidence and the lexical bias stands
    members = [seat("A", "us", None, age=None), seat("B", "eu", None, age=None)]
    pick, why, d = run(members, legacy="usw")
    assert (d["baseline"], d["tie"], why) == ("eu", "lexical", "quorum")


def test_home_of_is_the_lowest_ping_code_after_cleaning():
    assert region_pick.home_of({"us": 60, "eu": 35}) == "eu"
    assert region_pick.home_of({"us": 50, "eu": 50}) == "eu"             # ties lexical
    assert region_pick.home_of({"us": 60, "xx": 0, "eu": "35"}) == "us"  # garbage entries dropped
    for empty in (None, {}, {"us": "60"}, "us=60", []):
        assert region_pick.home_of(empty) is None, empty


# ── R1 / R4 and the selection order ──────────────────────────────────────────

def test_r1_baseline_wins_an_exact_tie_even_against_a_busier_region():
    m = {"usw": 50, "us": 50}                     # us has 1000 volume, usw 300
    pick, why, d = run([seat("a", "usw", m), seat("b", "usw", m)])
    assert (pick, why) == ("usw", "baseline")
    assert cand(d, "us")["admitted_by"] == "bounded"


def test_equal_total_with_lower_worst_departs():
    members = [seat("a", "usw", {"usw": 40, "us": 50}), seat("b", "usw", {"usw": 60, "us": 50})]
    pick, why, d = run(members)
    assert (pick, why) == ("us", "bounded")
    assert (d["sum_b"], d["sum_pick"], d["worst_b"], d["worst_pick"]) == (100, 100, 60, 50)


def test_r4_bound_zero_still_moves_when_nobody_pays():
    m = {"us": 60, "ussc": 60}
    members = [seat("a", "us", m), seat("b", "us", m), seat("c", "us", m),
               seat("d", "us", {"us": 100, "ussc": 70})]
    pick, why, d = run(members, regret_ms=0)
    assert (pick, why) == ("ussc", "bounded")
    assert (cand(d, "ussc")["gain"], cand(d, "ussc")["max_regret"]) == (1, 0)


def test_volume_then_code_order_candidates_that_beat_the_baseline():
    m = {"eu": 100, "us": 60, "usw": 60}          # us and usw identical; us busier
    members = [seat("a", "eu", m), seat("b", "eu", m)]
    pick, why, d = run(members)
    assert (pick, why) == ("us", "majority")
    assert [c["region"] for c in d["candidates"]] == ["us", "usw"]
    vols = dict(VOLUMES, usw=5000)
    assert run(members, volumes=vols)[0] == "usw"
    vols["usw"] = vols["us"]
    assert run(members, volumes=vols)[0] == "us"   # lexical last


def test_majority_names_the_verdict_when_both_arms_pass():
    _, why, d = run(row8())
    assert why == "majority" and cand(d, "ussc")["max_regret"] <= 30


# ── Choosable set, live filter, small rooms ──────────────────────────────────

def test_candidate_must_be_live_and_in_every_map():
    m = {"us": 90, "hk": 20, "ussc": 40}
    members = [seat("a", "us", m), seat("b", "us", m), seat("c", "us", {"us": 90, "hk": 20})]
    pick, why, d = run(members)                   # hk: not live; ussc: missing from c
    assert (pick, why) == ("us", "baseline") and d["candidates"] == []
    assert run(members, live=LIVE + ("hk",))[0] == "hk"


def test_baseline_outside_live_regions_is_still_the_baseline():
    m = {"hk": 30, "us": 90}
    members = [seat("a", "hk", m), seat("b", "hk", m)]
    pick, why, d = run(members)
    assert (pick, why, d["baseline"]) == ("hk", "baseline", "hk")
    assert cand(d, "us")["admitted_by"] is None


def test_pair_one_gainer_is_a_majority():
    members = [seat("a", "us", {"us": 100, "ussc": 40}), seat("b", "us", {"us": 50, "ussc": 90})]
    pick, why, d = run(members)
    assert (pick, why) == ("ussc", "majority")
    assert (cand(d, "ussc")["gain"], cand(d, "ussc")["max_regret"]) == (1, 40)


def test_solo_goes_to_its_best_measured_live_region():
    pick, why, _ = run([seat("a", "us", {"us": 80, "eu": 40})])
    assert (pick, why) == ("eu", "majority")


def test_three_room_lone_far_seat_cannot_move_it():
    near = {"us": 30, "eu": 110}
    members = [seat("a", "us", near), seat("b", "us", near), seat("c", "eu", {"us": 120, "eu": 30})]
    pick, why, d = run(members)
    assert (pick, why) == ("us", "baseline")
    assert (cand(d, "eu")["gain"], cand(d, "eu")["max_regret"]) == (1, 80)


# ── Contract: detail keys and the disclosure ─────────────────────────────────

DETAIL_KEYS = {"baseline", "n", "sum_b", "sum_pick", "worst_b", "worst_pick", "gain",
               "max_regret", "candidates", "seats", "tie"}


@pytest.mark.parametrize("members", [row1(), row8(), row8(stale_last=True), []])
def test_detail_carries_every_documented_field(members):
    _, _, d = run(members)
    assert set(d) == DETAIL_KEYS
    for c in d["candidates"]:
        assert set(c) == {"region", "sum", "worst", "gain", "max_regret", "admitted_by"}
    for s in d["seats"]:
        assert set(s) == {"id", "state", "cost_b", "cost_pick"}


def test_docstring_carries_both_disclosure_sentences_together():
    doc = " ".join(pick_region_for_group.__doc__.split())
    first = ("A move needs either half the room to gain 20 ms or nobody to lose more "
             "than 30 ms, and then happens only if it lowers the room's total ping, or keeps "
             "the total and lowers its worst ping — so a majority can move a minority, but "
             "never by more than the majority gains.")
    second = "The room may be a region no member calls home."
    assert first in doc and second in doc
    assert doc.index(second) - (doc.index(first) + len(first)) <= 1   # side by side
    assert "Outcomes the rule can never reach" in doc


def test_knobs_default_off():
    assert (region_pick._MAJORITY_STRICT, region_pick._SKIP_QUORUM, region_pick._SELECT_BY_WORST) \
        == (False, False, False)


# ── Mutation controls (each a real negative control with its default twin) ───

def test_m1_strict_majority_arm_flips_a_majority_only_fixture(monkeypatch):
    members = row2(west_us=100)                   # ussc: gain 2 of 4, regret 45; sum 250 < 260
    assert run(members)[:2] == ("ussc", "majority")
    monkeypatch.setattr(region_pick, "_MAJORITY_STRICT", True)
    pick, why, d = run(members)
    assert (pick, why) == ("us", "baseline")
    assert cand(d, "ussc")["admitted_by"] is None


def test_m1_companion_last_row_is_not_a_control_for_the_strict_arm(monkeypatch):
    # gain 4 of 4 satisfies `2*gain > N` too, and ussc is bounded-admitted
    # anyway (regret -25): the spec's claim that `>` fails this row is false.
    monkeypatch.setattr(region_pick, "_MAJORITY_STRICT", True)
    pick, why, _ = run(row8())
    assert (pick, why) == ("ussc", "majority")


def bounded_only():
    """3 near + 1 far where the compromise costs the near seats 20 each and
    only the far seat gains: admitted by the bound alone, never by count."""
    near = {"us": 30, "ussc": 50}
    return [seat("a", "us", near), seat("b", "us", near), seat("c", "us", near),
            seat("d", "ussc", {"us": 200, "ussc": 60})]


def test_m2_regret_bound_zero_flips_the_bounded_only_fixture():
    pick, why, d = run(bounded_only())
    assert (pick, why) == ("ussc", "bounded")
    assert (cand(d, "ussc")["gain"], cand(d, "ussc")["max_regret"], d["sum_b"], d["sum_pick"]) == (1, 20, 290, 210)
    pick, why, d = run(bounded_only(), regret_ms=0)
    assert (pick, why) == ("us", "baseline")
    assert cand(d, "ussc")["admitted_by"] is None


def test_m3_dropping_the_quorum_guard_moves_a_room_with_a_stale_seat(monkeypatch):
    members = row8(stale_last=True)
    assert run(members, legacy="us")[:2] == ("us", "quorum")
    monkeypatch.setattr(region_pick, "_SKIP_QUORUM", True)
    pick, why, d = run(members, legacy="us")
    assert why != "quorum"
    assert (pick, why) == ("ussc", "majority")    # the stale map was used to move the room
    assert d["seats"][3]["state"] == "stale"


def test_m4_selecting_by_worst_flips_the_sister_fixture(monkeypatch):
    assert run(sister())[:2] == ("us", "baseline")
    monkeypatch.setattr(region_pick, "_SELECT_BY_WORST", True)
    pick, why, d = run(sister())
    assert (pick, why) == ("ussc", "bounded")
    assert (d["worst_b"], d["worst_pick"], d["sum_b"], d["sum_pick"]) == (130, 95, 250, 305)
