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

Fix pass 5 H1: the attachment traversal is complete - no hop bound. Every
member reached from a sink is expanded once (cycle-safe), every hop, end
and cycle end is a row of the attachment manifest, every sink row carries
the digest of its whole subgraph, and a traversal past its budget is red
(TRUNCATED, naming the path). The fix-4 tests now read the fix-5 rows; the
fix-5 tests pin the six-hop ControlsOutro path round 5 named, the 22 paths
the fix-4 bound printed DEAD, a truncation, a cyclic and a 201-hop
synthetic graph, a manifest without its cycle rows, and the source pin of
each of the 167 UNRESOLVED ends the complete traversal reaches.
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
    # fix pass 5: a sink's chains are every path up its recorded hops; the
    # manifest's hop, end, cycle and sink rows must equal the derivation's
    st, cman, att, aman = attach4
    assert att["missing"] == [] and len(att["roots"]) == len(KS.RENDER_ROOTS), att["missing"]
    sinks = {c for (s, c), row in cman.items() if row[2] == "display"}
    assert sinks <= set(att["sinks"]), sorted(sinks - set(att["sinks"]))
    for s, rec in att["sinks"].items():
        assert rec["attached"], "orphan display sink %s" % s
        assert any(att["ends"][n].startswith(("root:", "unresolved:")) for n in rec["ends"]), s
    rows = KS.attach_rows(st.t, att)
    for kind in ("hop", "end", "cycle", "sink"):
        assert rows[kind] == aman[kind], (kind, sorted(set(rows[kind]) ^ set(aman[kind]))[:3])


def test_h1_fix4_the_keyboard_guide_is_attached_through_the_controls_segment(attach4):
    st, cman, att, aman = attach4
    first = [KS._hop_token(st.t, h, False) for h in att["tr"]["up"][KBD]]
    assert first == ['dispatch[case "keyboard"]{keyboard}>InfoViz.cs:Dispatch'], first
    leg = att["legs"][(KBD, att["tr"]["up"][KBD][0].digest)]
    assert leg == "register:InfoViz.cs:Dispatch{keyboard}"
    regs = [KS._hop_token(st.t, h, False) for h in att["tr"]["up"][leg]]
    assert regs and all(r == "register[[0]/Category.Articles/Article{controls}.Segments=>/[1]]{keyboard}"
                                 ">InfoLibrary.cs:Categories" for r in regs), regs
    assert att["bkeys"] == {"keyboard"} and att["tables"] == {"InfoViz.cs:Dispatch": {"keyboard"}}


def test_h1_fix4_the_controls_outro_is_attached_by_both_controls_entries(attach4):
    st, cman, att, aman = attach4
    firsts = {KS._hop_token(st.t, h, False) for h in att["tr"]["up"][OUTRO]}
    assert firsts == {
        "entry[[0]/Category.Articles/Article{controls}.Body=>]>InfoLibrary.cs:Categories",
        "entry[[0]/Category.Articles/Article{controls}.Segments=>/[2]/Seg.T(#0)]>InfoLibrary.cs:Categories"}, firsts


def test_h1_fix4_a_chain_the_manifest_lacks_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = _rows(ATTACH)
    gone = [r for r in rows if r.startswith("hop\t%s\t" % KBD)]
    assert len(gone) == 1
    problems = _check(st, tmp_path, attach=[r for r in rows if r != gone[0]])
    d = gone[0].split("\t")[2]
    assert any(p.startswith("NEW attachment chain hop %s of display sink %s: " % (d, KBD)) for p in problems), problems[:5]


def test_h1_fix4_a_recorded_chain_the_source_does_not_derive_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = _rows(ATTACH) + ["\t".join(["hop", KBD, "0" * 16, "NativeUI.cs:BuildPage", "ref>NativeUI.cs:BuildPage"])]
    problems = _check(st, tmp_path, attach=rows)
    assert any(p.startswith("STALE attachment chain hop %s of display sink %s" % ("0" * 16, KBD)) for p in problems), \
        problems[:5]


def test_h1_fix4_a_sink_with_no_chain_to_a_declared_root_is_an_orphan(attach4, monkeypatch):
    # fix pass 5: the complete traversal reaches many roots and UNRESOLVED
    # ends from the guide, so the orphan is made by declaring no root, no
    # entry point and no reference at file scope (every path then ends
    # unreferenced)
    st, cman, att, aman = attach4
    up = KS.up_hops
    monkeypatch.setattr(KS, "RENDER_ROOTS", ())
    monkeypatch.setattr(KS, "entry_point", lambda t, key: None)
    monkeypatch.setattr(KS, "up_hops", lambda t, key: [h for h in up(t, key) if h.kind != "field"])
    cut = KS.derive_attach(st, {KBD})
    assert not cut["sinks"][KBD]["attached"], cut["sinks"][KBD]["roots"]
    assert set(cut["ends"].values()) <= {"unreferenced", "unregistered"}, set(cut["ends"].values())
    empty = {"root": {}, "hop": {}, "end": {}, "cycle": {}, "sink": {}, "unresolved": {}, "line": {}}
    problems = KS.attach_problems(str(REPO), st, cut, empty, {})
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
    # fix pass 5: the complete traversal reaches more UNRESOLVED ends; fix
    # pass 4's four keep their T8 controls (the fix-5 ends: FIX5_ENDS below)
    assert set(att["unresolved"]) == set(aman["unresolved"]) >= {
        RESET_MENU,
        "harmony:Keybinds.cs:OnEnablePatch.Postfix#3(CharacterSelectionInstance.OnEnable)",
        "harmony:Keybinds.cs:StartPickingPatch.Postfix#4(CharacterSelectionInstance.StartPicking)",
        "harmony:Keybinds.cs:ReadyUpPatch.Postfix#5(CharacterSelectionInstance.ReadyUp)"}
    for name in (RESET_MENU, "harmony:Keybinds.cs:OnEnablePatch.Postfix#3(CharacterSelectionInstance.OnEnable)",
                 "harmony:Keybinds.cs:StartPickingPatch.Postfix#4(CharacterSelectionInstance.StartPicking)",
                 "harmony:Keybinds.cs:ReadyUpPatch.Postfix#5(CharacterSelectionInstance.ReadyUp)"):
        assert aman["unresolved"][name][0].startswith(
            "backend/tests/test_client_keybinds.py::test_t8_each_prompt_postfix_has_its_target["), name
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


# ---- fix pass 5 (round 5 H1): the complete, cycle-safe attachment traversal ----

