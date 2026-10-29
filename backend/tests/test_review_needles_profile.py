"""The needle tool over a measure-parameter family keyed by deal profile
identity (card_measures PROFILE_KEYED; review_rules.compile_rules admits one
value set per full-digest profile id): review_needles derives the value set's
members as it derives a flat family's, by position and derivation type, never
by the compiler's value rules. A value the compiler would refuse (a string
where a weight belongs) is still a private byte of the revision and still a
needle, for the profile-keyed family exactly as for a flat one; the tool's
refusals are the shapes it cannot derive: an object under a key that is not a
profile id, and an object inside a profile's value set."""
import hashlib
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "api"))
sys.path.insert(0, HERE)

import review_needles as rn  # noqa: E402
import review_testkit as tk  # noqa: E402

WEIGHTS = "params.card_weights"
OTHER_PROFILE = hashlib.sha256(b"another synthetic deal profile").hexdigest()


def _store(tmp, doc):
    # one revision per store: a root that already holds one would let an
    # earlier revision's refusal stand in for the one under test
    assert not [d for d in os.listdir(str(tmp)) if d.startswith("rules-")], os.listdir(str(tmp))
    rdir = os.path.join(str(tmp), "rules-" + hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest()[:12])
    os.makedirs(os.path.join(rdir, "data"))
    with open(os.path.join(rdir, "rules.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(doc))
    return str(tmp)


def _hit(text, needles):
    return bool(rn.count(text, needles).get("value"))


def test_a_profile_keyed_value_set_derives_as_a_flat_family_does(tmp_path):
    doc = tk.synthetic_doc()
    doc["measure_params"][WEIGHTS] = {tk.PROFILE: {"common": 7777, "uncommon": 3, "rare": 1},
                                      OTHER_PROFILE: {"common": 5, "uncommon": 3, "rare": 8888}}
    needles = rn.derive(_store(tmp_path, doc))
    assert _hit("common is 7777 here", needles)          # beside its key, first profile
    assert _hit("rare is 8888 here", needles)            # second profile, its own set
    assert _hit("a threshold of 7777 for it", needles)   # bare, as a flat family's number
    assert not _hit("common is 98765 here", needles)     # control: a value the revision does not hold


def test_a_value_the_compiler_would_refuse_is_still_a_needle_in_either_family(tmp_path):
    # the tool derives the revision's bytes by position; validity is the compiler's
    doc = tk.synthetic_doc()
    doc["measure_params"][WEIGHTS][tk.PROFILE]["common"] = "not numeric weight"
    doc["measure_params"]["params.age_sum"]["budget_slack_ms"] = "not numeric slack"
    needles = rn.derive(_store(tmp_path, doc))
    assert _hit("the weight was not numeric weight here", needles)   # bare string needle, profile-keyed
    assert _hit("slack was not numeric slack here", needles)         # the same for the flat family


@pytest.mark.parametrize("shape", ["flat-family", "short-profile-key"])
def test_an_object_under_a_key_that_is_not_a_profile_id_is_refused(tmp_path, shape):
    # each shape alone in its own store: the refusal under test is the only
    # one the store can raise
    doc = tk.synthetic_doc()
    if shape == "flat-family":
        doc["measure_params"]["params.age_sum"] = {"budget_slack_ms": {"common": 17}}
    else:
        doc["measure_params"][WEIGHTS] = {"deadbeef": {"common": 5, "uncommon": 3, "rare": 1}}   # not a full digest
    with pytest.raises(rn.NoVerdict, match="an object as a measure parameter"):
        rn.derive(_store(tmp_path, doc))


def test_an_object_inside_a_profiles_value_set_is_refused(tmp_path):
    doc = tk.synthetic_doc()
    doc["measure_params"][WEIGHTS][tk.PROFILE]["common"] = {"nested": 5}
    with pytest.raises(rn.NoVerdict, match="an object as a profile-keyed measure parameter"):
        rn.derive(_store(tmp_path, doc))
