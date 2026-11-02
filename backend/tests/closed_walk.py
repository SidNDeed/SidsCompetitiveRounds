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
# The placeholder a formatted value of an f-string SQL reads as: an
# identifier, never SQL text.
SQL_FV = "fv_ident"


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
            if t[0] == "ident" and (name in lists.syntax or name == SQL_FV):
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


# --- SQL text a call executes ---------------------------------------------

def sql_text(node, scope, guarded=frozenset()):
    """The SQL a `text(...)` argument holds: a string constant, a name bound
    to a string at module level in `scope`, an f-string whose formatted values
    read as identifiers (never in the statement's head), or a `+` of these.
    None when it is none of them."""
    if isinstance(node, _ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, _ast.Name):
        value = getattr(scope, node.id, None)
        return value if isinstance(value, str) else None
    if isinstance(node, _ast.BinOp) and isinstance(node.op, _ast.Add):
        a, b = (sql_text(node.left, scope, guarded),
                sql_text(node.right, scope, guarded))
        return None if a is None or b is None else a + b
    if isinstance(node, _ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, _ast.Constant):
                parts.append(v.value)
            elif isinstance(v, _ast.FormattedValue):
                if v.format_spec is not None or v.conversion != -1:
                    return None
                inner = v.value
                held = (getattr(scope, inner.id, None)
                        if isinstance(inner, _ast.Name) else None)
                table = (getattr(scope, inner.value.id, None)
                         if isinstance(inner, _ast.Subscript)
                         and isinstance(inner.value, _ast.Name) else None)
                if isinstance(held, str):
                    parts.append(held)
                elif isinstance(inner, _ast.Name) and inner.id in guarded:
                    parts.append(f" {SQL_FV} ")
                elif isinstance(table, dict) and table and all(
                        isinstance(x, str) and _re.fullmatch(r"[a-z_][a-z_0-9]*", x)
                        for x in table.values()):
                    parts.append(f" {SQL_FV} ")
                else:
                    return None
            else:
                return None
        text = "".join(parts)
        first = text.split()[0] if text.split() else ""
        return None if first == SQL_FV else text
    return None


def returned_sql(fn, scope):
    """The SQL texts a plain module function returns, when every `return`
    in it returns SQL sql_text can read; or, for a builder of one argument
    that indexes module tables by it (`_SERIES_TABLE[mode]`), its own output
    over every key those tables share. [None] otherwise."""
    if fn is None or _inspect.iscoroutinefunction(fn):
        return [None]
    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(fn)))
    rets = [n.value for n in _ast.walk(tree) if isinstance(n, _ast.Return)]
    out = [sql_text(r, scope) if r is not None else None for r in rets] or [None]
    if None not in out:
        return out
    params = list(_inspect.signature(fn).parameters)
    tables = [getattr(scope, n.value.id, None) for n in _ast.walk(tree)
              if isinstance(n, _ast.Subscript) and isinstance(n.value, _ast.Name)
              and isinstance(n.slice, _ast.Name) and len(params) == 1
              and n.slice.id == params[0]]
    if not tables or not all(isinstance(d, dict) and d for d in tables):
        return [None]
    keys = set(tables[0])
    for d in tables[1:]:
        keys &= set(d)
    texts = [fn(k) for k in sorted(keys)]
    return texts if texts and all(isinstance(x, str) for x in texts) else [None]


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
    """The local names a function guards as identifiers before use:
    `if <name> not in <MODULE_COLLECTION>: raise ...`, the collection
    holding only lower-case identifiers."""
    out = set()
    for n in _ast.walk(tree):
        test = getattr(n, "test", None)
        if (isinstance(n, _ast.If) and isinstance(test, _ast.Compare)
                and isinstance(test.left, _ast.Name) and len(test.ops) == 1
                and isinstance(test.ops[0], _ast.NotIn)
                and isinstance(test.comparators[0], _ast.Name)
                and all_paths_raise(n.body)):
            coll = getattr(scope, test.comparators[0].id, None)
            if isinstance(coll, (set, frozenset, tuple, list, dict)) and coll and all(
                    isinstance(x, str) and _re.fullmatch(r"[a-z_][a-z_0-9]*", x)
                    for x in coll):
                out.add(test.left.id)
    return frozenset(out)


