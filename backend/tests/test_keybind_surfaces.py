"""Item 17 fix pass 1 F1: the binding-surface oracle, run.

tools/keybind_surfaces.py enumerates every harvested display string (every
plugin file, the shop snapshot, the catalogue keys, the vanilla tables),
every binding-producer call site and every binding reader, and requires a
disposition for each (tools/keybind_surfaces.tsv, the sites manifest). An
undispositioned string, a new site or a new reader is red. These run it on
this tree and pin the dispositions of the surfaces the round-1 report named.
The oracle's own mutants (a new catalogue entry, a new hardcoded hint, a new
producer site, a new reader, and a comment-only control) are run by the lane
evidence, each on a copied tree.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TOOL = REPO / "tools" / "keybind_surfaces.py"


def _tool():
    spec = importlib.util.spec_from_file_location("keybind_surfaces_f1", TOOL)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["keybind_surfaces_f1"] = mod
    spec.loader.exec_module(mod)
    return mod


KS = _tool()


@pytest.fixture(scope="module")
def run():
    problems, summary, state = KS.check(str(REPO))
    return problems, summary, state


def test_f1_every_surface_is_dispositioned_and_every_site_known(run):
    problems, summary, _ = run
    assert problems == [], "\n".join(problems[:40]) + "\n" + summary


NAMED = {
    "Loading your dances - try {0} again in a second.": "P",
    "point + release {0} to dance": "P",
    "point + release {0} to send": "P",
    "the Chat overlay mode control cycles the same state in game; Muted also tells the room you cannot read chat": "N",
}


@pytest.mark.parametrize("text,code", sorted(NAMED.items()))
def test_f1_the_reported_surfaces_have_their_disposition(run, text, code):
    _, _, (t, u, found, disp) = run
    i = KS.kid(text)
    assert i in u, text
    assert disp[i][0] == code, (text, disp[i])


@pytest.mark.parametrize("prefix,code", [
    ("The board below shows every key that does something during competitive play", "F"),
    ("<color=#FFD94D><b>THE KEYS IN PRACTICE</b></color>\n{0} works everywhere", "P"),
    ("<color=#CCCCCC>In this Photon room for <b>{0}s</b>", "P"),
])
def test_f1_the_help_and_hint_bodies_have_their_disposition(run, prefix, code):
    _, _, (t, u, found, disp) = run
    hits = [i for i, (o, text, s) in u.items() if o == "H" and text.startswith(prefix)]
    assert len(hits) == 1, prefix
    assert disp[hits[0]][0] == code


def test_f1_no_retired_fixed_binding_string_is_harvested(run):
    _, _, (t, u, found, disp) = run
    live = {text for o, text, s in u.values() if o == "H"}
    for retired in ("M cycles the same state in game; Muted also tells the room you cannot read chat",
                    "point + release E to dance", "point + release Q to send",
                    "Loading your dances - try E again in a second."):
        assert retired not in live, retired
    assert not any("try space again" in s for s in live)


def test_f1_the_keyboard_board_is_a_known_site(run):
    _, _, (t, u, found, disp) = run
    assert found[("InfoViz.cs", "BuildKeyboard", "Fill")][0] == 54
