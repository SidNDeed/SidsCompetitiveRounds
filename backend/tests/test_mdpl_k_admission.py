"""MDPL class K: rule K's store census admits by hand the account deletion's two arming forms (the integrator's
ruling of 17 Nov 2026 12:03:04Z, Q1).

closed_walk.K_ADMITTED_STORES holds two rows: main.py's `setattr(db, name, fn)` in _deletion_arm_every_statement,
and `delattr(db, name)` in that function's undo. The census reads the names each form stores from the code at walk
time (the keys of the function's dict `installed`) and records them as stores of those names.

1. THE ROWS. Each row names main.py, its function and place, its form, the dict and the reviewed count, and carries
   a reason. No row holds a stored name. Over main.py as it stands, the census refuses nothing and records the
   names it reads at the two forms' lines. Those names are the four the review read (execute, flush, commit and
   begin_nested): this test pins them, the admission does not.
2. A MUTANT PER SITE. Without one row, the census refuses that row's form at its line, as it does today, and the
   other form stays admitted. With both rows it refuses nothing (the control).
3. THE CONTROLS ASKED, each plant with a twin (the same place, an edit that leaves the reading whole):
   - a third dynamic setattr in main.py stays refused, both in another function and as a second copy in the same
     loop;
   - the admission without its names refuses as today: rows whose dict the function never binds give exactly the
     refusals of the module read with no file;
   - a fifth key, a missing key, a key that is not a constant, and a use of the dict the reading does not account
     for each make both forms refused;
   - a rule K-m read of a method named flush is refused by the recorded store. The class is planted in a module
     file named main.py that holds the arming function as main.py has it. The same read of a method named
     flushed is not refused. With no admission row, the read is refused as today, by the census's refusal.
4. MDPL CLASS K2 (the ruling of 17 Nov 2026 14:10:47Z, 1): the rows read `installed` and the loop's `name`
   through the resolver, so a binding of either name in any form the resolver knows refuses both rows. One plant
   per form and place, each with a twin (the same edit under another identifier) that stays admitted; and a
   check that each plant adds exactly one binding and that the plants cover every kind the resolver's _collect
   gives a plain name.
Every part reads main.py's source and imports closed_walk; none imports main."""
import ast
import importlib.util
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import closed_walk as cw  # noqa: E402
from closed_walk import Unclassified  # noqa: E402

MAIN = os.path.normpath(os.path.join(HERE, "..", "api", "main.py"))
FN = "_deletion_arm_every_statement"
SET_FORM = "setattr(db, name, fn)"
DEL_FORM = "delattr(db, name)"
REVIEWED = {"execute", "flush", "commit", "begin_nested"}
TODAY = "a %s whose name no constant gives"


@pytest.fixture(autouse=True)
def _fresh_census_cache(monkeypatch):
    monkeypatch.setattr(cw, "_STORE_CENSUS", {})


def _source():
    with open(MAIN, encoding="utf-8") as fh:
        return fh.read()


def _census(tree, path=MAIN):
    cw._STORE_CENSUS.clear()
    return object.__new__(cw.Bindings)._store_census(tree, path)


def _fn(tree):
    got = [st for st in tree.body if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef))
           and st.name == FN]
    assert len(got) == 1
    return got[0]


def _form_line(tree, form):
    got = [c.lineno for c in ast.walk(_fn(tree)) if isinstance(c, ast.Call) and ast.unparse(c) == form]
    assert len(got) == 1, form
    return got[0]


def _edit(src, anchor, new_lines=(), replace=False):
    """`src` with `new_lines` put after the one line equal to `anchor`, or in its place."""
    lines = src.split("\n")
    hits = [i for i, line in enumerate(lines) if line == anchor]
    assert len(hits) == 1, (anchor, len(hits))
    i = hits[0]
    lines[i:i + 1] = list(new_lines) if replace else [lines[i]] + list(new_lines)
    return "\n".join(lines)


def _both_refused(tree):
    return [(_form_line(tree, SET_FORM), TODAY % "setattr"), (_form_line(tree, DEL_FORM), TODAY % "delattr")]


# --- 1. the rows ----------------------------------------------------------------------------------------------

def test_k_rows_name_main_py_a_place_a_form_a_dict_a_count_and_a_reason():
    rows = cw.K_ADMITTED_STORES
    assert [r[3] for r in rows] == [SET_FORM, DEL_FORM]
    assert [r[2] for r in rows] == [FN, "undo"]
    for r in rows:
        assert len(r) == 7 and r[0] == "main.py" and r[1] == FN and r[4] == "installed" and r[5] == 4
        assert isinstance(r[6], str) and len(r[6]) > 40
    assert not REVIEWED & {x for r in rows for x in r if isinstance(x, str)}