# R5H1 (a): the six-hop path the round-4 bound printed DEAD and left unhashed
# (plugin/InfoLibrary.cs:67,186-187; plugin/NativeUI.cs:2512,13637,13868,13891)
PATH5 = ("InfoLibrary.cs:ControlsOutro", "InfoLibrary.cs:Categories", "InfoLibrary.cs:Find",
         "NativeUI.cs:InfoArticleMatches", "NativeUI.cs:ApplyInfoNavFilter", "NativeUI.cs:BuildInfoTab",
         "NativeUI.cs:BuildPage")

# R5H1 (c): every (sink, member) the round-4 oracle printed "#DEAD ... (beyond
# the bound)" (item17-fix4-oracle.log lines 736-845): 22 paths
DEAD4 = [(s, m) for s in ("InfoLibrary.cs:ControlsOutro", "InfoLibrary.cs:Cosmetics", "InfoLibrary.cs:Spectating",
                          "InfoLibrary.cs:StartHere", "InfoLibrary.cs:VanillaBugs")
         for m in ("NativeUI.cs:ApplyInfoNavFilter", "NativeUI.cs:SwitchTab", "NativeUI.cs:Tick")]
DEAD4 += [("Keybinds.cs:OnRoundStart", "GameStateWatcher.cs:Initialize")]
DEAD4 += [("TabStatsOverlay.cs:EnsureLocaleStrings", m) for m in (
    "NativeUI.cs:BuildFfaCardsText", "NativeUI.cs:BuildOvtRecentRowText", "NativeUI.cs:BuildTeamCardsTooltipBody",
    "NativeUI.cs:CardsPlusBuildBody", "NativeUI.cs:TeamColumnHasBuild", "SessionReportView.cs:MeasureBlock")]


def _hop_between(att, aman, lower, upper):
    """The derived hop keys (lower, digest) from lower up to upper that the
    manifest records with the same upper member."""
    return sorted(k for k, (n, h) in att["hops"].items()
                  if n == lower and KS._upper(h) == upper and aman["hop"].get(k, (None,))[0] == upper)


def test_h1_fix5_the_six_hop_controls_outro_path_is_manifested_and_hashed(attach4):
    st, cman, att, aman = attach4
    sink = att["sinks"][PATH5[0]]
    assert sink["attached"], PATH5[0]
    for lower, upper in zip(PATH5, PATH5[1:]):
        keys = _hop_between(att, aman, lower, upper)
        assert keys, "no manifested hop %s > %s" % (lower, upper)
        assert set(keys) <= sink["hops"], (lower, upper)
    assert att["ends"][PATH5[-1]] == "root:" + PATH5[-1]
    assert aman["end"][PATH5[-1]] == "root:" + PATH5[-1]
    rows = KS.attach_rows(st.t, att)
    assert rows["sink"][PATH5[0]] == aman["sink"][PATH5[0]]


def test_h1_fix5_the_traversal_is_complete_and_the_round4_dead_paths_are_manifested(attach4):
    st, cman, att, aman = attach4
    assert att["truncated"] == [], att["truncated"][:3]
    assert not hasattr(KS, "ATTACH_BOUND"), "a hop bound is back"
    assert len(DEAD4) == 22
    for s, m in DEAD4:
        rec = att["sinks"][s]
        assert m in rec["nodes"], (s, m)
        assert m in att["tr"]["up"], "%s is reached from %s and never expanded" % (m, s)
        mine = [k for k in rec["hops"] if k[0] == m]
        assert mine or m in rec["ends"], (s, m)
        assert all(k in aman["hop"] for k in mine), (s, m)


def test_h1_fix5_a_truncated_traversal_is_red_and_names_its_path(attach4):
    st, cman, att, aman = attach4
    small = KS.derive_attach(st, [PATH5[0]], budget=3)
    assert small["truncated"], "a budget of three members truncated nothing"
    empty = {"root": {}, "hop": {}, "end": {}, "cycle": {}, "sink": {}, "unresolved": {}, "line": {}}
    probs = KS.attach_problems(str(REPO), st, small, empty, {})
    trunc = [p for p in probs if p.startswith("TRUNCATED attachment traversal at ")]
    assert len(trunc) == len(small["truncated"]), probs[:3]
    for (n, trail), p in zip(small["truncated"], trunc):
        assert trail.startswith(PATH5[0] + " <- ") and trail.endswith(" <- " + n), trail
        assert ("reached by the path %s and never expanded" % trail) in p, p


CYCLIC = """internal static class Lib
{
    internal static string Sink() { return "x"; }
    internal static string A(int n) { return n > 0 ? B(n - 1) : Sink(); }
    internal static string B(int n) { return A(n); }
    internal static string Root() { return A(3); }
}
"""


def _synthetic(tmp_path, monkeypatch, src, root):
    (tmp_path / "plugin").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "plugin" / "Lib.cs").write_text(src, encoding="utf-8")
    (tmp_path / "tools" / "i18n_extract.py").write_bytes((REPO / "tools" / "i18n_extract.py").read_bytes())
    monkeypatch.setattr(KS, "RENDER_ROOTS", (("Lib.cs", root, "the synthetic root"),))
    monkeypatch.setattr(KS, "DISPATCHERS", ())

    class St:
        pass
    st = St()
    st.t = KS.Tree(str(tmp_path))
    return st


def test_h1_fix5_a_cyclic_graph_terminates_and_records_its_cycle_end(tmp_path, monkeypatch):
    # R5H1 (d): A and B call each other; the traversal expands each once,
    # ends, and records the hops that close the cycle as cycle rows
    st = _synthetic(tmp_path, monkeypatch, CYCLIC, "Root")
    att = KS.derive_attach(st, ["Lib.cs:Sink"], budget=50)
    assert att["truncated"] == []
    assert att["ends"] == {"Lib.cs:Root": "root:Lib.cs:Root"}, att["ends"]
    cyc = {(n, KS._upper(att["hops"][(n, d)][1])) for (n, d) in att["cycles"]}
    assert cyc == {("Lib.cs:A", "Lib.cs:B"), ("Lib.cs:B", "Lib.cs:A")}, cyc
    assert att["sinks"]["Lib.cs:Sink"]["attached"]
    rows = KS.attach_rows(st.t, att)
    assert set(rows["cycle"]) == set(att["cycles"]) and len(rows["cycle"]) == 2, rows["cycle"]
    lines = KS.attach_lines(st.t, att, {"root": {"Lib.cs:Root": (0, "", "n")}, "unresolved": {}})
    assert sorted(x.split("\t")[1] for x in lines if x.startswith("cycle\t")) == ["Lib.cs:A", "Lib.cs:B"], lines


