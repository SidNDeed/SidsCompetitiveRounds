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


# ---------------------------------------------------------------------------
# The complete layer (ruling REHEARSAL-R8-A1 G1): complete opener forms.
# The coarse forms above bind an opener's callee spelling and nothing else,
# so a call that keeps its callee and changes its arguments (keyword
# unpacking, a different positional DSN) keeps every coarse form, and a
# getattr whose attribute name is built at run time yields no form at all.
# This layer binds every node of an opener call and refuses, by shape, every
# construction it does not recognise. Each file's layer is census key
# `file + COMPLETE`, frozen once at the round-8 tip effc36c6 (a judgement
# recorded in the round-9 notes). Kinds:
#
#   call      every Call whose callee is an opener name (a Name in
#             OPENER_NAMES, or an Attribute whose attr is one) spelled as a
#             dotted name chain, with no starred argument and no keyword
#             unpacking: the whole call as written (callee, every positional
#             argument, every keyword name and value, their order);
#   ref       every Load of an opener name that is not a call's callee (an
#             alias capture, a callback, a receiver): its parent node as
#             written;
#   dynamic   every dynamic attribute or module access, whatever it names:
#             getattr/setattr/delattr/hasattr whose attribute name is not a
#             string literal (a Name, a concatenation, an f-string, ...),
#             any call of vars, globals, locals, __import__, eval, exec,
#             attrgetter, methodcaller or import_module, any __dict__,
#             __getattribute__ or __getattr__ attribute, and sys.modules: the
#             node as written;
#   refuse    an opener call with a starred argument or keyword unpacking,
#             or whose callee is not a dotted name chain: refused by shape;
#             the freeze holds none (the one declared exception, FORWARDING,
#             is a `call`).
#
# A form of any kind the freeze lacks is refused by the census diff; a
# `refuse` form is refused whatever the freeze holds.
COMPLETE = "#complete"
DYNAMIC_ATTR_CALLS = frozenset({"getattr", "setattr", "delattr", "hasattr"})
DYNAMIC_BUILTINS = frozenset({"vars", "globals", "locals", "__import__", "eval", "exec"})
DYNAMIC_CALLS = frozenset({"attrgetter", "methodcaller", "import_module"})
DYNAMIC_ATTRS = frozenset({"__dict__", "__getattribute__", "__getattr__"})
# Declared exceptions to the keyword-unpacking refusal, one by one, each
# with its reason: (file, the complete call as written).
FORWARDING = {
    ("api/database.py",
     "_sqlalchemy_create_async_engine(url, hide_parameters=True, **options)"):
        "database.create_async_engine is the module's forwarding wrapper "
        "(def create_async_engine(url, **options)); every keyword it forwards "
        "comes from a call of create_async_engine, and each such call is "
        "itself a complete `call` form here (literal keyword names, frozen), "
        "so the forwarded keywords are bound at their call sites",
}


def _name_of(func):
    """The opener name a callee or reference spells (its last segment)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def complete_forms(path, source):
    """The sorted list of (kind, spelling) forms of the complete layer of
    `source` (`path` relative to backend/, as in the census)."""
    out = []
    tree = ast.parse(source, filename=path)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _name_of(node.func)
            if name in OPENER_NAMES:
                text = ast.unparse(node)
                unpacked = any(k.arg is None for k in node.keywords) or any(
                    isinstance(a, ast.Starred) for a in node.args)
                if (path, text) in FORWARDING:
                    out.append(("call", text))
                elif unpacked or _dotted(node.func) is None:
                    out.append(("refuse", text))
                else:
                    out.append(("call", text))
            if name in DYNAMIC_ATTR_CALLS:
                literal = (len(node.args) >= 2 and not any(
                    isinstance(a, ast.Starred) for a in node.args[:2])
                    and isinstance(node.args[1], ast.Constant)
                    and isinstance(node.args[1].value, str)
                    and not any(k.arg is None for k in node.keywords))
                if not literal:
                    out.append(("dynamic", ast.unparse(node)))
            elif (isinstance(node.func, ast.Name) and name in DYNAMIC_BUILTINS) \
                    or name in DYNAMIC_CALLS:
                out.append(("dynamic", ast.unparse(node)))
        if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load) \
                and _name_of(node) in OPENER_NAMES:
            up = parent.get(node)
            if not (isinstance(up, ast.Call) and up.func is node):
                out.append(("ref", ast.unparse(up) if up is not None else ast.unparse(node)))
        if isinstance(node, ast.Attribute) and (
                node.attr in DYNAMIC_ATTRS or _dotted(node) == "sys.modules"):
            out.append(("dynamic", ast.unparse(node)))
    return sorted(out)


def file_forms(rel, source):
    """Both layers of one file: {rel: forms, rel + COMPLETE: complete forms}."""
    return {rel: forms(rel, source), rel + COMPLETE: complete_forms(rel, source)}


def census(root, files):
    """{file: sorted forms, file + COMPLETE: sorted complete forms} over
    `files` (paths relative to `root`); a file with no form maps to []."""
    got = {}
    for rel in files:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            got.update(file_forms(rel, fh.read()))
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
