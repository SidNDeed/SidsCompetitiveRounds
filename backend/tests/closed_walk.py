"""The one closed, default-deny walker of the two D5 source checks
(rehearsal-four round 3, ruling REHEARSAL-FOUR-R3).

Users: test_a1_identity_formation.py (the formation exit walk, the barrier,
the resolver and family-pick checks) and test_match_hold_admission_gate_pg.py
(the refusal and claim-prefix walks). Each file keeps its own statement
STRUCTURE (which exits a path takes, which branch refuses), but every
expression it meets, every helper body it descends into, and every execute
it runs is classified HERE, by one visitor, so a construct cannot be
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
  * An execute is classified by a FROZEN LOOKUP, not an analysis (round
    8, ruling REHEARSAL-FOUR-R7-A1, M1, rule (1)(c)): 'read' only at a
    position (file, line, end line) of the walk's frozen read table, the
    covered positions the read-only role ran 'ok' (ro_covered); every
    other execute is 'write'. No SQL text is read; the static S analysis
    (lexer, allow-lists, local SQL names, builders) is retired.
"""
import ast as _ast
import collections as _collections
import inspect as _inspect
import re as _re
import textwrap as _textwrap
import types as _types
import os as _os
# The frozen providers of PLAIN_BODY_CALLS (round 10, ruling REHEARSAL-R9-A1
# (D)): bound by this module's own static imports.
import builtins as _builtins
import datetime as _cw_datetime
import json as _cw_json
import math as _cw_math

import shape_grammar as _sg
# Round 11 (ruling FOUR-R10-A2, FIX-R11-ID): the one identity binder.
import grammar_providers as _gp
import identity_binder as _ib
from shape_grammar import header_digest as _header_digest



class Unclassified(Exception):
    """A construct the closed walk has no named shape for: (line, what)."""


# --- the default-deny grammar (ruling REHEARSAL-FOUR-R6 (1)(b)) -----------

def local_imports(d):
    """[(line, (module, name, asname))] for every import under `d`: module
    None for a plain `import`, the dotted module (with its leading dots for
    a relative one) for a `from ... import`."""
    out = []
    for n in _ast.walk(d):
        if isinstance(n, _ast.Import):
            out.extend((n.lineno, (None, a.name, a.asname)) for a in n.names)
        elif isinstance(n, _ast.ImportFrom):
            mod = "." * (n.level or 0) + (n.module or "")
            out.extend((n.lineno, (mod, a.name, a.asname)) for a in n.names)
    return out


class Grammar:
    """A walk's frozen default-deny grammar (ruling REHEARSAL-FOUR-R6
    (1)(b)). Every span the walk visits (a handler, an awaited or plain
    helper's body, a builder's body, a module accessor's body) is ADMITTED
    before any walker reasoning reads it:

      1. every node, by shape_grammar.check, has a shape in `shapes`;
      2. the anchored rule (round 8, ruling REHEARSAL-FOUR-R7-A1, M3,
         anchored_refusals): every store or deletion of a spelling in
         `meaningful`, and every call of a method named `commit` or
         `rollback` (a transaction end, whatever its receiver), stands at a
         frozen ANCHOR: `allowed` holds (spelling, "store", anchor) and
         (attr, "end", anchor), the anchor being the tuple of the shapes of
         every node from the span root's child down to the Name or the
         call; any other binding of a meaningful spelling (a parameter, a
         definition, an import, an except or match name, a global) needs
         its pair (spelling, how) in `allowed`, as in round 7 (the span's
         own root definition is its name, not a binding). A refusal names
         the anchor's innermost shape. Round 7 admitted a meaningful store,
         and the commit call's shape, anywhere in a span, so a commit
         before the drift rollback, a budget refilled inside its loop and a
         rolled-back roster kept were refused only by the walks' sentences
         over admitted shapes.

    A local import needs no further rule: its shape carries its module (an
    ImportFrom's) and each alias's name and asname, so the shape rule admits
    exactly the frozen imports' statements.

    `imports` is the frozen CALLEE TABLE (round 8, M4; rule (1)(c)):
    {form: function} for every callee a walk reaches outside the walked
    function's own module namespace, the form being the callee's spelling
    (`_match_hold._hold_latch`, `_mrw_mod().series_fresh`) or, for a
    local `from ... import`, the import statement's text (a statement that
    imports several names maps to {bound name: function}). The functions are
    bound by the test's own static imports and asserted against frozen
    spans; nothing is imported, and no attribute is looked up, by a name
    read from the tree (Bindings.callee).

    `namedtuples` is the frozen DEFINITION SCOPE (round 8, M5): the spelled
    shape (shape_grammar.shape, plus `#<spelling>` for a Name) of every
    node of every module that defines a constructor-pure class
    (Bindings.namedtuple_class, definition_scope_refusals), so a statement
    such a module gains anywhere, a store to the class or its attributes
    included, is refused by shape.

    Any refusal raises Unclassified((line, sentence)), the sentence naming
    the file, the absolute line and the shape or anchor. `admitted` maps
    each span (file, line, name) to the number of nodes checked (the
    completeness count).

    With `record`, nothing is refused: the shapes met are collected instead
    (the one-time generator, RF/r7/ga1/gen_shapes.py)."""

    def __init__(self, shapes, meaningful, allowed, imports,
                 namedtuples=frozenset(), record=False):
        self.shapes = frozenset(shapes)
        self.meaningful = frozenset(meaningful)
        self.allowed = frozenset(allowed)
        self.imports = dict(imports)
        self.namedtuples = frozenset(namedtuples)
        self.record = record
        self.admitted = {}
        self.trees = {}
        self.seen = {}
        self._done = {}

    def admit(self, d, filename, offset=0):
        """Admit span `d` (a definition node) of `filename`, its lines
        offset by `offset`; refused (Unclassified) by the first rule it
        breaks. A node already admitted is not checked twice."""
        if self._done.get(id(d)) is d:
            return
        key = (filename, offset + getattr(d, "lineno", 0),
               getattr(d, "name", type(d).__name__))
        if self.record:
            for s, ln in _sg.shapes(d).items():
                self.seen.setdefault(s, f"{filename}:{offset + ln}")
            self.trees[key] = d
            n = len(_sg.visit(d))
        else:
            try:
                n = _sg.check(d, self.shapes, filename)
            except _sg.Refused as e:
                f, ln, s = e.args[0]
                raise Unclassified((ln, f"a shape outside the grammar at "
                                        f"{f}:{offset + ln}: {s}"))
            own = (getattr(d, "lineno", 0), f"binds {getattr(d, 'name', '')} (def)")
            for f, ln, why in anchored_refusals(d, self.meaningful,
                                                self.allowed, filename):
                if (ln, why) == own:
                    continue        # the span's own name: its root definition
                raise Unclassified((ln, f"the anchored rule at "
                                        f"{f}:{offset + ln}: {why}"))
        self._done[id(d)] = d
        self.admitted[key] = n



def anchors(d, meaningful):
    """[(key, line)] for every store or deletion of a spelling in
    `meaningful` and every transaction end under definition `d`, in visit
    order: key (spelling, "store", anchor) for a Name stored or deleted (a
    deletion's anchor ends in its `ctx=Del` shape), (attr, "end", anchor)
    for a call of a method named commit or rollback; the anchor is the
    tuple of the node shapes from `d`'s child down to the node."""
    chains = {}
    for n, p, f in _sg.visit(d):
        if p is not None:
            chains[id(n)] = _chain(chains, n, p, f)
    out = []
    for n, p, f in _sg.visit(d):
        if _anchored_node(n, meaningful):
            out.append(_anchor_key(n, chains.get(id(n)), _line(n, p)))
    return out


def _chain(chains, n, p, f):
    """The shapes from the root's child down to `n` (shape_grammar.visit
    lists a parent before its children)."""
    chain = []
    if id(p) in chains:
        chain.extend(chains.get(id(p)))
    chain.append(_sg.shape(n, p, f))
    return chain


def _is_end(n):
    """Whether `n` calls a method named commit or rollback."""
    return (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Attribute)
            and n.func.attr in ("commit", "rollback"))


def _anchored_node(n, meaningful):
    """Whether the anchored rule reads node `n`: a transaction end, or a
    Name of a spelling in `meaningful` that is stored or deleted."""
    if _is_end(n):
        return True
    return (isinstance(n, _ast.Name) and n.id in meaningful
            and not isinstance(n.ctx, _ast.Load))


def _anchor_key(n, chain, line):
    """(key, line) of an anchored node (anchors)."""
    key = (_ast.unparse(n), "store", tuple(chain))
    if _is_end(n):
        key = (_end_attr(n), "end", tuple(chain))
    return (key, line)


def _end_attr(n):
    """The method a transaction end calls."""
    if _is_end(n):
        return n.func.attr
    return None


def _line(n, p):
    """A node's line, or its parent's."""
    return getattr(n, "lineno", None) or getattr(p, "lineno", None) or 0


def anchored_refusals(d, meaningful, allowed, filename):
    """[(file, line, sentence)], for definition `d`: every anchor (anchors)
    outside the frozen `allowed`, then every other binding of a spelling
    in `meaningful` (shape_grammar.bindings: a parameter, a definition, an
    import, an except or match name, a global) whose pair (spelling, how)
    is not in `allowed` (the root's own name included; Grammar.admit
    skips it)."""
    out = []
    for key, ln in anchors(d, meaningful):
        if key not in allowed:
            out.append((filename, ln, _anchor_sentence(key)))
    for ln, s, how in _sg.bindings(d):
        pair = (s, how)
        if (s in meaningful and how not in ("store", "del")
                and pair not in allowed):
            out.append((filename, ln, f"binds {s} ({how})"))
    for key, ln, shape in positions(d, meaningful, allowed):
        if key not in allowed:
            out.append((filename, ln, _position_sentence(key, shape)))
    for key, ln, shape in orders(d, allowed):
        if key not in allowed:
            out.append((filename, ln, _order_sentence(key, shape)))
    return out


# Round 9 (ruling REHEARSAL-R8-A1, G2 and G3): the POSITION rule. An anchor
# (above) binds a node's shape chain but not WHICH of the equal chains it
# stands at, nor where among its siblings: a commit at the place of the
# rollback at main.py:20747 matched the committing refusal at :20641
# (finding grammar_shapes_a1:2106), and a commit moved up its block kept
# its chain. A constant's shape binds its type, not its value. When
# `allowed` holds POSITIONED, every anchored node and every constant of a
# span stands at a frozen POSITION: (spelling, how, the span's name, the
# index path from the span's root down to the node), how being "store" or
# "end" as for an anchor, or "const" with the constant's repr as its
# spelling. Taken once from the real spans (grammar_shapes_a1.A1_POSITIONS).
POSITIONED = ("<positions>",)


def positions(d, meaningful, allowed):
    """[(key, line, shape)] for every anchored node and every constant
    under definition `d`, in visit order, when `allowed` holds POSITIONED
    (the position rule); empty otherwise."""
    paths = {}
    for n, p, f in _sg.visit(d):
        if p is not None:
            paths[id(n)] = _index_path(paths, n, p, f)
    out = []
    for n, p, f in _sg.visit(d):
        if _positioned_node(n, meaningful, allowed):
            out.append(_position_key(n, d, paths.get(id(n)), _line(n, p),
                                     _sg.shape(n, p, f)))
    return out


def _positioned_node(n, meaningful, allowed):
    """Whether the position rule reads node `n`."""
    if POSITIONED not in allowed:
        return False
    if isinstance(n, _ast.Constant):
        return True
    return _anchored_node(n, meaningful)


def _position_key(n, d, path, line, shape):
    """(key, line, shape) of a positioned node (positions)."""
    key = (_ast.unparse(n), "store", d.name, tuple(path))
    if _is_end(n):
        key = (_end_attr(n), "end", d.name, tuple(path))
    if isinstance(n, _ast.Constant):
        key = (repr(n.value), "const", d.name, tuple(path))
    return (key, line, shape)


def _index_path(paths, n, p, f):
    """The places from the root's child down to `n` (_place)."""
    path = []
    if id(p) in paths:
        path.extend(paths.get(id(p)))
    path.append(_place(n, f, getattr(p, f)))
    return path


def _place(n, f, kids):
    """`n`'s place in its parent: the field `f` it sits in, with its index
    when the field is the list `kids`."""
    at = str(f)
    if isinstance(kids, list):
        at = f"{f}[{_index_of(n, kids)}]"
    return at


def _index_of(n, kids):
    """`n`'s index in the list `kids` (by identity)."""
    for i, k in enumerate(kids):
        if k is n:
            return i
    return None


# Round 9 (W30b at the merge; the gr child's question 2): the ORDER rule.
# The position rule binds where every anchored node and every constant
# stands, and A1_SPANS pins each span's node count, but a permutation of
# consecutive statements none of which holds a position kept every
# position (RF/r9/tip/order_runs.py measured 39 such runs in the a1 spans,
# among them queue_poll's `db.add(series)` before `await db.flush()`).
# When `allowed` holds ORDERED, every statement of a span, the root
# included, stands at a frozen ORDER key: (shape_grammar.header_digest of
# the statement, "order", the span's name, the index path), the header
# being the statement's own nodes with each nested list of statements
# replaced by its length. A permutation, an inserted or removed statement,
# or a change to any node a statement owns refuses, naming the statement.
# Taken once from the real spans at the round-9 merge
# (grammar_shapes_a1.A1_ORDERS).
ORDERED = ("<orders>",)


def orders(d, allowed):
    """[(key, line, shape)] for every statement under definition `d` (`d`
    included, at the empty path), in visit order, when `allowed` holds
    ORDERED (the order rule); empty otherwise."""
    paths = {}
    for n, p, f in _sg.visit(d):
        if p is not None:
            paths[id(n)] = _index_path(paths, n, p, f)
    out = []
    for n, p, f in _sg.visit(d):
        path = paths.get(id(n))
        if path is None:
            path = []
        if _ordered_node(n, allowed):
            out.append(_order_key(n, d, path, _line(n, p),
                                  _sg.shape(n, p, f)))
    return out


def _ordered_node(n, allowed):
    """Whether the order rule reads node `n`."""
    if ORDERED not in allowed:
        return False
    return isinstance(n, _ast.stmt)


def _order_key(n, d, path, line, shape):
    """(key, line, shape) of a statement (orders)."""
    key = (_header_digest(n), "order", d.name, tuple(path))
    return (key, line, shape)


def _order_sentence(key, shape):
    """The refusal of a statement outside its frozen order key."""
    digest, how, name, path = key
    return (f"a statement, {shape}, outside its frozen {how} "
            f"(header {digest}), in {name} at {path}")


def _position_sentence(key, shape):
    """The refusal of a node outside its frozen position."""
    spelling, how, name, path = key
    if how == "const":
        return (f"a constant outside its frozen position, {shape}#{spelling}, "
                f"in {name} at {path}")
    if how == "end":
        return (f"a transaction end, {spelling}, outside its frozen position, "
                f"in {name} at {path}")
    return f"a {how} of {spelling} outside its frozen position, in {name} at {path}"


def _anchor_sentence(key):
    """The refusal of an anchor outside the frozen ones, naming its
    innermost shape."""
    spelling, how, chain = key
    where = chain[-1]
    if how == "end":
        return f"a transaction end, {spelling}, at {where}"
    return f"binds {spelling} ({how}) at {where}"


def definition_scope_refusals(tree, g, filename):
    """[(line, sentence)] for every node of module `tree` whose spelled
    shape (shape_grammar.shape, plus `#<spelling>` for a Name) is not in
    grammar `g`'s frozen definition scope (round 8, M5)."""
    out = []
    for n, p, f in _sg.visit(tree):
        if _spelled_shape(n, p, f) not in g.namedtuples:
            ln = _line(n, p)
            out.append((ln, f"a shape outside the definition scope at "
                            f"{filename}:{ln}: {_spelled_shape(n, p, f)}"))
    return out


def _spelled_shape(n, p, f):
    """shape_grammar.shape of `n`, a Name's spelling appended."""
    if isinstance(n, _ast.Name):
        return f"{_sg.shape(n, p, f)}#{n.id}"
    return _sg.shape(n, p, f)


def _frozen_callee(grammar, node, name=None):
    """The function grammar's frozen callee table holds for `node`'s
    text (a callee spelling, or a local import statement); for a statement
    that imports several names the table holds {bound name: function} and
    `name` picks one. None without a grammar or for any other text."""
    if grammar is None:
        return None
    table = getattr(grammar, "imports")
    obj = table.get(_ast.unparse(node))
    if isinstance(obj, dict) and name is not None:
        obj = obj.get(name)
    return obj


def _admitted_scope(name, scope, g, line):
    """The parsed module `scope` when every node of it is in grammar `g`'s
    frozen definition scope; refused BY SHAPE otherwise, naming the first
    node outside it (round 8, M5)."""
    tree = _module_tree(scope)
    f = _os.path.basename(getattr(scope, "__file__", "?"))
    if tree is None:
        raise Unclassified((line, f"{name}: no source of {f} to admit"))
    got = definition_scope_refusals(tree, g, f)
    if len(got) > 0:
        raise Unclassified((line, f"{name}: {got[0][1]}"))
    return tree


def source_of(fn):
    """(file, line offset) of function `fn`'s source, for Grammar.admit."""
    try:
        f = _inspect.getsourcefile(fn) or "?"
    except TypeError:
        f = "?"
    return _os.path.basename(f), fn.__code__.co_firstlineno - 1


def _one_top_binding(tree, name):
    """The one top-level statement of module `tree` that binds `name`, when
    the module binds `name` exactly once anywhere (shape_grammar.bindings);
    None otherwise."""
    if tree is None or sum(1 for _l, s, _h in _sg.bindings(tree)
                           if s == name) != 1:
        return None
    hits = [st for st in tree.body
            if any(s == name for _l, s, _h in _sg.bindings(st))]
    return hits[0] if len(hits) == 1 else None


_MODULE_TREES = {}
_SOURCE_TREES = {}


