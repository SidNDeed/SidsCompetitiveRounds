"""The one closed, default-deny walker of the two D5 source checks
(rehearsal-four round 3, ruling REHEARSAL-FOUR-R3).

Users: test_a1_identity_formation.py (the formation exit walk, the barrier,
the resolver and family-pick checks) and test_match_hold_admission_gate_pg.py
(the refusal and claim-prefix walks). Each file keeps its own statement
STRUCTURE (which exits a path takes, which branch refuses), but every
expression it meets, every helper body it descends into, and every SQL text
it executes is classified HERE, by one visitor, so a construct cannot be
accepted by omission in a walk written separately.

The rules:

  * NODE_TABLE names every concrete class of the running interpreter's ast
    module with its rule. `table_gaps()` lists any concrete ast.AST subclass
    the table does not name; the two test files assert it is empty, so a
    node class added by a newer interpreter fails the tests instead of being
    accepted.
  * An expression is visited node by node through the table. A class whose
    rule is "refuse" raises Unclassified naming the class and its line.
  * A call classifies its callee shape (a plain name, or a method named on a
    value) and every argument kind: positional, `*args`, keyword and
    `**kwargs`. A call of any other callee shape (a lambda, a subscript, a
    call result) is refused. `*args` and `**kwargs` are refused in a call of
    a resolved function (they would hide which parameter a value binds) and
    visited as values in a call of a listed pure builtin.
  * A lambda is a value: its parameter defaults and its body are visited.
    Calling it is a computed callee, refused.
  * An await, a yield and a comprehension are classified the same way: an
    await must be a session call (`db.execute(text(...))`, a transaction
    end) or a resolved coroutine function whose body is walked; yield and
    `yield from` are refused; a comprehension's iterables, conditions and
    element are visited, an async comprehension is refused.
  * A helper body is walked statement by statement through the same table.
    Its parameter defaults are visited. No fallback of either polarity: a
    construct the walk cannot classify raises, whatever the helper is for.
  * SQL is classified from the tokens of migration_table_ddl's lexer, the
    one lexer of the two files: string literals and quoted identifiers are
    single tokens (a comment marker inside a literal is literal text), a
    quoted function name is classified by its resolved name, dollar quoting,
    E'' strings and U& forms are refused, SELECT ... INTO and CREATE TABLE
    ... AS are writes.
"""
import ast as _ast
import collections as _collections
import importlib as _importlib
import sys as _sys
import inspect as _inspect
import re as _re
import textwrap as _textwrap
import types as _types

from migration_table_ddl import MigrationDdlError as _LexError
from migration_table_ddl import _tokens as _lex_tokens
from migration_table_ddl import _views as _lex_views


class Unclassified(Exception):
    """A construct the closed walk has no named shape for: (line, what)."""


# --- the node table -------------------------------------------------------

# Every concrete ast class, by name, with its rule:
#   leaf      a value with nothing to evaluate (a name, a constant, a context
#             or operator marker)
#   children  evaluate every child node through the table
#   call      a call: the callee shape and every argument kind classified
#   await     an awaited call: a session call or a walked helper
#   lambda    a lambda value: its defaults and body visited, never called
#   comp      a comprehension: iterables, conditions and element visited;
#             async refused
#   stmt      a statement the statement walkers place (helper bodies:
#             _helper_stmt; the D5 walks: their own structure)
#   refuse    never classified: the walk fails naming it
NODE_TABLE = {
    # values
    "Name": "leaf", "Constant": "leaf",
    "Attribute": "children", "Subscript": "children", "Slice": "children",
    "BinOp": "children", "BoolOp": "children", "UnaryOp": "children",
    "Compare": "children", "IfExp": "children", "JoinedStr": "children",
    "FormattedValue": "children", "List": "children", "Tuple": "children",
    "Dict": "children", "Set": "children", "Starred": "children",
    "keyword": "children",
    "Call": "call", "Await": "await", "Lambda": "lambda",
    "ListComp": "comp", "SetComp": "comp", "DictComp": "comp",
    "GeneratorExp": "comp", "comprehension": "comp",
    "arguments": "children", "arg": "leaf",
    # contexts and operators
    "Load": "leaf", "Store": "leaf", "Del": "leaf",
    "And": "leaf", "Or": "leaf",
    "Add": "leaf", "Sub": "leaf", "Mult": "leaf", "MatMult": "leaf",
    "Div": "leaf", "Mod": "leaf", "Pow": "leaf", "LShift": "leaf",
    "RShift": "leaf", "BitOr": "leaf", "BitXor": "leaf", "BitAnd": "leaf",
    "FloorDiv": "leaf", "Invert": "leaf", "Not": "leaf", "UAdd": "leaf",
    "USub": "leaf", "Eq": "leaf", "NotEq": "leaf", "Lt": "leaf",
    "LtE": "leaf", "Gt": "leaf", "GtE": "leaf", "Is": "leaf",
    "IsNot": "leaf", "In": "leaf", "NotIn": "leaf",
    # statements the walkers place
    "Expr": "stmt", "Assign": "stmt", "AugAssign": "stmt",
    "AnnAssign": "stmt", "Return": "stmt", "If": "stmt", "For": "stmt",
    "While": "stmt", "Try": "stmt", "ExceptHandler": "stmt",
    "AsyncWith": "stmt", "withitem": "stmt", "Raise": "stmt",
    "Pass": "stmt", "Break": "stmt", "Continue": "stmt",
    "ImportFrom": "stmt", "alias": "stmt", "Delete": "stmt",
    "Assert": "stmt",
    # never classified
    "NamedExpr": "refuse", "Yield": "refuse", "YieldFrom": "refuse",
    "Match": "refuse", "match_case": "refuse", "MatchValue": "refuse",
    "MatchSingleton": "refuse", "MatchSequence": "refuse",
    "MatchMapping": "refuse", "MatchClass": "refuse", "MatchStar": "refuse",
    "MatchAs": "refuse", "MatchOr": "refuse",
    "AsyncFor": "refuse", "With": "refuse", "TryStar": "refuse",
    "Global": "stmt", "Nonlocal": "refuse", "Import": "refuse",
    "FunctionDef": "stmt", "AsyncFunctionDef": "refuse",
    "ClassDef": "refuse",
    "TypeAlias": "refuse", "TypeVar": "refuse", "ParamSpec": "refuse",
    "TypeVarTuple": "refuse",
    "Module": "refuse", "Interactive": "refuse", "Expression": "refuse",
    "FunctionType": "refuse", "TypeIgnore": "refuse",
    # deprecated aliases and markers the parser no longer produces
    "Num": "refuse", "Str": "refuse", "Bytes": "refuse",
    "NameConstant": "refuse", "Ellipsis": "refuse", "Index": "refuse",
    "ExtSlice": "refuse", "Suite": "refuse", "Param": "refuse",
    "AugLoad": "refuse", "AugStore": "refuse",
}


def concrete_ast_classes():
    """Every concrete class under ast.AST in the running interpreter: a class
    with no subclass of its own."""
    out, todo = set(), [_ast.AST]
    while todo:
        c = todo.pop()
        subs = c.__subclasses__()
        if subs:
            todo.extend(subs)
        elif c is not _ast.AST:
            out.add(c.__name__)
    return out


def table_gaps():
    """Concrete ast classes NODE_TABLE does not name (must be empty)."""
    return sorted(concrete_ast_classes() - set(NODE_TABLE))


def _rule(node):
    rule = NODE_TABLE.get(type(node).__name__)
    if rule is None:
        raise Unclassified((getattr(node, "lineno", 0),
                            f"a node class the table does not name: "
                            f"{type(node).__name__}"))
    return rule


# --- stores ---------------------------------------------------------------

# Methods that change the value they are called on: a call of one on a name
# is a store of that name (state carry, ruling REHEARSAL-FOUR-R3 item b).
MUTATING_METHODS = frozenset({
    "append", "extend", "update", "clear", "pop", "setdefault", "add",
    "remove", "discard", "insert", "sort", "reverse", "popitem",
    "difference_update", "intersection_update", "symmetric_difference_update",
})


def stores(node):
    """The local names `node` stores: an assignment, augmented assignment
    (`|=`, `+=`, ...), annotated assignment, deletion, loop or comprehension
    target, or a call of a mutating method on the name
    (`others.extend(still)`)."""
    out = set()
    for n in _ast.walk(node):
        if isinstance(n, _ast.Name) and isinstance(n.ctx, (_ast.Store, _ast.Del)):
            out.add(n.id)
        elif (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
              and n.func.attr in MUTATING_METHODS):
            base = n.func.value
            while isinstance(base, (_ast.Attribute, _ast.Subscript)):
                base = base.value
            if isinstance(base, _ast.Name):
                out.add(base.id)
        elif isinstance(n, (_ast.AugAssign,)):
            base = n.target
            while isinstance(base, (_ast.Attribute, _ast.Subscript)):
                base = base.value
            if isinstance(base, _ast.Name):
                out.add(base.id)
        elif isinstance(n, (_ast.Assign, _ast.AnnAssign)):
            for tg in (n.targets if isinstance(n, _ast.Assign) else [n.target]):
                base = tg
                while isinstance(base, (_ast.Attribute, _ast.Subscript)):
                    base = base.value
                if isinstance(base, _ast.Name):
                    out.add(base.id)
    return out


# --- SQL, lexer-first -----------------------------------------------------

SqlLists = _collections.namedtuple("SqlLists", "read setting write syntax")

_SQL_END_WORDS = frozenset({"commit", "rollback", "begin", "savepoint",
                            "release", "abort", "end", "prepare", "start"})
_SQL_OTHER_COMMANDS = frozenset({
    "merge", "truncate", "copy", "call", "lock", "grant", "revoke", "alter",
    "drop", "vacuum", "analyze", "notify", "listen", "unlisten", "reset",
    "discard", "refresh", "cluster", "reindex", "comment", "security",
    "import", "load", "checkpoint", "execute", "deallocate",
})
_DML = frozenset({"insert", "update", "delete"})


def bound_names(fn):
    """Every name function definition `fn` binds, in any form other than a
    mutation of its value (Bindings): a bound name is never the module's
    value (findings closed_walk:699 and :322)."""
    return Bindings(None, fn).bound()


