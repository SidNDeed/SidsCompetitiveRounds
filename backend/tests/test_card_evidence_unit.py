"""Card draw evidence, the parts that need no database: the client's fixtures
accepted byte for byte, the record and census checks, the deal profile, every
measure's NOT-RUN dependency with its control, the held-card rule per
generation source, the pickers, the rarity expectation against a sampler,
Same Cards against the series rule, pairing, the card scope of the review
rules over SYNTHETIC revisions, the statement scan and the health word.

Judging is not tested here: which measure opens a review item, at what value
and with what words lives in a rules revision outside the repository."""

import copy
import hashlib
import inspect
import json
import os
import random
import re
import sys
import textwrap

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import card_evidence as ce  # noqa: E402
import card_measures as cm  # noqa: E402
import card_read_dispositions as crdisp  # noqa: E402
import card_read_dynamic as crd  # noqa: E402
import card_read_sets as crs  # noqa: E402
import card_revision_kit as k  # noqa: E402
import review_rules as rr  # noqa: E402
import seat_evidence as se  # noqa: E402

API = os.path.normpath(os.path.join(HERE, "..", "api"))
BACKEND = os.path.normpath(os.path.join(HERE, ".."))

# The client lane's generated files (tools/tests/card-draw-client/fixtures at
# the client lane's fixture tip), by sha256: the copies here are those bytes.
FIXTURE_SHA = {
    "cases.txt": "eeb75853e7a5a8ea318a2b473ade1a0fc5a12144a597a4352007c6fd8d9e8412",
    "cut_left.envelope.json": "1d68b12a84f79f3adf6ca7fd198c220952a56fe15f3b59f7bae91dbc18b5769f",
    "cut_left.input.json": "aeb0288ebb42f2f83c59074e3a3ea60aeee387a2d6873721e3748c57026fd900",
    "cut_left.record.txt": "aeb0288ebb42f2f83c59074e3a3ea60aeee387a2d6873721e3748c57026fd900",
    "first_phase_lost.envelope.json": "8f496b32f9e666b357c5a9d182e44c675c678ea3c084763808097dd1f13eb672",
    "first_phase_lost.input.json": "6cbbb405666868f6a57e946a6f9f7aa8d80f1d3ac779c5cb5f09115773214f83",
    "first_phase_lost.record.txt": "6cbbb405666868f6a57e946a6f9f7aa8d80f1d3ac779c5cb5f09115773214f83",
    "full_game.envelope.json": "7ec88ca748d7ac2dbb45693fb8de8760ab7c1011bdf4f8c3e5d6a2026f65f299",
    "full_game.input.json": "34261b71da6ebe645c52c51863db73b2aac01acb674e18b22d3964d25b57df82",
    "full_game.record.txt": "34261b71da6ebe645c52c51863db73b2aac01acb674e18b22d3964d25b57df82",
    "game2_held_samecards.envelope.json": "c9528a22e1f360cadcb90b275eb3590d629e4d24da25e57ce4b62e1f6e02efe9",
    "game2_held_samecards.input.json": "e6392327e29bfe1825c8dc988687d4a95bb7f19d9dfd91f805ae2f99e5c6bcf7",
    "game2_held_samecards.record.txt": "e6392327e29bfe1825c8dc988687d4a95bb7f19d9dfd91f805ae2f99e5c6bcf7",
    "over_cap.envelope.json": "79f94c27841f8e9c17e9eea5384881408e0d41d3237a42686edcf2a6cddd0557",
    "over_cap.input.json": "365b8fe1714c38b51bef730fe488e8972546f44052590bbd15957e6c5b32117d",
    "over_cap.record.txt": "4fdf88fd89e03839c74726d6bc2c8b3392944c8e7f071e6bebd53e1d1f04dacf",
}


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


# -- the client's fixtures, byte for byte ------------------------------------------

def test_the_fixtures_are_the_client_files():
    names = sorted(os.listdir(k.FIX))
    assert names == sorted(FIXTURE_SHA)
    for n in names:
        with open(os.path.join(k.FIX, n), "rb") as f:
            assert hashlib.sha256(f.read()).hexdigest() == FIXTURE_SHA[n], n
    assert k.cases() == ["full_game", "game2_held_samecards", "cut_left", "over_cap", "first_phase_lost"]


@pytest.mark.parametrize("name", ["full_game", "game2_held_samecards", "cut_left", "over_cap",
                                  "first_phase_lost"])
def test_each_fixture_parses_budgets_and_verifies(name):
    text = k.fixture(name, "record.txt").decode("ascii")
    assert k.budget(k.fixture_input(name)) == text           # the server's own budget of the input
    env = ce.parse_envelope(json.loads(k.fixture(name, "envelope.json")))
    assert env["record_text"] == text
    assert ce.verify_sig(k.FIXTURE_KEY, env)
    assert not ce.verify_sig(k.KEY, env)                     # control: another key
    rec = ce.parse_record(env)
    assert cm.dumps(rec) == text


def test_the_over_cap_fixture_is_trimmed_and_the_signature_covers_every_byte():
    rec = k.fixture_record("over_cap")
    assert len(k.fixture(name="over_cap", part="record.txt")) <= cm.W["record_max_bytes"]
    assert rec["omit"]["hd"] > 0 and rec["omit"]["ap"] > 0
    env = json.loads(k.fixture("over_cap", "envelope.json"))
    env["record"] = env["record"].replace('"g":3', '"g":4')
    assert not ce.verify_sig(k.FIXTURE_KEY, ce.parse_envelope(env))


def test_the_signed_string_is_its_own_and_not_the_seat_string():
    env = ce.parse_envelope(json.loads(k.fixture("full_game", "envelope.json")))
    assert ce.record_canonical(env).startswith("card-evidence:v1:")
    assert se.record_canonical(env) != ce.record_canonical(env)
    assert not se.verify_sig(k.FIXTURE_KEY, env)              # a seat signature is not a card one


# -- the envelope and record checks ------------------------------------------------

def _env(**over):
    e = json.loads(k.fixture("full_game", "envelope.json"))
    e.update(over)
    return e


def test_envelope_refusals_and_control():
    ce.parse_envelope(_env())
    cases = [(_env(contract=1), 400, "contract"),
             (_env(record="x" * (cm.W["record_max_bytes"] + 1)), 413, "record_bytes"),
             (_env(record="{\"a\":\t1}"), 422, "record_ascii"),
             (_env(sig="Z" * 64), 400, "sig"),
             (_env(attach_key="other_r5"), 400, "attach_key")]
    for body, status, field in cases:
        with pytest.raises(se.EvidenceRefused) as ei:
            ce.parse_envelope(body)
        assert (ei.value.status, ei.value.field) == (status, field), field


def _refused(rec):
    with pytest.raises(cm.Refusal) as ei:
        cm.check_record(rec)
    return ei.value.field


def test_record_refusals_each_with_its_control():
    base = k.fixture_record("full_game")
    cm.check_record(base)                                       # control
    r = copy.deepcopy(base)
    r["pool"] = [12, "", "ok"]
    assert _refused(r) == "pool"                                # "" digest only with not_run
    r["pool"] = [12, "", "not_run"]
    cm.check_record(r)
    r = copy.deepcopy(base)
    r["prof"][1] = "no_location"                                # a hash with a not-ok state
    assert _refused(r) == "prof"
    r = copy.deepcopy(base)
    r["hd"][0][6] = [0, 1, 2, 3, 77]                            # an index the cards do not name
    assert _refused(r) == "cards_named"
    r = copy.deepcopy(base)
    r["inc"] = cm.INC["first"]                                  # first phase lost but po kept
    assert _refused(r) == "inc_first"
    r["po"], r["held0"] = [], [None, None]
    cm.check_record(r)
    r = copy.deepcopy(base)
    r = {kk: r[kk] for kk in reversed(list(r))}
    assert _refused(r) == "key_order"
    r = copy.deepcopy(base)
    r["extra"] = 1
    assert _refused(r) == "extra"
    r = copy.deepcopy(base)
    r["cards"][1], r["cards"][2] = r["cards"][2], r["cards"][1]
    assert _refused(r) == "cards"                               # not ascending
    r = copy.deepcopy(base)
    r["hd"][0] = r["hd"][0][:-1]
    assert _refused(r) == "hd"
    with pytest.raises(cm.Refusal):
        cm.parse_record_text(k.fixture("full_game", "record.txt").decode().replace('"g":1', '"g":1.0'))


# -- the census and its registration -------------------------------------------------

def test_a_census_dump_is_accepted_only_whole():
    d = k.census_dump(k.census_cards(12))
    c = cm.census_from_dump(d)
    assert c.digest == hashlib.sha256(d["census_text"].encode()).hexdigest() and c.count == 12
    bad = dict(d, digest="0" * 64)
    with pytest.raises(cm.Refusal) as ei:
        cm.census_from_dump(bad)
    assert ei.value.field == "digest"
    spaced = d["census_text"].replace(",", ", ", 1)
    with pytest.raises(cm.Refusal) as ei:
        cm.census_from_dump(dict(d, census_text=spaced, digest=cm.census_digest(spaced)))
    assert ei.value.field == "census_canonical"                 # not its own canonical form
    with pytest.raises(cm.Refusal) as ei:
        cm.census_from_dump(dict(d, card_count=11))
    assert ei.value.field == "card_count"
    with pytest.raises(cm.Refusal) as ei:
        cm.census_from_dump(k.census_dump(k.census_cards(3), state="read_failed"))
    assert ei.value.field == "game_dll"


def test_the_deal_profile_moves_with_each_identity_part():
    rec = k.fixture_record("full_game")
    base = cm.deal_profile(rec)
    assert len(base) == cm.W["hex_len"]
    for i in range(len(rec["prof"])):
        r = copy.deepcopy(rec)
        r["prof"][i] = r["prof"][i] + "x" if r["prof"][i] != "ok" else "read_failed"
        assert cm.deal_profile(r) != base, i
    r = copy.deepcopy(rec)
    r["pool"][1] = "b" * 64
    assert cm.deal_profile(r) != base
    r = copy.deepcopy(rec)
    r["ns"] = 6
    assert cm.deal_profile(r) != base
    r = copy.deepcopy(rec)
    r["hd"] = []                                                 # control: not an identity part
    assert cm.deal_profile(r) == base


# -- NOT-RUN per dependency (CD-P1, M3, CD-A16) ------------------------------------

def _full_on(census=None, **edit):
    rec = k.fixture_record("full_game")
    c = census or k.fixture_census("full_game")
    rec = k.on_census(rec, c)
    for path, v in edit.items():
        rec[path] = v
    return rec, c


def _hand0(rec, c, weights=k.WEIGHTS, registry=True):
    return k.hand(k.view([("a", "b", rec)], [c] if registry else [], None, weights), 0)


def test_pool_dependent_measures_run_only_with_the_records_own_registered_census():
    rec, c = _full_on()
    h = _hand0(rec, c)
    assert h["b4.hand.notpool"] == 0 and h["b4.hand.heldrej"] == 0 and h["b4.hand.eligible"] == 1
    assert _hand0(rec, c, registry=False)["b4.hand.notpool"] is None      # unregistered
    for state in ("collision", "changed"):
        r = copy.deepcopy(rec)
        r["pool"][2] = state
        assert _hand0(r, c)["b4.hand.notpool"] is None, state
    r = copy.deepcopy(rec)
    r["prof"][0], r["prof"][1] = "", "read_failed"                         # game hash unread
    assert _hand0(r, c)["b4.hand.notpool"] is None
    other = k.fixture_census("full_game")
    other = k.census(other.cards, game_sha="e" * 64)                        # another game build
    r = k.on_census(k.fixture_record("full_game"), other)
    assert _hand0(r, other)["b4.hand.notpool"] is None
    r = copy.deepcopy(rec)
    r["prof"][7] = "cd-sem:9"                                               # unknown semantics
    assert _hand0(r, c)["b4.hand.notpool"] is None and _hand0(r, c)["b4.hand.size"] is None


def test_lost_or_faulted_collectors_make_every_dependent_measure_unknown():
    rec, c = _full_on()
    for bit in (cm.INC["lost"], cm.INC["fault"]):
        r = copy.deepcopy(rec)
        r["inc"] = bit
        h = _hand0(r, c)
        assert h["b4.hand.dup"] is None and h["b4.hand.size"] is None and h["b4.pick.slot"] is None
        assert h["b4.hand.notrun"] == len(cm.HAND_RULES)
    assert _hand0(rec, c)["b4.hand.notrun"] == 0                           # control


def test_a_hand_cut_by_the_slot_cap_is_unknown_for_slot_measures():
    rec, c = _full_on()
    r = copy.deepcopy(rec)
    r["hd"][0][5] = 6                                                       # n 6, five kept
    r["omit"]["sl"] = 1
    h = _hand0(r, c)
    assert h["b4.hand.unres"] is None and h["b4.hand.dup"] is None and h["b4.hand.heldrej"] is None
    assert h["b4.hand.size"] == 1                                           # n against ns still runs


def test_held_set_inputs_trimmed_or_inconsistent_are_unknown():
    rec, c = _full_on()
    h3 = k.hand(k.view([("a", "b", rec)], [c], None, k.WEIGHTS), 3)
    assert h3["b4.hand.heldrej"] == 0
    for edit in ("omit_ap", "omit_held", "hn", "an", "first"):
        r = copy.deepcopy(rec)
        if edit == "omit_ap":
            r["omit"]["ap"] = 1
        elif edit == "omit_held":
            r["omit"]["held0"] = [1, 0]
        elif edit == "hn":
            r["hd"][3][17] = 4                                              # held count disagrees
        elif edit == "an":
            r["hd"][3][4] = 9                                               # more applications than listed
        else:
            r["inc"], r["po"], r["held0"] = cm.INC["first"], [], [None, None]
        h = k.hand(k.view([("a", "b", r)], [c], None, k.WEIGHTS), 3)
        assert h["b4.hand.heldrej"] is None, edit


