"""The DSN census of the read-only bound, default-deny over import and
opener forms (ruling REHEARSAL-FOUR-R7-A1 M2).

Over a frozen file list (the import closure of the covered files), every
FORM below is collected, per file, by its spelling alone (rule (1)(c): no
alias tracking and no import resolution). test_r7_ro_role_pg asserts the
collected multiset equals ro_census_frozen.FROZEN exactly, so any form not
frozen is refused by its shape, whatever it does:

  import    every import statement naming a database driver module
            (DRIVER_ROOTS), as written (`import asyncpg as pg` is a
            different form from `import asyncpg as _asyncpg`);
  opener    every Name, Attribute, definition or string constant spelled
            with a name in OPENER_NAMES (a call, a reference, a store, a
            `def`, or a getattr key), with its full dotted spelling: a bare
            `connect(...)` or `pg.connect(...)` is a form the freeze lacks;
  kwarg     every keyword argument in IDENTITY_KWARGS of any call, with
            the callee and the value as written (`user=`, `options=`,
            `server_settings=`, `connect_args=`, ...);
  dsntext   every string constant (f-string parts included) containing
            "://", "@" or "postgres": the texts a DSN is rebuilt from;
  identity  every string constant matching IDENTITY_SQL (SET ROLE, SET
            SESSION AUTHORIZATION, set_config('role', ...), -c role=):
            the freeze holds none, so each is refused;
  env       every environment read whose key is a string constant naming
            DSN or DATABASE_URL, or a Name ending in DSN_VAR.
"""

import ast
import collections
import os
import re

DRIVER_ROOTS = frozenset({"asyncpg", "sqlalchemy", "psycopg", "psycopg2",
                          "psycopg_pool", "aiopg", "pg8000", "databases"})
OPENER_NAMES = frozenset({
    "connect", "create_async_engine", "create_engine", "create_pool",
    "connect_bound", "bound_engine", "CaseSchema", "fresh_database",
    "make_asm_engine", "case", "checkout", "engine_from_config",
    "async_engine_from_config", "_sqlalchemy_create_async_engine", "make_url",
})
IDENTITY_KWARGS = frozenset({"user", "username", "password", "role", "options",
                             "server_settings", "connect_args", "dsn", "url",
                             "host", "database", "passfile"})
IDENTITY_SQL = re.compile(
    r"(?i)\bset\s+(?:local\s+|session\s+)?role\b|session[\s_]+authorization"
    r"|set_config\s*\(\s*'role'|-c\s*role\s*=")
ENV_CALLS = ("os.environ.get", "os.getenv", "environ.get")


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _env_key(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value if ("DSN" in node.value or "DATABASE_URL" in node.value) else None
    if isinstance(node, ast.Name) and node.id.endswith("DSN_VAR"):
        return node.id
    return None


def _spelling(node):
    return _dotted(node) or ast.unparse(node)


def forms(path, source):
    """The sorted list of (kind, spelling) forms of `source`."""
    out = []
    tree = ast.parse(source, filename=path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name.split(".")[0] in DRIVER_ROOTS for a in node.names):
                out.append(("import", ast.unparse(node)))
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in DRIVER_ROOTS:
                out.append(("import", ast.unparse(node)))
        if isinstance(node, ast.Attribute) and node.attr in OPENER_NAMES:
            out.append(("opener", "%s %s" % (type(node.ctx).__name__, _spelling(node))))
        elif isinstance(node, ast.Name) and node.id in OPENER_NAMES:
            out.append(("opener", "%s %s" % (type(node.ctx).__name__, node.id)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name in OPENER_NAMES:
            out.append(("opener", "def " + node.name))
        elif isinstance(node, ast.alias) and (node.asname or node.name).split(".")[-1] \
                in OPENER_NAMES:
            out.append(("opener", "alias " + (node.asname or node.name)))
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in IDENTITY_KWARGS:
                    out.append(("kwarg", "%s %s=%s" % (_spelling(node.func), kw.arg,
                                                       ast.unparse(kw.value))))
            d = _dotted(node.func)
            if d in ENV_CALLS and node.args and _env_key(node.args[0]):
                out.append(("env", _env_key(node.args[0])))
        elif isinstance(node, ast.Subscript) and _dotted(node.value) == "os.environ":
            if _env_key(node.slice):
                out.append(("env", _env_key(node.slice)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value
            if IDENTITY_SQL.search(v):
                out.append(("identity", v))
            if "://" in v or "@" in v or "postgres" in v.lower():
                out.append(("dsntext", v))
            if v in OPENER_NAMES:
                out.append(("opener", "str " + v))
    return sorted(out)


def census(root, files):
    """{file: sorted forms} over `files` (paths relative to `root`); a file
    with no form maps to []."""
    got = {}
    for rel in files:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            got[rel] = forms(rel, fh.read())
    return got


def diff(got, frozen):
    """Every form of `got` not in `frozen` and every frozen form missing,
    as (file, '+'|'-', kind, spelling), counted as multisets."""
    out = []
    for rel in sorted(set(got) | set(frozen)):
        g = collections.Counter(got.get(rel, []))
        f = collections.Counter(tuple(x) for x in frozen.get(rel, []))
        for form, n in sorted((g - f).items()):
            out += [(rel, "+") + form] * n
        for form, n in sorted((f - g).items()):
            out += [(rel, "-") + form] * n
    return out