def _body_bindings(stmts):
    """The names statements `stmts` bind (bound_names)."""
    return Bindings(None, stmts=stmts).bound()


def _root_through(expr):
    """The name an attribute or item chain starts from (`a` of `a.b[c].d`),
    else None."""
    while isinstance(expr, (_ast.Attribute, _ast.Subscript)):
        expr = expr.value
    return expr.id if isinstance(expr, _ast.Name) else None


_MISSING = object()
# The most SQL texts one statement may stand for (every combination of its
# formatted values); more is refused.
SQL_COMBINATIONS = 256


def _arg_names(a):
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs
            + [y for y in (a.vararg, a.kwarg) if y is not None]]


class Bindings:
    """THE resolver of the closed walk (ruling REHEARSAL-FOUR-R5 item 2).

    Every name a walk gives a meaning to is resolved here and nowhere else:
    a callee, a SQL constant, template, table or builder, a guard's name and
    its collection, an import, a local function, a class, the session, and
    every name a statement walker identifies by its spelling (the barrier,
    the admission gate, the raised refusal, the answer classes). The rule is
    one binding per name:

      * a name the walked function (or statement list) does not bind
        resolves in the module `scope`;
      * a name it binds exactly once resolves to that binding (a
        parameter, an assignment, an import, a local definition), never to
        the module's value;
      * a name it binds more than once is refused: resolve raises
        Unclassified naming it.

    A binding is any store of the name: a parameter; an assignment,
    augmented or annotated assignment or deletion; a loop, with, except,
    comprehension or walrus target; an import; a local definition; a
    global or nonlocal declaration; a match capture; and a mutation of the
    value the name holds (a mutating method call, an item or attribute
    store). Nested definitions, lambdas and comprehensions are counted with
    the function: a superset, so more refusals and never fewer.

    One recorded deviation from "exactly one": a local SQL name may be
    extended by `+=` outside any loop (real spans do: match_hold's
    `sql += " FOR NO KEY UPDATE"`, main's `_sql += " AND ..."`). local_sql
    reads EVERY binding of such a name (each assignment's arms, each
    suffix) and refuses the name when any binding is not one it reads, so
    the texts it gives are a superset of every path's.

    test_r5_every_resolution_site_goes_through_the_resolver counts, in each
    function span of the walkers, the sites that look a walked name up (a
    getattr keyed by a name read from the tree, a comparison of a walked
    name's spelling, a lookup in a name table, an import) and the sites
    inside this class, and asserts the two counts are equal."""

    def __init__(self, scope, fn=None, stmts=None, session="db"):
        self.scope = scope
        self.session = session
        self.sites = {}
        self.has_fn = fn is not None
        self._enumerated = set()
        nodes = []
        if fn is not None:
            for x in _arg_names(fn.args):
                self._add(x, "param", fn)
            nodes = list(fn.body) + list(fn.args.defaults) + [
                x for x in fn.args.kw_defaults if x is not None]
        if stmts is not None:
            nodes = list(stmts)
        for top in nodes:
            for n in _ast.walk(top):
                self._collect(n)

    def _add(self, name, kind, node):
        self.sites.setdefault(name, []).append((kind, node))

    def _collect(self, n):
        if isinstance(n, _ast.Name) and not isinstance(n.ctx, _ast.Load):
            self._add(n.id, "local", n)
        elif isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            self._add(n.name, "def", n)
            for x in _arg_names(n.args):
                self._add(x, "param", n)
        elif isinstance(n, _ast.ClassDef):
            self._add(n.name, "def", n)
        elif isinstance(n, _ast.Lambda):
            for x in _arg_names(n.args):
                self._add(x, "param", n)
        elif isinstance(n, (_ast.Import, _ast.ImportFrom)):
            for x in n.names:
                self._add((x.asname or x.name).split(".")[0], "import", (n, x))
        elif isinstance(n, _ast.ExceptHandler) and n.name:
            self._add(n.name, "local", n)
        elif isinstance(n, (_ast.Global, _ast.Nonlocal)):
            for nm in n.names:
                self._add(nm, "global", n)
        elif isinstance(n, (_ast.MatchAs, _ast.MatchStar)) and n.name:
            self._add(n.name, "local", n)
        elif isinstance(n, _ast.MatchMapping) and n.rest:
            self._add(n.rest, "local", n)
        elif (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
              and n.func.attr in MUTATING_METHODS):
            r = _root_through(n.func.value)
            if r is not None and r not in self.roots():
                # A session root's method (`db.add(row)`) is a session call
                # the walk classifies as one, not a binding of the root.
                self._add(r, "mutated", n)
        if isinstance(n, (_ast.Assign, _ast.AugAssign, _ast.AnnAssign,
                          _ast.Delete)):
            tgs = (n.targets if isinstance(n, (_ast.Assign, _ast.Delete))
                   else [n.target])
            for tg in tgs:
                for t in _ast.walk(tg):
                    if isinstance(t, (_ast.Attribute, _ast.Subscript)):
                        r = _root_through(t)
                        if r is not None and r not in self.roots():
                            self._add(r, "mutated", n)
                            break

    # --- the rule ---------------------------------------------------------

    def count(self, name):
        """How many bindings the walked function gives `name`."""
        return len(self.sites.get(name, ()))

    def bound(self):
        """The names bound other than by a mutation (bound_names)."""
        return frozenset(k for k, v in self.sites.items()
                         if any(kind != "mutated" for kind, _n in v))

    def resolve(self, name, line=0):
        """(kind, what) for `name`: ('module', the module's value or
        _MISSING) when the function does not bind it; its one binding
        ('param', 'local', 'import', 'def', 'global' or 'mutated', node)
        when it binds it once; refused when it binds it more than once."""
        got = self.sites.get(name, ())
        if len(got) > 1:
            raise Unclassified((line, f"a name bound more than once: {name}"))
        if got:
            return got[0]
        return ("module", getattr(self.scope, name, _MISSING))

    def module(self, name, line=0):
        """The module's value of `name` when the function does not bind it;
        None when it binds it once or the module holds no such name."""
        kind, v = self.resolve(name, line)
        return v if kind == "module" and v is not _MISSING else None

    def spelled(self, node, name, line=0):
        """Whether `node` is the plain name `name`, read by a walk as the
        module's (the barrier, the admission gate, an answer class, the
        raised refusal); refused when the walked function binds it."""
        if not (isinstance(node, _ast.Name) and node.id == name):
            return False
        line = line or getattr(node, "lineno", 0)
        kind, _v = self.resolve(name, line)
        if kind != "module":
            raise Unclassified((line, f"{name}, a name the walk reads as the "
                                      "module's, is bound by the function"))
        return True

    def named(self, node, names, line=0):
        """The name of `names` that plain name `node` denotes as a function
        of its module: the module's own (the function does not bind it), or
        bound once by `from <module> import <name>` in the function, not
        renamed and not relative (match_hold imports the gate so); None when
        `node` spells none of them; refused when the function binds it in
        any other way."""
        if not (isinstance(node, _ast.Name) and node.id in names):
            return None
        line = line or getattr(node, "lineno", 0)
        kind, v = self.resolve(node.id, line)
        if kind == "module":
            return node.id
        if kind == "import":
            imp, alias = v
            if (isinstance(imp, _ast.ImportFrom) and imp.module
                    and not imp.level and alias.name == node.id):
                return node.id
        raise Unclassified((line, f"{node.id}, a name the walk reads as the "
                                  "module's, is bound by the function"))

    def spelled_any(self, node, names, line=0):
        """The name of `names` that plain name `node` spells (spelled), or
        None."""
        for name in names:
            if self.spelled(node, name, line):
                return name
        return None

    def spelled_once(self, node, name, kinds=("param", "local"), line=0):
        """Whether `node` is the plain name `name` bound exactly once by the
        function, as one of `kinds` (a walk's own parameter or loop
        target); refused when it is bound otherwise."""
        if not (isinstance(node, _ast.Name) and node.id == name):
            return False
        line = line or getattr(node, "lineno", 0)
        kind, _n = self.resolve(name, line)
        if kind not in kinds:
            raise Unclassified((line, f"{name} is not bound exactly once as "
                                      f"{' or '.join(kinds)}"))
        return True

    def listed(self, node, table, line=0):
        """The spelling of callee `node` when `table` lists it (a pure
        call, a pure await, an opaque helper) and the walked function does
        not bind its root, so it is the module's; None when `table` does
        not list it; refused when it does and the function binds the root."""
        name = _ast.unparse(node)
        if name not in table:
            return None
        root = _root(node)
        line = line or getattr(node, "lineno", 0)
        if root is None or not self._module_object(root, line):
            raise Unclassified((line, f"a call of {name}, a name the "
                                      "function binds"))
        return name

    def _module_object(self, name, line=0):
        """Whether `name` denotes the module's own object: the function does
        not bind it, or binds it once by an import of that same object
        (team_queue_poll's `import uuid as uuid_mod` beside the module's)."""
        kind, v = self.resolve(name, line)
        if kind == "module":
            return True
        if kind != "import":
            return False
        imp, alias = v
        held = getattr(self.scope, name, _MISSING)
        if isinstance(imp, _ast.Import):
            if alias.asname is None and "." in alias.name:
                return False
            if held is _MISSING:
                # a local import of a standard-library module under the
                # listed spelling (`import uuid as uuid_mod`): it reaches no
                # session
                return alias.name.split(".")[0] in _sys.stdlib_module_names
            return _importlib.import_module(alias.name) is held
        if (isinstance(imp, _ast.ImportFrom) and imp.module and not imp.level
                and held is not _MISSING):
            return getattr(_importlib.import_module(imp.module), alias.name,
                           _MISSING) is held
        return False

    def spelled_in(self, node, names, kinds=("param", "local"), line=0):
        """The name of `names` that plain name `node` spells when the
        function binds it exactly once as one of `kinds` (spelled_once);
        None when it spells none of them."""
        for name in names:
            if self.spelled_once(node, name, kinds, line):
                return name
        return None

    def same(self, a, b, kinds=("param", "local"), line=0):
        """Whether plain names `a` and `b` spell one name the function binds
        exactly once as one of `kinds` (a loop counter read back, a
        variable compared with its own earlier binding)."""
        if not (isinstance(a, _ast.Name) and isinstance(b, _ast.Name)
                and a.id == b.id):
            return False
        return self.spelled_once(a, a.id, kinds, line)

    def every_binding(self, name, kinds=("local",), line=0):
        """Every binding of `name`, as nodes, for a walk that accounts for
        each one itself (an attempt budget: opened, spent and floored by
        name); refused when any binding is not one of `kinds`. The name is
        then read as enumerated by `text` and `reads`."""
        got = self.sites.get(name, ())
        for kind, node in got:
            if kind not in kinds:
                raise Unclassified((line, f"{name} is bound as a {kind}; the "
                                          f"walk reads it only as "
                                          f"{' or '.join(kinds)}"))
        self._enumerated.add(name)
        return [node for _kind, node in got]

    def _module_or_enumerated(self, x, line):
        if x.id in self._enumerated:
            return
        if self.resolve(x.id, line)[0] != "module":
            raise Unclassified((line, f"{x.id}, a name the walk reads as the "
                                      "module's, is bound by the function"))

    def text(self, node, line=0):
        """The source text of `node` for a comparison against a fixed
        expression (`range(1, FORMATION_MAX_ATTEMPTS + 1)`, `<budget> > 0`),
        once every name it reads is the module's or was enumerated
        (every_binding); refused otherwise."""
        line = line or getattr(node, "lineno", 0)
        for x in _ast.walk(node):
            if isinstance(x, _ast.Name):
                self._module_or_enumerated(x, line)
        return _ast.unparse(node)

    def reads(self, node, name, line=0):
        """Whether `node` reads the plain name `name`, which is then the
        module's or was enumerated (every_binding); refused otherwise."""
        hit = [x for x in _ast.walk(node) if isinstance(x, _ast.Name)
               and isinstance(x.ctx, _ast.Load) and x.id == name]
        for x in hit:
            self._module_or_enumerated(x, line or getattr(x, "lineno", 0))
        return bool(hit)

    def is_root(self, node):
        """Whether plain name `node` is one of the session roots."""
        return isinstance(node, _ast.Name) and node.id in self.roots()

    def is_param(self, name):
        """Whether the function binds `name` exactly once, as a parameter."""
        got = self.sites.get(name, ())
        return len(got) == 1 and got[0][0] == "param"

    # --- the session ------------------------------------------------------

    def _sessions(self):
        return ((self.session,) if isinstance(self.session, str)
                else tuple(self.session))

    def roots(self):
        """The names the session spellings start from ('db'; 'ctx' of
        'ctx.db')."""
        return frozenset(s.split(".")[0] for s in self._sessions())

    def is_session(self, expr):
        """Whether expression `expr` spells the session."""
        return _ast.unparse(expr) in self._sessions()

    def session_value(self, expr):
        """Whether `expr` evaluates the session or a value it is reached
        from: a session spelling, or a bare root name ('db', 'ctx')."""
        return self.is_session(expr) or (
            isinstance(expr, _ast.Name) and expr.id in self.roots())

    def session_root_ok(self, expr, line=0):
        """Refused unless the name session spelling `expr` starts from is
        the walked function's own parameter, bound exactly once (finding
        closed_walk:1005: the session through an alias)."""
        root = _root(expr) if not isinstance(expr, _ast.Name) else expr.id
        ok = self.is_param(root) if self.has_fn else self.count(root) == 0
        if not ok:
            raise Unclassified((line, f"the session {root} is not the "
                                      "function's own parameter, bound once"))

    def opaque_callee(self, func, opaque, line=0):
        """The opaque helper plain name `func` calls: the scope's function
        (callee), or else its definition when `opaque` maps names to the
        definitions the caller reads separately."""
        fn = self.callee(func, line)
        if fn is None and isinstance(opaque, dict):
            fn = opaque.get(func.id)
        return fn

    def session_argument(self, call, arg, fn, line=0):
        """A session value passed as an argument of call `call` of function
        `fn` is classified only when it binds `fn`'s parameter of the same
        name (the helper's own session); refused otherwise (finding
        closed_walk:1005: a plain parameter `session` took `db`)."""
        name = _ast.unparse(arg).split(".")[-1]
        if isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            params = [x.arg for x in fn.args.posonlyargs + fn.args.args]
        else:
            params = (list(_inspect.signature(fn).parameters)
                      if fn is not None else [])
        bound = None
        for i, a in enumerate(call.args):
            if a is arg and i < len(params):
                bound = params[i]
        for k in call.keywords:
            if k.value is arg:
                bound = k.arg
        if bound != name or not (isinstance(arg, _ast.Name)
                                 or self.is_session(arg)):
            raise Unclassified((line, f"the session as a value: "
                                      f"{_ast.unparse(arg)} passed to "
                                      f"{getattr(fn, '__name__', '?')}"))

    # --- callees ----------------------------------------------------------

    def callee(self, func, line=0):
        """The Python function a callee expression names: a plain name the
        function does not bind, or imports once (`from m import f`); a
        module attribute (`_match_hold._hold_latch`) whose module name the
        function does not bind; `<accessor>().f` of a module accessor. None
        otherwise; a name bound more than once is refused."""
        line = line or getattr(func, "lineno", 0)
        obj = None
        if isinstance(func, _ast.Name):
            kind, v = self.resolve(func.id, line)
            if kind == "import":
                imp, alias = v
                if not (isinstance(imp, _ast.ImportFrom) and imp.module
                        and not imp.level):
                    return None
                obj = getattr(_importlib.import_module(imp.module),
                              alias.name, None)
            elif kind == "module" and v is not _MISSING:
                obj = v
        elif isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Name):
            mod = self.module(func.value.id, line)
            obj = getattr(mod, func.attr, None) if mod is not None else None
        elif (isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Call)
              and isinstance(func.value.func, _ast.Name) and not func.value.args
              and not func.value.keywords):
            mod = self.module_accessor(self.module(func.value.func.id, line))
            obj = getattr(mod, func.attr, None) if mod is not None else None
        obj = _inspect.unwrap(obj) if callable(obj) else None
        return obj if _inspect.isfunction(obj) else None

    @staticmethod
    def module_accessor(fn):
        """The module a module accessor returns: a plain function of no
        parameters whose body is exactly `import <m>` then `return <m>`
        (after an optional docstring), such as main._mrw_mod. None for
        anything else."""
        if not _inspect.isfunction(fn) or _inspect.signature(fn).parameters:
            return None
        try:
            d = _helper_tree(fn)
        except (Unclassified, OSError, TypeError):
            return None
        body = [s for s in d.body if not (isinstance(s, _ast.Expr)
                                          and isinstance(s.value, _ast.Constant))]
        if not (len(body) == 2 and isinstance(body[0], _ast.Import)
                and len(body[0].names) == 1 and body[0].names[0].asname is None
                and isinstance(body[1], _ast.Return)
                and isinstance(body[1].value, _ast.Name)
                and body[1].value.id == body[0].names[0].name):
            return None
        return _importlib.import_module(body[0].names[0].name)

    def namedtuple_class(self, func, line=0):
        """The class plain name `func` names when it is a class
        collections.namedtuple made (finding closed_walk:759: a `_fields`
        marker granted purity to a class whose own __new__ wrote): its only
        base is tuple, it defines no __init__, and its __new__ is the one
        namedtuple generates (evaluated in namedtuple's own namespace, not
        a module's). None otherwise."""
        if not isinstance(func, _ast.Name):
            return None
        obj = self.module(func.id, line or getattr(func, "lineno", 0))
        if not (isinstance(obj, type) and obj.__bases__ == (tuple,)
                and "__init__" not in vars(obj)):
            return None
        new = vars(obj).get("__new__")
        new = getattr(new, "__func__", new)
        g = getattr(new, "__globals__", None)
        if not (isinstance(g, dict)
                and g.get("__name__") == f"namedtuple_{obj.__name__}"
                and g.get("_tuple_new") is tuple.__new__):
            return None
        return obj

    # --- SQL --------------------------------------------------------------

    def sql_texts(self, node, guarded=None):
        """Every SQL text a `text(...)` argument can hold, or None: a string
        constant; a module string the function does not bind; an f-string
        whose formatted values are each a module string, a guarded name (its
        collection's values) or a module table's item (the table's values),
        in every combination (finding closed_walk:326: a placeholder hid a
        guarded name in a function position, so the real value is
        classified instead); or a `+` of these."""
        guarded = guarded or {}
        if isinstance(node, _ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, _ast.Name):
            if self.count(node.id):
                # the function's own name: read with every one of its
                # bindings by local_sql, never as the module's
                return None
            v = self.module(node.id, node.lineno)
            return [v] if isinstance(v, str) else None
        if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Add):
            return _combine([self.sql_texts(node.left, guarded),
                             self.sql_texts(node.right, guarded)])
        if isinstance(node, _ast.JoinedStr):
            parts = []
            for v in node.values:
                if isinstance(v, _ast.Constant):
                    parts.append([v.value])
                elif isinstance(v, _ast.FormattedValue):
                    if v.format_spec is not None or v.conversion != -1:
                        return None
                    parts.append(self._formatted(v.value, guarded))
                else:
                    return None
            return _combine(parts)
        return None

    def _formatted(self, inner, guarded):
        if isinstance(inner, _ast.Name) and inner.id in guarded:
            return list(guarded[inner.id])
        if isinstance(inner, _ast.Name):
            held = self.module(inner.id, inner.lineno)
            return [held] if isinstance(held, str) else None
        if isinstance(inner, _ast.Subscript) and isinstance(inner.value, _ast.Name):
            table = self.module(inner.value.id, inner.lineno)
            if isinstance(table, dict) and table and all(
                    isinstance(x, str) and _re.fullmatch(r"[a-z_][a-z_0-9]*", x)
                    for x in table.values()):
                return sorted(set(table.values()))
        return None

    def guards(self, tree):
        """{name: (ids of the nodes its guard proves it at, the values it may
        hold)} for the names the function guards as identifiers before use:
        a statement `if <name> not in <COLLECTION>: raise ...` (every path
        of its body raises), where <name> is bound exactly once by the
        function and never in the guard's own branches, and <COLLECTION> a
        module tuple or frozenset the function does not bind or mutate,
        holding only lower-case identifiers (finding closed_walk:501: a
        rebinding in the guard's else, and a mutated list, kept their
        proof). The proof covers the statements after the guard in its own
        block, up to (not including) the first that stores the name
        (finding closed_walk:345)."""
        out = {}
        blocks = []
        for n in _ast.walk(tree):
            for field in ("body", "orelse", "finalbody"):
                b = getattr(n, field, None)
                if isinstance(b, list) and b and isinstance(b[0], _ast.stmt):
                    blocks.append(b)
        for b in blocks:
            for i, n in enumerate(b):
                test = getattr(n, "test", None)
                if not (isinstance(n, _ast.If) and isinstance(test, _ast.Compare)
                        and isinstance(test.left, _ast.Name) and len(test.ops) == 1
                        and isinstance(test.ops[0], _ast.NotIn)
                        and isinstance(test.comparators[0], _ast.Name)
                        and all_paths_raise(n.body)):
                    continue
                name = test.left.id
                if self.count(name) != 1 or self.sites[name][0][0] not in (
                        "param", "local"):
                    continue
                coll = self.module(test.comparators[0].id, n.lineno)
                if not (isinstance(coll, (frozenset, tuple)) and coll
                        and all(isinstance(x, str)
                                and _re.fullmatch(r"[a-z_][a-z_0-9]*", x)
                                for x in coll)):
                    continue
                ids, _vals = out.setdefault(name, (set(), tuple(sorted(set(coll)))))
                for later in b[i + 1:]:
                    if name in _body_bindings([later]):
                        break
                    ids.update(id(x) for x in _ast.walk(later))
        return {k: (frozenset(ids), vals) for k, (ids, vals) in out.items()}

    def local_sql(self, tree):
        """{local name: [SQL texts]} for each name EVERY binding of which
        is one this reads: an assignment of SQL sql_texts reads (directly,
        as either arm of a conditional expression, or as
        `<MODULE_TEMPLATE>.format(k=<sql or a conditional>)`, every
        combination), or `<name> += <sql>` outside any loop (every text with
        and without each suffix). A name with any other binding (a
        parameter, a loop target, a mutation, a second kind) is left out,
        so a local SQL name stands for a superset of every path's text."""
        binds, suffixes, seen = {}, {}, {}
        looped = {id(x) for lp in _ast.walk(tree)
                  if isinstance(lp, (_ast.For, _ast.While, _ast.AsyncFor))
                  for x in _ast.walk(lp)}

        def arms(v):
            if isinstance(v, _ast.IfExp):
                a, b = self.sql_texts(v.body), self.sql_texts(v.orelse)
                return None if a is None or b is None else a + b
            return self.sql_texts(v)

        for n in _ast.walk(tree):
            if (isinstance(n, _ast.Assign) and len(n.targets) == 1
                    and isinstance(n.targets[0], _ast.Name)):
                name, v = n.targets[0].id, n.value
                seen[name] = seen.get(name, 0) + 1
                tmpl = (self.module(v.func.value.id, n.lineno)
                        if isinstance(v, _ast.Call)
                        and isinstance(v.func, _ast.Attribute)
                        and v.func.attr == "format"
                        and isinstance(v.func.value, _ast.Name) else None)
                if isinstance(tmpl, str) and not v.args and all(
                        k.arg for k in v.keywords):
                    combos = [{}]
                    for k in v.keywords:
                        opts = arms(k.value)
                        if opts is None:
                            combos = None
                            break
                        combos = [dict(c, **{k.arg: o}) for c in combos for o in opts]
                    texts = (None if combos is None
                             else [tmpl.format(**c) for c in combos])
                else:
                    texts = arms(v)
                binds.setdefault(name, []).append(texts)
            elif (isinstance(n, _ast.AugAssign) and isinstance(n.op, _ast.Add)
                  and isinstance(n.target, _ast.Name)):
                name = n.target.id
                seen[name] = seen.get(name, 0) + 1
                s = self.sql_texts(n.value)
                if id(n) in looped or s is None or len(s) != 1:
                    binds.setdefault(name, []).append(None)
                else:
                    suffixes.setdefault(name, []).append(
                        (n.lineno, n.col_offset, s[0]))
        out = {}
        for name in set(binds) | set(suffixes):
            if seen.get(name) != self.count(name):
                continue        # a binding this does not read
            assigned = binds.get(name, [])
            if not assigned or any(t is None for t in assigned):
                continue
            texts = [x for t in assigned for x in t]
            for _line, _col, s in sorted(suffixes.get(name, [])):
                texts = texts + [x + s for x in texts]
            if len(texts) <= SQL_COMBINATIONS:
                out[name] = texts
        return out

    def builder_texts(self, func, line=0, call=None, pure=None):
        """The SQL texts a plain builder function can return, or [None].

        First, read: every `return` of it read by sql_texts through its own
        bindings (a name the builder binds is read as none), the builder
        standing for the union of them all (finding closed_walk:441: a
        builder was read by calling it on sampled keys, so an unsampled
        branch was missed).

        Otherwise, its whole argument domain, proved: the call `call` passes
        one positional argument per parameter (no defaults, nothing else),
        each parameter is bound once and read ONLY as the key of a module
        dict (`_SERIES_TABLE[mode]`), so the builder can depend on it only
        through those lookups and can return without raising only for a key
        all of its tables hold; `pure(fn)` (the walk's plain_effects) finds
        no effect in its body; and the builder is called on every
        combination of those keys, each answer a str. Anything else is
        [None]."""
        fn = self.callee(func, line)
        if fn is None or _inspect.iscoroutinefunction(fn):
            return [None]
        d = _helper_tree(fn)
        b = Bindings(_inspect.getmodule(fn), d, session=self.session)
        out = []
        for r in _own_nodes(d, _ast.Return):
            texts = b.sql_texts(r.value) if r.value is not None else None
            if texts is None:
                out = None
                break
            out.extend(texts)
        if out:
            return out
        return b._builder_domain_texts(fn, d, call, pure) or [None]

    def _builder_domain_texts(self, fn, d, call, pure):
        a = d.args
        params = [x.arg for x in a.posonlyargs + a.args]
        if (call is None or pure is None or a.vararg or a.kwarg
                or a.kwonlyargs or a.defaults or call.keywords
                or len(call.args) != len(params)
                or any(isinstance(x, _ast.Starred) for x in call.args)):
            return None
        keys = {p: None for p in params}
        subs = {}
        for x in _ast.walk(d):
            if (isinstance(x, _ast.Subscript) and isinstance(x.slice, _ast.Name)
                    and x.slice.id in keys):
                subs[id(x.slice)] = x
        for x in _ast.walk(d):
            if not (isinstance(x, _ast.Name) and x.id in keys):
                continue
            if self.count(x.id) != 1 or not self.is_param(x.id):
                return None
            sub = subs.get(id(x))
            table = (self.module(sub.value.id) if sub is not None
                     and isinstance(sub.value, _ast.Name) else None)
            # a plain dict: a subclass (a defaultdict) answers keys it
            # does not hold
            if not (isinstance(x.ctx, _ast.Load) and type(table) is dict):
                return None
            got = frozenset(table)
            keys[x.id] = got if keys[x.id] is None else keys[x.id] & got
        if any(v is None for v in keys.values()) or pure(fn):
            return None
        combos = [[]]
        for p in params:
            combos = [c + [k] for c in combos for k in sorted(keys[p], key=repr)]
            if len(combos) > SQL_COMBINATIONS:
                return None
        out = []
        for c in combos:
            got = fn(*c)
            if not isinstance(got, str):
                return None
            out.append(got)
        return out

    def execute_kind(self, call, lists, local=None, guarded=frozenset(),
                     pure=None):
        """'read', 'lock' or 'write' when `call` is `<session>.execute(
        text(<sql>), <binds>)` with SQL sql_texts (or a local SQL name, or a
        builder) reads in every combination and sql_kind classifies each;
        raises Unclassified otherwise."""
        first = call.args[0] if call.args else None
        if not (isinstance(first, _ast.Call) and len(first.args) == 1
                and not first.keywords and self.spelled(first.func, "text")):
            raise Unclassified((call.lineno, "an execute of something other "
                                             "than text(<sql>)"))
        if any(isinstance(a, _ast.Starred) for a in call.args) or any(
                k.arg is None for k in call.keywords):
            raise Unclassified((call.lineno, "an execute with unpacked arguments"))
        arg = first.args[0]
        if isinstance(guarded, dict):
            guarded = {n: vals for n, (ids, vals) in guarded.items()
                       if id(call) in ids}
        else:
            guarded = {}
        sqls = self.sql_texts(arg, guarded)
        if sqls is None and isinstance(arg, _ast.Name) and local is not None:
            sqls = local.get(arg.id) if self.count(arg.id) else None
        elif (sqls is None and isinstance(arg, _ast.Call)
              and isinstance(arg.func, _ast.Name) and not arg.keywords
              and not any(isinstance(a, _ast.Starred) for a in arg.args)):
            sqls = self.builder_texts(arg.func, call.lineno, arg, pure)
        if not sqls or None in sqls:
            raise Unclassified((call.lineno, "an execute whose SQL the walk "
                                             "cannot read"))
        try:
            kinds = {sql_kind(s, lists) for s in sqls}
        except Unclassified as e:
            raise Unclassified((call.lineno, e.args[0][1])) from None
        return ("write" if "write" in kinds else "lock" if "lock" in kinds
                else "read")