def _module_tree(scope):
    """The parsed source of module `scope` (cached), or None. Looked up by
    the scope OBJECT and shared by the source TEXT (round 11): a composed
    scope answers `__name__` with its module's, and a key by name made the
    two evict each other, so main.py was parsed again at every alternation
    (run 8's MemoryError, probe 3); a tree per scope object kept one parse
    of main.py per composed scope for the whole session (run 10's oom-kill).
    Equal source text is one tree, so a scope can never read another's."""
    key = id(scope)
    if key in _MODULE_TREES and _MODULE_TREES[key][0] is scope:
        return _MODULE_TREES[key][1]
    try:
        src = _inspect.getsource(scope)
    except (OSError, TypeError):
        src = None
    if src is None:
        tree = None
    else:
        tree = _SOURCE_TREES.get(src)
        if tree is None:
            tree = _SOURCE_TREES[src] = _ast.parse(src)
    _MODULE_TREES[key] = (scope, tree)
    return tree


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


def _arg_names(a):
    return [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs
            + [y for y in (a.vararg, a.kwarg) if y is not None]]


def rule_p_roots(b, F, pname, line):
    """Rule P's root of parameter `pname` of function F, read by Bindings
    `b` (Bindings.bound_root): the roots a body walk takes for its own
    function. Round 11 (ruling FOUR-R11-A13 (2)): a Bindings' param_roots,
    this unless its caller hands it another."""
    return b.bound_root(F, pname, line)


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

    test_r5_every_resolution_site_goes_through_the_resolver counts, in each
    function span of the walkers, the sites that look a walked name up (a
    getattr keyed by a name read from the tree, a comparison of a walked
    name's spelling, a lookup in a name table, an import) and the sites
    inside this class, and asserts the two counts are equal."""

    def __init__(self, scope, fn=None, stmts=None, session="db",
                 grammar=None, param_roots=rule_p_roots):
        self.scope = scope
        self.session = session
        # round 11 (ruling FOUR-R11-A13 (2)): (b, F, pname, line) -> the
        # root of the walked function's parameter at entry (_rooted); rule
        # P's own unless the caller hands another
        self.param_roots = param_roots
        # The walk's Grammar, when it has one: a callee outside the
        # module's own namespace resolves only through its frozen callee
        # table (round 8, M4; rule (1)(c): no import resolution by name);
        # without one, only the module's own names resolve.
        self.grammar = grammar
        self.sites = {}
        self.has_fn = fn is not None
        # the walked definition: an execute's position offset (_position)
        self.where = fn
        self._enumerated = set()
        # round 11 (F10): the parent of every walked node, for the
        # provenance of a local's one binding (receiver_provenance)
        self.parent = {}
        # round 11 (rule K's A5 clause, ruling FOUR-R11-A4 (2)(g)): a
        # parameter bound to ("A", q, (), False) while a walk carries a
        # handed instance's per-attribute conditions (def_effects)
        self.param_values = {}
        # round 11 (rules W and P): the definition a statement span is the
        # body of (a prefix walk's statements), set by the span's walker
        self.span_def = None
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
                for c in _ast.iter_child_nodes(n):
                    self.parent[id(c)] = n

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
        v = getattr(self.scope, name, _MISSING)
        # Round 11 (FIX-R11-ID): every module-scope read is reported to the
        # identity binder, so a cached walk is honoured only while it still
        # binds the same object (identity_binder.Deps.valid).
        _ib.observe(self.scope, name, v)
        return ("module", v)

    def bound_identity(self, name, line=0):
        """Round 11 (ruling FOUR-R10-A2, FIX-R11-ID; finding gate:842): the
        object the module scope binds `name` to (its own binding, else its
        __builtins__ entry) must BE the definition the name addresses, proven
        by identity_binder.trusted: for a provider of
        grammar_providers.PROVIDERS, the provider at its description; for any
        other name, the scope module's own definition of that name. The
        spelling only chose `name` (a filter); this is the guarantee. A
        rebinding (`main.HTTPException = writer`, a functools.wraps wrapper,
        a subclass carrying the description) refuses."""
        v = getattr(self.scope, name, _MISSING)
        _ib.observe(self.scope, name, v)
        if v is _MISSING:
            bi = getattr(self.scope, "__builtins__", _MISSING)
            if isinstance(bi, dict):
                v = bi.get(name, _MISSING)
            else:
                v = getattr(bi, name, _MISSING)
            _ib.observe(bi, name, v)
        desc = _gp.PROVIDERS.get(name)
        if desc is not None and len(desc) == 1:
            ok = _ib.trusted(v, desc[0][0], desc[0][1])
        elif type(self.scope) is _types.ModuleType:
            ok = _ib.trusted(v, self.scope.__name__, name)
        else:
            # a scope that is not a module (a test's composed scope) names
            # where each of its names is defined only through its own
            # class's declaration, never through a __name__ it answers
            addr = vars(type(self.scope)).get("__binder_address__")
            where = addr(self.scope, name) if callable(addr) else None
            ok = where is not None and _ib.trusted(v, where[0], where[1])
        if ok is not True:
            raise Unclassified((line, f"{name}, which the walk reads as the "
                                      "module's, is not the definition it "
                                      "names"))
        return v

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
        self.bound_identity(name, line)
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
            self.bound_identity(node.id, line)
            return node.id
        if kind == "import":
            imp, alias = v
            if self.grammar is not None:
                # the grammar admitted this import's exact statement shape;
                # round 11 (FIX-R11-ID): the object its frozen callee table
                # holds for it must be a trusted definition
                if isinstance(imp, _ast.ImportFrom) and alias.name == node.id:
                    obj = _frozen_callee(self.grammar, imp, node.id)
                    if obj is None or not (_ib.trusted_function(obj)
                                           or _ib.trusted_class(obj)):
                        raise Unclassified((line, f"{node.id}, imported by "
                                                  "the function, is not a "
                                                  "frozen definition"))
                    return node.id
            elif (isinstance(imp, _ast.ImportFrom) and imp.module
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
        call, a pure await) and the walked function does not bind its root,
        so it is the module's; None when `table` does not list it; refused
        when it does and the function binds the root.

        Round 10 (ruling REHEARSAL-R9-A1 (D); finding closed_walk:859: a
        module binding `int = writer` left `int(...)` pure): a listed
        spelling is admitted only when the scope's binding of it IS its
        frozen provider. `table` maps each spelling to its provider
        objects, one per component of the spelling, bound by the calling
        file's own static imports (`"int": (builtins.int,)`,
        `"_json.loads": (json, json.loads)`). The root resolves as Python
        resolves it: the module's own binding; else, when the module binds
        no such name, its `__builtins__` entry; else, for a root the
        function binds once by its frozen local import, the provider the
        import statement names (`import uuid as uuid_mod`: the provider
        module's own name). The root must be the provider's first object
        by identity, and a dotted spelling's attribute, read off that
        object, its second (by identity; a method bound fresh on each read
        is the same method of the same object). Any other binding refuses,
        and so does a table that gives no provider for the spelling.
        A Policy holds its tables as Providers; the opaque-helper table a
        caller passes (`opaque`) is not one, and keeps the round-9 rule:
        the walk then reads the helper through opaque_callee, the scope's
        own object or the definition the caller maps."""
        name = _ast.unparse(node)
        if name not in table:
            return None
        root = _root(node)
        line = line or getattr(node, "lineno", 0)
        if root is None or not self._module_object(root, line):
            raise Unclassified((line, f"a call of {name}, a name the "
                                      "function binds"))
        # (D) provider identity: every Policy table is a Providers; the
        # one other table, a caller's opaque helpers, names helpers whose
        # body the caller reads from the definition the walk resolves
        pt = isinstance(table, Providers)
        if pt is False:
            return name
        want = table[name]
        parts = name.split(".")
        if len(want) != len(parts):
            raise Unclassified((line, f"a call of {name}, which has no frozen "
                                      "provider"))
        w0 = want[0]
        kind, got = self.resolve(root, line)
        bi = self.module("__builtins__", line)
        pb = Bindings(bi)
        fallback = pb.module(root, line)
        if isinstance(bi, dict):
            fallback = bi.get(root, _MISSING)
        _ib.observe(bi, root, fallback)
        if kind == "module" and got is _MISSING:
            got = fallback
        if kind == "import":
            imp, alias = got
            got = _MISSING
            wname = getattr(w0, "__name__", _MISSING)
            iname = alias.name
            plain = isinstance(imp, _ast.Import)
            if plain is False:
                iname = None
            if iname == wname and _ib._module(iname) is w0:
                # round 11 (FIX-R11-ID): the spelling chose the module; the
                # binding is the frozen provider object itself
                got = w0
        if got is not w0:
            raise Unclassified((line, f"a call of {name}, whose {root} is "
                                      "not its frozen provider"))
        lb = Bindings(got)
        wl = want[-1]
        leaf = want[-1]
        last = parts[-1]
        if len(want) == 2:
            leaf = lb.module(last, line)
        bound = getattr(leaf, "__self__", _MISSING)
        wbound = getattr(wl, "__self__", _MISSING)
        # round 11 (FIX-R11-ID): a method read fresh off its object is the
        # frozen one by its type and method equality (the same receiver and
        # the same function), never by its writable __name__
        method = (bound is got and wbound is got and type(leaf) is type(wl)
                  and leaf == wl)
        if leaf is not wl and method is not True:
            raise Unclassified((line, f"a call of {name}, whose {last} is "
                                      "not its frozen provider"))
        return name

    def _module_object(self, name, line=0):
        """Whether `name` denotes the module's own object: the function does
        not bind it, or binds it once by a local import the walk's GRAMMAR
        admitted (team_queue_poll's `import uuid as uuid_mod`: its exact
        statement shape is frozen). Round 7 (ruling REHEARSAL-FOUR-R6 (1)(c))
        deleted the reading that imported the module by name and compared
        the objects; without a grammar a local import is never the
        module's."""
        kind, _v = self.resolve(name, line)
        if kind == "module":
            return True
        return kind == "import" and self.grammar is not None

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

    def opaque_def(self, func, opaque, line=0):
        """Round 11 (F10): the definition `opaque` maps plain name `func`
        to (the one the caller reads separately), or None."""
        if isinstance(opaque, dict) and isinstance(func, _ast.Name):
            return opaque.get(func.id)
        return None

    def supplied(self, node, d, line=0):
        """Round 11: whether `node` is the plain name of definition `d`, a
        definition the caller supplies and reads separately (a walk's opaque
        helper), as the walk's opaque branch reads it; refused when the
        walked function binds that name (then it is not `d`). When the
        module binds the name (a live helper), that binding must be the
        definition it names (bound_identity, as `spelled`); a name the
        module does not bind at all is a planted program's helper, read only
        as `d`."""
        if self.opaque_def(node, {d.name: d}) is not d:
            return False
        line = line or getattr(node, "lineno", 0)
        kind, v = self.resolve(d.name, line)
        if kind != "module":
            raise Unclassified((line, f"{d.name}, a supplied helper the walk "
                                      "reads separately, is bound by the "
                                      "function"))
        if v is not _MISSING or hasattr(_builtins, d.name):
            self.bound_identity(d.name, line)
        return True

    def nested_def(self, f, at):
        """Round 11 (run 18: region_pick._pick's `state(s)`): the plain (not
        async) definition nested in the walked function that plain name `f`
        denotes at node `at`, or None: its one binding (resolve; a name
        bound more than once is unproven), a `def` statement inside the
        walked function that binds in a scope the read at `at` sees (run
        20: the resolver decides it, the census counting a lookup of the
        spelling outside the resolver)."""
        if not isinstance(f, _ast.Name):
            return None
        try:
            kind, node = self.resolve(f.id, getattr(at, "lineno", 0))
        except Unclassified:
            return None
        if not (kind == "def" and isinstance(node, _ast.FunctionDef)
                and node is not self.where):
            return None
        home = _binding_scope(kind, node, self)
        if not any(home is s for s in _scope_chain(at, self) + [None]):
            return None
        return node

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
        function does not bind, the module's own value. Any other callee
        only through the walk grammar's FROZEN callee table (round 8, ruling
        REHEARSAL-FOUR-R7-A1, M4; rule (1)(c)): a name the function binds
        once by a local `from ... import` whose statement text is a frozen
        form, or a module attribute (`_match_hold._hold_latch`) or an
        accessor's attribute (`_mrw_mod().series_fresh`) whose spelling is
        a frozen form and whose root name the function does not bind.
        Nothing is imported and no attribute is looked up by a name read
        from the tree; without a grammar only the module's own names
        resolve. None otherwise; a name bound more than once is refused."""
        line = line or getattr(func, "lineno", 0)
        obj = None
        if isinstance(func, _ast.Name):
            kind, v = self.resolve(func.id, line)
            if kind == "import":
                imp, alias = v
                if not isinstance(imp, _ast.ImportFrom):
                    return None
                obj = _frozen_callee(self.grammar, imp, func.id)
            elif kind == "module" and v is not _MISSING:
                obj = v
        elif isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Name):
            mod = self.module(func.value.id, line)
            obj = _frozen_callee(self.grammar, func) if mod is not None else None
        elif (isinstance(func, _ast.Attribute) and isinstance(func.value, _ast.Call)
              and isinstance(func.value.func, _ast.Name) and not func.value.args
              and not func.value.keywords):
            mod = self.module(func.value.func.id, line)
            obj = _frozen_callee(self.grammar, func) if mod is not None else None
        # Round 11 (FIX-R11-ID; finding closed_walk:1125): the walk reads
        # the ACTUAL callable. inspect.unwrap discarded every wrapper layer's
        # body; now a callee is admitted only when it is a plain function
        # defined by its own module's source, with no __wrapped__ layer and
        # no closure (identity_binder.trusted_function), and its chain is
        # recorded for any cached walk that reads it.
        if obj is None or not callable(obj):
            return None
        _ib.observe_chain(obj)
        return obj if _ib.trusted_function(obj) else None

    @staticmethod
    def module_accessor(fn, grammar=None):
        """`fn` itself when it is a module accessor BY SHAPE: a plain
        function of no parameters whose body is exactly `import <m>` then
        `return <m>` (after an optional docstring), such as main._mrw_mod;
        None for anything else. Nothing is imported (round 8, M4): what an
        accessor's attribute names is the grammar's frozen callee table."""
        if not _inspect.isfunction(fn) or _inspect.signature(fn).parameters:
            return None
        try:
            d = _helper_tree(fn)
        except (Unclassified, OSError, TypeError):
            return None
        if grammar is not None:
            grammar.admit(d, *source_of(fn))
        body = [s for s in d.body if not (isinstance(s, _ast.Expr)
                                          and isinstance(s.value, _ast.Constant))]
        if not (len(body) == 2 and isinstance(body[0], _ast.Import)
                and len(body[0].names) == 1 and body[0].names[0].asname is None
                and isinstance(body[1], _ast.Return)
                and isinstance(body[1].value, _ast.Name)
                and body[1].value.id == body[0].names[0].name):
            return None
        return fn

    def namedtuple_class(self, func, line=0):
        """The class plain name `func` names when its module is a COMPLETE
        frozen definition scope (round 8, ruling REHEARSAL-FOUR-R7-A1, M5):
        every node of the module that holds it (every statement, and every
        later store to the class or its attributes) has its spelled shape
        in the grammar's frozen definition scope; any other node refuses
        the call BY SHAPE, naming it (_admitted_scope). Round 7 admitted
        the class's one top-level statement only, so a store appended
        anywhere (`_Cand.__new__ = staticmethod(writer)`) left the class
        constructor-pure. Within the admitted scope the module binds the
        name exactly once, by a top-level `X = <maker>(...)`, and the
        maker's root name exactly once. None for a callee that is not a
        class, and always None without a grammar."""
        if not isinstance(func, _ast.Name):
            return None
        line = line or getattr(func, "lineno", 0)
        obj = self.module(func.id, line)
        g = self.grammar
        if g is None or not isinstance(obj, type):
            return None
        tree = _admitted_scope(func.id, self.scope, g, line)
        made = _one_top_binding(tree, func.id)
        if not (isinstance(made, _ast.Assign)
                and isinstance(made.value, _ast.Call)):
            return None
        root = _root(made.value.func)
        maker = _one_top_binding(tree, root) if root else None
        if maker is None:
            return None
        return obj

    # --- the frozen execute lookup (round 8, M1) -------------------------

    def execute_kind(self, call, table):
        """The answer the walk's frozen table gives for the execute `call`'s
        position (round 8, ruling REHEARSAL-FOUR-R7-A1 M1, revised by R-A):
        'read' at a position of ro_covered.COVERED measured green under the
        read-only role, 'lock' at a position of ro_covered.WRITERS, and
        'write' for every other execute, one at a position in no table, or
        one the walk cannot place (edited, planted, ambiguous), included.
        No SQL text is read: the static S analysis is retired."""
        pos = _position(self, call)
        if pos in table:
            return table[pos]
        return "write"

    # --- round 11: rules W, P and K (ruling FOUR-R11-A4 (2)) -------------
    #
    # A receiver condition met at a span walked on its own (Visitor.helper
    # None) on a value rooted at one of the span's parameters, or at a local
    # it binds once by `<root>.<m>(...)`, is discharged here when that root
    # is an instance of an exact frozen class K, reached by rule W (the
    # function is handed whole to one walked caller, which calls it at
    # sites the recorder observes, its class named in W_NAMED) or by rule P
    # (every call site of the function passes, for the parameter, the
    # caller's own parameter rooted the same way, or a local the caller
    # binds once by such a call). Every discharge is marked (BOUND_MARKS)
    # and observed by the bound test, never assumed.

    def span_function(self, line):
        """(F, d): the function object the walked definition d is the body
        of: the module binding of d's name, a trusted plain function of that
        name with no decorator, whose parameters, read from the function
        object, are d's. None when d is no such body (a definition parsed on
        its own, a scope that is not a module): no rule roots its
        parameters, and the walk's own reading (a parameter's condition no
        walked call site discharges) refuses as before."""
        d = self.where if self.has_fn else self.span_def
        if not isinstance(d, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            raise Unclassified((line, "a bound discharge outside a walked "
                                      "definition"))
        mod = self.scope
        if type(mod) is not _types.ModuleType:
            return None
        F = vars(mod).get(d.name, _MISSING)
        _ib.observe(mod, d.name, F)
        if (not _ib.trusted_function(F) or F.__code__.co_name != d.name
                or d.decorator_list or d.args.vararg or d.args.kwarg
                or F.__code__.co_flags & 0x0C
                or _param_table(F)[0] != _param_table(d)[0]):
            return None
        return F, d

    def bound_value(self, expr, line):
        """(F, d, root, var) for argument `expr` of the walked span when it
        is a bound form (a parameter of the span, one attribute of one, or a
        local bound once by `<root>.<m>(...)`), else None; root is ("K", K,
        mod, path) or ("KM", K, mod, m) (_rooted)."""
        d = self.where if self.has_fn else self.span_def
        if not isinstance(d, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            return None
        if self._local_root(expr, d) is None:
            return None
        span = self.span_function(line)
        if span is None:
            return None
        F, d = span
        got = self._rooted(expr, F, d, line)
        if got is None:
            return None
        return F, d, got[0], got[1]

    def _local_root(self, expr, d):
        """The parameter of definition d (the walked one) that `expr` is
        spelled from as a bound form: the parameter (bound only as one), one
        attribute of it, or a local bound once by a method call of it; None
        for any other spelling."""
        if isinstance(expr, _ast.Attribute):
            return (self._local_root(expr.value, d)
                    if isinstance(expr.value, _ast.Name) else None)
        if not isinstance(expr, _ast.Name):
            return None
        name = expr.id
        own = [(k, n) for k, n in self.sites.get(name, ()) if k != "mutated"]
        params = _param_table(d)[0]
        if name in params and (own == [("param", d)] if self.has_fn
                               else not own):
            return name
        if len(own) != 1 or own[0][0] != "local":
            return None
        par = self.parent.get(id(own[0][1]))
        if (isinstance(par, _ast.Assign) and len(par.targets) == 1
                and isinstance(par.value, _ast.Call)
                and isinstance(par.value.func, _ast.Attribute)
                and isinstance(par.value.func.value, _ast.Name)):
            return self._local_root(par.value.func.value, d)
        return None

    def _rooted(self, expr, F, d, line):
        """(root, var): the bound root of `expr` in function F (definition
        d, these its bindings) and the frame variable it is read from, or
        None when expr is not a bound form."""
        if isinstance(expr, _ast.Attribute):
            if not isinstance(expr.value, _ast.Name):
                return None
            got = self._rooted(expr.value, F, d, line)
            if got is None or got[0][0] != "K" or got[0][3]:
                return None
            r = got[0]
            return ("K", r[1], r[2], (expr.attr,)), got[1]
        if not isinstance(expr, _ast.Name):
            return None
        name = expr.id
        own = [(k, n) for k, n in self.sites.get(name, ()) if k != "mutated"]
        params = _param_table(d)[0]
        param = (own == [("param", d)] if self.has_fn
                 else (not own and name in params))
        if param and name in params:
            return self.param_roots(self, F, name, line), name
        if len(own) != 1 or own[0][0] != "local":
            return None
        node = own[0][1]
        par = self.parent.get(id(node))
        if not (isinstance(par, _ast.Assign) and len(par.targets) == 1
                and par.targets[0] is node and isinstance(par.value, _ast.Call)
                and isinstance(par.value.func, _ast.Attribute)
                and isinstance(par.value.func.value, _ast.Name)):
            return None
        call = par.value
        if any(isinstance(a, _ast.Starred) for a in call.args) or any(
                k.arg is None for k in call.keywords):
            return None
        got = self._rooted(call.func.value, F, d, line)
        if got is None or got[0][0] != "K" or got[0][3]:
            return None
        K, mod = got[0][1], got[0][2]
        self.k_method(K, mod, call.func.attr, line)
        return ("KM", K, mod, call.func.attr), name

    def bound_root(self, F, pname, line):
        """The root of parameter `pname` of function F at entry, over every
        reference to F in its own module (_call_sites): ("K", K, mod, ())
        by rule W at a handed site, or the one root every direct call site's
        argument has (rule P). Refused for no site, for sites that disagree,
        and for a cycle."""
        key = (id(F), pname)
        hit = _BOUND_ROOTS.get(key)
        if hit is not None and hit[0] is F and hit[3].valid():
            _ib.carry(hit[3])
            BOUND_MARKS.extend(hit[2])
            return hit[1]
        if key in _BOUND_STACK:
            raise Unclassified((line, f"{F.__name__}'s parameter {pname} is "
                                      "rooted through itself, a cycle rule P "
                                      "refuses"))
        start = len(BOUND_MARKS)
        _BOUND_STACK.add(key)
        try:
            with _ib.recording() as deps:
                out = self._root_over_sites(F, pname, line)
        finally:
            _BOUND_STACK.discard(key)
        _BOUND_ROOTS[key] = (F, out, list(BOUND_MARKS[start:]), deps)
        return out

    def _root_over_sites(self, F, pname, line):
        mod = _ib._owner_module(F)
        got = []
        for site in self._call_sites(F, line):
            if site[0] == "handed":
                got.append(self._w_root(F, pname, site, mod, line))
                continue
            _k, C, cdef, call = site
            params = _param_table(F)[0]
            at = params.index(pname)
            if any(isinstance(a, _ast.Starred) for a in call.args) or any(
                    k.arg is None for k in call.keywords):
                raise Unclassified((line, f"a call of {F.__name__} with "
                                          "unpacked arguments, which rule P "
                                          "does not read"))
            arg = call.args[at] if at < len(call.args) else next(
                (k.value for k in call.keywords if k.arg == pname), None)
            cb = Bindings(mod, cdef, session=self.session, grammar=self.grammar)
            r = cb._rooted(arg, C, cdef, line) if arg is not None else None
            if r is None:
                raise Unclassified((line, f"{F.__name__}'s parameter {pname} "
                                          f"at its call in {C.__name__} (line "
                                          f"{call.lineno}) is no form rule P "
                                          "roots"))
            got.append(r[0])
        if not got or any(r != got[0] for r in got):
            raise Unclassified((line, f"{F.__name__}'s parameter {pname}: "
                                      f"{len(got)} call sites with no one root"))
        return got[0]

    def _w_root(self, F, pname, site, mod, line):
        """Rule W at a handed site: F's parameter `pname` is the first one,
        its class named in W_NAMED (identity), the caller's parameter that
        receives F only ever called (_param_calls); one mark per call."""
        _k, G, gdef, wname, wcalls, handed = site
        K = W_NAMED.get(F, {}).get(pname)
        params = _param_table(F)[0]
        if K is None or not params or params[0] != pname:
            raise Unclassified((line, f"{F.__name__} is handed to "
                                      f"{G.__name__} and rule W names no "
                                      f"class for its first parameter "
                                      f"{pname}"))
        self.k_class(K, line)
        if vars(mod).get(K.__name__, _MISSING) is not K:
            raise Unclassified((line, f"{K.__qualname__} is not the module's "
                                      "binding of its name"))
        _ib.observe(mod, K.__name__, K)
        for wc in wcalls:
            BOUND_MARKS.append(("W", G, wc.lineno, F, pname, handed, K))
        return ("K", K, mod, ())

    def _call_sites(self, F, line):
        """Every reference to F in its own module's source, each a direct
        call ("direct", C, its definition, the call) or an argument handed
        to a module function G whose receiving parameter is only ever
        called ("handed", G, its definition, the parameter, its calls, the
        functions handed there). Any other reference refuses: a store of
        the name, a reference outside a module function or inside a nested
        one, an attribute or string of the name, a caller that binds it."""
        mod = _ib._owner_module(F)
        tree = _module_tree(mod)
        name = F.__name__
        if tree is None or _one_top_binding(tree, name) is None:
            raise Unclassified((line, f"{name}: a function its module's source "
                                      "does not bind exactly once"))
        idx = self._name_index(tree)
        if idx["attr"].get(name) or not all(
                self._inert_string(idx, c, stmt)
                for c, stmt in idx["str"].get(name, ())):
            raise Unclassified((line, f"{name} is spelled as an attribute or a "
                                      "string in its module, a reference rule "
                                      "P does not read"))
        out = []
        for n, par, top, nested in idx["name"].get(name, ()):
            if not isinstance(n.ctx, _ast.Load) or top is None or nested:
                raise Unclassified((line, f"a reference to {name} at line "
                                          f"{n.lineno} outside a direct call "
                                          "in a module function"))
            C = self._module_function(mod, top, line)
            if Bindings(mod, top).count(name):
                raise Unclassified((line, f"{top.name} binds {name}, a caller "
                                          "rule P does not read"))
            if isinstance(par, _ast.Call) and par.func is n:
                out.append(("direct", C, top, par))
            elif (isinstance(par, _ast.Call) and isinstance(par.func, _ast.Name)
                  and any(a is n for a in par.args)):
                out.append(self._handed(mod, idx, par, n, line))
            else:
                raise Unclassified((line, f"a reference to {name} at line "
                                          f"{n.lineno} that is neither a "
                                          "direct call nor a handed argument"))
        return out

    def _inert_string(self, idx, c, stmt):
        """Whether string constant `c` (in module statement `stmt`) is a
        name compared and never looked up: an element of a row of a tuple
        table bound once at module level by `stmt`, whose every read is the
        iterable of a comprehension that unpacks each row into names and
        uses the name at c's place only as the left operand of `in` or
        `not in`."""
        if not (isinstance(stmt, _ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], _ast.Name)
                and isinstance(stmt.value, _ast.Tuple)):
            return False
        rows = [r for r in stmt.value.elts if isinstance(r, _ast.Tuple)
                and any(x is c for x in r.elts)]
        if len(rows) != 1 or any(not isinstance(r, _ast.Tuple)
                                 for r in stmt.value.elts):
            return False
        at = next(i for i, x in enumerate(rows[0].elts) if x is c)
        table = stmt.targets[0].id
        uses = idx["name"].get(table, ())
        for n, par, top, nested in uses:
            if n is stmt.targets[0]:
                continue
            if not (isinstance(n.ctx, _ast.Load)
                    and isinstance(par, _ast.comprehension) and par.iter is n
                    and isinstance(par.target, _ast.Tuple)
                    and len(par.target.elts) > at
                    and all(isinstance(t, _ast.Name) for t in par.target.elts)):
                return False
            tgt = par.target.elts[at].id
            outer = idx["stmt"].get(id(n))
            comp = next((x for x in _ast.walk(outer) if isinstance(
                x, (_ast.GeneratorExp, _ast.ListComp, _ast.SetComp))
                and any(g is par for g in x.generators)), None)
            if comp is None or len(comp.generators) != 1:
                return False
            reads = [x for x in _ast.walk(comp) if isinstance(x, _ast.Name)
                     and x.id == tgt and x is not par.target.elts[at]]
            tests = [t for t in par.ifs for t in _ast.walk(t)
                     if isinstance(t, _ast.Compare)]
            for x in reads:
                if not any(t.left is x and len(t.ops) == 1
                           and isinstance(t.ops[0], (_ast.In, _ast.NotIn))
                           for t in tests):
                    return False
        return True

    def _module_function(self, mod, d, line):
        fn = vars(mod).get(d.name, _MISSING)
        _ib.observe(mod, d.name, fn)
        if not _ib.trusted_function(fn) or fn.__code__.co_name != d.name:
            raise Unclassified((line, f"{d.name}: not a trusted function of "
                                      "its module"))
        return fn

    def _handed(self, mod, idx, call, n, line):
        """("handed", G, gdef, w, w's calls, handed set) for argument `n` of
        `call`, a call of module function G."""
        gname = call.func.id
        gdef = _one_top_binding(_module_tree(mod), gname)
        if not isinstance(gdef, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            raise Unclassified((line, f"{gname}: a receiver of a handed "
                                      "function that is not a module function"))
        G = self._module_function(mod, gdef, line)
        at = next(i for i, a in enumerate(call.args) if a is n)
        params = [a.arg for a in gdef.args.posonlyargs + gdef.args.args]
        if at >= len(params):
            raise Unclassified((line, f"{gname}: a handed argument past its "
                                      "positional parameters"))
        w = params[at]
        wcalls = self._param_calls(gdef, w, mod, line)
        handed = set()
        for x, par, top, nested in idx["name"].get(gname, ()):
            if not (isinstance(par, _ast.Call) and par.func is x
                    and isinstance(x.ctx, _ast.Load) and not nested):
                raise Unclassified((line, f"a reference to {gname} at line "
                                          f"{x.lineno} that is not a direct "
                                          "call"))
            if any(isinstance(a, _ast.Starred) for a in par.args) or any(
                    k.arg is None for k in par.keywords):
                raise Unclassified((line, f"a call of {gname} with unpacked "
                                          "arguments"))
            arg = par.args[at] if at < len(par.args) else next(
                (k.value for k in par.keywords if k.arg == w), None)
            if not isinstance(arg, _ast.Name):
                raise Unclassified((line, f"{gname}'s {w} at line {x.lineno} "
                                          "is not a module function by name"))
            fd = _one_top_binding(_module_tree(mod), arg.id)
            if not isinstance(fd, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                raise Unclassified((line, f"{gname}'s {w} at line {x.lineno} "
                                          "is not a module function by name"))
            handed.add(self._module_function(mod, fd, line))
        return ("handed", G, gdef, w, wcalls, frozenset(handed))

    def _param_calls(self, gdef, w, mod, line):
        """The calls of parameter `w` in G (definition gdef): w bound only as
        the parameter, every read of it the callee of a call in G's own
        scope, and nothing in G that reads names dynamically."""
        gb = Bindings(mod, gdef)
        own = gb.sites.get(w, ())
        if list(own) != [("param", gdef)]:
            raise Unclassified((line, f"{gdef.name}'s {w}, a handed function, "
                                      "is bound or stored other than as its "
                                      "parameter"))
        calls = []
        for n in _ast.walk(gdef):
            if (isinstance(n, _ast.Call) and isinstance(n.func, _ast.Name)
                    and n.func.id in ("locals", "vars", "globals", "eval",
                                      "exec")):
                raise Unclassified((line, f"{gdef.name} reads names "
                                          "dynamically"))
            if isinstance(n, _ast.Name) and n.id == w:
                par = gb.parent.get(id(n))
                if not (isinstance(par, _ast.Call) and par.func is n
                        and not _scope_chain(n, gb)):
                    raise Unclassified((line, f"{gdef.name}'s {w}, a handed "
                                              f"function, at line {n.lineno} "
                                              "is used other than called"))
                calls.append(par)
        if not calls:
            raise Unclassified((line, f"{gdef.name} never calls {w}"))
        return calls

    # --- rule K's class checks --------------------------------------------

    def k_class(self, K, line):
        """K is an exact frozen class: a trusted class whose type IS type,
        with no subclass, and no class of its MRO but object defining the
        attribute protocol or __slots__ (read from the class objects)."""
        name = getattr(K, "__qualname__", repr(K))
        if (type(K) is not type or not _ib.trusted_class(K)
                or K.__mro__[-1] is not object):
            raise Unclassified((line, f"{name} is not a trusted class whose "
                                      "type IS type, the class rule K reads"))
        if K.__subclasses__():
            raise Unclassified((line, f"{name} has a subclass "
                                      f"({K.__subclasses__()[0].__qualname__}), "
                                      "so rule K cannot read its instances "
                                      "by identity"))
        got = [f"{c.__qualname__}.{p}" for c in K.__mro__[:-1]
               for p in K_PROTOCOL if p in vars(c)]
        if got:
            raise Unclassified((line, f"{name}'s MRO defines {got[0]}, an "
                                      "attribute protocol rule K does not "
                                      "read"))

    def k_attr(self, K, mod, attr, line):
        """Rule K-a: `attr` is a plain instance attribute of K (no class of
        its MRO holds the name) and the module's store census is complete
        (_dynamic_forms finds no refusing form)."""
        self.k_class(K, line)
        if any(attr in vars(c) for c in K.__mro__):
            raise Unclassified((line, f"{K.__qualname__}.{attr} is held by a "
                                      "class of its MRO, not an instance "
                                      "attribute rule K-a reads"))
        self._k_census(mod, line)

    def k_method(self, K, mod, m, line):
        """Rule K-m: `m` is a plain trusted function on the class object K
        itself, and no store of the NAME m exists in the module."""
        self.k_class(K, line)
        fn = next((vars(c)[m] for c in K.__mro__ if m in vars(c)), _MISSING)
        if (vars(K).get(m, _MISSING) is not fn or type(fn) is not _types.FunctionType
                or not _ib.trusted_function(fn)):
            raise Unclassified((line, f"{K.__qualname__}.{m} is not a plain "
                                      "function on the class object"))
        census = self._k_census(mod, line)
        if census["stores"].get(m):
            raise Unclassified((line, f"an attribute store of the name {m} at "
                                      f"line {census['stores'][m][0]}, the "
                                      "method rule K-m reads"))

    def _k_census(self, mod, line):
        tree = _module_tree(mod)
        if tree is None:
            raise Unclassified((line, f"{mod!r}: no source for rule K's census"))
        census = self._store_census(tree)
        if census["refused"]:
            ln, what = census["refused"][0]
            raise Unclassified((line, f"{what} at line {ln}, a store rule K's "
                                      "census does not read"))
        return census

    # --- rule T (rulings FOUR-R11-A3 (3), FOUR-R11-A4 (5), FOUR-R11-A5) ---

    def t_pair(self, m, line):
        """Rule T's premise T1, by identity: datetime.datetime (this
        module's own import) is an immutable C type whose type IS type,
        named by its module and qualified name, and its attribute `m`, read
        from the class object, is a method descriptor the identity binder
        proves is the class's own."""
        cls = _cw_datetime.datetime
        desc = vars(cls).get(m, _MISSING)
        if (type(cls) is not type
                or not _ib.trusted(cls, "datetime", "datetime")
                or type(desc) is not _types.MethodDescriptorType
                or not _ib.trusted(desc, "datetime", "datetime." + m)):
            raise Unclassified((line, f"rule T: datetime.datetime.{m} is not "
                                      "a method descriptor of the immutable "
                                      "class, read from the class object"))

    def rule_t(self, call):
        """Rule T at method call `call`, whose result no other rule proves:
        None unless the call is `<name>.<m>()` with m the pair whose result
        is builtin (timestamp); else "B" once the walk shows condition (i)
        of FOUR-R11-A5 (2) in the walked definition (_t_condition), the
        site marked in BOUND_MARKS for the recorder; refused otherwise. The
        receiver's alternatives are not derived here: the recorder asserts
        at the site that its type IS datetime.datetime and observes every
        root (FOUR-R11-A4 (2)(d), (e))."""
        f = call.func
        if not (isinstance(f, _ast.Attribute)
                and isinstance(f.value, _ast.Name)):
            return None
        if T_PAIRS.get(f.attr, "") != "B" or call.args or call.keywords:
            return None
        line = call.lineno
        self.t_pair(f.attr, line)
        span = self.span_function(line)
        if span is None:
            raise Unclassified((line, f"rule T: {f.value.id}.{f.attr}() in a "
                                      "definition that is no module "
                                      "function's body, whose code the "
                                      "recorder cannot watch"))
        F, d = span
        off = F.__code__.co_firstlineno - d.lineno
        root, pairs = self._t_condition(f.value.id, call, off)
        BOUND_MARKS.append(("T", F, line + off, "." + f.attr, f.value.id,
                            "datetime", _cw_datetime.datetime,
                            root.lineno + off,
                            tuple(sorted(p.value.lineno + off
                                         for p in pairs))))
        return "B"

    def _t_condition(self, name, call, off):
        """Condition (i) of FOUR-R11-A5 (2) for receiver `name` of rule T's
        site `call` (`off` maps a walked line to its file line): every
        binding of `name` is an assignment target in the function's own
        scope; exactly one statement is not a pair (`name =
        name.replace(...)`, the receiver the same name), the root; the
        root and the site's statement stand in one statement list, the root
        first; every pair statement stands between them, in that list or as
        the one statement of an If between them with no else. (root
        statement, [pair statements]), or refused."""
        site = self._t_stmt(call)
        roots, pairs = [], []
        for kind, node in self.sites.get(name, ()):
            stmt = self._t_stmt(node) if kind == "local" else None
            if stmt is None or _scope_chain(node, self):
                raise Unclassified((call.lineno, f"rule T: {name} has a {kind} "
                                                 "binding other than an "
                                                 "assignment in the function's"
                                                 " own scope; condition (i) "
                                                 "refuses"))
            v = stmt.value if isinstance(stmt, _ast.Assign) else None
            if (isinstance(v, _ast.Call) and len(stmt.targets) == 1
                    and stmt.targets[0] is node
                    and isinstance(v.func, _ast.Attribute)
                    and isinstance(v.func.value, _ast.Name)
                    and v.func.value.id == name):
                if T_PAIRS.get(v.func.attr, "") != "datetime":
                    raise Unclassified((call.lineno, f"rule T: {name} is bound "
                                                     f"at line {stmt.lineno + off}"
                                                     f" by {name}.{v.func.attr}"
                                                     "(...), a method outside "
                                                     "rule T's pairs"))
                self.t_pair(v.func.attr, call.lineno)
                pairs.append(stmt)
            else:
                roots.append(stmt)
        if len(roots) != 1:
            lines = ", ".join(str(s.lineno + off) for s in roots)
            raise Unclassified((call.lineno, f"rule T: {name} is bound by "
                                             f"{len(roots)} statements that are"
                                             f" no pair of rule T (lines "
                                             f"{lines}); condition (i) needs "
                                             "exactly one root statement"))
        root = roots[0]
        held, i_root = self._t_place(root)
        sheld, i_site = self._t_place(site)
        if held is None or sheld is not held or i_root >= i_site:
            raise Unclassified((call.lineno, f"rule T: the root statement of "
                                             f"{name} (line {root.lineno + off})"
                                             " and the site's statement (line "
                                             f"{site.lineno + off}) are not one "
                                             "statement list, the root first; "
                                             "condition (i) refuses"))
        for p in pairs:
            plist, ip = self._t_place(p)
            holder = self.parent.get(id(p))
            if (plist is not held and isinstance(holder, _ast.If)
                    and len(holder.body) == 1 and not holder.orelse):
                plist, ip = self._t_place(holder)
            if plist is not held or ip <= i_root or ip >= i_site:
                raise Unclassified((call.lineno, f"rule T: the pair statement "
                                                 f"of {name} at line "
                                                 f"{p.lineno + off} does not "
                                                 "stand between its root (line "
                                                 f"{root.lineno + off}) and the "
                                                 f"site (line {site.lineno + off})"
                                                 "; condition (i) refuses"))
        return root, pairs

    def _t_stmt(self, node):
        """The statement of the walked definition that holds `node` (node
        itself when it is one), or None."""
        n = node
        while n is not None and not isinstance(n, _ast.stmt):
            n = self.parent.get(id(n))
        return n

    def _t_place(self, stmt):
        """(the statement list that holds `stmt`, its index there), by
        identity; (None, -1) when no list of its parent holds it."""
        par = self.parent.get(id(stmt))
        if par is None:
            par = self.where
        if par is None:
            return None, -1
        for _f, kids in _ast.iter_fields(par):
            if isinstance(kids, list):
                i = _index_of(stmt, kids)
                if i is not None:
                    return kids, i
        return None, -1

    def _name_index(self, tree):
        """{"name": {id: [(node, parent, top definition or None, nested)]},
        "attr": {attr: [line]}, "str": {text: [line]}} of a module tree."""
        hit = _NAME_INDEX.get(id(tree))
        if hit is not None and hit[0] is tree:
            return hit[1]
        idx = {"name": {}, "attr": {}, "str": {}, "stmt": {}}
        todo = [(c, tree, None, False, c) for c in _ast.iter_child_nodes(tree)]
        while todo:
            n, par, top, nested, stmt = todo.pop()
            if isinstance(n, _ast.Name):
                idx["name"].setdefault(n.id, []).append((n, par, top, nested))
                idx["stmt"][id(n)] = stmt
            elif isinstance(n, _ast.Attribute):
                idx["attr"].setdefault(n.attr, []).append(n.lineno)
            elif isinstance(n, _ast.Constant) and isinstance(n.value, str):
                idx["str"].setdefault(n.value, []).append((n, stmt))
            scope = isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                   _ast.Lambda, _ast.ClassDef))
            kid_top, kid_nested = top, nested
            if scope and top is None and par is tree and not isinstance(
                    n, (_ast.Lambda, _ast.ClassDef)):
                kid_top = n
            elif scope:
                kid_nested = True
            for c in _ast.iter_child_nodes(n):
                todo.append((c, n, kid_top, kid_nested, stmt))
        _NAME_INDEX[id(tree)] = (tree, idx)
        return idx


    def _const_names(self, expr, fdef):
        """The strings `expr` can be, read from constants only (a constant, a
        conditional of two, `<dict display>.get(<x>, <constant>)`, a subscript
        of a dict display, or a name `fdef` binds once to one), or None."""
        if isinstance(expr, _ast.Constant) and isinstance(expr.value, str):
            return {expr.value}
        if isinstance(expr, _ast.IfExp):
            a, c = self._const_names(expr.body, fdef), self._const_names(expr.orelse, fdef)
            return None if a is None or c is None else a | c
        if (isinstance(expr, _ast.Call) and isinstance(expr.func, _ast.Attribute)
                and expr.func.attr == "get" and isinstance(expr.func.value, _ast.Dict)
                and len(expr.args) == 2 and not expr.keywords):
            vals = self._const_names(expr.func.value, fdef)
            dft = self._const_names(expr.args[1], fdef)
            return None if vals is None or dft is None else vals | dft
        if isinstance(expr, _ast.Subscript) and isinstance(expr.value, _ast.Dict):
            return self._const_names(expr.value, fdef)
        if isinstance(expr, _ast.Dict):
            out = set()
            for v in expr.values:
                got = self._const_names(v, fdef)
                if got is None:
                    return None
                out |= got
            return out
        if isinstance(expr, _ast.Name) and fdef is not None:
            sets = [n for n in _ast.walk(fdef) if isinstance(n, _ast.Assign)
                    and any(isinstance(t, _ast.Name) and t.id == expr.id
                            for t in n.targets)]
            stores = [n for n in _ast.walk(fdef) if isinstance(n, _ast.Name)
                      and n.id == expr.id and not isinstance(n.ctx, _ast.Load)]
            if len(sets) == 1 and len(stores) == 1 and len(sets[0].targets) == 1:
                return self._const_names(sets[0].value, None)
        return None


    def _store_census(self, tree):
        """Rule K's store census of a module: {"stores": {attribute name:
        [line]} (attribute stores and deletes, and setattr/delattr names read
        from constants), "refused": [(line, form)]} where a refusing form is a
        setattr/delattr whose name no constant gives, a call of __setattr__ or
        __delattr__, a store through __dict__ or vars(), or a store of
        __class__ or __dict__."""
        hit = _STORE_CENSUS.get(id(tree))
        if hit is not None and hit[0] is tree:
            return hit[1]
        stores, refused = {}, []
        tops = {}
        for st in tree.body:
            for n in _ast.walk(st):
                tops[id(n)] = st if isinstance(st, (_ast.FunctionDef,
                                                    _ast.AsyncFunctionDef)) else None
        for n in _ast.walk(tree):
            if isinstance(n, _ast.Attribute) and not isinstance(n.ctx, _ast.Load):
                stores.setdefault(n.attr, []).append(n.lineno)
                if n.attr in ("__class__", "__dict__"):
                    refused.append((n.lineno, f"a store of {n.attr}"))
            if isinstance(n, _ast.Subscript) and not isinstance(n.ctx, _ast.Load):
                v = n.value
                if ((isinstance(v, _ast.Attribute) and v.attr == "__dict__")
                        or (isinstance(v, _ast.Call) and isinstance(v.func, _ast.Name)
                            and v.func.id == "vars")):
                    refused.append((n.lineno, "a store through a namespace"))
            if not isinstance(n, _ast.Call):
                continue
            f = n.func
            if isinstance(f, _ast.Attribute) and f.attr in ("__setattr__",
                                                             "__delattr__"):
                refused.append((n.lineno, f"a call of {f.attr}"))
            if (isinstance(f, _ast.Attribute) and f.attr in MUTATING_METHODS
                    and ((isinstance(f.value, _ast.Attribute)
                          and f.value.attr == "__dict__")
                         or (isinstance(f.value, _ast.Call)
                             and isinstance(f.value.func, _ast.Name)
                             and f.value.func.id == "vars"))):
                refused.append((n.lineno, "a store through a namespace"))
            if isinstance(f, _ast.Name) and f.id in ("setattr", "delattr"):
                names = (self._const_names(n.args[1], tops.get(id(n)))
                         if len(n.args) >= 2 else None)
                if names is None:
                    refused.append((n.lineno, f"a {f.id} whose name no constant "
                                              "gives"))
                else:
                    # round 11 (ruling FOUR-R11-A10 (3)): `names` is a set;
                    # the census table's keys are entered in text order,
                    # never in the set's hash order
                    for s in sorted(names):
                        stores.setdefault(s, []).append(n.lineno)
        census = {"stores": stores, "refused": sorted(refused)}
        _STORE_CENSUS[id(tree)] = (tree, census)
        return census


