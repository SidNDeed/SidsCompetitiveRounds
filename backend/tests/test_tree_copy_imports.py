"""Every test that copies test modules into a tree takes the list from
tree_copy_imports.local_test_imports (see that module for why).

A copying test is one whose source holds a call
shutil.copyfile(BACKEND / "tests" / <name>, ...) inside a for loop over the
names; that loop's iterable must be a call of local_test_imports. Planted
controls: a hand list is refused, and the closure adds a helper a copied
file imports.
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


def test_the_closure_adds_the_helpers_a_copied_file_imports():
    got = local_test_imports(("conftest.py", "test_team_series_report_dc.py"))
    assert got[:2] == ["conftest.py", "test_team_series_report_dc.py"]
    assert "ban_read_tables.py" in got
    assert "soft_check_standin.py" in local_test_imports(("test_ovt_abandoned_horizon.py",))
    # a name that is no module of the folder adds nothing
    assert local_test_imports(("no_such_file.py",)) == ["no_such_file.py"]