def _combine(parts):
    """Every concatenation of one text from each list in `parts`; None when
    any part is None or there are more than SQL_COMBINATIONS."""
    out = [""]
    for p in parts:
        if p is None:
            return None
        out = [a + b for a in out for b in p]
        if len(out) > SQL_COMBINATIONS:
            return None
    return out


def _own_nodes(d, cls):
    """The nodes of class `cls` in definition `d`'s body, outside any nested
    definition or lambda."""
    out, todo = [], list(d.body)
    while todo:
        n = todo.pop()
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                          _ast.ClassDef, _ast.Lambda)):
            continue
        if isinstance(n, cls):
            out.append(n)
        todo.extend(_ast.iter_child_nodes(n))
    return out


def finally_exits(stmts):
    """The return, break and continue statements that leave the `finally`
    block `stmts` (finding closed_walk:1217: `finally: return None` swallowed
    a rollback-then-raise): a return anywhere in it outside a nested
    definition, and a break or continue not inside a loop of its own."""
    out = []

    def scan(block, in_loop):
        for st in block:
            if isinstance(st, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                               _ast.ClassDef)):
                continue
            if isinstance(st, _ast.Return):
                out.append(st)
            elif isinstance(st, (_ast.Break, _ast.Continue)) and not in_loop:
                out.append(st)
            elif isinstance(st, (_ast.For, _ast.AsyncFor, _ast.While)):
                scan(st.body, True)
                scan(st.orelse, in_loop)
            else:
                for field in ("body", "orelse", "finalbody"):
                    scan(getattr(st, field, None) or [], in_loop)
                for h in getattr(st, "handlers", None) or []:
                    scan(h.body, in_loop)
                for c in getattr(st, "cases", None) or []:
                    scan(c.body, in_loop)

    scan(stmts, False)
    return out