def local_sql(tree, scope):
    """{local name: [SQL texts]} for each name a function binds only to SQL
    sql_text can read, directly, as either arm of a conditional expression,
    or as `<MODULE_TEMPLATE>.format(k=<sql or a conditional>)` (every
    combination of the arms), each optionally extended by `<name> += <sql>`
    outside any loop (every text with and without each suffix, a superset of
    what any path builds). A name stored any other way (including by a
    mutating method, or by += inside a loop) is left out."""
    binds = {}
    suffixes = {}
    looped = {id(x) for lp in _ast.walk(tree)
              if isinstance(lp, (_ast.For, _ast.While, _ast.AsyncFor))
              for x in _ast.walk(lp)}

    def arms(v):
        return ([sql_text(v.body, scope), sql_text(v.orelse, scope)]
                if isinstance(v, _ast.IfExp) else [sql_text(v, scope)])

    for n in _ast.walk(tree):
        if isinstance(n, _ast.Assign):
            for tg in n.targets:
                if not isinstance(tg, _ast.Name):
                    for nm in stores(tg):
                        binds.setdefault(nm, []).append(None)
                    continue
                v = n.value
                tmpl = (getattr(scope, v.func.value.id, None)
                        if isinstance(v, _ast.Call)
                        and isinstance(v.func, _ast.Attribute)
                        and v.func.attr == "format"
                        and isinstance(v.func.value, _ast.Name) else None)
                if isinstance(tmpl, str) and not v.args and all(
                        k.arg for k in v.keywords):
                    combos = [{}]
                    for k in v.keywords:
                        combos = [dict(c, **{k.arg: o})
                                  for c in combos for o in arms(k.value)]
                    texts = [None if None in c.values() else tmpl.format(**c)
                             for c in combos]
                    binds.setdefault(tg.id, []).extend(texts)
                else:
                    binds.setdefault(tg.id, []).extend(arms(v))
        elif (isinstance(n, _ast.AugAssign) and isinstance(n.op, _ast.Add)
              and isinstance(n.target, _ast.Name) and id(n) not in looped
              and sql_text(n.value, scope) is not None):
            suffixes.setdefault(n.target.id, []).append(
                (n.lineno, n.col_offset, sql_text(n.value, scope)))
        elif not isinstance(n, (_ast.Name,)):
            if isinstance(n, (_ast.AugAssign, _ast.AnnAssign, _ast.For,
                              _ast.Delete, _ast.Call, _ast.comprehension)):
                for nm in stores(n):
                    binds.setdefault(nm, []).append(None)
    for name, adds in suffixes.items():
        texts = binds.setdefault(name, [None])
        for _line, _col, s in sorted(adds):
            texts = texts + [None if x is None else x + s for x in texts]
        binds[name] = texts
    return {k: v for k, v in binds.items() if None not in v}


def is_session(expr, session="db"):
    """Whether expression `expr` spells the session: `session` is one
    spelling ('db') or a tuple of them (('db', 'ctx.db'))."""
    text = _ast.unparse(expr)
    return text == session if isinstance(session, str) else text in session


def is_db_call(call, attr, session="db"):
    return (isinstance(call, _ast.Call) and isinstance(call.func, _ast.Attribute)
            and is_session(call.func.value, session)
            and call.func.attr == attr)


def execute_kind(call, scope, lists, local=None, guarded=frozenset()):
    """'read', 'lock' or 'write' when `call` is `<session>.execute(text(<sql>),
    <binds>)` with SQL sql_text (or a local SQL name, or a SQL builder) can
    read and sql_kind classifies; raises Unclassified otherwise."""
    if not (call.args and isinstance(call.args[0], _ast.Call)
            and isinstance(call.args[0].func, _ast.Name)
            and call.args[0].func.id == "text"
            and len(call.args[0].args) == 1 and not call.args[0].keywords):
        raise Unclassified((call.lineno, "an execute of something other than "
                                         "text(<sql>)"))
    if any(isinstance(a, _ast.Starred) for a in call.args) or any(
            k.arg is None for k in call.keywords):
        raise Unclassified((call.lineno, "an execute with unpacked arguments"))
    arg = call.args[0].args[0]
    sqls = [sql_text(arg, scope, guarded)]
    if sqls == [None] and isinstance(arg, _ast.Name) and local is not None:
        sqls = local.get(arg.id, [None])
    elif (sqls == [None] and isinstance(arg, _ast.Call)
          and isinstance(arg.func, _ast.Name) and not arg.keywords
          and not any(isinstance(a, _ast.Starred) for a in arg.args)):
        sqls = returned_sql(resolve_callee(arg.func, scope), scope)
    if not sqls or None in sqls:
        raise Unclassified((call.lineno, "an execute whose SQL the walk cannot "
                                         "read"))
    try:
        kinds = {sql_kind(s, lists) for s in sqls}
    except Unclassified as e:
        raise Unclassified((call.lineno, e.args[0][1])) from None
    return ("write" if "write" in kinds else "lock" if "lock" in kinds
            else "read")