# Round 11, rules W, P and K (ruling FOUR-R11-A4 (2)): W_NAMED is rule W's
# named table, {F (a function object): {its first parameter: K}}, set by the
# walk's own test; BOUND_MARKS lists every bound discharge (2)(e):
# ("W", G, line, F, parameter, handed functions, K) and (rule, F, line,
# callee, frame path, group, K) for rule "K-a" or "K-m".
W_NAMED = {}
BOUND_MARKS = []
K_PROTOCOL = ("__setattr__", "__getattr__", "__getattribute__",
              "__delattr__", "__slots__")
# Round 11, rule T (rulings FOUR-R11-A3 (3), FOUR-R11-A4 (5), FOUR-R11-A5):
# its two named pairs on the class datetime.datetime, taken by identity
# (Bindings.t_pair), keyed by the method's name: "B" for timestamp, whose
# result is a float and whose call is a site the recorder observes;
# "datetime" for replace, whose result derives an alternative of a site's
# receiver under condition (i) (Bindings.rule_t). A rule T mark in
# BOUND_MARKS is ("T", F, site line, ".timestamp", receiver name,
# "datetime", datetime.datetime, root statement line, (pair call lines)).
T_PAIRS = {"timestamp": "B", "replace": "datetime"}
# Round 11, rule N (rulings FOUR-R11-A10 (1), FOUR-R11-A14 (2)): the named
# members, set by the walk's own tests as W_NAMED is: {(F, form, callee,
# name): (label, spelled, group, binds, census)}. Form "arg": the argument a
# call of function `callee` inside F hands to its parameter `name`, spelled
# `spelled`; form "method": the receiver Name `name` of a method call whose
# method is `callee` (".get") inside F. binds: ((module, name, object), ...)
# held by identity; census: ((owner, name, frozen rows), ...), the static
# half (_n_census) compared row by row. Nothing here gives a value a
# provenance: a discharge is a mark ("N", F, site line, callee, name, group,
# label) that the bound test observes, or a refusal.
# Member (B) (ruling FOUR-R11-A20 (1)) adds two forms, each one expression of
# F's body that the visitor does not classify, discharged by a CALLEE
# identity the bound test asserts at run time: form "call", the call of the
# Name `callee` ("sorted"), name the same Name, group "call"; form "result",
# the method call `callee` (".all") whose receiver is a call of method
# `name` ("mappings"), group "result". Spelled: the whole call, unparsed.
# Their site line is the line of the call's CALL instruction (the call's own
# line; for a method, the attribute's last line).
N_MEMBERS = {}
_N_CENSUS = {}
_BOUND_ROOTS = {}
_BOUND_STACK = set()
_NAME_INDEX = {}
_STORE_CENSUS = {}