def _root(expr):
    """The name a dotted spelling starts from (`a` of `a.b.c`), else None."""
    while isinstance(expr, _ast.Attribute):
        expr = expr.value
    return expr.id if isinstance(expr, _ast.Name) else None


def sql_tokens(sql):
    """The lexer's tokens of `sql` as (kind, value, start, end), kind
    'ident' (lower-cased), 'qident' (as written), 'string', 'dollar' or
    'punct'; raises Unclassified for SQL the lexer refuses, dollar quoting,
    a prefixed string (E'', U&'', B'', X'', N''), or a U& identifier."""
    try:
        code, mask, bodies = _lex_views(sql)
        toks = _lex_tokens(code, mask)
    except _LexError as e:
        raise Unclassified((0, f"SQL the lexer refuses: {e}")) from None
    if bodies or any(t[0] == "dollar" for t in toks):
        raise Unclassified((0, "dollar quoting in walked SQL"))
    for a, b in zip(toks, toks[1:]):
        if a[0] == "ident" and a[3] == b[2] and a[1] in (
                "e", "u", "b", "x", "n") and b[0] == "string":
            raise Unclassified((0, f"a {a[1].upper()}'' string in walked SQL"))
        if a[0] == "ident" and a[1] == "u" and a[3] == b[2] and b[1] == "&":
            raise Unclassified((0, "a U& form in walked SQL"))
    return toks


