"""The census behind test_ban_read_table_census.py (bans part 2a, D1).

Which functions of main reach a read of player_bans, and which test files
build a database of their own whose tests run one of them.

  * BAN READ: a top-level function of main whose body holds a string
    constant that reads player_bans (FROM player_bans, or a JOIN of it).
  * REACHES (direct): the ban read functions and every top-level function of
    main whose BODY calls one that reaches, or passes it as an argument
    (a callback, a task). The parameter defaults are left out: a test that
    calls main.f(...) directly passes its own arguments, so Depends(...) in
    f's signature does not run.
  * A ROUTE REACHES when its function reaches, or a dependency in its
    signature (Depends(g), transitively through g's own signature) reaches:
    a request through the app runs both.
  * A TEST FILE RUNS THE BAN READ when it names main.<f> for an f that
    reaches (a name read only as source or signature, inspect.getsource(
    main.f), runs nothing), or holds a string that is the path of a route
    that reaches (a path with parameters: the string starts with the path's
    text before its first '{').
  * A BUILDER FILE builds its own table list: a create_all(..., tables=...)
    call, or a string constant holding a hand-typed CREATE TABLE of players.
  * IT HAS THE TABLE when it, or a module of backend/tests it imports
    (transitively), imports ban_read_tables; or when it is ruled to build
    from the whole model metadata or the migration files (WHOLE_SCHEMA).

Everything is read from the syntax trees of main.py and the test files.
"""
import ast
import os
import re

from tree_copy_imports import local_test_imports

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.normpath(os.path.join(HERE, "..", "api", "main.py"))
_READS_BANS = re.compile(r"\b(FROM|JOIN)\s+player_bans\b", re.I)
_CREATE_PLAYERS = re.compile(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?([\w@]+\.)?players\s*\(", re.I)
_METHODS = {"get", "post", "put", "delete", "patch"}
_SOURCE_READERS = {"getsource", "getsourcelines", "signature", "getfile", "unwrap"}

# Builder files whose database for the calls the census counts is built from
# every model (create_all with no hand list) and the numbered migrations,
# 028_admin.sql (player_bans) among them. Each entry must still be a builder
# file that runs the ban read, or the census fails (no stale ruling).
WHOLE_SCHEMA = {
    "test_pc_trades.py": "_build: _create_all over every mapped table but the held-out "
                         "list, then the numbered migrations up to 352 (028 among them)",
}


def _functions(tree):
    return {n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _strings(node):
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            yield n.value


def _body_names(fn):
    """The names fn's body can run: every call of a bare name, and every
    bare name passed as an argument to a call."""
    for stmt in fn.body:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    yield n.func.id
                for a in list(n.args) + [k.value for k in n.keywords]:
                    if isinstance(a, ast.Name):
                        yield a.id


def _depends_names(fn):
    """g for every Depends(g) in fn's parameter defaults."""
    defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
    for d in defaults:
        for n in ast.walk(d):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Depends"
                    and n.args and isinstance(n.args[0], ast.Name)):
                yield n.args[0].id


def _route_paths(fn):
    for dec in fn.decorator_list:
        if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                and isinstance(dec.func.value, ast.Name) and dec.func.value.id == "app"
                and dec.func.attr in _METHODS and dec.args
                and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str)):
            yield dec.args[0].value


def reaching(main_src):
    """(ban read functions, functions that reach directly, route paths that reach)."""
    tree = ast.parse(main_src)
    funcs = _functions(tree)
    reads = {name for name, fn in funcs.items()
             if any(_READS_BANS.search(s) for s in _strings(fn))}
    callers = {}
    for name, fn in funcs.items():
        for callee in set(_body_names(fn)):
            if callee in funcs and callee != name:
                callers.setdefault(callee, set()).add(name)
    reach, todo = set(reads), list(reads)
    while todo:
        f = todo.pop()
        for c in callers.get(f, ()):
            if c not in reach:
                reach.add(c)
                todo.append(c)

    memo = {}

    def entry_reaches(name, seen=()):
        if name in memo:
            return memo[name]
        if name in reach:
            memo[name] = True
            return True
        fn = funcs.get(name)
        ok = bool(fn) and any(d not in seen and entry_reaches(d, seen + (name,))
                              for d in _depends_names(fn))
        memo[name] = ok
        return ok

    paths = {p for name, fn in funcs.items() for p in _route_paths(fn) if entry_reaches(name)}
    return reads, reach, paths


def _builds_tables(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.keyword) and n.arg == "tables":
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and _CREATE_PLAYERS.search(n.value):
            return True
    return False


def _main_names(tree):
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name in _SOURCE_READERS:
                for a in n.args:
                    skip.add(id(a))
    return {n.attr for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "main" and id(n) not in skip}


def _path_strings(tree):
    """Every string constant, and the leading text of every f-string."""
    out = set(_strings(tree))
    for n in ast.walk(tree):
        if isinstance(n, ast.JoinedStr) and n.values and isinstance(n.values[0], ast.Constant):
            out.add(str(n.values[0].value))
    return out


def _hits_path(strings, paths):
    for p in paths:
        if "{" in p:
            stem = p[:p.index("{")]
            if any(s.startswith(stem) for s in strings):
                return True
        elif p in strings:
            return True
    return False


def _imports_table(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == "ban_read_tables":
            return True
        if isinstance(n, ast.Import) and any(a.name == "ban_read_tables" for a in n.names):
            return True
    return False


def classify(sources, reach, paths, tests_dir=HERE):
    """sources: {file name: source}. Returns {name: (builds, runs, direct, has)}:
    direct is the file's own import of ban_read_tables; has counts the
    modules it imports and WHOLE_SCHEMA as well."""
    out = {}
    for name, src in sources.items():
        tree = ast.parse(src)
        builds = _builds_tables(tree)
        runs = bool(_main_names(tree) & reach) or _hits_path(_path_strings(tree), paths)
        direct = _imports_table(tree)
        has = direct or name in WHOLE_SCHEMA
        if not has:
            for mod in local_test_imports((name,), tests_dir)[1:]:
                p = os.path.join(tests_dir, mod)
                with open(p, encoding="utf-8") as fh:
                    if _imports_table(ast.parse(fh.read())):
                        has = True
                        break
        out[name] = (builds, runs, direct, has)
    return out


def failures(classes, rulings=None):
    """rulings: the whole-schema rulings checked (WHOLE_SCHEMA by default)."""
    rulings = WHOLE_SCHEMA if rulings is None else rulings
    out = []
    for name, (builds, runs, direct, has) in sorted(classes.items()):
        if builds and runs and not has:
            out.append((name, "runs the ban read on a database built without player_bans"))
        if direct and not (builds and runs):
            out.append((name, "carries the ban read tables but is no builder that runs the ban read"))
    for name in sorted(rulings):
        b, r, _, _ = classes.get(name, (False, False, False, False))
        if not (b and r):
            out.append((name, "a whole-schema ruling for a file that is no builder that runs the ban read"))
    return out


def tree_sources():
    out = {}
    for n in sorted(os.listdir(HERE)):
        if n.startswith("test_") and n.endswith(".py"):
            with open(os.path.join(HERE, n), encoding="utf-8") as fh:
                out[n] = fh.read()
    return out


def main_source():
    with open(MAIN, encoding="utf-8") as fh:
        return fh.read()
