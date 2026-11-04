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
        "so the forwarded keywords are bound at their call sites; round 10: "
        "the wrapper itself is bound whole (its `wrapper` form: signature, "
        "body and every local statement that builds what it forwards), so a "
        "change inside it refuses",
}


# Round 10 (ruling REHEARSAL-R9-A1 (C), refuse by default). Four more kinds
# of the complete layer, each frozen at the round-9 tip 0b317394 (the literal
# R10_FROZEN in ro_census_frozen; never regenerated):
#
#   constructed  every Call whose callee is CONSTRUCTED: not a Name and not an
#                Attribute (a call's result called, a subscript, a lambda, an
#                await, a conditional, ...), or an Attribute named __call__
#                on any receiver: the whole call as written. Its callee has no
#                name the census could bind, so the exact form must be frozen.
#   alias        every ALIAS of a dynamic-access name or of an opener: an
#                import statement that names one (as its name or its asname)
#                or that imports from the builtins module; a Name spelling a
#                DYNAMIC_NAMES entry anywhere except as the bare callee of a
#                call (an assignment, an argument, a default, a store, a
#                rebinding); an Attribute spelling one anywhere except as a
#                callee the round-9 dynamic rule classifies (CLASSIFIED_*:
#                f = builtins.getattr, builtins.vars(m), x.getattr_static);
#                a Name or Attribute builtins / __builtins__ / __builtin__ in
#                any context; a
#                def, class or parameter named a DYNAMIC_NAMES entry; a string
#                constant equal to one of those names (globals()['getattr']).
#                Each as its parent node as written.
#   wrapper      every FORWARDING WRAPPER, whole: the innermost function (def
#                or lambda) that holds an opener call one of whose arguments
#                reads a name a function around the call binds (a parameter
#                or a local), and the function that binds it (a closure):
#                the definition as written, once per function. Any change
#                to the body, the signature, the defaults or the local
#                assignments and mutations that build a forwarded argument
#                changes this form.
#   argdef       the DEFINITIONS of every module-scope name an opener call
#                forwards (a Name read by an argument, bound by no function
#                around the call): every module-scope statement that binds it
#                (assignment, import, def, class, for, with, del), every
#                statement anywhere that stores into it or deletes from it (a
#                subscript or attribute target rooted at it, an augmented
#                assignment), every expression statement that calls a method
#                on it (the mutating call shape, n.update(...)), and every
#                function that declares it global, whole: as
#                'name <- statement', once per statement per file.
DYNAMIC_NAMES = (DYNAMIC_ATTR_CALLS | DYNAMIC_BUILTINS | DYNAMIC_CALLS
                 | frozenset({"getattr_static"}))
DYNAMIC_MODULES = frozenset({"builtins", "__builtins__", "__builtin__"})
_FUNCS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _name_of(func):
    """The opener name a callee or reference spells (its last segment)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _constructed(func):
    """Whether a callee is constructed (round 10): not a Name, not an
    Attribute, or an Attribute named __call__."""
    if isinstance(func, ast.Name):
        return False
    if isinstance(func, ast.Attribute):
        return func.attr == "__call__"
    return True


def _root(node):
    """The Name at the root of an Attribute / Subscript chain, or None."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _own_nodes(fn):
    """The nodes of function `fn`'s own scope: its body (or lambda body),
    not descending into nested functions or classes (whose own node is
    included)."""
    body = fn.body if isinstance(fn.body, list) else [fn.body]
    stack, out = list(body), []
    while stack:
        n = stack.pop()
        out.append(n)
        if isinstance(n, _FUNCS + (ast.ClassDef,)):
            continue
        stack.extend(ast.iter_child_nodes(n))
    return out


def _binds(fn):
    """The names function `fn` binds: its parameters and every name its own
    scope stores, deletes, imports or defines, less those it declares
    global or nonlocal."""
    a = fn.args
    out = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
    out |= {x.arg for x in (a.vararg, a.kwarg) if x is not None}
    declared = set()
    for n in _own_nodes(fn):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            out.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            out |= {(al.asname or al.name).split(".")[0] for al in n.names}
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            declared |= set(n.names)
    return out - declared