def module_accessor(fn):
    """The module a module accessor returns: a plain function of no
    parameters whose body is exactly `import <m>` then `return <m>` (after
    an optional docstring), such as main._mrw_mod. None for anything else."""
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


def resolve_callee(func, scope, imports=None):
    """The Python function a callee expression names in `scope` (a plain
    name, or a module attribute such as `_match_hold._hold_latch`), else
    None."""
    if isinstance(func, _ast.Name) and imports and func.id in imports:
        mod, attr = imports[func.id]
        obj = getattr(_importlib.import_module(mod), attr, None)
    elif isinstance(func, _ast.Name):
        obj = getattr(scope, func.id, None)
    elif isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Name):
        mod = getattr(scope, func.value.id, None)
        obj = getattr(mod, func.attr, None) if mod is not None else None
    elif (isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Call)
          and isinstance(func.value.func, _ast.Name) and not func.value.args
          and not func.value.keywords):
        mod = module_accessor(getattr(scope, func.value.func.id, None))
        obj = getattr(mod, func.attr, None) if mod is not None else None
    else:
        return None
    obj = _inspect.unwrap(obj) if callable(obj) else None
    return obj if _inspect.isfunction(obj) else None


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
    or 'pure'."""

    def __init__(self, policy, local=None, guarded=frozenset(), imports=None,
                 params=(), permitted=frozenset(), helper=None, opaque=frozenset()):
        self.p = policy
        self.local = local
        self.guarded = guarded
        self.imports = imports or {}
        self.params = tuple(params)
        self.permitted = permitted
        self.helper = helper
        self.opaque = frozenset(opaque)
        self.local_defs = set()
        self.effects = []
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

    def visit(self, n):
        rule = _rule(n)
        self._walked_nodes.add(id(n))
        self.p.met["node " + type(n).__name__] += 1
        if rule == "leaf":
            return
        if rule == "refuse" or rule == "stmt":
            self.fail(n, f"a {type(n).__name__} this walk does not classify")
        if rule == "children":
            if isinstance(n, _ast.Attribute) and n.attr in TXN_ATTRS:
                self.fail(n, f"a transaction word in a spelling this walk does "
                             f"not read (.{n.attr})")
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

    # A call: the callee shape, then every argument kind.
    def call(self, n):
        name = _ast.unparse(n.func)
        args = call_arguments(n)
        # the argument nodes as written (a `*x` visits its Starred node)
        written = list(n.args) + [k.value for k in n.keywords]
        if isinstance(n.func, _ast.Name) and n.func.id in self.local_defs:
            # A plain function the helper defines: its defaults and body were
            # walked at its definition, through the same table.
            for kind, a in args:
                if kind in ("star", "double-star"):
                    self.fail(n, f"a call of {name} with unpacked arguments")
                self.visit(a)
            self._spelled(n.func)
            self.p.met["local function call"] += 1
            self.effects.append(("call", "pure"))
            return
        if isinstance(n.func, _ast.Name):
            if name in self.p.pure_calls:
                self.p.met["call " + name] += 1
                self._spelled(n.func)
                for a in written:
                    self.visit(a)
                self.effects.append(("call", "pure"))
                return
            fn = resolve_callee(n.func, self.p.scope, self.imports)
            if fn is None or _inspect.iscoroutinefunction(fn):
                self.fail(n, f"a call this walk does not classify: {name}")
            for kind, a in args:
                if kind in ("star", "double-star"):
                    self.fail(n, f"a call of {name} with unpacked arguments")
                self.visit(a)
            if any(isinstance(x, _ast.Attribute) and x.attr in (
                    "commit", "rollback", "execute", "begin", "flush", "close",
                    "begin_nested") for x in _ast.walk(_ast.parse(
                        _textwrap.dedent(_inspect.getsource(fn))))):
                self.fail(n, f"a plain call of {name}, which touches a session")
            self._spelled(n.func)
            self.p.met["plain function " + name] += 1
            self.effects.append(("call", "pure"))
            return
        if isinstance(n.func, _ast.Attribute):
            if name in self.p.pure_calls:
                self.p.met["call " + name] += 1
                self._spelled(n.func)
                for a in written:
                    self.visit(a)
                self.effects.append(("call", "pure"))
                return
            if is_session(n.func.value, self.p.session):
                self._spelled(n.func)
                if n.func.attr == "expire":
                    # Marks loaded rows stale; their next read is a SELECT.
                    for kind, a in args:
                        if kind in ("star", "double-star"):
                            self.fail(n, f"a call of {name} with unpacked arguments")
                        self.visit(a)
                    self.p.met["session .expire"] += 1
                    self.effects.append(("sql", "read"))
                    return
                if n.func.attr in ("add", "add_all"):
                    # An ORM row added to the session: a write at its flush.
                    for kind, a in args:
                        if kind in ("star", "double-star"):
                            self.fail(n, f"a call of {name} with unpacked arguments")
                        self.visit(a)
                    self.p.met["session ." + n.func.attr] += 1
                    self.effects.append(("sql", "write"))
                    return
                self.fail(n, f"a session call this walk does not classify: {name}")
            if n.func.attr not in self.p.pure_methods:
                self.fail(n, f"a method call this walk does not classify: {name}")
            self.p.met["method ." + n.func.attr] += 1
            self._walked_nodes.add(id(n.func))
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
            self.effects.append(("sql", execute_kind(
                call, self.p.scope, self.p.sql, self.local, self.guarded)))
            self.p.met["execute"] += 1
            return
        name = _ast.unparse(call.func)
        if name in self.p.pure_awaits:
            for _kind, a in call_arguments(call):
                self.visit(a)
            self.effects.append(("call", "pure"))
            return
        if isinstance(call.func, _ast.Name) and call.func.id in self.params:
            # A callback parameter of the helper being walked: classified at
            # each call site (checked_callbacks).
            for _kind, a in call_arguments(call):
                self.visit(a)
            self.effects.append((f"callback:{call.func.id}", "pure"))
            return
        if not isinstance(call.func, (_ast.Name, _ast.Attribute)):
            self.fail(n, f"an await of a computed callee: {name}")
        if isinstance(call.func, _ast.Name) and call.func.id in self.opaque:
            # A helper whose own shape the caller reads separately (the team
            # resolver's relock helper): its arguments are classified here,
            # its body there.
            for kind, a in call_arguments(call):
                if kind in ("star", "double-star"):
                    self.fail(n, f"a call of {name} with unpacked arguments")
                self.visit(a)
            self.effects.append((f"helper:{name}", "opaque"))
            return
        fn = resolve_callee(call.func, self.p.scope, self.imports)
        if fn is None or not _inspect.iscoroutinefunction(fn):
            self.fail(n, f"an awaited call this walk does not classify: {name}")
        for kind, a in call_arguments(call):
            if kind in ("star", "double-star"):
                self.fail(n, f"a call of {fn.__name__} with unpacked arguments")
            self.visit(a)
        if self.p.helper_hook is not None and self.helper is None:
            self.p.met["helper by the policy's hook"] += 1
            self.effects.append((f"helper:{fn.__name__}", self.p.helper_hook(fn)))
            return
        eff = checked_callbacks(call, fn, helper_effects(fn, self.p), n.lineno)
        kinds = eff & {"read", "lock", "write"}
        self.effects.append((f"helper:{fn.__name__}",
                             "write" if "write" in kinds else "lock" if "lock" in kinds
                             else "read" if "read" in kinds else "pure"))


def expr_effects(node, policy, local=None, guarded=frozenset(),
                 opaque=frozenset()):
    """The (shape, effect) list of evaluating `node` (Visitor); raises
    Unclassified naming the construct and its line."""
    return list(Visitor(policy, local, guarded, opaque=opaque).accept(node).effects)


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
    imports = {}
    for n in _ast.walk(d):
        if isinstance(n, _ast.ImportFrom):
            if not n.module or n.level:
                raise Unclassified((0, f"{fn.__name__}: a relative import"))
            for a in n.names:
                imports[a.asname or a.name] = (n.module, a.name)
    params = [a.arg for a in d.args.posonlyargs + d.args.args + d.args.kwonlyargs]
    if d.args.vararg or d.args.kwarg:
        raise Unclassified((0, f"{fn.__name__} takes *args or **kwargs"))
    guarded = guarded_names(d, scope)
    local = local_sql(d, scope)
    permitted = set()
    s = policy.session
    for n in _ast.walk(d):
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
    v = Visitor(sub, local, guarded, imports, params, frozenset(permitted), fn,
                opaque)
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
            v.local_defs.add(st.name)
        elif isinstance(st, _ast.Global):
            # A module-level cache the helper refreshes (the service-account
            # uuid cache): a process value, not a session effect.
            pass
        else:
            v.fail(st, f"{v.helper.__name__}: a {name} this walk does not "
                       "classify")
