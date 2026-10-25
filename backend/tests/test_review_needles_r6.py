"""Fix pass 6 for the private-needle check: a store holding revisions of the
PRE-CLOSURE rules document shape derives every needle class, against
SYNTHETIC planted stores only.

The pre-closure shape is what the public writer (backend/api/review_rules.py)
wrote before commit 23bf1ade: no `closure` key, and `vocabulary` a map of
entry name -> that entry's fingerprint (a sha256 hex the writer recorded from
the binder), where the current writer records a list of the names.

  * L1: a document whose vocabulary is a map is accepted when every key is a
    string; its names are the vocabulary (a sitting argument naming one is a
    public name, not a value), and its values are derived as data-table
    values are (class `value`). Every other check is the current shape's.
  * L2: a refusal names the revision folder and the reason, never a value.
  * L3: the controls. The counts below are counted by hand from the planted
    documents (the derivation rule per leaf type is review_needles.LEAF_TYPES
    and _value_needles). Every planted value is made at run time (round 7
    recut) from this file's seed SEED: LITERAL and MEMBER are numbers of the
    bare magnitude, FRACTION a fraction, SMALL a number under the bare
    magnitude and LONG a string of the bare length; no line writes one, and
    no line holds a key beside one. Counts are spelled out in words.
      current revision (CUR): rule_id one, nonce one, wording one, data none,
        value four
        value: LITERAL beside its key: two key-adjacent forms (either order),
               one comparison form and one sign form, four
      pre-closure revision (OLD): rule_id two, nonce one, wording two, data
        two, value twenty-five
        value: vocabulary value FP1 under its two keys (the entry name and
               its tail): two keys by two forms and one bare string, five
               vocabulary value FP2, the same, five
               FRACTION beside its key: two key-adjacent and two bare, four
               the sitting window argument SMALL (under the bare
               magnitude): two key-adjacent forms
               the sitting argument num = side.shots_hit: a vocabulary NAME,
               none
               the legacy table: its key (a short string) beside the table
               name, two; MEMBER beside that key, two and two bare, four;
               LONG beside it, two and one bare, three; one numeric member
               only, so no adjacent-member form and no slash form: nine
               in all five, five, four, two and nine, twenty-five (the
               vocabulary map's share: ten)
        data:  legacy_table.json and legacy_table (shipped and referenced)
      both: rule_id three, nonce two, wording three, data two, value
        twenty-nine; listed and basename none everywhere (no tests/ and no
        private file)
    A pre-closure map with a key that is not a string refuses naming its
    folder; a vocabulary of a third shape (a string, a number, null) and a
    pre-closure document whose closure is not an object refuse naming theirs.
"""

import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))

import review_needles as rn  # noqa: E402


def _hex(seed, n=64):
    return hashlib.sha256(seed.encode()).hexdigest()[:n]


FP1 = _hex("fix six pre-closure fingerprint one")
FP2 = _hex("fix six pre-closure fingerprint two")
NONCE_CUR = _hex("fix six current nonce", 32)
NONCE_OLD = _hex("fix six pre-closure nonce", 32)
CUR = "rules-f6c0000000c1"
OLD = "rules-f6b0000000b1"
THIRD = "rules-f6d0000000d1"
BADKEY = "rules-f6e0000000e1"
CLASSES = ("rule_id", "nonce", "wording", "data", "value", "listed", "basename")


SEED = "test_review_needles_r6"


def _number(tag, lo, span):
    """A synthetic number of this file's seed: lo plus a hash of SEED and tag, modulo span."""
    return lo + int(_hex(SEED + " " + tag), 16) % span


LITERAL = _number("literal", 6000, 900)            # of the bare magnitude
FRACTION = _number("fraction", 11, 88) / 100.0     # a fraction
SMALL = _number("small", 2, 8)                     # under the bare magnitude
MEMBER = _number("member", 30000, 900)             # of the bare magnitude
LONG = "pv" + "".join(chr(ord("a") + int(c, 16)) for c in _hex(SEED + " long", 8))   # of the bare length
CONTROL = 98765                                    # a number no planted revision holds


def _current():
    return {"format": 1, "nonce": NONCE_CUR, "vocabulary": ["seat.published_hits", "op.cmp"], "closure": {},
            "measure_params": {},
            "rules": [{"id": "r0000f6c1", "scope": "game", "subject": "seat", "effect": "flag", "post": False,
                       "post_since": None,
                       "when": {"op": "op.cmp", "args": {"a": {"m": "seat.published_hits"}, "b": {"v": LITERAL}}},
                       "show": [["seat", "seat.index"]], "line": "current shape control {seat}"}]}


def _pre_closure():
    return {"format": 1, "nonce": NONCE_OLD,
            "vocabulary": {"seat.published_hits": FP1, "side.shots_hit": FP2},
            "measure_params": {},
            "rules": [{"id": "r0000f6b1", "scope": "game", "subject": "seat", "effect": "flag", "post": False,
                       "post_since": None,
                       "when": {"all": [
                           {"op": "op.cmp", "args": {"a": {"m": "seat.published_hits"}, "b": {"v": FRACTION}}},
                           {"op": "op.in_set", "args": {"a": {"m": "seat.published_hits"},
                                                        "set": {"data": "legacy_table"}}}]},
                       "show": [["seat", "seat.index"]], "line": "legacy shape control {seat} closed"},
                      {"id": "r0000f6b2", "scope": "sitting", "effect": "note", "post": False, "post_since": None,
                       "sitting": {"op": "sitting.rate_vs_own",
                                   "args": {"num": "side.shots_hit", "window_days": SMALL}},
                       "show": [["d", "d"]], "line": "legacy sitting control {d}"}]}