def reset_bound():
    """Forget every bound mark and root (the bound test's fresh start)."""
    BOUND_MARKS.clear()
    _BOUND_ROOTS.clear()


_EXECUTES = {}
_DEFS = {}


def _position(b, call):
    """(file, line, end line) of execute `call` in the source of the module
    that DEFINES the function whose body holds it (_defining_module), found
    by AST identity and never by a name: `call`'s dump among the module's
    execute calls and, when the walked definition b.where is known, that
    definition equal by dump to exactly one of the module's (its line
    offset). None when no defining module is known, or `call` is in no
    module source or in not exactly one place (a planted or synthetic
    program): the execute then reads as a write.

    Round 11 (ruling FOUR-R11-A18 (2)): the rule is stated for every
    function. For a real row the defining module is the scope module, so
    nothing changes there (measured: every execute placement of every gate
    and a1 row); a span walked in a planted module is placed in the module
    that defines its function, and a planted helper's body in its planted
    text."""
    scope = _defining_module(b)
    d = getattr(b, "where")
    tree = _module_tree(scope) if scope is not None else None
    if tree is None:
        return None
    hits = _executes(tree)
    if d is not None:
        top = [x for x in _defs(tree) if _named_as(x, d)]
        top = [x for x in top if _same(x, d)]
        if len(top) != 1:
            return None
        t = top[0]
        hits = [x for x in hits if _at(x, call, t, d)]
    hits = [x for x in hits if _same(x, call)]
    if len(hits) != 1:
        return None
    x = hits[0]
    a = getattr(x, "lineno")
    e = getattr(x, "end_lineno")
    f = _os.path.basename(getattr(scope, "__file__", "?"))
    return f, a, e


def _defining_module(b):
    """The module that defines the function whose body b walks (b.where,
    else the span's b.span_def), known by identity through the binder: the
    walked scope's binding of the definition's name is a trusted function
    (identity_binder: its code equals a fresh compile of its owner module's
    own source) whose code bears that name, and the module is its owner,
    the one whose namespace IS its globals. None when there is no such
    function (no definition, a scope that is not a module, a name bound to
    anything else)."""
    d = b.where if b.has_fn else b.span_def
    scope = getattr(b, "scope")
    name = getattr(d, "name", None)
    if name is None or type(scope) is not _types.ModuleType:
        return None
    F = vars(scope).get(name, _MISSING)
    if not _ib.trusted_function(F) or F.__code__.co_name != d.name:
        return None
    return _ib._owner_module(F)


def _same(a, b):
    """Whether nodes `a` and `b` are equal by dump."""
    p = _ast.dump(a)
    q = _ast.dump(b)
    if p == q:
        return True
    return False


def _at(x, call, top, d):
    """Whether module node `x` stands where `call` of definition `d` stands
    in `top`, d's equal in the module."""
    p = getattr(x, "lineno")
    q = getattr(top, "lineno")
    r = getattr(call, "lineno")
    t = getattr(d, "lineno")
    u = p + t
    w = r + q
    if u == w:
        return True
    return False


def _executes(tree):
    """Every call of a method named `execute` in module `tree`, cached by
    the tree."""
    key = id(tree)
    if key not in _EXECUTES:
        got = [x for x in _ast.walk(tree) if _is_execute(x)]
        _EXECUTES[key] = tree, got
    return _EXECUTES.get(key)[1]


def _defs(tree):
    """Every function definition of module `tree`, cached by the tree."""
    key = id(tree)
    if key not in _DEFS:
        got = [x for x in _ast.walk(tree) if isinstance(
            x, (_ast.FunctionDef, _ast.AsyncFunctionDef))]
        _DEFS[key] = tree, got
    return _DEFS.get(key)[1]


def _named_as(x, d):
    """Whether definitions `x` and `d` carry one name (a cheap filter
    before the dump comparison)."""
    p = getattr(x, "name")
    q = getattr(d, "name")
    if p == q:
        return True
    return False


