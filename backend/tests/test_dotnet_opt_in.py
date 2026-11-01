"""Every test that invokes the dotnet CLI asks _dotnet_opt_in first.

`dotnet build` and `dotnet run` compile a project, which runs only where
building is opted into (_dotnet_opt_in.py says where). This module reads every
Python module under backend/tests and finds each function that reaches dotnet:
a call to a dotnet locator (`_dotnet()` / `dotnet()`), `shutil.which("dotnet")`,
or an argument list starting with the string "dotnet". The locator functions
themselves are exempt. Each such function must call require_dotnet_opt_in()
on a line before its first dotnet use, or its module must carry a pytestmark
built on dotnet_opt_in. The controls below show the reading finds a missing
gate and a gate placed after the use.
"""
import ast
from pathlib import Path

from _dotnet_opt_in import HARNESS_OPT_IN, dotnet_opt_in

TESTS = Path(__file__).resolve().parent
LOCATORS = {"_dotnet", "dotnet"}
GATE = "require_dotnet_opt_in"

# Modules known to invoke dotnet when this test was written; the reading must
# find at least these, so an empty or broken walk cannot pass.
KNOWN = {
    "test_client_avatar_defaults.py",
    "test_client_rules_harness.py",
    "test_emoji_matcher_harness.py",
    "test_faq_client_upload_caps.py",
    "test_ffa_assembly_client_structure.py",
    "test_h2h_rules_harness.py",
    "test_title_ladders_current_server_compat.py",
}


def _is_dotnet_use(node):
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name) and f.id in LOCATORS:
            return True
        if (isinstance(f, ast.Attribute) and f.attr == "which" and node.args
                and isinstance(node.args[0], ast.Constant) and node.args[0].value == "dotnet"):
            return True
    if isinstance(node, ast.List) and node.elts:
        first = node.elts[0]
        if isinstance(first, ast.Constant) and first.value == "dotnet":
            return True
    return False


def _is_gate(node):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == GATE)


def _module_mark_gated(tree):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            for sub in ast.walk(node.value):
                if (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
                        and sub.func.id == "dotnet_opt_in"):
                    return True
    return False


def ungated(source):
    """(uses dotnet, [function names that use it with no gate before the use])."""
    tree = ast.parse(source)
    marked = _module_mark_gated(tree)
    uses_any = False
    bad = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or fn.name in LOCATORS:
            continue
        uses = [n.lineno for n in ast.walk(fn) if _is_dotnet_use(n)]
        if not uses:
            continue
        uses_any = True
        gates = [n.lineno for n in ast.walk(fn) if _is_gate(n)]
        if not marked and not (gates and min(gates) < min(uses)):
            bad.append(fn.name)
    return uses_any, bad


def test_every_dotnet_use_under_backend_tests_asks_the_opt_in_first():
    found, problems = set(), {}
    for p in sorted(TESTS.rglob("*.py")):
        if "_out" in p.parts or "__pycache__" in p.parts:
            continue
        uses, bad = ungated(p.read_text(encoding="utf-8"))
        if uses:
            found.add(p.name)
        if bad:
            problems[str(p.relative_to(TESTS))] = bad
    assert KNOWN <= found, "the reading missed modules known to use dotnet: %s" % sorted(KNOWN - found)
    assert not problems, "these functions reach dotnet before require_dotnet_opt_in(): %s" % problems


def test_the_reading_finds_a_missing_or_late_gate():
    missing = 'def f():\n    exe = _dotnet()\n    run([exe, "build"])\n'
    late = 'def f():\n    exe = dotnet()\n    require_dotnet_opt_in()\n'
    bare = 'def f():\n    run(["dotnet", "build", "x.csproj"])\n'
    which = 'def f():\n    if shutil.which("dotnet") is None:\n        pass\n'
    good = 'def f():\n    require_dotnet_opt_in()\n    exe = _dotnet()\n'
    marked = ('pytestmark = [pytest.mark.skipif(dotnet_opt_in() is None, reason="x")]\n'
              'def f():\n    run(["dotnet", "build"])\n')
    assert ungated(missing) == (True, ["f"])
    assert ungated(late) == (True, ["f"])
    assert ungated(bare) == (True, ["f"])
    assert ungated(which) == (True, ["f"])
    assert ungated(good) == (True, [])
    assert ungated(marked) == (True, [])
    assert ungated("def f():\n    return 1\n") == (False, [])


def test_the_opt_in_is_the_seat_runner_or_the_explicit_variable():
    assert dotnet_opt_in({}) is None
    assert dotnet_opt_in({"SCR_DECOMPILED_DIR": "C:/decompiled"}) is None
    assert dotnet_opt_in({HARNESS_OPT_IN: "0"}) is None
    assert dotnet_opt_in({HARNESS_OPT_IN: "1"})
    assert dotnet_opt_in({"SCR_DECOMPILED_DIR": "/seat/stage/decompiled"})
