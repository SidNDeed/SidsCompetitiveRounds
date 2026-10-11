"""Item 17 fix pass 1 F1, fix passes 2 and 3 H1: the binding-surface oracle, run.

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
and whitespace-only controls; fix 3: RefreshAll's Override branch
inverted, a new caller in a file no manifest names, a recorded caller
removed or moved, and the comment-, whitespace- and unfollowed-call
controls) are run by the lane evidence, each on a copied tree.

Fix pass 3 H1: the consumers of a reader are no longer the readers
manifest's word. The oracle derives every caller of every followed member
from source (tools/keybind_surfaces_callers.tsv records each edge with its
reference count, its content digest and its reviewed class), a display
reader's via must equal the display-reachable set the source derives, and a
caller the manifest lacks, a recorded caller the source no longer derives, a
caller whose text changed and a class change are each red. The fix-3 tests
below run the oracle on this tree's own state with one manifest varied.

Fix pass 4 H1: a display consumer is no longer a silent terminal. Every
terminal display sink must reach a declared render root by an attachment
chain (each hop a call, a delegate registration, a table or segment entry
or a string-dispatch key paired with its registration), every chain is a
row of tools/keybind_surfaces_attach.tsv, and a sink with no chain, a chain
the manifest lacks or no longer derives, a root that is missing or entered
differently, an UNRESOLVED hop without a control that names it, a binding
visual table that differs from the derived set and a retired consumer that
is referenced again are each red. The fix-4 tests below run the derivation
on this tree's state with one manifest or the declared roots varied, and
classify each hop kind on a synthetic tree; the detachments themselves (the
keyboard guide's segment removed, the Controls outro's entries removed, a
sink moved or attached anew) are the lane's mutants, each on a copied tree.
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
    # fix pass 3 H1: RefreshAll decides the prompts too (it was omitted)
    assert via == ["ApplyJoin", "ApplyReady", "RefreshAll"]


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


# -- fix pass 3 H1: the callers are derived, never the manifest's word -------

OVR = "Keybinds.cs:Override"
CALLERS = REPO / "tools" / "keybind_surfaces_callers.tsv"
READERS = REPO / "tools" / "keybind_surfaces_readers.tsv"


@pytest.fixture(scope="module")
def graph3():
    """This tree's state, its derived caller graph and its callers manifest
    (the round-3 oracle has none of them: every fix-3 test fails there)."""
    for name in ("derive_callers", "read_callers", "display_reach", "caller_digest"):
        assert hasattr(KS, name), "the oracle derives no caller graph (%s)" % name
    st = KS.State(str(REPO))
    cman, probs = KS.read_callers(str(CALLERS))
    assert probs == [], probs
    graph = KS.derive_callers(st, cman)
    return st, cman, graph


def _rows(path):
    return path.read_text(encoding="utf-8").split("\n")


def _check(st, tmp_path, callers=None, readers=None, attach=None):
    kw = {}
    if callers is not None:
        p = tmp_path / "callers.tsv"
        p.write_text("\n".join(callers), encoding="utf-8")
        kw["callers_path"] = str(p)
    if readers is not None:
        p = tmp_path / "readers.tsv"
        p.write_text("\n".join(readers), encoding="utf-8")
        kw["readers_path"] = str(p)
    if attach is not None:
        p = tmp_path / "attach.tsv"
        p.write_text("\n".join(attach), encoding="utf-8")
        kw["attach_path"] = str(p)
    problems, summary, _ = KS.check(str(REPO), verbose=False, state=st, **kw)
    return problems


def test_h1_fix3_every_derived_caller_is_a_reviewed_row(graph3):
    st, cman, graph = graph3
    assert set(graph) == set(cman), (sorted(set(graph) - set(cman))[:5], sorted(set(cman) - set(graph))[:5])
    for (s, c), (refs, digest, cls, note) in cman.items():
        assert cls in KS.CALLER_CLASSES, (s, c, cls)
        assert note.strip(), (s, c)
        assert refs == len(graph[(s, c)]), (s, c)
        assert digest == KS.caller_digest(st.t, c, graph[(s, c)]), (s, c)


def test_h1_fix3_refreshall_is_a_recorded_display_caller_of_the_override(graph3):
    st, cman, graph = graph3
    refs, digest, cls, note = cman[(OVR, "Keybinds.cs:RefreshAll")]
    assert cls == "display" and refs == 1
    reach = KS.display_reach(graph, cman)
    assert sorted(reach[OVR]) == ["Keybinds.cs:ApplyJoin", "Keybinds.cs:ApplyReady", "Keybinds.cs:RefreshAll"]


def test_h1_fix3_a_caller_the_manifest_lacks_is_red(graph3, tmp_path):
    st, cman, graph = graph3
    rows = [r for r in _rows(CALLERS) if not r.startswith(OVR + "\tKeybinds.cs:RefreshAll\t")]
    assert len(rows) == len(_rows(CALLERS)) - 1
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("NEW caller Keybinds.cs:RefreshAll of " + OVR) for p in problems), problems[:5]


def test_h1_fix3_a_recorded_caller_the_source_does_not_derive_is_red(graph3, tmp_path):
    st, cman, graph = graph3
    rows = _rows(CALLERS)
    rows.insert(1, "\t".join([OVR, "Keybinds.cs:KeyboardSeat", "1", "0" * 16, "display", "not a caller"]))
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("STALE caller Keybinds.cs:KeyboardSeat of " + OVR) for p in problems), problems[:5]


def test_h1_fix3_a_caller_whose_text_changed_is_red(graph3, tmp_path):
    st, cman, graph = graph3
    rows = []
    for r in _rows(CALLERS):
        f = r.split("\t")
        if r.startswith(OVR + "\tKeybinds.cs:RefreshAll\t"):
            f[3] = "0" * 16
        rows.append("\t".join(f))
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("CALLER CHANGED Keybinds.cs:RefreshAll of " + OVR) for p in problems), problems[:5]


def test_h1_fix3_the_readers_via_must_equal_the_derived_display_set(graph3, tmp_path):
    st, cman, graph = graph3
    rows = []
    for r in _rows(READERS):
        f = r.split("\t")
        if f[:2] == ["Keybinds.cs", "Override"]:
            f[5] = "ApplyJoin,ApplyReady"   # the round-3 row, RefreshAll omitted
        rows.append("\t".join(f))
    problems = _check(st, tmp_path, readers=rows)
    assert any(p.startswith("VIA DIFFERS display reader " + OVR) for p in problems), problems[:5]


def test_h1_fix3_a_display_role_change_is_red(graph3, tmp_path):
    st, cman, graph = graph3
    # the recorded caller RefreshAll reclassed as non-display: the override's
    # derived display set loses it, so its via differs
    rows = []
    for r in _rows(CALLERS):
        f = r.split("\t")
        if r.startswith(OVR + "\tKeybinds.cs:RefreshAll\t"):
            f[4] = "nondisplay"
        rows.append("\t".join(f))
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("VIA DIFFERS display reader " + OVR) for p in problems), problems[:5]
    # a non-display reader whose value gains a display caller is red
    rows = []
    for r in _rows(CALLERS):
        f = r.split("\t")
        if r.startswith("KeybindRules.cs:FormatToken\tKeybinds.cs:Init\t"):
            f[4] = "display"
        rows.append("\t".join(f))
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("reader KeybindRules.cs:FormatToken role rules, but its value reaches the player")
               for p in problems), problems[:5]


# -- fix pass 4 H1: every display sink is attached to a declared render root --

ATTACH = REPO / "tools" / "keybind_surfaces_attach.tsv"
KBD = "InfoViz.cs:BuildKeyboard"
OUTRO = "InfoLibrary.cs:ControlsOutro"
RESET_MENU = "harmony:Keybinds.cs:ResetMenuPatch.Postfix#2(CharacterSelectionInstance.ResetMenu)"
HOP = re.compile(r" \| | \|\| ")


@pytest.fixture(scope="module")
def attach4(graph3):
    """This tree's attachment derivation and its attachment manifest (the
    round-4 oracle has neither: every fix-4 test fails there)."""
    for name in ("derive_attach", "read_attach", "attach_sinks", "attach_problems", "RENDER_ROOTS", "hop_at"):
        assert hasattr(KS, name), "the oracle derives no attachment (%s)" % name
    st, cman, graph = graph3
    rman, _ = KS.read_readers(str(READERS))
    att = KS.derive_attach(st, KS.attach_sinks(st, graph, cman, rman))
    aman, probs = KS.read_attach(str(ATTACH))
    assert probs == [], probs
    return st, cman, att, aman


def test_h1_fix4_every_display_sink_has_a_recorded_chain_to_a_declared_root(attach4):
    st, cman, att, aman = attach4
    assert att["missing"] == [] and len(att["roots"]) == len(KS.RENDER_ROOTS), att["missing"]
    sinks = {c for (s, c), row in cman.items() if row[2] == "display"}
    assert sinks <= set(att["sinks"]), sorted(sinks - set(att["sinks"]))
    for s, rec in att["sinks"].items():
        assert rec["chains"], "orphan display sink %s" % s
        for text, lined in rec["chains"].values():
            assert text.split(" ## reg ")[0].rsplit(" || ", 1)[1].startswith(("root:", "unresolved:")), text
    derived = {(s, cid) for s, rec in att["sinks"].items() for cid in rec["chains"]}
    assert derived == set(aman["chain"]), (sorted(derived - set(aman["chain"]))[:3],
                                           sorted(set(aman["chain"]) - derived)[:3])


def test_h1_fix4_the_keyboard_guide_is_attached_through_the_controls_segment(attach4):
    st, cman, att, aman = attach4
    chains = [text for text, _ in att["sinks"][KBD]["chains"].values()]
    assert chains
    for text in chains:
        leg, reg = text.split(" ## reg ")
        assert leg.startswith('dispatch[case "keyboard"]{keyboard}>InfoViz.cs:Dispatch | '), leg
        assert reg.startswith("register[[0]/Category.Articles/Article{controls}.Segments=>/[1]]{keyboard}"
                              ">InfoLibrary.cs:Categories"), reg
    assert att["bkeys"] == {"keyboard"} and att["tables"] == {"InfoViz.cs:Dispatch": {"keyboard"}}


def test_h1_fix4_the_controls_outro_is_attached_by_both_controls_entries(attach4):
    st, cman, att, aman = attach4
    firsts = {HOP.split(text)[0] for text, _ in att["sinks"][OUTRO]["chains"].values()}
    assert firsts == {
        "entry[[0]/Category.Articles/Article{controls}.Body=>]>InfoLibrary.cs:Categories",
        "entry[[0]/Category.Articles/Article{controls}.Segments=>/[2]/Seg.T(#0)]>InfoLibrary.cs:Categories"}, firsts


def test_h1_fix4_a_chain_the_manifest_lacks_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = _rows(ATTACH)
    gone = [r for r in rows if r.startswith("chain\t%s\t" % KBD)]
    assert gone
    problems = _check(st, tmp_path, attach=[r for r in rows if r != gone[0]])
    cid = gone[0].split("\t")[2]
    assert any(p.startswith("NEW attachment chain %s of display sink %s: " % (cid, KBD)) for p in problems), problems[:5]


def test_h1_fix4_a_recorded_chain_the_source_does_not_derive_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = _rows(ATTACH) + ["\t".join(["chain", KBD, "0" * 16,
                                       'dispatch[case "keyboard"]{keyboard}>InfoViz.cs:Dispatch || root:NativeUI.cs:BuildPage'])]
    problems = _check(st, tmp_path, attach=rows)
    assert any(p.startswith("STALE attachment chain %s of display sink %s" % ("0" * 16, KBD)) for p in problems), \
        problems[:5]


def test_h1_fix4_a_sink_with_no_chain_to_a_declared_root_is_an_orphan(attach4, monkeypatch):
    st, cman, att, aman = attach4
    monkeypatch.setattr(KS, "RENDER_ROOTS", tuple(r for r in KS.RENDER_ROOTS if r[1] != "SelectInfoArticle"))
    cut = KS.derive_attach(st, {KBD})
    assert cut["sinks"][KBD]["chains"] == {}, cut["sinks"][KBD]
    problems = KS.attach_problems(str(REPO), st, cut, aman, cman)
    assert any(p.startswith("ORPHAN display sink %s: no attachment chain to a declared render root" % KBD)
               for p in problems), problems[:5]


def test_h1_fix4_a_declared_root_that_is_not_one_member_is_red(attach4, monkeypatch, tmp_path):
    st, cman, att, aman = attach4
    monkeypatch.setattr(KS, "RENDER_ROOTS", KS.RENDER_ROOTS + (("NativeUI.cs", "NoSuchRoot", "a root that is gone"),))
    gone = KS.derive_attach(st, set())
    problems = KS.attach_problems(str(REPO), st, gone, aman, cman)
    assert "ROOT MISSING NativeUI.cs:NoSuchRoot: a declared render root is not one member of the tree" in problems
    rows = []
    for r in _rows(ATTACH):
        f = r.split("\t")
        if r.startswith("root\tCompetitiveUI.cs:DrawUI\t"):
            f[3] = "0" * 16
        rows.append("\t".join(f))
    monkeypatch.undo()
    problems = _check(st, tmp_path, attach=rows)
    assert any(p.startswith("ROOT ENTRY CHANGED CompetitiveUI.cs:DrawUI: entered from ref>Plugin.cs:OnGUI")
               for p in problems), problems[:5]


def test_h1_fix4_every_unresolved_hop_is_dispositioned_with_a_control_that_names_it(attach4):
    st, cman, att, aman = attach4
    assert set(att["unresolved"]) == set(aman["unresolved"]) == {
        RESET_MENU,
        "harmony:Keybinds.cs:OnEnablePatch.Postfix#3(CharacterSelectionInstance.OnEnable)",
        "harmony:Keybinds.cs:StartPickingPatch.Postfix#4(CharacterSelectionInstance.StartPicking)",
        "harmony:Keybinds.cs:ReadyUpPatch.Postfix#5(CharacterSelectionInstance.ReadyUp)"}
    for name, (ctl, note) in aman["unresolved"].items():
        assert KS.control_names(str(REPO), ctl, KS._unresolved_names(name)) is None, (name, ctl)
        assert note.strip(), name


def test_h1_fix4_an_unresolved_hop_without_a_naming_control_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = [r for r in _rows(ATTACH) if not r.startswith("unresolved\t%s\t" % RESET_MENU)]
    problems = _check(st, tmp_path, attach=rows)
    assert any(p.startswith("UNRESOLVED hop %s (on the chains of Keybinds.cs:ApplyJoin) has no disposition" % RESET_MENU)
               for p in problems), problems[:5]
    for ctl, why in (("backend/tests/test_client_keybinds_fix2.py::test_m3_the_live_store_has_no_silent_write",
                      "does not name ResetMenuPatch"),
                     ("backend/tests/test_no_such_control.py::test_x", "control file backend/tests/test_no_such_control.py missing")):
        rows = []
        for r in _rows(ATTACH):
            f = r.split("\t")
            if r.startswith("unresolved\t%s\t" % RESET_MENU):
                f[2] = ctl
            rows.append("\t".join(f))
        problems = _check(st, tmp_path, attach=rows)
        assert any(p.startswith("UNRESOLVED hop %s: " % RESET_MENU) and why in p for p in problems), (ctl, problems[:5])


def test_h1_fix4_a_retired_consumer_referenced_again_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    assert cman[("NativeUI.Keybinds.cs:KeybindRowFace", "CompetitiveUI.cs:DrawMatchFoundStuckOverlay")][2] == "retired"
    rows = []
    for r in _rows(CALLERS):
        f = r.split("\t")
        if r.startswith("NativeUI.Keybinds.cs:KeybindRowFace\tCompetitiveUI.cs:DrawChatInput\t"):
            f[4] = "retired"
        rows.append("\t".join(f))
    problems = _check(st, tmp_path, callers=rows)
    assert any(p.startswith("RETIRED consumer CompetitiveUI.cs:DrawChatInput of NativeUI.Keybinds.cs:KeybindRowFace "
                            "is referenced again") for p in problems), problems[:5]


def test_h1_fix4_the_binding_visual_table_must_equal_the_derived_set(attach4):
    st, cman, att, aman = attach4
    wrong = dict(att, tables={"InfoViz.cs:Dispatch": {"keyboard", "grow-curve"}})
    problems = KS.attach_problems(str(REPO), st, wrong, aman, cman)
    assert any(p.startswith("BINDING VISUALS DIFFER at InfoViz.cs:Dispatch: the table declares grow-curve,keyboard")
               for p in problems), problems[:5]


SYNTH = """internal static class Lib
{
    internal struct Seg { public string Viz; public static Seg V(string k) => new Seg { Viz = k }; }
    internal sealed class Art { public string Key; public System.Func<string> Body; }
    internal static Art[] Arts => new[] { new Art { Key = "first" }, new Art { Key = "a", Body = () => Sink() } };
    internal static string Sink() { return "x"; }
    internal static object Pick(string key)
    {
        switch (key)
        {
            case "kb": return Sink();
            default: return null;
        }
    }
    internal static void Reg(System.Action<System.Func<string>> on) { on(Sink); }
    internal static void Plain() { var s = Sink(); }
}
"""


def test_h1_fix4_each_hop_kind_is_classified_with_its_context(tmp_path):
    (tmp_path / "plugin").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "plugin" / "Lib.cs").write_text(SYNTH, encoding="utf-8")
    (tmp_path / "tools" / "i18n_extract.py").write_bytes((REPO / "tools" / "i18n_extract.py").read_bytes())
    t = KS.Tree(str(tmp_path))
    got = {(h.consumer, h.kind, h.ctx, h.key) for h in KS.up_hops(t, "Lib.cs:Sink")}
    assert got == {
        ("Lib.cs:Arts", "entry", "Art{a}.Body=>", None),
        ("Lib.cs:Pick", "dispatch", 'case "kb"', "kb"),
        ("Lib.cs:Reg", "delegate", "on(#0)/&", None),
        ("Lib.cs:Plain", "ref", "", None)}, got