def _is_execute(x):
    """Whether node `x` calls a method named `execute`."""
    return (isinstance(x, _ast.Call) and isinstance(x.func, _ast.Attribute)
            and x.func.attr == "execute")


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


def is_session(expr, session="db"):
    """Whether expression `expr` spells the session: `session` is one
    spelling ('db') or a tuple of them (('db', 'ctx.db'))."""
    return Bindings(None, session=session).is_session(expr)


def is_db_call(call, attr, session="db"):
    return (isinstance(call, _ast.Call) and isinstance(call.func, _ast.Attribute)
            and is_session(call.func.value, session)
            and call.func.attr == attr)


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


class Providers(dict):
    """A pure-callee table: {spelling: its frozen provider objects, one per
    component of the spelling} (round 10, ruling REHEARSAL-R9-A1 (D)).
    Bindings.listed admits a spelling of a Providers table only on its
    provider; every Policy holds its pure tables as Providers.

    Round 11 (ruling FOUR-R10-A2, FIX-R11-ID; finding a1:5655): a table is
    admitted only when every provider object IS the definition
    grammar_providers.PROVIDERS addresses for its component, proven by
    identity_binder.trusted (code identity, C names, immutable types), never
    by the object's writable __module__ and __qualname__. A provider rebound
    before the table was built (`json.loads` replaced by a functools.wraps
    wrapper at import) refuses the table here."""

    def __init__(self, table=(), **kw):
        super().__init__(table, **kw)
        for spelling, objs in self.items():
            desc = _gp.PROVIDERS.get(spelling)
            if desc is None or len(desc) != len(objs):
                raise Unclassified((0, f"{spelling}: no frozen provider "
                                       "description"))
            for o, (m, q) in zip(objs, desc):
                if _ib.trusted(o, m, q) is not True:
                    raise Unclassified((0, f"{spelling}: its provider is not "
                                           f"the definition {m}.{q}"))


class Policy:
    """What one test file lets the visitor accept, all positive and named:
    the plain calls and methods that touch no session, the awaited library
    calls that touch none, the frozen read table (`sql`: the positions an
    execute is 'read' at, Bindings.execute_kind; round 8, M1), and the
    scope names resolve in."""

    def __init__(self, scope, pure_calls, pure_methods, pure_awaits, sql,
                 session="db"):
        self.scope = scope
        # {spelling: its frozen provider objects} (round 10, (D):
        # Bindings.listed admits a listed call only on its provider)
        self.pure_calls = Providers(pure_calls)
        self.pure_methods = frozenset(pure_methods)
        self.pure_awaits = Providers(pure_awaits)
        self.sql = sql
        self.session = session
        # An awaited helper's effect, when a file names its own reading of
        # helpers (the gate's kinds): called with the function, its result
        # is the effect recorded. Only the top-level walk of a span uses it;
        # helper bodies walked by def_effects never do.
        self.helper_hook = None
        # The walk's default-deny Grammar (ruling REHEARSAL-FOUR-R6 (1)(b)):
        # when set, every helper body def_effects reads is admitted by it
        # first. None for a file that has no grammar of its own yet.
        self.grammar = None
        # round 11 (ruling FOUR-R11-A13 (2)): the param_roots of the
        # Bindings def_effects builds for a body this policy walks
        self.param_roots = rule_p_roots
        self.helpers = {}           # id(fn) -> (fn, effects, Deps); round 11
        self.walking = set()        # helpers being walked now
        self.met = _collections.Counter()


# A plain (not awaited) function the walk resolves has its whole body walked
# (finding closed_walk:712), under the calling file's lists plus these: the
# builtins and library calls, and the methods on local values, that the real
# plain callees' bodies make. None of them takes a session; a session method
# is read by the session branch first, whatever its name.
#
# Round 10 (ruling REHEARSAL-R9-A1 (D)): each spelling maps to its frozen
# provider, one object per component of the spelling, bound by this module's
# own static imports; Bindings.listed admits a call only when the scope's
# binding of the spelling IS that provider (a module binding `max = writer`
# refuses). grammar_providers.PROVIDERS names each provider by (module,
# qualified name); the test asserts the two agree.
PLAIN_BODY_CALLS = {
    "Counter": (_collections.Counter,),
    "_json.dumps": (_cw_json, _cw_json.dumps),
    "_json.loads": (_cw_json, _cw_json.loads),
    "abs": (_builtins.abs,), "all": (_builtins.all,), "any": (_builtins.any,),
    "dict": (_builtins.dict,), "float": (_builtins.float,),
    "getattr": (_builtins.getattr,), "id": (_builtins.id,),
    "isinstance": (_builtins.isinstance,), "len": (_builtins.len,),
    "math.ceil": (_cw_math, _cw_math.ceil), "max": (_builtins.max,),
    "min": (_builtins.min,), "repr": (_builtins.repr,),
    "hasattr": (_builtins.hasattr,), "set": (_builtins.set,),
    "sorted": (_builtins.sorted,), "sum": (_builtins.sum,),
    "timedelta": (_cw_datetime.timedelta,), "tuple": (_builtins.tuple,),
    "zip": (_builtins.zip,)}
PLAIN_BODY_METHODS = frozenset({
    "_asdict", "add", "isoformat", "items", "join", "lstrip", "pop", "sort", "split",
    "strip", "time", "total_seconds", "values"})


def plain_effects(fn, policy):
    """The effects of plain function `fn`'s body, walked by def_effects under
    `policy`'s lists plus the plain-body lists (one sub-policy per policy,
    sharing its met counter).

    Round 11: the sub-policy lives on the policy's OWNER, the policy a
    def_effects sub-policy was made from (its lists are the owner's), so
    every walk under one policy shares one plain sub-policy and its helper
    cache; a sub-policy made per walk had its own, and every plain helper
    was walked again under every function that calls it (probe 4:
    _admission_key 392 times in one test)."""
    return helper_effects(fn, _plain_policy(policy))


def _plain_policy(policy):
    """The plain-body sub-policy of `policy` (plain_effects); round 11:
    rule K's A5 walk of a plain callee reads it under the same one."""
    policy = getattr(policy, "_plain_owner", policy)
    sub = getattr(policy, "_plain_sub", None)
    if sub is None:
        sub = Policy(policy.scope, policy.pure_calls | PLAIN_BODY_CALLS,
                     policy.pure_methods | PLAIN_BODY_METHODS,
                     policy.pure_awaits, policy.sql, policy.session)
        sub.met = policy.met
        sub.grammar = policy.grammar
        sub._plain_owner = policy           # its own plain helpers: the same lists
        policy._plain_sub = sub
    return sub


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


# --- round 11, F10: the receiver of a pure method, by provenance ----------
#
# Ruling FOUR-R11-A1 (3) (finding closed_walk:1775): a method call admitted
# by its NAME (pure_methods) is pure only when its receiver is exactly the
# frozen type the method belongs to. The receiver's PROVENANCE inside the
# walked function decides it (receiver_provenance), never its spelling:
#
#   "B"     builtin by construction, the whole value: a literal, a display
#           or comprehension of such values, a call of a frozen provider
#           whose result is builtin (RESULT_BUILTIN), a method result,
#           subscript or attribute of such a value, a column value of a
#           session row, the return of a trusted function every return of
#           which is such a value;
#   ("C", e)  an exact builtin container (a display, a comprehension, a
#           listed constructor's result) whose elements have provenance e:
#           its own methods run builtin code; what it yields is e;
#   "R"     a session result (`await <session>.execute(...)`, and its
#           .mappings()/.scalars()), whose methods are the result methods;
#   "ROW"   a row a session result yields (a list of rows is ("C", "ROW"));
#   ("P", ps, deep)  derived from the walked function's own parameters
#           ps (a sorted tuple of names): one of them itself (deep False),
#           or a value read from them (deep True: an attribute, a subscript,
#           a method result, an element, an operation over them and builtin
#           operands). The verdict is CONDITIONAL, one effect
#           "receiver:<p>:<group>" per parameter (group "deep" when derived:
#           p must then be builtin whole), discharged at every walked call
#           site by the argument's provenance there (discharge_receivers),
#           carried up through the callers' own parameters, refused in a
#           span walked on its own;
#   None    anything else (a user class instance, an unknown callable's
#           result, a name bound to either): the call site is refused.
#
# Every rule is a bound on the value's TYPE that holds whatever path
# reaches the read (a name bound more than once takes the join of every
# binding; a name met again while its own bindings are read adds nothing to
# the join). A display or a listed container constructor is an exact
# container whatever its elements ("B" only when they all are); a mutation
# (an insertion, a store into the value) never changes the name's own type:
# what it inserts joins the container's elements.
RESULT_METHODS = frozenset({"all", "fetchall", "first", "mappings", "one",
                            "scalar", "scalar_one", "scalars"})
ROW_METHODS = frozenset({"get", "items", "values", "keys", "_asdict"})
# Frozen providers (by the spelling the pure tables list, resolved through
# Bindings.listed against the policy's Providers table) whose result is
# builtin by construction: "B" a whole builtin value, "C" an exact builtin
# container of its argument's elements (B when they are), "E" one of its
# arguments' elements (min, max, random.choice).
RESULT_BUILTIN = {
    "str": "B", "int": "B", "float": "B", "bool": "B", "len": "B",
    "repr": "B", "round": "B", "abs": "B", "id": "B", "isinstance": "B",
    "hasattr": "B", "json.dumps": "B", "_json.dumps": "B",
    "json.loads": "B", "_json.loads": "B", "math.ceil": "B",
    "timedelta": "B", "datetime.timedelta": "B", "uuid.uuid4": "B",
    "uuid_mod.uuid4": "B", "uuid.UUID": "B", "time.time": "B",
    "time.monotonic": "B", "datetime.now": "B", "datetime.utcnow": "B",
    "datetime.datetime.now": "B", "datetime.datetime.utcnow": "B",
    "sum": "B", "any": "B", "all": "B",
    "list": "C", "tuple": "C", "set": "C", "dict": "C", "sorted": "C",
    "frozenset": "C", "min": "E", "max": "E", "random.choice": "E",
    # round 11 (run 13): an exact collections.Counter, the frozen provider's
    # own class (a dict whose methods are dict's or the frozen stdlib
    # class's own), counting its argument's elements
    "Counter": "C", "collections.Counter": "C",
    # round 11 (run 17): iterators of their arguments' elements: zip's
    # elements are tuples of one element of each argument, enumerate's a
    # count and an element, reversed's an element
    "zip": "Z", "enumerate": "N", "reversed": "C",
}
_DISPLAYS = (_ast.List, _ast.Tuple, _ast.Set)
_INSERTING = {"append": (0,), "add": (0,), "insert": (1,),
              "setdefault": (0, 1)}
_INSERTING_ALL = frozenset({"extend", "update"})
_PROV_DEPTH = 40


def _is_p(p):
    return isinstance(p, tuple) and p[0] == "P"


def _is_c(p):
    """An exact builtin container ("C", element provenance)."""
    return isinstance(p, tuple) and p[0] == "C"


def _is_u(p):
    """One of several provenances ("U", frozenset of alternatives): a name
    bound in ways no single provenance covers (a session row in one
    binding, a parameter's element in another). Every use is judged per
    alternative: each must meet the use, and each parameter alternative
    carries its own condition (round 11, run 12)."""
    return isinstance(p, tuple) and p[0] == "U"


def _alts(p):
    """The alternatives of provenance `p` (itself when it is not a union),
    in the order of their canonical text (_prov_text)."""
    return sorted(p[1], key=_prov_text) if _is_u(p) else [p]


def _prov_text(p):
    """Round 11 (ruling FOUR-R11-A10 (3)): the sort key of a provenance:
    its repr with every frozenset (a union's alternatives, at any depth)
    written as its members ordered by their own canonical text. A plain
    repr writes a frozenset in the set's iteration order, which follows the
    process's string hash; the key does not. A provenance that holds no
    frozenset keeps its repr, so alternatives that hold none keep the order
    repr gave them."""
    return repr(_prov_canon(p))


def _prov_canon(p):
    """`p` with each frozenset replaced by ("frozenset", its members in
    canonical-text order), recursively (_prov_text)."""
    if isinstance(p, frozenset):
        items = [_prov_canon(x) for x in p]
        items = sorted(items, key=repr)
        return ("frozenset", tuple(items))
    if isinstance(p, tuple):
        return tuple(_prov_canon(x) for x in p)
    return p


def _is_a(p):
    """Round 11 (rule K's A5 clause): ("A", q, path, deep), a value read from
    parameter q at attribute `path` of it, q bound to an instance whose
    per-attribute conditions the walk carries (deep: read from that value,
    so it must be builtin whole)."""
    return isinstance(p, tuple) and p[0] == "A"


def _attr_of(p, attr):
    """The provenance of attribute `attr` of a value of provenance `p`: an
    A value's path extended, else _derive."""
    return _over(lambda a: ("A", a[1], a[2] + (attr,), False)
                 if _is_a(a) and not a[3] else _derive(a), p)


def _at_path(p, path):
    """The provenance of the value at attribute `path` of a value of `p`."""
    for attr in path:
        p = _attr_of(p, attr)
    return p


def _a_condition(a, group):
    """The condition an A alternative carries, on its parameter's path."""
    g = "deep" if (a[3] or group == "deep") else group
    return "receiver:" + ".".join((a[1],) + a[2]) + ":" + g


def _over(f, p):
    """The join of `f` applied to each alternative of `p`."""
    return _join([f(a) for a in _alts(p)]) if _is_u(p) else f(p)


ROWS = ("C", "ROW")                         # a list of session rows


def _derive(p):
    """The provenance of a value READ from a value of provenance `p` (an
    attribute, a subscript, a method result)."""
    if _is_u(p):
        return _over(_derive, p)
    if p in ("B", "ROW"):
        return "B"
    if _is_p(p):
        return ("P", p[1], True)
    if _is_a(p):
        return ("A", p[1], p[2], True)
    if _is_c(p):
        return p[1]                         # one of its elements
    return None


def _elements(p):
    """The provenance of an element a value of provenance `p` yields."""
    if _is_u(p):
        return _over(_elements, p)
    if p in ("B", "RS"):
        return "B"                          # a scalar result yields values
    if p == "R":
        return "ROW"
    if _is_c(p):
        return p[1]
    if _is_p(p):
        return ("P", p[1], True)
    if _is_a(p):
        return ("A", p[1], p[2], True)
    return None


def _join(ps):
    """The provenance of a value that is one of values of provenances
    `ps`: equal provenances are themselves; parameters join with builtin
    values; exact containers join with builtin values and with each other,
    their elements joined; anything else that is no single provenance is
    the union of the alternatives (round 11, run 12: a name bound once to
    a session row and once to a parameter's element), each judged on its
    own wherever the value is used."""
    ps = list(ps)
    if not ps or any(p is None for p in ps):
        return None
    flat = [a for p in ps for a in _alts(p)]
    if any(_is_a(p) for p in flat):
        # round 11 (rule K's A5 clause): an A alternative is kept beside
        # the join of the rest, as a parameter one is (a builtin value
        # beside it adds no condition)
        rest = [p for p in flat if not _is_a(p) and p != "B"]
        j = _join(rest) if rest else None
        if rest and j is None:
            return None
        alts = {p for p in flat if _is_a(p)} | (set(_alts(j)) if rest else set())
        return next(iter(alts)) if len(alts) == 1 else ("U", frozenset(alts))
    got = _join_one(flat)
    if got is not None:
        return got
    alts = {p for p in flat if p in ("ROW", "R", "RS")}
    if "B" in flat and not any(_is_p(p) or _is_c(p) or p == "ROW"
                               for p in flat):
        alts.add("B")                       # beside a result, kept itself
    cs = [p[1] for p in flat if _is_c(p)]
    if cs:
        alts.add(("C", _join(cs + (["B"] if "B" in flat else []))))
    names = sorted({n for p in flat if _is_p(p) for n in p[1]})
    if names:
        alts.add(("P", tuple(names), any(p[2] for p in flat if _is_p(p))))
    if any(not (_is_p(p) or _is_c(p) or p in ("B", "ROW", "R", "RS"))
           for p in flat):
        return None
    return next(iter(alts)) if len(alts) == 1 else ("U", frozenset(alts))


def _join_one(ps):
    """_join's single-provenance rules over alternatives `ps` (no union,
    no None), or None when no single provenance covers them."""
    params = sorted({n for p in ps if _is_p(p) for n in p[1]})
    rest = [p for p in ps if not _is_p(p)]
    if params:
        if all(p == "B" for p in rest):
            return ("P", tuple(params), any(p[2] for p in ps if _is_p(p)))
        return None
    if all(p == "B" for p in rest):
        return "B"
    if all(p == "B" or _is_c(p) for p in rest):
        es = [p[1] for p in rest if _is_c(p)]
        if len(es) != len(rest):
            es.append("B")                  # a builtin value's own parts
        return ("C", _join(es))
    if all(p in ("B", "ROW") for p in rest):
        # a row or a builtin value: "ROW" admits no use that "B" does not
        # (the join is the narrower of the two)
        return "ROW"
    return rest[0] if all(p == rest[0] for p in rest) else None


def _container(elts):
    """An exact builtin container holding elements of provenances `elts`:
    "B" when every element is, else ("C", their join)."""
    j = _join(elts) if elts else "B"
    return "B" if j == "B" else ("C", j)


def _comp_element(expr, b, policy, d):
    if isinstance(expr, _ast.DictComp):
        return _join([receiver_provenance(expr.key, b, policy, d),
                      receiver_provenance(expr.value, b, policy, d)])
    return receiver_provenance(expr.elt, b, policy, d)


