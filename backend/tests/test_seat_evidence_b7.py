"""Seat evidence (contract V2), the amended B7 (2026-10-04): every hit_sent
entry has ten elements, the tenth `reset` the copy's last-reset state at the
decision, a closed enum: 0 none (since_ms -1, last_* [0,-1,0]), 1 keyed
(since_ms 0..600000, last_kind 0..9), 2 unkeyed (since_ms 0..600000, last_*
[0,-1,0]). Every other combination is refused with 422 naming the FIRST
failing rule in the contract's order (reset_none_since, reset_none_last,
reset_keyed_since, reset_keyed_last, reset_unkeyed_since, reset_unkeyed_last);
a wrong length or a reset outside 0..2 is refused by the entry bound (field
hit_sent). The old names (hit_sent.since_unset_with_block,
hit_sent.since_set_without_block, hit_sent.last) are retired.

Here, with no database:
  * the parser against an oracle written from the contract text, over a grid
    of every (since_ms, last_*, reset) class, plus the shape refusals;
  * the CLIENT lane's generated fixtures (copied byte for byte from
    tools/tests/seat-evidence-client/server_fixtures at client commit
    be00e3a8, pinned below by sha256) through the REAL parser: for every
    record the envelope carries its exact bytes, the budgeter reproduces
    them and the signature verifies, and all eight complete records pass
    the whole check as they are. At the earlier fixture set (client tip
    b4fe3710) seven of them carried path-1 hit_recv entries, a fault of the
    client's test generator (production writes path 0), and were refused
    as hit_recv.path; at the regenerated set they are accepted. The
    parser's refusal of a path-1 hit_recv entry stays, with its own
    negative test below on a client record; the 7700-entry state space
    admitted; the client's 20 refused combinations refused with the same
    names;
  * the measures: the case table reads each state as itself (an unkeyed
    reset is a real reset with no key, never absent, never keyed), and an
    entry without the state is refused, never misread;
  * the lift used only by the equivalence replay of frozen pre-amendment games.
The stored-and-read-back half is in test_seat_evidence_live.py."""

import hashlib
import itertools
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_measures as rm  # noqa: E402
import review_testkit as tk  # noqa: E402
import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402

CLIENT = os.path.join(HERE, "fixtures", "seat_evidence_client_b7")
CLIENT_KEY = "fixture-key-not-a-secret"        # the client harness's public fixture key
SENTINEL = [0, -1, 0]
SIX = ("hit_sent.reset_none_since", "hit_sent.reset_none_last", "hit_sent.reset_keyed_since",
       "hit_sent.reset_keyed_last", "hit_sent.reset_unkeyed_since", "hit_sent.reset_unkeyed_last")
RETIRED = ("hit_sent.since_unset_with_block", "hit_sent.since_set_without_block", "hit_sent.last")

