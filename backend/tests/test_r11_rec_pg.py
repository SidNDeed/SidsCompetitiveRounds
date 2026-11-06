"""Rulings FOUR-R11-A8 and FOUR-R11-A11: the a1 arm's open recorder, its
control, and the census that shows the module reaches no open.

test_a1_identity_formation.py installs ro_census.OpenRecorder at its own
freeze (one freeze before its first id, one thaw after its last) and
requires, at the thaw, the recorder active with zero opens and zero
connections built. This file holds:

  the control      an open to another DSN planted inside a window frozen by
                   the module's own _a1_freeze is refused by the module's own
                   _a1_window_refusal, with the recorder's message;
  the census       whether any id of the module reaches an opener: (1) the
                   module text, (2) the fixtures it uses (conftest.py), (3)
                   production code called from it, by reachability over the
                   call graph of backend/api and backend/tests from every
                   call the module makes into a project module, to a
                   reference that resolves to database.py's engines,
                   session factories or session dependencies, or to a
                   driver's opener (asyncpg.connect, create_pool,
                   SQLAlchemy's engine constructors);
  their controls   a planted opener call in the module text is found; a
                   planted call of a main.py function that opens its own
                   session is found, with the site it reaches.

The census is a filter over the text; the recorder in the module is the
bound over the run. The reachability is an over-approximation: every name a
reached function references that resolves to a project function or class is
followed, called or not.
"""

import ast
import asyncio
import os
import sys

import asyncpg
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, "..", "api")
sys.path.insert(0, API)
sys.path.insert(0, HERE)

import r11_open_window as ow  # noqa: E402
import ro_census  # noqa: E402
import ro_role  # noqa: E402
import test_a1_identity_formation as a1  # noqa: E402

A1_REL = "tests/test_a1_identity_formation.py"
MODULE = "<module>"
BACKEND = os.path.normpath(os.path.join(HERE, ".."))
# The census kinds that name or build an open. dynamic, alias and
# constructed forms are counted and listed apart (the recorder covers them).
OPENER_SITE_KINDS = frozenset({"opener", "call", "ref", "refuse", "wrapper", "argdef"})
# database.py's names that open or hand out a connection: its engines, its
# session factories, the session dependencies, the engine builders.
DATABASE_OPENERS = frozenset({
    "engine", "async_session", "release_engine", "release_session", "asm_engine",
    "asm_session", "make_asm_engine", "create_async_engine", "get_db",
    "get_release_db", "get_asm_db"})
# A driver's own opener functions, by the module root they resolve to.
DRIVER_OPENERS = frozenset({"connect", "create_pool", "create_async_engine", "create_engine",
                            "engine_from_config", "async_engine_from_config"})


def _read(rel):
    with open(os.path.join(BACKEND, rel), encoding="utf-8") as fh:
        return fh.read()


def _opener_sites(rel, source):
    got = ro_census.file_forms(rel, source)
    return sorted(f for v in got.values() for f in v if f[0] in OPENER_SITE_KINDS)


# ------------------------------------------------------- the reachability

def _project_modules():
    """{module name: path} of every .py in backend/api and backend/tests."""
    out = {}
    for d in (os.path.join(BACKEND, "api"), os.path.join(BACKEND, "tests")):
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                out.setdefault(name[:-3], os.path.join(d, name))
    return out


class _Module:
    def __init__(self, name, path, source=None):
        self.name = name
        if source is None:
            with open(path, encoding="utf-8") as fh:
                source = fh.read()
        self.tree = ast.parse(source, filename=path)
        self.defs = {}
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.defs[node.name] = node
        self.imports = _imports(self.tree)