def sql_kind(sql, lists):
    """'read', 'lock' or 'write' for ONE statement of SQL text, from its
    lexer tokens; raises Unclassified for a transaction command, more than
    one statement, a head off the list, a command off the list, a function
    off the allow-lists, or any form sql_tokens refuses."""
    toks = sql_tokens(sql)
    while toks and toks[-1][1] == ";":
        toks = toks[:-1]
    if any(t[0] == "punct" and t[1] == ";" for t in toks):
        raise Unclassified((0, "more than one SQL statement"))
    if not toks or toks[0][0] != "ident":
        raise Unclassified((0, "SQL with no command word"))
    words = [t[1] if t[0] == "ident" else None for t in toks]
    head = words[0]
    if head in _SQL_END_WORDS:
        raise Unclassified((0, f"a transaction command in SQL text ({head.upper()})"))
    # Row-lock clauses: FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE, FOR KEY
    # SHARE. Their UPDATE is the clause's, not a command.
    lock, clause = False, set()
    for i, w in enumerate(words):
        if w == "for":
            for seq in (("update",), ("no", "key", "update"), ("share",),
                        ("key", "share")):
                if tuple(words[i + 1:i + 1 + len(seq)]) == seq:
                    lock = True
                    clause.update(range(i, i + 1 + len(seq)))
    # ON CONFLICT ... DO UPDATE / DO NOTHING belongs to an INSERT.
    for i, w in enumerate(words):
        if w == "do" and i > 0 and head == "insert":
            clause.add(i)
            if i + 1 < len(words) and words[i + 1] == "update":
                clause.add(i + 1)
    funcs = []
    for i, t in enumerate(toks[:-1]):
        if t[0] in ("ident", "qident") and toks[i + 1][1] == "(":
            prev = words[i - 1] if i else None
            if prev in ("into", "table", "exists") and t[0] in ("ident", "qident"):
                if prev == "into" or (prev in ("table", "exists") and head == "create"):
                    continue        # a table and its column list
            name = t[1]
            if t[0] == "ident" and name in lists.syntax:
                continue
            funcs.append((name, t[0] == "qident"))
    named = {n for n, _q in funcs}
    present = {w for k, w in enumerate(words) if w and k not in clause}
    if present & _SQL_OTHER_COMMANDS:
        raise Unclassified((0, "a SQL command off the allow-list: "
                               + ", ".join(sorted(present & _SQL_OTHER_COMMANDS))))
    if head == "create":
        # CREATE [TEMP|TEMPORARY|UNLOGGED] TABLE ... AS ...: a write.
        rest = [w for w in words[1:4] if w]
        if "table" in rest and "as" in present:
            bad = named - lists.read - lists.write
            if bad:
                raise Unclassified((0, "a SQL function off the write allow-list: "
                                       + ", ".join(sorted(bad))))
            return "write"
        raise Unclassified((0, "a SQL command off the allow-list: create"))
    if head in ("select", "with") and not (present & _DML) and "into" not in present:
        bad = named - lists.read - lists.setting
        if bad:
            raise Unclassified((0, "a SQL function off the read allow-list: "
                                   + ", ".join(sorted(bad))))
        return "lock" if lock or named & lists.setting else "read"
    if head in ("select", "with", "insert", "update", "delete"):
        if head == "select" and "into" in present and not (present & _DML):
            pass                # SELECT ... INTO creates a table: a write
        bad = named - lists.read - lists.write
        if bad:
            raise Unclassified((0, "a SQL function off the write allow-list: "
                                   + ", ".join(sorted(bad))))
        return "write"
    raise Unclassified((0, f"a SQL statement head off the allow-list ({head!r})"))


# --- SQL text a call executes: wrappers over the resolver ----------------

def sql_text(node, scope, guarded=frozenset(), bound=frozenset()):
    """The one SQL text a `text(...)` argument holds read in module `scope`
    (Bindings.sql_texts), or None when it holds none or more than one."""
    texts = Bindings(scope).sql_texts(node)
    return texts[0] if texts and len(texts) == 1 else None


def all_paths_raise(stmts):
    """Whether every path through `stmts` ends in a raise, with no await,
    return, break or continue on the way."""
    if not stmts or any(isinstance(x, (_ast.Await, _ast.Return, _ast.Break,
                                       _ast.Continue))
                        for s in stmts for x in _ast.walk(s)):
        return False
    last = stmts[-1]
    if isinstance(last, _ast.Raise):
        return True
    return (isinstance(last, _ast.If) and all_paths_raise(last.body)
            and all_paths_raise(last.orelse))


def guarded_names(tree, scope):
    """Bindings.guards of function `tree` (a definition, or a module of one)
    in `scope`."""
    fn = tree.body[0] if (isinstance(tree, _ast.Module)
                          and len(tree.body) == 1) else tree
    return Bindings(scope, fn if isinstance(
        fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)) else None).guards(tree)


def local_sql(tree, scope):
    """Bindings.local_sql of function `tree` (a definition, or a module of
    one) in `scope`."""
    fn = tree.body[0] if (isinstance(tree, _ast.Module)
                          and len(tree.body) == 1) else tree
    if isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
        return Bindings(scope, fn).local_sql(tree)
    return Bindings(scope, stmts=getattr(tree, "body", [])).local_sql(tree)


def is_session(expr, session="db"):
    """Whether expression `expr` spells the session: `session` is one
    spelling ('db') or a tuple of them (('db', 'ctx.db'))."""
    return Bindings(None, session=session).is_session(expr)


def is_db_call(call, attr, session="db"):
    return (isinstance(call, _ast.Call) and isinstance(call.func, _ast.Attribute)
            and is_session(call.func.value, session)
            and call.func.attr == attr)


def execute_kind(call, scope, lists, local=None, guarded=frozenset(),
                 bindings=None):
    """Bindings.execute_kind under `bindings` (the walked function's), or
    module `scope`'s when none is given."""
    return (bindings or Bindings(scope)).execute_kind(call, lists, local, guarded)


module_accessor = Bindings.module_accessor


def resolve_callee(func, scope, bindings=None):
    """Bindings.callee under `bindings` (the walked function's), or module
    `scope`'s when none is given."""
    return (bindings or Bindings(scope)).callee(func)


# --- the visitor ----------------------------------------------------------

# Session attributes that begin or end a transaction or a savepoint: the walk
# places them only at named shapes (an awaited `<session>.commit()` or
# `.rollback()` statement, a savepoint block); any other spelling is refused.
TXN_ATTRS = frozenset({"commit", "rollback", "begin", "begin_nested", "close",
                       "flush", "invalidate", "connection"})


_ACCEPT_TOKEN = object()


class Accepted:
    """The one acceptance outcome of the closed walk: `node` (an expression,
    or a helper definition's body) walked whole by the shared visitor, with
    the (shape, effect) list it gave. Only Visitor.accept constructs one
    (ruling REHEARSAL-FOUR-R4 item 1; test_closed_walk_acceptance_bound
    enumerates every construction site by AST); every other module can only
    pass one on or refuse."""

    __slots__ = ("node", "effects")

    def __init__(self, token, node, effects):
        if token is not _ACCEPT_TOKEN:
            raise TypeError("Accepted is constructed only by Visitor.accept")
        object.__setattr__(self, "node", node)
        object.__setattr__(self, "effects", tuple(effects))

    def __setattr__(self, name, value):
        raise TypeError("an Accepted outcome is not changed after the walk")