def test_the_unregistered_digest_is_stored_as_a_fact_and_reads_not_run():
    rec, c = _full_on()
    v = k.view([("a", "b", rec)], [], None, k.WEIGHTS)
    assert v["records"][0][0]["b4.rec.unreg"] == 1 and v["records"][0][0]["b4.rec.census"] == 0
    v = k.view([("a", "b", rec)], [c], None, k.WEIGHTS)
    assert v["records"][0][0]["b4.rec.unreg"] == 0 and v["records"][0][0]["b4.rec.census"] == 1


# -- the refusal examples (r5:143) --------------------------------------------------

def test_a_repeated_slot_reads_dup_one_and_its_control_zero():
    rec, c = _full_on()
    assert _hand0(rec, c)["b4.hand.dup"] == 0
    r = copy.deepcopy(rec)
    r["hd"][0][6] = [0, 1, 2, 3, 0]
    assert _hand0(r, c)["b4.hand.dup"] == 1


# -- the held-card rule per generation source (M1, M2) ------------------------------

def _ph3(census):
    rec = k.on_census(k.fixture_record("full_game"), census)
    return k.hand(k.view([("a", "b", rec)], [census], None, k.WEIGHTS), 3)["b4.hand.heldrej"]


def test_vanilla_held_rule_slot_zero_is_exempt_slot_one_is_not():
    # phase 3, own hand: slots [4, 6, 8, 10, 2], held [2] (an 1 application)
    assert _ph3(k.fixture_census("full_game")) == 0                                     # control
    assert _ph3(k.fixture_census("full_game", cats={4: ["X"]}, black={2: ["X"]})) == 0  # slot 0
    assert _ph3(k.fixture_census("full_game", cats={6: ["X"]}, black={2: ["X"]})) == 1  # slot 1
    assert _ph3(k.fixture_census("full_game", multi={2: 0})) == 1                       # same name held
    assert _ph3(k.fixture_census("full_game", cats={6: [None, "X"]}, black={2: [None, "Y"]})) == 0


def test_the_gun_lock_clause_reads_the_recorded_bit():
    c = k.fixture_census("full_game", lock={6: 1})
    rec = k.on_census(k.fixture_record("full_game"), c)
    assert k.hand(k.view([("a", "b", rec)], [c]), 3)["b4.hand.heldrej"] == 0           # gl 0
    rec["hd"][3][15] = 1
    assert k.hand(k.view([("a", "b", rec)], [c]), 3)["b4.hand.heldrej"] == 1
    rec["hd"][3][15] = -1
    assert k.hand(k.view([("a", "b", rec)], [c]), 3)["b4.hand.heldrej"] is None


def test_engine_opening_is_exempt_and_engine_later_applies_on_every_slot():
    # game2: phase 1 own hand engine opening (gen 1), phase 2 engine later (gen 2,
    # slots 0, 2, 3 engine-served), held [3, 5, 1] at phase 2
    g2 = k.fixture_record("game2_held_samecards")

    def h(census, phase):
        rec = k.on_census(g2, census)
        return k.hand(k.view([("a", "b", rec)], [census]), phase)["b4.hand.heldrej"]
    base = k.fixture_census("game2_held_samecards")
    assert h(base, 1) == 0 and h(base, 2) == 0
    opening = k.fixture_census("game2_held_samecards", cats={1: ["X"]}, black={3: ["X"]})
    assert h(opening, 1) == 0                                   # opening draw: no held check
    opening1 = k.fixture_census("game2_held_samecards", cats={2: ["X"]}, black={3: ["X"]})
    assert h(opening1, 1) == 0                                  # ... on a slot after the first too
    assert h(k.fixture_census("game2_held_samecards", cats={9: ["X"]}, black={3: ["X"]}), 2) == 1  # control
    later0 = k.fixture_census("game2_held_samecards", cats={8: ["X"]}, black={3: ["X"]})
    assert h(later0, 2) == 1                                    # engine slot 0 is checked
    # a candidate named as a held card, not allowMultiple: refused on a vanilla
    # slot (slot 1, card 9), not on an engine-later slot (slot 0, card 8)
    def named(ix):
        census = k.fixture_census("game2_held_samecards", multi={ix: 0}, names={ix: "Card3"})
        rec = k.on_census(k.renamed(g2, {ix: "Card3"}), census)
        return k.hand(k.view([("a", "b", rec)], [census]), 2)["b4.hand.heldrej"]
    assert named(8) == 0 and named(9) == 1


def test_a_measured_hand_reads_the_dealers_own_source_or_the_series_rule():
    full = k.fixture_record("full_game")
    c = k.fixture_census("full_game")
    rec = k.on_census(full, c)
    v = k.view([("a", "b", rec)], [c], None, k.WEIGHTS)
    assert k.hand(v, 1)["b4.hand.heldrej"] is None              # unknown source: not run
    v = k.view([("a", "b", rec)], [c], "off", k.WEIGHTS)
    assert k.hand(v, 1)["b4.hand.heldrej"] == 0                 # series rule off: vanilla
    v = k.view([("a", "b", rec)], [c], "on", k.WEIGHTS)
    assert k.hand(v, 1)["b4.hand.heldrej"] is None


# -- the pickers (M7) ---------------------------------------------------------------

def test_opening_pickers_against_po_and_later_ones_against_rounds():
    rec = k.fixture_record("full_game")
    v = k.view([("a", "b", rec)])
    assert [r["b4.ph.picker"] for r, _m in v["phases"]] == [0, 0, 0, 0]
    r = copy.deepcopy(rec)
    r["po"] = [1, 0]
    assert [x["b4.ph.picker"] for x, _m in k.view([("a", "b", r)])["phases"]][:2] == [1, 1]
    r = copy.deepcopy(rec)
    r["ph"][2][1] = 0                                           # the round winner picking
    assert [x["b4.ph.picker"] for x, _m in k.view([("a", "b", r)])["phases"]][2] == 1
    r = copy.deepcopy(rec)
    r["inc"], r["po"], r["held0"] = cm.INC["first"], [], [None, None]
    assert [x["b4.ph.picker"] for x, _m in k.view([("a", "b", r)])["phases"]][:2] == [None, None]


# -- the rarity expectation against a sampler (CD-A11, L1) --------------------------

def _sample_hand(census, held, ns, weights, rng):
    """The game's own vanilla draw, written independently: draw a card in
    proportion to its rarity's weight, redraw while it is already in the hand
    or, from the second slot on, a held card refuses it."""
    cards = census.cards
    w = [weights[cm.RARITIES[c[1]]] for c in cards]
    hand = []
    for j in range(ns):
        while True:
            ix = rng.choices(range(len(cards)), weights=w)[0]
            if ix in hand:
                continue
            if j > 0:
                cats = {x for x in (cards[ix][3] or []) if x is not None}
                if any(b in cats for h in held for b in (cards[h][4] or []) if b is not None):
                    continue
                if not cards[ix][2] and any(cards[h][0] == cards[ix][0] for h in held):
                    continue
            break
        hand.append(ix)
    return hand


def _moments(census, held, weights_true, weights_model, n=3000, seed=7):
    rng = random.Random(seed)
    resid = [0.0] * len(cm.RARITIES)
    sq = [0.0] * len(cm.RARITIES)
    var = [0.0] * len(cm.RARITIES)
    for _ in range(n):
        sl = _sample_hand(census, held, census.slots, weights_true, rng)
        obs, exp, v = cm.expectation(census, sl, held, 0, weights_model)
        for r in range(len(cm.RARITIES)):
            resid[r] += obs[r] - exp[r]
            sq[r] += (obs[r] - exp[r]) ** 2
            var[r] += v[r]
    return [x / n for x in resid], [x / n for x in sq], [x / n for x in var]


def test_the_expectation_matches_the_sampler_with_the_rejection_rule():
    census = k.census(k.census_cards(12, multi={1: 0}, cats={4: ["X"], 7: ["X"]}, black={1: ["X"]}))
    held = [1]
    mean, sq, var = _moments(census, held, k.WEIGHTS, k.WEIGHTS)
    for r in range(len(cm.RARITIES)):
        assert abs(mean[r]) < 0.06, (r, mean)
        assert abs(sq[r] - var[r]) < 0.08 * max(var[r], 0.1), (r, sq, var)


def _hand_break(edit, census_attrs=None, weights=k.WEIGHTS):
    """Hand 0 of the full game after `edit(entry, rec)`: its row, and whether
    the worker would write a card_hand_outside row for it."""
    c = k.fixture_census("full_game", **(census_attrs or {}))
    rec = k.on_census(k.fixture_record("full_game"), c)
    edit(rec["hd"][0], rec)
    v = k.view([("a", "b", rec)], [c], "off", weights)
    row = v["hands"][0][0]
    return row, bool(ce._nonzero(row, ce._HAND_KEYS))


def _phase_break(edit):
    rec = k.fixture_record("full_game")
    edit(rec["ph"][0], rec)
    row = k.view([("a", "b", rec)])["phases"][0][0]
    return row, bool(ce._nonzero(row, ce._PHASE_KEYS))


def _set(i, value):
    def edit(e, _rec):
        e[i] = value(e) if callable(value) else value
    return edit


HAND_BREAKS = [                       # (rule, measure, the edit of hand 0, census overrides, weights)
    ("R1", "b4.hand.size", _set(5, lambda e: e[5] + 1), None, k.WEIGHTS),
    ("R2", "b4.hand.notpool", lambda e, r: None, "rename", k.WEIGHTS),
    ("R2", "b4.hand.unres", _set(6, lambda e: [e[6][0], -1] + e[6][2:]), None, k.WEIGHTS),
    ("R3", "b4.hand.dup", _set(6, lambda e: [e[6][0], e[6][0]] + e[6][2:]), None, k.WEIGHTS),
    ("R7", "b4.hand.spx", _set(7, lambda e: e[7] + 1), None, k.WEIGHTS),
    ("R7", "b4.hand.spo", _set(8, lambda e: list(reversed(e[6]))), None, k.WEIGHTS),
    ("R8", "b4.pick.out", _set(10, -1), None, k.WEIGHTS),
    ("R8", "b4.pick.slot", _set(9, lambda e: (e[10] + 1) % len(e[6])), None, k.WEIGHTS),
    ("R8", "b4.pick.who", _set(3, lambda e: 1 - e[2]), None, k.WEIGHTS),
    ("R9", "b4.hand.w0", lambda e, r: None, None, "zero"),
]


@pytest.mark.parametrize("rule,measure,edit,census,weights", HAND_BREAKS,
                         ids=[b[0] + "-" + b[1] for b in HAND_BREAKS])
def test_each_rule_breaking_hand_reads_one_and_writes_a_row_its_control_neither(
        rule, measure, edit, census, weights):
    control, control_row = _hand_break(lambda e, r: None)
    assert control[measure] == 0 and not control_row, (rule, measure, control[measure])
    attrs = None
    if census == "rename":
        first = k.fixture_record("full_game")["hd"][0][6][0]
        attrs = {"names": {first: "SomeOtherCard"}}
    if weights == "zero":
        rar = k.fixture_census("full_game").cards[k.fixture_record("full_game")["hd"][0][6][0]][1]
        weights = dict(k.WEIGHTS, **{cm.RARITIES[rar]: 0})
    broken, broken_row = _hand_break(edit, attrs, weights)
    assert broken[measure] is not None and broken[measure] >= 1 and broken_row, (rule, measure, broken[measure])


PHASE_BREAKS = [
    ("R5", "b4.ph.dvp", _set(5, lambda e: e[2] + 1)),
    ("R5", "b4.ph.notdone", _set(6, 0)),
]


@pytest.mark.parametrize("rule,measure,edit", PHASE_BREAKS, ids=[b[0] + "-" + b[1] for b in PHASE_BREAKS])
def test_each_phase_rule_breaking_phase_reads_one_and_writes_a_row_its_control_neither(rule, measure, edit):
    control, control_row = _phase_break(lambda e, r: None)
    assert control[measure] == 0 and not control_row, (rule, measure, control[measure])
    broken, broken_row = _phase_break(edit)
    assert broken[measure] is not None and broken[measure] >= 1 and broken_row, (rule, measure, broken[measure])


def test_the_expectation_equals_hand_computed_values():
    # three cards, one per rarity, synthetic weights; hand [0, 1], nothing held
    census = k.census(k.census_cards(3))
    w = [k.WEIGHTS[r] for r in cm.RARITIES]
    p0 = [x / sum(w) for x in w]                                  # slot 0: the whole pool
    p1 = [0.0, w[1] / (w[1] + w[2]), w[2] / (w[1] + w[2])]        # slot 1: card 0 drawn already
    obs, exp, var = cm.expectation(census, [0, 1], [], 0, k.WEIGHTS)
    assert obs == [1, 1, 0]
    for r in range(len(cm.RARITIES)):
        assert abs(exp[r] - (p0[r] + p1[r])) < 1e-12
        assert abs(var[r] - (p0[r] * (1 - p0[r]) + p1[r] * (1 - p1[r]))) < 1e-12
    # control: a held card whose blacklist names card 1's category takes card 1 out of slot 1
    held_census = k.census(k.census_cards(4, cats={1: ["X"]}, black={3: ["X"]}))
    _o, exp_h, _v = cm.expectation(held_census, [0, 2], [3], 0, k.WEIGHTS)
    _o, exp_n, _v = cm.expectation(held_census, [0, 2], [], 0, k.WEIGHTS)
    assert exp_h != exp_n


def test_an_over_weighted_model_does_not_match_the_sampler():
    census = k.census(k.census_cards(12, multi={1: 0}, cats={4: ["X"], 7: ["X"]}, black={1: ["X"]}))
    wrong = dict(k.WEIGHTS, rare=k.WEIGHTS["rare"] * 4)
    mean, _sq, _var = _moments(census, [1], k.WEIGHTS, wrong)
    assert mean[cm.RARITIES.index("rare")] < -0.2