def _imports(tree):
    """{local name: (module, attribute or None)} over every import in the
    tree, wherever it stands (function-local imports included)."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for al in node.names:
                if al.asname:
                    out[al.asname] = (al.name, None)
                else:
                    out[al.name.split(".")[0]] = (al.name.split(".")[0], None)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for al in node.names:
                out[al.asname or al.name] = (node.module, al.name)
    return out


class Reach:
    """Reachability by CALL from seed (module, name) pairs over the
    project's modules, to opener sites. A reached function's every call
    whose callee resolves (a module-level name, an import, `<module
    alias>.<name>`) to a project function or class is followed (a class:
    every method). A site is any reference in a reached function, called or
    not, that resolves to database.py's openers or a driver's opener. A
    call through a callee no static resolution names (getattr with a
    computed name, a method of an object) is not followed: the census is
    the filter, the module's recorder is the bound."""

    # The recorder itself is not followed: it forwards an open only when the
    # run makes one (it compares with and wraps asyncpg.connect, which is
    # what the census would otherwise name); every hit is listed in .skipped.
    SKIP = frozenset({("ro_census", "OpenRecorder")})

    def __init__(self, overrides=None):
        self.paths = _project_modules()
        self.overrides = dict(overrides or {})
        self.mods = {}
        self.skipped = set()

    def mod(self, name):
        if name not in self.paths:
            return None
        if name not in self.mods:
            self.mods[name] = _Module(name, self.paths[name], self.overrides.get(name))
        return self.mods[name]

    def defs_of(self, name):
        """Every top-level function and class of the module, and MODULE, its
        module-level statements (calls made at import or in a module-level
        expression)."""
        m = self.mod(name)
        return ({(name, n) for n in m.defs} | {(name, MODULE)}) if m else set()

    def _resolve(self, m, node, local_imports):
        """The (module, name) a Name or Attribute chain refers to, or None."""
        imports = dict(m.imports)
        imports.update(local_imports)
        if isinstance(node, ast.Name):
            if node.id in imports:
                mod, attr = imports[node.id]
                return (mod, attr) if attr else None
            if node.id in m.defs:
                return (m.name, node.id)
            return None
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base in imports and imports[base][1] is None:
                return (imports[base][0], node.attr)
            if base in imports and imports[base][1] is not None:
                return ("%s.%s" % imports[base], node.attr)
        return None

    def run(self, seeds):
        """{reached (module, name)}, [(module, function, line, site)]."""
        seen, sites, todo = set(), [], list(seeds)
        while todo:
            key = todo.pop()
            if key in seen:
                continue
            seen.add(key)
            if key in self.SKIP:
                self.skipped.add(key)
                continue
            mod, name = key
            root = mod.split(".")[0]
            if mod == "database" and name in DATABASE_OPENERS:
                sites.append(key + (0, "database.%s" % name))
                continue
            if root in ro_census.DRIVER_ROOTS and name in DRIVER_OPENERS:
                sites.append(key + (0, "%s.%s" % (mod, name)))
                continue
            m = self.mod(mod)
            if m is None:
                continue
            if name == MODULE:
                fn = ast.Module(body=[s for s in m.tree.body if not isinstance(
                    s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])
            elif name in m.defs:
                fn = m.defs[name]
            else:
                continue
            local = _imports(fn)
            for node in ast.walk(fn):
                if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(
                        getattr(node, "ctx", None), ast.Load):
                    target = self._resolve(m, node, local)
                    if target is None:
                        continue
                    troot = target[0].split(".")[0]
                    if target[0] == "database" and target[1] in DATABASE_OPENERS:
                        sites.append((mod, name, node.lineno, "database.%s" % target[1]))
                    elif troot in ro_census.DRIVER_ROOTS and target[1] in DRIVER_OPENERS:
                        sites.append((mod, name, node.lineno, "%s.%s" % target))
                elif isinstance(node, ast.Call):
                    target = self._resolve(m, node.func, local)
                    if target is not None and target[0] in self.paths:
                        todo.append(target)
        return seen, sorted(set(sites))


def seeds_of(source, modname="test_a1_identity_formation"):
    """Every call the module text makes into a project module: a call whose
    callee is `<alias>.<name>` with <alias> a project module import, or a
    Name imported from one. The module's own functions are seeds too (its
    fixtures and ids)."""
    tree = ast.parse(source)
    imports = _imports(tree)
    paths = _project_modules()
    out = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
            imp = imports.get(f.value.id)
            if imp and imp[1] is None and imp[0] in paths:
                out.add((imp[0], f.attr))
        elif isinstance(f, ast.Name):
            imp = imports.get(f.id)
            if imp and imp[1] is not None and imp[0] in paths:
                out.add((imp[0], imp[1]))
    return out


# ------------------------------------------------------------- the census

def test_r11_a1_module_text_has_no_opener_site():
    """A11 (1), the module: no form of an opener kind in its text."""
    assert _opener_sites(A1_REL, _read(A1_REL)) == []


def test_r11_a1_module_census_control():
    """The same check finds a planted opener call."""
    planted = _read(A1_REL) + "\n\nasync def _r11_planted(d):\n    return await asyncpg.connect(d)\n"
    assert ("call", "asyncpg.connect(d)") in _opener_sites(A1_REL, planted)


def test_r11_a1_fixtures_have_no_opener_site():
    """A11 (1), the fixtures it uses: its own are in its text (above);
    conftest.py's autouse fixtures and the module's window fixture
    (r11_open_window.py, which reaches asyncpg only through
    ro_census.OpenRecorder) hold no opener form."""
    assert _opener_sites("tests/conftest.py", _read("tests/conftest.py")) == []
    assert _opener_sites("tests/r11_open_window.py", _read("tests/r11_open_window.py")) == []


A1_MOD = "test_a1_identity_formation"


def _a1_reach(overrides=None, skipped=None):
    r = Reach(overrides)
    # the module, conftest.py's fixtures, and the module's own window fixture
    seeds = r.defs_of(A1_MOD) | r.defs_of("conftest") | r.defs_of("r11_open_window")
    reached, sites = r.run(seeds)
    if skipped is not None:
        skipped.update(r.skipped)
    return seeds, reached, sites


def test_r11_a1_reaches_no_opener():
    """A11 (1): no function of the module (its ids, fixtures and helpers)
    nor of conftest.py reaches, by call, an opener site in backend/api or
    backend/tests. Not vacuous: the module's calls into main.py are among
    the seeds' callees and are reached. The one function not followed is
    the recorder the module installs (Reach.SKIP)."""
    skipped = set()
    seeds, reached, sites = _a1_reach(skipped=skipped)
    assert skipped == {("ro_census", "OpenRecorder")}, skipped
    assert ("main", "_identity_lock_many") in reached and ("main", "_ffa_gather_decide") in reached
    assert seeds_of(_read(A1_REL)) <= reached
    main_reached = sorted(n for m, n in reached if m == "main")
    print("R11-REC a1 reach: seeds %d reached %d main %d sites %d: %s" % (
        len(seeds), len(reached), len(main_reached), len(sites), main_reached))
    assert sites == [], sites


def test_r11_reach_control():
    """The same route finds a planted call, in the module text, of a main.py
    function that opens its own session through database.async_session,
    with that site."""
    main = Reach().mod("main")
    opener_fns = sorted(n for n, fn in main.defs.items()
                        if ("database", "async_session") in _imports(fn).values())
    assert opener_fns, "no main.py function imports database.async_session"
    planted = _read(A1_REL) + "\n\ndef _r11_planted(db):\n    return main.%s(db)\n" % opener_fns[0]
    _seeds, reached, sites = _a1_reach({A1_MOD: planted})
    assert ("main", opener_fns[0]) in reached
    assert any(s[0] == "main" and s[1] == opener_fns[0] and s[3] == "database.async_session"
               for s in sites), sites


def test_r11_database_openers_are_databases_own():
    """Every name DATABASE_OPENERS lists is defined in database.py, and every
    database.py name bound to an engine or a session factory is listed."""
    tree = ast.parse(_read("api/database.py"))
    defined, bound = set(), set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    defined.add(t.id)
                    if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) \
                            and node.value.func.id in ("create_async_engine", "async_sessionmaker",
                                                       "make_asm_engine"):
                        bound.add(t.id)
    assert DATABASE_OPENERS <= defined, DATABASE_OPENERS - defined
    assert bound and bound <= DATABASE_OPENERS, bound - DATABASE_OPENERS


# ------------------------------------------------------------ the control

def test_r11_a1_window_control():
    """A8 (2) and A11 (2), the control: inside a window frozen by the
    module's own window (r11_open_window.a1_freeze, the fixture the module
    imports), an open to another DSN (the frozen URL with another database)
    is refused by r11_open_window.a1_window_refusal, and the refusal carries
    the recorder's message."""
    assert a1._a1_open_window is ow._a1_open_window
    rec = ow.a1_freeze()
    planted = ro_role.dsn_for(ow.a1_frozen_dsn(), "rf11rec_planted_" + os.urandom(3).hex())

    async def plant():
        try:
            conn = await asyncpg.connect(planted, timeout=5)   # the planted open
            await conn.close()
        except Exception as e:   # noqa: BLE001 -- the open's own failure is not the point
            return repr(e)
        return None

    try:
        err = asyncio.run(plant())
        w = rec.report()
    finally:
        rec.thaw()
    refusal = ow.a1_window_refusal(w)
    assert refusal is not None and "open not the frozen DSN" in refusal, (refusal, w, err)
    assert w["active"] and w["opens"] == 1, w
    assert asyncpg.connect is asyncpg.connection.connect, "the thaw did not restore connect"