class Policy:
    """What one test file lets the visitor accept, all positive and named:
    the plain calls and methods that touch no session, the awaited library
    calls that touch none, the SQL allow-lists, and the scope names resolve
    in."""

    def __init__(self, scope, pure_calls, pure_methods, pure_awaits, sql,
                 session="db"):
        self.scope = scope
        self.pure_calls = frozenset(pure_calls)
        self.pure_methods = frozenset(pure_methods)
        self.pure_awaits = frozenset(pure_awaits)
        self.sql = sql
        self.session = session
        # An awaited helper's effect, when a file names its own reading of
        # helpers (the gate's kinds): called with the function, its result
        # is the effect recorded. Only the top-level walk of a span uses it;
        # helper bodies walked by def_effects never do.
        self.helper_hook = None
        self.helpers = {}           # (module, qualname) -> effects
        self.walking = set()        # helpers being walked now
        self.met = _collections.Counter()


# A plain (not awaited) function the walk resolves has its whole body walked
# (finding closed_walk:712), under the calling file's lists plus these: the
# builtins and library calls, and the methods on local values, that the real
# plain callees' bodies make. None of them takes a session; a session method
# is read by the session branch first, whatever its name.
PLAIN_BODY_CALLS = frozenset({
    "Counter", "_json.dumps", "_json.loads", "abs", "all", "any", "dict",
    "float", "getattr", "id", "isinstance", "len", "math.ceil", "max", "min", "repr",
    "hasattr", "set", "sorted", "sum", "timedelta", "tuple", "zip"})
PLAIN_BODY_METHODS = frozenset({
    "_asdict", "add", "isoformat", "items", "join", "lstrip", "pop", "sort", "split",
    "strip", "time", "total_seconds", "values"})


def plain_effects(fn, policy):
    """The effects of plain function `fn`'s body, walked by def_effects under
    `policy`'s lists plus the plain-body lists (one sub-policy per policy,
    sharing its met counter)."""
    sub = getattr(policy, "_plain_sub", None)
    if sub is None:
        sub = Policy(policy.scope, policy.pure_calls | PLAIN_BODY_CALLS,
                     policy.pure_methods | PLAIN_BODY_METHODS,
                     policy.pure_awaits, policy.sql, policy.session)
        sub.met = policy.met
        policy._plain_sub = sub
    return helper_effects(fn, sub)


def call_arguments(call):
    """Every argument expression of `call`, by kind, in source order:
    ('positional' | 'star' | 'keyword' | 'double-star', expression)."""
    out = []
    for a in call.args:
        out.append(("star", a.value) if isinstance(a, _ast.Starred)
                   else ("positional", a))
    for k in call.keywords:
        out.append(("double-star", k.value) if k.arg is None else ("keyword", k.value))
    return out


