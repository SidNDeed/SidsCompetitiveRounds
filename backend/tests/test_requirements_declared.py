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

ZONE DATA, the dependency no import names (lesson 913). zoneinfo looks a key
up in TZPATH first and in the tzdata package second. Windows Python's
default TZPATH is empty, so unless PYTHONTZPATH names a zone database, every
ZoneInfo(key) there needs tzdata installed, UTC included (zoneinfo keeps no
built-in zone); tournaments.py builds ZoneInfo("America/Los_Angeles") at
import time, and the same 2026-10-17 laptop seat had 2 failures and 18
errors on it in its database test sets. So every file under backend/api or
backend/tests that constructs a ZoneInfo (ZoneInfo(key) or
ZoneInfo.no_cache(key), by any name zoneinfo was imported as, at import time
or inside a function) needs tzdata declared: by backend/api/requirements.txt
for a file under backend/api (the api runs on every seat), by either file for
a test. requirements.lock must carry the same version with one hash.
datetime.timezone.utc needs no zone data and is not a site. Controls: the
scanner on synthetic sources, the import-time site in tournaments.py found
today, and tzdata taken out of the declared names reporting exactly that
file.
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


def _importorskip_of(stmt):
    """The top-level package a STATEMENT `pytest.importorskip("pkg")` (bare,
    or its value assigned) skips on; None for any other statement. A call
    nested inside another statement (an `if`, an argument) is not one."""
    value = stmt.value if isinstance(stmt, (ast.Expr, ast.Assign, ast.AnnAssign)) else None
    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
            and value.func.attr == "importorskip" and value.args
            and isinstance(value.args[0], ast.Constant)
            and isinstance(value.args[0].value, str)):
        return value.args[0].value.split(".")[0]
    return None


def _skipped_before(node, parent, mod):
    """True when THIS import site is reached only after `mod` imported: a
    statement earlier in a block that encloses the site is
    pytest.importorskip(mod), so that scope stops before the site when the
    package is missing. Judged per site: an importorskip in one function
    guards nothing at module level or in another function."""
    child = node
    while child in parent:
        anc = parent[child]
        for field in ("body", "orelse", "finalbody"):
            block = getattr(anc, field, None)
            if not isinstance(block, list):
                continue
            for i, stmt in enumerate(block):
                if stmt is child:
                    if any(_importorskip_of(s) == mod for s in block[:i]):
                        return True
                    break
        child = anc
    return False


def imports_of(source):
    """{top-level module: guarded?} for every absolute import in `source`.
    Each import SITE is judged by its own guard (an enclosing try that
    catches the failed import, or an importorskip of the package earlier in
    an enclosing block); a module with any unguarded site counts as
    unguarded."""
    tree = ast.parse(source)
    parent = _parents(tree)
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
            out[m] = out.get(m, True) and (g or _skipped_before(n, parent, m))
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


API_LOCK = BACKEND / "api" / "requirements.lock"
ZONE_DATA = "tzdata"


def zone_sites(source):
    """[(line, import_time)] for every ZoneInfo construction in `source`:
    ZoneInfo(...) or ZoneInfo.no_cache(...), reached through any name the
    file bound from `zoneinfo` (`from zoneinfo import ZoneInfo as Z`,
    `import zoneinfo as z`). import_time: no enclosing def or lambda, so the
    import of the module runs it. A name ZoneInfo that zoneinfo did not
    provide is not a site."""
    tree = ast.parse(source)
    parent = _parents(tree)
    classes, modules = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module == "zoneinfo":
            classes.update(a.asname or a.name for a in n.names if a.name == "ZoneInfo")
        elif isinstance(n, ast.Import):
            modules.update(a.asname or a.name for a in n.names if a.name == "zoneinfo")

    def is_class(node):
        return ((isinstance(node, ast.Name) and node.id in classes)
                or (isinstance(node, ast.Attribute) and node.attr == "ZoneInfo"
                    and isinstance(node.value, ast.Name) and node.value.id in modules))

    out = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if not (is_class(f) or (isinstance(f, ast.Attribute) and f.attr == "no_cache"
                                and is_class(f.value))):
            continue
        child, import_time = n, True
        while child in parent:
            child = parent[child]
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                import_time = False
                break
        out.append((n.lineno, import_time))
    return sorted(out)


def _zone_scan():
    """{file under backend/: zone_sites(file)} for every scanned file with a site."""
    out = {}
    for top in SCANNED:
        for root, dirs, files in os.walk(top):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for f in files:
                if f.endswith(".py"):
                    p = Path(root) / f
                    sites = zone_sites(p.read_text(encoding="utf-8"))
                    if sites:
                        out[p.relative_to(BACKEND).as_posix()] = sites
    return out


def zone_data_missing(sites, api_declared, all_declared):
    """{file: sites} for each file that constructs a ZoneInfo while the file
    its code is installed from does not declare tzdata: the api file for
    backend/api, either file for backend/tests."""
    missing = {}
    for rel, found in sorted(sites.items()):
        need = api_declared if rel.startswith("api/") else all_declared
        if ZONE_DATA not in need:
            missing[rel] = found
    return missing


SCAN = _scan()
FOUND = third_party(SCAN)
DECLARED = _declared(API_REQ) | _declared(TEST_REQ)
ZONE_SITES = _zone_scan()


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