# The client fixtures as copied (client commit be00e3a8, the regenerated
# server_fixtures): one sha256 per file, and the digest of the sorted
# "<sha256>  <name>\n" lines. The earlier set (client tip b4fe3710) had the set
# digest 91d17ee3d4f4cde37516f88aa5c7766b91e6e2879c70c512c9588affcbc17ac6.
CLIENT_SET_SHA256 = "f995a6b02d8e267f238fe74c81ca9040771a1db2d48ca40e9792ef425e220ca5"
CLIENT_FILES = {
    "b7_negative.json": "a936def566f8cddf2cced035d1cfa4864f467c64150beb40b01b0d5e4888f5c0",
    "b7_states.json": "ce22c9d91bf1ed1b0f3d4758d73f1df04aaf2387e3a1e30327ff82098b4ce02d",
    "cap160.envelope.json": "32365878babb1b6db8267b5a3cb0205e533bbbf96db39148ff87c2f6feae305e",
    "cap160.input.json": "422d1cb4f26e92e59a48893191d2765bb3d35a4cd4915ff904c48578fd758fc5",
    "cap160.record.txt": "ab2e6c1eebad277051e949ab89e77b833b9acdf32df73a63a89e2c2776c99684",
    "cases.txt": "f7c0b30f57055181229691f76a49b75cb377b793c10b726f48832ecfdde73b9a",
    "compat.json": "1006e9f066d710698fac0d8607a6870b97617ee9003aee5d5258d25d41dd1efe",
    "empty.envelope.json": "891d29476bda5e4eee8259ed568cdec49fe8ac2c756105e6d7a81a06d61a86c8",
    "empty.input.json": "4d03488763b2cfe0af8bb957f77a24cc0f23cfa67580043efe204423b6a145d6",
    "empty.record.txt": "4d03488763b2cfe0af8bb957f77a24cc0f23cfa67580043efe204423b6a145d6",
    "end_closing_over.envelope.json": "3a3d4fd4b7cded0783251fd6b2033fffb73d3795ec283a3cd067c55b54f7b408",
    "end_closing_over.input.json": "e6ad2ae3f645d9cdc53e4f52cfbde5f61b1891a7ed39adc2ede8177d4af8462e",
    "end_closing_over.record.txt": "8488dce43672f3f38e1d7a3f023784afbfd4c12473cd503e7a792377b3f820b1",
    "end_left.envelope.json": "f93cd1b975a9ef8da788f23811caa4276788d16720f0305dc2ea9ebea81a8c64",
    "end_left.input.json": "177f89d55e01cb9062fd047050a82ed69cd8c326b1c74cb04c2425df38b3debf",
    "end_left.record.txt": "177f89d55e01cb9062fd047050a82ed69cd8c326b1c74cb04c2425df38b3debf",
    "nulls.envelope.json": "09cb050b88bc1c3ee143cccae017a40c03db8f595dd95746663bf4b77ffd4a47",
    "nulls.input.json": "bacfd11de1e8652866d32291d74ee7f873d51fd7d93e4733a94583eae7615a4a",
    "nulls.record.txt": "bacfd11de1e8652866d32291d74ee7f873d51fd7d93e4733a94583eae7615a4a",
    "over160_wide.envelope.json": "d7c0dd7e7b94d0b22527d1a98463ba4b1d77ffcb5bbedc9bdf8bee93d438eae1",
    "over160_wide.input.json": "13ec64f6bc32a8f950355f1fbb4b5f08b7e0773993e2fe8630c1a9acc09ac54c",
    "over160_wide.record.txt": "0284f835bae8a9dc01c9fbd7fec914fe9575d6e05255636649b0a9d6d96d6015",
    "pub_omit_seed.envelope.json": "7ab2419c1359463abce9ff1f6863db7855bce7d69a9845a70540818081fd66f9",
    "pub_omit_seed.input.json": "9d0f75ca416eff4902773bcf02f257c8af6fd8fbe5dd27cbfaae3a2f2f66db47",
    "pub_omit_seed.record.txt": "9d0f75ca416eff4902773bcf02f257c8af6fd8fbe5dd27cbfaae3a2f2f66db47",
    "small.envelope.json": "0f0a57b95f5eb4b9b48f4a3e091fa2e7a27213a2175099dc982e394a32f37f49",
    "small.input.json": "44052afb673dbbe0ee3f09536a5921b7f0779140aa48a62bd61610f6d4f5d46e",
    "small.record.txt": "44052afb673dbbe0ee3f09536a5921b7f0779140aa48a62bd61610f6d4f5d46e",
}
CLIENT_CASES = ["small", "cap160", "over160_wide", "empty", "nulls", "pub_omit_seed", "end_left",
                "end_closing_over"]


def _client(name, mode="rb"):
    with open(os.path.join(CLIENT, name), mode) as f:
        return f.read()


def _verdict(entry):
    """The parser's answer for one hit_sent entry in an otherwise valid
    record: None (accepted) or the refused field."""
    try:
        se.check_record(fx.base_record(hit_sent=[entry]))
    except se.EvidenceRefused as e:
        assert e.status == 422
        return e.field
    return None