def test_h1_fix5_a_manifest_without_its_cycle_ends_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    assert att["cycles"], "the tree's traversal closes no cycle"
    rows = _rows(ATTACH)
    cut = [r for r in rows if not r.startswith("cycle\t")]
    assert len(rows) - len(cut) == len(att["cycles"])
    problems = _check(st, tmp_path, attach=cut)
    assert sum(1 for p in problems if p.startswith("NEW attachment cycle hop ")) == len(att["cycles"]), problems[:3]


DEEP = 200     # the tree's deepest first-reach path is 32 hops at the fix tip


def test_h1_fix5_no_hop_bound_a_two_hundred_hop_chain_is_recorded_whole(tmp_path, monkeypatch):
    body = ["internal static class Lib", "{", "    internal static string Sink() { return \"x\"; }",
            "    internal static string C1() { return Sink(); }"]
    body += ["    internal static string C%d() { return C%d(); }" % (i, i - 1) for i in range(2, DEEP + 1)]
    body += ["    internal static string Root() { return C%d(); }" % DEEP, "}", ""]
    st = _synthetic(tmp_path, monkeypatch, "\n".join(body), "Root")
    att = KS.derive_attach(st, ["Lib.cs:Sink"])
    assert att["truncated"] == []
    assert att["sinks"]["Lib.cs:Sink"]["attached"]
    assert len(att["hops"]) == DEEP + 1, len(att["hops"])
    assert att["ends"] == {"Lib.cs:Root": "root:Lib.cs:Root"}, att["ends"]


