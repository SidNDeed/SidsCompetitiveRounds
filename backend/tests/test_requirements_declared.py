"""Every package the api and its tests import is declared (small docket item d).

The api image installs backend/api/requirements.lock, resolved from
backend/api/requirements.txt. A test seat installs
backend/tests/requirements-test.txt, which takes the api file first. On
2026-10-17 a seat built from those files alone (the laptop) failed 18 route
tests on `import httpx`: the tests imported httpx and PyYAML and no file
declared either. The VM seat carried both as hand installs and the LXC seats
inherited them through a lock taken from the VM's pip freeze, so only a seat
built from the repository's files showed it.

Required behaviour: every top-level module that a file under backend/api or
backend/tests imports, and that is neither the standard library nor a module
of this repository, is provided by a distribution one of the two files
declares BY NAME, unless the import is optional:

  * guarded: inside a try whose handler catches the failed import, or the
    file calls pytest.importorskip for that module;
  * NOT_REACHED: an unguarded import in a script the suite never loads (not
    a test module, imported by no scanned file), listed with the reason; the
    entry fails when either stops being true.

A distribution imported directly but reached only through a declared one
(fastapi brings starlette) is listed in THROUGH, and that claim is checked
against the installed metadata rather than trusted.

Controls (#391): the scanner reports a bare import and skips a guarded one
(synthetic sources); taking httpx or PyYAML out of the declared names makes
the check report exactly that module with its importing files, which is the
2026-10-17 finding; taking out a declared distribution that nothing imports
directly leaves the check green.
"""

import ast
import os
import re
import sys
from importlib import metadata
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
REPO = BACKEND.parent
API_REQ = BACKEND / "api" / "requirements.txt"
TEST_REQ = HERE / "requirements-test.txt"
BOT_DOCKERFILE = BACKEND / "Dockerfile.bot"
SCANNED = (BACKEND / "api", HERE)
# The directories that hold the repository's own Python.
LOCAL_ROOTS = (BACKEND, REPO / "scripts", REPO / "tools")
SKIP_DIRS = {"__pycache__", ".pytest_cache"}

# Import name -> distribution name, where the two differ.
DISTRIBUTION = {"yaml": "PyYAML", "PIL": "pillow", "_pytest": "pytest", "discord": "discord.py"}
# Imported directly, declared only through the named declared distribution.
THROUGH = {"starlette": "fastapi"}
# (module, script under backend/) -> why the suite never loads that import.
NOT_REACHED = {
    ("UnityPy", "tests/reproduce_337_theme_color.py"):
        "a reproduction script run by hand against a game install; "
        "test_pc_card_themes.py uses it only when importlib.util.find_spec finds UnityPy",
}
GUARD_ERRORS = {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"}


def _norm(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared(path):
    """Distribution names a requirements file declares by name (options such
    as -r and --hash are not names)."""
    out = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", line)
        assert m, (path.name, raw)
        out.add(_norm(m.group(0)))
    return out


def _pins(text):
    out = {}
    for m in re.finditer(r"(?m)^\s*([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;#]+)", text):
        out[_norm(m.group(1))] = m.group(2)
    return out


def _local_names():
    """Every module name the repository's own Python provides (a test may put
    any of these directories on sys.path; a directory may be a namespace
    package)."""
    names = set()
    for top in LOCAL_ROOTS:
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            names.add(os.path.basename(root))
            names.update(f[:-3] for f in files if f.endswith(".py"))
    return names


def _parents(tree):
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


def _guarded(node, parent):
    """True when an enclosing try catches the failed import."""
    child = node
    while child in parent:
        anc = parent[child]
        if isinstance(anc, ast.Try) and any(child is s for s in anc.body):
            for h in anc.handlers:
                if h.type is None:
                    return True
                kinds = h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]
                if any(isinstance(k, ast.Name) and k.id in GUARD_ERRORS for k in kinds):
                    return True
        child = anc
    return False


def imports_of(source):
    """{top-level module: guarded?} for every absolute import in `source`; a
    module imported both ways counts as unguarded."""
    tree = ast.parse(source)
    parent = _parents(tree)
    skipped = {n.args[0].value.split(".")[0] for n in ast.walk(tree)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "importorskip" and n.args
               and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)}
    out = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods = [a.name.split(".")[0] for a in n.names]
        elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
            mods = [n.module.split(".")[0]]
        else:
            continue
        g = _guarded(n, parent)
        for m in mods:
            out[m] = out.get(m, True) and (g or m in skipped)
    return out


def _scan():
    """{file under backend/: imports_of(file)} for every scanned file."""
    out = {}
    for top in SCANNED:
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith(".py"):
                    p = Path(root) / f
                    out[p.relative_to(BACKEND).as_posix()] = imports_of(
                        p.read_text(encoding="utf-8"))
    return out


