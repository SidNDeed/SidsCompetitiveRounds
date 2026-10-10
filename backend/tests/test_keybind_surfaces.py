"""Item 17 fix pass 1 F1, fix pass 2 H1: the binding-surface oracle, run.

tools/keybind_surfaces.py enumerates every harvested display string (every
plugin file, the shop snapshot, the catalogue keys, every occurrence of the
vanilla tables), every binding-producer call site and every member that
reads a binding root, and requires a disposition for each
(tools/keybind_surfaces.tsv, the sites manifest, the readers manifest). An
undispositioned string, a new site or a new reader is red; so is a reader
whose content changed, a review whose display role changed, and a row with
no rule and no review. These run it on this tree, pin the dispositions of
the surfaces the round-1 report named, and pin the H1 shape: no file is
exempt, the ready-prompt override is a display reader, every locale
occurrence is its own row, and no row takes a disposition by default. The
oracle's own mutants (fix 1: a new catalogue entry, a new hardcoded hint, a
new producer site, a new reader, a comment-only control; fix 2: a display
reader in a formerly exempt file, one locale occurrence changed beneath an
unchanged path, a default-N row gaining a display role, and the comment-
and whitespace-only controls) are run by the lane evidence, each on a
copied tree.
"""
from __future__ import annotations

import importlib.util
import re
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


# -- fix pass 2 H1 ----------------------------------------------------------

def _readers():
    read = getattr(KS, "read_readers", None)
    assert read is not None, "the oracle has no readers manifest"
    rman, probs = read(str(REPO / "tools" / "keybind_surfaces_readers.tsv"))
    assert probs == [], probs
    return rman


def test_h1_no_file_is_exempt_from_the_reader_census():
    assert not hasattr(KS, "NON_DISPLAY"), "a whole-file reader exemption is back"
    st = KS.State(str(REPO))
    files = {fn for fn, _ in st.reads}
    # the two files the round-1 oracle exempted whole are now read member by member
    assert "Keybinds.cs" in files and "KeybindRules.cs" in files, sorted(files)
    assert ("Keybinds.cs", "Override") in st.reads


def test_h1_the_ready_prompt_override_is_a_display_reader():
    rman = _readers()
    count, digest, role, via, note = rman[("Keybinds.cs", "Override")]
    assert role == "display"
    assert via == ["ApplyJoin", "ApplyReady"]


def test_h1_every_reader_row_has_a_role_and_a_reason():
    rman = _readers()
    assert rman
    for k, (count, digest, role, via, note) in rman.items():
        assert role in KS.ROLES, k
        assert note.strip(), k
        assert count >= 1, k


_ENTRY = re.compile(r'(?m)^\s*\["(?:[^"\\\n]|\\.)*"\]\s*=\s*new\[\]\s*\{')


def test_h1_every_locale_occurrence_is_its_own_row(run):
    _, _, (t, u, found, disp) = run
    src = (REPO / "plugin" / "GameLocaleCatalogues.cs").read_text(encoding="utf-8")
    entries = len(_ENTRY.findall(src))
    vrows = [text for o, text, s in u.values() if o == "V"]
    assert entries > 0
    assert len(vrows) == entries, (len(vrows), entries)
    # one path in both tables: two rows, never collapsed under the path
    join = [v for v in vrows if ":StringTableDefault/PROMPT_SPACE_TO_JOIN#" in v]
    assert len(join) == 2 and len({KS.kid(v) for v in join}) == 2, join


def test_h1_no_row_takes_a_disposition_by_default(run):
    _, _, (t, u, found, disp) = run
    bare = [i for i, d in disp.items() if not (d[1].startswith("rule:") or d[1].startswith("rev:"))]
    assert bare == [], bare[:10]
