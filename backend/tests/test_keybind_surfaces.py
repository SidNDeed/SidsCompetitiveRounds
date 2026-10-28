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
each UNRESOLVED end the complete traversal reaches beyond fix pass 4's four
(167 at item 17's fix-5 tip; 1022 at the merged v1.41.0 client tree, the
table regenerated from the fix-5 writer's output there; 1136 at the
merged round 3 tree, with the RJ Stage 2 and readmission ends; 1137 at
the round 3 refit tree, with the autolog fold's LogBundleCore.cs field end;
1141 at the round 3 fold tree, with the net-stall lane's three
using-directive ends and the stall detector's stream-snapshot field).
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
    for kind in ("hop", "end", "cycle", "member", "sink"):
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


# The sinks whose chains carry the ResetMenuPatch hop, as the check prints them
# (sorted, comma-joined). Fix 5's graph had ApplyJoin's chain only; at the
# merged v1.41.0 client tree the folded lanes' references join the InfoLibrary
# and keyboard sinks' subgraph to it, so the hop is on seven chains.
RESET_MENU_CHAINS = ",".join(("InfoLibrary.cs:ControlsOutro", "InfoLibrary.cs:Cosmetics", "InfoLibrary.cs:Spectating",
                              "InfoLibrary.cs:StartHere", "InfoLibrary.cs:VanillaBugs", "InfoViz.cs:BuildKeyboard",
                              "Keybinds.cs:ApplyJoin"))


def test_h1_fix4_an_unresolved_hop_without_a_naming_control_is_red(attach4, tmp_path):
    st, cman, att, aman = attach4
    rows = [r for r in _rows(ATTACH) if not r.startswith("unresolved\t%s\t" % RESET_MENU)]
    problems = _check(st, tmp_path, attach=rows)
    assert any(p.startswith("UNRESOLVED hop %s (on the chains of %s) has no disposition" % (RESET_MENU, RESET_MENU_CHAINS))
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


# ---- merged hold 3 (Codex client merged round 1 H1): the normalized
# full-member digest. A hop pins the one statement that holds its reference;
# at plugin/NativeUI.cs ApplyInfoNavFilter, `bool all = q.Length == 0;` made
# unconditionally true short-circuits `bool vis = all || InfoArticleMatches(...)`
# and suppresses the binding-dependent search path while that statement, its
# hop row and (at T) the sink digest stay the same. The fixture below has the
# same shape: Sink <- Matches <- Filter (the guard and the short-circuit) <- Update.

ADJACENT = """internal static class Lib
{
    internal static string Q = "";
    internal static string Sink() { return "x"; }
    internal static bool Matches(string q) { return Sink().Contains(q); }
    internal static void Filter()
    {
        string q = Q.Trim();
        bool all = q.Length == 0;
        int total = 0;
        for (int i = 0; i < 3; i++)
        {
            bool vis = all || Matches(q);
            Show(i, vis);
            if (!vis) continue;
            total++;
        }
    }
    internal static void Show(int i, bool v) { }
    internal static void Update() { Filter(); }
}
"""

# (label, old, new, red?): the two adjacent-guard edits of the hold-3 red
# control (the report's edit, then a reordered early exit), and the negative
# controls (a comment and whitespace edit the normalization removes; an edit in
# Show, a member Filter calls that no path crosses: outside every traversed
# member, the stated bound)
ADJACENT_EDITS = [
    ("guard made unconditionally true", "bool all = q.Length == 0;", "bool all = true;", True),
    ("early exit reordered", "            Show(i, vis);\n            if (!vis) continue;\n",
     "            if (!vis) continue;\n            Show(i, vis);\n", True),
    ("comment and whitespace only", "        int total = 0;\n", "        int   total = 0;  // a count\n", False),
    ("edit outside every traversed member", "internal static void Show(int i, bool v) { }",
     "internal static void Show(int i, bool v) { if (v) return; }", False),
]


def _adjacent_state(tmp_path, monkeypatch, src):
    d = tmp_path / ("t%d" % len(list(tmp_path.iterdir())))
    d.mkdir()
    return _synthetic(d, monkeypatch, src, "Update")


@pytest.mark.parametrize("label,old,new,red", ADJACENT_EDITS, ids=[e[0].replace(" ", "-") for e in ADJACENT_EDITS])
def test_hold3_an_adjacent_control_flow_edit_in_a_traversed_member_is_red(tmp_path, monkeypatch, label, old, new, red):
    st = _adjacent_state(tmp_path, monkeypatch, ADJACENT)
    base = KS.derive_attach(st, ["Lib.cs:Sink"])
    assert base["sinks"]["Lib.cs:Sink"]["attached"] and base["truncated"] == []
    assert {"Lib.cs:Sink", "Lib.cs:Matches", "Lib.cs:Filter", "Lib.cs:Update"} <= set(base["sinks"]["Lib.cs:Sink"]["members"])
    assert "Lib.cs:Show" not in base["sinks"]["Lib.cs:Sink"]["nodes"]
    p = tmp_path / "attach.tsv"
    p.write_text("\n".join(KS.attach_lines(st.t, base, {"root": {"Lib.cs:Update": (0, "", "the synthetic root")},
                                                         "unresolved": {}})), encoding="utf-8")
    aman, probs = KS.read_attach(str(p))
    assert probs == [] and set(aman["member"]) == set(base["sinks"]["Lib.cs:Sink"]["members"]), probs
    # the unedited fixture is GREEN against its own manifest
    assert KS.attach_problems(str(tmp_path), st, base, aman, {}) == []
    assert ADJACENT.count(old) == 1, label
    st2 = _adjacent_state(tmp_path, monkeypatch, ADJACENT.replace(old, new))
    cut = KS.derive_attach(st2, ["Lib.cs:Sink"])
    rows = KS.attach_rows(st2.t, cut)
    problems = KS.attach_problems(str(tmp_path), st2, cut, aman, {})
    if not red:
        assert problems == [], (label, problems)
        return
    # the statement-level pins alone do not see the edit: every hop, end and
    # cycle row is unchanged (the round-1 false green) ...
    for kind in ("hop", "end", "cycle"):
        assert rows[kind] == aman[kind], (label, kind)
    # ... and the member digest turns it RED, naming the member and the sink
    assert any(x.startswith("MEMBER BODY CHANGED Lib.cs:Filter: ") and "display sink(s) Lib.cs:Sink:" in x
               for x in problems), (label, problems)
    assert any(x.startswith("SINK CHANGED display sink Lib.cs:Sink: ") for x in problems), (label, problems)
    assert not any("Lib.cs:Matches" in x or "Lib.cs:Update" in x for x in problems if x.startswith("MEMBER")), problems


def test_hold3_every_traversed_member_of_the_six_hop_path_is_hashed_into_its_sink(attach4):
    st, cman, att, aman = attach4
    sink = att["sinks"][PATH5[0]]
    for n in PATH5:
        assert n in sink["members"], n
        assert aman["member"][n] == sink["members"][n] == KS.member_body_digest(st.t, n), n
    rows = KS.attach_rows(st.t, att)
    assert set(rows["member"]) == {n for rec in att["sinks"].values() for n in rec["members"]}
    assert all(not (n.startswith(("field:", "register:"))) for n in rows["member"])


# Every UNRESOLVED end the complete traversal reaches beyond fix pass 4's
# four Harmony ends: (id, end name, the member it ends at). Its control in
# tools/keybind_surfaces_attach.tsv is test_h1_fix5_each_unresolved_end_is_pinned_in_source[id].
FIX5_ENDS = [
    ('dispatch-ApiClient.cs-KickRefusalText-cannot_kick_yourself', 'dispatch:ApiClient.cs:KickRefusalText[cannot_kick_yourself]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-KickRefusalText-not_host', 'dispatch:ApiClient.cs:KickRefusalText[not_host]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-KickRefusalText-target_is_admin', 'dispatch:ApiClient.cs:KickRefusalText[target_is_admin]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-KickRefusalText-target_not_in_lobby', 'dispatch:ApiClient.cs:KickRefusalText[target_not_in_lobby]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-RulesDetailText-not_in_open_lobby', 'dispatch:ApiClient.cs:RulesDetailText[not_in_open_lobby]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-RulesDetailText-rules_need_update', 'dispatch:ApiClient.cs:RulesDetailText[rules_need_update]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-RulesDetailText-rules_unsupported', 'dispatch:ApiClient.cs:RulesDetailText[rules_unsupported]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-RulesDetailText-settings_unseen', 'dispatch:ApiClient.cs:RulesDetailText[settings_unseen]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SendLfpPing-cooldown', 'dispatch:ApiClient.cs:SendLfpPing[cooldown]', 'CompetitiveUI.cs:ShowNotification'),
    ('dispatch-ApiClient.cs-SendLfpPing-not_linked', 'dispatch:ApiClient.cs:SendLfpPing[not_linked]', 'CompetitiveUI.cs:ShowNotification'),
    ('dispatch-ApiClient.cs-SendLfpPing-queued', 'dispatch:ApiClient.cs:SendLfpPing[queued]', 'CompetitiveUI.cs:ShowNotification'),
    ('dispatch-ApiClient.cs-SendLfpPing-ranked_disabled', 'dispatch:ApiClient.cs:SendLfpPing[ranked_disabled]', 'CompetitiveUI.cs:ShowNotification'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-already_in_game', 'dispatch:ApiClient.cs:SpectateReasonExact[already_in_game]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-game_not_live', 'dispatch:ApiClient.cs:SpectateReasonExact[game_not_live]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-mode_not_ready', 'dispatch:ApiClient.cs:SpectateReasonExact[mode_not_ready]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-room_not_ready', 'dispatch:ApiClient.cs:SpectateReasonExact[room_not_ready]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-session_required', 'dispatch:ApiClient.cs:SpectateReasonExact[session_required]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-spectating_disabled', 'dispatch:ApiClient.cs:SpectateReasonExact[spectating_disabled]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-spectator_full', 'dispatch:ApiClient.cs:SpectateReasonExact[spectator_full]', 'I18n.cs:Tr'),
    ('dispatch-ApiClient.cs-SpectateReasonExact-spectator_upgrade_required', 'dispatch:ApiClient.cs:SpectateReasonExact[spectator_upgrade_required]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-crash', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[crash]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-gameplay', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[gameplay]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-high', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[high]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-low', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[low]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-medium', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[medium]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-network', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[network]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-other', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[other]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-BugChoiceLabel-ui', 'dispatch:CompetitiveUI.cs:BugChoiceLabel[ui]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-ChannelDisplayLabel-global', 'dispatch:CompetitiveUI.cs:ChannelDisplayLabel[global]', 'I18n.cs:Tr'),
    ('dispatch-CompetitiveUI.cs-DrawAdminPrompt-ban', 'dispatch:CompetitiveUI.cs:DrawAdminPrompt[ban]', 'ApiClient.cs:AdminBan'),
    ('dispatch-CompetitiveUI.cs-DrawAdminPrompt-grant', 'dispatch:CompetitiveUI.cs:DrawAdminPrompt[grant]', 'ApiClient.cs:AdminGrantAchievement'),
    ('dispatch-CompetitiveUI.cs-DrawAdminPrompt-reverse', 'dispatch:CompetitiveUI.cs:DrawAdminPrompt[reverse]', 'ApiClient.cs:AdminReverseSeries'),
    ('dispatch-DateFmt.cs-FullShortYear-DMY', 'dispatch:DateFmt.cs:FullShortYear[DMY]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-FullShortYear-YMD', 'dispatch:DateFmt.cs:FullShortYear[YMD]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-Full-DMY', 'dispatch:DateFmt.cs:Full[DMY]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-Full-YMD', 'dispatch:DateFmt.cs:Full[YMD]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-MonthDay-DMY', 'dispatch:DateFmt.cs:MonthDay[DMY]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-MonthDay-YMD', 'dispatch:DateFmt.cs:MonthDay[YMD]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-Short-DMY', 'dispatch:DateFmt.cs:Short[DMY]', 'KeybindRules.cs:ToString'),
    ('dispatch-DateFmt.cs-Short-YMD', 'dispatch:DateFmt.cs:Short[YMD]', 'KeybindRules.cs:ToString'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-admitted_late', 'dispatch:FfaAssembly.cs:HandleAnswer[admitted_late]', 'FfaAssembly.cs:OnLoadGrant'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-admitting', 'dispatch:FfaAssembly.cs:HandleAnswer[admitting]', 'FfaLateEntry.cs:FenceMaster'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-assembling', 'dispatch:FfaAssembly.cs:HandleAnswer[assembling]', 'FfaAssembly.cs:Banner'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-dissolved', 'dispatch:FfaAssembly.cs:HandleAnswer[dissolved]', 'FfaAssembly.cs:Exit'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-reformed', 'dispatch:FfaAssembly.cs:HandleAnswer[reformed]', 'FfaAssembly.cs:Move'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-start_ok', 'dispatch:FfaAssembly.cs:HandleAnswer[start_ok]', 'FfaAssembly.cs:OnLoadGrant'),
    ('dispatch-FfaAssembly.cs-HandleAnswer-wrong_region', 'dispatch:FfaAssembly.cs:HandleAnswer[wrong_region]', 'FfaAssembly.cs:OnWrongRegion'),
    ('dispatch-FfaReadmitEntryRules.cs-OnAnswer-admitted_late', 'dispatch:FfaReadmitEntryRules.cs:OnAnswer[admitted_late]', 'FfaReadmitEntryRules.cs:Refuse'),
    ('dispatch-FfaReadmitEntryRules.cs-OnAnswer-claimed', 'dispatch:FfaReadmitEntryRules.cs:OnAnswer[claimed]', 'FfaReadmitEntryRules.cs:Refuse'),
    ('dispatch-FfaReadmitEntryRules.cs-OnAnswer-entered', 'dispatch:FfaReadmitEntryRules.cs:OnAnswer[entered]', 'RegionPingSweep.cs:Done'),
    ('dispatch-FfaReadmitEntryRules.cs-OnAnswer-refused', 'dispatch:FfaReadmitEntryRules.cs:OnAnswer[refused]', 'FfaReadmitEntryRules.cs:Refuse'),
    ('dispatch-InfoViz.cs-GoldBucketName-achievements', 'dispatch:InfoViz.cs:GoldBucketName[achievements]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-betting', 'dispatch:InfoViz.cs:GoldBucketName[betting]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-boosters', 'dispatch:InfoViz.cs:GoldBucketName[boosters]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-casual_1v1', 'dispatch:InfoViz.cs:GoldBucketName[casual_1v1]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-ffa', 'dispatch:InfoViz.cs:GoldBucketName[ffa]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-level_ups', 'dispatch:InfoViz.cs:GoldBucketName[level_ups]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-other', 'dispatch:InfoViz.cs:GoldBucketName[other]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-ovt_1v2', 'dispatch:InfoViz.cs:GoldBucketName[ovt_1v2]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-ranked_1v1', 'dispatch:InfoViz.cs:GoldBucketName[ranked_1v1]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-shop_sales', 'dispatch:InfoViz.cs:GoldBucketName[shop_sales]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-GoldBucketName-team_2v2', 'dispatch:InfoViz.cs:GoldBucketName[team_2v2]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-TextFallback-damage-matrix', 'dispatch:InfoViz.cs:TextFallback[damage-matrix]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-TextFallback-refresh-flow', 'dispatch:InfoViz.cs:TextFallback[refresh-flow]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-TextFallback-refresh-gate', 'dispatch:InfoViz.cs:TextFallback[refresh-gate]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-TextFallback-refresh-sequences', 'dispatch:InfoViz.cs:TextFallback[refresh-sequences]', 'I18n.cs:Tr'),
    ('dispatch-InfoViz.cs-TextFallback-refresh-window-sequences', 'dispatch:InfoViz.cs:TextFallback[refresh-window-sequences]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail', 'dispatch:MailClient.cs:ErrorDetail[]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-banned', 'dispatch:MailClient.cs:ErrorDetail[banned]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-body_control_character', 'dispatch:MailClient.cs:ErrorDetail[body_control_character]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-body_empty', 'dispatch:MailClient.cs:ErrorDetail[body_empty]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-body_repeated_characters', 'dispatch:MailClient.cs:ErrorDetail[body_repeated_characters]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-body_too_long', 'dispatch:MailClient.cs:ErrorDetail[body_too_long]', 'I18n.cs:TrF'),
    ('dispatch-MailClient.cs-ErrorDetail-cannot_block_self', 'dispatch:MailClient.cs:ErrorDetail[cannot_block_self]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-cannot_report_broadcast', 'dispatch:MailClient.cs:ErrorDetail[cannot_report_broadcast]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-censored', 'dispatch:MailClient.cs:ErrorDetail[censored]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-insecure-transport', 'dispatch:MailClient.cs:ErrorDetail[insecure-transport]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-mod_required', 'dispatch:MailClient.cs:ErrorDetail[mod_required]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-muted', 'dispatch:MailClient.cs:ErrorDetail[muted]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-no-consent', 'dispatch:MailClient.cs:ErrorDetail[no-consent]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-not-ready', 'dispatch:MailClient.cs:ErrorDetail[not ready]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-not_authorised', 'dispatch:MailClient.cs:ErrorDetail[not_authorised]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-not_found', 'dispatch:MailClient.cs:ErrorDetail[not_found]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-outdated', 'dispatch:MailClient.cs:ErrorDetail[outdated]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-rate_limited', 'dispatch:MailClient.cs:ErrorDetail[rate_limited]', 'MailClient.cs:RateLimitText'),
    ('dispatch-MailClient.cs-ErrorDetail-reason_control_character', 'dispatch:MailClient.cs:ErrorDetail[reason_control_character]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-reason_repeated_characters', 'dispatch:MailClient.cs:ErrorDetail[reason_repeated_characters]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-reason_too_long', 'dispatch:MailClient.cs:ErrorDetail[reason_too_long]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-recipient_invalid', 'dispatch:MailClient.cs:ErrorDetail[recipient_invalid]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-recipient_unknown', 'dispatch:MailClient.cs:ErrorDetail[recipient_unknown]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-recipients_empty', 'dispatch:MailClient.cs:ErrorDetail[recipients_empty]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-reply_all_refused', 'dispatch:MailClient.cs:ErrorDetail[reply_all_refused]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-session_required', 'dispatch:MailClient.cs:ErrorDetail[session_required]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-subject_control_character', 'dispatch:MailClient.cs:ErrorDetail[subject_control_character]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-subject_empty', 'dispatch:MailClient.cs:ErrorDetail[subject_empty]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-subject_newline', 'dispatch:MailClient.cs:ErrorDetail[subject_newline]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-subject_repeated_characters', 'dispatch:MailClient.cs:ErrorDetail[subject_repeated_characters]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-subject_too_long', 'dispatch:MailClient.cs:ErrorDetail[subject_too_long]', 'I18n.cs:TrF'),
    ('dispatch-MailClient.cs-ErrorDetail-too_many_blocks', 'dispatch:MailClient.cs:ErrorDetail[too_many_blocks]', 'I18n.cs:Tr'),
    ('dispatch-MailClient.cs-ErrorDetail-too_many_recipients', 'dispatch:MailClient.cs:ErrorDetail[too_many_recipients]', 'I18n.cs:Tr'),
    ('dispatch-MailUI.cs-PaintMailFrom-nobody', 'dispatch:MailUI.cs:PaintMailFrom[nobody]', 'I18n.cs:Tr'),
    ('dispatch-MailUI.cs-PaintMailFrom-played', 'dispatch:MailUI.cs:PaintMailFrom[played]', 'I18n.cs:Tr'),
    ('dispatch-MusicEngine.cs-TsBegin-album', 'dispatch:MusicEngine.cs:TsBegin[album]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-fail', 'dispatch:MusicEngine.cs:TsBegin[fail]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-loop', 'dispatch:MusicEngine.cs:TsBegin[loop]', 'MusicEngine.cs:LoopEnabled'),
    ('dispatch-MusicEngine.cs-TsBegin-play-pause', 'dispatch:MusicEngine.cs:TsBegin[play-pause]', 'MusicEngine.cs:PlayPause'),
    ('dispatch-MusicEngine.cs-TsBegin-play', 'dispatch:MusicEngine.cs:TsBegin[play]', 'MusicEngine.cs:PlayTrack'),
    ('dispatch-MusicEngine.cs-TsBegin-prev', 'dispatch:MusicEngine.cs:TsBegin[prev]', 'MusicEngine.cs:PlayPrevious'),
    ('dispatch-MusicEngine.cs-TsBegin-preview', 'dispatch:MusicEngine.cs:TsBegin[preview]', 'MusicEngine.cs:TogglePreview'),
    ('dispatch-MusicEngine.cs-TsBegin-reset', 'dispatch:MusicEngine.cs:TsBegin[reset]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-seek', 'dispatch:MusicEngine.cs:TsBegin[seek]', 'MusicEngine.cs:TsEnd'),
    ('dispatch-MusicEngine.cs-TsBegin-select', 'dispatch:MusicEngine.cs:TsBegin[select]', 'CombatEvidenceCore.cs:Add#1'),
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
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-arm', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[arm]', 'NativeUI.Settings.cs:SettingsSelectRec'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-mutations', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[mutations]', 'Keybinds.cs:RequestMutationBattery'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-reset', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[reset]', 'NativeUI.Keybinds.cs:KeybindResetRow'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-resetall', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[resetall]', 'Keybinds.cs:ResetAll'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindDirective-t3', 'dispatch:NativeUI.Keybinds.cs:KeybindDirective[t3]', 'Keybinds.cs:TranspilerMatcherBattery'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-AltGr', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[AltGr]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Alt', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Alt]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Backspace', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Backspace]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-CapsLock', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[CapsLock]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Clear', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Clear]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Command', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Command]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Control', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Control]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Delete', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Delete]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-DownArrow', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[DownArrow]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-End', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[End]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Escape', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Escape]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Home', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Home]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Insert', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Insert]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-LeftAlt', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[LeftAlt]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-LeftArrow', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[LeftArrow]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-LeftCommand', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[LeftCommand]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-LeftControl', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[LeftControl]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-LeftShift', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[LeftShift]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Numlock', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Numlock]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad0', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad0]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad1', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad1]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad2', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad2]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad3', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad3]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad4', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad4]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad5', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad5]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad6', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad6]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad7', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad7]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad8', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad8]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Pad9', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Pad9]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadDivide', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadDivide]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadEnter', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadEnter]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadEquals', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadEquals]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadMinus', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadMinus]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadMultiply', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadMultiply]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadPeriod', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadPeriod]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PadPlus', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PadPlus]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PageDown', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PageDown]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-PageUp', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[PageUp]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Return', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Return]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-RightAlt', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[RightAlt]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-RightArrow', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[RightArrow]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-RightCommand', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[RightCommand]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-RightControl', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[RightControl]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-RightShift', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[RightShift]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Shift', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Shift]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Space', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Space]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-Tab', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[Tab]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Keybinds.cs-KeybindKeyName-UpArrow', 'dispatch:NativeUI.Keybinds.cs:KeybindKeyName[UpArrow]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAllowSpec', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAllowSpec]', 'NativeUI.cs:PaintAllowSpectators'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAnimCos', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAnimCos]', 'NativeUI.cs:PaintAnimCos'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAppOff', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAppOff]', 'NativeUI.cs:PaintAppearOffline'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAutoLog', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAutoLog]', 'NativeUI.cs:PaintAutoLog'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAvAuto', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAvAuto]', 'NativeUI.cs:PaintAvatarAuto'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAvMod', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAvMod]', 'NativeUI.cs:PaintAvatarModded'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SAvVan', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SAvVan]', 'NativeUI.cs:PaintAvatarVanilla'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SBlkDbg', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SBlkDbg]', 'NativeUI.cs:PaintBlockDebug'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SBloom', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SBloom]', 'NativeUI.cs:PaintBloom'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SCT', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SCT]', 'NativeUI.cs:PaintConsent'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SChatTtl', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SChatTtl]', 'NativeUI.cs:PaintChatTtl'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SChromAb', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SChromAb]', 'NativeUI.cs:PaintChromAb'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SCursor', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SCursor]', 'NativeUI.cs:PaintCursorShape'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SDateFmt', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SDateFmt]', 'NativeUI.cs:PaintDateFormat'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SDeepIdle', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SDeepIdle]', 'NativeUI.cs:PaintDeepIdle'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SDmgNum', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SDmgNum]', 'NativeUI.cs:PaintDamageNumbers'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SFPSCap', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SFPSCap]', 'NativeUI.cs:PaintCapFps'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SFPS', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SFPS]', 'NativeUI.cs:PaintShowFps'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SHeavyFont', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SHeavyFont]', 'NativeUI.cs:PaintHeavyFont'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SHpPrec', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SHpPrec]', 'NativeUI.cs:PaintHealthPrecision'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SIgChat', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SIgChat]', 'NativeUI.cs:PaintIngameChat'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SInactiveLb', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SInactiveLb]', 'NativeUI.cs:PaintInactiveBoards'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SInpOv', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SInpOv]', 'NativeUI.cs:PaintInputOverlay'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SLagNotice', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SLagNotice]', 'NativeUI.cs:PaintLagNotices'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SLang', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SLang]', 'NativeUI.cs:PaintLanguage'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SLight', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SLight]', 'NativeUI.cs:PaintMapLighting'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SMailFrom', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SMailFrom]', 'MailUI.cs:PaintMailFrom'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SMailRelay', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SMailRelay]', 'MailUI.cs:PaintMailRelay'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SMenuMus', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SMenuMus]', 'NativeUI.cs:PaintMenuMusic'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SMusCredit', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SMusCredit]', 'NativeUI.cs:PaintMusicCredit'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SMuteBg', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SMuteBg]', 'NativeUI.cs:PaintMuteBg'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SNT', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SNT]', 'NativeUI.cs:PaintNotifications'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPColor', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPColor]', 'NativeUI.cs:PaintPlayerColors'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPcAnn', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPcAnn]', 'PlayerCardsUI.cs:PaintAnnounce'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPcDnc', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPcDnc]', 'PlayerCardsUI.cs:DanceOptionLabel'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPcPre', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPcPre]', 'PlayerCardsUI.cs:PaintPreset'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPcPub', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPcPub]', 'PlayerCardsUI.cs:PaintCollectionPublic'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPcTrd', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPcTrd]', 'PlayerCardsUI.cs:PaintTrades'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPing', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPing]', 'NativeUI.cs:PaintRegionPing'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SPrefSC', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SPrefSC]', 'NativeUI.cs:PaintPrefSameCards'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SShad', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SShad]', 'NativeUI.cs:PaintMapShadows'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SShake', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SShake]', 'NativeUI.cs:PaintScreenShake'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-SShowDc', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[SShowDc]', 'NativeUI.cs:PaintShowDiscord'),
    ('dispatch-NativeUI.Settings.cs-SettingsPaintValue-STrail', 'dispatch:NativeUI.Settings.cs:SettingsPaintValue[STrail]', 'NativeUI.cs:PaintTrails'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l11', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l11]', 'NativeUI.SettingsDrive.cs:DriveL11'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l2', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l2]', 'NativeUI.SettingsDrive.cs:DriveL2'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l3', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l3]', 'NativeUI.SettingsDrive.cs:DriveL3'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-l6', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[l6]', 'NativeUI.SettingsDrive.cs:DriveL6'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-m1', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[m1]', 'NativeUI.SettingsDrive.cs:DriveM1'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-ppwr', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[ppwr]', 'NativeUI.SettingsDrive.cs:DrivePpwr'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-r4', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[r4]', 'NativeUI.SettingsDrive.cs:DriveR4'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t4', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t4]', 'NativeUI.SettingsDrive.cs:DriveT4'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5a', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5a]', 'NativeUI.SettingsDrive.cs:DriveT5a'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5b]', 'NativeUI.SettingsDrive.cs:DriveT5b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5c', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5c]', 'NativeUI.SettingsDrive.cs:DriveT5c'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5d', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5d]', 'NativeUI.SettingsDrive.cs:DriveT5d'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5e', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5e]', 'NativeUI.SettingsDrive.cs:DriveT5e'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5f', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5f]', 'NativeUI.SettingsDrive.cs:DriveT5f'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5g', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5g]', 'NativeUI.SettingsDrive.cs:DriveT5g'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t5h', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t5h]', 'NativeUI.SettingsDrive.cs:DriveT5h'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t7', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t7]', 'NativeUI.SettingsDrive.cs:DriveT7'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-t7b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[t7b]', 'NativeUI.SettingsDrive.cs:DriveT7b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w10', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w10]', 'NativeUI.SettingsDrive.cs:DriveW10'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w1', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w1]', 'NativeUI.SettingsDrive.cs:DriveW1'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w2', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w2]', 'NativeUI.SettingsDrive.cs:DriveW2'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3]', 'NativeUI.SettingsDrive.cs:DriveW3'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3b]', 'NativeUI.SettingsDrive.cs:DriveW3b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w3c', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w3c]', 'NativeUI.SettingsDrive.cs:DriveW3c'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w4', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w4]', 'NativeUI.SettingsDrive.cs:DriveW4'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w5', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w5]', 'NativeUI.SettingsDrive.cs:DriveW5'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w6', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w6]', 'NativeUI.SettingsDrive.cs:DriveW6'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w9', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w9]', 'NativeUI.SettingsDrive.cs:DriveW9'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveScenario-w9b', 'dispatch:NativeUI.SettingsDrive.cs:DriveScenario[w9b]', 'NativeUI.SettingsDrive.cs:DriveW9b'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveT5g-chatmail', 'dispatch:NativeUI.SettingsDrive.cs:DriveT5g[chatmail]', 'NativeUI.SettingsDrive.cs:DrvShow'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveT5g-perf', 'dispatch:NativeUI.SettingsDrive.cs:DriveT5g[perf]', 'NativeUI.SettingsDrive.cs:DrvList'),
    ('dispatch-NativeUI.SettingsDrive.cs-DriveT5g-visuals', 'dispatch:NativeUI.SettingsDrive.cs:DriveT5g[visuals]', 'NativeUI.SettingsDrive.cs:DrvBloomState'),
    ('dispatch-NativeUI.SettingsDrive.cs-DrvCfgEntry-SDmgNum', 'dispatch:NativeUI.SettingsDrive.cs:DrvCfgEntry[SDmgNum]', 'IdentityClockCore.cs:Entry#1'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-2v2-Rating', 'dispatch:NativeUI.cs:BuildCompareBarChart[2v2 Rating]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-5-0s-Given-Taken', 'dispatch:NativeUI.cs:BuildCompareBarChart[5-0s Given / Taken]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Achievements', 'dispatch:NativeUI.cs:BuildCompareBarChart[Achievements]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Avg-Cards-Game', 'dispatch:NativeUI.cs:BuildCompareBarChart[Avg Cards / Game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Avg-FPS', 'dispatch:NativeUI.cs:BuildCompareBarChart[Avg FPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Avg-Game-Length', 'dispatch:NativeUI.cs:BuildCompareBarChart[Avg Game Length]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Bets-Won-Lost', 'dispatch:NativeUI.cs:BuildCompareBarChart[Bets Won / Lost]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-FFA-Avg-Kills', 'dispatch:NativeUI.cs:BuildCompareBarChart[FFA Avg Kills]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-FFA-Avg-Placement', 'dispatch:NativeUI.cs:BuildCompareBarChart[FFA Avg Placement]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-FFA-DPS', 'dispatch:NativeUI.cs:BuildCompareBarChart[FFA DPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Hit-Block', 'dispatch:NativeUI.cs:BuildCompareBarChart[Hit / Block %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Keys-Game', 'dispatch:NativeUI.cs:BuildCompareBarChart[Keys / Game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Keys-Sec', 'dispatch:NativeUI.cs:BuildCompareBarChart[Keys / Sec]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Peak-Elo', 'dispatch:NativeUI.cs:BuildCompareBarChart[Peak Elo]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Rage-Quit', 'dispatch:NativeUI.cs:BuildCompareBarChart[Rage Quit %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Ranked-DPS', 'dispatch:NativeUI.cs:BuildCompareBarChart[Ranked DPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Ranked-Uniqueness', 'dispatch:NativeUI.cs:BuildCompareBarChart[Ranked Uniqueness %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Self-Death', 'dispatch:NativeUI.cs:BuildCompareBarChart[Self-Death %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Top-Streaks', 'dispatch:NativeUI.cs:BuildCompareBarChart[Top Streaks]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareBarChart-Total-XP', 'dispatch:NativeUI.cs:BuildCompareBarChart[Total XP]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-BuildCompareMetricTable-Achievements', 'dispatch:NativeUI.cs:BuildCompareMetricTable[Achievements]', 'DamageNumberRules.cs:Count'),
    ('dispatch-NativeUI.cs-BuildCompareMetricTable-Region-Time', 'dispatch:NativeUI.cs:BuildCompareMetricTable[Region Time]', 'DamageNumberRules.cs:Count'),
    ('dispatch-NativeUI.cs-BuildCompareMetricTable-Top-Cards', 'dispatch:NativeUI.cs:BuildCompareMetricTable[Top Cards]', 'NativeUI.cs:AppendCardList'),
    ('dispatch-NativeUI.cs-BuildCompareMetricTable-Worst-Cards', 'dispatch:NativeUI.cs:BuildCompareMetricTable[Worst Cards]', 'NativeUI.cs:AppendCardList'),
    ('dispatch-NativeUI.cs-ChatChannelDisplayName-global', 'dispatch:NativeUI.cs:ChatChannelDisplayName[global]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-BulletCap', 'dispatch:NativeUI.cs:PerfRowLabel[BulletCap]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-EdgeBn', 'dispatch:NativeUI.cs:PerfRowLabel[EdgeBn]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-HitSnd', 'dispatch:NativeUI.cs:PerfRowLabel[HitSnd]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-Master', 'dispatch:NativeUI.cs:PerfRowLabel[Master]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-Menu', 'dispatch:NativeUI.cs:PerfRowLabel[Menu]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-OOB', 'dispatch:NativeUI.cs:PerfRowLabel[OOB]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-PoolInit', 'dispatch:NativeUI.cs:PerfRowLabel[PoolInit]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-PerfRowLabel-Stun', 'dispatch:NativeUI.cs:PerfRowLabel[Stun]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-avg_dps', 'dispatch:NativeUI.cs:RecordBoardHeading[avg_dps]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-longest_game', 'dispatch:NativeUI.cs:RecordBoardHeading[longest_game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-luckiest', 'dispatch:NativeUI.cs:RecordBoardHeading[luckiest]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-max_health', 'dispatch:NativeUI.cs:RecordBoardHeading[max_health]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-rarest_hand', 'dispatch:NativeUI.cs:RecordBoardHeading[rarest_hand]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-shortest_game', 'dispatch:NativeUI.cs:RecordBoardHeading[shortest_game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordBoardHeading-single_hit', 'dispatch:NativeUI.cs:RecordBoardHeading[single_hit]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RecordValueText-avg_dps', 'dispatch:NativeUI.cs:RecordValueText[avg_dps]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-RefreshCardStats-Common', 'dispatch:NativeUI.cs:RefreshCardStats[Common]', 'I18n.cs:TrC'),
    ('dispatch-NativeUI.cs-RefreshCardStats-Rare', 'dispatch:NativeUI.cs:RefreshCardStats[Rare]', 'I18n.cs:TrC'),
    ('dispatch-NativeUI.cs-RefreshCardStats-Uncommon', 'dispatch:NativeUI.cs:RefreshCardStats[Uncommon]', 'I18n.cs:TrC'),
    ('dispatch-NativeUI.cs-RefreshCardStats-Unknown', 'dispatch:NativeUI.cs:RefreshCardStats[Unknown]', 'I18n.cs:TrC'),
    ('dispatch-NativeUI.cs-RefreshTournaments-EU', 'dispatch:NativeUI.cs:RefreshTournaments[EU]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-RefreshTournaments-ISO', 'dispatch:NativeUI.cs:RefreshTournaments[ISO]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-RefreshTournaments-US', 'dispatch:NativeUI.cs:RefreshTournaments[US]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-RefreshTournaments-cancelled', 'dispatch:NativeUI.cs:RefreshTournaments[cancelled]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RefreshTournaments-completed', 'dispatch:NativeUI.cs:RefreshTournaments[completed]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RefreshTournaments-locked', 'dispatch:NativeUI.cs:RefreshTournaments[locked]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RefreshTournaments-running', 'dispatch:NativeUI.cs:RefreshTournaments[running]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-RefreshTournaments-voting', 'dispatch:NativeUI.cs:RefreshTournaments[voting]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-ShapeLabelTr-Arrow', 'dispatch:NativeUI.cs:ShapeLabelTr[Arrow]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-ShapeLabelTr-Circle', 'dispatch:NativeUI.cs:ShapeLabelTr[Circle]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-ShapeLabelTr-Crosshair', 'dispatch:NativeUI.cs:ShapeLabelTr[Crosshair]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-ShapeLabelTr-Dot', 'dispatch:NativeUI.cs:ShapeLabelTr[Dot]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-ShapeLabelTr-ROUNDS-default', 'dispatch:NativeUI.cs:ShapeLabelTr[ROUNDS default]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-color', 'dispatch:NativeUI.cs:TrKindWord[color]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-cursor_color', 'dispatch:NativeUI.cs:TrKindWord[cursor_color]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-face', 'dispatch:NativeUI.cs:TrKindWord[face]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-music_album', 'dispatch:NativeUI.cs:TrKindWord[music_album]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-nametag', 'dispatch:NativeUI.cs:TrKindWord[nametag]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-player_color', 'dispatch:NativeUI.cs:TrKindWord[player_color]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-player_effect', 'dispatch:NativeUI.cs:TrKindWord[player_effect]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-title', 'dispatch:NativeUI.cs:TrKindWord[title]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-trail', 'dispatch:NativeUI.cs:TrKindWord[trail]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrKindWord-utility', 'dispatch:NativeUI.cs:TrKindWord[utility]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-2v2-Rating', 'dispatch:NativeUI.cs:TrMetric[2v2 Rating]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-5-0-Sweeps', 'dispatch:NativeUI.cs:TrMetric[5-0 Sweeps]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-5-0s-Given-Taken', 'dispatch:NativeUI.cs:TrMetric[5-0s Given / Taken]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Achievement-Grid', 'dispatch:NativeUI.cs:TrMetric[Achievement Grid]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Achievements', 'dispatch:NativeUI.cs:TrMetric[Achievements]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Avg-Cards-Game', 'dispatch:NativeUI.cs:TrMetric[Avg Cards / Game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Avg-FPS', 'dispatch:NativeUI.cs:TrMetric[Avg FPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Avg-Game-Length', 'dispatch:NativeUI.cs:TrMetric[Avg Game Length]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Bets-Won-Lost', 'dispatch:NativeUI.cs:TrMetric[Bets Won / Lost]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Build-Types', 'dispatch:NativeUI.cs:TrMetric[Build Types]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Card-Win-Rate', 'dispatch:NativeUI.cs:TrMetric[Card Win Rate]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Elo', 'dispatch:NativeUI.cs:TrMetric[Elo]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-FFA-Avg-Kills', 'dispatch:NativeUI.cs:TrMetric[FFA Avg Kills]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-FFA-Avg-Placement', 'dispatch:NativeUI.cs:TrMetric[FFA Avg Placement]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-FFA-DPS', 'dispatch:NativeUI.cs:TrMetric[FFA DPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-FFA-Elo', 'dispatch:NativeUI.cs:TrMetric[FFA Elo]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Gold-Sources', 'dispatch:NativeUI.cs:TrMetric[Gold Sources]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Hit-Block', 'dispatch:NativeUI.cs:TrMetric[Hit / Block %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Keys-Game', 'dispatch:NativeUI.cs:TrMetric[Keys / Game]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Keys-Sec', 'dispatch:NativeUI.cs:TrMetric[Keys / Sec]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Most-Similar-Player', 'dispatch:NativeUI.cs:TrMetric[Most Similar Player]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Most-Stacked', 'dispatch:NativeUI.cs:TrMetric[Most Stacked]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Nemesis-Comparison', 'dispatch:NativeUI.cs:TrMetric[Nemesis Comparison]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Pass-Rate', 'dispatch:NativeUI.cs:TrMetric[Pass Rate]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Peak-Elo', 'dispatch:NativeUI.cs:TrMetric[Peak Elo]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Player-Nemesis', 'dispatch:NativeUI.cs:TrMetric[Player Nemesis]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Rage-Quit', 'dispatch:NativeUI.cs:TrMetric[Rage Quit %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Ranked-DPS', 'dispatch:NativeUI.cs:TrMetric[Ranked DPS]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Ranked-Friends', 'dispatch:NativeUI.cs:TrMetric[Ranked Friends]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Ranked-Picks', 'dispatch:NativeUI.cs:TrMetric[Ranked Picks]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Ranked-Uniqueness', 'dispatch:NativeUI.cs:TrMetric[Ranked Uniqueness %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Ranked-Win-Rate', 'dispatch:NativeUI.cs:TrMetric[Ranked Win Rate]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Records', 'dispatch:NativeUI.cs:TrMetric[Records]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Region-Time', 'dispatch:NativeUI.cs:TrMetric[Region Time]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Self-Death', 'dispatch:NativeUI.cs:TrMetric[Self-Death %]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Shop-Sales', 'dispatch:NativeUI.cs:TrMetric[Shop Sales]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Times-Offered', 'dispatch:NativeUI.cs:TrMetric[Times Offered]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Times-Picked', 'dispatch:NativeUI.cs:TrMetric[Times Picked]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Top-Cards', 'dispatch:NativeUI.cs:TrMetric[Top Cards]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Top-Pickers', 'dispatch:NativeUI.cs:TrMetric[Top Pickers]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Top-Streaks', 'dispatch:NativeUI.cs:TrMetric[Top Streaks]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Top-Winners', 'dispatch:NativeUI.cs:TrMetric[Top Winners]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Total-XP', 'dispatch:NativeUI.cs:TrMetric[Total XP]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Unique-Players', 'dispatch:NativeUI.cs:TrMetric[Unique Players]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrMetric-Worst-Cards', 'dispatch:NativeUI.cs:TrMetric[Worst Cards]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrRarity-common', 'dispatch:NativeUI.cs:TrRarity[common]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrRarity-epic', 'dispatch:NativeUI.cs:TrRarity[epic]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrRarity-legendary', 'dispatch:NativeUI.cs:TrRarity[legendary]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrRarity-rare', 'dispatch:NativeUI.cs:TrRarity[rare]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-TrRarity-uncommon', 'dispatch:NativeUI.cs:TrRarity[uncommon]', 'I18n.cs:Tr'),
    ('dispatch-NativeUI.cs-_FmtSlot-EU', 'dispatch:NativeUI.cs:_FmtSlot[EU]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-_FmtSlot-ISO', 'dispatch:NativeUI.cs:_FmtSlot[ISO]', 'KeybindRules.cs:ToString'),
    ('dispatch-NativeUI.cs-_FmtSlot-US', 'dispatch:NativeUI.cs:_FmtSlot[US]', 'KeybindRules.cs:ToString'),
    ('dispatch-PcLabels.cs-Tr-pc.band.common', 'dispatch:PcLabels.cs:Tr[pc.band.common]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band.epic', 'dispatch:PcLabels.cs:Tr[pc.band.epic]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band.legendary', 'dispatch:PcLabels.cs:Tr[pc.band.legendary]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band.rare', 'dispatch:PcLabels.cs:Tr[pc.band.rare]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band.uncommon', 'dispatch:PcLabels.cs:Tr[pc.band.uncommon]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band_short.common', 'dispatch:PcLabels.cs:Tr[pc.band_short.common]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band_short.epic', 'dispatch:PcLabels.cs:Tr[pc.band_short.epic]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band_short.legendary', 'dispatch:PcLabels.cs:Tr[pc.band_short.legendary]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band_short.rare', 'dispatch:PcLabels.cs:Tr[pc.band_short.rare]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.band_short.uncommon', 'dispatch:PcLabels.cs:Tr[pc.band_short.uncommon]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.edition', 'dispatch:PcLabels.cs:Tr[pc.edition]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.foil', 'dispatch:PcLabels.cs:Tr[pc.foil]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.foil_short', 'dispatch:PcLabels.cs:Tr[pc.foil_short]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.preview_footer', 'dispatch:PcLabels.cs:Tr[pc.preview_footer]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.signed', 'dispatch:PcLabels.cs:Tr[pc.signed]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.stat.board', 'dispatch:PcLabels.cs:Tr[pc.stat.board]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.stat.pool', 'dispatch:PcLabels.cs:Tr[pc.stat.pool]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.stat.rank', 'dispatch:PcLabels.cs:Tr[pc.stat.rank]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.stat.rating', 'dispatch:PcLabels.cs:Tr[pc.stat.rating]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.stat.record', 'dispatch:PcLabels.cs:Tr[pc.stat.record]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.unnamed', 'dispatch:PcLabels.cs:Tr[pc.unnamed]', 'I18n.cs:TrC'),
    ('dispatch-PcLabels.cs-Tr-pc.unranked', 'dispatch:PcLabels.cs:Tr[pc.unranked]', 'I18n.cs:TrC'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-card', 'dispatch:PlayerCardMotionDev.cs:DevRun[card]', 'PlayerCardsUI.cs:DevMotionAct'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-close', 'dispatch:PlayerCardMotionDev.cs:DevRun[close]', 'PlayerCardsUI.cs:DevMotionAct'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-off', 'dispatch:PlayerCardMotionDev.cs:DevRun[off]', 'PlayerCardMotion.cs:Clear'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-seed', 'dispatch:PlayerCardMotionDev.cs:DevRun[seed]', 'PlayerCardMotionDev.cs:DevSeed'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t39', 'dispatch:PlayerCardMotionDev.cs:DevRun[t39]', 'PlayerCardMotionDev.cs:DevT39'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t40', 'dispatch:PlayerCardMotionDev.cs:DevRun[t40]', 'PlayerCardMotionDev.cs:DevT40'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t41', 'dispatch:PlayerCardMotionDev.cs:DevRun[t41]', 'PlayerCardMotionDev.cs:DevT41'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t49', 'dispatch:PlayerCardMotionDev.cs:DevRun[t49]', 'PlayerCardMotionDev.cs:DevT49'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t50', 'dispatch:PlayerCardMotionDev.cs:DevRun[t50]', 'PlayerCardMotionDev.cs:DevT50'),
    ('dispatch-PlayerCardMotionDev.cs-DevRun-t51', 'dispatch:PlayerCardMotionDev.cs:DevRun[t51]', 'PlayerCardMotionDev.cs:DevT51'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-card', 'dispatch:PlayerCardsUI.cs:DevMotionAct[card]', 'PlayerCardsUI.cs:DevMotionCard'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-overlay-close', 'dispatch:PlayerCardsUI.cs:DevMotionAct[overlay-close]', 'CombatEvidenceCore.cs:Clear'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-seed', 'dispatch:PlayerCardsUI.cs:DevMotionAct[seed]', 'PlayerCardsUI.cs:DevSeedMotionPrints'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-sort', 'dispatch:PlayerCardsUI.cs:DevMotionAct[sort]', 'PlayerCardsUI.cs:CycleSort'),
    ('dispatch-PlayerCardsUI.cs-DevMotionAct-view', 'dispatch:PlayerCardsUI.cs:DevMotionAct[view]', 'IdentityClockCore.cs:Open#1'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-accept', 'dispatch:PlayerCardsUI.cs:DevTrade[accept]', 'DamageNumberRules.cs:Count'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-back', 'dispatch:PlayerCardsUI.cs:DevTrade[back]', 'PlayerCardsUI.cs:OnComposeBack'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-cancel', 'dispatch:PlayerCardsUI.cs:DevTrade[cancel]', 'DamageNumberRules.cs:Count'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-decline', 'dispatch:PlayerCardsUI.cs:DevTrade[decline]', 'DamageNumberRules.cs:Count'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-get', 'dispatch:PlayerCardsUI.cs:DevTrade[get]', 'PlayerCardsUI.cs:DevToggle'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-give', 'dispatch:PlayerCardsUI.cs:DevTrade[give]', 'PlayerCardsUI.cs:DevToggle'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-new', 'dispatch:PlayerCardsUI.cs:DevTrade[new]', 'PlayerCardsUI.cs:StartTradeSearch'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-offer', 'dispatch:PlayerCardsUI.cs:DevTrade[offer]', 'PlayerCardsUI.cs:StartCompose'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-pick', 'dispatch:PlayerCardsUI.cs:DevTrade[pick]', 'PlayerCardsUI.cs:StartCompose'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-poll', 'dispatch:PlayerCardsUI.cs:DevTrade[poll]', 'PlayerCardsUI.cs:ReadTrades'),
    ('dispatch-PlayerCardsUI.cs-DevTrade-send', 'dispatch:PlayerCardsUI.cs:DevTrade[send]', 'PlayerCardsUI.cs:SendProposal'),
    ('dispatch-PlayerCardsUI.cs-FailShard-key_reused', 'dispatch:PlayerCardsUI.cs:FailShard[key_reused]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-PlayerCardsUI.cs-FailShard-not_owned', 'dispatch:PlayerCardsUI.cs:FailShard[not_owned]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-PlayerCardsUI.cs-FailShard-shard_batch_unavailable', 'dispatch:PlayerCardsUI.cs:FailShard[shard_batch_unavailable]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-FailShard-too_many', 'dispatch:PlayerCardsUI.cs:FailShard[too_many]', 'I18n.cs:TrF'),
    ('dispatch-PlayerCardsUI.cs-HandleAnswer-http', 'dispatch:PlayerCardsUI.cs:HandleAnswer[http]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-HandleAnswer-in_progress', 'dispatch:PlayerCardsUI.cs:HandleAnswer[in_progress]', 'PlayerCardsUI.cs:ReasonText'),
    ('dispatch-PlayerCardsUI.cs-HandleAnswer-session_required', 'dispatch:PlayerCardsUI.cs:HandleAnswer[session_required]', 'PlayerCardsUI.cs:ReasonText'),
    ('dispatch-PlayerCardsUI.cs-HandleAnswer-transport', 'dispatch:PlayerCardsUI.cs:HandleAnswer[transport]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ModeLabel-1v1', 'dispatch:PlayerCardsUI.cs:ModeLabel[1v1]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ModeLabel-ffa', 'dispatch:PlayerCardsUI.cs:ModeLabel[ffa]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ModeLabel-ovt', 'dispatch:PlayerCardsUI.cs:ModeLabel[ovt]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ModeLabel-team', 'dispatch:PlayerCardsUI.cs:ModeLabel[team]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-PackLabel-daily', 'dispatch:PlayerCardsUI.cs:PackLabel[daily]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-PackLabel-earned', 'dispatch:PlayerCardsUI.cs:PackLabel[earned]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-PackSourceLabel-bought', 'dispatch:PlayerCardsUI.cs:PackSourceLabel[bought]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-PackSourceLabel-daily', 'dispatch:PlayerCardsUI.cs:PackSourceLabel[daily]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-PackSourceLabel-earned', 'dispatch:PlayerCardsUI.cs:PackSourceLabel[earned]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RarityLabel-epic', 'dispatch:PlayerCardsUI.cs:RarityLabel[epic]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RarityLabel-legendary', 'dispatch:PlayerCardsUI.cs:RarityLabel[legendary]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RarityLabel-rare', 'dispatch:PlayerCardsUI.cs:RarityLabel[rare]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RarityLabel-uncommon', 'dispatch:PlayerCardsUI.cs:RarityLabel[uncommon]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-already_claimed', 'dispatch:PlayerCardsUI.cs:ReasonText[already_claimed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-already_processed', 'dispatch:PlayerCardsUI.cs:ReasonText[already_processed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-bad_request', 'dispatch:PlayerCardsUI.cs:ReasonText[bad_request]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-bad_terms', 'dispatch:PlayerCardsUI.cs:ReasonText[bad_terms]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-bad_terms_local', 'dispatch:PlayerCardsUI.cs:ReasonText[bad_terms_local]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-busy', 'dispatch:PlayerCardsUI.cs:ReasonText[busy]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cancelled', 'dispatch:PlayerCardsUI.cs:ReasonText[cancelled]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cap_executed_day', 'dispatch:PlayerCardsUI.cs:ReasonText[cap_executed_day]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cap_executed_pair_day', 'dispatch:PlayerCardsUI.cs:ReasonText[cap_executed_pair_day]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cap_open_received', 'dispatch:PlayerCardsUI.cs:ReasonText[cap_open_received]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cap_open_sent', 'dispatch:PlayerCardsUI.cs:ReasonText[cap_open_sent]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cap_proposals_day', 'dispatch:PlayerCardsUI.cs:ReasonText[cap_proposals_day]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cooldown_declined', 'dispatch:PlayerCardsUI.cs:ReasonText[cooldown_declined]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-cooldown_reversal', 'dispatch:PlayerCardsUI.cs:ReasonText[cooldown_reversal]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-counterparty_closed', 'dispatch:PlayerCardsUI.cs:ReasonText[counterparty_closed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-counterparty_not_eligible', 'dispatch:PlayerCardsUI.cs:ReasonText[counterparty_not_eligible]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-counterparty_unavailable', 'dispatch:PlayerCardsUI.cs:ReasonText[counterparty_unavailable]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-daily_cap', 'dispatch:PlayerCardsUI.cs:ReasonText[daily_cap]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-declined', 'dispatch:PlayerCardsUI.cs:ReasonText[declined]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-expired', 'dispatch:PlayerCardsUI.cs:ReasonText[expired]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-in_progress', 'dispatch:PlayerCardsUI.cs:ReasonText[in_progress]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-insufficient_gold', 'dispatch:PlayerCardsUI.cs:ReasonText[insufficient_gold]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-insufficient_shards', 'dispatch:PlayerCardsUI.cs:ReasonText[insufficient_shards]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-no-consent', 'dispatch:PlayerCardsUI.cs:ReasonText[no-consent]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-no_edition', 'dispatch:PlayerCardsUI.cs:ReasonText[no_edition]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-not_eligible', 'dispatch:PlayerCardsUI.cs:ReasonText[not_eligible]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-not_found', 'dispatch:PlayerCardsUI.cs:ReasonText[not_found]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-not_owned', 'dispatch:PlayerCardsUI.cs:ReasonText[not_owned]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-outdated', 'dispatch:PlayerCardsUI.cs:ReasonText[outdated]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-pair_busy', 'dispatch:PlayerCardsUI.cs:ReasonText[pair_busy]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-pool_changed', 'dispatch:PlayerCardsUI.cs:ReasonText[pool_changed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-pool_empty', 'dispatch:PlayerCardsUI.cs:ReasonText[pool_empty]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-price_changed', 'dispatch:PlayerCardsUI.cs:ReasonText[price_changed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-print_gone', 'dispatch:PlayerCardsUI.cs:ReasonText[print_gone]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-print_offered_elsewhere', 'dispatch:PlayerCardsUI.cs:ReasonText[print_offered_elsewhere]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-private', 'dispatch:PlayerCardsUI.cs:ReasonText[private]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-rate_limit_waited', 'dispatch:PlayerCardsUI.cs:ReasonText[rate_limit_waited]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-rate_limited', 'dispatch:PlayerCardsUI.cs:ReasonText[rate_limited]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-recently_traded', 'dispatch:PlayerCardsUI.cs:ReasonText[recently_traded]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-reversed', 'dispatch:PlayerCardsUI.cs:ReasonText[reversed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-self_trade', 'dispatch:PlayerCardsUI.cs:ReasonText[self_trade]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-service_account_forbidden', 'dispatch:PlayerCardsUI.cs:ReasonText[service_account_forbidden]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-session_required', 'dispatch:PlayerCardsUI.cs:ReasonText[session_required]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-stale_revision', 'dispatch:PlayerCardsUI.cs:ReasonText[stale_revision]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-subject_unavailable', 'dispatch:PlayerCardsUI.cs:ReasonText[subject_unavailable]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-trading_closed', 'dispatch:PlayerCardsUI.cs:ReasonText[trading_closed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-trading_off', 'dispatch:PlayerCardsUI.cs:ReasonText[trading_off]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-trading_unavailable', 'dispatch:PlayerCardsUI.cs:ReasonText[trading_unavailable]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-transfer_conflict', 'dispatch:PlayerCardsUI.cs:ReasonText[transfer_conflict]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-transport', 'dispatch:PlayerCardsUI.cs:ReasonText[transport]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-void', 'dispatch:PlayerCardsUI.cs:ReasonText[void]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-voided', 'dispatch:PlayerCardsUI.cs:ReasonText[voided]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-ReasonText-wrong_party', 'dispatch:PlayerCardsUI.cs:ReasonText[wrong_party]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RecentLine-cancelled', 'dispatch:PlayerCardsUI.cs:RecentLine[cancelled]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RecentLine-declined', 'dispatch:PlayerCardsUI.cs:RecentLine[declined]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RecentLine-executed', 'dispatch:PlayerCardsUI.cs:RecentLine[executed]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RecentLine-expired', 'dispatch:PlayerCardsUI.cs:RecentLine[expired]', 'I18n.cs:Tr'),
    ('dispatch-PlayerCardsUI.cs-RecentLine-reversed', 'dispatch:PlayerCardsUI.cs:RecentLine[reversed]', 'PlayerCardsUI.cs:ReasonText'),
    ('dispatch-ProfileCard.cs-ModeName-casual_1v1', 'dispatch:ProfileCard.cs:ModeName[casual_1v1]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ModeName-ffa', 'dispatch:ProfileCard.cs:ModeName[ffa]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ModeName-ovt', 'dispatch:ProfileCard.cs:ModeName[ovt]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ModeName-ranked_1v1', 'dispatch:ProfileCard.cs:ModeName[ranked_1v1]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ModeName-team_2v2', 'dispatch:ProfileCard.cs:ModeName[team_2v2]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ResultName-L', 'dispatch:ProfileCard.cs:ResultName[L]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ResultName-T', 'dispatch:ProfileCard.cs:ResultName[T]', 'I18n.cs:Tr'),
    ('dispatch-ProfileCard.cs-ResultName-W', 'dispatch:ProfileCard.cs:ResultName[W]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportModel.cs-KindLabel-casual', 'dispatch:SessionReportModel.cs:KindLabel[casual]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportModel.cs-KindLabel-ffa', 'dispatch:SessionReportModel.cs:KindLabel[ffa]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportModel.cs-KindLabel-ovt', 'dispatch:SessionReportModel.cs:KindLabel[ovt]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportModel.cs-KindLabel-ranked', 'dispatch:SessionReportModel.cs:KindLabel[ranked]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportModel.cs-KindLabel-team', 'dispatch:SessionReportModel.cs:KindLabel[team]', 'I18n.cs:Tr'),
    ('dispatch-SessionReportRules.cs-ParseGame-available', 'dispatch:SessionReportRules.cs:ParseGame[available]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-deaths', 'dispatch:SessionReportRules.cs:ParseGame[deaths]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-end_build', 'dispatch:SessionReportRules.cs:ParseGame[end_build]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-end_stats', 'dispatch:SessionReportRules.cs:ParseGame[end_stats]', 'SessionReportRules.cs:Members#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-gold', 'dispatch:SessionReportRules.cs:ParseGame[gold]', 'SessionReportRules.cs:Ints'),
    ('dispatch-SessionReportRules.cs-ParseGame-match_id', 'dispatch:SessionReportRules.cs:ParseGame[match_id]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-ParseGame-picks', 'dispatch:SessionReportRules.cs:ParseGame[picks]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-points', 'dispatch:SessionReportRules.cs:ParseGame[points]', 'SessionReportRules.cs:Members#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-scores', 'dispatch:SessionReportRules.cs:ParseGame[scores]', 'SessionReportRules.cs:Members#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-settings', 'dispatch:SessionReportRules.cs:ParseGame[settings]', 'PortraitRenderDance.cs:Max'),
    ('dispatch-SessionReportRules.cs-ParseGame-started_at', 'dispatch:SessionReportRules.cs:ParseGame[started_at]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-ParseGame-timelines', 'dispatch:SessionReportRules.cs:ParseGame[timelines]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-totals', 'dispatch:SessionReportRules.cs:ParseGame[totals]', 'SessionReportRules.cs:Members#1'),
    ('dispatch-SessionReportRules.cs-ParseGame-xp', 'dispatch:SessionReportRules.cs:ParseGame[xp]', 'SessionReportRules.cs:Ints'),
    ('dispatch-SessionReportRules.cs-ParsePlayer-color', 'dispatch:SessionReportRules.cs:ParsePlayer[color]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-ParsePlayer-id', 'dispatch:SessionReportRules.cs:ParsePlayer[id]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-ParsePlayer-name', 'dispatch:SessionReportRules.cs:ParsePlayer[name]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-Parse-games', 'dispatch:SessionReportRules.cs:Parse[games]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-Parse-games_omitted', 'dispatch:SessionReportRules.cs:Parse[games_omitted]', 'PortraitRenderDance.cs:Max'),
    ('dispatch-SessionReportRules.cs-Parse-kind', 'dispatch:SessionReportRules.cs:Parse[kind]', 'SessionReportRules.cs:Str'),
    ('dispatch-SessionReportRules.cs-Parse-players', 'dispatch:SessionReportRules.cs:Parse[players]', 'CombatEvidenceCore.cs:Add#1'),
    ('dispatch-SessionReportRules.cs-Parse-set_summary', 'dispatch:SessionReportRules.cs:Parse[set_summary]', 'SessionReportRules.cs:ParseSummary'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SAnimCos', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SAnimCos]', 'PlayerEffectCosmetic.cs:SetAnimatedCosmetics'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SBloom', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SBloom]', 'Plugin.cs:Set#3'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SChromAb', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SChromAb]', 'SeatEvidenceCore.cs:Set#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SCursor', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SCursor]', 'CursorColorCosmetic.cs:SetShape'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SDmgNum', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SDmgNum]', 'SeatEvidenceCore.cs:Set#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SHeavyFont', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SHeavyFont]', 'NativeUI.cs:SetUiHeavyFont'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SHpPrec', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SHpPrec]', 'SeatEvidenceCore.cs:Set#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SIgChat', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SIgChat]', 'CompetitiveUI.cs:SetChatOverlayMode'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SLight', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SLight]', 'Plugin.cs:SetLighting'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SMenuMus', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SMenuMus]', 'NativeUI.cs:SetMenuMusicMode'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SPColor', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SPColor]', 'PlayerColorCosmetic.cs:SetShowPlayerColors'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SShad', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SShad]', 'Plugin.cs:SetShadows'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-SShake', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[SShake]', 'SeatEvidenceCore.cs:Set#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-InvokeReset-STrail', 'dispatch:SettingsDescriptorWriters.g.cs:InvokeReset[STrail]', 'TrailRenderer.cs:SetShowTrails'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SAvMod', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SAvMod]', 'AvatarDefaults.cs:PresetLabel'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SAvVan', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SAvVan]', 'AvatarDefaults.cs:PresetLabel'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SBloom', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SBloom]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SChatTtl', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SChatTtl]', 'Plugin.cs:ChatOverlaySecondsLabel#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SCursor', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SCursor]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SPcDnc', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SPcDnc]', 'PlayerCardsUI.cs:DanceOptionLabel'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SPcPre', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SPcPre]', 'PlayerCardsUI.cs:PresetLabel#1'),
    ('dispatch-SettingsDescriptorWriters.g.cs-RenderExpression-SShake', 'dispatch:SettingsDescriptorWriters.g.cs:RenderExpression[SShake]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SAllowSpec', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SAllowSpec]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SAutoLog', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SAutoLog]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SAvAuto', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SAvAuto]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SCT', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SCT]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SDBtn', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SDBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SDateFmt', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SDateFmt]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SEBtn', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SEBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SLang', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SLang]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ExclusionReasonTr-SMailBlocked', 'dispatch:SettingsDescriptors.g.cs:ExclusionReasonTr[SMailBlocked]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SAvAuto', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SAvAuto]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SAvMod', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SAvMod]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SAvVan', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SAvVan]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SDBtn', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SDBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SDXBtn', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SDXBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SEBtn', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SEBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SInfoOpen', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SInfoOpen]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SMailBlocked', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SMailBlocked]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SMailFrom', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SMailFrom]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SMailRelay', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SMailRelay]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-HelpBodyTr-SPerfH', 'dispatch:SettingsDescriptors.g.cs:HelpBodyTr[SPerfH]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAllowSpec', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAllowSpec]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAnimCos', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAnimCos]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAppOff', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAppOff]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAutoLog', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAutoLog]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAvAuto', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAvAuto]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAvMod', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAvMod]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SAvVan', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SAvVan]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SBlkDbg', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SBlkDbg]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SBloom', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SBloom]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SCT', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SCT]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SChatTtl', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SChatTtl]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SChromAb', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SChromAb]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SCursor', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SCursor]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDBtn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDCBtn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDCBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDXBtn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDXBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDateFmt', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDateFmt]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDeepIdle', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDeepIdle]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SDmgNum', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SDmgNum]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SEBtn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SEBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SFPSCap', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SFPSCap]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SFPS', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SFPS]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SHeavyFont', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SHeavyFont]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SHpPrec', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SHpPrec]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SIgChat', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SIgChat]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SInactiveLb', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SInactiveLb]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SInfoOpen', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SInfoOpen]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SInpOv', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SInpOv]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SLagNotice', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SLagNotice]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SLang', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SLang]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SLight', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SLight]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMailBlocked', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMailBlocked]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMailFrom', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMailFrom]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMailRelay', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMailRelay]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMenuMus', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMenuMus]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMusCredit', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMusCredit]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SMuteBg', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SMuteBg]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SNT', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SNT]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPColor', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPColor]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPcAnn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPcAnn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPcDnc', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPcDnc]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPcPre', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPcPre]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPcPub', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPcPub]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPcTrd', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPcTrd]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerfH', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerfH]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_BulletCap', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_BulletCap]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_EdgeBn', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_EdgeBn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_HitSnd', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_HitSnd]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_Master', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_Master]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_Menu', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_Menu]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_OOB', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_OOB]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_PoolInit', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_PoolInit]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPerf_Stun', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPerf_Stun]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPing', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPing]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPortal', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPortal]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SPrefSC', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SPrefSC]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SShad', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SShad]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SShake', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SShake]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-SShowDc', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[SShowDc]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-ReasonTr-STrail', 'dispatch:SettingsDescriptors.g.cs:ReasonTr[STrail]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-chatmail', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[chatmail]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-ingame', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[ingame]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-langmenus', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[langmenus]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-perf', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[perf]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-privacy', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[privacy]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-sound', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[sound]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-SubTabLabelTr-visuals', 'dispatch:SettingsDescriptors.g.cs:SubTabLabelTr[visuals]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SDBtn', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SDBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SDCBtn', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SDCBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SDXBtn', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SDXBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SEBtn', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SEBtn]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SInfoOpen', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SInfoOpen]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SMailBlocked', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SMailBlocked]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SPerfH', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SPerfH]', 'I18n.cs:Tr'),
    ('dispatch-SettingsDescriptors.g.cs-WhenToPressTr-SPortal', 'dispatch:SettingsDescriptors.g.cs:WhenToPressTr[SPortal]', 'I18n.cs:Tr'),
    ('dispatch-SettingsModel.cs-ActivationAccepts-DESTRUCTIVE', 'dispatch:SettingsModel.cs:ActivationAccepts[DESTRUCTIVE]', 'DamageNumberRules.cs:Enter'),
    ('dispatch-TitleLaddersUI.cs-UnitCount-games', 'dispatch:TitleLaddersUI.cs:UnitCount[games]', 'I18n.cs:TrF'),
    ('dispatch-TitleLaddersUI.cs-UnitCount-gold', 'dispatch:TitleLaddersUI.cs:UnitCount[gold]', 'I18n.cs:TrF'),
    ('dispatch-TitleLaddersUI.cs-UnitCount-losses', 'dispatch:TitleLaddersUI.cs:UnitCount[losses]', 'I18n.cs:TrF'),
    ('dispatch-TitleLaddersUI.cs-UnitCount-streak', 'dispatch:TitleLaddersUI.cs:UnitCount[streak]', 'I18n.cs:TrF'),
    ('dispatch-TitleLaddersUI.cs-UnitCount-wins', 'dispatch:TitleLaddersUI.cs:UnitCount[wins]', 'I18n.cs:TrF'),
    ('field-ApiClient.cs', 'field:ApiClient.cs:?', 'ApiClient.cs:FetchChatMutes'),
    ('field-ApiClient.cs-body', 'field:ApiClient.cs:body', 'KeybindRules.cs:ToString'),
    ('field-AutoLogUpload.cs', 'field:AutoLogUpload.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-BinderSortRules.cs', 'field:BinderSortRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-BroadcastHud.cs', 'field:BroadcastHud.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-BroadcastMode.cs', 'field:BroadcastMode.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-BroadcastMode.cs-InstanceId', 'field:BroadcastMode.cs:InstanceId', 'KeybindRules.cs:ToString'),
    ('field-CardDrawEvidence.cs', 'field:CardDrawEvidence.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-CardDrawEvidence.cs-_sw', 'field:CardDrawEvidence.cs:_sw', 'FfaNumberingRules.cs:StartNew'),
    ('field-CardDrawEvidenceCore.cs', 'field:CardDrawEvidenceCore.cs:?', 'CombatEvidenceCore.cs:Add#1'),
    ('field-ChatClient.cs', 'field:ChatClient.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-CombatEvidenceCore.cs', 'field:CombatEvidenceCore.cs:?', 'CombatEvidenceCore.cs:Count'),
    ('field-CombatEvidenceCore.cs-LIST_IX', 'field:CombatEvidenceCore.cs:LIST_IX', 'CombatEvidenceCore.cs:ListIndices'),
    ('field-CombatEvidenceCore.cs-Width', 'field:CombatEvidenceCore.cs:Width', 'CombatEvidenceCore.cs:LoOf'),
    ('field-DamageNumberRules.cs', 'field:DamageNumberRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-DanceMotionCore.cs', 'field:DanceMotionCore.cs:?', 'FfaLateRules.cs:Answer'),
    ('field-DanceStep0Probe.cs', 'field:DanceStep0Probe.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-EmojiSprites.cs', 'field:EmojiSprites.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-EscMenuLeaveGuard.cs-Handler', 'field:EscMenuLeaveGuard.cs:Handler', 'EscMenuLeaveGuard.cs:OnGatedClick'),
    ('field-FfaAssembly.cs', 'field:FfaAssembly.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-FfaLateEntry.cs', 'field:FfaLateEntry.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-FfaLateRules.cs', 'field:FfaLateRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-FfaLateRules.cs-AckComplete', 'field:FfaLateRules.cs:AckComplete', 'FfaLateRules.cs:AckComplete'),
    ('field-FfaLateRules.cs-BarrierEpoch', 'field:FfaLateRules.cs:BarrierEpoch', 'FfaLateRules.cs:BarrierEpoch'),
    ('field-FfaLateRules.cs-BoundaryDigest', 'field:FfaLateRules.cs:BoundaryDigest', 'FfaLateRules.cs:BoundaryDigest'),
    ('field-FfaLateRules.cs-DigestGate', 'field:FfaLateRules.cs:DigestGate', 'FfaLateRules.cs:DigestGate'),
    ('field-FfaLateRules.cs-ElectReporter', 'field:FfaLateRules.cs:ElectReporter', 'FfaLateRules.cs:ElectReporter'),
    ('field-FfaLateRules.cs-FenceStep', 'field:FfaLateRules.cs:FenceStep', 'FfaLateRules.cs:FenceStep'),
    ('field-FfaLateRules.cs-FenceTarget', 'field:FfaLateRules.cs:FenceTarget', 'FfaLateRules.cs:FenceTarget'),
    ('field-FfaLateRules.cs-KeptActorTest', 'field:FfaLateRules.cs:KeptActorTest', 'FfaLateRules.cs:KeptActorValue'),
    ('field-FfaLateRules.cs-KeptSender', 'field:FfaLateRules.cs:KeptSender', 'FfaLateRules.cs:KeptSender'),
    ('field-FfaLateRules.cs-MasterKeptTest', 'field:FfaLateRules.cs:MasterKeptTest', 'FfaLateRules.cs:MasterKeptValue'),
    ('field-FfaLateRules.cs-PairDecision', 'field:FfaLateRules.cs:PairDecision', 'FfaLateRules.cs:PairDecision'),
    ('field-FfaLateRules.cs-ReadyEpoch', 'field:FfaLateRules.cs:ReadyEpoch', 'FfaLateRules.cs:ReadyEpoch'),
    ('field-FfaLateRules.cs-RecordDecision', 'field:FfaLateRules.cs:RecordDecision', 'FfaLateRules.cs:RecordDecision'),
    ('field-FfaLateRules.cs-ScaleDecision', 'field:FfaLateRules.cs:ScaleDecision', 'FfaLateRules.cs:ScaleDecision'),
    ('field-FfaLateRules.cs-ValidateEpoch', 'field:FfaLateRules.cs:ValidateEpoch', 'FfaLateRules.cs:ValidateEpoch'),
    ('field-FfaLateRules.cs-ValidateStamp', 'field:FfaLateRules.cs:ValidateStamp', 'FfaLateRules.cs:ValidateStamp'),
    ('field-FfaNumberingRules.cs', 'field:FfaNumberingRules.cs:?', 'FfaNumberingRules.cs:Exp'),
    ('field-FfaReadmitEntryRules.cs', 'field:FfaReadmitEntryRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-FfaReportRules.cs', 'field:FfaReportRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-FfaReportRules.cs-ServerGameSuffix', 'field:FfaReportRules.cs:ServerGameSuffix', 'DamageNumberRules.cs:Text#1'),
    ('field-FpsFocusCore.cs', 'field:FpsFocusCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-GameStateWatcher.cs', 'field:GameStateWatcher.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-GameStateWatcher.cs-_tickStopwatch', 'field:GameStateWatcher.cs:_tickStopwatch', 'FfaNumberingRules.cs:StartNew'),
    ('field-Gate0TriggerWiringProbe.cs', 'field:Gate0TriggerWiringProbe.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-Gate0WiringFormat.cs', 'field:Gate0WiringFormat.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-H2HSummary.cs', 'field:H2HSummary.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-HitEvidenceCore.cs', 'field:HitEvidenceCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-I18n.cs', 'field:I18n.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-IdentityClockCore.cs', 'field:IdentityClockCore.cs:?', 'CombatEvidenceCore.cs:Add#1'),
    ('field-IdentityClockEvidence.cs-_sw', 'field:IdentityClockEvidence.cs:_sw', 'FfaNumberingRules.cs:StartNew'),
    ('field-IdleShowcase.cs-script', 'field:IdleShowcase.cs:script', 'ShowcaseRules.cs:Script'),
    ('field-InboundStallCore.cs', 'field:InboundStallCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-KeybindRules.cs', 'field:KeybindRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-Keybinds.cs-HookDown', 'field:Keybinds.cs:HookDown', 'Keybinds.cs:VanillaDown'),
    ('field-Keybinds.cs-HookHeld', 'field:Keybinds.cs:HookHeld', 'Keybinds.cs:VanillaHeld'),
    ('field-Keybinds.cs-MenuToggle', 'field:Keybinds.cs:MenuToggle', 'SeatEvidenceCore.cs:Block'),
    ('field-LagNotices.cs', 'field:LagNotices.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-LetterboxClear.cs', 'field:LetterboxClear.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-LogBundleCore.cs', 'field:LogBundleCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-LogScrub.cs', 'field:LogScrub.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-LogScrub.cs-SepAny', 'field:LogScrub.cs:SepAny', 'LogScrub.cs:BuildSepAny'),
    ('field-MailClient.cs', 'field:MailClient.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-MailUI.cs', 'field:MailUI.cs:?', 'CombatEvidenceCore.cs:Summary'),
    ('field-MailUI.cs-inboxItems', 'field:MailUI.cs:inboxItems', 'CombatEvidenceCore.cs:Summary'),
    ('field-MailUI.cs-sentItems', 'field:MailUI.cs:sentItems', 'CombatEvidenceCore.cs:Summary'),
    ('field-MusicAssets.cs', 'field:MusicAssets.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-MusicAssets.cs-Manifest', 'field:MusicAssets.cs:Manifest', 'MusicAssets.cs:BuildManifest'),
    ('field-MusicEngine.cs', 'field:MusicEngine.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-MusicLevels.cs', 'field:MusicLevels.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NameGlyphs.cs', 'field:NameGlyphs.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NametagFontRenderer.cs', 'field:NametagFontRenderer.cs:?', 'NametagFontRenderer.cs:PollLoop'),
    ('field-NametagGlowRenderer.cs', 'field:NametagGlowRenderer.cs:?', 'NametagGlowRenderer.cs:PollLoop'),
    ('field-NametagStyler.cs', 'field:NametagStyler.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NativeUI.Keybinds.cs', 'field:NativeUI.Keybinds.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NativeUI.Settings.cs', 'field:NativeUI.Settings.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NativeUI.cs', 'field:NativeUI.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NativeUI.cs-_tInfoTitle', 'field:NativeUI.cs:_tInfoTitle', 'NativeUI.cs:_SYNC_INSTRUCTIONS'),
    ('field-NetJitterBudgetCore.cs', 'field:NetJitterBudgetCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NetworkReplicaDiagnostics.cs', 'field:NetworkReplicaDiagnostics.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NetworkSeatTelemetry.cs', 'field:NetworkSeatTelemetry.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-NetworkSeatTelemetry.cs-_stallStreams', 'field:NetworkSeatTelemetry.cs:_stallStreams', 'NetworkReplicaDiagnostics.cs:SnapshotRemoteStreams'),
    ('field-PcQuickShardRules.cs', 'field:PcQuickShardRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PcTradeRules.cs', 'field:PcTradeRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PeerBuildCore.cs', 'field:PeerBuildCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PlayerCardsUI.cs', 'field:PlayerCardsUI.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PlayerCardsUI.cs-MotionViews', 'field:PlayerCardsUI.cs:MotionViews', 'PlayerCardsUI.cs:MotionViewNames'),
    ('field-PlayerCardsUI.cs-ShardUuid', 'field:PlayerCardsUI.cs:ShardUuid', 'DamageNumberRules.cs:Text#1'),
    ('field-PlayerCardsUI.cs-binderSort', 'field:PlayerCardsUI.cs:binderSort', 'IdentityClockCore.cs:Name'),
    ('field-PlayerCardsUI.cs-view', 'field:PlayerCardsUI.cs:view', 'IdentityClockCore.cs:Open#1'),
    ('field-PortraitGrade.cs', 'field:PortraitGrade.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PortraitRender.cs', 'field:PortraitRender.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PortraitRenderDance.cs', 'field:PortraitRenderDance.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PortraitRenderDanceDev.cs', 'field:PortraitRenderDanceDev.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PostSessionReport.cs', 'field:PostSessionReport.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-PostSessionReport.cs-_allTagStrip', 'field:PostSessionReport.cs:_allTagStrip', 'DamageNumberRules.cs:Text#1'),
    ('field-PostSessionReport.cs-_tagStrip', 'field:PostSessionReport.cs:_tagStrip', 'DamageNumberRules.cs:Text#1'),
    ('field-ProfileCard.cs', 'field:ProfileCard.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-RegionPingSweep.cs', 'field:RegionPingSweep.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-RegionPingSweep.cs-SessionNonce', 'field:RegionPingSweep.cs:SessionNonce', 'KeybindRules.cs:ToString'),
    ('field-RoomActors.cs', 'field:RoomActors.cs:?', 'FfaLateEntry.cs:KeptPlayers'),
    ('field-RoomRulesStrip.cs', 'field:RoomRulesStrip.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-RosterCensus.cs', 'field:RosterCensus.cs:?', 'CombatEvidenceCore.cs:Add#1'),
    ('field-RosterCensusRules.cs', 'field:RosterCensusRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SeatDeckLog.cs', 'field:SeatDeckLog.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SeatEvidence.cs', 'field:SeatEvidence.cs:?', 'CardDrawEvidenceCore.cs:Record#1'),
    ('field-SeatEvidence.cs-_cad', 'field:SeatEvidence.cs:_cad', 'IdentityClockCore.cs:Cadence'),
    ('field-SeatEvidence.cs-_sw', 'field:SeatEvidence.cs:_sw', 'FfaNumberingRules.cs:StartNew'),
    ('field-SeatEvidenceCore.cs', 'field:SeatEvidenceCore.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SecureRouteRules.cs', 'field:SecureRouteRules.cs:?', 'PortraitRenderDance.cs:Free'),
    ('field-SessionReportModel.cs', 'field:SessionReportModel.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SessionReportRules.cs', 'field:SessionReportRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SettingsModel.cs', 'field:SettingsModel.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-ShowcaseRules.cs', 'field:ShowcaseRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SpectatorHud.cs', 'field:SpectatorHud.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-SpectatorHud.cs-_allTagStrip', 'field:SpectatorHud.cs:_allTagStrip', 'DamageNumberRules.cs:Text#1'),
    ('field-SpectatorHud.cs-_tagStrip', 'field:SpectatorHud.cs:_tagStrip', 'DamageNumberRules.cs:Text#1'),
    ('field-SpectatorTeardownProbe.cs', 'field:SpectatorTeardownProbe.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-TabStatsOverlay.cs', 'field:TabStatsOverlay.cs:?', 'PortraitRenderDance.cs:Max'),
    ('field-TeamGameNumber.cs-Account', 'field:TeamGameNumber.cs:Account', 'TeamGameNumber.cs:NewHarnessName'),
    ('field-TeamHoldNet.cs', 'field:TeamHoldNet.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-TeamHoldPick.cs-Audit', 'field:TeamHoldPick.cs:Audit', 'TeamHoldPick.cs:AuditNow'),
    ('field-TeamHoldPick.cs-RecordEntry0', 'field:TeamHoldPick.cs:RecordEntry0', 'TeamHoldPick.cs:RecordEntry0Now'),
    ('field-TeamHoldReturn.cs-AdmissionLatched', 'field:TeamHoldReturn.cs:AdmissionLatched', 'TeamHoldReturn.cs:AdmissionNow'),
    ('field-TeamHoldRules.cs', 'field:TeamHoldRules.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-TopStripBand.cs', 'field:TopStripBand.cs:?', 'DamageNumberRules.cs:Text#1'),
    ('field-TrailRenderer.cs', 'field:TrailRenderer.cs:?', 'TrailRenderer.cs:EnsureSprite'),
    ('harmony-AvatarDefaults.cs-AvatarCreatePlayerPatch.Prefix-PlayerAssigner.CreatePlayer', 'harmony:AvatarDefaults.cs:AvatarCreatePlayerPatch.Prefix(PlayerAssigner.CreatePlayer)', 'AvatarDefaults.cs:Prefix'),
    ('harmony-AvatarDefaults.cs-AvatarLoadFacesPatch.Postfix-1-CharacterCreatorHandler.LoadFaces', 'harmony:AvatarDefaults.cs:AvatarLoadFacesPatch.Postfix#1(CharacterCreatorHandler.LoadFaces)', 'AvatarDefaults.cs:Postfix#1'),
    ('harmony-AvatarDefaults.cs-AvatarSelectFacePatch.Postfix-2-CharacterCreatorHandler.SelectFace', 'harmony:AvatarDefaults.cs:AvatarSelectFacePatch.Postfix#2(CharacterCreatorHandler.SelectFace)', 'AvatarDefaults.cs:Postfix#2'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_CardAwakePatch.Postfix-2-CardInfo.Awake', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_CardAwakePatch.Postfix#2(CardInfo.Awake)', 'CardDrawEvidence.cs:Postfix#2'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_DonePickingPatch.Prefix-2-CardChoice.RPCA_DonePicking', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_DonePickingPatch.Prefix#2(CardChoice.RPCA_DonePicking)', 'CardDrawEvidence.cs:Prefix#2'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_EndPickPatch.Prefix-1-CardChoice.RPCA_DoEndPick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_EndPickPatch.Prefix#1(CardChoice.RPCA_DoEndPick)', 'CardDrawEvidence.cs:Prefix#1'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_OfflinePickPatch.Finalizer-2-ApplyCardStats.OFFLINE_Pick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_OfflinePickPatch.Finalizer#2(ApplyCardStats.OFFLINE_Pick)', 'CardDrawEvidence.cs:Finalizer#2'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_OfflinePickPatch.Postfix-4-ApplyCardStats.OFFLINE_Pick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_OfflinePickPatch.Postfix#4(ApplyCardStats.OFFLINE_Pick)', 'CardDrawEvidence.cs:Postfix#4'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_PickPatch.Finalizer-1-ApplyCardStats.RPCA_Pick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_PickPatch.Finalizer#1(ApplyCardStats.RPCA_Pick)', 'CardDrawEvidence.cs:Finalizer#1'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_PickPatch.Postfix-3-ApplyCardStats.RPCA_Pick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_PickPatch.Postfix#3(ApplyCardStats.RPCA_Pick)', 'CardDrawEvidence.cs:Postfix#3'),
    ('harmony-CardDrawEvidence.cs-CardDrawEvidence_StartPickPatch.Postfix-1-CardChoice.StartPick', 'harmony:CardDrawEvidence.cs:CardDrawEvidence_StartPickPatch.Postfix#1(CardChoice.StartPick)', 'CardDrawEvidence.cs:Postfix#1'),
    ('harmony-CardDrawEvidenceTestDealer.cs-CardDrawEvidenceTestDealer_SpawnPatch.Prefix-CardChoice.SpawnUniqueCard', 'harmony:CardDrawEvidenceTestDealer.cs:CardDrawEvidenceTestDealer_SpawnPatch.Prefix(CardChoice.SpawnUniqueCard)', 'CardDrawEvidenceTestDealer.cs:Prefix'),
    ('harmony-CombatEvidence.cs-CombatEvidence_AttackPatch.Postfix-1-Gun.Attack', 'harmony:CombatEvidence.cs:CombatEvidence_AttackPatch.Postfix#1(Gun.Attack)', 'CombatEvidence.cs:Postfix#1'),
    ('harmony-CombatEvidence.cs-CombatEvidence_AttackPatch.Prefix-1-Gun.Attack', 'harmony:CombatEvidence.cs:CombatEvidence_AttackPatch.Prefix#1(Gun.Attack)', 'CombatEvidence.cs:Prefix#1'),
    ('harmony-CombatEvidence.cs-CombatEvidence_BlockPatch.Finalizer-3-Block.RPCA_DoBlock', 'harmony:CombatEvidence.cs:CombatEvidence_BlockPatch.Finalizer#3(Block.RPCA_DoBlock)', 'CombatEvidence.cs:Finalizer#3'),
    ('harmony-CombatEvidence.cs-CombatEvidence_ContactPatch.Prefix-7-ProjectileHit.Hit', 'harmony:CombatEvidence.cs:CombatEvidence_ContactPatch.Prefix#7(ProjectileHit.Hit)', 'CombatEvidence.cs:Prefix#7'),
    ('harmony-CombatEvidence.cs-CombatEvidence_DamagePatch.Finalizer-6-HealthHandler.RPCA_SendTakeDamage', 'harmony:CombatEvidence.cs:CombatEvidence_DamagePatch.Finalizer#6(HealthHandler.RPCA_SendTakeDamage)', 'CombatEvidence.cs:Finalizer#6'),
    ('harmony-CombatEvidence.cs-CombatEvidence_DamagePatch.Prefix-12-HealthHandler.RPCA_SendTakeDamage', 'harmony:CombatEvidence.cs:CombatEvidence_DamagePatch.Prefix#12(HealthHandler.RPCA_SendTakeDamage)', 'CombatEvidence.cs:Prefix#12'),
    ('harmony-CombatEvidence.cs-CombatEvidence_DealtPatch.Postfix-3-CharacterStatModifiers.DealtDamage', 'harmony:CombatEvidence.cs:CombatEvidence_DealtPatch.Postfix#3(CharacterStatModifiers.DealtDamage)', 'CombatEvidence.cs:Postfix#3'),
    ('harmony-CombatEvidence.cs-CombatEvidence_DiePatch.Prefix-13-HealthHandler.RPCA_Die', 'harmony:CombatEvidence.cs:CombatEvidence_DiePatch.Prefix#13(HealthHandler.RPCA_Die)', 'CombatEvidence.cs:Prefix#13'),
    ('harmony-CombatEvidence.cs-CombatEvidence_DiePhoenixPatch.Prefix-14-HealthHandler.RPCA_Die_Phoenix', 'harmony:CombatEvidence.cs:CombatEvidence_DiePhoenixPatch.Prefix#14(HealthHandler.RPCA_Die_Phoenix)', 'CombatEvidence.cs:Prefix#14'),
    ('harmony-CombatEvidence.cs-CombatEvidence_EdgeBouncePatch.Finalizer-4-ScreenEdgeBounce.DoHit', 'harmony:CombatEvidence.cs:CombatEvidence_EdgeBouncePatch.Finalizer#4(ScreenEdgeBounce.DoHit)', 'CombatEvidence.cs:Finalizer#4'),
    ('harmony-CombatEvidence.cs-CombatEvidence_EdgeBouncePatch.Prefix-10-ScreenEdgeBounce.DoHit', 'harmony:CombatEvidence.cs:CombatEvidence_EdgeBouncePatch.Prefix#10(ScreenEdgeBounce.DoHit)', 'CombatEvidence.cs:Prefix#10'),
    ('harmony-CombatEvidence.cs-CombatEvidence_FindTargetPatch.Postfix-5-BounceEffectRetarget.FindTarget', 'harmony:CombatEvidence.cs:CombatEvidence_FindTargetPatch.Postfix#5(BounceEffectRetarget.FindTarget)', 'CombatEvidence.cs:Postfix#5'),
    ('harmony-CombatEvidence.cs-CombatEvidence_ForcePatch.Finalizer-5-HealthHandler.RPCA_SendTakeForce', 'harmony:CombatEvidence.cs:CombatEvidence_ForcePatch.Finalizer#5(HealthHandler.RPCA_SendTakeForce)', 'CombatEvidence.cs:Finalizer#5'),
    ('harmony-CombatEvidence.cs-CombatEvidence_ForcePatch.Prefix-11-HealthHandler.RPCA_SendTakeForce', 'harmony:CombatEvidence.cs:CombatEvidence_ForcePatch.Prefix#11(HealthHandler.RPCA_SendTakeForce)', 'CombatEvidence.cs:Prefix#11'),
    ('harmony-CombatEvidence.cs-CombatEvidence_HitPatch.Finalizer-2-ProjectileHit.RPCA_DoHit', 'harmony:CombatEvidence.cs:CombatEvidence_HitPatch.Finalizer#2(ProjectileHit.RPCA_DoHit)', 'CombatEvidence.cs:Finalizer#2'),
    ('harmony-CombatEvidence.cs-CombatEvidence_HitPatch.Prefix-6-ProjectileHit.RPCA_DoHit', 'harmony:CombatEvidence.cs:CombatEvidence_HitPatch.Prefix#6(ProjectileHit.RPCA_DoHit)', 'CombatEvidence.cs:Prefix#6'),
    ('harmony-CombatEvidence.cs-CombatEvidence_InitAmmoPatch.Finalizer-1-ProjectileInit.RPCA_Init', 'harmony:CombatEvidence.cs:CombatEvidence_InitAmmoPatch.Finalizer#1(ProjectileInit.RPCA_Init)', 'CombatEvidence.cs:Finalizer#1'),
    ('harmony-CombatEvidence.cs-CombatEvidence_InitAmmoPatch.Prefix-2-ProjectileInit.RPCA_Init', 'harmony:CombatEvidence.cs:CombatEvidence_InitAmmoPatch.Prefix#2(ProjectileInit.RPCA_Init)', 'CombatEvidence.cs:Prefix#2'),
    ('harmony-CombatEvidence.cs-CombatEvidence_InitNoAmmoPatch.Prefix-3-ProjectileInit.RPCA_Init_noAmmoUse', 'harmony:CombatEvidence.cs:CombatEvidence_InitNoAmmoPatch.Prefix#3(ProjectileInit.RPCA_Init_noAmmoUse)', 'CombatEvidence.cs:Prefix#3'),
    ('harmony-CombatEvidence.cs-CombatEvidence_InitSeparatePatch.Prefix-4-ProjectileInit.RPCA_Init_SeparateGun', 'harmony:CombatEvidence.cs:CombatEvidence_InitSeparatePatch.Prefix#4(ProjectileInit.RPCA_Init_SeparateGun)', 'CombatEvidence.cs:Prefix#4'),
    ('harmony-CombatEvidence.cs-CombatEvidence_MovePatch.Finalizer-7-MoveTransform.Update', 'harmony:CombatEvidence.cs:CombatEvidence_MovePatch.Finalizer#7(MoveTransform.Update)', 'CombatEvidence.cs:Finalizer#7'),
    ('harmony-CombatEvidence.cs-CombatEvidence_MovePatch.Prefix-15-MoveTransform.Update', 'harmony:CombatEvidence.cs:CombatEvidence_MovePatch.Prefix#15(MoveTransform.Update)', 'CombatEvidence.cs:Prefix#15'),
    ('harmony-CombatEvidence.cs-CombatEvidence_ReloadPatch.Prefix-5-GunAmmo.ReloadAmmo', 'harmony:CombatEvidence.cs:CombatEvidence_ReloadPatch.Prefix#5(GunAmmo.ReloadAmmo)', 'CombatEvidence.cs:Prefix#5'),
    ('harmony-CombatEvidence.cs-CombatEvidence_SyncPatch.Postfix-4-SyncProjectile.OnPhotonSerializeView', 'harmony:CombatEvidence.cs:CombatEvidence_SyncPatch.Postfix#4(SyncProjectile.OnPhotonSerializeView)', 'CombatEvidence.cs:Postfix#4'),
    ('harmony-CombatEvidence.cs-CombatEvidence_TargetBouncePatch.Prefix-9-BounceEffectRetarget.SetNewVel', 'harmony:CombatEvidence.cs:CombatEvidence_TargetBouncePatch.Prefix#9(BounceEffectRetarget.SetNewVel)', 'CombatEvidence.cs:Prefix#9'),
    ('harmony-CombatEvidence.cs-CombatEvidence_TryBlockPatch.Postfix-2-Block.TryBlock', 'harmony:CombatEvidence.cs:CombatEvidence_TryBlockPatch.Postfix#2(Block.TryBlock)', 'CombatEvidence.cs:Postfix#2'),
    ('harmony-CombatEvidence.cs-CombatEvidence_TryBlockPatch.Prefix-8-Block.TryBlock', 'harmony:CombatEvidence.cs:CombatEvidence_TryBlockPatch.Prefix#8(Block.TryBlock)', 'CombatEvidence.cs:Prefix#8'),
    ('harmony-CombatTelemetry.cs-DamageDealtLocalTrackerPatch.AfterDealtDamage-1-CharacterStatModifiers.DealtDamage', 'harmony:CombatTelemetry.cs:DamageDealtLocalTrackerPatch.AfterDealtDamage#1(CharacterStatModifiers.DealtDamage)', 'CombatTelemetry.cs:AfterDealtDamage#1'),
    ('harmony-CombatTelemetry.cs-DamageStampPatch.Prefix-1-HealthHandler.DoDamage', 'harmony:CombatTelemetry.cs:DamageStampPatch.Prefix#1(HealthHandler.DoDamage)', 'CombatTelemetry.cs:Prefix#1'),
    ('harmony-CombatTelemetry.cs-DeathClassifierPatch.Prefix-2-HealthHandler.RPCA_Die', 'harmony:CombatTelemetry.cs:DeathClassifierPatch.Prefix#2(HealthHandler.RPCA_Die)', 'CombatTelemetry.cs:Prefix#2'),
    ('harmony-CombatTelemetry.cs-LocalTookDamageTrackerPatch.AfterDealtDamage-2-CharacterStatModifiers.DealtDamage', 'harmony:CombatTelemetry.cs:LocalTookDamageTrackerPatch.AfterDealtDamage#2(CharacterStatModifiers.DealtDamage)', 'CombatTelemetry.cs:AfterDealtDamage#2'),
    ('harmony-CustomCosmetics.cs-CosmeticButtonSpawnerPatch.Postfix-1-CharacterCreatorButtonSpawner.OpenMenu', 'harmony:CustomCosmetics.cs:CosmeticButtonSpawnerPatch.Postfix#1(CharacterCreatorButtonSpawner.OpenMenu)', 'CustomCosmetics.cs:Postfix#1'),
    ('harmony-CustomCosmetics.cs-CosmeticSelectButtonPatch.Postfix-2-CharacterCreatorButtonSpawner.SelectButton', 'harmony:CustomCosmetics.cs:CosmeticSelectButtonPatch.Postfix#2(CharacterCreatorButtonSpawner.SelectButton)', 'CustomCosmetics.cs:Postfix#2'),
    ('harmony-DamageNumbers.cs-DoDamageHooks.DoDamagePostfix-HealthHandler.DoDamage', 'harmony:DamageNumbers.cs:DoDamageHooks.DoDamagePostfix(HealthHandler.DoDamage)', 'DamageNumbers.cs:DoDamagePostfix'),
    ('harmony-DamageNumbers.cs-DoDamageHooks.DoDamagePrefix-HealthHandler.DoDamage', 'harmony:DamageNumbers.cs:DoDamageHooks.DoDamagePrefix(HealthHandler.DoDamage)', 'DamageNumbers.cs:DoDamagePrefix'),
    ('harmony-DamageNumbers.cs-HealHooks.HealPostfix-HealthHandler.Heal', 'harmony:DamageNumbers.cs:HealHooks.HealPostfix(HealthHandler.Heal)', 'DamageNumbers.cs:HealPostfix'),
    ('harmony-DamageNumbers.cs-HealHooks.HealPrefix-HealthHandler.Heal', 'harmony:DamageNumbers.cs:HealHooks.HealPrefix(HealthHandler.Heal)', 'DamageNumbers.cs:HealPrefix'),
    ('harmony-DanceEmotes.cs-Arm_DancePatch.Postfix-2-IKArmMove.Update', 'harmony:DanceEmotes.cs:Arm_DancePatch.Postfix#2(IKArmMove.Update)', 'DanceEmotes.cs:Postfix#2'),
    ('harmony-DanceEmotes.cs-Arm_DancePatch.Prefix-2-IKArmMove.Update', 'harmony:DanceEmotes.cs:Arm_DancePatch.Prefix#2(IKArmMove.Update)', 'DanceEmotes.cs:Prefix#2'),
    ('harmony-DanceEmotes.cs-Dance_BlockTryBlock_Patch.Prefix-4-Block.TryBlock', 'harmony:DanceEmotes.cs:Dance_BlockTryBlock_Patch.Prefix#4(Block.TryBlock)', 'DanceEmotes.cs:Prefix#4'),
    ('harmony-DanceEmotes.cs-Dance_GeneralInput_Patch.Postfix-3-GeneralInput.Update', 'harmony:DanceEmotes.cs:Dance_GeneralInput_Patch.Postfix#3(GeneralInput.Update)', 'DanceEmotes.cs:Postfix#3'),
    ('harmony-DanceEmotes.cs-Dance_GunAttack_Patch.Prefix-3-Gun.Attack', 'harmony:DanceEmotes.cs:Dance_GunAttack_Patch.Prefix#3(Gun.Attack)', 'DanceEmotes.cs:Prefix#3'),
    ('harmony-DanceEmotes.cs-Wobble_DancePatch.Postfix-1-PlayerWobblePosition.Update', 'harmony:DanceEmotes.cs:Wobble_DancePatch.Postfix#1(PlayerWobblePosition.Update)', 'DanceEmotes.cs:Postfix#1'),
    ('harmony-DanceEmotes.cs-Wobble_DancePatch.Prefix-1-PlayerWobblePosition.Update', 'harmony:DanceEmotes.cs:Wobble_DancePatch.Prefix#1(PlayerWobblePosition.Update)', 'DanceEmotes.cs:Prefix#1'),
    ('harmony-FfaAssembly.cs-FfaAssembly_LoadGate_Patch.Prefix-MapManager.RPCA_LoadLevel', 'harmony:FfaAssembly.cs:FfaAssembly_LoadGate_Patch.Prefix(MapManager.RPCA_LoadLevel)', 'FfaAssembly.cs:Prefix'),
    ('harmony-FfaLateEntry.cs-FfaLate_CallInHold_Patch.Prefix-6-MapManager.RPCA_CallInNewMapAndMovePlayers', 'harmony:FfaLateEntry.cs:FfaLate_CallInHold_Patch.Prefix#6(MapManager.RPCA_CallInNewMapAndMovePlayers)', 'FfaLateEntry.cs:Prefix#6'),
    ('harmony-FfaLateEntry.cs-FfaLate_ForceQuarantine_Patch.Prefix-2-HealthHandler.RPCA_SendTakeForce', 'harmony:FfaLateEntry.cs:FfaLate_ForceQuarantine_Patch.Prefix#2(HealthHandler.RPCA_SendTakeForce)', 'FfaLateEntry.cs:Prefix#2'),
    ('harmony-FfaLateEntry.cs-FfaLate_NoMapReport_Patch.Prefix-4-MapManager.ReportMapLoaded', 'harmony:FfaLateEntry.cs:FfaLate_NoMapReport_Patch.Prefix#4(MapManager.ReportMapLoaded)', 'FfaLateEntry.cs:Prefix#4'),
    ('harmony-FfaLateEntry.cs-FfaLate_NoSyncReply_Patch.Prefix-3-GM_ArmsRace.RPCO_RequestSyncUp', 'harmony:FfaLateEntry.cs:FfaLate_NoSyncReply_Patch.Prefix#3(GM_ArmsRace.RPCO_RequestSyncUp)', 'FfaLateEntry.cs:Prefix#3'),
    ('harmony-FfaLateEntry.cs-FfaLate_PickQuarantine_Patch.Prefix-1-ApplyCardStats.RPCA_Pick', 'harmony:FfaLateEntry.cs:FfaLate_PickQuarantine_Patch.Prefix#1(ApplyCardStats.RPCA_Pick)', 'FfaLateEntry.cs:Prefix#1'),
    ('harmony-FfaLateEntry.cs-FfaLate_Register_Patch.Postfix-3-PlayerManager.RegisterPlayer', 'harmony:FfaLateEntry.cs:FfaLate_Register_Patch.Postfix#3(PlayerManager.RegisterPlayer)', 'FfaLateEntry.cs:Postfix#3'),
    ('harmony-FfaLateEntry.cs-FfaLate_Simulated_Patch.Postfix-2-PlayerManager.SetPlayersSimulated', 'harmony:FfaLateEntry.cs:FfaLate_Simulated_Patch.Postfix#2(PlayerManager.SetPlayersSimulated)', 'FfaLateEntry.cs:Postfix#2'),
    ('harmony-FfaLateEntry.cs-FfaLate_Visible_Patch.Postfix-1-PlayerManager.SetPlayersVisible', 'harmony:FfaLateEntry.cs:FfaLate_Visible_Patch.Postfix#1(PlayerManager.SetPlayersVisible)', 'FfaLateEntry.cs:Postfix#1'),
    ('harmony-FfaLateEntry.cs-FfaReadmit_RegisterOrder_Patch.Prefix-5-PlayerManager.RegisterPlayer', 'harmony:FfaLateEntry.cs:FfaReadmit_RegisterOrder_Patch.Prefix#5(PlayerManager.RegisterPlayer)', 'FfaLateEntry.cs:Prefix#5'),
    ('harmony-FfaMapScale.cs-MapTransition_SetStartPos_FfaScale_Patch.Postfix-1-MapTransition.SetStartPos', 'harmony:FfaMapScale.cs:MapTransition_SetStartPos_FfaScale_Patch.Postfix#1(MapTransition.SetStartPos)', 'FfaMapScale.cs:Postfix#1'),
    ('harmony-FfaMapScale.cs-OutOfBoundsHandler_FfaScale_Patch.Prefix-2-OutOfBoundsHandler.LateUpdate', 'harmony:FfaMapScale.cs:OutOfBoundsHandler_FfaScale_Patch.Prefix#2(OutOfBoundsHandler.LateUpdate)', 'FfaMapScale.cs:Prefix#2'),
    ('harmony-FfaMapScale.cs-PhotonMapObject_Start_FfaScale_Patch.Postfix-2-PhotonMapObject.Start', 'harmony:FfaMapScale.cs:PhotonMapObject_Start_FfaScale_Patch.Postfix#2(PhotonMapObject.Start)', 'FfaMapScale.cs:Postfix#2'),
    ('harmony-FfaMapScale.cs-PlayerManager_MovePlayers_FfaScale_Patch.Prefix-1-PlayerManager.MovePlayers', 'harmony:FfaMapScale.cs:PlayerManager_MovePlayers_FfaScale_Patch.Prefix#1(PlayerManager.MovePlayers)', 'FfaMapScale.cs:Prefix#1'),
    ('harmony-FfaMode.cs-Block_FfaSpawnGrace_Patch.Prefix-11-Block.TryBlock', 'harmony:FfaMode.cs:Block_FfaSpawnGrace_Patch.Prefix#11(Block.TryBlock)', 'FfaMode.cs:Prefix#11'),
    ('harmony-FfaMode.cs-CardBarHandler_AddCard_Ffa_Patch.Prefix-5-CardBarHandler.AddCard', 'harmony:FfaMode.cs:CardBarHandler_AddCard_Ffa_Patch.Prefix#5(CardBarHandler.AddCard)', 'FfaMode.cs:Prefix#5'),
    ('harmony-FfaMode.cs-GMArmsRace_DoStartGame_Ffa_Patch.Prefix-4-GM_ArmsRace.DoStartGame', 'harmony:FfaMode.cs:GMArmsRace_DoStartGame_Ffa_Patch.Prefix#4(GM_ArmsRace.DoStartGame)', 'FfaMode.cs:Prefix#4'),
    ('harmony-FfaMode.cs-GMArmsRace_NextRound_Ffa_Patch.Prefix-3-GM_ArmsRace.RPCA_NextRound', 'harmony:FfaMode.cs:GMArmsRace_NextRound_Ffa_Patch.Prefix#3(GM_ArmsRace.RPCA_NextRound)', 'FfaMode.cs:Prefix#3'),
    ('harmony-FfaMode.cs-GMArmsRace_PlayerDied_Ffa_Patch.Prefix-1-GM_ArmsRace.PlayerDied', 'harmony:FfaMode.cs:GMArmsRace_PlayerDied_Ffa_Patch.Prefix#1(GM_ArmsRace.PlayerDied)', 'FfaMode.cs:Prefix#1'),
    ('harmony-FfaMode.cs-GeneralInput_FfaSpawnGrace_Patch.Postfix-2-GeneralInput.Update', 'harmony:FfaMode.cs:GeneralInput_FfaSpawnGrace_Patch.Postfix#2(GeneralInput.Update)', 'FfaMode.cs:Postfix#2'),
    ('harmony-FfaMode.cs-LineRangeEffect_FfaOwnerExclusion_Patch.Prefix-9-LineRangeEffect.Update', 'harmony:FfaMode.cs:LineRangeEffect_FfaOwnerExclusion_Patch.Prefix#9(LineRangeEffect.Update)', 'FfaMode.cs:Prefix#9'),
    ('harmony-FfaMode.cs-MapManager_GetSpawnPoints_FfaShuffle_Patch.Postfix-1-MapManager.GetSpawnPoints', 'harmony:FfaMode.cs:MapManager_GetSpawnPoints_FfaShuffle_Patch.Postfix#1(MapManager.GetSpawnPoints)', 'FfaMode.cs:Postfix#1'),
    ('harmony-FfaMode.cs-NCH_OnPlayerLeftRoom_Ffa_Patch.Prefix-6-NetworkConnectionHandler.OnPlayerLeftRoom', 'harmony:FfaMode.cs:NCH_OnPlayerLeftRoom_Ffa_Patch.Prefix#6(NetworkConnectionHandler.OnPlayerLeftRoom)', 'FfaMode.cs:Prefix#6'),
    ('harmony-FfaMode.cs-PlayerManager_GetClosestPlayerInTeam_Ffa_Patch.Prefix-8-PlayerManager.GetClosestPlayerInTeam', 'harmony:FfaMode.cs:PlayerManager_GetClosestPlayerInTeam_Ffa_Patch.Prefix#8(PlayerManager.GetClosestPlayerInTeam)', 'FfaMode.cs:Prefix#8'),
    ('harmony-FfaMode.cs-PlayerManager_GetOtherPlayer_Ffa_Patch.Prefix-7-PlayerManager.GetOtherPlayer', 'harmony:FfaMode.cs:PlayerManager_GetOtherPlayer_Ffa_Patch.Prefix#7(PlayerManager.GetOtherPlayer)', 'FfaMode.cs:Prefix#7'),
    ('harmony-FfaMode.cs-PlayerManager_PlayerDied_Ffa_Patch.Prefix-2-PlayerManager.PlayerDied', 'harmony:FfaMode.cs:PlayerManager_PlayerDied_Ffa_Patch.Prefix#2(PlayerManager.PlayerDied)', 'FfaMode.cs:Prefix#2'),
    ('harmony-FfaMode.cs-WeaponHandler_FfaSpawnGrace_Patch.Prefix-10-WeaponHandler.Attack', 'harmony:FfaMode.cs:WeaponHandler_FfaSpawnGrace_Patch.Prefix#10(WeaponHandler.Attack)', 'FfaMode.cs:Prefix#10'),
    ('harmony-GameLocaleInjector.cs-GameLocaleOptionsInitPatch.Finalizer-OptionsData.InitializeLocalization', 'harmony:GameLocaleInjector.cs:GameLocaleOptionsInitPatch.Finalizer(OptionsData.InitializeLocalization)', 'GameLocaleInjector.cs:Finalizer'),
    ('harmony-GameLocaleInjector.cs-GameLocaleOptionsInitPatch.Postfix-OptionsData.InitializeLocalization', 'harmony:GameLocaleInjector.cs:GameLocaleOptionsInitPatch.Postfix(OptionsData.InitializeLocalization)', 'GameLocaleInjector.cs:Postfix'),
    ('harmony-Gate0TriggerWiringProbe.cs-Gate0TriggerWiringProbe.AfterStart', 'harmony:Gate0TriggerWiringProbe.cs:Gate0TriggerWiringProbe.AfterStart(?)', 'Gate0TriggerWiringProbe.cs:AfterStart'),
    ('harmony-HealBarOverlay.cs-HealthHandler_HealOverlayReviveReset_Patch.Postfix-2-HealthHandler.Revive', 'harmony:HealBarOverlay.cs:HealthHandler_HealOverlayReviveReset_Patch.Postfix#2(HealthHandler.Revive)', 'HealBarOverlay.cs:Postfix#2'),
    ('harmony-HitEvidence.cs-HitEvidence_BlockPatch.Finalizer-5-Block.RPCA_DoBlock', 'harmony:HitEvidence.cs:HitEvidence_BlockPatch.Finalizer#5(Block.RPCA_DoBlock)', 'HitEvidence.cs:Finalizer#5'),
    ('harmony-HitEvidence.cs-HitEvidence_BlockPatch.Prefix-3-Block.RPCA_DoBlock', 'harmony:HitEvidence.cs:HitEvidence_BlockPatch.Prefix#3(Block.RPCA_DoBlock)', 'HitEvidence.cs:Prefix#3'),
    ('harmony-HitEvidence.cs-HitEvidence_DamagePatch.Finalizer-2-HealthHandler.RPCA_SendTakeDamage', 'harmony:HitEvidence.cs:HitEvidence_DamagePatch.Finalizer#2(HealthHandler.RPCA_SendTakeDamage)', 'HitEvidence.cs:Finalizer#2'),
    ('harmony-HitEvidence.cs-HitEvidence_DotPatch.Finalizer-4-HealthHandler.DoDamage', 'harmony:HitEvidence.cs:HitEvidence_DotPatch.Finalizer#4(HealthHandler.DoDamage)', 'HitEvidence.cs:Finalizer#4'),
    ('harmony-HitEvidence.cs-HitEvidence_ExecuteRpcPatch.Prefix-1', 'harmony:HitEvidence.cs:HitEvidence_ExecuteRpcPatch.Prefix#1(?)', 'HitEvidence.cs:Prefix#1'),
    ('harmony-HitEvidence.cs-HitEvidence_FfaDoStartGamePatch.Finalizer-11-GM_ArmsRace.DoStartGame', 'harmony:HitEvidence.cs:HitEvidence_FfaDoStartGamePatch.Finalizer#11(GM_ArmsRace.DoStartGame)', 'HitEvidence.cs:Finalizer#11'),
    ('harmony-HitEvidence.cs-HitEvidence_ForcePatch.Finalizer-3-HealthHandler.RPCA_SendTakeForce', 'harmony:HitEvidence.cs:HitEvidence_ForcePatch.Finalizer#3(HealthHandler.RPCA_SendTakeForce)', 'HitEvidence.cs:Finalizer#3'),
    ('harmony-HitEvidence.cs-HitEvidence_ImpactPatch.Finalizer-9-ProjectileHit.RPCA_DoHit', 'harmony:HitEvidence.cs:HitEvidence_ImpactPatch.Finalizer#9(ProjectileHit.RPCA_DoHit)', 'HitEvidence.cs:Finalizer#9'),
    ('harmony-HitEvidence.cs-HitEvidence_ImpactPatch.Prefix-4-ProjectileHit.RPCA_DoHit', 'harmony:HitEvidence.cs:HitEvidence_ImpactPatch.Prefix#4(ProjectileHit.RPCA_DoHit)', 'HitEvidence.cs:Prefix#4'),
    ('harmony-HitEvidence.cs-HitEvidence_SpawnAmmoPatch.Finalizer-6-ProjectileInit.RPCA_Init', 'harmony:HitEvidence.cs:HitEvidence_SpawnAmmoPatch.Finalizer#6(ProjectileInit.RPCA_Init)', 'HitEvidence.cs:Finalizer#6'),
    ('harmony-HitEvidence.cs-HitEvidence_SpawnNoAmmoPatch.Finalizer-7-ProjectileInit.RPCA_Init_noAmmoUse', 'harmony:HitEvidence.cs:HitEvidence_SpawnNoAmmoPatch.Finalizer#7(ProjectileInit.RPCA_Init_noAmmoUse)', 'HitEvidence.cs:Finalizer#7'),
    ('harmony-HitEvidence.cs-HitEvidence_SpawnSeparatePatch.Finalizer-8-ProjectileInit.RPCA_Init_SeparateGun', 'harmony:HitEvidence.cs:HitEvidence_SpawnSeparatePatch.Finalizer#8(ProjectileInit.RPCA_Init_SeparateGun)', 'HitEvidence.cs:Finalizer#8'),
    ('harmony-HitEvidence.cs-HitEvidence_StartGamePatch.Finalizer-10-GM_ArmsRace.StartGame', 'harmony:HitEvidence.cs:HitEvidence_StartGamePatch.Finalizer#10(GM_ArmsRace.StartGame)', 'HitEvidence.cs:Finalizer#10'),
    ('harmony-IdentityClockEvidence.cs-IdentityClock_ExecuteRpcPatch.Prefix-1', 'harmony:IdentityClockEvidence.cs:IdentityClock_ExecuteRpcPatch.Prefix#1(?)', 'IdentityClockEvidence.cs:Prefix#1'),
    ('harmony-IdentityClockEvidence.cs-IdentityClock_MovePlayersPatch.Prefix-3-PlayerManager.MovePlayers', 'harmony:IdentityClockEvidence.cs:IdentityClock_MovePlayersPatch.Prefix#3(PlayerManager.MovePlayers)', 'IdentityClockEvidence.cs:Prefix#3'),
    ('harmony-IdentityClockEvidence.cs-IdentityClock_MovementPatch.Postfix-SyncPlayerMovement.OnPhotonSerializeView', 'harmony:IdentityClockEvidence.cs:IdentityClock_MovementPatch.Postfix(SyncPlayerMovement.OnPhotonSerializeView)', 'IdentityClockEvidence.cs:Postfix'),
    ('harmony-IdentityClockEvidence.cs-IdentityClock_MovementPatch.Prefix-4-SyncPlayerMovement.OnPhotonSerializeView', 'harmony:IdentityClockEvidence.cs:IdentityClock_MovementPatch.Prefix#4(SyncPlayerMovement.OnPhotonSerializeView)', 'IdentityClockEvidence.cs:Prefix#4'),
    ('harmony-IdentityClockEvidence.cs-IdentityClock_PointStartPatch.Prefix-2-MapManager.RPCA_CallInNewMapAndMovePlayers', 'harmony:IdentityClockEvidence.cs:IdentityClock_PointStartPatch.Prefix#2(MapManager.RPCA_CallInNewMapAndMovePlayers)', 'IdentityClockEvidence.cs:Prefix#2'),
    ('harmony-Keybinds.cs-CharacterReadyPatch.Cleanup-3-CharacterSelectionInstance.Update', 'harmony:Keybinds.cs:CharacterReadyPatch.Cleanup#3(CharacterSelectionInstance.Update)', 'Keybinds.cs:Cleanup#3'),
    ('harmony-Keybinds.cs-CharacterReadyPatch.Transpiler-2-CharacterSelectionInstance.Update', 'harmony:Keybinds.cs:CharacterReadyPatch.Transpiler#2(CharacterSelectionInstance.Update)', 'Keybinds.cs:Transpiler#2'),
    ('harmony-Keybinds.cs-KeyboardFactoryPatch.Cleanup-1-PlayerActions.CreateWithKeyboardBindings', 'harmony:Keybinds.cs:KeyboardFactoryPatch.Cleanup#1(PlayerActions.CreateWithKeyboardBindings)', 'Keybinds.cs:Cleanup#1'),
    ('harmony-Keybinds.cs-KeyboardFactoryPatch.Postfix-1-PlayerActions.CreateWithKeyboardBindings', 'harmony:Keybinds.cs:KeyboardFactoryPatch.Postfix#1(PlayerActions.CreateWithKeyboardBindings)', 'Keybinds.cs:Postfix#1'),
    ('harmony-Keybinds.cs-LobbyReadyPatch.Cleanup-2-PlayerAssigner.LateUpdate', 'harmony:Keybinds.cs:LobbyReadyPatch.Cleanup#2(PlayerAssigner.LateUpdate)', 'Keybinds.cs:Cleanup#2'),
    ('harmony-Keybinds.cs-LobbyReadyPatch.Transpiler-1-PlayerAssigner.LateUpdate', 'harmony:Keybinds.cs:LobbyReadyPatch.Transpiler#1(PlayerAssigner.LateUpdate)', 'Keybinds.cs:Transpiler#1'),
    ('harmony-Keybinds.cs-MapArtPatch.Cleanup-4-ArtHandler.Update', 'harmony:Keybinds.cs:MapArtPatch.Cleanup#4(ArtHandler.Update)', 'Keybinds.cs:Cleanup#4'),
    ('harmony-Keybinds.cs-MapArtPatch.Transpiler-3-ArtHandler.Update', 'harmony:Keybinds.cs:MapArtPatch.Transpiler#3(ArtHandler.Update)', 'Keybinds.cs:Transpiler#3'),
    ('harmony-Keybinds.cs-OnEnablePatch.Cleanup-6-CharacterSelectionInstance.OnEnable', 'harmony:Keybinds.cs:OnEnablePatch.Cleanup#6(CharacterSelectionInstance.OnEnable)', 'Keybinds.cs:Cleanup#6'),
    ('harmony-Keybinds.cs-ReadyUpPatch.Cleanup-8-CharacterSelectionInstance.ReadyUp', 'harmony:Keybinds.cs:ReadyUpPatch.Cleanup#8(CharacterSelectionInstance.ReadyUp)', 'Keybinds.cs:Cleanup#8'),
    ('harmony-Keybinds.cs-ResetMenuPatch.Cleanup-5-CharacterSelectionInstance.ResetMenu', 'harmony:Keybinds.cs:ResetMenuPatch.Cleanup#5(CharacterSelectionInstance.ResetMenu)', 'Keybinds.cs:Cleanup#5'),
    ('harmony-Keybinds.cs-StartPickingPatch.Cleanup-7-CharacterSelectionInstance.StartPicking', 'harmony:Keybinds.cs:StartPickingPatch.Cleanup#7(CharacterSelectionInstance.StartPicking)', 'Keybinds.cs:Cleanup#7'),
    ('harmony-MusicEngine.cs-MusicSuppressionPatch.PlayIngamePrefix', 'harmony:MusicEngine.cs:MusicSuppressionPatch.PlayIngamePrefix(?)', 'MusicEngine.cs:PlayIngamePrefix'),
    ('harmony-MusicEngine.cs-MusicSuppressionPatch.PlayMainMenuPrefix', 'harmony:MusicEngine.cs:MusicSuppressionPatch.PlayMainMenuPrefix(?)', 'MusicEngine.cs:PlayMainMenuPrefix'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.AfterSpectatorMute', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.AfterSpectatorMute(?)', 'NetworkReplicaDiagnostics.cs:AfterSpectatorMute'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.Prefix-1', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.Prefix#1(?)', 'NetworkReplicaDiagnostics.cs:Prefix#1'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSerializationObserverPatch.Transpiler', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSerializationObserverPatch.Transpiler(?)', 'NetworkReplicaDiagnostics.cs:Transpiler'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorActivationPatch.Cleanup-5', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorActivationPatch.Cleanup#5(?)', 'NetworkReplicaDiagnostics.cs:Cleanup#5'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorActivationPatch.Postfix-3', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorActivationPatch.Postfix#3(?)', 'NetworkReplicaDiagnostics.cs:Postfix#3'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorBoundaryPatch.Cleanup-4', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorBoundaryPatch.Cleanup#4(?)', 'NetworkReplicaDiagnostics.cs:Cleanup#4'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorBoundaryPatch.Postfix-2', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorBoundaryPatch.Postfix#2(?)', 'NetworkReplicaDiagnostics.cs:Postfix#2'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorFfaTerminalPatch.Postfix-1', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorFfaTerminalPatch.Postfix#1(?)', 'NetworkReplicaDiagnostics.cs:Postfix#1'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorGmTerminalPatch.Cleanup-2', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorGmTerminalPatch.Cleanup#2(?)', 'NetworkReplicaDiagnostics.cs:Cleanup#2'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorGmTerminalPatch.Prefix-2', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorGmTerminalPatch.Prefix#2(?)', 'NetworkReplicaDiagnostics.cs:Prefix#2'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorRoundEndPatch.Cleanup-6', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorRoundEndPatch.Cleanup#6(?)', 'NetworkReplicaDiagnostics.cs:Cleanup#6'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorRoundEndPatch.Prefix-4', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorRoundEndPatch.Prefix#4(?)', 'NetworkReplicaDiagnostics.cs:Prefix#4'),
    ('harmony-NetworkReplicaDiagnostics.cs-NetworkReplicaSpectatorSnapshotPatch.Postfix-4', 'harmony:NetworkReplicaDiagnostics.cs:NetworkReplicaSpectatorSnapshotPatch.Postfix#4(?)', 'NetworkReplicaDiagnostics.cs:Postfix#4'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_DispatchDepthPatch.Prefix-2', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_DispatchDepthPatch.Prefix#2(?)', 'NetworkSeatTelemetry.cs:Prefix#2'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecycleDiePatch.Finalizer-2-HealthHandler.RPCA_Die', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecycleDiePatch.Finalizer#2(HealthHandler.RPCA_Die)', 'NetworkSeatTelemetry.cs:Finalizer#2'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecycleDiePatch.Postfix-3-HealthHandler.RPCA_Die', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecycleDiePatch.Postfix#3(HealthHandler.RPCA_Die)', 'NetworkSeatTelemetry.cs:Postfix#3'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecyclePhoenixPatch.Finalizer-3-HealthHandler.RPCA_Die_Phoenix', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecyclePhoenixPatch.Finalizer#3(HealthHandler.RPCA_Die_Phoenix)', 'NetworkSeatTelemetry.cs:Finalizer#3'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecyclePhoenixPatch.Postfix-4-HealthHandler.RPCA_Die_Phoenix', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecyclePhoenixPatch.Postfix#4(HealthHandler.RPCA_Die_Phoenix)', 'NetworkSeatTelemetry.cs:Postfix#4'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecycleRevivePatch.Finalizer-4-HealthHandler.Revive', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecycleRevivePatch.Finalizer#4(HealthHandler.Revive)', 'NetworkSeatTelemetry.cs:Finalizer#4'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_LifecycleRevivePatch.Postfix-5-HealthHandler.Revive', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_LifecycleRevivePatch.Postfix#5(HealthHandler.Revive)', 'NetworkSeatTelemetry.cs:Postfix#5'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_MovementCapturePatch.Postfix-6-SyncPlayerMovement.OnPhotonSerializeView', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_MovementCapturePatch.Postfix#6(SyncPlayerMovement.OnPhotonSerializeView)', 'NetworkSeatTelemetry.cs:Postfix#6'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_MovementCapturePatch.Prefix-7-SyncPlayerMovement.OnPhotonSerializeView', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_MovementCapturePatch.Prefix#7(SyncPlayerMovement.OnPhotonSerializeView)', 'NetworkSeatTelemetry.cs:Prefix#7'),
    ('harmony-NetworkSeatTelemetry.cs-NetworkSeat_RaiseEventInternalPatch.Prefix-1', 'harmony:NetworkSeatTelemetry.cs:NetworkSeat_RaiseEventInternalPatch.Prefix#1(?)', 'NetworkSeatTelemetry.cs:Prefix#1'),
    ('harmony-OverlayInputGate.cs-OverlayGate_GeneralInput_Patch.Postfix-GeneralInput.Update', 'harmony:OverlayInputGate.cs:OverlayGate_GeneralInput_Patch.Postfix(GeneralInput.Update)', 'OverlayInputGate.cs:Postfix'),
    ('harmony-PerfPatches.cs-DynamicParticlesPlayBulletHitCap.Prefix-4-DynamicParticles.PlayBulletHit', 'harmony:PerfPatches.cs:DynamicParticlesPlayBulletHitCap.Prefix#4(DynamicParticles.PlayBulletHit)', 'PerfPatches.cs:Prefix#4'),
    ('harmony-PerfPatches.cs-MenuControllerHandlerUpdateBail.Prefix-6-MenuControllerHandler.Update', 'harmony:PerfPatches.cs:MenuControllerHandlerUpdateBail.Prefix#6(MenuControllerHandler.Update)', 'PerfPatches.cs:Prefix#6'),
    ('harmony-PerfPatches.cs-PlayerManagerSetInputActiveNullGuard.Prefix-1-PlayerManager.SetInputActive', 'harmony:PerfPatches.cs:PlayerManagerSetInputActiveNullGuard.Prefix#1(PlayerManager.SetInputActive)', 'PerfPatches.cs:Prefix#1'),
    ('harmony-PerfPatches.cs-ProjectileHitOutOfBoundsCleanup.Prefix-3-ProjectileHit.Update', 'harmony:PerfPatches.cs:ProjectileHitOutOfBoundsCleanup.Prefix#3(ProjectileHit.Update)', 'PerfPatches.cs:Prefix#3'),
    ('harmony-PerfPatches.cs-RayHitBulletSoundDoHitEffectFinalizer.Finalizer-2-RayHitBulletSound.DoHitEffect', 'harmony:PerfPatches.cs:RayHitBulletSoundDoHitEffectFinalizer.Finalizer#2(RayHitBulletSound.DoHitEffect)', 'PerfPatches.cs:Finalizer#2'),
    ('harmony-PerfPatches.cs-ScreenEdgeBounceDoHitFinalizer.Finalizer-3-ScreenEdgeBounce.DoHit', 'harmony:PerfPatches.cs:ScreenEdgeBounceDoHitFinalizer.Finalizer#3(ScreenEdgeBounce.DoHit)', 'PerfPatches.cs:Finalizer#3'),
    ('harmony-PerfPatches.cs-ScreenEdgeBounceUpdateFinalizer.Finalizer-4-ScreenEdgeBounce.Update', 'harmony:PerfPatches.cs:ScreenEdgeBounceUpdateFinalizer.Finalizer#4(ScreenEdgeBounce.Update)', 'PerfPatches.cs:Finalizer#4'),
    ('harmony-PerfPatches.cs-ScreenshakerDisablePatch.PreOnGameFeel-Screenshaker.', 'harmony:PerfPatches.cs:ScreenshakerDisablePatch.PreOnGameFeel(Screenshaker.?)', 'PerfPatches.cs:PreOnGameFeel'),
    ('harmony-PerfPatches.cs-ScreenshakerDisablePatch.PreOnUIGameFeel-Screenshaker.', 'harmony:PerfPatches.cs:ScreenshakerDisablePatch.PreOnUIGameFeel(Screenshaker.?)', 'PerfPatches.cs:PreOnUIGameFeel'),
    ('harmony-PerfPatches.cs-StunPlayerGoNullGuard.Prefix-2-StunPlayer.Go', 'harmony:PerfPatches.cs:StunPlayerGoNullGuard.Prefix#2(StunPlayer.Go)', 'PerfPatches.cs:Prefix#2'),
    ('harmony-Plugin.cs-ArtHandlerAwakePatch.Postfix-20-ArtHandler.Awake', 'harmony:Plugin.cs:ArtHandlerAwakePatch.Postfix#20(ArtHandler.Awake)', 'Plugin.cs:Postfix#20'),
    ('harmony-Plugin.cs-ArtHandlerNextArtPatch.Prefix-26-ArtHandler.NextArt', 'harmony:Plugin.cs:ArtHandlerNextArtPatch.Prefix#26(ArtHandler.NextArt)', 'Plugin.cs:Prefix#26'),
    ('harmony-Plugin.cs-BlockRpcaDoBlockZombieScrubPatch.Prefix-25-Block.RPCA_DoBlock', 'harmony:Plugin.cs:BlockRpcaDoBlockZombieScrubPatch.Prefix#25(Block.RPCA_DoBlock)', 'Plugin.cs:Prefix#25'),
    ('harmony-Plugin.cs-BlockTryBlockCounterPatch.Postfix-16-Block.TryBlock', 'harmony:Plugin.cs:BlockTryBlockCounterPatch.Postfix#16(Block.TryBlock)', 'Plugin.cs:Postfix#16'),
    ('harmony-Plugin.cs-CardChoiceEndPickPatch.Prefix-17-CardChoice.RPCA_DoEndPick', 'harmony:Plugin.cs:CardChoiceEndPickPatch.Prefix#17(CardChoice.RPCA_DoEndPick)', 'Plugin.cs:Prefix#17'),
    ('harmony-Plugin.cs-CardChoiceVisuals_Hide_PopupCarrier_Patch.Postfix-9-CardChoiceVisuals.Hide', 'harmony:Plugin.cs:CardChoiceVisuals_Hide_PopupCarrier_Patch.Postfix#9(CardChoiceVisuals.Hide)', 'Plugin.cs:Postfix#9'),
    ('harmony-Plugin.cs-CardChoiceVisuals_SetSelected_Instinct_Patch.Postfix-11-CardChoiceVisuals.RPCA_SetCurrentSelected', 'harmony:Plugin.cs:CardChoiceVisuals_SetSelected_Instinct_Patch.Postfix#11(CardChoiceVisuals.RPCA_SetCurrentSelected)', 'Plugin.cs:Postfix#11'),
    ('harmony-Plugin.cs-CardChoiceVisuals_Show_Competitive_Patch.Postfix-8-CardChoiceVisuals.Show', 'harmony:Plugin.cs:CardChoiceVisuals_Show_Competitive_Patch.Postfix#8(CardChoiceVisuals.Show)', 'Plugin.cs:Postfix#8'),
    ('harmony-Plugin.cs-CardChoiceVisuals_Show_Competitive_Patch.Prefix-8-CardChoiceVisuals.Show', 'harmony:Plugin.cs:CardChoiceVisuals_Show_Competitive_Patch.Prefix#8(CardChoiceVisuals.Show)', 'Plugin.cs:Prefix#8'),
    ('harmony-Plugin.cs-CharacterSelectionMenu_PlayerJoined_2v2_Patch.Prefix-1-CharacterSelectionMenu.PlayerJoined', 'harmony:Plugin.cs:CharacterSelectionMenu_PlayerJoined_2v2_Patch.Prefix#1(CharacterSelectionMenu.PlayerJoined)', 'Plugin.cs:Prefix#1'),
    ('harmony-Plugin.cs-GMArmsRaceAwakePatch.Postfix-1-GM_ArmsRace.Awake', 'harmony:Plugin.cs:GMArmsRaceAwakePatch.Postfix#1(GM_ArmsRace.Awake)', 'Plugin.cs:Postfix#1'),
    ('harmony-Plugin.cs-GMArmsRaceOnEnable_4Player_Patch.Postfix-2-GM_ArmsRace.OnEnable', 'harmony:Plugin.cs:GMArmsRaceOnEnable_4Player_Patch.Postfix#2(GM_ArmsRace.OnEnable)', 'Plugin.cs:Postfix#2'),
    ('harmony-Plugin.cs-GMArmsRaceStartGameBlockResetPatch.Postfix-18-GM_ArmsRace.StartGame', 'harmony:Plugin.cs:GMArmsRaceStartGameBlockResetPatch.Postfix#18(GM_ArmsRace.StartGame)', 'Plugin.cs:Postfix#18'),
    ('harmony-Plugin.cs-GMArmsRace_DoStartGame_PopupCarrier_Patch.Prefix-9-GM_ArmsRace.DoStartGame', 'harmony:Plugin.cs:GMArmsRace_DoStartGame_PopupCarrier_Patch.Prefix#9(GM_ArmsRace.DoStartGame)', 'Plugin.cs:Prefix#9'),
    ('harmony-Plugin.cs-GMArmsRace_PlayerJoined_Diag_Patch.Prefix-6-GM_ArmsRace.PlayerJoined', 'harmony:Plugin.cs:GMArmsRace_PlayerJoined_Diag_Patch.Prefix#6(GM_ArmsRace.PlayerJoined)', 'Plugin.cs:Prefix#6'),
    ('harmony-Plugin.cs-GMArmsRace_StartGame_Diag_Patch.Prefix-7-GM_ArmsRace.StartGame', 'harmony:Plugin.cs:GMArmsRace_StartGame_Diag_Patch.Prefix#7(GM_ArmsRace.StartGame)', 'Plugin.cs:Prefix#7'),
    ('harmony-Plugin.cs-GameCrownHandler2v2Patch.Prefix-10-GameCrownHandler.LateUpdate', 'harmony:Plugin.cs:GameCrownHandler2v2Patch.Prefix#10(GameCrownHandler.LateUpdate)', 'Plugin.cs:Prefix#10'),
    ('harmony-Plugin.cs-GunApplyPlayerStuffProvenancePatch.Postfix-24-Gun.ApplyPlayerStuff', 'harmony:Plugin.cs:GunApplyPlayerStuffProvenancePatch.Postfix#24(Gun.ApplyPlayerStuff)', 'Plugin.cs:Postfix#24'),
    ('harmony-Plugin.cs-MapManager_GetSpawnPoints_2v2_Patch.Postfix-13-MapManager.GetSpawnPoints', 'harmony:Plugin.cs:MapManager_GetSpawnPoints_2v2_Patch.Postfix#13(MapManager.GetSpawnPoints)', 'Plugin.cs:Postfix#13'),
    ('harmony-Plugin.cs-MapManager_UnloadAfterSeconds_Diag_Patch.Finalizer-1-MapManager.UnloadAfterSeconds', 'harmony:Plugin.cs:MapManager_UnloadAfterSeconds_Diag_Patch.Finalizer#1(MapManager.UnloadAfterSeconds)', 'Plugin.cs:Finalizer#1'),
    ('harmony-Plugin.cs-MapPhysicalColorPatch.GetTransformPath-Map.Start', 'harmony:Plugin.cs:MapPhysicalColorPatch.GetTransformPath(Map.Start)', 'Plugin.cs:GetTransformPath'),
    ('harmony-Plugin.cs-MapPhysicalColorPatch.Postfix-21-Map.Start', 'harmony:Plugin.cs:MapPhysicalColorPatch.Postfix#21(Map.Start)', 'Plugin.cs:Postfix#21'),
    ('harmony-Plugin.cs-ModRoomChurnFreezePatch.Postfix-4-NetworkConnectionHandler.OnJoinedRoom', 'harmony:Plugin.cs:ModRoomChurnFreezePatch.Postfix#4(NetworkConnectionHandler.OnJoinedRoom)', 'Plugin.cs:Postfix#4'),
    ('harmony-Plugin.cs-MultiPickerShowVisualsPatch.Prefix-13-CardChoice.StartPick', 'harmony:Plugin.cs:MultiPickerShowVisualsPatch.Prefix#13(CardChoice.StartPick)', 'Plugin.cs:Prefix#13'),
    ('harmony-Plugin.cs-NetworkConnectionHandler_NetworkRestart_Diag_Patch.Prefix-4-NetworkConnectionHandler.NetworkRestart', 'harmony:Plugin.cs:NetworkConnectionHandler_NetworkRestart_Diag_Patch.Prefix#4(NetworkConnectionHandler.NetworkRestart)', 'Plugin.cs:Prefix#4'),
    ('harmony-Plugin.cs-NetworkConnectionHandler_OnJoinedRoom_RestyleNick_Patch.Postfix-6-NetworkConnectionHandler.OnJoinedRoom', 'harmony:Plugin.cs:NetworkConnectionHandler_OnJoinedRoom_RestyleNick_Patch.Postfix#6(NetworkConnectionHandler.OnJoinedRoom)', 'Plugin.cs:Postfix#6'),
    ('harmony-Plugin.cs-OvtExtraPickPatch.Prefix-14-CardChoice.StartPick', 'harmony:Plugin.cs:OvtExtraPickPatch.Prefix#14(CardChoice.StartPick)', 'Plugin.cs:Prefix#14'),
    ('harmony-Plugin.cs-PlayerAssigner_CreatePlayer_2v2_Patch.Prefix-2-PlayerAssigner.CreatePlayer', 'harmony:Plugin.cs:PlayerAssigner_CreatePlayer_2v2_Patch.Prefix#2(PlayerAssigner.CreatePlayer)', 'Plugin.cs:Prefix#2'),
    ('harmony-Plugin.cs-PlayerManagerResetCharactersBlockResetPatch.Postfix-19-PlayerManager.ResetCharacters', 'harmony:Plugin.cs:PlayerManagerResetCharactersBlockResetPatch.Postfix#19(PlayerManager.ResetCharacters)', 'Plugin.cs:Postfix#19'),
    ('harmony-Plugin.cs-PlayerSkinBank_GetPlayerSkinColors_2v2_Patch.Prefix-12-PlayerSkinBank.GetPlayerSkinColors', 'harmony:Plugin.cs:PlayerSkinBank_GetPlayerSkinColors_2v2_Patch.Prefix#12(PlayerSkinBank.GetPlayerSkinColors)', 'Plugin.cs:Prefix#12'),
    ('harmony-Plugin.cs-PlayerSkinHandlerInitRebakeGuard.Postfix-14-PlayerSkinHandler.Init', 'harmony:Plugin.cs:PlayerSkinHandlerInitRebakeGuard.Postfix#14(PlayerSkinHandler.Init)', 'Plugin.cs:Postfix#14'),
    ('harmony-Plugin.cs-Player_FullReset_CardBaseline_Patch.Postfix-12-.FullReset', 'harmony:Plugin.cs:Player_FullReset_CardBaseline_Patch.Postfix#12(?.FullReset)', 'Plugin.cs:Postfix#12'),
    ('harmony-Plugin.cs-Player_Start_Diag_Patch.Postfix-7-.Start', 'harmony:Plugin.cs:Player_Start_Diag_Patch.Postfix#7(?.Start)', 'Plugin.cs:Postfix#7'),
    ('harmony-Plugin.cs-PopUpHandler_StartPicking_Competitive_Patch.Prefix-11-PopUpHandler.StartPicking', 'harmony:Plugin.cs:PopUpHandler_StartPicking_Competitive_Patch.Prefix#11(PopUpHandler.StartPicking)', 'Plugin.cs:Prefix#11'),
    ('harmony-Plugin.cs-QuickplayChurnAbandonGuardPatch.Prefix-3-NetworkConnectionHandler.PlayOnBestActiveRegion', 'harmony:Plugin.cs:QuickplayChurnAbandonGuardPatch.Prefix#3(NetworkConnectionHandler.PlayOnBestActiveRegion)', 'Plugin.cs:Prefix#3'),
    ('harmony-Plugin.cs-QuickplayChurnFreezePatch.Postfix-3-NetworkConnectionHandler.OnPlayerEnteredRoom', 'harmony:Plugin.cs:QuickplayChurnFreezePatch.Postfix#3(NetworkConnectionHandler.OnPlayerEnteredRoom)', 'Plugin.cs:Postfix#3'),
    ('harmony-PoisonSync.cs-PointEndEvidencePatch.After-2', 'harmony:PoisonSync.cs:PointEndEvidencePatch.After#2(?)', 'PoisonSync.cs:After#2'),
    ('harmony-PoisonSync.cs-PoisonArmPatch.Finalizer-3-RayHitPoison.DoHitEffect', 'harmony:PoisonSync.cs:PoisonArmPatch.Finalizer#3(RayHitPoison.DoHitEffect)', 'PoisonSync.cs:Finalizer#3'),
    ('harmony-PoisonSync.cs-PoisonArmPatch.Prefix-4-RayHitPoison.DoHitEffect', 'harmony:PoisonSync.cs:PoisonArmPatch.Prefix#4(RayHitPoison.DoHitEffect)', 'PoisonSync.cs:Prefix#4'),
    ('harmony-PoisonSync.cs-PoisonDeathFlushPatch.After-5-HealthHandler.RPCA_Die', 'harmony:PoisonSync.cs:PoisonDeathFlushPatch.After#5(HealthHandler.RPCA_Die)', 'PoisonSync.cs:After#5'),
    ('harmony-PoisonSync.cs-PoisonDotSchedulerPatch.Cleanup-2-DamageOverTime.TakeDamageOverTime', 'harmony:PoisonSync.cs:PoisonDotSchedulerPatch.Cleanup#2(DamageOverTime.TakeDamageOverTime)', 'PoisonSync.cs:Cleanup#2'),
    ('harmony-PoisonSync.cs-PoisonDotSchedulerPatch.Prefix-1-DamageOverTime.TakeDamageOverTime', 'harmony:PoisonSync.cs:PoisonDotSchedulerPatch.Prefix#1(DamageOverTime.TakeDamageOverTime)', 'PoisonSync.cs:Prefix#1'),
    ('harmony-PoisonSync.cs-PoisonHitBracketPatch.Finalizer-2-ProjectileHit.Hit', 'harmony:PoisonSync.cs:PoisonHitBracketPatch.Finalizer#2(ProjectileHit.Hit)', 'PoisonSync.cs:Finalizer#2'),
    ('harmony-PoisonSync.cs-PoisonHitBracketPatch.Prefix-3-ProjectileHit.Hit', 'harmony:PoisonSync.cs:PoisonHitBracketPatch.Prefix#3(ProjectileHit.Hit)', 'PoisonSync.cs:Prefix#3'),
    ('harmony-PoisonSync.cs-PoisonPhoenixBoundaryPatch.After-4-HealthHandler.RPCA_Die_Phoenix', 'harmony:PoisonSync.cs:PoisonPhoenixBoundaryPatch.After#4(HealthHandler.RPCA_Die_Phoenix)', 'PoisonSync.cs:After#4'),
    ('harmony-PoisonSync.cs-PoisonPhoenixBoundaryPatch.Threw-3-HealthHandler.RPCA_Die_Phoenix', 'harmony:PoisonSync.cs:PoisonPhoenixBoundaryPatch.Threw#3(HealthHandler.RPCA_Die_Phoenix)', 'PoisonSync.cs:Threw#3'),
    ('harmony-PoisonSync.cs-PoisonPointBoundaryPatch.After-3', 'harmony:PoisonSync.cs:PoisonPointBoundaryPatch.After#3(?)', 'PoisonSync.cs:After#3'),
    ('harmony-PoisonSync.cs-PoisonPointBoundaryPatch.Threw-2', 'harmony:PoisonSync.cs:PoisonPointBoundaryPatch.Threw#2(?)', 'PoisonSync.cs:Threw#2'),
    ('harmony-PoisonSync.cs-PoisonReviveFencePatch.AfterRevive-HealthHandler.Revive', 'harmony:PoisonSync.cs:PoisonReviveFencePatch.AfterRevive(HealthHandler.Revive)', 'PoisonSync.cs:AfterRevive'),
    ('harmony-PoisonSync.cs-PoisonReviveFencePatch.Threw-1-HealthHandler.Revive', 'harmony:PoisonSync.cs:PoisonReviveFencePatch.Threw#1(HealthHandler.Revive)', 'PoisonSync.cs:Threw#1'),
    ('harmony-PoisonSync.cs-SawPointEvidencePatch.After-1-Saw.Update', 'harmony:PoisonSync.cs:SawPointEvidencePatch.After#1(Saw.Update)', 'PoisonSync.cs:After#1'),
    ('harmony-PoisonSync.cs-SawPointEvidencePatch.Before-Saw.Update', 'harmony:PoisonSync.cs:SawPointEvidencePatch.Before(Saw.Update)', 'PoisonSync.cs:Before'),
    ('harmony-ProximityVictimPatches.cs-DealDamageToPlayerFreshVictimPatch.BeforeGo-1-DealDamageToPlayer.Go', 'harmony:ProximityVictimPatches.cs:DealDamageToPlayerFreshVictimPatch.BeforeGo#1(DealDamageToPlayer.Go)', 'ProximityVictimPatches.cs:BeforeGo#1'),
    ('harmony-ProximityVictimPatches.cs-StunPlayerFreshVictimPatch.BeforeGo-2-StunPlayer.Go', 'harmony:ProximityVictimPatches.cs:StunPlayerFreshVictimPatch.BeforeGo#2(StunPlayer.Go)', 'ProximityVictimPatches.cs:BeforeGo#2'),
    ('harmony-ProximityVictimPatches.cs-TeleportToOpponentFreshVictimPatch.BeforeGo-3-TeleportToOpponent.Go', 'harmony:ProximityVictimPatches.cs:TeleportToOpponentFreshVictimPatch.BeforeGo#3(TeleportToOpponent.Go)', 'ProximityVictimPatches.cs:BeforeGo#3'),
    ('harmony-SeatEvidence.cs-SeatEvidence_RpcSendPatch.Postfix', 'harmony:SeatEvidence.cs:SeatEvidence_RpcSendPatch.Postfix(?)', 'SeatEvidence.cs:Postfix'),
    ('harmony-SpectatorPatches.cs-Spectator_BoundaryObserver_Patch.Postfix-3-MapManager.RPCA_CallInNewMapAndMovePlayers', 'harmony:SpectatorPatches.cs:Spectator_BoundaryObserver_Patch.Postfix#3(MapManager.RPCA_CallInNewMapAndMovePlayers)', 'SpectatorPatches.cs:Postfix#3'),
    ('harmony-SpectatorPatches.cs-Spectator_EntryIsNotMatchFound_Patch.Prefix-23-NetworkConnectionHandler.OnPlayerEnteredRoom', 'harmony:SpectatorPatches.cs:Spectator_EntryIsNotMatchFound_Patch.Prefix#23(NetworkConnectionHandler.OnPlayerEnteredRoom)', 'SpectatorPatches.cs:Prefix#23'),
    ('harmony-SpectatorPatches.cs-Spectator_LeaveIsInvisible_Patch.Prefix-22-NetworkConnectionHandler.OnPlayerLeftRoom', 'harmony:SpectatorPatches.cs:Spectator_LeaveIsInvisible_Patch.Prefix#22(NetworkConnectionHandler.OnPlayerLeftRoom)', 'SpectatorPatches.cs:Prefix#22'),
    ('harmony-SpectatorPatches.cs-Spectator_MapLoadGate_Patch.Prefix-17-MapManager.RPCA_LoadLevel', 'harmony:SpectatorPatches.cs:Spectator_MapLoadGate_Patch.Prefix#17(MapManager.RPCA_LoadLevel)', 'SpectatorPatches.cs:Prefix#17'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_CallInBare_Patch.Prefix-21-MapManager.CallInNewMap', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_CallInBare_Patch.Prefix#21(MapManager.CallInNewMap)', 'SpectatorPatches.cs:Prefix#21'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_CallIn_Patch.Prefix-20-MapManager.CallInNewMapAndMovePlayers', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_CallIn_Patch.Prefix#20(MapManager.CallInNewMapAndMovePlayers)', 'SpectatorPatches.cs:Prefix#20'),
    ('harmony-SpectatorPatches.cs-Spectator_NoMapAuthority_Load_Patch.Prefix-19-MapManager.LoadNextLevel', 'harmony:SpectatorPatches.cs:Spectator_NoMapAuthority_Load_Patch.Prefix#19(MapManager.LoadNextLevel)', 'SpectatorPatches.cs:Prefix#19'),
    ('harmony-SpectatorPatches.cs-Spectator_ObserveNextRound_Patch.Prefix-10-GM_ArmsRace.RPCA_NextRound', 'harmony:SpectatorPatches.cs:Spectator_ObserveNextRound_Patch.Prefix#10(GM_ArmsRace.RPCA_NextRound)', 'SpectatorPatches.cs:Prefix#10'),
    ('harmony-SpectatorPatches.cs-Spectator_RegistrationFirewall_Patch.Prefix-25-PlayerManager.RegisterPlayer', 'harmony:SpectatorPatches.cs:Spectator_RegistrationFirewall_Patch.Prefix#25(PlayerManager.RegisterPlayer)', 'SpectatorPatches.cs:Prefix#25'),
    ('harmony-SpectatorPatches.cs-Spectator_ReplayQuarantine_Patch.Prefix-15-PhotonMapObject.Start', 'harmony:SpectatorPatches.cs:Spectator_ReplayQuarantine_Patch.Prefix#15(PhotonMapObject.Start)', 'SpectatorPatches.cs:Prefix#15'),
    ('harmony-SpectatorPatches.cs-Spectator_ReplayTag_Patch.Postfix-1-PhotonMapObject.Awake', 'harmony:SpectatorPatches.cs:Spectator_ReplayTag_Patch.Postfix#1(PhotonMapObject.Awake)', 'SpectatorPatches.cs:Postfix#1'),
    ('harmony-SpectatorTeardownProbe.cs-PlayerVelocity_TeardownDrive_Patch.Prefix-PlayerVelocity.FixedUpdate', 'harmony:SpectatorTeardownProbe.cs:PlayerVelocity_TeardownDrive_Patch.Prefix(PlayerVelocity.FixedUpdate)', 'SpectatorTeardownProbe.cs:Prefix'),
    ('harmony-StatusIndicatorGuard.cs-CodeAnimStartRestorePatch.Prefix-4-CodeAnimation.Start', 'harmony:StatusIndicatorGuard.cs:CodeAnimStartRestorePatch.Prefix#4(CodeAnimation.Start)', 'StatusIndicatorGuard.cs:Prefix#4'),
    ('harmony-StatusIndicatorGuard.cs-SilenceDisableCapturePatch.Prefix-2-SilenceHandler.OnDisable', 'harmony:StatusIndicatorGuard.cs:SilenceDisableCapturePatch.Prefix#2(SilenceHandler.OnDisable)', 'StatusIndicatorGuard.cs:Prefix#2'),
    ('harmony-StatusIndicatorGuard.cs-SilenceStartPatch.Postfix-2', 'harmony:StatusIndicatorGuard.cs:SilenceStartPatch.Postfix#2(?)', 'StatusIndicatorGuard.cs:Postfix#2'),
    ('harmony-StatusIndicatorGuard.cs-SilenceStartPatch.Prefix-1', 'harmony:StatusIndicatorGuard.cs:SilenceStartPatch.Prefix#1(?)', 'StatusIndicatorGuard.cs:Prefix#1'),
    ('harmony-StatusIndicatorGuard.cs-SilenceStartRewirePatch.Postfix-1-SilenceHandler.Start', 'harmony:StatusIndicatorGuard.cs:SilenceStartRewirePatch.Postfix#1(SilenceHandler.Start)', 'StatusIndicatorGuard.cs:Postfix#1'),
    ('harmony-StatusIndicatorGuard.cs-StunDisableCapturePatch.Prefix-3-StunHandler.OnDisable', 'harmony:StatusIndicatorGuard.cs:StunDisableCapturePatch.Prefix#3(StunHandler.OnDisable)', 'StatusIndicatorGuard.cs:Prefix#3'),
    ('harmony-TeamColorIdentity.cs-GameOverTextTeamColorPatch.AfterDisplay-UIHandler.DisplayScreenText', 'harmony:TeamColorIdentity.cs:GameOverTextTeamColorPatch.AfterDisplay(UIHandler.DisplayScreenText)', 'TeamColorIdentity.cs:AfterDisplay'),
    ('harmony-TeamColorIdentity.cs-GameOverTextTeamColorPatch.Cleanup-6-UIHandler.DisplayScreenText', 'harmony:TeamColorIdentity.cs:GameOverTextTeamColorPatch.Cleanup#6(UIHandler.DisplayScreenText)', 'TeamColorIdentity.cs:Cleanup#6'),
    ('harmony-TeamColorIdentity.cs-JumpDustTeamColorPatch.BeforeJump-PlayerJump.Jump', 'harmony:TeamColorIdentity.cs:JumpDustTeamColorPatch.BeforeJump(PlayerJump.Jump)', 'TeamColorIdentity.cs:BeforeJump'),
    ('harmony-TeamColorIdentity.cs-JumpDustTeamColorPatch.Cleanup-4-PlayerJump.Jump', 'harmony:TeamColorIdentity.cs:JumpDustTeamColorPatch.Cleanup#4(PlayerJump.Jump)', 'TeamColorIdentity.cs:Cleanup#4'),
    ('harmony-TeamColorIdentity.cs-LandDustTeamColorPatch.BeforeTouchGround-CharacterData.TouchGround', 'harmony:TeamColorIdentity.cs:LandDustTeamColorPatch.BeforeTouchGround(CharacterData.TouchGround)', 'TeamColorIdentity.cs:BeforeTouchGround'),
    ('harmony-TeamColorIdentity.cs-LandDustTeamColorPatch.Cleanup-5-CharacterData.TouchGround', 'harmony:TeamColorIdentity.cs:LandDustTeamColorPatch.Cleanup#5(CharacterData.TouchGround)', 'TeamColorIdentity.cs:Cleanup#5'),
    ('harmony-TeamColorIdentity.cs-PlayerNameTeamColorPatch.AfterStart-PlayerName.Start', 'harmony:TeamColorIdentity.cs:PlayerNameTeamColorPatch.AfterStart(PlayerName.Start)', 'TeamColorIdentity.cs:AfterStart'),
    ('harmony-TeamColorIdentity.cs-PlayerNameTeamColorPatch.Cleanup-3-PlayerName.Start', 'harmony:TeamColorIdentity.cs:PlayerNameTeamColorPatch.Cleanup#3(PlayerName.Start)', 'TeamColorIdentity.cs:Cleanup#3'),
    ('harmony-TeamColorIdentity.cs-PointVisualizerTeamColorPatch.AfterDoShowPoints-PointVisualizer.DoShowPoints', 'harmony:TeamColorIdentity.cs:PointVisualizerTeamColorPatch.AfterDoShowPoints(PointVisualizer.DoShowPoints)', 'TeamColorIdentity.cs:AfterDoShowPoints'),
    ('harmony-TeamColorIdentity.cs-PointVisualizerTeamColorPatch.Cleanup-1-PointVisualizer.DoShowPoints', 'harmony:TeamColorIdentity.cs:PointVisualizerTeamColorPatch.Cleanup#1(PointVisualizer.DoShowPoints)', 'TeamColorIdentity.cs:Cleanup#1'),
    ('harmony-TeamColorIdentity.cs-RematchTextTeamColorPatch.AfterDisplayLoop', 'harmony:TeamColorIdentity.cs:RematchTextTeamColorPatch.AfterDisplayLoop(?)', 'TeamColorIdentity.cs:AfterDisplayLoop'),
    ('harmony-TeamColorIdentity.cs-RoundCounterTeamColorPatch.AfterReDraw-RoundCounter.ReDraw', 'harmony:TeamColorIdentity.cs:RoundCounterTeamColorPatch.AfterReDraw(RoundCounter.ReDraw)', 'TeamColorIdentity.cs:AfterReDraw'),
    ('harmony-TeamColorIdentity.cs-RoundCounterTeamColorPatch.Cleanup-2-RoundCounter.ReDraw', 'harmony:TeamColorIdentity.cs:RoundCounterTeamColorPatch.Cleanup#2(RoundCounter.ReDraw)', 'TeamColorIdentity.cs:Cleanup#2'),
    ('harmony-TeamGameLifecycle.cs-TeamGameLifecycle_DoStartGame_Patch.Prefix-1-GM_ArmsRace.DoStartGame', 'harmony:TeamGameLifecycle.cs:TeamGameLifecycle_DoStartGame_Patch.Prefix#1(GM_ArmsRace.DoStartGame)', 'TeamGameLifecycle.cs:Prefix#1'),
    ('harmony-TeamGameLifecycle.cs-TeamGameLifecycle_GameOverTransition_Patch.Prefix-2-GM_ArmsRace.GameOverTransition', 'harmony:TeamGameLifecycle.cs:TeamGameLifecycle_GameOverTransition_Patch.Prefix#2(GM_ArmsRace.GameOverTransition)', 'TeamGameLifecycle.cs:Prefix#2'),
    ('harmony-TeamHoldFence.cs-TeamHold_PointTransitionPatch.Prefix-1-GM_ArmsRace.PointTransition', 'harmony:TeamHoldFence.cs:TeamHold_PointTransitionPatch.Prefix#1(GM_ArmsRace.PointTransition)', 'TeamHoldFence.cs:Prefix#1'),
    ('harmony-TeamHoldFence.cs-TeamHold_RematchFencePatch.Postfix-GM_ArmsRace.DoStartGame', 'harmony:TeamHoldFence.cs:TeamHold_RematchFencePatch.Postfix(GM_ArmsRace.DoStartGame)', 'TeamHoldFence.cs:Postfix'),
    ('harmony-TeamHoldFence.cs-TeamHold_RoundTransitionPatch.Prefix-2-GM_ArmsRace.RoundTransition', 'harmony:TeamHoldFence.cs:TeamHold_RoundTransitionPatch.Prefix#2(GM_ArmsRace.RoundTransition)', 'TeamHoldFence.cs:Prefix#2'),
    ('harmony-TeamHoldPatches.cs-NCH_OnPlayerLeftRoom_Hold_Patch.Prefix-5-NetworkConnectionHandler.OnPlayerLeftRoom', 'harmony:TeamHoldPatches.cs:NCH_OnPlayerLeftRoom_Hold_Patch.Prefix#5(NetworkConnectionHandler.OnPlayerLeftRoom)', 'TeamHoldPatches.cs:Prefix#5'),
    ('harmony-TeamHoldPatches.cs-TeamHold_GameOverPatch.Prefix-4-GM_ArmsRace.GameOverTransition', 'harmony:TeamHoldPatches.cs:TeamHold_GameOverPatch.Prefix#4(GM_ArmsRace.GameOverTransition)', 'TeamHoldPatches.cs:Prefix#4'),
    ('harmony-TeamHoldPatches.cs-TeamHold_GameStartPatch.Prefix-3-GM_ArmsRace.DoStartGame', 'harmony:TeamHoldPatches.cs:TeamHold_GameStartPatch.Prefix#3(GM_ArmsRace.DoStartGame)', 'TeamHoldPatches.cs:Prefix#3'),
    ('harmony-TeamHoldPatches.cs-TeamHold_OfflinePickPatch.Postfix-2-ApplyCardStats.OFFLINE_Pick', 'harmony:TeamHoldPatches.cs:TeamHold_OfflinePickPatch.Postfix#2(ApplyCardStats.OFFLINE_Pick)', 'TeamHoldPatches.cs:Postfix#2'),
    ('harmony-TeamHoldPatches.cs-TeamHold_PhoenixClaimPatch.Prefix-2-HealthHandler.RPCA_Die_Phoenix', 'harmony:TeamHoldPatches.cs:TeamHold_PhoenixClaimPatch.Prefix#2(HealthHandler.RPCA_Die_Phoenix)', 'TeamHoldPatches.cs:Prefix#2'),
    ('harmony-TeamHoldPatches.cs-TeamHold_PickSeamPatch.Finalizer-ApplyCardStats.RPCA_Pick', 'harmony:TeamHoldPatches.cs:TeamHold_PickSeamPatch.Finalizer(ApplyCardStats.RPCA_Pick)', 'TeamHoldPatches.cs:Finalizer'),
    ('harmony-TeamHoldPatches.cs-TeamHold_PickSeamPatch.Postfix-1-ApplyCardStats.RPCA_Pick', 'harmony:TeamHoldPatches.cs:TeamHold_PickSeamPatch.Postfix#1(ApplyCardStats.RPCA_Pick)', 'TeamHoldPatches.cs:Postfix#1'),
    ('harmony-TeamHoldPatches.cs-TeamHold_PickSeamPatch.Prefix-1-ApplyCardStats.RPCA_Pick', 'harmony:TeamHoldPatches.cs:TeamHold_PickSeamPatch.Prefix#1(ApplyCardStats.RPCA_Pick)', 'TeamHoldPatches.cs:Prefix#1'),
    ('harmony-TeamHoldPick.cs-TeamHold_DoPickPatch.Postfix-CardChoice.DoPick', 'harmony:TeamHoldPick.cs:TeamHold_DoPickPatch.Postfix(CardChoice.DoPick)', 'TeamHoldPick.cs:Postfix'),
    ('harmony-TeamHoldPick.cs-TeamHold_DoPickPatch.Prefix-CardChoice.DoPick', 'harmony:TeamHoldPick.cs:TeamHold_DoPickPatch.Prefix(CardChoice.DoPick)', 'TeamHoldPick.cs:Prefix'),
    ('harmony-VanillaCardSequence.cs-CardChoice_DoPick_SameCards_Patch.Prefix-2-CardChoice.DoPick', 'harmony:VanillaCardSequence.cs:CardChoice_DoPick_SameCards_Patch.Prefix#2(CardChoice.DoPick)', 'VanillaCardSequence.cs:Prefix#2'),
    ('harmony-VanillaCardSequence.cs-CardChoice_ReplaceCards_SameCards_Patch.Prefix-3-CardChoice.ReplaceCards', 'harmony:VanillaCardSequence.cs:CardChoice_ReplaceCards_SameCards_Patch.Prefix#3(CardChoice.ReplaceCards)', 'VanillaCardSequence.cs:Prefix#3'),
    ('harmony-VanillaCardSequence.cs-CardChoice_SpawnUniqueCard_SameCards_Patch.Prefix-4-CardChoice.SpawnUniqueCard', 'harmony:VanillaCardSequence.cs:CardChoice_SpawnUniqueCard_SameCards_Patch.Prefix#4(CardChoice.SpawnUniqueCard)', 'VanillaCardSequence.cs:Prefix#4'),
    ('harmony-VanillaCardSequence.cs-GMArmsRace_DoStartGame_SameCards_Patch.Prefix-1-GM_ArmsRace.DoStartGame', 'harmony:VanillaCardSequence.cs:GMArmsRace_DoStartGame_SameCards_Patch.Prefix#1(GM_ArmsRace.DoStartGame)', 'VanillaCardSequence.cs:Prefix#1'),
    ('harmony-VanillaFixes.cs-BulletPoolReleaseGuardPatch.Finalizer-2', 'harmony:VanillaFixes.cs:BulletPoolReleaseGuardPatch.Finalizer#2(?)', 'VanillaFixes.cs:Finalizer#2'),
    ('harmony-VanillaFixes.cs-CardChoiceStaleSpawnedCardsPatch.Postfix-2-CardChoice.ReplaceCards', 'harmony:VanillaFixes.cs:CardChoiceStaleSpawnedCardsPatch.Postfix#2(CardChoice.ReplaceCards)', 'VanillaFixes.cs:Postfix#2'),
    ('harmony-VanillaFixes.cs-CardChoiceStaleSpawnedCardsPatch.Prefix-3-CardChoice.ReplaceCards', 'harmony:VanillaFixes.cs:CardChoiceStaleSpawnedCardsPatch.Prefix#3(CardChoice.ReplaceCards)', 'VanillaFixes.cs:Prefix#3'),
    ('harmony-VanillaFixes.cs-CardPickChatInputGuardPatch.BeforeDoPlayerSelect-CardChoice.DoPlayerSelect', 'harmony:VanillaFixes.cs:CardPickChatInputGuardPatch.BeforeDoPlayerSelect(CardChoice.DoPlayerSelect)', 'VanillaFixes.cs:BeforeDoPlayerSelect'),
    ('harmony-VanillaFixes.cs-CardPickChatInputGuardPatch.Cleanup-31-CardChoice.DoPlayerSelect', 'harmony:VanillaFixes.cs:CardPickChatInputGuardPatch.Cleanup#31(CardChoice.DoPlayerSelect)', 'VanillaFixes.cs:Cleanup#31'),
    ('harmony-VanillaFixes.cs-ChaseCardTextPatch.AfterCardChoiceAwake', 'harmony:VanillaFixes.cs:ChaseCardTextPatch.AfterCardChoiceAwake(?)', 'VanillaFixes.cs:AfterCardChoiceAwake'),
    ('harmony-VanillaFixes.cs-ChaseCardTextPatch.BeforeCardInfoAwake', 'harmony:VanillaFixes.cs:ChaseCardTextPatch.BeforeCardInfoAwake(?)', 'VanillaFixes.cs:BeforeCardInfoAwake'),
    ('harmony-VanillaFixes.cs-DeadPlayerForcePatch.BeforeForceOverTime-HealthHandler.RPCA_SendForceOverTime', 'harmony:VanillaFixes.cs:DeadPlayerForcePatch.BeforeForceOverTime(HealthHandler.RPCA_SendForceOverTime)', 'VanillaFixes.cs:BeforeForceOverTime'),
    ('harmony-VanillaFixes.cs-DeadPlayerForcePatch.Cleanup-10-HealthHandler.RPCA_SendForceOverTime', 'harmony:VanillaFixes.cs:DeadPlayerForcePatch.Cleanup#10(HealthHandler.RPCA_SendForceOverTime)', 'VanillaFixes.cs:Cleanup#10'),
    ('harmony-VanillaFixes.cs-DeadPlayerForcePointPatch.BeforeForceTowardsPoint-HealthHandler.RPCA_SendForceTowardsPointOverTime', 'harmony:VanillaFixes.cs:DeadPlayerForcePointPatch.BeforeForceTowardsPoint(HealthHandler.RPCA_SendForceTowardsPointOverTime)', 'VanillaFixes.cs:BeforeForceTowardsPoint'),
    ('harmony-VanillaFixes.cs-DeadPlayerForcePointPatch.Cleanup-11-HealthHandler.RPCA_SendForceTowardsPointOverTime', 'harmony:VanillaFixes.cs:DeadPlayerForcePointPatch.Cleanup#11(HealthHandler.RPCA_SendForceTowardsPointOverTime)', 'VanillaFixes.cs:Cleanup#11'),
    ('harmony-VanillaFixes.cs-DealtDamageGuardPatch.Cleanup-18-CharacterStatModifiers.DealtDamage', 'harmony:VanillaFixes.cs:DealtDamageGuardPatch.Cleanup#18(CharacterStatModifiers.DealtDamage)', 'VanillaFixes.cs:Cleanup#18'),
    ('harmony-VanillaFixes.cs-DealtDamageGuardPatch.Finalizer-3-CharacterStatModifiers.DealtDamage', 'harmony:VanillaFixes.cs:DealtDamageGuardPatch.Finalizer#3(CharacterStatModifiers.DealtDamage)', 'VanillaFixes.cs:Finalizer#3'),
    ('harmony-VanillaFixes.cs-DemonicPactSprayPatch.AfterResetStats-Gun.ResetStats', 'harmony:VanillaFixes.cs:DemonicPactSprayPatch.AfterResetStats(Gun.ResetStats)', 'VanillaFixes.cs:AfterResetStats'),
    ('harmony-VanillaFixes.cs-DemonicPactSprayPatch.Cleanup-5-Gun.ResetStats', 'harmony:VanillaFixes.cs:DemonicPactSprayPatch.Cleanup#5(Gun.ResetStats)', 'VanillaFixes.cs:Cleanup#5'),
    ('harmony-VanillaFixes.cs-DevConsoleToggleGuardPatch.BeforeToggle', 'harmony:VanillaFixes.cs:DevConsoleToggleGuardPatch.BeforeToggle(?)', 'VanillaFixes.cs:BeforeToggle'),
    ('harmony-VanillaFixes.cs-DrillVisibilityPatch.BeforeDrillDeactivate', 'harmony:VanillaFixes.cs:DrillVisibilityPatch.BeforeDrillDeactivate(?)', 'VanillaFixes.cs:BeforeDrillDeactivate'),
    ('harmony-VanillaFixes.cs-DrillVisibilityPatch.DiagnoseDroppedDrillStop', 'harmony:VanillaFixes.cs:DrillVisibilityPatch.DiagnoseDroppedDrillStop(?)', 'VanillaFixes.cs:DiagnoseDroppedDrillStop'),
    ('harmony-VanillaFixes.cs-EndScreenKillPatch.BeforeTransitionPlayerDied', 'harmony:VanillaFixes.cs:EndScreenKillPatch.BeforeTransitionPlayerDied(?)', 'VanillaFixes.cs:BeforeTransitionPlayerDied'),
    ('harmony-VanillaFixes.cs-EscToggleDiagPatch.Cleanup-33-EscapeMenuHandler.ToggleEsc', 'harmony:VanillaFixes.cs:EscToggleDiagPatch.Cleanup#33(EscapeMenuHandler.ToggleEsc)', 'VanillaFixes.cs:Cleanup#33'),
    ('harmony-VanillaFixes.cs-EscToggleDiagPatch.Postfix-1-EscapeMenuHandler.ToggleEsc', 'harmony:VanillaFixes.cs:EscToggleDiagPatch.Postfix#1(EscapeMenuHandler.ToggleEsc)', 'VanillaFixes.cs:Postfix#1'),
    ('harmony-VanillaFixes.cs-ExplosionPerColliderIsolationPatch.Cleanup-37-Explosion.DoExplosionEffects', 'harmony:VanillaFixes.cs:ExplosionPerColliderIsolationPatch.Cleanup#37(Explosion.DoExplosionEffects)', 'VanillaFixes.cs:Cleanup#37'),
    ('harmony-VanillaFixes.cs-ExplosionPerColliderIsolationPatch.Finalizer-7-Explosion.DoExplosionEffects', 'harmony:VanillaFixes.cs:ExplosionPerColliderIsolationPatch.Finalizer#7(Explosion.DoExplosionEffects)', 'VanillaFixes.cs:Finalizer#7'),
    ('harmony-VanillaFixes.cs-FfaDamageDealtTrackerPatch.AfterDealtDamage-CharacterStatModifiers.DealtDamage', 'harmony:VanillaFixes.cs:FfaDamageDealtTrackerPatch.AfterDealtDamage(CharacterStatModifiers.DealtDamage)', 'VanillaFixes.cs:AfterDealtDamage'),
    ('harmony-VanillaFixes.cs-FfaDamageDealtTrackerPatch.Cleanup-29-CharacterStatModifiers.DealtDamage', 'harmony:VanillaFixes.cs:FfaDamageDealtTrackerPatch.Cleanup#29(CharacterStatModifiers.DealtDamage)', 'VanillaFixes.cs:Cleanup#29'),
    ('harmony-VanillaFixes.cs-GetColorFromTeamEmptyTeamPatch.Prefix-1-PlayerManager.GetColorFromTeam', 'harmony:VanillaFixes.cs:GetColorFromTeamEmptyTeamPatch.Prefix#1(PlayerManager.GetColorFromTeam)', 'VanillaFixes.cs:Prefix#1'),
    ('harmony-VanillaFixes.cs-GetFirstPlayerInTeamEmptyTeamPatch.Prefix-2-PlayerManager.GetFirstPlayerInTeam', 'harmony:VanillaFixes.cs:GetFirstPlayerInTeamEmptyTeamPatch.Prefix#2(PlayerManager.GetFirstPlayerInTeam)', 'VanillaFixes.cs:Prefix#2'),
    ('harmony-VanillaFixes.cs-GrowFpsNormalizePatch.Cleanup-22-TrickShot.Update', 'harmony:VanillaFixes.cs:GrowFpsNormalizePatch.Cleanup#22(TrickShot.Update)', 'VanillaFixes.cs:Cleanup#22'),
    ('harmony-VanillaFixes.cs-GrowFpsNormalizePatch.Transpiler-TrickShot.Update', 'harmony:VanillaFixes.cs:GrowFpsNormalizePatch.Transpiler(TrickShot.Update)', 'VanillaFixes.cs:Transpiler'),
    ('harmony-VanillaFixes.cs-GrowPreJoinSyncPatch.BeforeJoin', 'harmony:VanillaFixes.cs:GrowPreJoinSyncPatch.BeforeJoin(?)', 'VanillaFixes.cs:BeforeJoin'),
    ('harmony-VanillaFixes.cs-HealSoundGuardPatch.Cleanup-19-HealthHandler.Heal', 'harmony:VanillaFixes.cs:HealSoundGuardPatch.Cleanup#19(HealthHandler.Heal)', 'VanillaFixes.cs:Cleanup#19'),
    ('harmony-VanillaFixes.cs-HealSoundGuardPatch.Finalizer-4-HealthHandler.Heal', 'harmony:VanillaFixes.cs:HealSoundGuardPatch.Finalizer#4(HealthHandler.Heal)', 'VanillaFixes.cs:Finalizer#4'),
    ('harmony-VanillaFixes.cs-HostRoomCodeClipboardPatch.AfterSetRoomCode-LoadingScreen.SetRoomCode', 'harmony:VanillaFixes.cs:HostRoomCodeClipboardPatch.AfterSetRoomCode(LoadingScreen.SetRoomCode)', 'VanillaFixes.cs:AfterSetRoomCode'),
    ('harmony-VanillaFixes.cs-HostRoomCodeClipboardPatch.Cleanup-32-LoadingScreen.SetRoomCode', 'harmony:VanillaFixes.cs:HostRoomCodeClipboardPatch.Cleanup#32(LoadingScreen.SetRoomCode)', 'VanillaFixes.cs:Cleanup#32'),
    ('harmony-VanillaFixes.cs-InRangeIndicatorRadiusPatch.AfterStart-1-PlayerInRangeTrigger.Start', 'harmony:VanillaFixes.cs:InRangeIndicatorRadiusPatch.AfterStart#1(PlayerInRangeTrigger.Start)', 'VanillaFixes.cs:AfterStart#1'),
    ('harmony-VanillaFixes.cs-InRangeIndicatorRadiusPatch.Cleanup-4-PlayerInRangeTrigger.Start', 'harmony:VanillaFixes.cs:InRangeIndicatorRadiusPatch.Cleanup#4(PlayerInRangeTrigger.Start)', 'VanillaFixes.cs:Cleanup#4'),
    ('harmony-VanillaFixes.cs-InactiveVisualsHidePatch.BeforeHide-CardChoiceVisuals.Hide', 'harmony:VanillaFixes.cs:InactiveVisualsHidePatch.BeforeHide(CardChoiceVisuals.Hide)', 'VanillaFixes.cs:BeforeHide'),
    ('harmony-VanillaFixes.cs-InactiveVisualsHidePatch.Cleanup-26-CardChoiceVisuals.Hide', 'harmony:VanillaFixes.cs:InactiveVisualsHidePatch.Cleanup#26(CardChoiceVisuals.Hide)', 'VanillaFixes.cs:Cleanup#26'),
    ('harmony-VanillaFixes.cs-LocalPlayerIdPublishPatch.Cleanup-39-PlayerAssigner.CreatePlayer', 'harmony:VanillaFixes.cs:LocalPlayerIdPublishPatch.Cleanup#39(PlayerAssigner.CreatePlayer)', 'VanillaFixes.cs:Cleanup#39'),
    ('harmony-VanillaFixes.cs-LocalPlayerIdPublishPatch.Prefix-6-PlayerAssigner.CreatePlayer', 'harmony:VanillaFixes.cs:LocalPlayerIdPublishPatch.Prefix#6(PlayerAssigner.CreatePlayer)', 'VanillaFixes.cs:Prefix#6'),
    ('harmony-VanillaFixes.cs-OverpowerNonPlayerTargetPatch.Cleanup-36-Explosion_Overpower.HitPlayer', 'harmony:VanillaFixes.cs:OverpowerNonPlayerTargetPatch.Cleanup#36(Explosion_Overpower.HitPlayer)', 'VanillaFixes.cs:Cleanup#36'),
    ('harmony-VanillaFixes.cs-OverpowerNonPlayerTargetPatch.Prefix-4-Explosion_Overpower.HitPlayer', 'harmony:VanillaFixes.cs:OverpowerNonPlayerTargetPatch.Prefix#4(Explosion_Overpower.HitPlayer)', 'VanillaFixes.cs:Prefix#4'),
    ('harmony-VanillaFixes.cs-PhoenixRespawnPatch.BeforeRespawn-DeathEffect.RespawnPlayer', 'harmony:VanillaFixes.cs:PhoenixRespawnPatch.BeforeRespawn(DeathEffect.RespawnPlayer)', 'VanillaFixes.cs:BeforeRespawn'),
    ('harmony-VanillaFixes.cs-PhoenixRespawnPatch.Cleanup-12-DeathEffect.RespawnPlayer', 'harmony:VanillaFixes.cs:PhoenixRespawnPatch.Cleanup#12(DeathEffect.RespawnPlayer)', 'VanillaFixes.cs:Cleanup#12'),
    ('harmony-VanillaFixes.cs-PlayerManagerRevivePlayersWeaponCooldownPatch.AfterRevivePlayers-PlayerManager.RevivePlayers', 'harmony:VanillaFixes.cs:PlayerManagerRevivePlayersWeaponCooldownPatch.AfterRevivePlayers(PlayerManager.RevivePlayers)', 'VanillaFixes.cs:AfterRevivePlayers'),
    ('harmony-VanillaFixes.cs-PlayerManagerRevivePlayersWeaponCooldownPatch.Cleanup-24-PlayerManager.RevivePlayers', 'harmony:VanillaFixes.cs:PlayerManagerRevivePlayersWeaponCooldownPatch.Cleanup#24(PlayerManager.RevivePlayers)', 'VanillaFixes.cs:Cleanup#24'),
    ('harmony-VanillaFixes.cs-PlayerNicknameLabelRefreshPatch.AfterStart-2-PlayerName.Start', 'harmony:VanillaFixes.cs:PlayerNicknameLabelRefreshPatch.AfterStart#2(PlayerName.Start)', 'VanillaFixes.cs:AfterStart#2'),
    ('harmony-VanillaFixes.cs-PlayerNicknameLabelRefreshPatch.Cleanup-35-PlayerName.Start', 'harmony:VanillaFixes.cs:PlayerNicknameLabelRefreshPatch.Cleanup#35(PlayerName.Start)', 'VanillaFixes.cs:Cleanup#35'),
    ('harmony-VanillaFixes.cs-PlayerNicknameRepairPatch.AfterJoin-NetworkConnectionHandler.OnJoinedRoom', 'harmony:VanillaFixes.cs:PlayerNicknameRepairPatch.AfterJoin(NetworkConnectionHandler.OnJoinedRoom)', 'VanillaFixes.cs:AfterJoin'),
    ('harmony-VanillaFixes.cs-PlayerNicknameRepairPatch.Cleanup-34-NetworkConnectionHandler.OnJoinedRoom', 'harmony:VanillaFixes.cs:PlayerNicknameRepairPatch.Cleanup#34(NetworkConnectionHandler.OnJoinedRoom)', 'VanillaFixes.cs:Cleanup#34'),
    ('harmony-VanillaFixes.cs-PoisonEffectRegistrationPatch.DedupeEffectsAfterStart', 'harmony:VanillaFixes.cs:PoisonEffectRegistrationPatch.DedupeEffectsAfterStart(?)', 'VanillaFixes.cs:DedupeEffectsAfterStart'),
    ('harmony-VanillaFixes.cs-PoisonGhostPatch.BeforeDoDamage-1', 'harmony:VanillaFixes.cs:PoisonGhostPatch.BeforeDoDamage#1(?)', 'VanillaFixes.cs:BeforeDoDamage#1'),
    ('harmony-VanillaFixes.cs-RemotePlayerIdOrderPatch.Cleanup-38-.Start', 'harmony:VanillaFixes.cs:RemotePlayerIdOrderPatch.Cleanup#38(?.Start)', 'VanillaFixes.cs:Cleanup#38'),
    ('harmony-VanillaFixes.cs-RemotePlayerIdOrderPatch.Prefix-5-.Start', 'harmony:VanillaFixes.cs:RemotePlayerIdOrderPatch.Prefix#5(?.Start)', 'VanillaFixes.cs:Prefix#5'),
    ('harmony-VanillaFixes.cs-RpcDispatchGuardPatch.Finalizer-1', 'harmony:VanillaFixes.cs:RpcDispatchGuardPatch.Finalizer#1(?)', 'VanillaFixes.cs:Finalizer#1'),
    ('harmony-VanillaFixes.cs-SawDeadTargetPatch.AfterUpdate-1-Saw.Update', 'harmony:VanillaFixes.cs:SawDeadTargetPatch.AfterUpdate#1(Saw.Update)', 'VanillaFixes.cs:AfterUpdate#1'),
    ('harmony-VanillaFixes.cs-SawDeadTargetPatch.Cleanup-2-Saw.Update', 'harmony:VanillaFixes.cs:SawDeadTargetPatch.Cleanup#2(Saw.Update)', 'VanillaFixes.cs:Cleanup#2'),
    ('harmony-VanillaFixes.cs-SawLiveTargetPatch.AfterUpdate-2-Saw.Update', 'harmony:VanillaFixes.cs:SawLiveTargetPatch.AfterUpdate#2(Saw.Update)', 'VanillaFixes.cs:AfterUpdate#2'),
    ('harmony-VanillaFixes.cs-SawLiveTargetPatch.BeforeUpdate-Saw.Update', 'harmony:VanillaFixes.cs:SawLiveTargetPatch.BeforeUpdate(Saw.Update)', 'VanillaFixes.cs:BeforeUpdate'),
    ('harmony-VanillaFixes.cs-SawLiveTargetPatch.Cleanup-3-Saw.Update', 'harmony:VanillaFixes.cs:SawLiveTargetPatch.Cleanup#3(Saw.Update)', 'VanillaFixes.cs:Cleanup#3'),
    ('harmony-VanillaFixes.cs-SonigonPlayGuardPatch.Finalizer-5', 'harmony:VanillaFixes.cs:SonigonPlayGuardPatch.Finalizer#5(?)', 'VanillaFixes.cs:Finalizer#5'),
    ('harmony-VanillaFixes.cs-SonigonVoiceUpdateGuardPatch.Finalizer-6', 'harmony:VanillaFixes.cs:SonigonVoiceUpdateGuardPatch.Finalizer#6(?)', 'VanillaFixes.cs:Finalizer#6'),
    ('harmony-VanillaFixes.cs-StaleProjectileSweepPatch.AfterMovePlayers', 'harmony:VanillaFixes.cs:StaleProjectileSweepPatch.AfterMovePlayers(?)', 'VanillaFixes.cs:AfterMovePlayers'),
    ('harmony-VanillaFixes.cs-StaleProjectileSweepPatch.BeforeMovePlayers', 'harmony:VanillaFixes.cs:StaleProjectileSweepPatch.BeforeMovePlayers(?)', 'VanillaFixes.cs:BeforeMovePlayers'),
    ('harmony-VanillaFixes.cs-WeaponCooldownPhoenixDiagPatch.BeforeRevive-HealthHandler.Revive', 'harmony:VanillaFixes.cs:WeaponCooldownPhoenixDiagPatch.BeforeRevive(HealthHandler.Revive)', 'VanillaFixes.cs:BeforeRevive'),
    ('harmony-VanillaFixes.cs-WeaponCooldownPhoenixDiagPatch.Cleanup-25-HealthHandler.Revive', 'harmony:VanillaFixes.cs:WeaponCooldownPhoenixDiagPatch.Cleanup#25(HealthHandler.Revive)', 'VanillaFixes.cs:Cleanup#25'),
    ('reflection-ApiClient.cs-UnlockAchievement', 'reflection:ApiClient.cs:UnlockAchievement', 'ApiClient.cs:UnlockAchievement'),
    ('reflection-CombatEvidenceCore.cs-Empty', 'reflection:CombatEvidenceCore.cs:Empty', 'CombatEvidenceCore.cs:Empty'),
    ('reflection-CombatEvidenceCore.cs-TargetBounce', 'reflection:CombatEvidenceCore.cs:TargetBounce', 'CombatEvidenceCore.cs:TargetBounce'),
    ('reflection-Plugin.cs-OnJoinedRoom', 'reflection:Plugin.cs:OnJoinedRoom', 'Plugin.cs:OnJoinedRoom'),
    ('reflection-Plugin.cs-OnPlayerEnteredRoom', 'reflection:Plugin.cs:OnPlayerEnteredRoom', 'Plugin.cs:OnPlayerEnteredRoom'),
    ('unity-DamageNumbers.cs-DamageNumberDriver.Update', 'unity:DamageNumbers.cs:DamageNumberDriver.Update', 'DamageNumbers.cs:Update'),
    ('unity-HealBarOverlay.cs-HealBarOverlay.LateUpdate', 'unity:HealBarOverlay.cs:HealBarOverlay.LateUpdate', 'HealBarOverlay.cs:LateUpdate'),
    ('unity-HealBarOverlay.cs-HealBarOverlay.OnEnable', 'unity:HealBarOverlay.cs:HealBarOverlay.OnEnable', 'HealBarOverlay.cs:OnEnable'),
    ('unity-MusicEngine.cs-MusicEngineHost.Awake', 'unity:MusicEngine.cs:MusicEngineHost.Awake', 'MusicEngine.cs:Awake'),
    ('unity-MusicEngine.cs-MusicEngineHost.OnDestroy', 'unity:MusicEngine.cs:MusicEngineHost.OnDestroy', 'MusicEngine.cs:OnDestroy'),
    ('unity-MusicEngine.cs-MusicEngineHost.Update', 'unity:MusicEngine.cs:MusicEngineHost.Update', 'MusicEngine.cs:Update'),
    ('unity-NativeUI.cs-ClickHandler.Update', 'unity:NativeUI.cs:ClickHandler.Update', 'NativeUI.cs:Update'),
    ('unity-NativeUI.cs-FfaRecentGraphDrawer.OnGUI-1', 'unity:NativeUI.cs:FfaRecentGraphDrawer.OnGUI#1', 'NativeUI.cs:OnGUI#1'),
    ('unity-NativeUI.cs-OneVTwoHoverDrawer.OnGUI-2', 'unity:NativeUI.cs:OneVTwoHoverDrawer.OnGUI#2', 'NativeUI.cs:OnGUI#2'),
    ('unity-Plugin.cs-CompetitiveRoundsBehaviour.OnDestroy', 'unity:Plugin.cs:CompetitiveRoundsBehaviour.OnDestroy', 'Plugin.cs:OnDestroy'),
    ('unity-Plugin.cs-CompetitiveRoundsBehaviour.OnGUI', 'unity:Plugin.cs:CompetitiveRoundsBehaviour.OnGUI', 'Plugin.cs:OnGUI'),
    ('unity-Plugin.cs-CompetitiveRoundsBehaviour.Update-2', 'unity:Plugin.cs:CompetitiveRoundsBehaviour.Update#2', 'Plugin.cs:Update#2'),
    ('unity-Plugin.cs-Plugin.Awake-1', 'unity:Plugin.cs:Plugin.Awake#1', 'Plugin.cs:Awake#1'),
    ('unity-Plugin.cs-QueueRoomJoiner.Update-1', 'unity:Plugin.cs:QueueRoomJoiner.Update#1', 'Plugin.cs:Update#1'),
    ('unity-TeamColorIdentity.cs-TeamColorNametagTint.Update', 'unity:TeamColorIdentity.cs:TeamColorNametagTint.Update', 'TeamColorIdentity.cs:Update'),
    ('unity-VanillaFixes.cs-PlayerNicknameLabelRefresher.OnEnable', 'unity:VanillaFixes.cs:PlayerNicknameLabelRefresher.OnEnable', 'VanillaFixes.cs:OnEnable'),
    ('unity-VanillaFixes.cs-PlayerNicknameRepairDriver.Update', 'unity:VanillaFixes.cs:PlayerNicknameRepairDriver.Update', 'VanillaFixes.cs:Update'),
]
PIN5 = "backend/tests/test_keybind_surfaces.py::test_h1_fix5_each_unresolved_end_is_pinned_in_source[%s]"


def test_h1_fix5_the_end_table_is_every_unresolved_end_beyond_the_four(attach4):
    st, cman, att, aman = attach4
    names = [n for i, n, m in FIX5_ENDS]
    assert len(names) == len(set(names)) == len({i for i, n, m in FIX5_ENDS}) == 1141
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