# Every UNRESOLVED end the complete traversal reaches beyond fix pass 4's
# four Harmony ends: (id, end name, the member it ends at). Its control in
# tools/keybind_surfaces_attach.tsv is test_h1_fix5_each_unresolved_end_is_pinned_in_source[id].
FIX5_ENDS = [
    ('dispatch-FfaAssembly.cs-HandleAnswer-admitted_late', 'dispatch:FfaAssembly.cs:HandleAnswer[admitted_late]', 'FfaAssembly.cs:OnLoadGrant'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-admitting', 'dispatch:FfaAssembly.cs:HandleAnswer[admitting]', 'FfaLateEntry.cs:FenceMaster'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-dissolved', 'dispatch:FfaAssembly.cs:HandleAnswer[dissolved]', 'FfaAssembly.cs:Exit'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-start_ok', 'dispatch:FfaAssembly.cs:HandleAnswer[start_ok]', 'FfaAssembly.cs:OnLoadGrant'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-wrong_region', 'dispatch:FfaAssembly.cs:HandleAnswer[wrong_region]', 'FfaAssembly.cs:OnWrongRegion'),
    ('dispatch-MusicEngine.cs-TsBegin-album', 'dispatch:MusicEngine.cs:TsBegin[album]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-fail', 'dispatch:MusicEngine.cs:TsBegin[fail]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-loop', 'dispatch:MusicEngine.cs:TsBegin[loop]', 'MusicEngine.cs:LoopEnabled'),
    ('dispatch-MusicEngine.cs-TsBegin-play-pause', 'dispatch:MusicEngine.cs:TsBegin[play-pause]', 'MusicEngine.cs:PlayPause'),
    ('dispatch-MusicEngine.cs-TsBegin-play', 'dispatch:MusicEngine.cs:TsBegin[play]', 'MusicEngine.cs:PlayTrack'),
    ('dispatch-MusicEngine.cs-TsBegin-prev', 'dispatch:MusicEngine.cs:TsBegin[prev]', 'MusicEngine.cs:PlayPrevious'),
    ('dispatch-MusicEngine.cs-TsBegin-preview', 'dispatch:MusicEngine.cs:TsBegin[preview]', 'MusicEngine.cs:TogglePreview'),
    ('dispatch-MusicEngine.cs-TsBegin-reset', 'dispatch:MusicEngine.cs:TsBegin[reset]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-seek', 'dispatch:MusicEngine.cs:TsBegin[seek]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-select', 'dispatch:MusicEngine.cs:TsBegin[select]', 'MusicEngine.cs:SetSelected'),
    ('dispatch-MusicEngine.cs-TsBegin-shuffle', 'dispatch:MusicEngine.cs:TsBegin[shuffle]', 'MusicEngine.cs:ShuffleEnabled'),
    ('dispatch-MusicEngine.cs-TsBegin-skip', 'dispatch:MusicEngine.cs:TsBegin[skip]', 'MusicEngine.cs:Skip'),
    ('dispatch-MusicEngine.cs-TsBegin-stall', 'dispatch:MusicEngine.cs:TsBegin[stall]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-stop-preview', 'dispatch:MusicEngine.cs:TsBegin[stop-preview]', 'MusicEngine.cs:StopPreviewAndRestore'),
    ('dispatch-MusicEngine.cs-TsBegin-stop', 'dispatch:MusicEngine.cs:TsBegin[stop]', 'MusicEngine.cs:Stop'),
    ('dispatch-MusicEngine.cs-TsBegin-unstall', 'dispatch:MusicEngine.cs:TsBegin[unstall]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-use-vanilla', 'dispatch:MusicEngine.cs:TsBegin[use-vanilla]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsRun-level', 'dispatch:MusicEngine.cs:TsRun[level]', 'MusicEngine.cs:TsRunLevel'),
    ('dispatch-MusicEngine.cs-TsRun-openall', 'dispatch:MusicEngine.cs:TsRun[openall]', 'MusicEngine.cs:TsRunOpenAll'),
    ('dispatch-MusicEngine.cs-TsRun-s1', 'dispatch:MusicEngine.cs:TsRun[s1]', 'MusicEngine.cs:TsRunS1'),
    ('dispatch-MusicEngine.cs-TsRun-s2', 'dispatch:MusicEngine.cs:TsRun[s2]', 'MusicEngine.cs:TsRunS2'),
    ('dispatch-MusicEngine.cs-TsRun-s3', 'dispatch:MusicEngine.cs:TsRun[s3]', 'MusicEngine.cs:TsRunS3'),
    ('dispatch-MusicEngine.cs-TsRun-s4', 'dispatch:MusicEngine.cs:TsRun[s4]', 'MusicEngine.cs:TsRunS4'),
    ('dispatch-MusicEngine.cs-TsRun-s4neg', 'dispatch:MusicEngine.cs:TsRun[s4neg]', 'MusicEngine.cs:TsRunS4Neg'),
    ('dispatch-MusicEngine.cs-TsRun-s5', 'dispatch:MusicEngine.cs:TsRun[s5]', 'MusicEngine.cs:TsRunS5'),
    ('dispatch-MusicEngine.cs-TsRun-s6', 'dispatch:MusicEngine.cs:TsRun[s6]', 'MusicEngine.cs:TsRunS6'),
    ('dispatch-MusicEngine.cs-TsRun-s6neg', 'dispatch:MusicEngine.cs:TsRun[s6neg]', 'MusicEngine.cs:TsRunS6'),
    ('dispatch-MusicEngine.cs-TsRun-wait', 'dispatch:MusicEngine.cs:TsRun[wait]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-reset', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[reset]', 'NativeUI.Keybinds.cs:KeybindResetRow'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-t3', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[t3]', 'Keybinds.cs:TranspilerMatcherBattery'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l2', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l2]', 'NativeUI.SettingsDrive.cs:DriveL2'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l3', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l3]', 'NativeUI.SettingsDrive.cs:DriveL3'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l6', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l6]', 'NativeUI.SettingsDrive.cs:DriveL6'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-m1', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[m1]', 'NativeUI.SettingsDrive.cs:DriveM1'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t4', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t4]', 'NativeUI.SettingsDrive.cs:DriveT4'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5a', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5a]', 'NativeUI.SettingsDrive.cs:DriveT5a'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5b]', 'NativeUI.SettingsDrive.cs:DriveT5b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5c', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5c]', 'NativeUI.SettingsDrive.cs:DriveT5c'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5e', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5e]', 'NativeUI.SettingsDrive.cs:DriveT5e'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5f', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5f]', 'NativeUI.SettingsDrive.cs:DriveT5f'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5g', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5g]', 'NativeUI.SettingsDrive.cs:DriveT5g'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5h', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5h]', 'NativeUI.SettingsDrive.cs:DriveT5h'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t7', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t7]', 'NativeUI.SettingsDrive.cs:DriveT7'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w10', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w10]', 'NativeUI.SettingsDrive.cs:DriveW10'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w2', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w2]', 'NativeUI.SettingsDrive.cs:DriveW2'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3]', 'NativeUI.SettingsDrive.cs:DriveW3'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3b]', 'NativeUI.SettingsDrive.cs:DriveW3b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3c', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3c]', 'NativeUI.SettingsDrive.cs:DriveW3c'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w4', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w4]', 'NativeUI.SettingsDrive.cs:DriveW4'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveT5g-perf', 'dispatch:NativeUI.SettingsDrive.cs:DriveT5g[perf]', 'NativeUI.SettingsDrive.cs:DrvList'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveT5g-visuals', 'dispatch:NativeUI.SettingsDrive.cs:DriveT5g[visuals]', 'NativeUI.SettingsDrive.cs:DrvBloomState'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-card', 'dispatch:PlayerCardMotionDev.cs:DevRun[card]', 'PlayerCardsUI.cs:DevMotionAct'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-close', 'dispatch:PlayerCardMotionDev.cs:DevRun[close]', 'PlayerCardsUI.cs:DevMotionAct'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-seed', 'dispatch:PlayerCardMotionDev.cs:DevRun[seed]', 'PlayerCardMotionDev.cs:DevSeed'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t39', 'dispatch:PlayerCardMotionDev.cs:DevRun[t39]', 'PlayerCardMotionDev.cs:DevT39'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t40', 'dispatch:PlayerCardMotionDev.cs:DevRun[t40]', 'PlayerCardMotionDev.cs:DevT40'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t41', 'dispatch:PlayerCardMotionDev.cs:DevRun[t41]', 'PlayerCardMotionDev.cs:DevT41'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t49', 'dispatch:PlayerCardMotionDev.cs:DevRun[t49]', 'PlayerCardMotionDev.cs:DevT49'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t50', 'dispatch:PlayerCardMotionDev.cs:DevRun[t50]', 'PlayerCardMotionDev.cs:DevT50'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t51', 'dispatch:PlayerCardMotionDev.cs:DevRun[t51]', 'PlayerCardMotionDev.cs:DevT51'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-card', 'dispatch:PlayerCardsUI.cs:DevMotionAct[card]', 'PlayerCardsUI.cs:DevMotionCard'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-seed', 'dispatch:PlayerCardsUI.cs:DevMotionAct[seed]', 'PlayerCardsUI.cs:DevSeedMotionPrints'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-accept', 'dispatch:PlayerCardsUI.cs:DevTrade[accept]', 'PlayerCardsUI.cs:OnAcceptClick'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-cancel', 'dispatch:PlayerCardsUI.cs:DevTrade[cancel]', 'PlayerCardsUI.cs:OnCloseClick'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-decline', 'dispatch:PlayerCardsUI.cs:DevTrade[decline]', 'PlayerCardsUI.cs:OnCloseClick'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-new', 'dispatch:PlayerCardsUI.cs:DevTrade[new]', 'PlayerCardsUI.cs:StartTradeSearch'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-offer', 'dispatch:PlayerCardsUI.cs:DevTrade[offer]', 'PlayerCardsUI.cs:StartCompose'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-pick', 'dispatch:PlayerCardsUI.cs:DevTrade[pick]', 'PlayerCardsUI.cs:StartCompose'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-send', 'dispatch:PlayerCardsUI.cs:DevTrade[send]', 'PlayerCardsUI.cs:SendProposal'),
    ('dispatch-PlayerCardsUI.cs-HandleAnswer-http', 'dispatch:PlayerCardsUI.cs:HandleAnswer[http]', 'PlayerCardsUI.cs:ClearIntent'),
    ('dispatch-SessionReportRules.cs-Parse-games', 'dispatch:SessionReportRules.cs:Parse[games]', 'FfaNumberingRules.cs:Games'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SAnimCos', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SAnimCos]', 'PlayerEffectCosmetic.cs:SetAnimatedCosmetics'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SHeavyFont', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SHeavyFont]', 'NativeUI.cs:SetUiHeavyFont'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SLight', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SLight]', 'Plugin.cs:SetLighting'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SMenuMus', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SMenuMus]', 'NativeUI.cs:SetMenuMusicMode'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SPColor', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SPColor]', 'PlayerColorCosmetic.cs:SetShowPlayerColors'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SShad', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SShad]', 'Plugin.cs:SetShadows'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-STrail', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[STrail]', 'TrailRenderer.cs:SetShowTrails'),
    ('dispatch-SettingsModel.cs-ActivationAccepts-DESTRUCTIVE', 'dispatch:SettingsModel.cs:ActivationAccepts[DESTRUCTIVE]', 'FfaNumberingRules.cs:Enter'),
    ('field-FfaLateRules.cs-BoundaryDigest', 'field:FfaLateRules.cs:BoundaryDigest', 'FfaLateRules.cs:BoundaryDigest'),
    ('field-Keybinds.cs-HookDown', 'field:Keybinds.cs:HookDown', 'Keybinds.cs:VanillaDown'),
    ('field-NametagFontRenderer.cs', 'field:NametagFontRenderer.cs:?', 'NametagFontRenderer.cs:PollLoop'),
    ('field-NametagGlowRenderer.cs', 'field:NametagGlowRenderer.cs:?', 'NametagGlowRenderer.cs:PollLoop'),
    ('field-RoomActors.cs', 'field:RoomActors.cs:?', 'FfaLateEntry.cs:KeptPlayers'),
    ('field-SecureRouteRules.cs', 'field:SecureRouteRules.cs:?', 'PortraitRenderDance.cs:Free'),
    ('field-TrailRenderer.cs', 'field:TrailRenderer.cs:?', 'TrailRenderer.cs:EnsureSprite'),
    ('harmony-CustomCosmetics.cs-CosmeticButtonSpawnerPatch.Postfix-1-CharacterCreatorButtonSpawner.OpenMenu', 'harmony:CustomCosmetics.cs:CosmeticButtonSpawnerPatch.Postfix#1(CharacterCreatorButtonSpawner.OpenMenu)', 'CustomCosmetics.cs:Postfix#1'),
    ('harmony-FfaAssembly.cs-FfaAssembly_LoadGate_Patch.Prefix-MapManager.RPCA_LoadLevel', 'harmony:FfaAssembly.cs:FfaAssembly_LoadGate_Patch.Prefix(MapManager.RPCA_LoadLevel)', 'FfaAssembly.cs:Prefix'),
    ('harmony-FfaLateEntry.cs-FfaLate_CallInHold_Patch.Prefix-5-MapManager.RPCA_CallInNewMapAndMovePlayers', 'harmony:FfaLateEntry.cs:FfaLate_CallInHold_Patch.Prefix#5(MapManager.RPCA_CallInNewMapAndMovePlayers)', 'FfaLateEntry.cs:Prefix#5'),
    ('harmony-FfaLateEntry.cs-FfaLate_ForceQuarantine_Patch.Prefix-2-HealthHandler.RPCA_SendTakeForce', 'harmony:FfaLateEntry.cs:FfaLate_ForceQuarantine_Patch.Prefix#2(HealthHandler.RPCA_SendTakeForce)', 'FfaLateEntry.cs:Prefix#2'),
    ('harmony-FfaLateEntry.cs-FfaLate_NoMapReport_Patch.Prefix-4-MapManager.ReportMapLoaded', 'harmony:FfaLateEntry.cs:FfaLate_NoMapReport_Patch.Prefix#4(MapManager.ReportMapLoaded)', 'FfaLateEntry.cs:Prefix#4'),
    ('harmony-FfaLateEntry.cs-FfaLate_NoSyncReply_Patch.Prefix-3-GM_ArmsRace.RPCO_RequestSyncUp', 'harmony:FfaLateEntry.cs:FfaLate_NoSyncReply_Patch.Prefix#3(GM_ArmsRace.RPCO_RequestSyncUp)', 'FfaLateEntry.cs:Prefix#3'),
    ('harmony-FfaLateEntry.cs-FfaLate_PickQuarantine_Patch.Prefix-1-ApplyCardStats.RPCA_Pick', 'harmony:FfaLateEntry.cs:FfaLate_PickQuarantine_Patch.Prefix#1(ApplyCardStats.RPCA_Pick)', 'FfaLateEntry.cs:Prefix#1'),
    ('harmony-FfaLateEntry.cs-FfaLate_Register_Patch.Postfix-3-PlayerManager.RegisterPlayer', 'harmony:FfaLateEntry.cs:FfaLate_Register_Patch.Postfix#3(PlayerManager.RegisterPlayer)', 'FfaLateEntry.cs:Postfix#3'),
    ('harmony-FfaLateEntry.cs-FfaLate_Simulated_Patch.Postfix-2-PlayerManager.SetPlayersSimulated', 'harmony:FfaLateEntry.cs:FfaLate_Simulated_Patch.Postfix#2(PlayerManager.SetPlayersSimulated)', 'FfaLateEntry.cs:Postfix#2'),
    ('harmony-FfaLateEntry.cs-FfaLate_Visible_Patch.Postfix-1-PlayerManager.SetPlayersVisible', 'harmony:FfaLateEntry.cs:FfaLate_Visible_Patch.Postfix#1(PlayerManager.SetPlayersVisible)', 'FfaLateEntry.cs:Postfix#1'),
    ('harmony-FfaMapScale.cs-MapTransition_SetStartPos_FfaScale_Patch.Postfix-1-MapTransition.SetStartPos', 'harmony:FfaMapScale.cs:MapTransition_SetStartPos_FfaScale_Patch.Postfix#1(MapTransition.SetStartPos)', 'FfaMapScale.cs:Postfix#1'),
    ('harmony-FfaMapScale.cs-OutOfBoundsHandler_FfaScale_Patch.Prefix-2-OutOfBoundsHandler.LateUpdate', 'harmony:FfaMapScale.cs:OutOfBoundsHandler_FfaScale_Patch.Prefix#2(OutOfBoundsHandler.LateUpdate)', 'FfaMapScale.cs:Prefix#2'),
    ('harmony-FfaMapScale.cs-PhotonMapObject_Start_FfaScale_Patch.Postfix-2-PhotonMapObject.Start', 'harmony:FfaMapScale.cs:PhotonMapObject_Start_FfaScale_Patch.Postfix#2(PhotonMapObject.Start)', 'FfaMapScale.cs:Postfix#2'),
    ('harmony-FfaMapScale.cs-PlayerManager_MovePlayers_FfaScale_Patch.Prefix-1-PlayerManager.MovePlayers', 'harmony:FfaMapScale.cs:PlayerManager_MovePlayers_FfaScale_Patch.Prefix#1(PlayerManager.MovePlayers)', 'FfaMapScale.cs:Prefix#1'),
    ('harmony-FfaMode.cs-GMArmsRace_DoStartGame_Ffa_Patch.Prefix-4-GM_ArmsRace.DoStartGame', 'harmony:FfaMode.cs:GMArmsRace_DoStartGame_Ffa_Patch.Prefix#4(GM_ArmsRace.DoStartGame)', 'FfaMode.cs:Prefix#4'),
    ('harmony-FfaMode.cs-GMArmsRace_NextRound_Ffa_Patch.Prefix-3-GM_ArmsRace.RPCA_NextRound', 'harmony:FfaMode.cs:GMArmsRace_NextRound_Ffa_Patch.Prefix#3(GM_ArmsRace.RPCA_NextRound)', 'FfaMode.cs:Prefix#3'),
    ('harmony-FfaMode.cs-GMArmsRace_PlayerDied_Ffa_Patch.Prefix-1-GM_ArmsRace.PlayerDied', 'harmony:FfaMode.cs:GMArmsRace_PlayerDied_Ffa_Patch.Prefix#1(GM_ArmsRace.PlayerDied)', 'FfaMode.cs:Prefix#1'),
    ('harmony-FfaMode.cs-MapManager_GetSpawnPoints_FfaShuffle_Patch.Postfix-1-MapManager.GetSpawnPoints', 'harmony:FfaMode.cs:MapManager_GetSpawnPoints_FfaShuffle_Patch.Postfix#1(MapManager.GetSpawnPoints)', 'FfaMode.cs:Postfix#1'),
    ('harmony-FfaMode.cs-NCH_OnPlayerLeftRoom_Ffa_Patch.Prefix-6-NetworkConnectionHandler.OnPlayerLeftRoom', 'harmony:FfaMode.cs:NCH_OnPlayerLeftRoom_Ffa_Patch.Prefix#6(NetworkConnectionHandler.OnPlayerLeftRoom)', 'FfaMode.cs:Prefix#6'),
    ('harmony-Keybinds.cs-CharacterReadyPatch.Transpiler-2-CharacterSelectionInstance.Update', 'harmony:Keybinds.cs:CharacterReadyPatch.Transpiler#2(CharacterSelectionInstance.Update)', 'Keybinds.cs:Transpiler#2'),
    ('harmony-Keybinds.cs-LobbyReadyPatch.Transpiler-1-PlayerAssigner.LateUpdate', 'harmony:Keybinds.cs:LobbyReadyPatch.Transpiler#1(PlayerAssigner.LateUpdate)', 'Keybinds.cs:Transpiler#1'),
    ('harmony-Keybinds.cs-MapArtPatch.Transpiler-3-ArtHandler.Update', 'harmony:Keybinds.cs:MapArtPatch.Transpiler#3(ArtHandler.Update)', 'Keybinds.cs:Transpiler#3'),
    ('harmony-MusicEngine.cs-MusicSuppressionPatch.PlayIngamePrefix', 'harmony:MusicEngine.cs:MusicSuppressionPatch.PlayIngamePrefix(?)', 'MusicEngine.cs:PlayIngamePrefix'),
    ('harmony-MusicEngine.cs-MusicSuppressionPatch.PlayMainMenuPrefix', 'harmony:MusicEngine.cs:MusicSuppressionPatch.PlayMainMenuPrefix(?)', 'MusicEngine.cs:PlayMainMenuPrefix'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.AfterSpectatorMute', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.AfterSpectatorMute(?)', 'NetworkReplicaDiagnostics.cs:AfterSpectatorMute'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.Prefix-1', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.Prefix#1(?)', 'NetworkReplicaDiagnostics.cs:Prefix#1'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.Transpiler', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.Transpiler(?)', 'NetworkReplicaDiagnostics.cs:Transpiler'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorBoundaryPatch.Postfix-2', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorBoundaryPatch.Postfix#2(?)', 'NetworkReplicaDiagnostics.cs:Postfix#2'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorFfaTerminalPatch.Postfix-1', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorFfaTerminalPatch.Postfix#1(?)', 'NetworkReplicaDiagnostics.cs:Postfix#1'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorGmTerminalPatch.Prefix-2', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorGmTerminalPatch.Prefix#2(?)', 'NetworkReplicaDiagnostics.cs:Prefix#2'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorSnapshotPatch.Postfix-4', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorSnapshotPatch.Postfix#4(?)', 'NetworkReplicaDiagnostics.cs:Postfix#4'),
    ('harmony-Plugin.cs-ArtHandlerNextArtPatch.Prefix-25-ArtHandler.NextArt', 'harmony:Plugin.cs:ArtHandlerNextArtPatch.Prefix#25(ArtHandler.NextArt)', 'Plugin.cs:Prefix#25'),
    ('harmony-Plugin.cs-CardChoiceEndPickPatch.Prefix-16-CardChoice.RPCA_DoEndPick', 'harmony:Plugin.cs:CardChoiceEndPickPatch.Prefix#16(CardChoice.RPCA_DoEndPick)', 'Plugin.cs:Prefix#16'),
    ('harmony-Plugin.cs-CardChoiceVisuals_Show_Competitive_Patch.Postfix-8-CardChoiceVisuals.Show', 'harmony:Plugin.cs:CardChoiceVisuals_Show_Competitive_Patch.Postfix#8(CardChoiceVisuals.Show)', 'Plugin.cs:Postfix#8'),
    ('harmony-Plugin.cs-GMArmsRaceAwakePatch.Postfix-1-GM_ArmsRace.Awake', 'harmony:Plugin.cs:GMArmsRaceAwakePatch.Postfix#1(GM_ArmsRace.Awake)', 'Plugin.cs:Postfix#1'),
    ('harmony-Plugin.cs-MapPhysicalColorPatch.Postfix-20-Map.Start', 'harmony:Plugin.cs:MapPhysicalColorPatch.Postfix#20(Map.Start)', 'Plugin.cs:Postfix#20'),
    ('harmony-Plugin.cs-NetworkConnectionHandler_NetworkRestart_Diag_Patch.Prefix-4-NetworkConnectionHandler.NetworkRestart', 'harmony:Plugin.cs:NetworkConnectionHandler_NetworkRestart_Diag_Patch.Prefix#4(NetworkConnectionHandler.NetworkRestart)', 'Plugin.cs:Prefix#4'),
    ('harmony-Plugin.cs-PlayerManagerResetCharactersBlockResetPatch.Postfix-18-PlayerManager.ResetCharacters', 'harmony:Plugin.cs:PlayerManagerResetCharactersBlockResetPatch.Postfix#18(PlayerManager.ResetCharacters)', 'Plugin.cs:Postfix#18'),
    ('harmony-Plugin.cs-QuickplayChurnAbandonGuardPatch.Prefix-3-NetworkConnectionHandler.PlayOnBestActiveRegion', 'harmony:Plugin.cs:QuickplayChurnAbandonGuardPatch.Prefix#3(NetworkConnectionHandler.PlayOnBestActiveRegion)', 'Plugin.cs:Prefix#3'),
    ('harmony-Plugin.cs-QuickplayChurnFreezePatch.Postfix-3-NetworkConnectionHandler.OnPlayerEnteredRoom', 'harmony:Plugin.cs:QuickplayChurnFreezePatch.Postfix#3(NetworkConnectionHandler.OnPlayerEnteredRoom)', 'Plugin.cs:Postfix#3'),
    ('harmony-PoisonSync.cs-PoisonArmPatch.Finalizer-3-RayHitPoison.DoHitEffect', 'harmony:PoisonSync.cs:PoisonArmPatch.Finalizer#3(RayHitPoison.DoHitEffect)', 'PoisonSync.cs:Finalizer#3'),
    ('harmony-PoisonSync.cs-PoisonArmPatch.Prefix-4-RayHitPoison.DoHitEffect', 'harmony:PoisonSync.cs:PoisonArmPatch.Prefix#4(RayHitPoison.DoHitEffect)', 'PoisonSync.cs:Prefix#4'),
    ('harmony-PoisonSync.cs-PoisonDeathFlushPatch.After-5-HealthHandler.RPCA_Die', 'harmony:PoisonSync.cs:PoisonDeathFlushPatch.After#5(HealthHandler.RPCA_Die)', 'PoisonSync.cs:After#5'),
    ('harmony-PoisonSync.cs-PoisonDotSchedulerPatch.Prefix-1-DamageOverTime.TakeDamageOverTime', 'harmony:PoisonSync.cs:PoisonDotSchedulerPatch.Prefix#1(DamageOverTime.TakeDamageOverTime)', 'PoisonSync.cs:Prefix#1'),
    ('harmony-PoisonSync.cs-PoisonHitBracketPatch.Finalizer-2-ProjectileHit.Hit', 'harmony:PoisonSync.cs:PoisonHitBracketPatch.Finalizer#2(ProjectileHit.Hit)', 'PoisonSync.cs:Finalizer#2'),
    ('harmony-PoisonSync.cs-PoisonHitBracketPatch.Prefix-3-ProjectileHit.Hit', 'harmony:PoisonSync.cs:PoisonHitBracketPatch.Prefix#3(ProjectileHit.Hit)', 'PoisonSync.cs:Prefix#3'),
    ('harmony-PoisonSync.cs-PoisonPhoenixBoundaryPatch.After-4-HealthHandler.RPCA_Die_Phoenix', 'harmony:PoisonSync.cs:PoisonPhoenixBoundaryPatch.After#4(HealthHandler.RPCA_Die_Phoenix)', 'PoisonSync.cs:After#4'),
    ('harmony-PoisonSync.cs-PoisonPhoenixBoundaryPatch.Threw-3-HealthHandler.RPCA_Die_Phoenix', 'harmony:PoisonSync.cs:PoisonPhoenixBoundaryPatch.Threw#3(HealthHandler.RPCA_Die_Phoenix)', 'PoisonSync.cs:Threw#3'),
    ('harmony-PoisonSync.cs-PoisonPointBoundaryPatch.After-3', 'harmony:PoisonSync.cs:PoisonPointBoundaryPatch.After#3(?)', 'PoisonSync.cs:After#3'),
    ('harmony-PoisonSync.cs-PoisonPointBoundaryPatch.Threw-2', 'harmony:PoisonSync.cs:PoisonPointBoundaryPatch.Threw#2(?)', 'PoisonSync.cs:Threw#2'),
    ('harmony-PoisonSync.cs-PoisonReviveFencePatch.AfterRevive-HealthHandler.Revive', 'harmony:PoisonSync.cs:PoisonReviveFencePatch.AfterRevive(HealthHandler.Revive)', 'PoisonSync.cs:AfterRevive'),
    ('harmony-PoisonSync.cs-PoisonReviveFencePatch.Threw-1-HealthHandler.Revive', 'harmony:PoisonSync.cs:PoisonReviveFencePatch.Threw#1(HealthHandler.Revive)', 'PoisonSync.cs:Threw#1'),
    ('harmony-SpectatorPatches.cs-Spectator_BoundaryObserver_Patch.Postfix-3-MapManager.RPCA_CallInNewMapAndMovePlayers', 'harmony:SpectatorPatches.cs:Spectator_BoundaryObserver_Patch.Postfix#3(MapManager.RPCA_CallInNewMapAndMovePlayers)', 'SpectatorPatches.cs:Postfix#3'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_CallInBare_Patch.Prefix-21-MapManager.CallInNewMap', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_CallInBare_Patch.Prefix#21(MapManager.CallInNewMap)', 'SpectatorPatches.cs:Prefix#21'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_CallIn_Patch.Prefix-20-MapManager.CallInNewMapAndMovePlayers', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_CallIn_Patch.Prefix#20(MapManager.CallInNewMapAndMovePlayers)', 'SpectatorPatches.cs:Prefix#20'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_Load_Patch.Prefix-19-MapManager.LoadNextLevel', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_Load_Patch.Prefix#19(MapManager.LoadNextLevel)', 'SpectatorPatches.cs:Prefix#19'),
    ('harmony-SpectatorPatches.cs-Spectator_RegistrationFirewall_Patch.Prefix-25-PlayerManager.RegisterPlayer', 'harmony:SpectatorPatches.cs:Spectator_RegistrationFirewall_Patch.Prefix#25(PlayerManager.RegisterPlayer)', 'SpectatorPatches.cs:Prefix#25'),
    ('harmony-SpectatorPatches.cs-Spectator_ReplayQuarantine_Patch.Prefix-15-PhotonMapObject.Start', 'harmony:SpectatorPatches.cs:Spectator_ReplayQuarantine_Patch.Prefix#15(PhotonMapObject.Start)', 'SpectatorPatches.cs:Prefix#15'),
    ('harmony-VanillaCardSequence.cs-CardChoice_DoPick_SameCards_Patch.Prefix-2-CardChoice.DoPick', 'harmony:VanillaCardSequence.cs:CardChoice_DoPick_SameCards_Patch.Prefix#2(CardChoice.DoPick)', 'VanillaCardSequence.cs:Prefix#2'),
    ('harmony-VanillaCardSequence.cs-CardChoice_ReplaceCards_SameCards_Patch.Prefix-3-CardChoice.ReplaceCards', 'harmony:VanillaCardSequence.cs:CardChoice_ReplaceCards_SameCards_Patch.Prefix#3(CardChoice.ReplaceCards)', 'VanillaCardSequence.cs:Prefix#3'),
    ('harmony-VanillaCardSequence.cs-GMArmsRace_DoStartGame_SameCards_Patch.Prefix-1-GM_ArmsRace.DoStartGame', 'harmony:VanillaCardSequence.cs:GMArmsRace_DoStartGame_SameCards_Patch.Prefix#1(GM_ArmsRace.DoStartGame)', 'VanillaCardSequence.cs:Prefix#1'),
    ('harmony-VanillaFixes.cs-PhoenixRespawnPatch.BeforeRespawn-DeathEffect.RespawnPlayer', 'harmony:VanillaFixes.cs:PhoenixRespawnPatch.BeforeRespawn(DeathEffect.RespawnPlayer)', 'VanillaFixes.cs:BeforeRespawn'),
    ('harmony-VanillaFixes.cs-RemotePlayerIdOrderPatch.Prefix-5-.Start', 'harmony:VanillaFixes.cs:RemotePlayerIdOrderPatch.Prefix#5(?.Start)', 'VanillaFixes.cs:Prefix#5'),
    ('harmony-VanillaFixes.cs-StaleProjectileSweepPatch.AfterMovePlayers', 'harmony:VanillaFixes.cs:StaleProjectileSweepPatch.AfterMovePlayers(?)', 'VanillaFixes.cs:AfterMovePlayers'),
    ('harmony-VanillaFixes.cs-StaleProjectileSweepPatch.BeforeMovePlayers', 'harmony:VanillaFixes.cs:StaleProjectileSweepPatch.BeforeMovePlayers(?)', 'VanillaFixes.cs:BeforeMovePlayers'),
    ('reflection-Plugin.cs-OnJoinedRoom', 'reflection:Plugin.cs:OnJoinedRoom', 'Plugin.cs:OnJoinedRoom'),
    ('reflection-Plugin.cs-OnPlayerEnteredRoom', 'reflection:Plugin.cs:OnPlayerEnteredRoom', 'Plugin.cs:OnPlayerEnteredRoom'),
    ('reflection-Plugin.cs-OnPlayerLeftRoom', 'reflection:Plugin.cs:OnPlayerLeftRoom', 'Plugin.cs:OnPlayerLeftRoom'),
    ('unity-MusicEngine.cs-MusicEngineHost.Awake', 'unity:MusicEngine.cs:MusicEngineHost.Awake', 'MusicEngine.cs:Awake'),
    ('unity-MusicEngine.cs-MusicEngineHost.Update', 'unity:MusicEngine.cs:MusicEngineHost.Update', 'MusicEngine.cs:Update'),
    ('unity-NativeUI.cs-FfaRecentGraphDrawer.OnGUI-1', 'unity:NativeUI.cs:FfaRecentGraphDrawer.OnGUI#1', 'NativeUI.cs:OnGUI#1'),
    ('unity-NativeUI.cs-OneVTwoHoverDrawer.OnGUI-2', 'unity:NativeUI.cs:OneVTwoHoverDrawer.OnGUI#2', 'NativeUI.cs:OnGUI#2'),
    ('unity-Plugin.cs-CompetitiveRoundsBehaviour.OnDestroy', 'unity:Plugin.cs:CompetitiveRoundsBehaviour.OnDestroy', 'Plugin.cs:OnDestroy'),
    ('unity-Plugin.cs-CompetitiveRoundsBehaviour.Update-2', 'unity:Plugin.cs:CompetitiveRoundsBehaviour.Update#2', 'Plugin.cs:Update#2'),
    ('unity-Plugin.cs-Plugin.Awake-1', 'unity:Plugin.cs:Plugin.Awake#1', 'Plugin.cs:Awake#1'),
    ('unity-Plugin.cs-QueueRoomJoiner.Update-1', 'unity:Plugin.cs:QueueRoomJoiner.Update#1', 'Plugin.cs:Update#1'),
]
PIN5 = "backend/tests/test_keybind_surfaces.py::test_h1_fix5_each_unresolved_end_is_pinned_in_source[%s]"


