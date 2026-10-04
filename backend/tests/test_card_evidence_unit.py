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
    assert cm.contributions(k.view([("a", "b", rec)], [c], None, k.WEIGHTS), k.WEIGHTS)[0]["hands"] == 0
    c = k.fixture_census("full_game")
    rec = k.on_census(k.fixture_record("full_game"), c)
    assert k.hand(k.view([("a", "b", rec)], [c], None, k.WEIGHTS), 0)["b4.hand.eligible"] == 1


def test_no_weights_means_no_expectation_and_no_contribution():
    rec, c = _full_on()
    v = k.view([("a", "b", rec)], [c], None, None)
    assert all(r["b4.hand.eligible"] == 0 for r, _m in v["hands"])
    assert cm.contributions(v, None) == []


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
    one = cm.contributions(k.view([("a", "b", rec)], [c], "off", k.WEIGHTS), k.WEIGHTS)
    two = cm.contributions(k.view([("a", "b", rec), ("b", "a", k.mirror(rec))], [c], "off", k.WEIGHTS),
                           k.WEIGHTS)
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
    assert rm.REGISTRY[cm.WINDOW].data == [cm.WINDOW_KEY]
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
