"""Every test that copies test modules into a tree takes the list from
tree_copy_imports.local_test_imports (see that module for why).

A copying test is one whose source holds a call
shutil.copyfile(BACKEND / "tests" / <name>, ...) inside a for loop over the
names; that loop's iterable must be a call of local_test_imports. A test
module copied into the tests folder outside that loop (a test copying
itself) must import no module of the tests folder. Planted controls: a hand
list is refused, a self-copy with a helper import is refused, and the
closure adds a helper a copied file imports.
"""
import ast
import os

from tree_copy_imports import local_test_imports

HERE = os.path.dirname(os.path.abspath(__file__))


def _copies_test_modules(call):
    if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
            and call.func.attr == "copyfile" and call.args):
        return False
    src = ast.unparse(call.args[0])
    return src.startswith('BACKEND / "tests" /') or src.startswith("BACKEND / 'tests' /")


def _failures(src, name):
    out = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.For) and any(_copies_test_modules(c) for b in node.body
                                             for c in ast.walk(b)):
            it = node.iter
            if not (isinstance(it, ast.Call) and isinstance(it.func, ast.Name)
                    and it.func.id == "local_test_imports"):
                out.append((name, node.lineno))
    return out


def _copiers():
    found = {}
    for n in sorted(os.listdir(HERE)):
        if n.startswith("test_") and n.endswith(".py"):
            with open(os.path.join(HERE, n), encoding="utf-8") as fh:
                src = fh.read()
            if "copyfile" in src:
                found[n] = src
    return found


def test_every_tree_copy_of_test_modules_takes_the_derived_list():
    copiers = _copiers()
    loops = [(n, node) for n, src in copiers.items() for node in ast.walk(ast.parse(src))
             if isinstance(node, ast.For) and any(_copies_test_modules(c) for b in node.body
                                                  for c in ast.walk(b))]
    assert len(loops) >= 6, [n for n, _ in loops]
    assert [f for n, src in copiers.items() for f in _failures(src, n)] == []


def test_a_hand_list_is_refused():
    planted = ("def copy(tests):\n"
               "    for name in ('conftest.py', 'test_x.py'):\n"
               "        shutil.copyfile(BACKEND / 'tests' / name, tests / name)\n")
    assert _failures(planted, "planted") == [("planted", 2)]


_SELF_SOURCES = ("THIS", "pathlib.Path(__file__)", "pathlib.Path(__file__).resolve()")


def _walk_bodies(tree):
    """ids of every node inside a for loop over a local_test_imports call."""
    inside = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.For) and isinstance(node.iter, ast.Call)
                and isinstance(node.iter.func, ast.Name)
                and node.iter.func.id == "local_test_imports"):
            for b in node.body:
                inside.update(id(c) for c in ast.walk(b))
    return inside


def _outside_walk_failures(src, name, tests_dir=HERE):
    """A copy into the copied tree's tests folder made OUTSIDE the derived
    walk (a test copying itself) carries none of the copied file's imports.
    It is admitted only when the copied file imports no module of the tests
    folder; a source this census cannot name is refused. (FIX-3C: the two
    match hold and tournament fence markers imported tree_copy_imports and
    copied themselves outside the walk, so the copy failed at import.)"""
    tree = ast.parse(src)
    inside = _walk_bodies(tree)
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "copyfile" and len(node.args) >= 2
                and ast.unparse(node.args[1]).startswith("tests /")):
            continue
        if id(node) in inside:
            continue
        source = ast.unparse(node.args[0])
        if source in _SELF_SOURCES:
            copied = name
        elif (isinstance(node.args[0], ast.BinOp)
              and isinstance(node.args[0].right, ast.Constant)
              and source.startswith(('BACKEND / "tests" /', "BACKEND / 'tests' /"))):
            copied = node.args[0].right.value
        else:
            out.append((name, node.lineno, "unnamed source " + source))
            continue
        missing = local_test_imports((copied,), tests_dir)[1:]
        if missing:
            out.append((name, node.lineno, copied, missing))
    return out