def test_an_importorskip_guards_only_the_sites_after_it_in_its_own_scope():
    """The SMALL-ABC-R1 MEDIUM: a guard elsewhere in the file does not guard
    a bare module-level import. Each form alone, then both together."""
    guarded_only = ("import pytest\n"
                    "def test_draw():\n"
                    "    pytest.importorskip('theta_pkg')\n"
                    "    import theta_pkg.image\n")
    assert imports_of(guarded_only)["theta_pkg"] is True
    bare_too = "import theta_pkg\n" + guarded_only
    assert imports_of(bare_too)["theta_pkg"] is False
    other_scope = ("import pytest\n"
                   "def a():\n    pytest.importorskip('theta_pkg')\n"
                   "def b():\n    import theta_pkg\n")
    assert imports_of(other_scope)["theta_pkg"] is False
    after_the_import = ("import pytest\n"
                        "def a():\n    import theta_pkg\n"
                        "    pytest.importorskip('theta_pkg')\n")
    assert imports_of(after_the_import)["theta_pkg"] is False
    conditional = ("import pytest\n"
                   "def a(x):\n    if x:\n        pytest.importorskip('theta_pkg')\n"
                   "    import theta_pkg\n")
    assert imports_of(conditional)["theta_pkg"] is False
    module_skip = ("import pytest\n"
                   "theta = pytest.importorskip('theta_pkg')\n"
                   "import theta_pkg\n"
                   "def a():\n    import theta_pkg.sub\n")
    assert imports_of(module_skip)["theta_pkg"] is True


def test_a_bare_import_beside_a_guarded_one_turns_the_census_red():
    """The finding's own case on the real file: a mandatory top-level
    `import matplotlib` added to test_discord_evidence_render.py, which keeps
    its function-local importorskip, is reported as undeclared; the file as
    it stands is not."""
    rel = "tests/test_discord_evidence_render.py"
    source = (BACKEND / rel).read_text(encoding="utf-8")
    assert SCAN[rel]["matplotlib"] is True, SCAN[rel].get("matplotlib")
    scan = dict(SCAN)
    scan[rel] = imports_of("import matplotlib\n" + source)
    assert scan[rel]["matplotlib"] is False
    missing = undeclared(third_party(scan), DECLARED)
    assert missing == {"matplotlib": [rel]}, missing
    assert undeclared(third_party(dict(SCAN)), DECLARED) == {}


def test_the_17_oct_finding_turns_the_check_red():
    for dist, mod in (("httpx", "httpx"), ("pyyaml", "yaml")):
        assert mod in FOUND, mod                      # the suite imports it today
        missing = undeclared(FOUND, DECLARED - {dist})
        assert set(missing) == {mod}, (dist, missing)
        assert missing[mod] == FOUND[mod]


def test_the_zone_scanner_finds_every_construction_form():
    src = ("import datetime\n"
           "from zoneinfo import ZoneInfo\n"
           "from zoneinfo import ZoneInfo as Z\n"
           "import zoneinfo as zi\n"
           "A = ZoneInfo('America/Los_Angeles')\n"
           "B = Z('UTC')\n"
           "C = zi.ZoneInfo.no_cache('Europe/Paris')\n"
           "U = datetime.timezone.utc\n"
           "def f(k):\n    return zi.ZoneInfo(k)\n"
           "g = lambda: ZoneInfo.no_cache('Asia/Tokyo')\n"
           "class K:\n    tz = Z('Etc/GMT')\n")
    assert zone_sites(src) == [(5, True), (6, True), (7, True), (10, False),
                               (11, False), (13, True)], zone_sites(src)
    # a ZoneInfo that zoneinfo did not provide, and zoneinfo.ZoneInfo.from_file
    # (no key lookup), are not sites
    other = ("from mytz import ZoneInfo\nX = ZoneInfo('UTC')\n"
             "import zoneinfo\nY = zoneinfo.ZoneInfo.from_file(open('f', 'rb'))\n")
    assert zone_sites(other) == [], zone_sites(other)


def test_tournaments_builds_a_zone_at_import_today():
    """The positive control: the site lesson 913 found is still found, at
    import time, so a green census below is not a scanner that sees nothing."""
    sites = ZONE_SITES.get("api/tournaments.py")
    assert sites and any(t for _line, t in sites), ZONE_SITES


def test_every_zone_construction_has_zone_data_declared():
    assert zone_data_missing(ZONE_SITES, _declared(API_REQ), DECLARED) == {}


def test_taking_tzdata_out_turns_the_zone_check_red():
    api = _declared(API_REQ)
    assert ZONE_DATA in api, sorted(api)
    gone = zone_data_missing(ZONE_SITES, api - {ZONE_DATA}, DECLARED - {ZONE_DATA})
    assert gone == {r: s for r, s in ZONE_SITES.items()}, gone
    assert "api/tournaments.py" in gone
    # declared by the test file only: an api file is still red (the image
    # and a seat that installs the api file alone do not read the test file)
    test_only = zone_data_missing(ZONE_SITES, api - {ZONE_DATA}, DECLARED | {ZONE_DATA})
    assert "api/tournaments.py" in test_only, test_only


def test_the_lock_carries_tzdata_at_the_declared_version_with_one_hash():
    want = _pins(API_REQ.read_text(encoding="utf-8"))[ZONE_DATA]
    text = API_LOCK.read_text(encoding="utf-8")
    m = re.search(r"(?m)^tzdata==(\S+) \\\n((?:    --hash=sha256:[0-9a-f]{64}(?: \\)?\n)+)", text)
    assert m, "requirements.lock has no tzdata entry"
    assert m.group(1) == want, (m.group(1), want)
    assert len(re.findall(r"--hash=sha256:", m.group(2))) == 1, m.group(2)


def test_an_inert_removal_keeps_the_check_green():
    imported = {_norm(DISTRIBUTION.get(m, m)) for m in FOUND}
    inert = sorted(d for d in DECLARED if d not in imported
                   and d not in {_norm(v) for v in THROUGH.values()})
    assert inert, "every declared distribution is imported directly"
    assert undeclared(FOUND, DECLARED - {inert[0]}) == {}