def test_k_main_py_census_refuses_nothing_and_records_the_names_read():
    tree = ast.parse(_source())
    c = _census(tree)
    assert c["refused"] == []
    s, d = _form_line(tree, SET_FORM), _form_line(tree, DEL_FORM)
    for name in sorted(REVIEWED):
        assert s in c["stores"][name] and d in c["stores"][name], name
    got = cw._k_admitted(tree, MAIN)
    assert sorted(sorted(v) for v in got.values()) == [sorted(REVIEWED)] * 2


def test_k_the_module_read_with_no_file_or_another_file_name_is_refused_as_today():
    tree = ast.parse(_source())
    assert _census(tree, None)["refused"] == _both_refused(tree)
    assert _census(tree, os.path.join(HERE, "main_copy.py"))["refused"] == _both_refused(tree)


# --- 2. a mutant per site -------------------------------------------------------------------------------------

@pytest.mark.parametrize("site", [0, 1], ids=["setattr", "delattr"])
def test_k_each_site_is_admitted_by_its_own_row(site, monkeypatch):
    tree = ast.parse(_source())
    refusals = _both_refused(tree)
    rows = cw.K_ADMITTED_STORES
    monkeypatch.setattr(cw, "K_ADMITTED_STORES", tuple(r for i, r in enumerate(rows) if i != site))
    c = _census(tree)
    assert c["refused"] == [refusals[site]]
    other = refusals[1 - site][0]
    assert all(other in c["stores"][n] for n in REVIEWED)
    monkeypatch.setattr(cw, "K_ADMITTED_STORES", rows)
    assert _census(tree)["refused"] == []


# --- 3. the controls asked ------------------------------------------------------------------------------------

ELSEWHERE = ("", "", "def _k_plant(db, extra):", "    for name, fn in extra.items():", "        setattr(db, %s, fn)")


@pytest.mark.parametrize("twin", [False, True], ids=["plant", "twin"])
def test_k_a_third_dynamic_setattr_in_another_function_stays_refused(twin):
    src = _source().rstrip("\n")
    lines = list(ELSEWHERE)
    lines[-1] = lines[-1] % ('"rollback"' if twin else "name")
    tree = ast.parse(src + "\n".join(lines) + "\n")
    plant = len(src.split("\n")) + len(lines) - 1
    c = _census(tree)
    if twin:
        assert c["refused"] == [] and plant in c["stores"]["rollback"]
    else:
        assert c["refused"] == [(plant, TODAY % "setattr")]
    assert all(_form_line(tree, SET_FORM) in c["stores"][n] for n in REVIEWED)


@pytest.mark.parametrize("twin", [False, True], ids=["plant", "twin"])
def test_k_a_second_copy_in_the_same_loop_refuses_both_copies(twin):
    copy = '        setattr(db, "rollback", fn)' if twin else "        " + SET_FORM
    src = _edit(_source(), "        " + SET_FORM, [copy])
    tree = ast.parse(src)
    c = _census(tree)
    d = _form_line(tree, DEL_FORM)
    if twin:
        assert c["refused"] == []
    else:
        hits = sorted(k.lineno for k in ast.walk(_fn(tree)) if isinstance(k, ast.Call) and ast.unparse(k) == SET_FORM)
        assert len(hits) == 2 and c["refused"] == [(hits[0], TODAY % "setattr"), (hits[1], TODAY % "setattr")]
    assert all(d in c["stores"][n] for n in REVIEWED)


def test_k_the_admission_without_its_names_refuses_as_today(monkeypatch):
    tree = ast.parse(_source())
    rows = tuple(r[:4] + ("absent",) + r[5:] for r in cw.K_ADMITTED_STORES)
    monkeypatch.setattr(cw, "K_ADMITTED_STORES", rows)
    got = _census(tree)["refused"]
    assert got == _both_refused(tree) == _census(tree, None)["refused"]


KEY_PLANTS = {
    # name: (anchor, new lines, replace?, twin's new lines)
    "fifth key": ('        installed["begin_nested"] = begin_nested', ['    installed["rollback"] = commit'], False,
                  ['    installed["commit"] = commit']),
    "missing key": ('        installed["commit"] = commit', ["        pass"], True,
                    ['        installed["commit"] = flush']),
    "key not a constant": ('        installed["flush"] = flush', ["        installed[key] = flush"], True,
                           ['        installed[("flush")] = flush']),
    "a use the reading does not account for": ('        installed["begin_nested"] = begin_nested',
                                               ["    installed.update(rollback=commit)"], False,
                                               ["    for _k, _v in installed.items():", "        pass"]),
}


