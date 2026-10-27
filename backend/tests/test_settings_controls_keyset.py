"""Item 17 T5 (fix pass 1 F8): the Controls sub-tab's settings key set.

tools/settings/controls_keyset.py follows the construction chain from the
Controls body to every KEYBIND row, recognises the row parts _q, _l, _c,
_b, _x and _r, and classifies every other "SKb" construction by its parent.
These run it against this tree and the baseline captured at the build
commit, and run each of its mutations and controls (#391): dropping one row
reds with exactly that key missing; a chrome button under SetDetail and an
extra Controls heading leave the key set unchanged.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOL = REPO / "tools" / "settings" / "controls_keyset.py"
BASE = REPO / "tools" / "settings" / "controls_keyset.json"


def _tool():
    spec = importlib.util.spec_from_file_location("controls_keyset_t5", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["controls_keyset_t5"] = mod
    spec.loader.exec_module(mod)
    mod.CS = mod._cs()
    return mod


T5 = _tool()
TEXTS = T5.read_tree(str(REPO))
BASELINE = json.loads(BASE.read_text(encoding="utf-8"))


def test_t5_the_controls_key_set_equals_the_baseline_with_sixteen_rows():
    verdict, detail, cur = T5.check(TEXTS, BASELINE)
    assert verdict == "GREEN", detail
    assert len(cur["rows"]) == 16 and len(set(cur["rows"])) == 16
    assert cur["home"] == "SubControls"
    assert cur["raw_controls"] == []
    assert sorted(cur["parts"]["row"] + cur["parts"]["cell"]) == sorted(["_q", "_l", "_c", "_b", "_x", "_r"])


def test_t5_the_baseline_is_sixteen_keys():
    assert len(BASELINE["keys"]) == 16 and BASELINE["home"] == "SubControls"


@pytest.mark.parametrize("case", T5.CASES, ids=[c[0] for c in T5.CASES])
def test_t5_each_mutation_and_control_has_its_outcome(case):
    cid, kind, mutate, want, needle = case
    mutated = mutate(TEXTS)
    assert mutated != TEXTS, cid
    verdict, detail, _ = T5.check(mutated, BASELINE)
    assert verdict == want and needle in detail, (cid, verdict, detail)


def test_t5_drop_one_row_names_exactly_that_key():
    mutated = T5.CASES[0][2](TEXTS)
    cur = T5.harvest(mutated)
    missing, added, _ = T5.compare(BASELINE, cur)
    assert missing == ["SKbMoveUp"] and added == []
