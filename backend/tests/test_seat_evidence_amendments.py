"""Seat evidence contract amendments adopted from the client half (2026-10-02):

  A1  an OPTIONAL `end` key right after `rounds` ("left", "other_left",
      "lost", "closing"): accepted, kept in place by the budgeter, never
      removed; a record without it keeps the contract V2 key set and bytes;
  A2  a path-1 `hit_sent` entry is the one-sided kind `shooter_only_direct`
      (contract text only: the server never looks one up as a missing pair);
  A3  a cut game's `rounds` and attach key follow the report (contract text
      only: attachment is by exact key, unchanged);
  D1  the drift row's wording (contract text only: nothing on the wire).

The client half's canonical fixtures (tools/tests/seat-evidence-client,
run_tests.py at client commit 117dae0a, key "fixture-key-not-a-secret") are
checked in under fixtures/seat_evidence_client byte for byte: the server's own
budgeter must produce each record text exactly, and the envelope, the record
(two of them carry `end`) and the signature must be accepted."""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import seat_evidence as se  # noqa: E402
import seat_evidence_fixtures as fx  # noqa: E402

CLIENT = os.path.join(HERE, "fixtures", "seat_evidence_client")
CLIENT_KEY = "fixture-key-not-a-secret"


def _cases():
    return open(os.path.join(CLIENT, "cases.txt"), encoding="ascii").read().split()


def _read(name, ext, mode="r"):
    with open(os.path.join(CLIENT, name + ext), mode) as f:
        return f.read()


def with_end(rec, kind):
    """The record with `end` inserted right after `rounds`."""
    out = {}
    for k, v in rec.items():
        out[k] = v
        if k == "rounds":
            out["end"] = kind
    return out


def reference_with_end(full):
    """The client's statement of A1, independently of the server's code: the
    record without `end` budgeted under a limit smaller by the key's constant
    bytes, with the key put back after `rounds`."""
    rest = {k: v for k, v in full.items() if k != "end"}
    ins = ',"end":' + json.dumps(full["end"])
    text = se.budget_record(rest, limit=se.RECORD_MAX_BYTES - len(ins))
    at = text.index(',"build":')
    return text[:at] + ins + text[at:]


# -- the client's canonical fixtures, byte for byte ---------------------------------------

def test_the_client_fixture_set_is_complete_and_two_carry_end():
    names = _cases()
    assert len(names) == 8
    ends = [n for n in names if "end" in json.loads(_read(n, ".input.json"))]
    assert sorted(ends) == ["end_closing_over", "end_left"]


@pytest.mark.parametrize("name", _cases())
def test_the_servers_budgeter_reproduces_each_client_record_byte_for_byte(name):
    full = json.loads(_read(name, ".input.json"))
    assert se.budget_record(full).encode("ascii") == _read(name, ".record.txt", "rb")


@pytest.mark.parametrize("name", _cases())
def test_each_client_envelope_parses_checks_and_verifies(name):
    env = se.parse_envelope(json.loads(_read(name, ".envelope.json")))
    rec = se.parse_record(env)
    assert env["record_bytes"] == _read(name, ".record.txt", "rb")
    assert se.verify_sig(CLIENT_KEY, env)
    assert not se.verify_sig(CLIENT_KEY + "x", env)                      # the key matters
    full = json.loads(_read(name, ".input.json"))
    assert rec.get("end") == full.get("end")


def test_the_client_compat_body_is_accepted():
    c = se.check_compat(json.loads(_read("compat", ".json")))
    assert se.verify_compat_sig(CLIENT_KEY, c)


def test_a_one_byte_change_in_a_client_record_is_seen():
    full = json.loads(_read("end_left", ".input.json"))
    mine = bytearray(_read("end_left", ".record.txt", "rb"))
    mine[-2] = ord("9") if mine[-2] != ord("9") else ord("8")
    assert se.budget_record(full).encode("ascii") != bytes(mine)


# -- A1 against the server's own fixtures -------------------------------------------------

@pytest.mark.parametrize("kind", se.END_KINDS)
def test_a1_each_end_kind_is_accepted_right_after_rounds(kind):
    rec = with_end(fx.base_record(), kind)
    se.check_record(rec)
    text = se.budget_record(rec)
    assert '"rounds":' in text and text.index('"end":') > text.index('"rounds":')
    assert text.index('"end":') < text.index('"build":')
    assert json.loads(text)["end"] == kind


def test_a1_a_record_without_end_keeps_the_v2_key_set_and_bytes():
    rec = fx.base_record()
    assert se.record_keys(rec) == se.RECORD_KEYS and "end" not in se.RECORD_KEYS
    assert list(json.loads(se.budget_record(rec)).keys()) == list(se.RECORD_KEYS)


def test_a1_an_unknown_kind_a_misplaced_end_or_a_non_string_is_refused():
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(with_end(fx.base_record(), "quit"))
    assert e.value.status == 422 and e.value.field == "end"
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(with_end(fx.base_record(), 1))
    assert e.value.field == "end"
    misplaced = dict(fx.base_record(), end="left")                       # appended last
    with pytest.raises(se.EvidenceRefused) as e:
        se.check_record(misplaced)
    assert e.value.status == 422 and e.value.field == "key_order"


def test_a1_the_end_key_is_never_removed_and_the_removal_sequence_matches_the_reference():
    full = with_end(fx.worst_case_record(), "closing")
    text = se.budget_record(full)
    assert len(text.encode("ascii")) <= se.RECORD_MAX_BYTES
    assert json.loads(text)["end"] == "closing"
    assert text == reference_with_end(full)
    se.check_record(json.loads(text))


def test_a1_a_signed_envelope_with_end_parses_and_verifies():
    body = fx.envelope(with_end(fx.base_record(), "other_left"))
    env = se.parse_envelope(body)
    assert se.parse_record(env)["end"] == "other_left"
    assert se.verify_sig(fx.KEY, env)