def test_a_pool_with_an_unsupported_rarity_reads_not_run():
    c = k.fixture_census("full_game", rarity={5: 3})
    rec = k.on_census(k.fixture_record("full_game"), c)
    h = k.hand(k.view([("a", "b", rec)], [c], None, k.WEIGHTS), 0)
    assert h["b4.hand.w0"] is None and h["b4.hand.eligible"] == 0
    assert cm.expectation(c, [0, 1], [], 0, k.WEIGHTS) is None   # the measure's own guard, not only the view's
    assert cm.contributions(k.view([("a", "b", rec)], [c], None, k.WEIGHTS))[0]["hands"] == 0
    c = k.fixture_census("full_game")
    rec = k.on_census(k.fixture_record("full_game"), c)
    assert k.hand(k.view([("a", "b", rec)], [c], None, k.WEIGHTS), 0)["b4.hand.eligible"] == 1


def test_no_weights_means_no_expectation_and_no_contribution():
    rec, c = _full_on()
    v = k.view([("a", "b", rec)], [c], None, None)
    assert all(r["b4.hand.eligible"] == 0 for r, _m in v["hands"])
    assert cm.contributions(v) == []


def test_window_rows_are_counts_and_their_deviation():
    agg = {"games": 3, "hands": 4, "slots": 20, "notrun_hands": 1, "source": "self", "coverage": "one",
           "obs": [10, 6, 4], "exp": [12000000, 6000000, 2000000], "var": [4000000, 3000000, 1000000]}
    row = cm.window_row(agg)
    assert row["b4.rar.exp.common"] == 12 and row["b4.rar.dev.common"] == pytest.approx(-1.0)
    assert row["b4.rar.dev.rare"] == pytest.approx(2.0) and row["b4.rar.meas"] == 0
    agg["var"] = [0, 0, 0]
    assert cm.window_row(agg)["b4.rar.dev.common"] is None


# -- Same Cards against the series rule (CD-A13) -------------------------------------

def test_same_cards_rule_measures():
    g2 = k.fixture_record("game2_held_samecards")              # sc [1, 1], own shared slots
    v = k.view([("a", "b", g2)], [], "on")
    assert v["records"][0][0]["b4.sc.rule"] == 0
    v = k.view([("a", "b", g2)], [], "off")
    assert v["records"][0][0]["b4.sc.rule"] == 1                # the room stated a rule the series did not freeze
    assert v["game"]["b4.sc.norule"] > 0                         # shared slots under an off rule
    v = k.view([("a", "b", g2)], [], None)
    assert v["records"][0][0]["b4.sc.rule"] is None and v["game"]["b4.sc.norule"] is None
    full = k.fixture_record("full_game")                        # sc [0, 0], no shared slot
    assert k.view([("a", "b", full)], [], "off")["game"]["b4.sc.norule"] == 0




def test_two_records_pair_by_dealer_phase_deal_and_view():
    full = k.fixture_record("full_game")
    other = k.mirror(full)
    v = k.view([("a", "b", full), ("b", "a", other)])
    assert v["two"] and v["game"]["b4.pair.n"] == 4 and v["game"]["b4.pair.unpair"] == 0
    assert all(r["b4.pair.slot"] == 0 and r["b4.pair.pick"] == 0 for r, _m in v["pairs"])
    other["hd"][1][6] = [5, 6, 7, 8, 0]                          # one slot differs
    v = k.view([("a", "b", full), ("b", "a", other)])
    assert sorted(r["b4.pair.slot"] for r, _m in v["pairs"]) == [0, 0, 0, 1]
    other["hd"][1][14] = 9999                                    # another pick view: not a pair
    v = k.view([("a", "b", full), ("b", "a", other)])
    assert v["game"]["b4.pair.n"] == 3 and v["game"]["b4.pair.unpair"] == 1


def test_coverage_is_paired_only_when_both_records_name_each_other():
    full = k.fixture_record("full_game")
    c = k.fixture_census("full_game")
    rec = k.on_census(full, c)
    one = cm.contributions(k.view([("a", "b", rec)], [c], "off", k.WEIGHTS))
    two = cm.contributions(k.view([("a", "b", rec), ("b", "a", k.mirror(rec))], [c], "off", k.WEIGHTS))
    assert {x["coverage"] for x in one} == {"one"} and {x["coverage"] for x in two} == {"paired"}


# -- the card scope of the review rules (SYNTHETIC revisions) -----------------------

def test_a_card_revision_builds_loads_and_runs_its_card_cases(tmp_path):
    store, rev = k.build_card_revision(tmp_path)
    st = k.load(store, rev)
    assert rr.CARD_CORE in st.ruleset.core and len(st.ruleset.card_rules) == len(k.card_doc()["rules"])
    v = k.view([("a", "b", k.dup_record())])
    findings, notes, fired, errors = st.ruleset.evaluate_card(cm.card_subjects(v))
    assert fired == [k.ID_DUP] and errors == 0 and notes == []
    assert findings[0][1][0][1] == {"dup": 1, "phase": 0}


def test_a_revision_whose_card_cases_disagree_is_refused(tmp_path):
    bad = [k.card_case([("a", "b", k.dup_record())], [])]       # fires, but lists nothing
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, cases=bad)


def test_a_card_rule_on_another_scopes_subject_is_malformed(tmp_path):
    doc = k.card_doc()
    doc["rules"][0]["subject"] = "seat"
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc=doc)
    doc = k.card_doc()
    doc["rules"][0]["when"] = k.cmp(k.M("b4.ph.picker"), "gt", k.V(0.37))   # a phase measure on a hand rule
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc=doc, name="other")


def test_a_revision_without_card_rules_binds_no_card_core_and_refuses_card_cases(tmp_path):
    import review_testkit as tk
    store, rev = tk.build_revision(tmp_path)
    st = k.load(store, rev)
    assert rr.CARD_CORE not in st.ruleset.core and st.ruleset.card_rules == []
    with pytest.raises(rr.Refused):
        tk.build_revision(tmp_path, cases=tk.quiet_cases() + k.quiet_card_cases(), name="mixed")


def test_the_card_measures_join_the_bound_code_closure():
    assert "card_measures.py" in rr.CODE_REQUIRED
    assert "code/card_measures.py" in rr._code_files(rr.CODE_REQUIRED)


def test_the_vocabulary_has_every_measure_and_the_two_families():
    import review_measures as rm
    for subject, names in cm.MEASURES.items():
        for n in names:
            assert rm.REGISTRY[n].subject == subject and rm.REGISTRY[n].kind == "measure", n
    assert rm.REGISTRY[cm.WEIGHTS].data == list(cm.RARITIES)
    assert rm.REGISTRY[cm.WEIGHTS].args == cm.PROFILE_KEYED              # keyed by deal profile
    assert rm.REGISTRY[cm.WINDOW].data == [cm.WINDOW_KEY] and not rm.REGISTRY[cm.WINDOW].args
    v = k.view([("a", "b", k.fixture_record("full_game"))])
    for subject, rows in (("card.hand", v["hands"]), ("card.phase", v["phases"]),
                          ("card.record", v["records"]), ("card.game", [(v["game"], None)])):
        assert set(rows[0][0]) == set(cm.MEASURES[subject]), subject


# -- the statement scan (CD-A15) and the health word (CD-A17) -------------------------

PROTECTED = ("matches", "ranked_series", "players", "rating_history", "glicko_ratings",
             "glicko_ratings_2v2", "player_gold", "gold_ledger", "player_items", "match_cards",
             "card_offers", "player_achievements")
CARD_WRITES = {"card_evidence", "card_pool_registry", "card_games", "card_hand_outside",
               "card_phase_outside", "card_contrib", "card_player_daily", "seat_evidence_findings"}
_WRITE = re.compile(r"\b(?:INSERT\s+INTO|(?<!DO\s)(?<!FOR\s)UPDATE|DELETE\s+FROM"
                    r"|TRUNCATE(?:\s+TABLE)?|ALTER\s+TABLE)"
                    r"\s+(?:ONLY\s+)?([A-Za-z_][A-Za-z0-9_]*)")


def _written(source):
    import ast
    out = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.update(m.group(1).lower() for m in _WRITE.finditer(node.value))
    return out


def _main():
    import main
    return main


def test_no_card_statement_writes_a_match_rating_gold_or_card_offer_table():
    mods = _read(API, "card_evidence.py") + "\n" + _read(API, "card_measures.py")
    main = _main()
    routes = "\n\n".join(textwrap.dedent(inspect.getsource(fn)) for fn in (
        main.submit_card_evidence, main.admin_card_evidence, main.admin_register_card_census))
    written = _written(mods) | _written(routes)
    assert written <= CARD_WRITES, sorted(written - CARD_WRITES)
    assert not written & set(PROTECTED)
    assert _written(routes) == set()                            # the routes write through the module only
    assert _written('x = "UPDATE match_cards SET card_name = 1"') == {"match_cards"}   # control


def test_the_route_stores_only_card_evidence_and_the_registry_only_its_table():
    assert _written(inspect.getsource(ce.store_record)) == {"card_evidence"}
    assert _written(inspect.getsource(ce.register_census)) == {"card_pool_registry"}


def test_the_seven_field_match_signature_is_untouched():
    main = _main()
    src = inspect.getsource(main.verify_hmac)
    assert "card" not in src
    assert "card-evidence" not in _read(API, "seat_evidence.py")


def test_the_card_word_is_derived_from_the_routing_table(monkeypatch):
    main = _main()
    assert main._card_evidence_health_word() == 1
    kept = [r for r in main.app.router.routes
            if getattr(r, "endpoint", None) is not main.submit_card_evidence]
    monkeypatch.setattr(main.app.router, "routes", kept)
    assert main._card_evidence_health_word() == 0


def test_the_card_word_is_required_and_on_both_arms():
    import schemas
    f = schemas.HealthResponse.model_fields["card_evidence"]
    assert f.annotation is int and f.is_required()
    assert inspect.getsource(_main().health_check).count("card_evidence=_card_evidence_health_word()") == 2


def test_the_migration_seeds_only_the_card_switches_and_is_transactional():
    sql = _read(BACKEND, "sql", "370_card_evidence.sql")
    seeded = re.findall(r"\('([a-z_]+)',\s*'[01]'\)", sql)
    assert sorted(seeded) == sorted(ce.SWITCHES)
    assert "BEGIN;" in sql and "COMMIT;" in sql
    rb = _read(BACKEND, "sql", "rollback_370_card_evidence.sql")
    assert "BEGIN;" in rb and "COMMIT;" in rb and "card_evidence_seeded_keys k" in rb


def test_the_worker_pass_runs_the_card_pass_on_the_published_state():
    src = inspect.getsource(_main().review_worker_pass)
    assert "_cev.games_pass(session_factory, state)" in src
    assert "_cev.purge_pass(session_factory) if purge" in src


# == fix pass 1 =========================================================================

# -- M1: the coverage catalog; an omitted or capped dependency fails closed -----------

def _omit(rec, fact):
    """The record stating `fact` not whole: the flag alone, every list kept,
    so only the stated coverage differs from the base game."""
    r = copy.deepcopy(rec)
    if fact == "whole":
        r["inc"] |= cm.INC["lost"]
    elif fact == "first":
        r["inc"] |= cm.INC["first"]
    elif fact == cm.W["omit_pair"]:
        r["omit"][fact] = [1, 0]
    else:
        r["omit"][fact] = 1
    return r


def _picked(rec, role):
    """The record's picked card names of the player in `role`."""
    names = {c[0]: c[1] for c in rec["cards"]}
    return [names[e[6][e[9]]] for e in rec["hd"] if e[2] == role and e[9] >= 0]


def _scenario_full():
    """The full game paired with its mirror, Same Cards off, a report read."""
    rec = k.default_record()
    other = k.mirror(rec)
    return ([("a", "b", rec), ("b", "a", other)], [k.fixture_census("full_game")], "off",
            {"a": _picked(rec, 0), "b": _picked(rec, 1)})


def _scenario_shared():
    """Game 2 under Same Cards on, both seats holding the same own deals: the
    shared-deal measures run."""
    c = k.fixture_census("game2_held_samecards")
    g2 = k.on_census(k.fixture_record("game2_held_samecards"), c)
    return [("a", "b", g2), ("b", "a", copy.deepcopy(g2))], [c], "on", None


SCENARIOS = (_scenario_full, _scenario_shared)


def _scn_view(scn, edit_first=None):
    recs, reg, sc, report = scn()
    if edit_first is not None:
        s, o, r = recs[0]
        recs[0] = (s, o, edit_first(r))
    return k.view(recs, reg, sc, k.WEIGHTS, report)


def _rows_of_first(v, subject):
    """The rows of `subject` the first record's coverage governs: its own hand,
    phase and record rows; every pair and game row (they need the fact on
    every record of the game)."""
    if subject == "card.hand":
        return [r for r, m in v["hands"] if m["recorder"] == "a"]
    if subject == "card.phase":
        return [r for r, m in v["phases"] if m["recorder"] == "a"]
    if subject == "card.record":
        return [r for r, m in v["records"] if m["recorder"] == "a"]
    if subject == "card.pair":
        return [r for r, _m in v["pairs"]]
    return [v["game"]]


def _first_contribs(v):
    return [c for c in cm.contributions(v) if c["recorder"] == "a"]


def test_the_coverage_catalog_names_every_measure_once_with_known_facts():
    table = cm.coverage_table()
    names = [n for _s, n, _d in table]
    assert len(names) == len(set(names)) == sum(len(v) for v in cm.MEASURES.values())
    assert set(names) == set(cm.NEEDS)
    assert all(set(d) <= set(cm.COVER) for _s, _n, d in table)
    assert all(d == cm.CONTRIB_NEEDS for s, _n, d in table if s == cm.WINDOW_SUBJECT)
    assert set(cm.CONTRIB_NEEDS) == set(cm.COVER)
    assert cm.NEEDS["b4.hand.dup"] and not cm.NEEDS["b4.hand.n"]          # control: identifiers need none


