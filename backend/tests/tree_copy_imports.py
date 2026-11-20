"""The test modules a copied tree needs: the named files of backend/tests and
every module of backend/tests they import, transitively.

The /health marker tests run some live tests from a copy of backend/ (so the
controls they plant never touch the tree a running suite reads). Each named
the test files to copy by hand, and a copied file that imports a helper
module of backend/tests which the list did not name fails in the copy at
import (bans part 2a added soft_check_standin.py and ban_read_tables.py to
copied files' imports). The copy list is now derived: local_test_imports
reads each file's import statements (its syntax tree, every Import and
ImportFrom at any depth) and adds every name that is a .py file of
backend/tests. test_tree_copy_imports.py checks that every test which copies
test modules into a tree takes its list from here.
"""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def _imported_modules(path):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module.split(".")[0]


def local_test_imports(names, tests_dir=HERE):
    """`names` (file names in tests_dir), in their order, then every module
    of tests_dir that they import, transitively, in sorted order."""
    out = list(names)
    seen = set(out)
    todo = list(out)
    extra = set()
    while todo:
        name = todo.pop()
        path = os.path.join(tests_dir, name)
        if not name.endswith(".py") or not os.path.isfile(path):
            continue
        for mod in _imported_modules(path):
            fname = mod + ".py"
            if fname not in seen and os.path.isfile(os.path.join(tests_dir, fname)):
                seen.add(fname)
                extra.add(fname)
                todo.append(fname)
    return out + sorted(extra)