def _arg_names(call):
    """The Names a call's arguments read: every Name anywhere in a
    positional or keyword argument (unpacked ones included), so the root
    Name of every attribute or subscript chain there too."""
    out = set()
    for a in list(call.args) + [k.value for k in call.keywords]:
        for n in ast.walk(a):
            if isinstance(n, ast.Name):
                out.add(n.id)
    return out


def _module_statements(tree):
    """Every statement of module scope: the module body, descending into
    compound statements (if, try, with, for, while, match) but not into a
    def or class body (their own statement is included)."""
    stack, out = list(tree.body), []
    while stack:
        s = stack.pop()
        out.append(s)
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for field in ("body", "orelse", "finalbody", "handlers", "cases"):
            for c in getattr(s, field, None) or []:
                stack.extend(c.body if isinstance(c, (ast.ExceptHandler, ast.match_case))
                             else [c])
    return out


def _stmt_binds(s, name):
    """Whether module-scope statement `s` binds `name` itself."""
    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return s.name == name
    if isinstance(s, (ast.Import, ast.ImportFrom)):
        return any((al.asname or al.name).split(".")[0] == name for al in s.names)
    targets = []
    if isinstance(s, ast.Assign):
        targets = s.targets
    elif isinstance(s, (ast.AnnAssign, ast.AugAssign, ast.For, ast.AsyncFor)):
        targets = [s.target]
    elif isinstance(s, (ast.With, ast.AsyncWith)):
        targets = [i.optional_vars for i in s.items if i.optional_vars is not None]
    elif isinstance(s, ast.Delete):
        targets = s.targets
    return any(isinstance(n, ast.Name) and n.id == name
               for t in targets for n in ast.walk(t))


def _stmt_mutates(s, name):
    """Whether statement `s` (anywhere) stores into, deletes from or calls a
    method on `name` (its targets' chain root, or an expression statement
    whose callee is an attribute chain rooted at it)."""
    targets = []
    if isinstance(s, ast.Assign):
        targets = s.targets
    elif isinstance(s, (ast.AnnAssign, ast.AugAssign)):
        targets = [s.target]
    elif isinstance(s, ast.Delete):
        targets = s.targets
    for t in targets:
        for n in ast.walk(t):
            if isinstance(n, (ast.Attribute, ast.Subscript)) and _root(n) == name:
                return True
        if isinstance(s, ast.AugAssign) and isinstance(t, ast.Name) and t.id == name:
            return True
    if isinstance(s, ast.Expr):
        v = s.value.value if isinstance(s.value, ast.Await) else s.value
        if isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) \
                and _root(v.func) == name:
            return True
    return False


def _forwarding(tree, parent, opener_calls):
    """The wrapper and argdef forms (round 10) of the opener calls of one
    module, once per function and once per definition statement."""
    wrappers, argdefs, module_names = {}, set(), set()
    for call in opener_calls:
        chain = []
        p = parent.get(call)
        while p is not None:
            if isinstance(p, _FUNCS):
                chain.append(p)
            p = parent.get(p)
        for name in sorted(_arg_names(call)):
            owner = next((fn for fn in chain if name in _binds(fn)), None)
            if owner is not None:
                # the innermost function holding the call is a wrapper, and
                # so is the function that binds the name (a closure)
                for fn in (chain[0], owner):
                    wrappers[id(fn)] = fn
            else:
                module_names.add(name)
    statements = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]
    module_stmts = _module_statements(tree)
    for name in module_names:
        for s in module_stmts:
            if _stmt_binds(s, name):
                argdefs.add("%s <- %s" % (name, ast.unparse(s)))
        for s in statements:
            if _stmt_mutates(s, name):
                argdefs.add("%s <- %s" % (name, ast.unparse(s)))
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                    isinstance(g, ast.Global) and name in g.names for g in _own_nodes(s)):
                argdefs.add("%s <- %s" % (name, ast.unparse(s)))
    out = [("wrapper", ast.unparse(fn)) for fn in wrappers.values()]
    out += [("argdef", a) for a in sorted(argdefs)]
    return out


