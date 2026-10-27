"""Fix pass 7 (build round 7, M4) for the private-needle check, against a
SYNTHETIC scratch rule set only (no store is read, no private value is used).

The evaluator decides on a text-table line as the exact string the loader
produced: review_rules.load_dir keeps every nonempty line of a text table
whole, and op.in_set compares the measure with those strings. The value
derivation (review_needles._value_items) therefore preserves every nonempty
line as that exact string and derives a value needle in that exact form; the
token and numeric forms of the line are derived in addition, never instead.

The control builds and loads a scratch revision with the seat's own tools
(review_rules.build_revision and load_dir: the compiler admits it) whose
deciding values are leading-zero strings, one of the bare string length and
one shorter, and asserts:
  * the loader produced exactly those strings and the compiled rule decides
    on them (each string is in the compiled set; its number is not);
  * the exact disclosure of each is found: the long one on its own, the short
    one beside its table's key;
  * a canonical rendering (the number beside the key, and after a threshold
    noun) is still found;
  * leading-zero strings the table does not hold are not found (control).

Planted values are made at run time from this file's seed SEED: only their
shape (the count of leading zeros and of digits) is written here, never a
value."""

import hashlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_measures as rm  # noqa: E402
import review_needles as rn  # noqa: E402
import review_rules as rr  # noqa: E402
import review_testkit as tk  # noqa: E402

SEED = "test_review_needles_r7"


def _hash(tag):
    return int(hashlib.sha256(("%s %s" % (SEED, tag)).encode("ascii")).hexdigest(), 16)


def _leading(tag, zeros, digits):
    """`zeros` leading zeros, then a number of exactly `digits` digits taken
    from the hash of SEED and tag."""
    low = 10 ** (digits - 1)
    return "0" * zeros + str(low + _hash(tag) % (9 * low))


def _other(v):
    """The same shape as v with the next number (wrapping within its digit
    count): a leading-zero string the table does not hold."""
    zeros = len(v) - len(v.lstrip("0"))
    n = v[zeros:]
    low = 10 ** (len(n) - 1)
    return "0" * zeros + str(low + (int(n) - low + 1) % (9 * low))


LONG = _leading("long", 4, 4)            # of the bare string length: found on its own
SHORT = _leading("short", 2, 1)          # shorter: found beside its table's key
ABSENT_LONG, ABSENT_SHORT = _other(LONG), _other(SHORT)
TABLE = "leading_zero_codes"             # a data name is letters and underscores only
KEY = TABLE.replace("_", " ")
RULE = "r0000f7a1"


def _numbers(node, out):
    """Every number of the synthetic document, by an independent walk."""
    if isinstance(node, dict):
        for v in node.values():
            _numbers(v, out)
    elif isinstance(node, list):
        for v in node:
            _numbers(v, out)
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        out.add(node)
    return out


def _doc():
    doc = tk.synthetic_doc()
    doc["rules"].append({
        "id": RULE, "scope": "game", "subject": "seat", "effect": "note", "post": False,
        "post_since": None,
        "when": {"op": "op.in_set", "args": {"a": tk.M("seat.decided_hits"), "set": {"data": TABLE}}},
        "show": [["seat", "seat.index"]], "line": "fix seven {seat}"})
    return doc


def build(tmp):
    """(store, the loaded ruleset, the derived needles) of the scratch rule set
    in the directory tmp, built and loaded by the seat's own tools."""
    # the controls below are meaningful only when the absent long number is
    # no number of the document either (its bare threshold form would then be
    # found as that value); a number under VALUE_MIN_BARE is matched only
    # beside its own key, and only the table's values have the table's key
    assert int(ABSENT_LONG) not in _numbers(_doc(), set())
    assert int(ABSENT_SHORT) < rn.VALUE_MIN_BARE <= int(ABSENT_LONG)
    assert len(LONG) >= rn.STR_MIN_BARE > len(SHORT)
    draft = tk.write_draft(os.path.join(str(tmp), "draft"), _doc(), [])
    os.makedirs(os.path.join(draft, "data"))
    with open(os.path.join(draft, "data", TABLE + ".txt"), "wb") as f:
        f.write(("%s\n%s\n" % (LONG, SHORT)).encode("ascii"))
    store = os.path.join(str(tmp), "store")
    os.makedirs(store)
    rev = rr.build_revision(draft, store, "fix seven")       # the compiler admits the rule set
    return store, rr.load_dir(os.path.join(store, "rules-" + rev)), rn.derive(store)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return build(tmp_path_factory.mktemp("fix7"))


def _hit(text, needles):
    return bool(rn.count(text, needles).get("value"))


def test_m4_fix7_the_loader_keeps_each_line_whole_and_the_rule_decides_on_it(built):
    _store, rs, _needles = built
    assert rs.data[TABLE] == [LONG, SHORT]                    # the exact strings, zeros kept
    op, _entry, args = rs.rule(RULE).when
    assert op == "op" and args[1] == ("v", [LONG, SHORT])
    for v in (LONG, SHORT):
        assert rm.op_in_set(v, args[1][1]) is True            # the string decides
        assert rm.op_in_set(int(v), args[1][1]) is False      # its number does not


def test_m4_fix7_the_exact_leading_zero_string_is_found(built):
    needles = built[2]
    assert _hit("the table holds %s now" % LONG, needles)                # on its own
    assert _hit('"%s"' % LONG, needles)                                   # quoted, as JSON or code writes it
    assert _hit("%s is %s here" % (KEY, SHORT), needles)                 # beside its table's key
    assert _hit("%s then %s" % (SHORT, KEY), needles)                    # the key after it


def test_m4_fix7_a_canonical_rendering_is_still_found(built):
    needles = built[2]
    assert _hit("%s is %d here" % (KEY, int(LONG)), needles)
    assert _hit("a threshold of %d" % int(LONG), needles)
    assert _hit("%s is %d here" % (KEY, int(SHORT)), needles)


def test_m4_fix7_control_strings_the_table_does_not_hold_are_not_found(built):
    needles = built[2]
    for text in ("the table holds %s now" % ABSENT_LONG, '"%s"' % ABSENT_LONG,
                 "%s is %s here" % (KEY, ABSENT_SHORT), "%s is %d here" % (KEY, int(ABSENT_LONG)),
                 "a threshold of %d" % int(ABSENT_LONG), "%s is %d here" % (KEY, int(ABSENT_SHORT))):
        assert not _hit(text, needles), text