def contract_b7(since, last, reset):
    """The amended B7 as the contract text states it (written here from the
    text, independent of the module): the field of the FIRST failing rule in
    the contract's order, or None."""
    if reset == 0:
        if since >= 0:
            return "hit_sent.reset_none_since"
        if last != SENTINEL:
            return "hit_sent.reset_none_last"
    elif reset == 1:
        if since == -1:
            return "hit_sent.reset_keyed_since"
        if last[1] == -1:
            return "hit_sent.reset_keyed_last"
    elif reset == 2:
        if since == -1:
            return "hit_sent.reset_unkeyed_since"
        if last != SENTINEL:
            return "hit_sent.reset_unkeyed_last"
    return None


SINCES = (-1, 0, 250, 600000)
LASTS = ([0, -1, 0], [5, 2, 1], [0, 0, 0], [-7, 9, 255], [0, -1, 3], [7, -1, 0], [7, -1, 2])


# -- the parser ----------------------------------------------------------------

@pytest.mark.parametrize("since,last,reset", list(itertools.product(SINCES, LASTS, (0, 1, 2))))
def test_b7_every_combination_is_answered_as_the_contract_text_says(since, last, reset):
    entry = [0, 7, 0, 0, since, 0] + list(last) + [reset]
    assert _verdict(entry) == contract_b7(since, last, reset)


def test_b7_the_grid_reaches_every_state_and_every_named_refusal():
    seen = {contract_b7(s, list(l), r) for s, l, r in itertools.product(SINCES, LASTS, (0, 1, 2))}
    assert seen == set(SIX) | {None}


@pytest.mark.parametrize("entry,state", [
    ([0, 7, 0, 0, -1, 0, 0, -1, 0, 0], "none"),
    ([1, 7, 9, 3, -1, 1, 0, -1, 0, 0], "none"),
    ([0, 7, 0, 0, 0, 0, 5, 0, 0, 1], "keyed"),
    ([0, 7, 0, 0, 600000, 1, -2147483648, 9, 255, 1], "keyed"),
    ([0, 7, 0, 0, 0, 0, 0, -1, 0, 2], "unkeyed"),
    ([0, 7, 0, 0, 600000, 1, 0, -1, 0, 2], "unkeyed"),
])
def test_b7_each_valid_state_is_accepted_at_its_bounds(entry, state):
    assert _verdict(entry) is None
    assert se.RESET_NAMES[entry[9]] == state


@pytest.mark.parametrize("entry,field", [
    # each rule alone
    ([0, 7, 0, 0, 0, 0, 0, -1, 0, 0], "hit_sent.reset_none_since"),
    ([0, 7, 0, 0, -1, 0, 0, -1, 1, 0], "hit_sent.reset_none_last"),
    ([0, 7, 0, 0, -1, 0, 5, 2, 1, 1], "hit_sent.reset_keyed_since"),
    ([0, 7, 0, 0, 50, 0, 0, -1, 0, 1], "hit_sent.reset_keyed_last"),
    ([0, 7, 0, 0, -1, 0, 0, -1, 0, 2], "hit_sent.reset_unkeyed_since"),
    ([0, 7, 0, 0, 50, 0, 5, 2, 1, 2], "hit_sent.reset_unkeyed_last"),
    # both rules of one state broken: the since rule is named (it is first)
    ([0, 7, 0, 0, 50, 0, 5, 2, 1, 0], "hit_sent.reset_none_since"),
    ([0, 7, 0, 0, -1, 0, 7, -1, 2, 1], "hit_sent.reset_keyed_since"),
    ([0, 7, 0, 0, -1, 0, 5, 2, 1, 2], "hit_sent.reset_unkeyed_since"),
])
def test_b7_each_of_the_six_refusals_is_named_and_the_first_failing_rule_wins(entry, field):
    assert _verdict(entry) == field