@pytest.mark.parametrize("twin", [False, True], ids=["plant", "twin"])
@pytest.mark.parametrize("plant", sorted(KEY_PLANTS))
def test_k_the_dict_keys_are_read_from_the_code(plant, twin):
    anchor, new, replace, twin_new = KEY_PLANTS[plant]
    tree = ast.parse(_edit(_source(), anchor, twin_new if twin else new, replace))
    c = _census(tree)
    if twin:
        assert c["refused"] == [], plant
        assert all(_form_line(tree, SET_FORM) in c["stores"][n] for n in REVIEWED)
    else:
        assert c["refused"] == _both_refused(tree), plant


# --- 4. MDPL class K2: every binding form of either name refuses both rows -----------------------------------
#
# The ruling of 17 Nov 2026 14:10:47Z, 1: a row reads `installed` and the loop's `name` through the resolver
# (Bindings over the function, the place and the loop), so a binding of either name in any form the resolver knows
# refuses both rows: assignment of each kind, for and with targets, except-as, import-as, def and class names,
# parameters of the arming function and of every nested function, global and nonlocal, the walrus, comprehension
# targets and match captures. Each plant is red under class K's reading where K saw no ast.Name; its twin makes the
# same edit under another identifier (installed2, name2), which the reading must leave admitted. A plant's lines
# spell its identifier @X. `installed` plants stand in the arming function's body after the dict is built (no plant
# reads the name); `name` plants stand inside the setattr loop before the setattr, or in undo.

_AFTER_DICT = '        installed["begin_nested"] = begin_nested'
_SET_LINE = "        " + SET_FORM
_ARM_DEF = "def _deletion_arm_every_statement(db, deadline):"
_UNDO_DEF = "    def undo():"
_UNDO_LOOP_IF = "            if mine.get(name) is fn:"
_UNDO_FIRST = '        mine = getattr(db, "__dict__", {})'


def _forms(pad, value):
    """The statement-level binding forms of @X, each as lines at indent `pad`, `value` the bound value's text."""
    p, q, r = pad, pad + "    ", pad + "        "
    return {
        "assign": [p + "@X = " + value],
        "augmented assign": [p + "@X += " + value],
        "annotated assign": [p + "@X: object = " + value],
        "delete": [p + "del @X"],
        "for target": [p + "for @X in ():", q + "pass"],
        "with target": [p + "with _k_cm() as @X:", q + "pass"],
        "except as": [p + "try:", q + "pass", p + "except Exception as @X:", q + "pass"],
        "import as": [p + "import collections as @X"],
        "from import as": [p + "from collections import OrderedDict as @X"],
        "def name": [p + "def @X():", q + "pass"],
        "async def name": [p + "async def @X():", q + "pass"],
        "class name": [p + "class @X:", q + "pass"],
        "lambda parameter": [p + "_k_f = lambda @X: 0"],
        "nested function parameter": [p + "def _k_g(@X=None):", q + "pass"],
        "nested function *parameter": [p + "def _k_g(*@X):", q + "pass"],
        "nested function **parameter": [p + "def _k_g(**@X):", q + "pass"],
        "nested function keyword-only parameter": [p + "def _k_g(*, @X=None):", q + "pass"],
        "nested function positional-only parameter": [p + "def _k_g(@X=None, /):", q + "pass"],
        "global in a nested function": [p + "def _k_g():", q + "global @X"],
        "nonlocal in a nested function": [p + "def _k_g():", q + "nonlocal @X"],
        "walrus": [p + "(@X := " + value + ")"],
        "list comprehension target": [p + "[0 for @X in ()]"],
        "dict comprehension target": [p + "{0: 0 for @X in ()}"],
        "generator target": [p + "sum(0 for @X in ())"],
        "match capture": [p + "match 0:", q + "case @X:", r + "pass"],
        "match as": [p + "match 0:", q + "case 1 as @X:", r + "pass"],
        "match star": [p + "match 0:", q + "case [*@X]:", r + "pass"],
        "match mapping rest": [p + "match 0:", q + "case {**@X}:", r + "pass"],
    }


# plant label: (the identifier, the anchor line, the lines put after it or in its place, in its place?)
BINDING_PLANTS = {}
for _label, _lines in _forms("    ", "{}").items():
    BINDING_PLANTS["installed: " + _label] = ("installed", _AFTER_DICT, _lines, False)
for _label, _lines in _forms("        ", "'flush'").items():
    BINDING_PLANTS["name in the setattr loop: " + _label] = ("name", _SET_LINE, _lines + [_SET_LINE], True)