def test_h1_fix5_the_end_table_is_every_unresolved_end_beyond_the_four(attach4):
    st, cman, att, aman = attach4
    names = [n for i, n, m in FIX5_ENDS]
    assert len(names) == len(set(names)) == len({i for i, n, m in FIX5_ENDS}) == 167
    extra = set(att["unresolved"]) - set(names)
    assert len(extra) == 4 and RESET_MENU in extra, sorted(extra)
    assert set(names) <= set(att["unresolved"]), sorted(set(names) - set(att["unresolved"]))
    for n in extra:
        assert not aman["unresolved"][n][0].startswith(PIN5.split("[")[0]), n
    for i, n, m in FIX5_ENDS:
        assert aman["unresolved"][n][0] == PIN5 % i, (n, aman["unresolved"][n][0])


def _plugin_src(fn):
    p = REPO / "plugin" / fn
    assert p.is_file(), "plugin/%s missing" % fn
    return p.read_text(encoding="utf-8")


def _base(mid):
    return mid.split("#", 1)[0]


@pytest.mark.parametrize("eid,name,node", FIX5_ENDS, ids=[r[0] for r in FIX5_ENDS])
def test_h1_fix5_each_unresolved_end_is_pinned_in_source(eid, name, node):
    """The source pin of each UNRESOLVED end, read from plugin/ by itself (no
    oracle): the patch class, message, literal, field or case label the end
    is named for is where the name says, and the member it ends at exists."""
    nfile, nmid = node.split(":", 1)
    assert re.search(r"\b%s\b" % re.escape(_base(nmid)), _plugin_src(nfile)), node
    kind, rest = name.split(":", 1)
    fn, what = rest.split(":", 1)
    src = _plugin_src(fn)
    if kind == "harmony":
        mm = re.fullmatch(r"(\w+)\.([\w#]+)\(([\w.?]+)\)", what)
        assert mm, name
        cls = re.search(r"\bclass\s+%s\b" % re.escape(mm.group(1)), src)
        assert cls, name
        assert re.search(r"\b%s\s*\(" % re.escape(_base(mm.group(2))), src[cls.end():]), name
        near = src[max(0, cls.start() - 600):cls.start()] + src[cls.end():]
        assert re.search(r"\[\s*Harmony", near), name
        target = mm.group(3).split(".")[-1]
        if target != "?":
            assert re.search(r"\b%s\b" % re.escape(target), near), name
    elif kind == "unity":
        mm = re.fullmatch(r"(\w+)\.([\w#]+)", what)
        assert mm, name
        cls = re.search(r"\bclass\s+%s\b" % re.escape(mm.group(1)), src)
        assert cls, name
        assert re.search(r"\bvoid\s+%s\s*\(" % re.escape(_base(mm.group(2))), src[cls.end():]), name
    elif kind == "reflection":
        assert re.search(r"\b%s\s*\(" % re.escape(_base(what)), src), name
        lit = '"%s"' % _base(what)
        assert any(lit in p.read_text(encoding="utf-8") for p in (REPO / "plugin").glob("*.cs")), name
    elif kind == "field":
        if what != "?":
            assert re.search(r"\b%s\b" % re.escape(what), src), name
        assert re.search(r"\b%s\b" % re.escape(_base(nmid)), src), name
    elif kind == "dispatch":
        mm = re.fullmatch(r"([\w#]+)\[(.*)\]", what)
        assert mm, name
        assert re.search(r"\b%s\s*\(" % re.escape(_base(mm.group(1))), src), name
        assert re.search(r'case\s+"%s"\s*:' % re.escape(mm.group(2)), src), name
    else:
        pytest.fail("an end of an unknown kind: %s" % name)