def receiver_provenance(expr, b, policy=None, depth=0):
    """The provenance of expression `expr` in the function `b` resolves
    (see above): "B", ("C", element), "R", "ROW", ("P", names, deep) or
    None."""
    if depth > _PROV_DEPTH:
        return None
    d = depth + 1
    if isinstance(expr, _ast.Constant):
        return "B"
    if isinstance(expr, _ast.JoinedStr):
        return "B"                          # a str, whatever it formats
    if isinstance(expr, _DISPLAYS):
        return _container([receiver_provenance(e, b, policy, d)
                           for e in expr.elts])
    if isinstance(expr, _ast.Dict):
        if any(k is None for k in expr.keys):
            return ("C", None)
        return _container([receiver_provenance(x, b, policy, d)
                           for x in list(expr.keys) + list(expr.values)])
    if isinstance(expr, (_ast.ListComp, _ast.SetComp, _ast.DictComp)):
        return _container([_comp_element(expr, b, policy, d)])
    if isinstance(expr, (_ast.BinOp, _ast.BoolOp, _ast.Compare,
                         _ast.UnaryOp)):
        parts = ([expr.left, expr.right] if isinstance(expr, _ast.BinOp)
                 else list(expr.values) if isinstance(expr, _ast.BoolOp)
                 else [expr.left] + list(expr.comparators)
                 if isinstance(expr, _ast.Compare) else [expr.operand])
        j = _join(receiver_provenance(x, b, policy, d) for x in parts)
        if isinstance(expr, _ast.BoolOp):
            return j                        # one of the operands
        return _operated(expr, j)
    if isinstance(expr, _ast.IfExp):
        return _join([receiver_provenance(expr.body, b, policy, d),
                      receiver_provenance(expr.orelse, b, policy, d)])
    if isinstance(expr, _ast.Await):
        call = expr.value
        if not isinstance(call, _ast.Call):
            return None
        if (isinstance(call.func, _ast.Attribute)
                and call.func.attr == "execute" and b.is_session(call.func.value)):
            return "R"
        return _returned(call, b, policy, d, awaited=True)
    if isinstance(expr, _ast.Subscript):
        v = receiver_provenance(expr.value, b, policy, d)
        sl = isinstance(expr.slice, _ast.Slice)
        # a slice of a list is one
        return _over(lambda a: a if (_is_c(a) and sl) else _derive(a), v)
    if isinstance(expr, _ast.Attribute):
        return _attr_of(receiver_provenance(expr.value, b, policy, d),
                        expr.attr)
    if isinstance(expr, _ast.Call):
        return _call_provenance(expr, b, policy, d)
    if isinstance(expr, _ast.Name):
        return _name_provenance(expr.id, b, policy, d, expr)
    return None


def _call_provenance(call, b, policy, d):
    f = call.func
    if isinstance(f, _ast.Attribute):
        if b.session_value(f.value):        # the session, or its root name
            return None
        listed = _listed_kind(f, b, policy)
        if listed is None:
            r = receiver_provenance(f.value, b, policy, d)
            got = _over(lambda a: _method_result(a, f.attr, call, b, policy, d), r)
            # round 11, rule T (rulings FOUR-R11-A3 (3), FOUR-R11-A5): a
            # result no other rule proves, of a call of a named pair,
            # discharged by its bound (Bindings.rule_t) or refused there
            return got if got is not None else b.rule_t(call)
    kind = _listed_kind(f, b, policy)
    if kind is None:
        try:
            cls = b.namedtuple_class(f)
        except Unclassified:
            cls = None
        if cls is not None:
            # round 11 (run 16): a constructor-pure namedtuple class of a
            # complete frozen definition scope (the walk's own route for
            # admitting its call) makes an exact tuple of its arguments; a
            # field read is one of them
            return _container([receiver_provenance(a, b, policy, d)
                               for a in list(call.args)
                               + [k.value for k in call.keywords]])
        nested = b.nested_def(f, call)
        if nested is not None:
            return _nested_returns(nested, b, policy, d)
        return _returned(call, b, policy, d, awaited=False)
    if kind == "B":
        return "B"
    if kind == "E":                         # min/max/choice: one element
        if len(call.args) == 1:
            return _arg_elements(call.args[0], b, policy, d)
        return _join(receiver_provenance(a, b, policy, d) for a in call.args)
    if kind == "C":
        if not call.args:
            return "B"
        return _container([_arg_elements(a, b, policy, d) for a in call.args])
    if kind in ("Z", "N"):
        parts = [_arg_elements(a, b, policy, d) for a in call.args[:1 if kind == "N" else None]]
        if kind == "N":
            parts = ["B"] + parts
        return _container([_container(parts)])
    return None



def _nested_returns(fn, b, policy, d):
    """The join of every value nested definition `fn` returns (the
    implicit None included), read in the walked function's own bindings
    (a read inside `fn` sees `fn`'s scope first, so its parameters are
    unproven); a definition reached again while its returns are read is
    unproven (None)."""
    seen = b.__dict__.setdefault("_nested_reading", set())
    if id(fn) in seen:
        return None
    seen.add(id(fn))
    try:
        rets, todo = [], list(fn.body)
        while todo:
            n = todo.pop()
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                              _ast.Lambda, _ast.ClassDef)):
                continue
            if isinstance(n, _ast.Return):
                rets.append(n.value)
            todo.extend(_ast.iter_child_nodes(n))
        return _join(["B" if r is None else receiver_provenance(r, b, policy, d)
                      for r in rets] + ["B"])
    finally:
        seen.discard(id(fn))


def _operated(expr, j):
    """The provenance of an operator's result over operands joined as `j`
    (round 11, run 18): an identity test is a bool whatever its operands
    (it runs no operand code); otherwise the operands' own operator code
    runs, so every alternative must be builtin whole or an exact builtin
    container (a comparison of such values is a bool; arithmetic over a
    container is a container of the same elements), and a parameter
    alternative makes the result derived from it."""
    if isinstance(expr, _ast.Compare) and all(
            isinstance(o, (_ast.Is, _ast.IsNot)) for o in expr.ops):
        return "B"
    alts = _alts(j)
    # round 11 (rule K's A5 clause): an operand read from a handed
    # instance's attribute is kept aside, then read whole
    handed = [a for a in alts if _is_a(a)]
    alts = [a for a in alts if not _is_a(a)] or ["B"]
    if j is None or not all(_is_p(a) or a == "B" or _is_c(a) for a in alts):
        return None
    names = sorted({n for a in alts if _is_p(a) for n in a[1]})
    cs = [a for a in alts if _is_c(a)]
    if isinstance(expr, _ast.BinOp) and cs:
        out = ("C", _join([a[1] for a in cs] + ["B"]))
    else:
        out = "B"
    parts = [out]
    if names:
        parts.append(("P", tuple(names), True))
    # its operator code runs, so a handed operand is read whole
    parts += [("A", a[1], a[2], True) for a in handed]
    return _join(parts) if len(parts) > 1 else out


def _method_result(r, m, call, b, policy, d):
    """The provenance of method `m`'s result on a receiver of (single)
    provenance `r`, for `call`. A session result's .scalars() is a scalar
    result ("RS"), whose rows are column values; a column value is builtin
    (round 11, run 12: `.scalars().all()` read as rows refused
    `(v or "0").lstrip` over its values)."""
    if r == "R":
        if m == "mappings":
            return "R"
        if m == "scalars":
            return "RS"
        if m in ("first", "one"):
            return "ROW"
        if m in ("scalar", "scalar_one"):
            return "B"
        if m in ("all", "fetchall"):
            return ROWS
        return None
    if r == "RS":
        if m in ("first", "one", "scalar", "scalar_one"):
            return "B"
        if m in ("all", "fetchall"):
            return "B"                      # a list of column values
        return None
    if r == "ROW":
        return "B" if m in ROW_METHODS else None
    if _is_c(r):
        if m in ("get", "pop", "setdefault") and len(call.args) > 1:
            return _join([r[1], receiver_provenance(
                call.args[1], b, policy, d)])
        if m in ("get", "pop", "setdefault"):
            return _join([r[1], "B"])       # or None
        if m in ("copy", "keys", "values", "items"):
            return r
        if m == "join":
            return "B"
        return None
    if r == "B" or _is_p(r) or _is_a(r):
        if m in ("get", "pop", "setdefault") and len(call.args) > 1:
            return _join([_derive(r), receiver_provenance(
                call.args[1], b, policy, d)])
        return _derive(r)
    return None


def _arg_elements(a, b, policy, d):
    """The provenance of the elements an iterable argument `a` yields."""
    if isinstance(a, (_ast.GeneratorExp, _ast.ListComp, _ast.SetComp,
                      _ast.DictComp)):
        return _comp_element(a, b, policy, d)
    return _elements(receiver_provenance(a, b, policy, d))


def _listed_kind(f, b, policy):
    """RESULT_BUILTIN's kind for callee `f` when the policy's own Providers
    table lists it at its frozen provider (identity-checked by listed; a
    plain dict would be read by spelling alone), else None."""
    kind = RESULT_BUILTIN.get(_ast.unparse(f))
    if kind is None or policy is None or not isinstance(
            policy.pure_calls, Providers):
        return None
    try:
        if b.listed(f, policy.pure_calls) is None:
            return None
    except Unclassified:
        return None
    return kind


_RET_TREES = {}


def _returned(call, b, policy, d, awaited):
    """The provenance of what a call of a walked function returns: the
    callee resolved by the resolver (a trusted definition, Bindings.callee),
    its own body's every return value (and the implicit None) read in its
    own bindings, a parameter-derived result mapped to this call's
    argument."""
    if d > _PROV_DEPTH // 2:
        return None
    f = call.func
    try:
        if isinstance(f, _ast.Name):
            fn = b.callee(f)
        elif (isinstance(f, _ast.Attribute) and isinstance(f.value, _ast.Call)
              and isinstance(f.value.func, _ast.Name) and not f.value.args
              and not f.value.keywords
              and module_accessor(b.callee(f.value.func), b.grammar)
              is not None):
            fn = b.callee(f)                # `<accessor>().f(...)`
        else:
            return None
    except Unclassified:
        return None
    if fn is None or _inspect.iscoroutinefunction(fn) is not awaited:
        return None
    j = _returns_cached(fn, b, policy)

    def mapped(p):
        # the callee's parameter-derived parts, wherever they stand (an
        # alternative, a container's elements), read as this call's
        # arguments (round 11: a container of a parameter was returned
        # with the CALLEE's parameter names)
        if _is_u(p):
            return _over(mapped, p)
        if _is_c(p):
            if p[1] is None:
                return p
            e = mapped(p[1])
            return None if e is None else _container([e])
        if not _is_p(p):
            return p
        params = list(_inspect.signature(fn).parameters)
        if any(isinstance(a, _ast.Starred) for a in call.args) or any(
                k.arg is None for k in call.keywords):
            return None
        out = []
        for name in p[1]:
            if name not in params:
                return None
            at = params.index(name)
            arg = call.args[at] if at < len(call.args) else next(
                (k.value for k in call.keywords if k.arg == name), None)
            if arg is None:
                return None
            a = receiver_provenance(arg, b, policy, d)
            out.append(_derive(a) if p[2] else a)
        return _join(out)
    return mapped(j)


_RET_READING = set()


def _returns_cached(fn, b, policy):
    """_returns_join of `fn`, one entry per function object on the policy
    (or none without one), honoured only while its recorded Deps hold."""
    memo = (policy.__dict__.setdefault("_ret_joins", {})
            if policy is not None else {})
    hit = memo.get(id(fn))
    if hit is not None:
        if hit[0] is fn and hit[2].valid():
            _ib.carry(hit[2])
            return hit[1]
        del memo[id(fn)]
    key = (id(fn), id(policy))
    if key in _RET_READING:
        return None                         # its own returns, being read
    _RET_READING.add(key)
    try:
        with _ib.recording() as deps:
            _ib.observe_chain(fn)
            j = _returns_join(fn, b, policy, 0)
    finally:
        _RET_READING.discard(key)
    memo[id(fn)] = (fn, j, deps)
    return j


def _returns_join(fn, b, policy, d):
    """The join of the provenances of every value trusted function `fn`
    returns (the implicit None included), read in its own bindings."""
    hit = _RET_TREES.get(id(fn.__code__))
    if hit is None or hit[0] is not fn.__code__:
        try:
            tree = _helper_tree(fn)
        except (Unclassified, OSError, TypeError, SyntaxError):
            return None
        hit = _RET_TREES[id(fn.__code__)] = (fn.__code__, tree)
    tree = hit[1]
    scope = _ib._owner_module(fn)
    if scope is None:
        return None
    cb = Bindings(scope, tree, session=b.session, grammar=b.grammar)
    rets, todo, falls = [], list(tree.body), True
    while todo:
        n = todo.pop()
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                          _ast.Lambda, _ast.ClassDef)):
            continue
        if isinstance(n, _ast.Return):
            rets.append(n.value)
        todo.extend(_ast.iter_child_nodes(n))
    provs = ["B" if r is None else receiver_provenance(r, cb, policy, d)
             for r in rets] + (["B"] if falls else [])
    return _join(provs)


def _name_provenance(name, b, policy, d, at=None):
    got, sc = _visible_sites(name, b, at)
    if not got:
        mod = b.scope if type(b.scope) is _types.ModuleType else None
        v = vars(mod).get(name, _MISSING) if mod is not None else _MISSING
        if (v is not _MISSING and type(v) in (str, int, float, bool, type(None))
                and _ib.trusted_constant(v, mod, name)):
            return "B"
        return None
    # a name reached again while its own bindings are being read (`x = x +
    # 1`): the cycle adds nothing to the join ("B" is the join's identity
    # among builtin values; a non-builtin binding still decides it)
    memo = b.__dict__.setdefault("_prov_memo", {})
    key = (name, sc)
    if key in memo:
        return memo[key]
    visiting = b.__dict__.setdefault("_prov_visiting", set())
    hits = b.__dict__.setdefault("_prov_hits", [])
    if key in visiting:
        hits.append(key)
        return "B"
    mark = len(hits)
    visiting.add(key)
    try:
        provs, ins = [], []
        for kind, node in got:
            if kind == "mutated":
                ins.extend(_inserted(name, node, b, policy, d))
            else:
                provs.append(_binding_provenance(name, kind, node, b, policy, d))
    finally:
        visiting.discard(key)
    base = _join(provs)
    if not ins or all(p == "B" for p in ins):
        out = base
    elif base == "B" or _is_c(base):
        # a mutation changes what the value holds, never its own type
        out = ("C", _join([base[1] if _is_c(base) else "B"] + ins))
    else:
        out = None
    if all(h == key for h in hits[mark:]):
        memo[key] = out                     # no other name's provisional value
    hits[mark:] = [h for h in hits[mark:] if h != key]   # an ancestor's stay
    return out


_SCOPES = (_ast.Lambda, _ast.FunctionDef, _ast.AsyncFunctionDef,
           _ast.ListComp, _ast.SetComp, _ast.DictComp, _ast.GeneratorExp)


def _scope_chain(node, b, outward=False):
    """The nested scopes of the walked function that enclose `node`,
    innermost first (a lambda's or nested definition's body, a
    comprehension past its first iterable), by Python's scoping: a
    lambda's defaults, a definition's decorators, defaults and annotations,
    and a comprehension's first iterable are read in the enclosing scope.
    With `outward` (an assignment expression's target), comprehensions are
    skipped: it binds the scope around them."""
    out, c, came = [], node, None
    p = b.parent.get(id(c))
    while p is not None and p is not b.where:
        if isinstance(p, _ast.Lambda) and c is p.body:
            out.append(p)
        elif (isinstance(p, (_ast.FunctionDef, _ast.AsyncFunctionDef))
              and any(c is s for s in p.body)):
            out.append(p)
        elif isinstance(p, (_ast.ListComp, _ast.SetComp, _ast.DictComp,
                            _ast.GeneratorExp)) and not outward:
            first = p.generators[0]
            if not (c is first and came is first.iter):
                out.append(p)
        came, c = c, p
        p = b.parent.get(id(c))
    return out


def _binding_scope(kind, node, b):
    """The nested scope a binding of the walked function binds in (None for
    the function's own), or "all" for a mutation or a global declaration
    (read wherever the name is)."""
    if kind in ("mutated", "global"):
        return "all"
    if kind == "param":
        return None if node is b.where else node
    if kind == "import":
        node = node[0]
    outward = isinstance(b.parent.get(id(node)), _ast.NamedExpr)
    if kind == "def":
        ch = _scope_chain(node, b)
    else:
        ch = _scope_chain(node, b, outward=outward)
    return ch[0] if ch else None


def _visible_sites(name, b, at):
    """Round 11 (run 12): the bindings of `name` a read at node `at`
    sees, by Python's scoping (a lambda's parameter is not the function's
    name of the same spelling), and the scope they bind in (None for the
    function's own); every binding when the read's place is unknown."""
    got = b.sites.get(name, ())
    if at is None or not got:
        return got, None
    by = [(_binding_scope(k, n, b), (k, n)) for k, n in got]
    shared = [kn for s, kn in by if s == "all"]
    for s in _scope_chain(at, b) + [None]:
        own = [kn for t, kn in by if t is s]
        if own:
            return own + shared, (None if s is None else id(s))
    return shared, None


def _inserted(name, node, b, policy, d):
    """The provenances of what mutation site `node` puts into `name`'s
    value (a store into it, or an inserting method): a container that
    received only builtin values stays builtin (_name_provenance)."""
    if isinstance(node, _ast.Call):
        m = node.func.attr if isinstance(node.func, _ast.Attribute) else None
        if m in _INSERTING:
            return [receiver_provenance(node.args[i], b, policy, d)
                    if i < len(node.args) else None for i in _INSERTING[m]]
        if m in _INSERTING_ALL:
            out = [_arg_elements(a, b, policy, d) for a in node.args]
            out += [receiver_provenance(k.value, b, policy, d)
                    for k in node.keywords]
            return out or ["B"]
        return ["B"]                        # pop, remove, sort, clear ...
    if isinstance(node, (_ast.Assign, _ast.AugAssign, _ast.AnnAssign)):
        v = node.value
        return [receiver_provenance(v, b, policy, d) if v is not None else "B"]
    if isinstance(node, _ast.Delete):
        return ["B"]
    return [None]