for _ident in ("installed", "name"):
    BINDING_PLANTS[_ident + ": parameter of the arming function"] = (
        _ident, _ARM_DEF, ["def _deletion_arm_every_statement(db, deadline, @X=None):"], True)
    BINDING_PLANTS[_ident + ": parameter of undo"] = (_ident, _UNDO_DEF, ["    def undo(@X=None):"], True)
    BINDING_PLANTS[_ident + ": global in undo"] = (_ident, _UNDO_FIRST, ["        global @X"], False)
    BINDING_PLANTS[_ident + ": nonlocal in undo"] = (_ident, _UNDO_FIRST, ["        nonlocal @X"], False)
BINDING_PLANTS["name in undo's loop: import as"] = (
    "name", _UNDO_LOOP_IF, ["            import os as @X", _UNDO_LOOP_IF], True)
BINDING_PLANTS["name in undo's loop: except as"] = (
    "name", _UNDO_LOOP_IF, ["            try:", "                pass", "            except Exception as @X:",
                            "                pass", _UNDO_LOOP_IF], True)


@pytest.mark.parametrize("twin", [False, True], ids=["plant", "twin"])
@pytest.mark.parametrize("plant", sorted(BINDING_PLANTS))
def test_k2_a_binding_of_either_name_in_any_form_refuses_both_rows(plant, twin):
    ident, anchor, lines, replace = BINDING_PLANTS[plant]
    spelled = ident + "2" if twin else ident
    tree = ast.parse(_edit(_source(), anchor, [ln.replace("@X", spelled) for ln in lines], replace))
    c = _census(tree)
    if twin:
        assert c["refused"] == [], plant
        assert all(_form_line(tree, SET_FORM) in c["stores"][n] and _form_line(tree, DEL_FORM) in c["stores"][n]
                   for n in REVIEWED), plant
    else:
        assert c["refused"] == _both_refused(tree), plant


def test_k2_the_plants_cover_every_binding_form_the_resolver_collects():
    """Each plant adds exactly one binding of its identifier to the resolver's table over the arming function, and
    together they cover every kind the resolver's _collect gives a plain name: param, local, def, import and global
    (a mutation is the dict's own item store, read by the key plants above)."""
    src = _source()
    base = cw.Bindings(None, fn=_fn(ast.parse(src)))
    kinds = set()
    for plant, (ident, anchor, lines, replace) in sorted(BINDING_PLANTS.items()):
        tree = ast.parse(_edit(src, anchor, [ln.replace("@X", ident) for ln in lines], replace))
        b = cw.Bindings(None, fn=_fn(tree))
        was = [k for k, _n in base.sites.get(ident, ())]
        now = [k for k, _n in b.sites.get(ident, ())]
        extra = list(now)
        for k in was:
            extra.remove(k)
        assert len(now) == len(was) + 1 and len(extra) == 1, (plant, was, now)
        kinds.add(extra[0])
    assert kinds == {"param", "local", "def", "import", "global"}, kinds


PLANT_CLASS = ("", "", "class KPlant:", "    def flush(self):", "        return 1", "",
               "    def flushed(self):", "        return 1", "")


def _plant_module(tmp_path, monkeypatch):
    """A module file named main.py holding main.py's arming function, as its source has it, and class KPlant."""
    src = _source()
    seg = ast.get_source_segment(src, _fn(ast.parse(src)))
    d = tmp_path / "kplant"
    d.mkdir()
    path = d / "main.py"
    path.write_text(seg + "\n" + "\n".join(PLANT_CLASS), encoding="utf-8")
    name = "mdpl_k_plant_main_%d" % id(tmp_path)
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)
    line = _form_line(ast.parse(path.read_text(encoding="utf-8")), SET_FORM)
    return mod, line


def test_k_m_read_of_a_stored_name_is_refused_by_the_recorded_store(tmp_path, monkeypatch):
    mod, line = _plant_module(tmp_path, monkeypatch)
    b = object.__new__(cw.Bindings)
    assert b.k_method(mod.KPlant, mod, "flushed", 7) is None
    with pytest.raises(Unclassified) as e:
        b.k_method(mod.KPlant, mod, "flush", 7)
    assert e.value.args[0][0] == 7
    assert e.value.args[0][1].startswith("an attribute store of the name flush at line %d," % line)


def test_k_m_read_with_no_admission_is_refused_as_today(tmp_path, monkeypatch):
    mod, line = _plant_module(tmp_path, monkeypatch)
    monkeypatch.setattr(cw, "K_ADMITTED_STORES", ())
    b = object.__new__(cw.Bindings)
    with pytest.raises(Unclassified) as e:
        b.k_method(mod.KPlant, mod, "flushed", 7)
    assert e.value.args[0] == (7, "%s at line %d, a store rule K's census does not read" % (TODAY % "setattr",
                                                                                          line))