class Visitor:
    """Classify one expression (or a simple statement's value) under a
    Policy. `effects` collects (shape, effect) in evaluation order: shape
    'sql' (an execute), 'helper:<name>' (an awaited helper), 'end:<commit or
    rollback>' (a transaction end; only the helper walk permits these, at
    named shapes), 'callback:<param>' (an awaited callback parameter, only in
    a helper body), or 'call' (a plain call); effect 'read', 'lock', 'write'
    or 'pure'. Every name it gives a meaning to is resolved by `bindings`,
    the walked function's Bindings (one binding per name, ruling
    REHEARSAL-FOUR-R5 item 2)."""

    def __init__(self, policy, local=None, guarded=frozenset(), params=(),
                 permitted=frozenset(), helper=None, opaque=frozenset(),
                 bindings=None):
        self.p = policy
        self.b = (bindings if bindings is not None
                  else Bindings(policy.scope, session=policy.session))
        self.local = local
        self.guarded = guarded
        self.params = tuple(params)
        self.permitted = permitted
        self.helper = helper
        # opaque helpers: names, or {name: its definition} when the caller
        # reads helpers that are not functions of the scope
        self.opaque = opaque if isinstance(opaque, dict) else frozenset(opaque)
        # the local function definitions the helper walk walked (by id)
        self.walked_defs = set()
        self.effects = []
        # ids of the nodes inside a try body that has handlers, in the
        # function def_effects walks: a rollback-then-raise there is caught
        # (finding closed_walk:825).
        self.caught = frozenset()
        # Every node this visitor walked or read as a callee's spelling;
        # accept refuses an expression with a node outside it.
        self._walked_nodes = set()

    def _spelled(self, node):
        """`node`, a callee's spelling read whole by name (a resolved
        function, a session method, a listed call): none of it evaluates
        anything the walk has not classified."""
        self._walked_nodes.update(id(x) for x in _ast.walk(node))

    def accept(self, node, block=None):
        """The one constructor of Accepted. Walks `node` (an expression), or,
        with `block`, the helper definition `node` by calling block() (which
        walks its body through this visitor); then refuses if any expression
        inside it (for a definition: inside its body and its parameter
        defaults) was not walked."""
        start = len(self.effects)
        if block is None:
            self.visit(node)
            parts = [node]
        else:
            block()
            parts = list(node.body) + list(node.args.defaults) + [
                x for x in node.args.kw_defaults if x is not None]
        for part in parts:
            for x in _ast.walk(part):
                if isinstance(x, _ast.expr) and id(x) not in self._walked_nodes:
                    self.fail(x, f"an expression the walk did not classify: "
                                 f"{_ast.unparse(x)[:60]}")
        self.p.met["accepted"] += 1
        return Accepted(_ACCEPT_TOKEN, node, self.effects[start:])

    def fail(self, node, what):
        if self.helper is not None and not what.startswith(self.helper.__name__):
            what = f"{self.helper.__name__}: {what} at its line {getattr(node, 'lineno', 0)}"
            raise Unclassified((0, what))
        raise Unclassified((getattr(node, "lineno", 0), what))

    def _resolve(self, n, name):
        """Bindings.resolve, a refusal reported by this visitor."""
        try:
            return self.b.resolve(name, getattr(n, "lineno", 0))
        except Unclassified as e:
            self.fail(n, e.args[0][1])

    def _check(self, n, how, *args):
        """A resolver call `how(*args)`, a refusal reported by this visitor."""
        try:
            return how(*args)
        except Unclassified as e:
            self.fail(n, e.args[0][1])

    def _helper_args(self, n, call, fn):
        """Every argument of the awaited call `call` of walked helper `fn`:
        a session value is classified only as fn's same-named parameter
        (Bindings.session_argument), anything unpacked is refused, every
        other argument is visited."""
        for kind, a in call_arguments(call):
            if kind in ("star", "double-star"):
                self.fail(n, f"a call of {getattr(fn, '__name__', '?')} with "
                             "unpacked arguments")
            if self.b.session_value(a):
                self._check(n, self.b.session_root_ok, a, n.lineno)
                self._check(n, self.b.session_argument, call, a, fn, n.lineno)
                self._spelled(a)
            else:
                self.visit(a)

    def visit(self, n):
        rule = _rule(n)
        self._walked_nodes.add(id(n))
        self.p.met["node " + type(n).__name__] += 1
        if isinstance(n, (_ast.Name, _ast.Attribute)) and self.b.session_value(n):
            # The session is reached only as the receiver of a session call
            # the walk reads, or as the same-named parameter of a helper it
            # walks (finding closed_walk:1005: `s = db; s.add(row)`, and a
            # plain function's `session.add(row)` given `db`).
            self.fail(n, f"the session as a value: {_ast.unparse(n)}")
        if rule == "leaf":
            return
        if rule == "refuse" or rule == "stmt":
            self.fail(n, f"a {type(n).__name__} this walk does not classify")
        if rule == "children":
            if isinstance(n, _ast.Attribute) and n.attr in TXN_ATTRS:
                self.fail(n, f"a transaction word in a spelling this walk does "
                             f"not read (.{n.attr})")
            if isinstance(n, _ast.Attribute) and self.b.is_session(n.value):
                # A session's attribute is reached only as a callee the walk
                # reads (finding closed_walk:699: `str = db.add`).
                self.fail(n, f"a session attribute outside a call of it: "
                             f"{_ast.unparse(n)}")
            if isinstance(n, _ast.Attribute) and self.b.is_root(n.value):
                # An attribute read off a session root that is not itself a
                # session spelling (`ctx.closed`): the root is the walked
                # function's own parameter, read whole.
                self._check(n, self.b.session_root_ok, n.value, n.lineno)
                self._walked_nodes.add(id(n.value))
                return
            for c in _ast.iter_child_nodes(n):
                self.visit(c)
            return
        if rule == "lambda":
            for d in n.args.defaults + [d for d in n.args.kw_defaults if d]:
                self.visit(d)
            self.visit(n.body)
            return
        if rule == "comp":
            if isinstance(n, _ast.comprehension):
                if n.is_async:
                    self.fail(n.iter, "an async comprehension")
                self.visit(n.target)
                self.visit(n.iter)
                for c in n.ifs:
                    self.visit(c)
                return
            for g in n.generators:
                self.visit(g)
            for c in ([n.key, n.value] if isinstance(n, _ast.DictComp) else [n.elt]):
                self.visit(c)
            return
        if rule == "call":
            self.call(n)
            return
        if rule == "await":
            self.awaited(n)
            return
        self.fail(n, f"a rule the walk does not know: {rule}")

    def _pure(self, n, name, written):
        self.p.met["call " + name] += 1
        self._spelled(n.func)
        for a in written:
            self.visit(a)
        self.effects.append(("call", "pure"))

    def _plain_args(self, n, name, args):
        for kind, a in args:
            if kind in ("star", "double-star"):
                self.fail(n, f"a call of {name} with unpacked arguments")
            self.visit(a)

    # A call: the callee shape, then every argument kind.
    def call(self, n):
        name = _ast.unparse(n.func)
        args = call_arguments(n)
        # the argument nodes as written (a `*x` visits its Starred node)
        written = list(n.args) + [k.value for k in n.keywords]
        if isinstance(n.func, _ast.Name):
            kind, what = self._resolve(n, n.func.id)
            if kind == "def" and id(what) in self.walked_defs:
                # A plain function the helper defines, bound exactly once:
                # its defaults and body were walked at its definition,
                # through the same table (finding closed_walk:897: a local
                # function rebound kept this reading).
                self._plain_args(n, name, args)
                self._spelled(n.func)
                self.p.met["local function call"] += 1
                self.effects.append(("call", "pure"))
                return
            if kind not in ("module", "import"):
                # A callee spelled from a name the function binds is not the
                # module's (finding closed_walk:699: `str = ...; str(row)`).
                self.fail(n, f"a call of {name}, a name the function binds")
            if kind == "module" and self._check(
                    n, self.b.listed, n.func, self.p.pure_calls) is not None:
                self._pure(n, name, written)
                return
            if kind == "module" and self._check(
                    n, self.b.namedtuple_class, n.func) is not None:
                self._plain_args(n, name, args)
                self._spelled(n.func)
                self.p.met["named tuple " + name] += 1
                self.effects.append(("call", "pure"))
                return
            fn = self._check(n, self.b.callee, n.func)
            if fn is None or _inspect.iscoroutinefunction(fn):
                self.fail(n, f"a call this walk does not classify: {name}")
            # a session value only as fn's same-named parameter
            self._helper_args(n, n, fn)
            # Its whole body through this visitor's table (finding
            # closed_walk:712: a source grep let `db.add(row)` through): a
            # plain function takes no effect at all. A module accessor
            # (`import m; return m`, module_accessor) is read by its shape.
            eff = (frozenset() if self.b.module_accessor(fn) is not None
                   else plain_effects(fn, self.p))
            if eff:
                self.fail(n, f"a plain call of {name}, which takes "
                             f"{', '.join(sorted(eff))}")
            self._spelled(n.func)
            self.p.met["plain function " + name] += 1
            self.effects.append(("call", "pure"))
            return
        if isinstance(n.func, _ast.Attribute):
            root = _root(n.func)
            if self._check(n, self.b.listed, n.func,
                           self.p.pure_calls) is not None:
                self._pure(n, name, written)
                return
            if self.b.is_session(n.func.value):
                self._check(n, self.b.session_root_ok, n.func.value, n.lineno)
                self._spelled(n.func)
                if n.func.attr == "expire":
                    # Marks loaded rows stale; their next read is a SELECT.
                    self._plain_args(n, name, args)
                    self.p.met["session .expire"] += 1
                    self.effects.append(("sql", "read"))
                    return
                if n.func.attr in ("add", "add_all"):
                    # An ORM row added to the session: a write at its flush.
                    self._plain_args(n, name, args)
                    self.p.met["session ." + n.func.attr] += 1
                    self.effects.append(("sql", "write"))
                    return
                self.fail(n, f"a session call this walk does not classify: {name}")
            acc = n.func.value
            if (isinstance(acc, _ast.Call) and isinstance(acc.func, _ast.Name)
                    and not acc.args and not acc.keywords
                    and self.b.module_accessor(self._check(
                        n, self.b.callee, acc.func)) is not None):
                # `<accessor>().f(...)`: a plain function of the module the
                # accessor returns, its body walked like any plain callee.
                fn = self._check(n, self.b.callee, n.func)
                if fn is None or _inspect.iscoroutinefunction(fn):
                    self.fail(n, f"a call this walk does not classify: {name}")
                self._plain_args(n, name, args)
                eff = plain_effects(fn, self.p)
                if eff:
                    self.fail(n, f"a plain call of {name}, which takes "
                                 f"{', '.join(sorted(eff))}")
                self._spelled(n.func)
                self.p.met["plain function " + name] += 1
                self.effects.append(("call", "pure"))
                return
            if n.func.attr not in self.p.pure_methods:
                self.fail(n, f"a method call this walk does not classify: {name}")
            self.p.met["method ." + n.func.attr] += 1
            self._walked_nodes.add(id(n.func))
            if self.b.is_root(n.func.value):
                # a listed method of a session root (`ctx.seat_of(pid)`):
                # the root is the function's own parameter, read whole as
                # the receiver, never as a value
                self._check(n, self.b.session_root_ok, n.func.value, n.lineno)
                self._walked_nodes.add(id(n.func.value))
            else:
                self.visit(n.func.value)
            for a in written:
                self.visit(a)
            self.effects.append(("call", "pure"))
            return
        self.fail(n, f"a call of a computed callee: {name}")

    def awaited(self, n):
        call = n.value
        if not isinstance(call, _ast.Call):
            self.fail(n, "an await of a non-call")
        if not isinstance(call.func, (_ast.Name, _ast.Attribute)):
            self.fail(n, f"an await of a computed callee: "
                         f"{_ast.unparse(call.func)}")
        # Every branch below reads the callee by its spelling (a session
        # method, a listed await, a parameter, a resolved helper) or refuses;
        # an attribute callee whose value is not a plain name chain does not
        # resolve and is refused there.
        self._walked_nodes.add(id(call))
        self._spelled(call.func)
        s = self.p.session
        if isinstance(call.func, _ast.Attribute) and self.b.is_session(call.func.value):
            self._check(n, self.b.session_root_ok, call.func.value, n.lineno)
        for end in ("commit", "rollback"):
            if is_db_call(call, end, s):
                if id(n) not in self.permitted:
                    self.fail(n, f"ends the transaction (.{end})"
                              if self.helper is not None else
                              "a transaction end in a spelling this walk "
                              "does not read")
                if call.args or call.keywords:
                    self.fail(n, f"a {end} with arguments")
                self.effects.append((f"end:{end}", "pure"))
                return
        if is_db_call(call, "flush", s) and not call.args and not call.keywords:
            # Pending ORM rows sent to the database: a write.
            self.p.met["session .flush"] += 1
            self.effects.append(("sql", "write"))
            return
        if isinstance(call.func, _ast.Attribute) and is_session(
                call.func.value, s) and call.func.attr != "execute":
            self.fail(n, f"a session call this walk does not classify: "
                         f"{_ast.unparse(call.func)}")
        if is_db_call(call, "execute", s):
            for _kind, a in call_arguments(call):
                self.visit(a)
            self.effects.append(("sql", self._check(
                n, self.b.execute_kind, call, self.p.sql, self.local,
                self.guarded, lambda f: plain_effects(f, self.p))))
            self.p.met["execute"] += 1
            return
        name = _ast.unparse(call.func)
        root = _root(call.func)
        kind = self._resolve(n, root)[0] if root is not None else "module"
        callback = (kind == "param" and self._check(
            n, self.b.spelled_in, call.func, self.params, ("param",))
            is not None)
        if kind not in ("module", "import") and not callback:
            # A callee spelled from a name the function binds is not the
            # module's (finding closed_walk:699).
            self.fail(n, f"an await of {name}, a name the function binds")
        if kind == "module" and self._check(
                n, self.b.listed, call.func, self.p.pure_awaits) is not None:
            for _kind, a in call_arguments(call):
                self.visit(a)
            self.effects.append(("call", "pure"))
            return
        if callback:
            # A callback parameter of the helper being walked: classified at
            # each call site (checked_callbacks). A session value passed to
            # it reaches the callback's own parameter, which its walk reads
            # under its own bindings: a parameter not spelled as a session
            # takes no session call there.
            for kind, a in call_arguments(call):
                if kind in ("star", "double-star"):
                    self.fail(n, f"a call of {_ast.unparse(call.func)} with "
                                 "unpacked arguments")
                if self.b.session_value(a):
                    self._check(n, self.b.session_root_ok, a, n.lineno)
                    self._spelled(a)
                else:
                    self.visit(a)
            self.effects.append((f"callback:{_ast.unparse(call.func)}", "pure"))
            return
        if (isinstance(call.func, _ast.Name) and self._check(
                n, self.b.listed, call.func, self.opaque) is not None):
            # A helper whose own shape the caller reads separately (the team
            # resolver's relock helper): its arguments are classified here,
            # its body there.
            self._helper_args(n, call, self._check(
                n, self.b.opaque_callee, call.func, self.opaque))
            self.effects.append((f"helper:{name}", "opaque"))
            return
        fn = self._check(n, self.b.callee, call.func)
        if fn is None or not _inspect.iscoroutinefunction(fn):
            self.fail(n, f"an awaited call this walk does not classify: {name}")
        self._helper_args(n, call, fn)
        if self.p.helper_hook is not None and self.helper is None:
            self.p.met["helper by the policy's hook"] += 1
            self.effects.append((f"helper:{fn.__name__}", self.p.helper_hook(fn)))
            return
        eff = checked_callbacks(call, fn, helper_effects(fn, self.p), n.lineno)
        ends = eff & {"rollback-then-raise", "rollback"}
        if ends and id(n) in self.caught:
            self.fail(n, f"a helper that ends the transaction and raises "
                         f"({fn.__name__}), awaited inside a try that catches")
        if ends:
            # Propagated (finding closed_walk:825): the caller's effects carry
            # the end its helper takes.
            self.effects.append((f"helper-end:{fn.__name__}",
                                 sorted(ends)[0]))
        kinds = eff & {"read", "lock", "write"}
        self.effects.append((f"helper:{fn.__name__}",
                             "write" if "write" in kinds else "lock" if "lock" in kinds
                             else "read" if "read" in kinds else "pure"))


def expr_effects(node, policy, local=None, guarded=frozenset(),
                 opaque=frozenset(), bindings=None):
    """The (shape, effect) list of evaluating `node` (Visitor) under
    `bindings`, the enclosing function's (finding a1:665: the formation
    walk's expressions resolved names in the module); raises Unclassified
    naming the construct and its line."""
    return list(Visitor(policy, local, guarded, opaque=opaque,
                        bindings=bindings).accept(node).effects)


def checked_callbacks(call, fn, effects, line):
    """`effects` of helper `fn` at the call `call`, without its callback
    parameters, after checking that the call binds none of them to a
    value: an awaited callback is not a shape the walk classifies. A
    callback parameter with a default other than None is refused at the
    helper (helper_effects)."""
    params = list(_inspect.signature(fn).parameters)
    out = set()
    for e in effects:
        if not e.startswith("callback:"):
            out.add(e)
            continue
        name = e.split(":", 1)[1]
        at = params.index(name)
        if any(k.arg == name or k.arg is None for k in call.keywords) or len(
                call.args) > at or any(isinstance(a, _ast.Starred) for a in call.args):
            raise Unclassified((line, f"a callback passed to {fn.__name__} "
                                      f"({name}), which the walk does not "
                                      "classify"))
    return frozenset(out)