def third_party(scan):
    """{module: [files]} for every unguarded, non-local, non-stdlib import."""
    skip = set(sys.stdlib_module_names) | _local_names() | {"__future__"}
    found = {}
    for rel, mods in scan.items():
        for mod, guarded in mods.items():
            if not guarded and mod not in skip:
                found.setdefault(mod, []).append(rel)
    return {m: sorted(f) for m, f in found.items()}


def _requires(dist):
    """Normalized names `dist` requires outside any extra."""
    out = set()
    for req in metadata.requires(dist) or []:
        name, _sep, marker = req.partition(";")
        if "extra" in marker:
            continue
        out.add(_norm(re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", name.strip()).group(0)))
    return out


def undeclared(found, declared):
    """{module: [files]} for each needed import no declared name provides."""
    missing = {}
    for mod, files in sorted(found.items()):
        needed = [f for f in files if (mod, f) not in NOT_REACHED]
        if not needed:
            continue
        dist = _norm(DISTRIBUTION.get(mod, mod))
        if dist in declared:
            continue
        via = THROUGH.get(mod)
        if via and _norm(via) in declared and dist in _requires(via):
            continue
        missing[mod] = needed
    return missing


SCAN = _scan()
FOUND = third_party(SCAN)
DECLARED = _declared(API_REQ) | _declared(TEST_REQ)


def test_the_test_file_takes_the_api_requirements_first():
    reqs = [ln.strip() for ln in TEST_REQ.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]
    assert reqs[0] == "-r ../api/requirements.txt", reqs[:2]
    assert (TEST_REQ.parent / "../api/requirements.txt").resolve() == API_REQ.resolve()


def test_the_test_only_packages_are_pinned_once():
    pins = _pins(TEST_REQ.read_text(encoding="utf-8"))
    assert {"pytest", "httpx", "pyyaml", "discord-py"} <= set(pins), pins
    assert not set(pins) & _declared(API_REQ), set(pins) & _declared(API_REQ)


def test_discord_py_matches_the_bot_image():
    # test_leaderboard_boards.py drives the real library the bot runs
    bot = _pins(BOT_DOCKERFILE.read_text(encoding="utf-8").replace("\\", " "))
    mine = _pins(TEST_REQ.read_text(encoding="utf-8"))
    assert mine["discord-py"] == bot["discord-py"], (mine["discord-py"], bot.get("discord-py"))


def test_every_imported_package_is_declared_by_name():
    assert undeclared(FOUND, DECLARED) == {}


def test_every_not_reached_entry_is_current():
    for mod, rel in NOT_REACHED:
        assert rel in SCAN and mod in SCAN[rel], (mod, rel, "no longer imported there")
        assert SCAN[rel][mod] is False, (mod, rel, "now guarded: drop the entry")
        assert not Path(rel).name.startswith("test_"), (rel, "collected by pytest")
        stem = Path(rel).stem
        assert not [r for r, mods in SCAN.items() if stem in mods], (rel, "imported")


def test_the_scanner_reports_a_bare_import_and_skips_a_guarded_one():
    src = ("import alpha_pkg\n"
           "from beta_pkg.sub import x\n"
           "try:\n    import gamma_pkg\nexcept ImportError:\n    gamma_pkg = None\n"
           "try:\n    import delta_pkg\nexcept (ValueError, ModuleNotFoundError):\n    pass\n"
           "try:\n    import eps_pkg\nexcept ValueError:\n    pass\n"
           "def f():\n    import zeta_pkg\n"
           "def g():\n    pytest.importorskip('eta_pkg')\n    import eta_pkg.sub\n"
           "from . import local_thing\n")
    got = imports_of(src)
    assert got == {"alpha_pkg": False, "beta_pkg": False, "gamma_pkg": True,
                   "delta_pkg": True, "eps_pkg": False, "zeta_pkg": False,
                   "eta_pkg": True}, got


def test_the_17_oct_finding_turns_the_check_red():
    for dist, mod in (("httpx", "httpx"), ("pyyaml", "yaml")):
        assert mod in FOUND, mod                      # the suite imports it today
        missing = undeclared(FOUND, DECLARED - {dist})
        assert set(missing) == {mod}, (dist, missing)
        assert missing[mod] == FOUND[mod]


def test_an_inert_removal_keeps_the_check_green():
    imported = {_norm(DISTRIBUTION.get(m, m)) for m in FOUND}
    inert = sorted(d for d in DECLARED if d not in imported
                   and d not in {_norm(v) for v in THROUGH.values()})
    assert inert, "every declared distribution is imported directly"
    assert undeclared(FOUND, DECLARED - {inert[0]}) == {}