def _binding_provenance(name, kind, node, b, policy, d):
    if kind == "param":
        if node is b.where:
            if name in b.param_values:
                return b.param_values[name]
            return ("P", (name,), False)
        return None
    if kind != "local" or not isinstance(node, _ast.Name):
        return None
    par = b.parent.get(id(node))
    if isinstance(par, _ast.Assign):
        # one target, or a chain (`a = b = None`): each target is the value
        if any(t is node for t in par.targets):
            return receiver_provenance(par.value, b, policy, d)
        return None
    if isinstance(par, _ast.Tuple):
        top = b.parent.get(id(par))
        if isinstance(top, (_ast.For, _ast.comprehension)) and top.target is par:
            return _derive(_arg_elements(top.iter, b, policy, d))
        if isinstance(top, _ast.Assign) and any(t is par for t in top.targets):
            if (isinstance(top.value, _ast.Tuple)
                    and len(top.value.elts) == len(par.elts)):
                return receiver_provenance(
                    top.value.elts[par.elts.index(node)], b, policy, d)
            return _derive(receiver_provenance(top.value, b, policy, d))
        return None
    if isinstance(par, _ast.AnnAssign) and par.target is node and par.value is not None:
        return receiver_provenance(par.value, b, policy, d)
    if isinstance(par, _ast.NamedExpr) and par.target is node:
        return receiver_provenance(par.value, b, policy, d)
    if isinstance(par, (_ast.For, _ast.comprehension)) and par.target is node:
        return _arg_elements(par.iter, b, policy, d)
    return None


def receiver_group(method):
    """The type group a pure method's receiver must be: "result" (a session
    result), "row" (a builtin value or a session row) or "builtin"."""
    if method in RESULT_METHODS:
        return "result"
    if method in ROW_METHODS:
        return "row"
    return "builtin"


def receiver_meets(p, group):
    """Whether provenance `p` discharges a receiver of type group `group`
    ("deep": the parameter is read from, so it must be builtin whole). A
    union meets a group when every alternative does; a parameter
    alternative never does here (its condition is the caller's to carry)."""
    if _is_u(p):
        return all(receiver_meets(a, group) for a in _alts(p))
    if group == "result":
        return p in ("R", "RS")
    if group == "row":
        return p in ("B", "ROW") or _is_c(p)
    if group == "deep":
        return p in ("B", "ROW", "R", "RS") or (
            _is_c(p) and receiver_meets(p[1], "deep"))
    return p == "B" or _is_c(p)


_NOT_CONSTANT = object()


def _in_param_order(conds, names):
    """Conditions `conds` ("receiver:<param>[.<attr>...]:<group>", or
    "callback:<param>") as a list sorted by the named parameter's position
    in `names`, then by the condition's text; a parameter not in `names`
    sorts last (the caller's loop then refuses it by its own message).
    Round 11 (ruling FOUR-R11-A10 (3)): written in the walker grammar's
    frozen shapes (the key class of 1279ffc5 was not)."""
    ranked = []
    for e in conds:
        p = e.split(":", 2)[1].split(".")[0]
        at = len(names)
        if p in names:
            at = names.index(p)
        ranked.append((at, e))
    return [e for _at, e in sorted(ranked)]


def _param_table(fn):
    """([names], [defaults]) of function object or definition `fn`'s
    parameters in order; a missing default is Parameter.empty, a definition's
    default that is not a constant is _NOT_CONSTANT (never provable)."""
    if isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
        a = fn.args
        pos = a.posonlyargs + a.args
        dfl = [_inspect.Parameter.empty] * (len(pos) - len(a.defaults)) + [
            x.value if isinstance(x, _ast.Constant) else _NOT_CONSTANT
            for x in a.defaults]
        kw = [x.value if isinstance(x, _ast.Constant) else
              (_inspect.Parameter.empty if x is None else _NOT_CONSTANT)
              for x in a.kw_defaults]
        return [x.arg for x in pos + a.kwonlyargs], dfl + kw
    params = list(_inspect.signature(fn).parameters.values())
    return [q.name for q in params], [q.default for q in params]


def discharge_receivers(call, fn, effects, line, visitor):
    """`effects` of callee `fn` at call `call` without its receiver
    conditions ("receiver:<param>:<group>"), each discharged here by the
    provenance of the argument the call binds to that parameter (its
    default when the call passes none: a None or immutable builtin
    constant); an argument derived from the caller's own parameter carries
    the condition on to the caller's verdict ("deep" when derived); any
    other provenance refuses the call site (ruling FOUR-R11-A1 (3)).
    `visitor` supplies the caller's bindings (.b), policy (.p), whether a
    def_effects walk encloses it (.helper) and its effect list (.effects)."""
    conds = [e for e in effects if e.startswith("receiver:")]
    if not conds:
        return effects
    co = (fn.name if isinstance(fn, (_ast.FunctionDef, _ast.AsyncFunctionDef))
          else fn.__code__.co_name)
    names, defaults = _param_table(fn)
    # round 11 (ruling FOUR-R11-A10 (C)): `effects` may be a set, whose
    # iteration order is the process's string-hash order (PYTHONHASHSEED 1, 2
    # and 3 named `members`, `volumes`, `volumes` first at _group_region's
    # call of the group picker, RULES NOTES); the conditions are refused in
    # the callee's parameter order, then by their text, so the first refusal
    # does not depend on the hash seed.
    conds = _in_param_order(conds, names)
    for e in conds:
        # round 11 (rule K's A5 clause): a condition may name a path of the
        # parameter ("receiver:<param>.<attr>...:<group>")
        _r, dotted, group = e.split(":", 2)
        p, *rest = dotted.split(".")
        path = tuple(rest)
        at = names.index(p)
        if any(isinstance(a, _ast.Starred) for a in call.args) or any(
                k.arg is None for k in call.keywords):
            raise Unclassified((line, f"a call of {co} with "
                                      f"unpacked arguments, whose {p} is a "
                                      "receiver"))
        arg = None
        if at < len(call.args):
            arg = call.args[at]
        for k in call.keywords:
            if k.arg == p:
                arg = k.value
        if arg is None:
            dft = defaults[at]
            if dft is _inspect.Parameter.empty or type(dft) not in (
                    type(None), str, int, float, bool, tuple, frozenset, bytes):
                raise Unclassified((line, f"{co}'s receiver "
                                          f"parameter {p} has a default the "
                                          "walk cannot prove builtin"))
            continue
        # round 11 (rule N, ruling FOUR-R11-A10 (1)): a named member's
        # argument is discharged by its bound, marked for the bound test
        if _member_arg(call, fn, arg, p, path, group, visitor):
            continue
        # round 11 (rules W, P and K): at a span walked on its own, an
        # argument rooted at an exact frozen class instance is discharged
        # by rule K, marked for the bound test
        if visitor.helper is None and _bound_discharge(
                call, fn, arg, p, path, group, visitor):
            continue
        prov = _at_path(receiver_provenance(arg, visitor.b, visitor.p), path)
        # each alternative of a union on its own (round 11, run 12): every
        # other one must meet the group, every parameter one carries on
        alts = _alts(prov)
        handed = [a for a in alts if _is_a(a)]
        alts = [a for a in alts if not _is_a(a)]
        if not all(_is_p(a) or receiver_meets(a, group) for a in alts):
            raise Unclassified((line, f"a call of {co} whose "
                                      f"{dotted}, a receiver of its {group} "
                                      f"methods, is {_ast.unparse(arg)}, which "
                                      "the walk cannot prove builtin"))
        for a in handed + alts:
            if _is_a(a) and visitor.helper is None:
                raise Unclassified((line, f"a call of {co} whose {dotted} is "
                                          "read from a handed instance outside "
                                          "the walk that binds it"))
            if _is_a(a) and not a[2] and not a[3] and not path:
                # the handed instance whole, at a receiver parameter: its
                # per-attribute conditions, walked (the A5 clause)
                for c in _bound_conditions(fn, visitor.p, p, line):
                    visitor.effects.append((
                        "receiver:" + ".".join((a[1],) + c[0]) + ":" + c[1],
                        "pure"))
                continue
            if _is_a(a):
                visitor.effects.append((_a_condition(a, group), "pure"))
                continue
            if not _is_p(a):
                continue
            if visitor.helper is None:
                raise Unclassified((line, f"a call of {co} "
                                          f"whose {p}, a receiver, is "
                                          f"{_ast.unparse(arg)}, read from the "
                                          f"parameter {', '.join(a[1])}, "
                                          "which no walked call site "
                                          "discharges"))
            g = "deep" if (a[2] or group == "deep") else group
            for q in a[1]:
                visitor.effects.append((f"receiver:{q}:{g}", "pure"))
    return frozenset(x for x in effects if not x.startswith("receiver:"))


def _bound_conditions(fn, policy, q, line):
    """Rule K's A5 clause (ruling FOUR-R11-A4 (2)(g)): [(path, group)], the
    conditions callee `fn` puts on its parameter q when q is bound to a
    handed instance ("A", q, (), False): its body walked again, q's
    conditions per attribute path (path () when it reads q whole), each
    read from the walk; cached per policy with the walk's Deps; a callee
    reached again inside its own walk refuses."""
    if not isinstance(fn, _types.FunctionType):
        raise Unclassified((line, f"{getattr(fn, 'name', fn)!r} takes a handed "
                                  "instance whole, a definition rule K's A5 "
                                  "clause does not walk"))
    pol = policy if _inspect.iscoroutinefunction(fn) else _plain_policy(policy)
    memo = pol.__dict__.setdefault("_bound_fx", {})
    key = (id(fn), q)
    hit = memo.get(key)
    if hit is not None and hit[0] is fn and hit[2].valid():
        _ib.carry(hit[2])
        return hit[1]
    stack = pol.__dict__.setdefault("_bound_stack", set())
    if key in stack:
        raise Unclassified((line, f"{fn.__name__}'s parameter {q} is handed "
                                  "whole into its own walk, a cycle rule K's "
                                  "A5 clause refuses"))
    scope = _ib._owner_module(fn)
    if scope is None:
        raise Unclassified((line, f"{fn.__name__}: not a function of a module"))
    stack.add(key)
    try:
        with _ib.recording() as deps:
            _ib.observe_chain(fn)
            eff = def_effects(_helper_tree(fn), scope, pol, fn.__name__,
                              source=source_of(fn), receivers=True,
                              param_values={q: ("A", q, (), False)})
    finally:
        stack.discard(key)
    out = []
    for e in sorted(eff):
        if not e.startswith("receiver:"):
            continue
        _r, dotted, g = e.split(":", 2)
        root, *rest = dotted.split(".")
        if root == q:
            out.append((tuple(rest), g))
    memo[key] = (fn, out, deps)
    return out


def _bound_method(n, group, visitor):
    """Rules W, P and K at a method call `n` of a span walked on its own:
    False when its receiver is no bound form; else the receiver discharged
    (a local bound by rule K-m, or one attribute of a K instance by rule
    K-a), marked with the method's name as ".<name>" for the callee, or
    refused."""
    got = visitor.b.bound_value(n.func.value, n.lineno)
    if got is None:
        return False
    F, d, root, var = got
    line = F.__code__.co_firstlineno + n.lineno - d.lineno
    callee = "." + n.func.attr
    if root[0] == "KM":
        BOUND_MARKS.append(("K-m", F, line, callee, var, group, root[1]))
        return True
    K, mod = root[1], root[2]
    if len(root[3]) != 1:
        raise Unclassified((n.lineno, f"a method call {_ast.unparse(n.func)} "
                                      f"on {var}, an instance of "
                                      f"{K.__qualname__}, at a path rule K-a "
                                      "does not read"))
    visitor.b.k_attr(K, mod, root[3][0], n.lineno)
    BOUND_MARKS.append(("K-a", F, line, callee, var + "." + root[3][0], group,
                        K))
    return True


def _bound_discharge(call, fn, arg, p, path, group, visitor):
    """Rules W, P and K at a span walked on its own: False when `arg` is no
    bound form (Bindings.bound_value); else its condition on callee `fn`'s
    parameter p at `path` discharged, every discharge marked in BOUND_MARKS
    with the span's function, the call's line in its source, the callee,
    the rule, the frame path and the group, or refused."""
    got = visitor.b.bound_value(arg, call.lineno)
    if got is None:
        return False
    F, d, root, var = got
    line = F.__code__.co_firstlineno + call.lineno - d.lineno
    if root[0] == "KM":
        g = "deep" if path else group
        BOUND_MARKS.append(("K-m", F, line, fn, var, g, root[1]))
        return True
    K, mod = root[1], root[2]
    full = root[3] + path
    if full:
        items = [(full, group)]
    else:
        items = _bound_conditions(fn, visitor.p, p, call.lineno)
    for sub, g in items:
        if len(sub) != 1:
            raise Unclassified((call.lineno, f"a call of {fn.__name__} whose "
                                             f"{p} at {'.'.join(sub) or 'whole'}"
                                             f" is read from {var}, an instance"
                                             f" of {K.__qualname__}, at a path "
                                             "rule K-a does not read"))
        visitor.b.k_attr(K, mod, sub[0], call.lineno)
        BOUND_MARKS.append(("K-a", F, line, fn, var + "." + sub[0], g, K))
    return True


# --- round 11, rule N (rulings FOUR-R11-A10 (1), FOUR-R11-A14 (2)) -------

def _n_site(b):
    """(F, d, off) for the definition d walked under bindings `b`: F the
    module's binding of d's name, a plain function whose code is named so
    and whose own source parses to d; off maps a line of the walked source
    to F's file line. None for any other walk (a planted or composed
    definition keeps today's refusals)."""
    d = b.where if b.has_fn else b.span_def
    mod = b.scope
    if (not isinstance(d, (_ast.FunctionDef, _ast.AsyncFunctionDef))
            or type(mod) is not _types.ModuleType):
        return None
    F = vars(mod).get(d.name, _MISSING)
    _ib.observe(mod, d.name, F)
    if type(F) is not _types.FunctionType or F.__code__.co_name != d.name:
        return None
    mine = b.__dict__.get("_n_dump")
    if mine is None or mine[0] is not d:
        mine = b.__dict__["_n_dump"] = (d, _ast.dump(d))
    code = F.__code__
    own = _N_DUMPS.get(id(code))
    if own is None or own[0] is not code:
        try:
            own = (code, _ast.dump(_helper_tree(F)))
        except (Unclassified, OSError, TypeError, SyntaxError):
            own = (code, None)
        _N_DUMPS[id(code)] = own
    if mine[1] != own[1]:
        return None
    first = d.decorator_list[0].lineno if d.decorator_list else d.lineno
    return F, d, code.co_firstlineno - first


_N_DUMPS = {}


def _n_named(b, form, name):
    """Whether a named member of form `form` names `name` in a function
    spelled as the definition `b` walks (a cheap test before _n_site)."""
    d = b.where if b.has_fn else b.span_def
    dn = getattr(d, "name", None)
    return any(k[1] == form and k[3] == name
               and getattr(k[0], "__name__", None) == dn for k in N_MEMBERS)


def _member_arg(call, fn, arg, p, path, group, visitor):
    """Rule N at a receiver condition of callee `fn`'s parameter p: False
    unless the call stands in a named member's function and hands that
    parameter; else discharged by bound (_n_discharge) or refused."""
    if not N_MEMBERS or path or not _n_named(visitor.b, "arg", p):
        return False
    site = _n_site(visitor.b)
    if site is None:
        return False
    F, _d, off = site
    key = (F, "arg", fn, p)
    if key not in N_MEMBERS:
        return False
    return _n_discharge(key, call.lineno + off, _ast.unparse(arg), group)


def _member_method(n, group, visitor):
    """Rule N at method call `n`: False unless its receiver is a Name a
    named member names in the walked function; else discharged by bound
    (_n_discharge) or refused."""
    if (not N_MEMBERS or not isinstance(n.func.value, _ast.Name)
            or not _n_named(visitor.b, "method", n.func.value.id)):
        return False
    site = _n_site(visitor.b)
    if site is None:
        return False
    F, _d, off = site
    key = (F, "method", "." + n.func.attr, n.func.value.id)
    if key not in N_MEMBERS:
        return False
    return _n_discharge(key, n.lineno + off, n.func.value.id, group)


def _member_callee(n, form, visitor):
    """Rule N member (B) (ruling FOUR-R11-A20 (1)) at call `n`, which the
    visitor would refuse ("a call ..." / "a method call this walk does not
    classify"): False unless a named member of form `form` names this
    callee in the walked function (form "call": a Name callee; form
    "result": a method whose receiver is a call of the member's method);
    else discharged by bound (_n_discharge: spelling, bindings, census) and
    marked, or refused. The caller then walks the arguments and the
    receiver as for any call; no provenance is assigned."""
    if not N_MEMBERS:
        return False
    if form == "call":
        callee = name = n.func.id
        line = n.lineno
    else:
        recv = n.func.value
        if not (isinstance(recv, _ast.Call)
                and isinstance(recv.func, _ast.Attribute)):
            return False
        callee, name = "." + n.func.attr, recv.func.attr
        line = n.func.end_lineno
    d = visitor.b.where if visitor.b.has_fn else visitor.b.span_def
    dn = getattr(d, "name", None)
    if not any(k[1] == form and k[2] == callee and k[3] == name
               and getattr(k[0], "__name__", None) == dn for k in N_MEMBERS):
        return False
    site = _n_site(visitor.b)
    if site is None:
        return False
    F, _d, off = site
    key = (F, form, callee, name)
    if key not in N_MEMBERS:
        return False
    return _n_discharge(key, line + off, _ast.unparse(n), form)