def _helper_tree(fn):
    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(fn)))
    defs = [n for n in tree.body if isinstance(n, (_ast.AsyncFunctionDef,
                                                   _ast.FunctionDef))]
    if len(defs) != 1:
        raise Unclassified((0, f"{fn.__name__}: not one function definition"))
    return defs[0]


def helper_effects(fn, policy, stack=()):
    """helper_effects of a function object (cached per policy)."""
    key = (fn.__module__, fn.__qualname__)
    if key in policy.helpers:
        return policy.helpers[key]
    if key in policy.walking:
        # A helper that awaits itself: its effects are the ones its other
        # statements give, which the outer walk of it is collecting.
        return frozenset()
    policy.walking.add(key)
    try:
        out = def_effects(_helper_tree(fn), _inspect.getmodule(fn), policy,
                          fn.__name__)
    finally:
        policy.walking.discard(key)
    policy.helpers[key] = out
    return out


def def_effects(d, scope, policy, label, opaque=frozenset(), rollbacks=False,
                ends=frozenset()):
    """The effects of an awaited helper, read from its own body statement by
    statement through the table: a frozenset drawn from 'read', 'lock',
    'write', 'await', 'savepoint', 'rollback-then-raise' and
    'callback:<param>'. Raises Unclassified for any construct off the table,
    any transaction end outside the two named shapes (a savepoint block
    `async with <session>.begin_nested():`, and an exception handler that
    opens with `await <session>.rollback()` and raises on every path), and
    any callback parameter with a default other than None. With
    `rollbacks`, every awaited `<session>.rollback()` is permitted and read
    as the effect 'rollback' (a caller that names such a helper decides what
    a rollback means for it)."""
    fn = _types.SimpleNamespace(__name__=label)
    sub = Policy(scope, policy.pure_calls, policy.pure_methods,
                 policy.pure_awaits, policy.sql, policy.session)
    sub.helpers = policy.helpers
    sub.walking = policy.walking
    sub.met = policy.met
    for n in _ast.walk(d):
        if isinstance(n, _ast.ImportFrom) and (not n.module or n.level):
            raise Unclassified((0, f"{fn.__name__}: a relative import"))
    # The helper's own bindings: every name the walk reads in it resolves
    # there, one binding per name (ruling REHEARSAL-FOUR-R5 item 2).
    b = Bindings(scope, d, session=policy.session)
    params = [a.arg for a in d.args.posonlyargs + d.args.args + d.args.kwonlyargs]
    if d.args.vararg or d.args.kwarg:
        raise Unclassified((0, f"{fn.__name__} takes *args or **kwargs"))
    guarded = b.guards(d)
    local = b.local_sql(d)
    permitted = set()
    s = policy.session
    caught = frozenset(id(x) for t in _ast.walk(d)
                       if isinstance(t, _ast.Try) and t.handlers
                       for st in t.body for x in _ast.walk(st))
    for n in _ast.walk(d):
        if isinstance(n, _ast.ExceptHandler) and n.body and id(n) in caught:
            # its raise is caught by an enclosing try of the same function
            continue
        if isinstance(n, _ast.ExceptHandler) and n.body:
            first = n.body[0]
            aw = first.value if isinstance(first, _ast.Expr) else None
            if (isinstance(aw, _ast.Await) and is_db_call(aw.value, "rollback", s)
                    and all_paths_raise(n.body[1:])):
                permitted.add(id(aw))
    if rollbacks:
        permitted.update(id(n) for n in _ast.walk(d) if isinstance(n, _ast.Await)
                         and is_db_call(n.value, "rollback", s))
    # Awaited commits and rollbacks the caller names by its own structural
    # read (a1's relock helper: its one commit, and its one rollback followed
    # by a raise): permitted here, read as 'commit' and 'rollback-then-raise'.
    named_ends = frozenset(id(n) for n in _ast.walk(d) if id(n) in ends
                           and isinstance(n, _ast.Await)
                           and (is_db_call(n.value, "commit", s)
                                or is_db_call(n.value, "rollback", s)))
    if len(named_ends) != len(ends):
        raise Unclassified((0, f"{fn.__name__}: a named end that is not an "
                               "awaited commit or rollback of its body"))
    permitted.update(named_ends)
    v = Visitor(sub, local, guarded, params, frozenset(permitted), fn,
                opaque, bindings=b)
    v.caught = caught
    effects = set()
    named = d.args.posonlyargs + d.args.args
    defaults = dict(zip([a.arg for a in named[len(named) - len(d.args.defaults):]],
                        d.args.defaults))
    defaults.update({a.arg: x for a, x in zip(d.args.kwonlyargs, d.args.kw_defaults)
                     if x is not None})

    def block():
        # The defaults of its parameters are evaluated at definition time; a
        # callback parameter may default only to None.
        for dft in d.args.defaults + [x for x in d.args.kw_defaults if x]:
            v.visit(dft)
        _helper_block(v, d.body, effects)

    for sh, e in v.accept(d, block).effects:
        if sh == "sql":
            effects.add(e)
        elif sh.startswith("helper:"):
            effects.add("await")
            if e not in ("pure", "opaque"):
                effects.add(e)
        elif sh.startswith("callback:"):
            p = sh.split(":", 1)[1]
            if p in defaults and not (isinstance(defaults[p], _ast.Constant)
                                      and defaults[p].value is None):
                raise Unclassified((0, f"{fn.__name__}: the callback parameter "
                                       f"{p} has a default the walk does not "
                                       "classify"))
            effects.add(sh)
        elif sh == "end:rollback":
            effects.add("rollback" if rollbacks else "rollback-then-raise")
        elif sh == "end:commit":
            effects.add("commit")
        elif sh.startswith("helper-end:"):
            effects.add(e)
        elif sh == "savepoint":
            effects.add("savepoint")
    return frozenset(effects)


def _helper_block(v, stmts, effects):
    """Walk a helper's statements through the table (helper_effects)."""
    for st in stmts:
        rule = _rule(st)
        name = type(st).__name__
        v.p.met["helper stmt " + name] += 1
        if rule != "stmt":
            v.fail(st, f"{v.helper.__name__}: a {name} this walk does not "
                       "classify")
        if isinstance(st, (_ast.Expr, _ast.Return)):
            if st.value is not None:
                v.visit(st.value)
        elif isinstance(st, _ast.Assign):
            for tg in st.targets:
                v.visit(tg)
            v.visit(st.value)
        elif isinstance(st, (_ast.AugAssign, _ast.AnnAssign)):
            v.visit(st.target)
            if st.value is not None:
                v.visit(st.value)
        elif isinstance(st, _ast.Delete):
            for tg in st.targets:
                v.visit(tg)
        elif isinstance(st, _ast.Assert):
            v.visit(st.test)
            if st.msg is not None:
                v.visit(st.msg)
        elif isinstance(st, _ast.If):
            v.visit(st.test)
            _helper_block(v, st.body, effects)
            _helper_block(v, st.orelse, effects)
        elif isinstance(st, (_ast.For, _ast.While)):
            if isinstance(st, _ast.For):
                v.visit(st.target)
                v.visit(st.iter)
            else:
                v.visit(st.test)
            _helper_block(v, st.body, effects)
            _helper_block(v, st.orelse, effects)
        elif isinstance(st, _ast.Try):
            # A return, break or continue that leaves a finally discards the
            # exception in flight (finding closed_walk:1217: `finally:
            # return None` swallowed a rollback-then-raise).
            for x in finally_exits(st.finalbody):
                v.fail(x, f"{v.helper.__name__}: a {type(x).__name__.lower()} "
                          "inside a finally")
            _helper_block(v, st.body, effects)
            for h in st.handlers:
                if h.type is not None:
                    v.visit(h.type)
                _helper_block(v, h.body, effects)
            _helper_block(v, st.orelse, effects)
            _helper_block(v, st.finalbody, effects)
        elif isinstance(st, _ast.AsyncWith):
            items = st.items
            ctx = items[0].context_expr if len(items) == 1 else None
            if not (is_db_call(ctx, "begin_nested", v.p.session) and not ctx.args
                    and not ctx.keywords and items[0].optional_vars is None):
                v.fail(st, f"{v.helper.__name__}: an async with this walk does "
                           "not classify")
            v._spelled(ctx)
            v.effects.append(("savepoint", "pure"))
            v.p.met["helper savepoint block"] += 1
            _helper_block(v, st.body, effects)
        elif isinstance(st, _ast.Raise):
            if st.exc is not None:
                v.visit(st.exc)
            if st.cause is not None:
                v.visit(st.cause)
        elif isinstance(st, (_ast.Pass, _ast.Break, _ast.Continue, _ast.ImportFrom)):
            pass
        elif isinstance(st, _ast.FunctionDef):
            # A plain local function: no decorator, no *args or **kwargs; its
            # defaults and its body are walked here, through the same table,
            # and a call of it is then a plain call (Visitor.call).
            if st.decorator_list or st.args.vararg or st.args.kwarg:
                v.fail(st, f"{v.helper.__name__}: a local function this walk "
                           "does not classify")
            for dft in st.args.defaults + [x for x in st.args.kw_defaults if x]:
                v.visit(dft)
            for a in (st.args.posonlyargs + st.args.args + st.args.kwonlyargs):
                if a.annotation is not None:
                    v.visit(a.annotation)
            if st.returns is not None:
                v.visit(st.returns)
            if any(isinstance(x, (_ast.Await, _ast.Yield, _ast.YieldFrom))
                   for x in _ast.walk(st)):
                v.fail(st, f"{v.helper.__name__}: a local function that awaits "
                           "or yields")
            v.p.met["helper local function"] += 1
            _helper_block(v, st.body, effects)
            v.walked_defs.add(id(st))
        elif isinstance(st, _ast.Global):
            # A module-level cache the helper refreshes (the service-account
            # uuid cache): a process value, not a session effect.
            pass
        else:
            v.fail(st, f"{v.helper.__name__}: a {name} this walk does not "
                       "classify")