# fix pass 2 (M1): the one-at-a-time omission cases are generated over what
# each measure's code READS (card_read_sets, derived from the code, never
# from NEEDS) as well as what the catalog declares, so a dependency the
# catalog leaves out is still exercised.
_RS, READS = crs.analyze()
DEPENDENT = [(s, n, d) for s, n, needs in cm.coverage_table() for d in sorted(set(needs) | READS[n])]


@pytest.mark.parametrize("subject,name,fact", DEPENDENT, ids=["%s-%s" % (n, d) for _s, n, d in DEPENDENT])
def test_every_measure_reads_not_run_and_no_contribution_when_a_fact_it_needs_is_omitted(subject, name, fact):
    if subject == cm.WINDOW_SUBJECT:
        # a window measure is a sum of contributions: the first record adds none
        for scn in SCENARIOS:
            assert _first_contribs(_scn_view(scn)), scn.__name__                 # control
            v = _scn_view(scn, lambda rec: _omit(rec, fact))
            assert _first_contribs(v) == [], (name, fact)
        return
    runs = [scn for scn in SCENARIOS
            if any(r[name] is not None for r in _rows_of_first(_scn_view(scn), subject))]
    assert runs, "no base game runs %s: its omission would prove nothing" % name   # control
    for scn in runs:
        v = _scn_view(scn, lambda rec: _omit(rec, fact))
        rows = _rows_of_first(v, subject)
        assert rows and all(r[name] is None for r in rows), (name, fact, scn.__name__)
        assert _first_contribs(v) == [], (name, fact)
        assert fact in v["uncovered"][0]["not_whole"]                           # the named reason
        assert _first_contribs(_scn_view(scn)), scn.__name__                     # control


def test_the_over_cap_fixture_reads_every_dependent_measure_not_run_and_contributes_nothing():
    c = k.fixture_census("over_cap")
    rec = k.on_census(k.fixture_record("over_cap"), c)
    omitted = {kk for kk, v in rec["omit"].items() if (any(v) if isinstance(v, list) else v)}
    assert omitted == {"cards", "held0", "ph", "hd", "ap", "sl", "sp"}
    v = k.view([("a", "b", rec)], [c], "off", k.WEIGHTS, {"a": [], "b": []})
    assert set(v["uncovered"][0]["not_whole"]) == omitted
    assert v["records"][0][0]["b4.rec.uncovered"] == len(omitted)
    rows = {"card.hand": [r for r, _m in v["hands"]], "card.phase": [r for r, _m in v["phases"]],
            "card.record": [r for r, _m in v["records"]], "card.game": [v["game"]]}
    checked = 0
    for subject, name, needs in cm.coverage_table():
        if subject in rows and (set(needs) | READS[name]) & omitted:
            assert all(r[name] is None for r in rows[subject]), name
            checked += 1
    assert checked > len(cm.HAND_RULES) and cm.contributions(v) == []
    whole = copy.deepcopy(rec)                                       # control: the same lists stated whole
    whole["omit"] = {kk: ([0, 0] if isinstance(x, list) else 0) for kk, x in rec["omit"].items()}
    vw = k.view([("a", "b", whole)], [c], "off", k.WEIGHTS, {"a": [], "b": []})
    assert vw["hands"][0][0]["b4.hand.size"] is not None and cm.contributions(vw)


# -- M2: weights by the exact deal profile ---------------------------------------------

W_OLD = {"common": 13, "uncommon": 5, "rare": 2}                    # synthetic
W_NEW = {"common": 3, "uncommon": 7, "rare": 11}                    # synthetic
W_NEWER = {"common": 4, "uncommon": 4, "rare": 9}                   # synthetic


def _other_build(rec):
    r = copy.deepcopy(rec)
    r["prof"][6] = "abcdef12"                                       # another mod commit: another profile
    return r


def _contrib(rec, fam):
    return cm.contributions(k.view([("a", "b", rec)], [k.fixture_census("full_game")], None, fam))


def test_a_game_is_weighed_only_with_its_own_profiles_weights_across_revisions(tmp_path):
    old, new = k.default_record(), _other_build(k.default_record())
    p_old, p_new = cm.deal_profile(old), cm.deal_profile(new)
    assert p_old != p_new
    store, r1 = k.build_card_revision(tmp_path, doc=k.card_doc(weights={p_old: W_OLD, p_new: W_NEW}), name="r1")
    fam1 = k.load(store, r1).ruleset.params[cm.WEIGHTS]
    assert fam1 == {p_old: W_OLD, p_new: W_NEW}
    assert _contrib(old, fam1) == _contrib(old, {p_old: W_OLD}) != _contrib(old, {p_old: W_NEW})
    assert _contrib(new, fam1) == _contrib(new, {p_new: W_NEW}) != _contrib(new, {p_new: W_OLD})
    assert _contrib(old, fam1) and _contrib(new, fam1)
    # a revision change that weighs only the newer build: the older games are
    # not re-evaluated with it, they read NOT-RUN and contribute nothing
    _s, r2 = k.build_card_revision(tmp_path, doc=k.card_doc(weights={p_new: W_NEWER}), name="r2")
    fam2 = k.load(store, r2).ruleset.params[cm.WEIGHTS]
    assert _contrib(old, fam2) == []
    v = k.view([("a", "b", old)], [k.fixture_census("full_game")], None, fam2)
    assert all(r["b4.hand.w0"] is None and r["b4.hand.eligible"] == 0 for r, _m in v["hands"])
    assert _contrib(new, fam2) == _contrib(new, {p_new: W_NEWER}) != _contrib(new, fam1)


def test_an_incomplete_or_not_ok_profile_identity_refuses_the_weights():
    base = k.default_record()
    assert _contrib(base, k.family(W_OLD, base))                                 # control
    for label, edit in (("mod hash unread", lambda r: r["prof"].__setitem__(slice(2, 4), ["", "read_failed"])),
                        ("game hash unread", lambda r: r["prof"].__setitem__(slice(0, 2), ["", "no_location"])),
                        ("pool changed", lambda r: r["pool"].__setitem__(2, "changed")),
                        ("unknown semantics", lambda r: r["prof"].__setitem__(7, "cd-sem:9"))):
        r = copy.deepcopy(base)
        edit(r)
        assert not cm.profile_complete(r), label
        fam = k.family(W_OLD, r)                                                 # the family names it exactly
        assert cm.profile_weights(r, fam) is None and _contrib(r, fam) == [], label
    assert cm.profile_weights(base, {}) is None and cm.profile_weights(base, None) is None
    assert cm.profile_weights(base, k.family(W_OLD, _other_build(base))) is None   # another profile's set


def test_the_weights_family_must_be_keyed_by_full_profile_ids(tmp_path):
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc=k.card_doc(weights=dict(W_OLD)), name="flat")
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc=k.card_doc(weights={"ab" * 8: W_OLD}), name="short")
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc=k.card_doc(weights={cm.deal_profile(k.default_record()): {"common": 1}}),
                              name="partial")
    k.build_card_revision(tmp_path, doc=k.card_doc(), name="keyed")                    # control


# -- M4: the final phase -----------------------------------------------------------

def _with_end(rec, kind):
    out = {}
    for key in cm.W["keys"]:
        if key in cm.W["optional"]:
            out[key] = kind
        elif key in rec:
            out[key] = rec[key]
    return out


def _last_phase(rec):
    return k.view([("a", "b", rec)])["phases"][-1][0]


def test_an_ordinary_games_final_phase_not_done_counts_and_only_a_cut_game_exempts_it():
    rec = k.fixture_record("full_game")
    assert "end" not in rec and _last_phase(rec)["b4.ph.notdone"] == 0                     # control
    open_ = copy.deepcopy(rec)
    open_["ph"][-1][6] = 0
    row = _last_phase(open_)
    assert row["b4.ph.notdone"] == 1 and ce._nonzero(row, ce._PHASE_KEYS)
    cut = _with_end(open_, "left")
    cm.check_record(cut)
    row = _last_phase(cut)
    assert row["b4.ph.notdone"] == 0 and not ce._nonzero(row, ce._PHASE_KEYS)
    cut["ph"][0][6] = 0                                                  # a cut game's earlier phase still counts
    assert k.view([("a", "b", cut)])["phases"][0][0]["b4.ph.notdone"] == 1


# -- M6: the evidence domain ----------------------------------------------------------

def test_a_card_finding_key_can_never_equal_a_seat_finding_key():
    lo, hi = "1d6f0000-0000-4000-8000-000000000001", "1d6f0000-0000-4000-8000-000000000002"
    gk = ce.game_key("ranked_x|y", lo, hi)
    wk = ce.window_key(lo, "self", "one", "f" * 64, "2026-10-05")
    assert gk.startswith("card ") and gk.count(" ") == 1 and wk.startswith("card win ") and wk.count(" ") == 2
    admitted = [chr(i) for i in range(32, 127) if se._KEY_CHARS.fullmatch("k" + chr(i))]
    assert "|" in admitted and " " not in admitted                       # the separator is admitted, the space never
    for stable in ("card", "card|ranked_x|y", "card win", "ranked_x"):
        seat = "%s|%s|%s" % (stable, lo, hi)
        if se._KEY_CHARS.fullmatch(stable):
            assert " " not in seat and seat not in (gk, wk)
    assert "%s|%s|%s" % (lo, hi, "2026-10-05") != wk                      # a seat sitting key
    # control: the old encoding aliased a seat key built from the stable key "card|ranked_x|y"
    assert "card|%s|%s|%s" % ("ranked_x|y", lo, hi) == "%s|%s|%s" % ("card|ranked_x|y", lo, hi)


_FINDING_WRITE = re.compile(r"\b(?:DELETE\s+FROM|UPDATE|INSERT\s+INTO)\s+seat_evidence_findings\b", re.I)


def _unscoped(statements):
    """The statements writing the shared findings table that do not name the
    card domain (an INSERT must write it, a DELETE or UPDATE must filter on it)."""
    out = []
    for s in statements:
        if not _FINDING_WRITE.search(s):
            continue
        if re.search(r"INSERT\s+INTO", s, re.I):
            if not re.search(r"\(domain,", s) or "'card'" not in s:
                out.append(s)
        elif "domain = 'card'" not in s:
            out.append(s)
    return out


def _sql_statements(name):
    body = "\n".join(ln.split("--")[0] for ln in _read(BACKEND, "sql", name).splitlines())
    return [s for s in body.split(";") if s.strip()]