@pytest.mark.parametrize("entry", [
    [0, 7, 0, 0, -1, 0, 0, -1, 0],                  # nine elements: the old shape
    [0, 7, 0, 0, 50, 0, 5, 2, 1],                   # nine elements, a valid old keyed pair
    [0, 7, 0, 0, -1, 0, 0, -1, 0, 0, 0],            # eleven
    [0, 7, 0, 0, 50, 0, 0, -1, 0, 3],               # reset above the enum
    [0, 7, 0, 0, -1, 0, 0, -1, 0, -1],              # reset below the enum
    [0, 7, 0, 0, 50, 0, 5, 2, 1, True],             # a boolean is not an integer here
    [0, 7, 0, 0, 50, 0, 5, 2, 1, "1"],
    [0, 7, 0, 0, 50, 0, 5, 2, 1, None],
])
def test_b7_a_wrong_length_or_reset_value_is_refused_by_the_entry_bound(entry):
    assert _verdict(entry) == "hit_sent"


def test_b7_the_retired_names_are_gone_from_the_module_and_never_answered():
    src = open(os.path.join(HERE, "..", "api", "seat_evidence.py"), encoding="utf-8").read()
    code = "\n".join(line.split("#", 1)[0] for line in src.splitlines())   # comments may cite them
    for name in RETIRED:
        assert '"%s"' % name not in code, name
    answers = {_verdict([0, 7, 0, 0, s] + [0] + list(l) + [r])
               for s, l, r in itertools.product(SINCES, LASTS, (0, 1, 2))}
    assert not answers & set(RETIRED)


def test_b7_the_parser_enum_and_the_measures_enum_are_the_same_three_values():
    assert se.RESET_NAMES == ("none", "keyed", "unkeyed")
    assert (se.RESET_NAMES.index("none"), se.RESET_NAMES.index("keyed"),
            se.RESET_NAMES.index("unkeyed")) == (rm.RESET_NONE, rm.RESET_KEYED, rm.RESET_UNKEYED)
    assert rm.HIT_SENT_LEN == 10
    assert se.ENTRY["hit_sent"]([0, 7, 0, 0, -1, 0, 0, -1, 0, 0])
    assert not se.ENTRY["hit_sent"]([0, 7, 0, 0, -1, 0, 0, -1, 0])


def test_b7_the_contract_copy_carries_the_amendment_the_parser_implements():
    path = os.path.normpath(os.path.join(HERE, "..", "..", "..", "SidsCompetitiveRounds", "ai-collab",
                                         "integrity-1001", "SEAT-EVIDENCE-CONTRACT-V2.md"))
    if not os.path.exists(path):
        pytest.skip("the contract copy lives in the integrator's ai-collab tree, not in this repository")
    text = open(path, encoding="utf-8").read()
    assert "AMENDMENT 2026-10-04" in text
    for name in SIX:
        assert "`%s`" % name in text, name
    order = [text.index("`%s` (" % n) for n in SIX]
    assert order == sorted(order)                 # the contract lists them in the parser's order


def test_b7_budget_effect_is_exactly_two_bytes_per_entry_and_the_cap_is_unchanged():
    nine = [1, -2147483648, 2147483647, 255, 600000, 1, -2147483648, 9, 255]
    assert len(se._dumps(nine + [1])) - len(se._dumps(nine)) == 2
    assert se.LIST_CAP == 160 and se.RECORD_MAX_BYTES == 12288


# -- the client lane's generated fixtures through the REAL parser --------------

def test_client_fixtures_are_the_pinned_bytes():
    names = sorted(os.listdir(CLIENT))
    assert names == sorted(CLIENT_FILES)
    lines = ""
    for n in names:
        digest = hashlib.sha256(_client(n)).hexdigest()
        assert digest == CLIENT_FILES[n], n
        lines += "%s  %s\n" % (digest, n)
    assert hashlib.sha256(lines.encode("ascii")).hexdigest() == CLIENT_SET_SHA256
    assert _client("cases.txt").decode("ascii").split() == CLIENT_CASES