# The callees the round-9 dynamic rule already classifies, so the alias kind
# leaves them to it: a bare Name callee of any of the three round-9 sets
# (getattr/setattr/delattr/hasattr by the literal-name rule, the rest always
# `dynamic`), and an Attribute callee of the attribute-call and call sets
# (builtins.getattr(m, n) is `dynamic` unless n is a string literal, whose
# opener name the coarse `str` form binds; operator.attrgetter(...) is always
# `dynamic`). Every other spelling of a dynamic name is an alias form: an
# Attribute callee of vars/globals/locals/__import__/eval/exec (the round-9
# rule reads those as bare Names only) and getattr_static in any spelling.
CLASSIFIED_NAME_CALLS = DYNAMIC_ATTR_CALLS | DYNAMIC_BUILTINS | DYNAMIC_CALLS
CLASSIFIED_ATTR_CALLS = DYNAMIC_ATTR_CALLS | DYNAMIC_CALLS


def _classified_callee(node, up):
    """Whether `node` is the callee of call `up` and the round-9 dynamic
    rule classifies that call (see CLASSIFIED_*)."""
    if not (isinstance(up, ast.Call) and up.func is node):
        return False
    if isinstance(node, ast.Name):
        return node.id in CLASSIFIED_NAME_CALLS
    return isinstance(node, ast.Attribute) and node.attr in CLASSIFIED_ATTR_CALLS


def _aliases(tree, parent):
    """The alias forms (round 10) of one module."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (getattr(node, "module", None) or "").split(".")[0]
            hit = isinstance(node, ast.ImportFrom) and mod in DYNAMIC_MODULES
            for al in node.names:
                last = al.name.split(".")[-1]
                if (al.name.split(".")[0] in DYNAMIC_MODULES or last in DYNAMIC_NAMES
                        or last in OPENER_NAMES or (al.asname or "") in DYNAMIC_NAMES
                        or (al.asname or "") in OPENER_NAMES):
                    hit = True
            if hit:
                out.append(("alias", ast.unparse(node)))
        elif isinstance(node, ast.Name) and (node.id in DYNAMIC_NAMES
                                             or node.id in DYNAMIC_MODULES):
            up = parent.get(node)
            if not (_classified_callee(node, up) and isinstance(node.ctx, ast.Load)):
                out.append(("alias", ast.unparse(up) if up is not None else node.id))
        elif isinstance(node, ast.Attribute) and (node.attr in DYNAMIC_NAMES
                                                  or node.attr in DYNAMIC_MODULES):
            up = parent.get(node)
            if not (_classified_callee(node, up) and node.attr in CLASSIFIED_ATTR_CALLS):
                out.append(("alias", ast.unparse(up) if up is not None else ast.unparse(node)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) \
                and node.name in DYNAMIC_NAMES:
            out.append(("alias", "def " + node.name))
        elif isinstance(node, ast.arg) and node.arg in DYNAMIC_NAMES:
            out.append(("alias", "arg " + node.arg))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and (
                node.value in DYNAMIC_NAMES or node.value in DYNAMIC_MODULES):
            out.append(("alias", "str " + node.value))
    return out


def complete_forms(path, source):
    """The sorted list of (kind, spelling) forms of the complete layer of
    `source` (`path` relative to backend/, as in the census)."""
    out = []
    tree = ast.parse(source, filename=path)
    parent = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    opener_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _name_of(node.func)
            if _constructed(node.func):
                out.append(("constructed", ast.unparse(node)))
            if name in OPENER_NAMES:
                opener_calls.append(node)
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
    out += _aliases(tree, parent)
    out += _forwarding(tree, parent, opener_calls)
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