def test_every_card_statement_on_the_shared_findings_table_names_the_card_domain():
    import ast
    consts = [n.value for n in ast.walk(ast.parse(_read(API, "card_evidence.py")))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    written = [s for s in consts if _FINDING_WRITE.search(s)]
    assert len(written) == 3 and _unscoped(consts) == []                  # the upsert, the retirement, the purge
    rb = _sql_statements("rollback_370_card_evidence.sql")
    assert [s for s in rb if _FINDING_WRITE.search(s)] and _unscoped(rb) == []
    m370 = [s for s in _sql_statements("370_card_evidence.sql") if _FINDING_WRITE.search(s)]
    assert len(m370) == 1 and "dedup_key LIKE 'card %'" in m370[0] and "domain = 'seat'" in m370[0]
    assert _unscoped(["DELETE FROM seat_evidence_findings WHERE dedup_key = :k"])          # control
    assert _unscoped(["INSERT INTO seat_evidence_findings (scope, dedup_key) VALUES (:s, :k)"])


# Every statement that writes the shared findings table, in this lane's files
# and the seat lane's files it runs with: (file, kind, the predicate that keeps
# it to one domain). A seat key never holds a space and a card key always
# begins 'card ', so the key form names the domain where the column may be absent.
_DOMAIN_PREDICATES = (
    ("api/card_evidence.py", "INSERT", "VALUES ('card'"),
    ("api/card_evidence.py", "DELETE", "domain = 'card'"),
    ("api/card_evidence.py", "DELETE", "domain = 'card'"),
    ("api/seat_evidence.py", "INSERT", "INSERT INTO seat_evidence_findings (scope, dedup_key"),   # default 'seat'
    ("api/seat_evidence.py", "UPDATE", "WHERE id = :i"),
    ("api/seat_evidence.py", "DELETE", "scope = 'game' AND dedup_key = :k"),
    ("api/seat_evidence.py", "DELETE", "dedup_key NOT LIKE 'card %'"),
    ("sql/370_card_evidence.sql", "UPDATE", "dedup_key LIKE 'card %'"),
    ("sql/rollback_370_card_evidence.sql", "DELETE", "domain = 'card'"),
)


def _finding_writes(rel):
    """(kind, statement) for every statement of `rel` writing the findings table."""
    if rel.endswith(".py"):
        import ast
        stmts = [n.value for n in ast.walk(ast.parse(_read(BACKEND, *rel.split("/"))))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    else:
        stmts = _sql_statements(rel.split("/")[1])
    out = []
    for s in stmts:
        m = _FINDING_WRITE.search(s)
        if m:
            out.append((m.group(0).split()[0].upper(), " ".join(s.split())))
    return out


def _domain_table():
    rows = []
    for rel in sorted({r[0] for r in _DOMAIN_PREDICATES}):
        for kind, s in _finding_writes(rel):
            preds = [p for (f, kk, p) in _DOMAIN_PREDICATES if f == rel and kk == kind and p in s]
            rows.append((rel, kind, preds[0] if preds else None))
    return sorted(rows, key=lambda r: (r[0], r[1], r[2] or ""))


def test_every_write_on_the_shared_findings_table_is_kept_to_one_domain():
    rows = _domain_table()
    assert None not in [p for _f, _k, p in rows], rows
    assert rows == sorted(_DOMAIN_PREDICATES, key=lambda r: (r[0], r[1], r[2]))   # the count is checkable
    assert len(rows) == 9
    # the seat purge names the card key form; control: without it the row is unclassified
    purge = [s for kk, s in _finding_writes("api/seat_evidence.py") if "changed_at <" in s]
    assert len(purge) == 1 and "dedup_key NOT LIKE 'card %'" in purge[0]
    bare = purge[0].replace("AND dedup_key NOT LIKE 'card %' ", "")
    assert not [p for (f, kk, p) in _DOMAIN_PREDICATES if f == "api/seat_evidence.py" and kk == "DELETE"
                and p in bare]                                                    # control


def test_the_migration_adds_the_domain_and_the_rollback_removes_it():
    sql = _read(BACKEND, "sql", "370_card_evidence.sql")
    assert "ADD COLUMN IF NOT EXISTS domain VARCHAR(8) NOT NULL DEFAULT 'seat'" in sql
    assert "CHECK (domain IN ('seat', 'card'))" in sql
    assert "ON seat_evidence_findings (domain, scope, dedup_key, rule_id)" in sql
    rb = _read(BACKEND, "sql", "rollback_370_card_evidence.sql")
    assert "DROP COLUMN IF EXISTS domain" in rb and "DROP INDEX IF EXISTS ux_seat_evidence_findings_domain" in rb
    assert "LIKE 'card|%'" not in rb


# -- M8: the report projection ----------------------------------------------------------

def _report_row(rec, report):
    return k.view([("a", "b", rec)], [k.fixture_census("full_game")], None, None, report)["records"][0][0]


def test_the_report_picks_measure_counts_each_sides_surplus():
    rec = k.default_record()
    mine, theirs = _picked(rec, 0), _picked(rec, 1)
    assert mine and theirs
    keys = cm.REPORT_PICKS
    assert [_report_row(rec, {"a": mine, "b": theirs})[x] for x in keys] == [0, 0, 0, 0]       # control
    row = _report_row(rec, {"a": mine[1:], "b": theirs + ["NotInTheRecord"]})
    assert [row[x] for x in keys] == [1, 0, 0, 1]
    row = _report_row(rec, {"b": theirs})                                    # no rows for one player
    assert [row[x] for x in keys] == [len(mine), 0, 0, 0]
    assert all(_report_row(rec, None)[x] is None for x in keys)              # no report read: not run
    unknown = copy.deepcopy(rec)
    e = next(e for e in unknown["hd"] if e[2] == 0 and e[9] >= 0)
    e[9] = -1                                                                # picked, the slot unknown
    row = _report_row(unknown, {"a": mine, "b": theirs})
    assert row[keys[0]] is None and row[keys[1]] is None and row[keys[2]] == 0


def test_the_report_is_read_only():
    src = inspect.getsource(ce._report)
    assert "SELECT player_id, card_name FROM match_cards" in src and _written(src) == set()
    assert _written(_read(API, "card_evidence.py")) & {"match_cards", "matches"} == set()


# == fix pass 2 =========================================================================

# -- M1: what each measure's code reads, against what the catalog declares ---------------

def test_m1_every_measure_declares_every_coverage_fact_its_code_reads():
    """DECLARED (NEEDS) contains READ for every measure; READ comes from the
    static read-set analysis of card_measures.py (card_read_sets), which
    never consults NEEDS."""
    assert set(READS) == {n for names in cm.MEASURES.values() for n in names}
    bad = {n: sorted(READS[n] - set(cm.NEEDS[n])) for n in READS if READS[n] - set(cm.NEEDS[n])}
    assert bad == {}, bad


def test_m1_the_read_set_analysis_covers_the_code_and_states_its_exclusions():
    for entry in crs.ENTRIES + ("_hand_row", "_phase_rows", "_record_row", "_same_cards",
                                "_report_surplus", "RecFacts.__init__", "RecFacts.held_at"):
        assert entry in _RS.reach, entry
    assert not set(crs.GATE) & _RS.reach                     # the gate itself is not read as data
    # the only NOT-RUN test the analysis leaves out is the not-run counter's
    assert {f for f, _line in _RS.drops} == {"_hand_row"} and len(_RS.drops) == 1
    src = _read(API, "card_measures.py")
    line = sorted(_RS.drops)[0][1]
    assert "b4.hand.notrun" in src.splitlines()[line - 1]
    # control: identifiers read nothing a fact certifies (the analysis is not
    # everything everywhere)
    for name in ("b4.hand.recorder", "b4.hand.phase", "b4.ph.phase", "b4.rec.index", "b4.pair.phase"):
        assert READS[name] == frozenset(), name
    assert "sl" in READS["b4.sc.norule"]                      # the round's own case, derived


def _reads_of(src):
    return crs.analyze(src)[1]


def test_m1_the_analysis_sees_a_new_read_the_catalog_lacks():
    """Controls on edited copies of the module source: a read moved into a
    measure shows in its READ, and an unknown construct is refused."""
    src = _read(API, "card_measures.py")
    edits = (('"b4.hand.phase": f["o"]', '"b4.hand.phase": len(sl)', "b4.hand.phase", "sl"),
             ('_bits(f["src"], len(f["sl"]))', '_bits(f["src"], len(f["sp"]))', "b4.sc.norule", "sp"),
             ('"b4.rec.index": rf.i', '"b4.rec.index": len(rec["ap"])', "b4.rec.index", "ap"),
             ('"b4.ph.role": w', '"b4.ph.role": w if not rf.first_lost else -1', "b4.ph.role", "first"),
             # a control decision over a stated omission count
             ('    if series_sc is None or rule < 0:', '    if series_sc is None or rule < 0 or not rf.ph_ok:',
              "b4.sc.rule", "ph"))
    for old, new, name, fact in edits:
        assert src.count(old) == 1, old
        got = _reads_of(src.replace(old, new))
        assert fact in got[name] and fact not in READS[name], (name, fact, sorted(got[name]))
    old = "    out = []\n    for _ in range(width):"
    assert src.count(old) == 1
    with pytest.raises(crs.Unsupported):
        _reads_of(src.replace(old, "    out = []\n    while not out:\n        out = [0]\n"
                                   "    for _ in range(width):"))


def test_m1_the_generated_omission_cases_are_counted():
    c = crs.counts(READS, cm.NEEDS)
    print("card read-set counts: %s" % c)
    assert c["measures"] == len(READS) and c["omission_cases"] == len(DEPENDENT)
    assert c["undeclared"] == 0
    assert c["read_pairs"] <= c["omission_cases"] and c["declared_pairs"] <= c["omission_cases"]


def test_m1_a_trimmed_slot_list_reads_same_cards_not_run_with_every_other_fact_whole():
    """The round's own case, isolated: one SELF hand's slot list cut short and
    stated so (sl), the hand list and every other fact whole. b4.sc.norule
    reads the slot list's length, so it is NOT-RUN, and the record adds no
    contribution."""
    recs, reg, sc, report = _scenario_full()
    base = k.view(recs, reg, sc, k.WEIGHTS, report)
    assert base["game"]["b4.sc.norule"] is not None and _first_contribs(base)    # control
    s, o, rec = recs[0]
    cut = copy.deepcopy(rec)
    j = next(i for i, e in enumerate(cut["hd"]) if e[2] == 0 and len(e[6]) > 1)
    cut["hd"][j][6] = cut["hd"][j][6][:-1]
    cut["omit"]["sl"] = 1
    v = k.view([(s, o, cut)] + recs[1:], reg, sc, k.WEIGHTS, report)
    assert v["uncovered"][0]["not_whole"] == ["sl"]
    assert v["game"]["b4.sc.norule"] is None
    assert _first_contribs(v) == []


# -- M1 fix pass 4: compositions, accepted with their attribution or refused --------------
#
# Source edits of card_measures.py. An ACCEPTED composition must show the read
# it adds in the measure's READ (the fact absent before the edit); a REFUSED
# one must raise Unsupported for the composition itself (the message names it).
_SIZE = '    row["b4.hand.size"] = None if rf.lossy else int(n != rec["ns"])\n'
_HAND_DEF = "def _hand_row(rf, f, other_rf, dealer_self, series_sc):\n"
_PH_APPEND = '        rows.append((row, {"recorder": rf.seat, "o": o, "w": w}))\n'
_HELD_TOP = "    count = 0\n    for j, ix in enumerate(sl):\n"
_DYN_KEY = "HAND_RULES[n % len(HAND_RULES)]"
FIX4_ACCEPTED = [
    # a union of measure rows overwriting a measure: the new value's read is recorded
    ("row_union_in_place", [(_SIZE, _SIZE + '    row |= {"b4.hand.size": len(rec["ap"])}\n')],
     "b4.hand.size", "ap"),
    ("row_union", [(_SIZE, _SIZE + '    row = row | {"b4.hand.size": len(rec["ap"])}\n')],
     "b4.hand.size", "ap"),
    ("row_unpacked_into_a_row", [(_SIZE, _SIZE + '    row = {**row, "b4.hand.size": len(rec["ap"])}\n')],
     "b4.hand.size", "ap"),
    # an augmented assignment on a measure of a row records its read
    ("augmented_measure", [(_SIZE, _SIZE + '    row["b4.hand.phase"] += len(rec["ap"])\n')],
     "b4.hand.phase", "ap"),
    # an augmented assignment on a counter
    ("augmented_counter", [('stated += sum(_bits(f["src"], len(f["sl"])))',
                            'stated += sum(_bits(f["src"], len(f["sl"]))) + len(rf.rec["ap"])')],
     "b4.sc.norule", "ap"),
    # through the setdefault alias, a field and an element of a list field:
    # followed to the window row
    ("alias_field", [('        c["slots"] += meta["n"]\n', '        c["slots"] += meta["n"] + len(view["phases"])\n')],
     "b4.rar.obs.common", "ph"),
    ("alias_list_field_element", [('            c["obs"][r] += obs[r]\n',
                                   '            c["obs"][r] += obs[r] + len(view["phases"])\n')],
     "b4.rar.obs.common", "ph"),
    # a container made here and changed before anything else holds it
    ("fresh_list", [(_SIZE, _SIZE + '    extra = []\n    extra.append(len(rec["ap"]))\n'
                     '    row["b4.hand.phase"] = sum(extra)\n')], "b4.hand.phase", "ap"),
    ("fresh_dict_computed_key", [(_SIZE, _SIZE + '    tally = {}\n    tally[n] = len(rec["ap"])\n'
                                  '    row["b4.hand.phase"] = sum(tally.values())\n')], "b4.hand.phase", "ap"),
    # a callee writing a measure into the row it is given: followed to the row
    ("callee_writes_the_row", [(_HAND_DEF, 'def _extra_measure(row, rec):\n    row["b4.hand.phase"] = '
                                'len(rec["ap"])\n\n\n' + _HAND_DEF),
                               (_SIZE, _SIZE + "    _extra_measure(row, rec)\n")], "b4.hand.phase", "ap"),
]
FIX4_REFUSED = [
    # the round's case: a union overwriting a measure under a key the analysis cannot resolve
    ("union_in_place_with_an_unresolved_key", [(_SIZE, _SIZE + "    row |= {%s: len(rec[\"ap\"])}\n" % _DYN_KEY)],
     "union of a measure row or field dict with what is not a measure row"),
    ("union_with_an_unresolved_key", [(_SIZE, _SIZE + "    row = row | {%s: len(rec[\"ap\"])}\n" % _DYN_KEY)],
     "union of a measure row or field dict with what is not a measure row"),
    ("row_unpacked_with_an_unresolved_key", [(_SIZE, _SIZE + "    row = {**row, %s: len(rec[\"ap\"])}\n" % _DYN_KEY)],
     "unresolved key in a measure row literal"),
    ("union_of_the_record", [(_SIZE, _SIZE + '    both = rec | {}\n')], "union of a record-derived structure"),
    ("in_place_set_union", [("        earlier = set(sl[:j])\n", "        earlier = set(sl[:j])\n        earlier |= {ix}\n")],
     "in-place union of what is not a measure row"),
    ("augmented_list", [("            rows.append((row, meta))\n", "            rows += [(row, meta)]\n")],
     "cannot show holds an immutable value"),
    ("augmented_dict_element", [("        mine[name] = mine.get(name, 0) + 1\n", "        mine[name] += [1]\n")],
     "cannot show holds an immutable value"),
    ("augmented_operator", [("            count += 1\n", "            count @= 1\n")], "augmented operator MatMult"),
    ("change_through_an_alias", [("    out = []\n    for _ in range(width):", "    out = []\n    alias = out\n"
                                  "    for _ in range(width):"), ("        out.append(r)\n", "        alias.append(r)\n")],
     "may hold an object another name holds"),
    ("computed_key_store_through_an_alias", [("    mine = {}\n", "    mine = {}\n    seen = mine\n"),
                                             ("        mine[name] = mine.get(name, 0) + 1\n",
                                              "        seen[name] = mine.get(name, 0) + 1\n")],
     "may hold an object another name holds"),
    ("change_to_a_parameter", [(_HELD_TOP, "    count = 0\n    held.append(0)\n    for j, ix in enumerate(sl):\n")],
     "change to the parameter held"),
    ("computed_key_store_into_a_parameter", [("        g = gens[j]\n", "        g = gens[j]\n        gens[j] = g\n")],
     "change to the parameter gens"),
    ("callee_changes_its_callers_list", [(_HAND_DEF, "def _stamp(rows):\n    rows.append(None)\n\n\n" + _HAND_DEF),
                                         (_PH_APPEND + "    return rows\n",
                                          _PH_APPEND + "    _stamp(rows)\n    return rows\n")],
     "change to the parameter rows"),
    ("change_after_handed_on", [("        per_rec_rows.append(rows)\n",
                                 "        per_rec_rows.append(rows)\n        rows.append((None, None))\n")],
     "after it was handed on"),
    ("change_after_handed_on_in_an_earlier_turn", [(_PH_APPEND, _PH_APPEND + "        snapshot = [rows]\n")],
     "after it was handed on"),
]


def _edited(edits):
    src = _read(API, "card_measures.py")
    for old, new in edits:
        assert src.count(old) == 1, old
        src = src.replace(old, new)
    return src


@pytest.mark.parametrize("case", FIX4_ACCEPTED, ids=[c[0] for c in FIX4_ACCEPTED])
def test_m1_fix4_an_accepted_composition_records_the_read_it_adds(case):
    _id, edits, name, fact = case
    assert fact not in READS[name]                          # control: the edit adds a read
    got = _reads_of(_edited(edits))
    assert fact in got[name], (name, fact, sorted(got[name]))


@pytest.mark.parametrize("case", FIX4_REFUSED, ids=[c[0] for c in FIX4_REFUSED])
def test_m1_fix4_a_composition_the_analysis_cannot_attribute_is_refused(case):
    _id, edits, refusal = case
    _reads_of(_edited([(old, old) for old, _new in edits]))   # control: the unedited source analyses
    with pytest.raises(crs.Unsupported, match=refusal):
        _reads_of(_edited(edits))


def test_m1_fix4_the_composition_tables_are_counted():
    print("compositions: %d accepted with a control, %d refused with a case"
          % (len(FIX4_ACCEPTED), len(FIX4_REFUSED)))
    assert len({c[0] for c in FIX4_ACCEPTED}) == len(FIX4_ACCEPTED)
    assert len({c[0] for c in FIX4_REFUSED}) == len(FIX4_REFUSED)


# -- M2: the window length is bounded, so a changed day's work is ----------------------

def test_m2_a_card_window_is_a_whole_number_of_days_up_to_the_derived_retention(tmp_path):
    assert cm.WINDOW_DAYS_MAX == ce.CARD_LIMITS["derived_retention_days"]
    for i, bad in enumerate((0, -3, cm.WINDOW_DAYS_MAX + 1, 9.5, True)):
        doc = k.card_doc()
        doc["measure_params"][cm.WINDOW] = {cm.WINDOW_KEY: bad}
        with pytest.raises(rr.Refused):
            k.build_card_revision(tmp_path, doc=doc, name="bad%d" % i)
    for i, good in enumerate((1, cm.WINDOW_DAYS_MAX)):                     # control
        doc = k.card_doc()
        doc["measure_params"][cm.WINDOW] = {cm.WINDOW_KEY: good}
        k.build_card_revision(tmp_path, doc=doc, name="good%d" % i)


# == fix pass 3 =========================================================================

# -- M1: the read-set analysis fails closed on every shape it does not model -------------
#
# Source edits of card_measures.py, one per shape the round named. Each moves
# a read into a measure that READS lacks; the analysis must either see the
# read (the fact appears in that measure's READ) or refuse the edited module
# (Unsupported, naming the shape). Reading nothing more is the defect.
FIX3_EDITS = [
    # nested integer indexing: an hd entry taken by position, then its slot list
    ("nested_index", '"b4.hand.phase": f["o"]', '"b4.hand.phase": rec["hd"][0][6]',
     "b4.hand.phase", "sl", None),
    # a dynamic .get on the record
    ("dynamic_get", '"b4.rec.index": rf.i', '"b4.rec.index": rec.get(rf.seat)',
     "b4.rec.index", "hd", "dynamic key into the record"),
    # a measure row read with a key the analysis cannot resolve
    ("dynamic_measure_row", 'h["b4.hand.notrun"]', 'h[HAND_RULES[rf.i]]',
     "b4.rec.notrun_hands", "held0", "measure row"),
    # a module helper taking the whole record
    ("opaque_helper", '"b4.rec.conflict": int(rf.conflict)', '"b4.rec.conflict": len(json.dumps(rec))',
     "b4.rec.conflict", "hd", "whole read"),
    # a method the analysis has no rule for, on the omission counts
    ("opaque_method", '"b4.rec.cut": int(rf.cut)', '"b4.rec.cut": rf.omit.__getitem__("hd")',
     "b4.rec.cut", "hd", "method __getitem__"),
]


@pytest.mark.parametrize("case", FIX3_EDITS, ids=[e[0] for e in FIX3_EDITS])
def test_m1_fix3_an_unmodelled_shape_is_seen_or_refused_never_read_as_nothing(case):
    _id, old, new, name, fact, refusal = case
    src = _read(API, "card_measures.py")
    assert src.count(old) == 1, old
    assert fact not in READS[name]                          # control: the edit adds a read
    edited = src.replace(old, new)
    if refusal is None:
        got = _reads_of(edited)
        assert fact in got[name], (name, fact, sorted(got[name]))
    else:
        with pytest.raises(crs.Unsupported, match=refusal):
            _reads_of(edited)


# -- M1 (a): every ast expression and statement class is modelled or refused ---------------

_PHASE = '"b4.hand.phase": f["o"]'
_AFTER = "    weights = rf.weights\n"

# The modelled expression classes, each with a positive case: the value of
# b4.hand.phase in _hand_row replaced by the snippet, and what it must read.
EXPR_CASES = {
    "Constant": ("0", set()),
    "Name": ("sl", {"sl"}),
    "Tuple": ("(sl, 0)", {"sl"}),
    "List": ("[sl]", {"sl"}),
    "Set": ("{len(sl)}", {"sl"}),
    "Starred": ("[*sl]", {"sl"}),
    "Dict": ('{"o": sl}["o"]', {"sl"}),
    "BinOp": ('0 + len(rec["ap"])', {"ap"}),
    "UnaryOp": ('-len(rec["ap"])', {"ap"}),
    "BoolOp": ("sl or 0", {"sl"}),
    "Compare": ('len(rec["ap"]) > 0', {"ap"}),
    "IfExp": ('0 if rec["ap"] else 1', {"ap"}),
    "Call": ('len(rec["ap"])', {"ap"}),
    "Attribute": ("rf.first_lost", {"first"}),
    "Subscript": ('rec["hd"][0][6]', {"hd", "sl"}),
    "Slice": ('rec["ap"][1:]', {"ap"}),                     # modelled inside the Subscript rule
    "ListComp": ("[x for x in sl]", {"sl"}),
    "SetComp": ("{x for x in sl}", {"sl"}),
    "GeneratorExp": ("sum(x for x in sl)", {"sl"}),
    "DictComp": ('len({x: 0 for x in rec["ap"]})', {"ap"}),
    "JoinedStr": ("f\"{len(rec['ap'])}\"", {"ap"}),
    "FormattedValue": ("f\"{len(rec['ap'])}\"", {"ap"}),
}
# The modelled statement classes: statements put before the row (the value
# is `probe`), and what b4.hand.phase must then read.
STMT_CASES = {
    "Assign": ('    probe = len(rec["ap"])\n', {"ap"}),
    "AugAssign": ('    probe = 0\n    probe += len(rec["ap"])\n', {"ap"}),
    "Expr": ('    probe = []\n    probe.append(len(rec["ap"]))\n', {"ap"}),
    "If": ('    probe = 0\n    if rec["ap"]:\n        probe = 1\n', {"ap"}),
    "For": ('    probe = 0\n    for x in rec["ap"]:\n        probe += 1\n', {"ap"}),
    # the continue's own test reaches the count (without the rule: ap only)
    "Continue": ('    probe = 0\n    for x in rec["ap"]:\n        if f["sl"]:\n            continue\n'
                 '        probe += 1\n', {"ap", "sl"}),
    "Pass": ('    probe = len(rec["ap"])\n    pass\n', {"ap"}),
    # the raise's test is in force where the row is built, and the row is
    # returned, so the test is kept on it
    "Raise": ('    probe = 0\n    if not f["sl"]:\n        raise probe\n    probe = len(rec["ap"])\n',
              {"ap", "sl"}),
    "Return": (None, {"ap"}),                                 # a helper returning the read
}


def _ast_classes():
    """Every expression and statement class the ast module defines, aliases
    mapped to the class they build."""
    import ast
    import warnings
    out = {}
    for name, cls in vars(ast).items():
        if not (isinstance(cls, type) and issubclass(cls, (ast.expr, ast.stmt))) or cls in (ast.expr, ast.stmt):
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                built = type(cls())
            except TypeError:
                built = cls
        out[name] = built
    return out


def _with_phase(value, before=""):
    src = _read(API, "card_measures.py")
    assert src.count(_PHASE) == 1 and src.count(_AFTER) == 1
    return src.replace(_AFTER, _AFTER + before).replace(_PHASE, '"b4.hand.phase": ' + value)


def _refused_node(cls):
    """An instance of `cls` whose every field holds the record, put where
    the analysis meets it: an expression evaluated in _hand_row where the
    record is bound, a statement in a function body."""
    import ast
    node = cls(**{f: ast.Name(id="rec", ctx=ast.Load()) for f in cls._fields})
    node.lineno = node.end_lineno = 1
    node.col_offset = node.end_col_offset = 0
    if issubclass(cls, ast.expr):
        fn = _RS._fn("_hand_row")
        site = next(i for i, st in enumerate(fn.stmts) if ast.unparse(st["node"]) == "weights = rf.weights")
        with pytest.raises(crs.Unsupported, match="no rule for the expression " + cls.__name__):
            _RS.ev(node, fn, site, ())
    else:
        fdef = ast.parse("def probe(rec):\n    pass\n").body[0]
        fdef.body = [node]
        with pytest.raises(crs.Unsupported, match="no rule for the statement " + cls.__name__):
            crs.Fn("probe", fdef)


def test_m1_fix3_every_ast_node_class_is_modelled_with_a_positive_case_or_refused():
    import ast
    classes = _ast_classes()
    exprs = {n for n, c in classes.items() if c is classes[n] and issubclass(c, ast.expr)}
    stmts = {n for n, c in classes.items() if c is classes[n] and issubclass(c, ast.stmt)}
    modelled_e = {c.__name__ for c in crs.Analysis.EXPRS} | {"Slice"}
    modelled_s = {c.__name__ for c in crs.STMTS}
    # the allowlist is exactly the classes with a positive case
    assert modelled_e == set(EXPR_CASES) and modelled_s == set(STMT_CASES)
    assert modelled_e <= exprs and modelled_s <= stmts
    positive = refused = aliases = 0
    for name, (snippet, want) in EXPR_CASES.items():
        got = _reads_of(_with_phase(snippet))["b4.hand.phase"]
        assert set(got) == want, (name, snippet, sorted(got))
        positive += 1
    for name, (body, want) in STMT_CASES.items():
        if body is None:
            src = _with_phase('_probe(rec["ap"])') + "\n\ndef _probe(x):\n    return len(x)\n"
        else:
            src = _with_phase("probe", body)
        got = _reads_of(src)["b4.hand.phase"]
        assert set(got) == want, (name, sorted(got))
        positive += 1
    for name, cls in sorted(classes.items()):
        if cls is not getattr(ast, name):
            aliases += 1                             # builds another class, counted there
            continue
        if name in modelled_e | modelled_s and name != "Slice":
            continue
        _refused_node(cls)
        refused += 1
    print("node classes: %d enumerated (%d expression, %d statement, %d aliases); modelled %d with "
          "a positive case; refused %d" % (len(classes), len(exprs), len(stmts), aliases, positive, refused))
    assert positive + refused + aliases == len(classes) + 1      # Slice: modelled in Subscript, refused bare
    assert refused > 0


# -- M1 (a): the modelled callables, each with its read semantics; anything else refused -----

def _callable_cases():
    pos = {}
    for n in crs.TRUTH_BUILTINS:
        pos[n] = '%s(rec["ap"], list)' % n if n == "isinstance" else '%s(rec["ap"])' % n
    for n in crs.CONTENT_BUILTINS | crs.PICK_BUILTINS | crs.KEEP_BUILTINS | crs.PAIR_BUILTINS:
        pos[n] = '%s(rec["ap"])' % n
    pos[crs.DICT_BUILTIN] = 'dict(rec["ap"])'
    for mod, fn in crs.MODULE_CALLS:
        pos["%s.%s" % (mod, fn)] = '%s.%s(rec["ap"])' % (mod, fn)
    pos[".encode"] = 'str(len(rec["ap"])).encode()'
    pos[".hexdigest"] = 'hashlib.sha256(rec["ap"]).hexdigest()'
    assert {m[1:] for m in pos if m.startswith(".")} == crs.SCALAR_METHODS
    return pos


def test_m1_fix3_each_modelled_callable_reads_what_its_semantics_say():
    cases = _callable_cases()
    for name, snippet in sorted(cases.items()):
        got = _reads_of(_with_phase(snippet))["b4.hand.phase"]
        assert set(got) == {"ap"}, (name, sorted(got))
    print("modelled callables: %d, each reading the list it was given" % len(cases))


def test_m1_fix3_a_record_or_record_list_given_to_any_other_callable_is_refused():
    import builtins
    import hashlib
    import json
    import math
    modelled = crs.BUILTIN_VALUES | {"Refusal"}
    names = sorted(n for n in dir(builtins) if not n.startswith("_") and callable(getattr(builtins, n))
                   and n not in modelled and not hasattr(cm, n))
    refused = 0
    for n in names:
        for arg in ("rec", 'rec["ap"]'):
            with pytest.raises(crs.Unsupported):
                _reads_of(_with_phase("%s(%s)" % (n, arg)))
            refused += 1
    for mod in (math, hashlib, json):
        for fn in sorted(a for a in dir(mod) if not a.startswith("_") and callable(getattr(mod, a))):
            if (mod.__name__, fn) in crs.MODULE_CALLS:
                continue
            with pytest.raises(crs.Unsupported, match="module call"):
                _reads_of(_with_phase('%s.%s(rec["ap"])' % (mod.__name__, fn)))
            refused += 1
    methods = set()
    for t in (dict, list, str, int, set, tuple):
        methods |= {a for a in dir(t) if not a.startswith("_")}
    methods -= crs.MUTATORS | crs.KEEP_METHODS | crs.SCALAR_METHODS | {"get"}
    methods -= set(_RS.methods)
    for m in sorted(methods | {"__getitem__", "__len__", "__iter__"}):
        for recv in ("rec", "rf.omit", 'rec["ap"]'):
            with pytest.raises(crs.Unsupported):
                _reads_of(_with_phase("%s.%s()" % (recv, m)))
            refused += 1
    # the modelled dict methods on the record itself: a whole read is refused
    for m in ("items", "values", "append", "update"):
        with pytest.raises(crs.Unsupported):
            _reads_of(_with_phase("rec.%s(0)" % m if m in ("append", "update") else "rec.%s()" % m))
        refused += 1
    print("callables refused on record data: %d cases" % refused)
    assert refused > len(names)


# -- M1 (c): a measure-row key the analysis cannot resolve is refused when written --------

_ROW_END = '"b4.hand.deal": f["k"], "b4.hand.n": n, "b4.hand.n_exp": rec["ns"]}\n'
WRITE_EDITS = [
    ("store_under_a_computed_key", _ROW_END, _ROW_END + "    row[HAND_RULES[rf.i]] = 0\n",
     "unresolved key into a measure row"),
    ("literal_with_a_computed_key", '"b4.hand.n": n,', '"b4.hand.n": n, HAND_RULES[rf.i]: 0,',
     "unresolved key in a measure row literal"),
    ("merge_of_a_non_row", _ROW_END, _ROW_END + '    row.update({"x": rf.i})\n',
     "merged with what is not a measure row"),
    ("gate_on_a_non_row", _ROW_END, _ROW_END + '    _gate({"x": rf.i}, rf.ok)\n',
     "gate applied to what is not a measure row"),
    ("row_name_rebound", _ROW_END, _ROW_END + "    row = dict(x=rf.i)\n",
     "bound to a value that is not a measure row"),
    ("mutation_of_a_row", _ROW_END, _ROW_END + "    row.pop(0)\n", "method pop"),
]


@pytest.mark.parametrize("case", WRITE_EDITS, ids=[e[0] for e in WRITE_EDITS])
def test_m1_fix3_a_measure_row_write_the_analysis_cannot_resolve_is_refused(case):
    _id, old, new, refusal = case
    src = _read(API, "card_measures.py")
    assert src.count(old) == 1, old
    _reads_of(src.replace(old, old))                          # control: the unedited source analyses
    with pytest.raises(crs.Unsupported, match=refusal):
        _reads_of(src.replace(old, new))


# -- M1 (b): the second method, and the two compared ---------------------------------------

_DYN = {}


def _dynamic():
    if "r" not in _DYN:
        _DYN["r"] = crd.measured()
    return _DYN["r"]


def test_m1_fix3_the_two_methods_share_no_walker_code():
    src = _read(HERE, "card_read_dynamic.py")
    assert "card_read_sets" not in src.replace("shares no code with card_read_sets", "")
    assert "import ast" not in src and "ast." not in src


def test_m1_fix3_dynamic_reads_are_static_reads_and_static_reads_are_declared():
    """DYN (what moved a value) within STATIC (what the code reads, by the
    analysis) within DECLARED (NEEDS), for every measure. A dynamic read the
    static method leaves out must be exactly one of its stated exclusions:
    a NOT-RUN counter's (the counted measures' own reads), or the incident
    word read whole (the bits' facts, on the measures that carry it)."""
    res, fns, taken, total, missing = _dynamic()
    assert res.raised == [] and res.runs > len(crd.fixtures())
    names = {n for ns in cm.MEASURES.values() for n in ns}
    assert set(res.dyn) == names
    # the recording view saw every fact touched, and nothing moved untouched
    assert res.touched == set(cm.COVER)
    assert set().union(*res.dyn.values()) <= res.touched
    excess = {m: res.dyn[m] - set(READS[m]) for m in names if res.dyn[m] - set(READS[m])}
    # the stated exclusions, from the static method's own record of them
    counters = {}
    for fn, line in _RS.drops:
        defined = [m for m, sites in _RS.sites.items() if (fn, line) in sites]
        assert len(defined) == 1, (fn, line, defined)
        counters[defined[0]] = set(cm.HAND_RULES)
    allowed = {m: set() for m in names}
    for m, counted in counters.items():
        allowed[m] |= set().union(*(res.dyn[r] for r in counted))
    for m in _RS.statements():
        allowed[m] |= {"whole", "first"}
    changed = True
    while changed:                                  # a measure built from one inherits its allowance
        changed = False
        for m in names:
            for x in _RS.defs.get(m, ()):
                if x.startswith("M:") and not allowed[x[2:]] <= allowed[m]:
                    allowed[m] |= allowed[x[2:]]
                    changed = True
    unexplained = {m: sorted(e - allowed[m]) for m, e in excess.items() if e - allowed[m]}
    assert unexplained == {}, unexplained
    undeclared = {m: sorted(set(READS[m]) - set(cm.NEEDS[m])) for m in names
                  if set(READS[m]) - set(cm.NEEDS[m])}
    assert undeclared == {}, undeclared
    # the other direction: what the static method reads and no run moved
    surplus = {(m, f) for m in names for f in READS[m] if f not in res.dyn[m]}
    never = {(m, f) for m, f in surplus if m not in res.valued}
    rowset = {(m, f) for m, f in surplus - never if f in res.rowset[m]}
    over = surplus - never - rowset
    static_pairs = sum(len(v) for v in READS.values())
    dyn_pairs = sum(len(v) for v in res.dyn.values())
    declared = sum(len(cm.NEEDS[m]) for m in names)
    print("two methods: measures %d, static pairs %d, dynamic pairs %d, declared pairs %d, "
          "Unsupported over the real tree 0" % (len(names), static_pairs, dyn_pairs, declared))
    print("dynamic beyond static, explained by the stated exclusions: %s"
          % {m: sorted(e) for m, e in sorted(excess.items())})
    print("static beyond dynamic: %d pairs (measure never held a value on these fixtures %d, fact "
          "moved only which rows exist %d, a read that did not move the value on these fixtures %d)"
          % (len(surplus), len(never), len(rowset), len(over)))
    # fix pass 4 (M2): every static-only pair and every unexercised arm is
    # accounted for by identity (card_read_dispositions), all printed
    for m, f in sorted(surplus):
        why = crdisp.PAIRS.get((m, f), "NONE")
        print("  static only: %s %s [%s] %s" % (m, f, why, crdisp.PAIR_REASONS.get(why, "")))
    print("recording view: %d runs, facts touched %s" % (res.runs, sorted(res.touched)))
    print("branch coverage of the measure functions: %d of %d arms in %d functions; %d unexercised"
          % (taken, total, fns, len(missing)))
    for fname, line, n, arm, _op, never, src_text in crd.describe(missing):
        why = crdisp.ARMS.get((fname, line, n, arm), "NONE")
        print("  unexercised: %s line %s site %d, %s arm (never %s: %s) [%s]"
              % (fname, line, n, arm, never, src_text.strip()[:80], why))
    for why, text in sorted(crdisp.ARM_REASONS.items()):
        print("  arm reason %s: %s" % (why, text))
    assert taken <= total and fns > 0
    problems = crdisp.check(surplus, res.rowset, missing)
    assert problems == [], problems


def test_m1_fix3_the_dynamic_method_sees_a_read_moved_into_a_measure():
    """Control for the second method: the measure code edited in memory so
    b4.hand.phase reads the slot list's length; the dynamic method must then
    see sl move it (and must not before)."""
    res, *_ = _dynamic()
    assert "sl" not in res.dyn["b4.hand.phase"]
    orig = cm._hand_row

    def edited(rf, f, other_rf, dealer_self, series_sc):
        row, meta = orig(rf, f, other_rf, dealer_self, series_sc)
        row["b4.hand.phase"] = len(f["sl"])
        return row, meta
    cm._hand_row = edited
    try:
        got = crd.dynamic_reads()
    finally:
        cm._hand_row = orig
    assert "sl" in got.dyn["b4.hand.phase"]


# -- M2 fix pass 4: the dynamic proof is accountable and cannot cancel ----------------------

def test_m2_fix4_the_gate_refuses_a_missing_stale_or_mismatched_disposition():
    res, _fns, _taken, _total, missing = _dynamic()
    names = {n for ns in cm.MEASURES.values() for n in ns}
    surplus = {(m, f) for m in names for f in READS[m] if f not in res.dyn[m]}
    assert crdisp.check(surplus, res.rowset, missing) == []                # control: accounted for
    pair = sorted(surplus)[0]
    arm = sorted(missing, key=str)[0]
    cases = {
        "a static-only pair with no disposition": (surplus | {("b4.game.records", "ap")}, res.rowset, missing),
        "a disposition for a pair that is not static-only": (surplus - {pair}, res.rowset, missing),
        "an unexercised arm with no disposition": (surplus, res.rowset, missing + [("card_view", 1, 1, "jump")]),
        "a disposition for an arm that is not unexercised": (surplus, res.rowset,
                                                             [a for a in missing if a != arm]),
    }
    for what, args in cases.items():
        assert crdisp.check(*args), what
    # a pair whose observed kind changed (rows moved, or no longer moved)
    flipped = {m: set(v) for m, v in res.rowset.items()}
    m, f = next(p for p in sorted(surplus) if crdisp.PAIRS[p] == "ROWSET")
    flipped[m].discard(f)
    assert any("no longer matches" in p for p in crdisp.check(surplus, flipped, missing))
    # the counts the round named, as identities
    print("dispositions: %d static-only pairs, %d unexercised arms, %d pair reasons, %d arm reasons"
          % (len(crdisp.PAIRS), len(crdisp.ARMS), len(crdisp.PAIR_REASONS), len(crdisp.ARM_REASONS)))


def test_m2_fix4_slot_and_spawn_lists_change_one_hand_and_one_entry_at_a_time():
    """Each sl / sp perturbation changes one hand's list only: one entry
    removed, or that list emptied. The rows it moved lie in the set that hand
    can reach (its deal's hand and pair rows, the record, game and window
    rows); the measures sl and sp moved are exactly the expected sets: the
    static reads of each, less the dispositioned pairs."""
    res, *_ = _dynamic()
    rec = k.default_record()
    count = {"sl": 0, "sp": 0}
    for fact, label, changed, where in crd.perturbations(rec):
        if fact not in ("sl", "sp"):
            assert where is None
            continue
        pos = crd.SL if fact == "sl" else crd.SP
        diff = [h for h, (a, b) in enumerate(zip(rec["hd"], changed["hd"])) if a[pos] != b[pos]]
        assert len(diff) == 1, (label, diff)
        h = diff[0]
        a, b = list(rec["hd"][h][pos]), list(changed["hd"][h][pos])
        assert b == [] or (len(b) == len(a) - 1 and any(a[:j] + a[j + 1:] == b for j in range(len(a)))), label
        assert where == (rec["hd"][h][0], rec["hd"][h][1])
        others = [i for i, (x, y) in enumerate(zip(rec["hd"], changed["hd"])) if i != h and x != y]
        assert others == [], label
        count[fact] += 1
    assert count["sl"] > len(rec["hd"])                                   # every hand, entry by entry
    assert res.outside == [], res.outside[:5]
    assert res.moved and any(res.moved.values())                          # control: they moved rows
    names = {n for ns in cm.MEASURES.values() for n in ns}
    allowed = _exclusions(res)
    for fact in ("sl", "sp"):
        moved = {m for m in names if fact in res.dyn[m]}
        expected = {m for m in names if fact in READS[m] and (m, fact) not in crdisp.PAIRS}
        excluded = {m for m in names if fact in allowed[m]}
        print("%s: %d one-hand perturbations over the fixtures; measures moved %d: %s; expected %d; "
              "moved through a stated exclusion: %s"
              % (fact, sum(1 for kk in res.moved if kk[3] == fact), len(moved), sorted(moved), len(expected),
                 sorted(moved - expected)))
        assert expected <= moved, (fact, sorted(expected - moved))
        assert moved - expected <= excluded, (fact, sorted(moved - expected - excluded))


def _exclusions(res):
    """Per measure, the facts the static method's stated exclusions let move
    it (a NOT-RUN counter: the counted measures' reads; the incident word
    read whole: its bits' facts), inherited by a measure built from one."""
    names = {n for ns in cm.MEASURES.values() for n in ns}
    allowed = {m: set() for m in names}
    for fn, line in _RS.drops:
        defined = [m for m, sites in _RS.sites.items() if (fn, line) in sites]
        for m in defined:
            allowed[m] |= set().union(*(res.dyn[r] for r in cm.HAND_RULES))
    for m in _RS.statements():
        allowed[m] |= {"whole", "first"}
    changed = True
    while changed:
        changed = False
        for m in names:
            for x in _RS.defs.get(m, ()):
                if x.startswith("M:") and not allowed[x[2:]] <= allowed[m]:
                    allowed[m] |= allowed[x[2:]]
                    changed = True
    return allowed


def test_m2_fix4_a_read_two_hands_would_cancel_is_seen_one_hand_at_a_time(monkeypatch):
    """Control: b4.rec.index edited in memory to the difference of the first
    two hands' slot-list lengths. Trimming every hand alike leaves it
    unchanged (the old perturbation's blind spot); one hand at a time moves
    it."""
    orig = cm._record_row

    def edited(rf, rows, series_sc, report):
        row = orig(rf, rows, series_sc, report)
        hd = rf.rec["hd"]
        row["b4.rec.index"] = len(hd[0][crd.SL]) - len(hd[1][crd.SL]) if len(hd) > 1 else 0
        return row
    monkeypatch.setattr(cm, "_record_row", edited)
    fx = crd.fixtures()
    got = crd.dynamic_reads(fx)
    assert "sl" in got.dyn["b4.rec.index"]
    single = crd.perturbations

    def every_hand_alike(rec):
        out = [p for p in single(rec) if p[0] != "sl"]
        r = copy.deepcopy(rec)
        hit = False
        for e in r["hd"]:
            if e[crd.SL]:
                e[crd.SL] = e[crd.SL][:-1]
                hit = True
        if hit:
            out.append(("sl", "every hand trimmed at the last entry", r, None))
        return out
    monkeypatch.setattr(crd, "perturbations", every_hand_alike)
    alike = crd.dynamic_reads(fx)
    assert "sl" not in alike.dyn["b4.rec.index"]


# -- M2: every revision shape the loader accepts, at every evaluator entry point ------------

_SHAPES = {}


def _shapes(tmp_path_factory):
    if not _SHAPES:
        _SHAPES.update(k.build_shapes(tmp_path_factory.mktemp("shapes")))
    return _SHAPES


SHAPE_NAMES = sorted(k.revision_shapes())


@pytest.mark.parametrize("shape", SHAPE_NAMES)
def test_m2_each_revision_shape_at_each_evaluator_entry_point(shape, tmp_path_factory):
    """The unit cells of the revision-shape table: the card evaluator, the
    card case, the card view the worker derives with the revision's weights,
    the window read without a window family, and the seat evaluator the same
    published state runs in the review pass. A shape without card rules
    evaluates to an empty result, never an error."""
    import asyncio
    import review_testkit as tk
    st = _shapes(tmp_path_factory)[shape]
    rs = st.ruleset
    _doc, _cases, has_card = k.revision_shapes()[shape]
    assert (rr.CARD_CORE in rs.core) == has_card == bool(rs.card_rules)
    v = k.view([("a", "b", k.dup_record())], None, None, rs.params.get(cm.WEIGHTS))
    windows = [cm.window_row(dict(c, games=1)) for c in cm.contributions(v)]
    findings, notes, fired, errors = rs.evaluate_card(cm.card_subjects(v, windows))
    assert errors == 0
    if has_card:
        assert k.ID_DUP in fired                                   # control: the card evaluator ran
    else:
        assert (findings, notes, fired, errors) == ([], [], [], 0)
    case = k.quiet_card_cases()[1]["card"]
    got = rs.card_case(case, None)
    assert got == ([k.ID_DUP] if has_card else None)
    if cm.WINDOW not in rs.params:
        assert asyncio.run(ce._windows(None, [("s", None, "self", "one", "p", rs.rev)], rs)) == ([], set())
    records = tk.game()
    _f, _seat_fired, seat_errors = rs.evaluate_game(records, tk.MATCH, tk.registry_of(records))
    assert seat_errors == 0


@pytest.mark.parametrize("shape", [s for s in SHAPE_NAMES if not k.revision_shapes()[s][2]])
def test_m2_a_shape_without_card_rules_refuses_a_card_self_test_case_at_build(shape, tmp_path):
    doc, cases, _card = k.revision_shapes()[shape]
    with pytest.raises(rr.Refused):
        k.build_card_revision(tmp_path, doc, cases + k.quiet_card_cases(), name="with-card-case")
    k.build_card_revision(tmp_path, doc, cases, name="control")    # control: the shape itself builds


def test_m2_the_shape_table_covers_every_shape_the_loader_accepts():
    """The table's rows: seat rules present or not, card rules present or
    not, and with card rules each optional card family present or not."""
    shapes = k.revision_shapes()
    rows = set()
    for name, (doc, _c, has_card) in shapes.items():
        seat = any(r["scope"] != "card" for r in doc["rules"])
        fams = tuple(sorted(f for f in (cm.WEIGHTS, cm.WINDOW) if f in doc["measure_params"]))
        rows.add((seat, has_card, fams))
    every = {(s, c, f) for s in (False, True) for c in (False, True)
             for f in ((), (cm.WEIGHTS,), (cm.WINDOW,), tuple(sorted((cm.WEIGHTS, cm.WINDOW))))}
    print("revision shapes: %d built, %d of %d (seat, card, families) rows" % (len(shapes), len(rows), len(every)))
    assert len(rows) == len(shapes)
    # the rows not built are the same code path as a built one: the seat
    # rules are never read by the card worker, and the card families are
    # read only through rs.params (each family present and absent is built)
    assert {(c, f) for _s, c, f in rows} >= {(True, f) for _s, _c, f in every}


# -- M2: the liveness bound ------------------------------------------------------------------

def test_m2_the_fault_bound_is_pinned_and_the_fault_word_fits_its_column():
    assert ce.CARD_FAULT_LIMITS["attempts"] > 0
    sql = _read(BACKEND, "sql", "370_card_evidence.sql")
    width = int(re.search(r"derive_fault\s+VARCHAR\((\d+)\)", sql).group(1))
    assert ce.CARD_FAULT_LIMITS["word_chars"] == width
    assert "fault_attempts INTEGER NOT NULL DEFAULT 0" in sql and "fault_rev VARCHAR(16) NULL" in sql
    rev_width = int(re.search(r"evaluated_rev\s+VARCHAR\((\d+)\)", sql).group(1))
    assert "fault_rev VARCHAR(%d)" % rev_width in sql


def test_m2_the_parked_word_is_required_and_on_both_arms():
    import schemas
    f = schemas.HealthResponse.model_fields["card_evidence_parked"]
    assert f.annotation is int and f.is_required()
    assert inspect.getsource(_main().health_check).count("card_evidence_parked=_cev.parked()") == 2
    assert ce.parked() == ce.PARKED_UNKNOWN < 0                    # no pass has run in this process


def test_m2_a_visit_that_raises_is_recorded_and_the_pass_moves_on():
    src = inspect.getsource(ce.games_pass)
    assert "await _fault(session_factory, key, lo, hi, rev, st, failed, fp)" in src
    q = ce._CANDIDATES.text
    assert "NOT (COALESCE(g.fault_attempts, 0) >= CAST(:cap AS int)" in q
    assert "g.fault_rev IS NOT DISTINCT FROM CAST(:rev AS varchar)" in q
    # nothing is finalized, signed or stamped evaluated by the fault record
    f = inspect.getsource(ce._fault)
    assert "finalized_at" not in f and "evaluated_rev" not in f and "signature" not in f


# == fix pass 4 ===========================================================================

# -- M3: input generations ---------------------------------------------------------------------

def test_m3_fix4_every_input_carries_a_generation_and_a_visit_records_what_it_read():
    sql = _read(BACKEND, "sql", "370_card_evidence.sql")
    assert "CREATE SEQUENCE IF NOT EXISTS card_input_gen;" in sql
    assert sql.count("gen BIGINT NOT NULL DEFAULT nextval('card_input_gen')") == 2   # records, censuses
    assert "seen_inputs TEXT NULL" in sql
    rb = _read(BACKEND, "sql", "rollback_370_card_evidence.sql")
    assert "DROP SEQUENCE IF EXISTS card_input_gen;" in rb
    # the conflict marker takes a new generation, once, with the marker
    st = inspect.getsource(ce.store_record)
    assert "gen = CASE WHEN conflict_at IS NULL THEN nextval('card_input_gen') ELSE gen END" in st
    # every visit arm records the inputs it read; a faulted one keeps the old
    ev = inspect.getsource(ce.evaluate_card_game)
    assert ev.count("seen_inputs = :fp") == 2
    assert "seen_inputs = CASE WHEN CAST(:fault AS varchar) IS NULL THEN CAST(:fp AS varchar)" in ev
    # the candidate query compares committed inputs with what was read
    q = ce._CANDIDATES.text
    assert "g.seen_inputs IS DISTINCT FROM f.fp" in q and ce._FP_SQL in q
    assert "received_at > g.processed_at" not in q and "registered_at" not in q


def test_m3_fix4_the_python_list_and_the_sql_list_have_one_form():
    rows = [{"gen": 9, "pool_digest": "b"}, {"gen": 4, "pool_digest": None}, {"gen": 12, "pool_digest": "a"}]
    assert ce._inputs_fp(rows, {"a": 7, "b": 3}) == "4:0,9:3,12:7"
    assert ce._inputs_fp(rows[:1], {}) == "9:0"
    # the SQL builds generation, colon, census generation (zero for none), by generation
    assert "e.gen::text || ':' || COALESCE(p.gen, 0)::text" in ce._FP_SQL and "ORDER BY e.gen" in ce._FP_SQL


# -- M4: bounded backoff with re-probe ---------------------------------------------------------

def test_m4_fix4_the_backoff_schedule_doubles_from_its_base_to_its_cap():
    lim = ce.CARD_RETRY_LIMITS
    got = [ce.retry_delay(i) for i in range(10)]
    want = []
    for i in range(10):
        want.append(min(lim["op_cap_s"], lim["op_base_s"] * 2 ** i))
    assert got == want
    assert got[0] == lim["op_base_s"] and got[-1] == lim["op_cap_s"]
    assert ce.retry_delay(-3) == lim["op_base_s"] and ce.retry_delay(10 ** 6) == lim["op_cap_s"]
    assert lim["reprobe_s"] > 0


def _wrapped_driver(err):
    import sqlalchemy.exc as sx
    w = sx.DBAPIError("SELECT", {}, err)
    return w


OPERATIONAL_CASES = [
    "ConnectionError", "TimeoutError", "ConnectionResetError", "sa.OperationalError", "sa.InterfaceError",
    "sa.TimeoutError", "sa.DisconnectionError", "sa.DBAPIError.invalidated", "pg.PostgresConnectionError",
    "pg.ConnectionDoesNotExistError", "pg.InterfaceError", "pg.DeadlockDetectedError",
    "pg.SerializationError", "pg.TooManyConnectionsError", "pg.AdminShutdownError",
    "pg.LockNotAvailableError", "sa.DBAPIError(pg.PostgresConnectionError)", "cause:ConnectionError",
    "context:sa.TimeoutError"]
DETERMINISTIC_CASES = [
    "RuntimeError", "ValueError", "KeyError", "ZeroDivisionError", "card_measures.Refusal",
    "sa.DBAPIError(pg.UniqueViolationError)", "sa.ProgrammingError", "pg.DataError",
    "pg.UndefinedColumnError", "sa.DBAPIError.valid"]


def _exception(name):
    import asyncpg.exceptions as pg
    import sqlalchemy.exc as sx
    if name.startswith("cause:") or name.startswith("context:"):
        how, inner = name.split(":", 1)
        outer = RuntimeError("wrapper")
        if how == "cause":
            outer.__cause__ = _exception(inner)
        else:
            outer.__context__ = _exception(inner)
        return outer
    if name.startswith("sa.DBAPIError("):
        return _wrapped_driver(_exception(name[len("sa.DBAPIError("):-1]))
    if name == "sa.DBAPIError.invalidated":
        return sx.DBAPIError("SELECT", {}, RuntimeError("x"), connection_invalidated=True)
    if name == "sa.DBAPIError.valid":
        return sx.DBAPIError("SELECT", {}, RuntimeError("x"), connection_invalidated=False)
    if name.startswith("sa."):
        cls = vars(sx)[name[3:]]
        if issubclass(cls, sx.StatementError):
            return cls("SELECT", {}, RuntimeError("x"))
        return cls("x")
    if name.startswith("pg."):
        return vars(pg)[name[3:]]("x")
    if name == "card_measures.Refusal":
        return cm.Refusal("x")
    return {"RuntimeError": RuntimeError, "ValueError": ValueError, "KeyError": KeyError,
            "ZeroDivisionError": ZeroDivisionError, "ConnectionError": ConnectionError,
            "TimeoutError": TimeoutError, "ConnectionResetError": ConnectionResetError}[name]("x")


@pytest.mark.parametrize("name", OPERATIONAL_CASES)
def test_m4_fix4_an_operational_failure_is_classified_operational(name):
    assert ce.operational(_exception(name)) is True


@pytest.mark.parametrize("name", DETERMINISTIC_CASES)
def test_m4_fix4_any_other_failure_is_deterministic(name):
    assert ce.operational(_exception(name)) is False


def test_m4_fix4_an_operational_failure_never_counts_toward_the_park():
    assert "fault_attempts" not in ce._OP_RETRY and "parked_at" not in ce._OP_RETRY
    assert "fault_inputs" not in ce._OP_RETRY
    f = inspect.getsource(ce._fault)
    assert f.count("_OP_RETRY") == 1 and f.count("_FAULT_COUNT") == 1
    assert "if is_operational:" in f
    # a deterministic fault ends an operational backoff; a completed visit clears both
    assert "op_attempts = 0, retry_at = NULL" in ce._FAULT_COUNT
    for col in ("derive_fault = NULL", "fault_attempts = 0", "fault_rev = NULL", "fault_inputs = NULL",
                "parked_at = NULL", "op_attempts = 0", "retry_at = NULL"):
        assert col in ce._CLEAR


def test_m4_fix4_a_parked_game_is_re_probed_and_a_waiting_retry_is_held():
    q = ce._CANDIDATES.text
    assert "(g.retry_at IS NULL OR g.retry_at <= now())" in q
    assert "g.fault_inputs IS NOT DISTINCT FROM f.fp" in q
    assert "g.processed_at > now() - make_interval(secs => CAST(:reprobe AS int))" in q
    src = inspect.getsource(ce.games_pass)
    assert '"reprobe": CARD_RETRY_LIMITS["reprobe_s"]' in src


def test_m4_fix4_the_parked_age_is_required_and_on_both_arms():
    import schemas
    f = schemas.HealthResponse.model_fields["card_evidence_parked_oldest_s"]
    assert f.annotation is int and f.is_required()
    assert inspect.getsource(_main().health_check).count(
        "card_evidence_parked_oldest_s=_cev.parked_oldest_s()") == 2
    assert ce.parked_oldest_s() == ce.PARKED_UNKNOWN < 0


def test_m4_fix4_the_retry_limits_are_pinned():
    sys.path.insert(0, os.path.join(BACKEND, "tools"))
    import review_guard as rg
    assert rg.PINNED[("card_evidence", "CARD_RETRY_LIMITS")] == ce.CARD_RETRY_LIMITS


# -- LOW 3: every completed visit clears derive_fault ------------------------------------------

def test_low3_fix4_every_completed_visit_arm_clears_every_fault_field():
    ev = inspect.getsource(ce.evaluate_card_game)
    # the no-revision arm and the unchanged arm write _CLEAR; the deriving arm
    # writes derive_fault = :fault with the fault counts (none: all cleared)
    assert ev.count("+ _CLEAR +") == 2
    assert "derive_fault = :fault" in ev and "+ _FAULT_COUNT +" in ev