def test_a_test_module_copied_outside_the_walk_imports_no_helper():
    copiers = _copiers()
    assert [f for n, src in copiers.items() for f in _outside_walk_failures(src, n)] == []
    # control: a marker that copies itself outside the walk and imports no
    # module of the tests folder is admitted, so the rule does not refuse
    # every self-copy
    src = copiers["test_health_ffa_exclusion_reasons_marker.py"]
    tree = ast.parse(src)
    outside = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
               and isinstance(n.func, ast.Attribute) and n.func.attr == "copyfile"
               and len(n.args) >= 2 and ast.unparse(n.args[1]).startswith("tests /")
               and id(n) not in _walk_bodies(tree)]
    assert len(outside) == 1


def test_the_two_markers_walk_themselves_and_the_base_shape_is_refused():
    """Mutant: each fixed marker put back in its base shape (itself left out
    of the walk and copied after it) is refused; the fixed file is admitted."""
    for name in ("test_health_match_hold_marker.py", "test_health_tournament_fence_marker.py"):
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            src = fh.read()
        fixed = 'local_test_imports(("conftest.py", "pc_themes_data.py", THIS.name))'
        assert src.count(fixed) == 1, name
        assert _outside_walk_failures(src, name) == []
        lines = src.splitlines(True)
        at = [i for i, ln in enumerate(lines) if fixed in ln]
        assert len(at) == 1, name
        indent = lines[at[0]][:len(lines[at[0]]) - len(lines[at[0]].lstrip())]
        base = (src.replace(fixed, 'local_test_imports(("conftest.py", "pc_themes_data.py"))')
                .replace('    return api / "main.py"',
                         indent + "shutil.copyfile(THIS, tests / THIS.name)\n"
                         '    return api / "main.py"', 1))
        got = _outside_walk_failures(base, name)
        assert len(got) == 1 and got[0][2] == name and "tree_copy_imports.py" in got[0][3], got


def test_a_planted_self_copy_with_a_helper_is_refused(tmp_path):
    (tmp_path / "helper_x.py").write_text("X = 1\n", encoding="utf-8")
    planted = ("import pathlib, shutil\n"
               "from helper_x import X\n"
               "THIS = pathlib.Path(__file__).resolve()\n"
               "def copy(tests):\n"
               "    for name in local_test_imports(('conftest.py',)):\n"
               "        shutil.copyfile(BACKEND / 'tests' / name, tests / name)\n"
               "    shutil.copyfile(THIS, tests / THIS.name)\n")
    (tmp_path / "test_planted.py").write_text(planted, encoding="utf-8")
    got = _outside_walk_failures(planted, "test_planted.py", str(tmp_path))
    assert got == [("test_planted.py", 7, "test_planted.py", ["helper_x.py"])], got
    # the same file with its helper import removed is admitted
    clean = planted.replace("from helper_x import X\n", "")
    (tmp_path / "test_planted.py").write_text(clean, encoding="utf-8")
    assert _outside_walk_failures(clean, "test_planted.py", str(tmp_path)) == []
    # a source the census cannot name is refused
    odd = clean.replace("shutil.copyfile(THIS,", "shutil.copyfile(other,")
    assert _outside_walk_failures(odd, "test_planted.py", str(tmp_path))[0][2].startswith("unnamed")


def test_the_closure_adds_the_helpers_a_copied_file_imports():
    got = local_test_imports(("conftest.py", "test_team_series_report_dc.py"))
    assert got[:2] == ["conftest.py", "test_team_series_report_dc.py"]
    assert "ban_read_tables.py" in got
    assert "soft_check_standin.py" in local_test_imports(("test_ovt_abandoned_horizon.py",))
    # a name that is no module of the folder adds nothing
    assert local_test_imports(("no_such_file.py",)) == ["no_such_file.py"]