@pytest.mark.parametrize("case", CLIENT_CASES)
def test_client_record_bytes_and_hit_sent_entries_pass_the_real_parser(case):
    """Every client record: the envelope's bytes, signature and the shared
    budgeter agree byte for byte, and the record passes the whole check as it
    is, B7 included. Every hit_recv entry is path 0 (contract A2)."""
    mine = _client(case + ".record.txt")
    body = json.loads(_client(case + ".envelope.json").decode("ascii"))
    env = se.parse_envelope(body)
    assert env["record_bytes"] == mine                           # the bytes the client sent
    assert se.verify_sig(CLIENT_KEY, env)
    full = json.loads(_client(case + ".input.json").decode("ascii"))
    assert se.budget_record(full).encode("ascii") == mine        # the shared budgeter agrees
    rec = se.parse_record(env)                                   # the whole check, B7 included
    assert all(x[0] == 0 for x in rec["hit_recv"])
    assert rec["hit_sent"] or case == "empty"
    assert all(len(x) == 10 for x in rec["hit_sent"])
    assert {se.RESET_NAMES[x[9]] for x in rec["hit_sent"]} <= set(se.RESET_NAMES)


def test_client_record_with_one_path_one_hit_recv_entry_is_refused_by_name():
    """The parser's refusal of a path-1 hit_recv entry (contract A2) stays: a
    client record carrying hit_recv entries, with only the first entry's path
    set to 1, is refused as hit_recv.path; the record as sent is accepted."""
    case = next(c for c in CLIENT_CASES
                if json.loads(_client(c + ".record.txt").decode("ascii"))["hit_recv"])
    raw = json.loads(_client(case + ".record.txt").decode("ascii"))
    se.check_record(raw)
    bad = dict(raw, hit_recv=[[1] + raw["hit_recv"][0][1:]] + raw["hit_recv"][1:])
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(bad)
    assert (e.value.status, e.value.field) == (422, "hit_recv.path")


def test_client_records_carry_all_three_states_between_them():
    states = set()
    for case in CLIENT_CASES:
        states |= {e[9] for e in json.loads(_client(case + ".record.txt").decode("ascii"))["hit_sent"]}
    assert states == {0, 1, 2}


def test_client_compat_body_is_accepted_and_its_signature_verifies():
    c = se.check_compat(json.loads(_client("compat.json").decode("ascii")))
    assert se.verify_compat_sig(CLIENT_KEY, c)


def test_client_state_space_is_admitted_by_the_real_parser():
    states = json.loads(_client("b7_states.json").decode("ascii"))
    assert len(states) == 7700
    per = {0: 0, 1: 0, 2: 0}
    for i in range(0, len(states), se.LIST_CAP):
        chunk = states[i:i + se.LIST_CAP]
        se.check_record(fx.base_record(hit_sent=chunk))
        for e in chunk:
            per[e[9]] += 1
    assert per == {0: 4200, 1: 1750, 2: 1750}


def test_client_refused_combinations_are_refused_with_the_same_names():
    neg = json.loads(_client("b7_negative.json").decode("ascii"))
    assert len(neg) == 20
    got = [(want, _verdict(e)) for want, e in neg]
    assert [g for w, g in got] == [w for w, g in got]
    assert {w for w, _ in neg} == set(SIX) | {"hit_sent"}


# -- the measures: each state read as itself -------------------------------------

TB = 100000
P_CASE = tk.synthetic_doc()["measure_params"]["params.case_table"]


def _pair(sent):
    """A victim that raised one window-opening block at TB and took one
    unhonoured hit 100 ms later, and a shooter whose copy received that block,
    ran its reset before the hit, and sent the hit as `sent` (since_ms,
    last_*, reset)."""
    since, last, reset = sent
    victim = fx.base_record(blk_sent=[[TB, 0, 0, 0]],
                            hit_recv=[[0, TB + 100, 0, 0, TB + 101, 0, 1, -1]])
    shooter = fx.base_record(blk_recv=[[TB, 0, 0, TB + 10, 1]],
                             hit_sent=[[0, TB + 100, 0, 0, since, 0] + list(last) + [reset]])
    for r in (victim, shooter):
        se.check_record(r)
    return victim, shooter


def _cls(sent):
    victim, shooter = _pair(sent)
    rows = rm.classify_blocks(victim, shooter, P_CASE)["rows"]
    assert len(rows) == 1
    return rows[0]["cls"]