def _n_discharge(key, line, spelled_got, group):
    """The static half of rule N at a member's site, then its mark: the
    member's spelling and group as named, each bound name holding its
    object, each census equal to its frozen rows; any difference refuses.
    No provenance is assigned (FOUR-R11-A10 (1)(a)); the mark is what the
    bound test observes (FOUR-R11-A4 (2)(e))."""
    F, _form, callee, name = key
    label, spelled, want, binds, census = N_MEMBERS[key]
    if spelled_got != spelled:
        raise Unclassified((line, f"rule N {label}: the member is spelled "
                                  f"{spelled_got}, not {spelled}"))
    if group != want:
        raise Unclassified((line, f"rule N {label}: the callee asks {group} "
                                  f"of {name}, the member names {want}"))
    for mod, nm, obj in binds:
        got = vars(mod).get(nm, _MISSING)
        # an absent binding is recorded as the binder's own absence, so the
        # walk cache stays valid while the name stays unbound (member (B))
        _ib.observe(mod, nm, _ib._MISSING if got is _MISSING else got)
        if got is not obj:
            raise Unclassified((line, f"rule N {label}: {nm} is not the "
                                      "object the member names"))
    for owner, nm, frozen in census:
        rows = _n_census(owner, nm)
        frozen = tuple(frozen)
        if rows != frozen:
            at = next((i for i, (x, y) in enumerate(zip(rows, frozen))
                       if x != y), min(len(rows), len(frozen)))
            got = rows[at] if at < len(rows) else "nothing"
            was = frozen[at] if at < len(frozen) else "nothing"
            raise Unclassified((line, f"rule N {label}: the census of {nm} in "
                                      f"{owner.__name__} differs at row {at}: "
                                      f"{got!r}, frozen {was!r}"))
    BOUND_MARKS.append(("N", F, line, callee, name, group, label))
    return True


_N_BINDERS = (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)


def _n_census(owner, name):
    """Rule N's static half (FOUR-R11-A10 (1)(a)): the rows of `name` in
    `owner`, read from source, no provenance assigned. A module: every
    occurrence of the Name (the top definition it stands in, its line there
    or 0 at module level, its context, its parent's text) and a row for
    every attribute or string spelling of it. A function: every occurrence
    of the Name in its own definition (line and column there, context, the
    field it stands in, the use around it, the statement's text), every
    other form that binds the name, or, for name "return", its own return
    statements (nested definitions and lambdas excluded), or, for a name
    ".m", every attribute m (member (B), FOUR-R11-A20 (1))."""
    if isinstance(owner, _types.ModuleType):
        tree = _module_tree(owner)
        if tree is None:
            raise Unclassified((0, f"rule N: {owner.__name__}: no source"))
        hit = _N_CENSUS.get((id(tree), name))
        if hit is not None and hit[0] is tree:
            return hit[1]
        idx = Bindings._name_index(None, tree)
        rows = [(top.name if top is not None else "<module>",
                 n.lineno - top.lineno if top is not None else 0,
                 type(n.ctx).__name__, _ast.unparse(par)[:160])
                for n, par, top, _nested in idx["name"].get(name, ())]
        rows += [("attr", ln) for ln in idx["attr"].get(name, ())]
        rows += [("str", c.lineno) for c, _s in idx["str"].get(name, ())]
        out = tuple(sorted(rows, key=repr))
        _N_CENSUS[(id(tree), name)] = (tree, out)
        return out
    code = owner.__code__
    hit = _N_CENSUS.get((id(code), name))
    if hit is not None and hit[0] is code:
        return hit[1]
    tree = _helper_tree(owner)
    par = {}
    for x in _ast.walk(tree):
        for c in _ast.iter_child_nodes(x):
            par[id(c)] = x
    rows = []
    if name == "return":
        todo = list(tree.body)
        while todo:
            x = todo.pop()
            if isinstance(x, _N_BINDERS + (_ast.Lambda,)):
                continue
            if isinstance(x, _ast.Return):
                rows.append((x.lineno, "return", _ast.unparse(x)[:200]))
            todo.extend(_ast.iter_child_nodes(x))
    if name.startswith("."):
        # member (B) (FOUR-R11-A20 (1)): every attribute spelled `name` in
        # the function's own definition (its last line and column there,
        # context, the expression around it)
        rows += [(x.end_lineno, x.end_col_offset, type(x.ctx).__name__,
                  _ast.unparse(par.get(id(x), x))[:200])
                 for x in _ast.walk(tree)
                 if isinstance(x, _ast.Attribute) and x.attr == name[1:]]
    for x in (_ast.walk(tree) if name != "return"
              and not name.startswith(".") else ()):
        if isinstance(x, _ast.Name) and x.id == name:
            u, p = x, par.get(id(x))
            while p is not None and (
                    (isinstance(p, (_ast.Attribute, _ast.Subscript))
                     and p.value is u)
                    or (isinstance(p, _ast.Call) and p.func is u)):
                u, p = p, par.get(id(p))
            field = next((f for f, v in _ast.iter_fields(p) if v is u or (
                isinstance(v, list) and any(y is u for y in v))), "?")
            st = p
            while st is not None and not isinstance(st, _ast.stmt):
                st = par.get(id(st))
            rows.append((x.lineno, x.col_offset, type(x.ctx).__name__,
                         type(p).__name__ + "." + field,
                         _ast.unparse(u)[:200],
                         _ast.unparse(st).split("\n")[0][:120]))
        elif ((isinstance(x, _ast.arg) and x.arg == name)
              or (isinstance(x, _N_BINDERS) and x.name == name)
              or (isinstance(x, (_ast.Global, _ast.Nonlocal))
                  and name in x.names)
              or (isinstance(x, _ast.alias)
                  and name in (x.name, x.asname))
              or (isinstance(x, _ast.ExceptHandler) and x.name == name)
              or (isinstance(x, (_ast.MatchAs, _ast.MatchStar))
                  and x.name == name)):
            rows.append((getattr(x, "lineno", 0), type(x).__name__))
    out = tuple(sorted(rows, key=repr))
    _N_CENSUS[(id(code), name)] = (code, out)
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

    def __init__(self, policy, params=(), permitted=frozenset(), helper=None,
                 opaque=frozenset(), bindings=None):
        self.p = policy
        self.b = (bindings if bindings is not None
                  else Bindings(policy.scope, session=policy.session,
                                grammar=getattr(policy, "grammar", None)))
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
            # the resolver in the census's one form, `<name>.b.<method>(...)`
            # (round 8, M7)
            kind, what = self.b.resolve(n.func.id, n.lineno)
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
            # round 11 (rule N member (B), ruling FOUR-R11-A20 (1)): a named
            # call whose callee's identity the bound test asserts at run
            # time; its arguments walked as any call's, marked
            if kind == "module" and _member_callee(n, "call", self):
                self._pure(n, name, written)
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
            eff = (frozenset() if self.b.module_accessor(fn, self.b.grammar)
                   is not None
                   else discharge_receivers(n, fn, plain_effects(fn, self.p),
                                            n.lineno, self))
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
                        n, self.b.callee, acc.func), self.b.grammar) is not None):
                # `<accessor>().f(...)`: a plain function of the module the
                # accessor returns, its body walked like any plain callee.
                fn = self._check(n, self.b.callee, n.func)
                if fn is None or _inspect.iscoroutinefunction(fn):
                    self.fail(n, f"a call this walk does not classify: {name}")
                self._plain_args(n, name, args)
                eff = discharge_receivers(n, fn, plain_effects(fn, self.p),
                                          n.lineno, self)
                if eff:
                    self.fail(n, f"a plain call of {name}, which takes "
                                 f"{', '.join(sorted(eff))}")
                self._spelled(n.func)
                self.p.met["plain function " + name] += 1
                self.effects.append(("call", "pure"))
                return
            # round 11 (rule N member (B), ruling FOUR-R11-A20 (1)): a named
            # method whose callee and receiver class the bound test asserts
            # by identity at run time, marked; its receiver is still read
            # below as any method's
            if (n.func.attr not in self.p.pure_methods
                    and not _member_callee(n, "result", self)):
                self.fail(n, f"a method call this walk does not classify: {name}")
            self.p.met["method ." + n.func.attr] += 1
            self._walked_nodes.add(id(n.func))
            if not self.b.is_root(n.func.value):
                # round 11 (F10, ruling FOUR-R11-A1 (3)): the receiver must
                # be exactly the type the method belongs to, by provenance
                group = receiver_group(n.func.attr)
                # round 11 (rules W, P and K): at a span walked on its own,
                # a receiver rooted at an exact frozen class instance is
                # discharged by rule K, marked (_bound_method); within a
                # walk that binds a handed instance, a receiver read from it
                # carries its path's condition (the A5 clause)
                bound = self.helper is None and _bound_method(n, group, self)
                # round 11 (rule N, ruling FOUR-R11-A10 (1)): a named
                # member's receiver is discharged by its bound, marked
                bound = bound or _member_method(n, group, self)
                prov = None if bound else receiver_provenance(
                    n.func.value, self.b, self.p)
                # each alternative of a union on its own (round 11, run 12)
                alts = [] if bound else _alts(prov)
                handed = [a for a in alts if _is_a(a)]
                alts = [a for a in alts if not _is_a(a)]
                if not all(_is_p(a) or receiver_meets(a, group) for a in alts):
                    self.fail(n, f"a method call {name} whose receiver the "
                                 "walk cannot prove builtin")
                for a in handed + alts:
                    if _is_a(a):
                        # round 11 (rule K's A5 clause): on the handed
                        # instance's path, carried to the walk's caller
                        if self.helper is None:
                            self.fail(n, f"a method call {name} on a handed "
                                         "instance outside the walk that "
                                         "binds it")
                        self.effects.append((_a_condition(a, group), "pure"))
                        continue
                    if not _is_p(a):
                        continue
                    g = "deep" if a[2] else group
                    if self.helper is None:
                        # a span walked on its own (no def_effects around
                        # it): no call site of it is walked to discharge
                        # the condition, so it is refused here, never
                        # dropped by a consumer that reads other shapes
                        self.fail(n, f"a method call {name} on the parameter "
                                     f"{', '.join(a[1])}, a receiver no "
                                     "walked call site discharges")
                    for q in a[1]:
                        self.effects.append((f"receiver:{q}:{g}", "pure"))
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
            kind = self._check(n, self.b.execute_kind, call, self.p.sql)
            if kind not in ("read", "lock"):
                # the frozen table answers read, lock or write; anything
                # else is a write
                kind = "write"
            self.effects.append(("sql", kind))
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
            # round 11 (F10): the conditions its consumer declared, read
            # from its body first, discharged at this call
            odef = self._check(n, self.b.opaque_def, call.func, self.opaque)
            got = self.p.__dict__.get("opaque_receivers", {}).get(id(odef))
            if got is not None and got[0] is odef and got[1]:
                discharge_receivers(call, odef, got[1], n.lineno, self)
            self.effects.append((f"helper:{name}", "opaque"))
            return
        fn = self._check(n, self.b.callee, call.func)
        if fn is None or not _inspect.iscoroutinefunction(fn):
            self.fail(n, f"an awaited call this walk does not classify: {name}")
        self._helper_args(n, call, fn)
        if self.p.helper_hook is not None and self.helper is None:
            # round 11 (F10): the helper's receiver conditions are
            # discharged at this call before its hook reads its kind
            discharge_receivers(call, fn, helper_effects(fn, self.p),
                                n.lineno, self)
            self.p.met["helper by the policy's hook"] += 1
            self.effects.append((f"helper:{fn.__code__.co_name}",
                                 self.p.helper_hook(fn)))
            return
        eff = discharge_receivers(call, fn, checked_callbacks(
            call, fn, helper_effects(fn, self.p), n.lineno), n.lineno, self)
        ends = eff & {"rollback-then-raise", "rollback"}
        if ends and id(n) in self.caught:
            self.fail(n, f"a helper that ends the transaction and raises "
                         f"({fn.__code__.co_name}), awaited inside a try that catches")
        if ends:
            # Propagated (finding closed_walk:825): the caller's effects carry
            # the end its helper takes.
            self.effects.append((f"helper-end:{fn.__code__.co_name}",
                                 sorted(ends)[0]))
        kinds = eff & {"read", "lock", "write"}
        self.effects.append((f"helper:{fn.__code__.co_name}",
                             "write" if "write" in kinds else "lock" if "lock" in kinds
                             else "read" if "read" in kinds else "pure"))


def expr_effects(node, policy, opaque=frozenset(), bindings=None):
    """The (shape, effect) list of evaluating `node` (Visitor) under
    `bindings`, the enclosing function's (finding a1:665: the formation
    walk's expressions resolved names in the module); raises Unclassified
    naming the construct and its line."""
    return list(Visitor(policy, opaque=opaque,
                        bindings=bindings).accept(node).effects)


def checked_callbacks(call, fn, effects, line):
    """`effects` of helper `fn` at the call `call`, without its callback
    parameters, after checking that the call binds none of them to a
    value: an awaited callback is not a shape the walk classifies. A
    callback parameter with a default other than None is refused at the
    helper (helper_effects)."""
    params = list(_inspect.signature(fn).parameters)
    out = set(e for e in effects if not e.startswith("callback:"))
    # round 11 (ruling FOUR-R11-A10 (3)): `effects` is a frozenset; the
    # callback conditions ("callback:<param>") are refused in the helper's
    # parameter order, then by their text (_in_param_order reads the
    # parameter after the first colon), never in the set's hash order
    conds = [e for e in effects if e.startswith("callback:")]
    conds = _in_param_order(conds, params)
    for e in conds:
        name = e.split(":", 1)[1]
        at = params.index(name)
        if any(k.arg == name or k.arg is None for k in call.keywords) or len(
                call.args) > at or any(isinstance(a, _ast.Starred) for a in call.args):
            raise Unclassified((line, f"a callback passed to {fn.__name__} "
                                      f"({name}), which the walk does not "
                                      "classify"))
    return frozenset(out)


def _helper_tree(fn):
    # Round 11 (FIX-R11-ID): the source of the function's OWN code object
    # (inspect.getsource(fn) follows __wrapped__ to another body).
    tree = _ast.parse(_textwrap.dedent(_inspect.getsource(fn.__code__)))
    defs = [n for n in tree.body if isinstance(n, (_ast.AsyncFunctionDef,
                                                   _ast.FunctionDef))]
    if len(defs) != 1:
        raise Unclassified((0, f"{fn.__name__}: not one function definition"))
    return defs[0]


def helper_effects(fn, policy, stack=()):
    """helper_effects of a function object (cached per policy).

    Round 11 (ruling FOUR-R10-A2, FIX-R11-ID; finding closed_walk:1949): the
    cache is keyed by the function OBJECT, never by its writable
    __module__/__qualname__, and an entry holds the identity_binder.Deps of
    its walk: every module-scope binding and every callee chain the walk
    read. A hit is honoured only while every one still binds the recorded
    object (`main.int = writer` after the cache is warm drops the entry and
    the body is walked again); a hit also carries its Deps into every
    enclosing recording. The scope is the module whose namespace IS the
    function's globals."""
    key = id(fn)
    hit = policy.helpers.get(key)
    if hit is not None:
        if hit[0] is fn and hit[2].valid():
            _ib.carry(hit[2])
            return hit[1]
        del policy.helpers[key]
    if key in policy.walking:
        # A helper that awaits itself: its effects are the ones its other
        # statements give, which the outer walk of it is collecting.
        return frozenset()
    scope = _ib._owner_module(fn) if isinstance(fn, _types.FunctionType) else None
    if scope is None:
        raise Unclassified((0, f"{getattr(fn, '__name__', fn)!r}: not a "
                               "function of a module"))
    policy.walking.add(key)
    try:
        with _ib.recording() as deps:
            _ib.observe_chain(fn)
            out = def_effects(_helper_tree(fn), scope, policy,
                              fn.__name__, source=source_of(fn),
                              receivers=True)
    finally:
        policy.walking.discard(key)
    policy.helpers[key] = (fn, out, deps)
    return out


def def_effects(d, scope, policy, label, opaque=frozenset(), rollbacks=False,
                ends=frozenset(), source=None, receivers=False,
                param_values=None):
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
    a rollback means for it).

    Round 11 (F10): a receiver condition on one of the helper's parameters
    ("receiver:<p>:<group>") is in the result only with `receivers`, which
    a caller passes when it discharges each at the helper's walked call
    sites (helper_effects, whose results only Visitor's call branches
    read); otherwise the walk refuses, so a consumer that reads named
    effects can never drop one."""
    fn = _types.SimpleNamespace(__name__=label)
    if policy.grammar is not None:
        # Admitted by the grammar BEFORE any reading below (ruling
        # REHEARSAL-FOUR-R6 (1)(b)); `source` is (file, line offset).
        f, off = (source if source is not None
                  else (getattr(scope, "__name__", "?"), 0))
        policy.grammar.admit(d, f, off)
    sub = Policy(scope, policy.pure_calls, policy.pure_methods,
                 policy.pure_awaits, policy.sql, policy.session)
    sub.grammar = policy.grammar
    sub.helpers = policy.helpers
    sub.walking = policy.walking
    sub.met = policy.met
    sub._ret_joins = policy.__dict__.setdefault("_ret_joins", {})
    sub.opaque_receivers = policy.__dict__.setdefault("opaque_receivers", {})
    sub._plain_owner = getattr(policy, "_plain_owner", policy)
    for n in _ast.walk(d):
        if isinstance(n, _ast.ImportFrom) and (not n.module or n.level):
            raise Unclassified((0, f"{fn.__name__}: a relative import"))
    # The helper's own bindings: every name the walk reads in it resolves
    # there, one binding per name (ruling REHEARSAL-FOUR-R5 item 2).
    b = Bindings(scope, d, session=policy.session, grammar=policy.grammar,
                 param_roots=policy.param_roots)
    # round 11 (rule K's A5 clause): a parameter bound to a handed instance
    b.param_values = dict(param_values or {})
    params = [a.arg for a in d.args.posonlyargs + d.args.args + d.args.kwonlyargs]
    if d.args.vararg or d.args.kwarg:
        raise Unclassified((0, f"{fn.__name__} takes *args or **kwargs"))
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
    v = Visitor(sub, params, frozenset(permitted), fn, opaque, bindings=b)
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
        elif sh.startswith("receiver:"):
            if not receivers:
                raise Unclassified((0, f"{fn.__name__}: {sh}, a receiver "
                                       "condition no walked call site "
                                       "discharges"))
            effects.add(sh)
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