OLD_TABLES = {"legacy_table.json": {"rows": [MEMBER, LONG]}}


def _plant(root, rev, doc, tables=None):
    rdir = os.path.join(str(root), rev)
    os.makedirs(rdir)
    with open(os.path.join(rdir, "rules.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc))
    if tables:
        os.makedirs(os.path.join(rdir, "data"))
        for name, t in tables.items():
            with open(os.path.join(rdir, "data", name), "w", encoding="utf-8") as f:
                f.write(json.dumps(t))
    return str(root)


def _counts(needles):
    return {c: len(needles[c]) for c in CLASSES}


def _hits(text, needles):
    return rn.count(text, needles).get("value", 0)


def test_l3_fix6_a_current_and_a_pre_closure_revision_derive_every_class(tmp_path):
    cur = _plant(tmp_path / "cur", CUR, _current())
    old = _plant(tmp_path / "old", OLD, _pre_closure(), OLD_TABLES)
    both = _plant(tmp_path / "both", CUR, _current())
    _plant(tmp_path / "both", OLD, _pre_closure(), OLD_TABLES)
    assert _counts(rn.derive(cur)) == {"rule_id": 1, "nonce": 1, "wording": 1, "data": 0, "value": 4,
                                       "listed": 0, "basename": 0}
    assert _counts(rn.derive(old)) == {"rule_id": 2, "nonce": 1, "wording": 2, "data": 2, "value": 25,
                                       "listed": 0, "basename": 0}
    needles = rn.derive(both)
    assert _counts(needles) == {"rule_id": 3, "nonce": 2, "wording": 3, "data": 2, "value": 29,
                                "listed": 0, "basename": 0}
    # the pre-closure revision's own needles, by class
    assert {"r0000f6b1", "r0000f6b2"} <= needles["rule_id"]
    assert NONCE_OLD in needles["nonce"]
    assert {("legacy shape control", "closed"), ("legacy sitting control",)} <= needles["wording"]
    assert needles["data"] == {"legacy_table.json", "legacy_table"}
    # its values, found where a text would carry them
    for text in ("the bound fingerprint %s was recorded" % FP1, "shots hit %s" % FP2,
                 "published hits above %s here" % FRACTION, "window days %s in the sitting" % SMALL,
                 "rows: %s" % MEMBER, "plain %s here" % LONG, "legacy table rows"):
        assert _hits(text, needles), text
    # a vocabulary NAME is public: never a value needle; and a control text
    for text in ("num is side.shots_hit here", "seat.published_hits and side.shots_hit", "rows: %s" % CONTROL):
        assert not _hits(text, needles), text


def test_l3_fix6_a_pre_closure_name_that_is_not_a_string_refuses_naming_the_folder(tmp_path, monkeypatch):
    store = _plant(tmp_path / "bad", BADKEY, _pre_closure(), OLD_TABLES)
    assert _counts(rn.derive(store))["value"] == 25          # control: the same document, string names only
    real = json.load

    def load(f, *a, **kw):
        # JSON on disk cannot carry a non-string key, so the parsed document
        # is given one at the parser (an integer entry name)
        doc = real(f, *a, **kw)
        if os.path.basename(os.path.dirname(f.name)) == BADKEY:
            doc["vocabulary"][7] = FP1
        return doc
    monkeypatch.setattr(rn.json, "load", load)
    with pytest.raises(rn.NoVerdict) as e:
        rn.derive(store)
    assert BADKEY in str(e.value) and "not a string" in str(e.value), str(e.value)
    assert FP1 not in str(e.value)


THIRD_SHAPES = [("a_string", FP1), ("a_number", LITERAL), ("null", None)]


@pytest.mark.parametrize("name,vocab", THIRD_SHAPES, ids=[s[0] for s in THIRD_SHAPES])
def test_l3_fix6_a_vocabulary_of_a_third_shape_refuses_naming_the_folder(tmp_path, name, vocab):
    doc = _pre_closure()
    doc["vocabulary"] = vocab
    store = _plant(tmp_path / "ok", CUR, _current())
    _plant(tmp_path / "ok", THIRD, doc, OLD_TABLES)
    with pytest.raises(rn.NoVerdict) as e:
        rn.derive(store)
    msg = str(e.value)
    assert THIRD in msg and "vocabulary" in msg, msg
    assert FP1 not in msg and str(LITERAL) not in msg, msg         # the reason, never a value


def test_l3_fix6_a_pre_closure_document_with_a_closure_of_no_known_form_refuses_naming_the_folder(tmp_path):
    doc = _pre_closure()
    doc["closure"] = [FP1]
    store = _plant(tmp_path / "c", OLD, doc, OLD_TABLES)
    with pytest.raises(rn.NoVerdict) as e:
        rn.derive(store)
    msg = str(e.value)
    assert OLD in msg and "closure" in msg and FP1 not in msg, msg