@pytest.mark.parametrize("sent,cls", [
    ((50, [TB, 0, 0], 1), "c"),                    # keyed on this block, inside its window
    ((P_CASE["window_ms"], [TB, 0, 0], 1), "expired"),
    ((50, [TB + 5, 0, 0], 1), "other_window"),     # keyed on another block
    ((50, SENTINEL, 2), "unkeyed_reset"),          # a real reset that named no block
    ((-1, SENTINEL, 0), "no_reset"),               # no reset seen at the decision
])
def test_measures_the_case_table_reads_each_state_as_itself(sent, cls):
    assert _cls(sent) == cls


def test_measures_unkeyed_is_never_read_as_absent_nor_as_keyed():
    unkeyed, none_ = _cls((50, SENTINEL, 2)), _cls((-1, SENTINEL, 0))
    assert unkeyed != none_
    assert unkeyed not in ("c", "expired", "other_window", "no_reset")
    victim, shooter = _pair((50, SENTINEL, 2))
    counts = rm.classify_blocks(victim, shooter, P_CASE)["counts"]
    assert counts["unkeyed_reset"] == 1 and counts["no_reset"] == 0 and counts["c"] == 0


def test_measures_an_entry_without_its_state_is_refused_never_misread():
    victim, shooter = _pair((50, [TB, 0, 0], 1))
    shooter["hit_sent"] = [e[:9] for e in shooter["hit_sent"]]   # the shape before the amendment
    with pytest.raises(ValueError, match="last-reset state"):
        rm.classify_blocks(victim, shooter, P_CASE)
    with pytest.raises(ValueError, match="last-reset state"):
        rm.reset_state([0, 7, 0, 0, -1, 0, 0, -1, 0])
    assert rm.reset_state([0, 7, 0, 0, -1, 0, 0, -1, 0, 2]) == rm.RESET_UNKEYED


def test_measures_the_game_view_carries_the_two_new_classes():
    victim, shooter = _pair((50, SENTINEL, 2))
    records = [{"seat": "a", "other": "b", "rec": victim, "header_version": "1.41.0", "conflict": False},
               {"seat": "b", "other": "a", "rec": shooter, "header_version": "1.41.0", "conflict": False}]
    view = rm.game_view(records, None, set(), tk.synthetic_doc()["measure_params"])
    counts = view["case_table"][0]["counts"]
    assert counts["unkeyed_reset"] == 1 and "no_reset" in counts


# -- the lift for the frozen pre-amendment games (equivalence replay only) ---------

def test_lift_maps_the_old_pairs_to_none_or_keyed_and_never_invents_unkeyed():
    recs = [{"rec": fx.base_record(hit_sent=[[0, 7, 0, 0, -1, 0, 0, -1, 0],
                                             [0, 8, 0, 0, 50, 0, 5, 2, 1],
                                             [0, 9, 0, 0, 50, 0, 5, 2, 1, 1]])}]
    before = json.dumps(recs)
    out = fx.lift_hit_sent(recs)
    assert json.dumps(recs) == before                              # the input is not modified
    assert [e[9] for e in out[0]["rec"]["hit_sent"]] == [0, 1, 1]
    se.check_record(out[0]["rec"])


@pytest.mark.parametrize("entry", [
    [0, 7, 0, 0, 50, 0, 0, -1, 0],     # since set with the no-block tuple: unkeyed or a lost key
    [0, 7, 0, 0, -1, 0, 5, 2, 1],      # since unset with a block named
    [0, 7, 0, 0, 50, 0, 7, -1, 2],     # a partial no-block tuple
    [0, 7, 0, 0, 50, 0, 5, 2],         # eight elements
])
def test_lift_refuses_what_the_old_coupling_refused(entry):
    with pytest.raises(fx.NotLiftable):
        fx.lift_hit_sent([{"rec": fx.base_record(hit_sent=[entry])}])


def test_lift_is_what_the_equivalence_replay_uses():
    src = open(os.path.join(HERE, "test_review_equivalence.py"), encoding="utf-8").read()
    body = src[src.index("def _game_result("):]
    body = body[:body.index("\ndef ")]
    assert re.search(r"rs\.evaluate_game\(fx\.lift_hit_sent\(g\[\"records\"\]\)", body)
